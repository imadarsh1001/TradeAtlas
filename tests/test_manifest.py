"""Source-manifest enforcement: coverage, hash integrity, unmanifested-file failure."""

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MANIFEST_PATH = ROOT / "data" / "manifest.json"
PINNED_DIRS = [ROOT / "data" / "raw", ROOT / "config"]
REQUIRED_FIELDS = ["path", "sha256", "source", "retrieved_date", "terms"]


def _manifest_entries() -> dict:
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    return {entry["path"]: entry for entry in manifest["files"]}


def _pinned_files() -> list[Path]:
    files = []
    for directory in PINNED_DIRS:
        files.extend(sorted(p for p in directory.rglob("*") if p.is_file()))
    return files


def test_manifest_exists_and_parses():
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    assert isinstance(manifest["files"], list) and manifest["files"]


def test_every_pinned_file_is_manifested():
    entries = _manifest_entries()
    missing = [p.relative_to(ROOT).as_posix() for p in _pinned_files() if p.relative_to(ROOT).as_posix() not in entries]
    assert missing == [], f"Files without a manifest entry: {missing}"


def test_manifest_entries_have_all_fields():
    entries = _manifest_entries()
    for path, entry in entries.items():
        for field in REQUIRED_FIELDS:
            assert entry.get(field), f"{path}: manifest field '{field}' is missing or empty"


def test_hashes_match_file_content():
    entries = _manifest_entries()
    for path, entry in entries.items():
        file = ROOT / path
        assert file.exists(), f"Manifest entry points to a missing file: {path}"
        assert path.startswith(("data/raw/", "config/")), f"Manifest entry outside pinned dirs: {path}"
        actual = hashlib.sha256(file.read_bytes()).hexdigest()
        assert actual == entry["sha256"], f"{path}: content changed since manifest (expected {entry['sha256'][:12]}…, got {actual[:12]}…)"
