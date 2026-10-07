# Release validation

Validation date: 2026-10-07. These checks describe the delivered project and one owner's authorized workspace, rather than certifying every possible deployment environment.

## Offline contracts and package

Python 3.12.14: **21 tests passed**, covering monthly/leap-year windows, complete pagination and changed totals, credential echo removal, safe HTTP failures, immutable content identity, finite values, source revisions, physical validation, NASA fill values, exact UTC weather keys, and EIA hour-ending conversion at a day boundary.

Ruff lint and formatting checks passed. Python source and task notebooks compiled. The 1.0.0 source archive and wheel built; the wheel installed without runtime dependencies and its `energy-ingest --help` entry point executed. These tests require no source key. GitHub Actions repeats offline validation and packaging on Linux.

## Cloud integration

The isolated fixture notebook creates a fresh `energy_validation_<random>` schema and its own managed Volume. It never uses the analytical schema for destructive fixture checks. It verifies:

1. EIA credential echoes disappear before persistence.
2. Replaying a completed collection preserves Silver uniqueness.
3. Bronze remains unique by source and content hash.
4. A revised measurement replaces the previous value.
5. An invalid revision replaces a formerly valid measurement as invalid.
6. A removed source key disappears only inside the authoritative window.
7. Quarantine replay does not accumulate duplicate rejections.
8. Failure while copying a publication keeps the previous pointer and consumer results.
9. A retry creates a fresh immutable release ID.
10. Additive Gold schema evolution is available after a complete publication.

See [`90_integration_validation.py`](../notebooks/90_integration_validation.py) for the runnable assertions. A previously failed dbt region-seed check also demonstrated the orchestration gate: publication was skipped until the seed was corrected and the failed tasks were repaired.

## Historical verification

All ten fixture checks passed on serverless Databricks. The full historical job completed all four tasks successfully. dbt-databricks 1.12.6 / dbt-core 1.12.5 built five Gold tables and a three-row seed, with **13 passing data tests** (`PASS=19`, zero warnings/errors/skips).

The full collection covers interval starts in `[2024-01-01, 2026-01-02)` UTC, with enough trailing hours to complete the 2025 local calendar year. It contains 149 sanitized immutable source snapshots. EIA acquisition labels are shifted appropriately at both query boundaries; NASA requests explicitly use UTC.

The aggregate evidence exporter re-executes all seven dashboard datasets, annual summaries, UTC grain/coverage checks, and twelve region/day checks at the 2024/2025 spring and autumn clock changes. It refuses output if the publication pointer changes while the queries run. Exact coverage and analytical results are recorded in [analysis](analysis.md).

## Security and display boundaries

Before publication, tracked content and the Git index were scanned for common credential patterns, forbidden secret/auth/data paths, and the exact EIA key without printing its value. The final Git history is scanned before push. The project scope was inspected: one explicit owner ACL. The dashboard publication has `embed_credentials=false`; its workspace remains access-controlled. CI has read-only contents permission and needs no EIA or Databricks key.

The Databricks dashboard was deployed and published through the API, and its dataset queries were executed through the SQL warehouse. **The native dashboard canvas and filter behavior were not visually verified**, because the owner chose to keep their existing browser login. Static Python figures were rendered and visually inspected separately. Native UI review is a remaining display check, not an unavailable data-source connection.
