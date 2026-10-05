"""Loading documents and storing user uploads."""

from pathlib import PurePath

from sqlalchemy import delete, select, update
from sqlalchemy.orm import Session

from anchor.extraction.schema import UPLOAD_DOC_TYPE
from anchor.models import (
    Chunk,
    ExtractedFact,
    ExtractionRun,
    ReviewQueue,
    SourceDocument,
)
from anchor.storage import RawStore
from anchor.text import EXTENSIONS, MEDIA_TYPES, document_to_text

MAX_UPLOAD_BYTES = 25 * 1024 * 1024


class UploadError(ValueError):
    pass


def load_text(store: RawStore, document: SourceDocument) -> str:
    """The canonical text of a document: every span offset refers to this string."""
    return document_to_text(store.get(document.raw_path), document.media_type)


def media_type_for(filename: str, declared: str | None) -> str:
    """Trust the file extension first: browsers often send a generic type for .md or .docx."""
    by_extension = EXTENSIONS.get(PurePath(filename).suffix.lower())
    if by_extension:
        return by_extension
    if declared in MEDIA_TYPES:
        return declared
    supported = ", ".join(sorted(EXTENSIONS))
    raise UploadError(f"Unsupported file type. Supported: {supported}")


def store_upload(
    session: Session,
    store: RawStore,
    filename: str,
    content: bytes,
    declared: str | None,
    *,
    previous: SourceDocument | None = None,
) -> tuple[SourceDocument, bool]:
    """Save an uploaded file, optionally as the next version of `previous`.

    Returns the document and whether identical content was already stored.
    """
    if previous is not None:
        if previous.doc_type != UPLOAD_DOC_TYPE:
            raise UploadError("Only uploaded documents can get a new version.")
        if latest_version(session, previous).id != previous.id:
            raise UploadError("A newer version already exists; add the version to that one.")
    if not content:
        raise UploadError("The file is empty.")
    if len(content) > MAX_UPLOAD_BYTES:
        raise UploadError(f"The file is larger than {MAX_UPLOAD_BYTES // 2**20} MB.")
    media_type = media_type_for(filename, declared)
    blob = store.put(content)
    existing = session.scalar(
        select(SourceDocument).where(SourceDocument.content_hash == blob.content_hash)
    )
    if existing is not None:
        if previous is not None:
            raise UploadError("This file is identical to a version that is already stored.")
        return existing, True
    try:
        text = document_to_text(content, media_type)
    except Exception as exc:  # parsers raise many types for corrupt files
        raise UploadError(f"The file could not be read: {exc}") from exc
    if not text.strip():
        raise UploadError("No text found. Scanned PDFs need OCR, which is not supported yet.")
    document = SourceDocument(
        source_url=f"upload://{filename}",
        doc_type=UPLOAD_DOC_TYPE,
        title=PurePath(filename).name,
        publisher="Uploaded document",
        media_type=media_type,
        supersedes_id=previous.id if previous is not None else None,
        content_hash=blob.content_hash,
        raw_path=blob.relative_path,
    )
    session.add(document)
    session.commit()
    return document, False


def version_chain(session: Session, document: SourceDocument) -> list[SourceDocument]:
    """All versions of a document, oldest first."""
    root = document
    while root.supersedes_id is not None:
        root = session.get(SourceDocument, root.supersedes_id)
    chain = [root]
    while (
        newer := session.scalar(
            select(SourceDocument).where(SourceDocument.supersedes_id == chain[-1].id)
        )
    ) is not None:
        chain.append(newer)
    return chain


def latest_version(session: Session, document: SourceDocument) -> SourceDocument:
    return version_chain(session, document)[-1]


def delete_upload(session: Session, store: RawStore, document: SourceDocument) -> int:
    """Remove an uploaded document with every version, fact, run and chunk.

    The no-deletion rule protects results the system produced from a source; it
    does not override a user's right to remove a file they uploaded. Filings from
    EDGAR are never deleted. Returns the number of versions removed.
    """
    if document.doc_type != UPLOAD_DOC_TYPE:
        raise UploadError(
            "Only uploaded documents can be deleted; filings are kept as audit trail."
        )
    chain = version_chain(session, document)
    ids = [version.id for version in chain]
    fact_ids = select(ExtractedFact.id).where(ExtractedFact.document_id.in_(ids))
    session.execute(delete(ReviewQueue).where(ReviewQueue.fact_id.in_(fact_ids)))
    session.execute(
        update(ExtractedFact).where(ExtractedFact.document_id.in_(ids)).values(superseded_by=None)
    )
    session.execute(delete(ExtractedFact).where(ExtractedFact.document_id.in_(ids)))
    session.execute(delete(ExtractionRun).where(ExtractionRun.document_id.in_(ids)))
    session.execute(delete(Chunk).where(Chunk.document_id.in_(ids)))
    session.execute(
        update(SourceDocument).where(SourceDocument.id.in_(ids)).values(supersedes_id=None)
    )
    paths = [version.raw_path for version in chain]
    session.execute(delete(SourceDocument).where(SourceDocument.id.in_(ids)))
    session.commit()
    for path in paths:
        still_used = session.scalar(
            select(SourceDocument.id).where(SourceDocument.raw_path == path)
        )
        if still_used is None:
            store.remove(path)
    return len(chain)
