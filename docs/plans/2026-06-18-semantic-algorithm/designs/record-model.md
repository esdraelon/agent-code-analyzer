# Design: Semantic Record Model

## Purpose

Define the canonical record shape for every semantic scope: package, module, file, class, method, and chunk.

## How it works

Each record is an immutable description unit with a stable identity and enough metadata to refresh it later without guessing. The record carries:

- project identifier
- scope type
- scope identity
- file path
- symbol path where relevant
- line range anchors
- parent scope reference
- source fingerprint
- description text
- update mode metadata

The record itself should not know how sqlite or Qdrant stores it. A mapper translates the value object into storage payloads.

## How it is used

- The mass-ingestion pipeline creates records.
- The diff-refresh pipeline updates or invalidates records.
- Retrieval uses the metadata to return useful anchors, not just text similarity.

## Design pattern

**Value Object + Data Mapper**

Why it fits:
- the record should be easy to compare and test
- storage concerns belong outside the record type
- the same record object can feed sqlite, vector storage, and tests

## Verification targets

- Every semantic scope fits the same record model.
- Stable identity does not change across refreshes unless the scope truly changes.
- Storage adapters can be tested without constructing the whole pipeline.
