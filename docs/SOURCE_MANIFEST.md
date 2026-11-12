# Source Manifest — Maintenance Note

`data/manifest.json` records provenance for every pinned file under `data/raw/` and `config/`: SHA-256 hash, source, retrieval date, and terms. The check in `tests/test_manifest.py` runs with the suite, so **`uv run python -m pytest tests/ -q` fails loudly if provenance drifts**.

## When you add or replace a data or config file

1. Place the file in `data/raw/` or `config/`.
2. Add an entry to `data/manifest.json` → `files` with:
   - `path` (POSIX-style, relative to repo root)
   - `sha256` (compute: `python -c "import hashlib;print(hashlib.sha256(open(r'<file>','rb').read()).hexdigest())"`)
   - `source` (URL or publisher revision)
   - `retrieved_date` (YYYY-MM-DD)
   - `terms` (licence/usage note; "presumed — confirm before external distribution" is acceptable only as an explicit interim statement)
3. Re-run the suite — `test_hashes_match_file_content` must pass.

## Rules

- A file without a manifest entry cannot pass the suite (`test_every_pinned_file_is_manifested` fails, naming the file).
- Changed content without an updated hash cannot pass (`test_hashes_match_file_content` fails, naming the file).
- The manifest itself lives in version control alongside the files it describes (source-manifest spec, OpenSpec change `core-stabilization-evidence-retrofit`).
