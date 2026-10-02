"""Content-addressed store for raw documents.

Bytes are written exactly as received and never rewritten, so every span offset
computed later can be checked against the same input.
"""

import hashlib
import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class StoredBlob:
    content_hash: str
    relative_path: str


def content_hash(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


class RawStore:
    def __init__(self, root: Path) -> None:
        self._root = root

    def put(self, content: bytes) -> StoredBlob:
        digest = content_hash(content)
        relative = f"{digest[:2]}/{digest}"
        target = self._root / relative
        if not target.exists():
            target.parent.mkdir(parents=True, exist_ok=True)
            # Write-then-rename: a crash mid-write must not leave a truncated blob
            # under a hash that claims to describe the full content.
            temporary = target.with_suffix(f".{os.getpid()}.tmp")
            temporary.write_bytes(content)
            temporary.replace(target)
        return StoredBlob(content_hash=digest, relative_path=relative)

    def get(self, relative_path: str) -> bytes:
        return (self._root / relative_path).read_bytes()
