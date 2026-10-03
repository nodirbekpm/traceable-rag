"""Loading documents and storing user uploads."""

from pathlib import PurePath

from sqlalchemy import select
from sqlalchemy.orm import Session

from anchor.extraction.schema import UPLOAD_DOC_TYPE
from anchor.models import SourceDocument
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
    session: Session, store: RawStore, filename: str, content: bytes, declared: str | None
) -> tuple[SourceDocument, bool]:
    """Save an uploaded file. Returns the document and whether it was already known."""
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
        content_hash=blob.content_hash,
        raw_path=blob.relative_path,
    )
    session.add(document)
    session.commit()
    return document, False
