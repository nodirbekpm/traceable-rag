import hashlib
from pathlib import Path

from anchor.storage import RawStore, content_hash


def test_hash_is_sha256_of_the_raw_bytes() -> None:
    content = b"<html>Item 2.02 Results of Operations</html>"

    assert content_hash(content) == hashlib.sha256(content).hexdigest()


def test_put_stores_bytes_unchanged(tmp_path: Path) -> None:
    store = RawStore(tmp_path)
    # CRLF and non-UTF-8 bytes must survive: span offsets depend on the exact input.
    content = b"line one\r\nline two\xa0\xff"

    blob = store.put(content)

    assert store.get(blob.relative_path) == content
    assert blob.relative_path == f"{blob.content_hash[:2]}/{blob.content_hash}"


def test_put_is_idempotent(tmp_path: Path) -> None:
    store = RawStore(tmp_path)

    first = store.put(b"same")
    second = store.put(b"same")

    assert first == second
    assert len([p for p in tmp_path.rglob("*") if p.is_file()]) == 1


def test_different_content_gets_a_different_hash(tmp_path: Path) -> None:
    store = RawStore(tmp_path)

    assert store.put(b"revenue $4.2M").content_hash != store.put(b"revenue $4.3M").content_hash
