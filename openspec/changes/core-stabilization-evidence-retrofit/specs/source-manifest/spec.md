# Spec Delta

## Purpose

Every pinned data and configuration file is traceable to its origin — content hash, source revision, retrieval date, and terms — so any figure TradeAtlas publishes can be reproduced from a verified source, and silent data drift is impossible.

## ADDED Requirements

### Requirement: Manifest coverage of pinned files
Every file under `data/raw/` and `config/` SHALL have a manifest entry recording: file path, SHA-256 hash, source (URL or publisher revision), retrieval date, and applicable terms/licence. The manifest SHALL live in version control alongside the files it describes.

#### Scenario: Every pinned file is manifested
- **WHEN** the manifest check runs against `data/raw/` and `config/`
- **THEN** each file found there has a manifest entry with all required fields populated

#### Scenario: Unmanifested file is flagged
- **WHEN** a data or config file exists without a manifest entry
- **THEN** the check fails, naming the file

### Requirement: Hash integrity
Each manifest SHA-256 hash SHALL match the current content of its file; a mismatch SHALL fail the check so any content change is caught.

#### Scenario: Changed file is detected
- **WHEN** a pinned file's content differs from its recorded hash
- **THEN** the check fails, naming the file and the expected vs. actual hash

### Requirement: Manifest maintenance rule
Adding or replacing a file under `data/raw/` or `config/` SHALL require a manifest update in the same change; the check SHALL enforce this so no unmanifested data can merge.

#### Scenario: New data file without manifest entry cannot pass
- **WHEN** a new extract or config file is added and the manifest is not updated
- **THEN** the check fails with the file name and the instruction to record its provenance
