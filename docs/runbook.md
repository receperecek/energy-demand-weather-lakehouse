# Operations runbook

## Preconditions

Python 3.11+, Git, the current Databricks CLI and an authorized Unity Catalog workspace with serverless jobs and a SQL warehouse. Source access needs only an EIA API key; NASA POWER requires no API key. The deployment identity must be able to create the selected schema/managed Volume, write its tables and use the warehouse. Paid workspace compute can incur costs; choose a budget and auto-stop policy before scheduling.

Authenticate with `databricks auth login --host <your-workspace-url> --profile portfolio` and verify the profile using `databricks current-user me --profile portfolio`. Do not publish authentication output or host-specific deployment files.

Create a project schema and managed raw Volume in the selected catalog:

```sql
CREATE SCHEMA IF NOT EXISTS workspace.energy_platform;
CREATE VOLUME IF NOT EXISTS workspace.energy_platform.raw;
```

Create the `energy-platform` secret scope with only the deployment identity as its initial manager, and add an `eia-api-key` secret through the Databricks UI or SDK. Never put the key in shell command arguments, a notebook literal, the bundle, or a GitHub Actions secret for this project's CI. Review scope ACLs before reusing an existing scope.

## Local checks

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e '.[dev]'
.\.venv\Scripts\python.exe -m pytest
.\.venv\Scripts\python.exe scripts/check_secrets.py --history
```

The scanner expects a Git checkout. Its history flag checks reachable commits. The tests use fixtures and need no cloud credentials. They do not emulate every runtime property of serverless Spark; cloud integration checks are necessary before release.

## Deploy and backfill

```powershell
databricks bundle validate --profile portfolio --var warehouse_id=<warehouse-id>
databricks bundle deploy --profile portfolio --var warehouse_id=<warehouse-id>
databricks bundle run energy_pipeline --profile portfolio --var warehouse_id=<warehouse-id> --params start_date=2024-01-01,end_date=2026-01-02
```

The exclusive UTC end includes enough hours to complete 2025-12-31 in the selected local time zones. Analytical report filters use local dates from 2024-01-01 through 2025-12-31. The prior local boundary date is flagged incomplete, rather than silently counted as a complete day.

The development target isolates files under the current user's home. Its schedule is paused by default. For an unattended schedule, create a production target with a deliberately owned workspace path and appropriate run-as identity. Change `pause_status` only after a bounded run, a replay and publication checks pass. Daily default execution re-fetches a 14-day source revision window with a seven-day lag; this is a historical monitoring dashboard, not real-time telemetry.

## Failure handling

| Failure | Response |
|---|---|
| 401/403 from EIA | Check/regenerate the provider key and update the scope; do not print it. |
| 429/5xx | Let bounded retries finish. If exhausted, wait and retry the same window; do not parallelize or rotate keys. |
| Pagination total changes | Retry the bounded window later; never publish a partial collection. |
| NASA hour keys or UTC contract fail | Check source latency and requested dates. Contract failures stop acquisition. |
| Invalid measurements | Inspect quarantine reasons and coverage. Do not impute zero demand or clamp negative storage generation. |
| Unknown fuel category | Verify EIA metadata, update the controlled mapping, test, replay the affected snapshots. |
| dbt model/test failure | Repair from Silver or dbt after fixing the cause. Consumer views retain the last successful publication. |
| Partial publication | Inspect the active pointer. Failed release copies may remain; rerun publication to a new release ID. |

Use a successful ingestion manifest ID to replay `02_silver` without downloading again. Only replay complete manifests. Rerunning the same authoritative window must preserve Silver grain and aggregates; Bronze remains unique by source/hash. Quarantine rows for that ingestion are replaced, rather than appended again.

## Checks after a successful run

Replay is authoritative within the requested window. Replaying an older manifest after a newer acquisition deliberately restores older source values in that window; use the latest relevant manifest for routine recovery. For a historical rollback, isolate the replay in another schema and inspect its results before publication. Serialized jobs prevent concurrent updates but do not make an old snapshot current.

Inspect `pipeline_runs`, quarantine counts/reasons, `v_gold_quality`, uniqueness at region-hour grain, complete local days at DST transitions, aggregate reconciliations and `publication_state`. Confirm the active release changed only after a successful dbt test task. Source missingness is a measured quality issue, not automatically a broken pipeline.

Run a 90-day reconciliation backfill periodically to capture NASA's longer-lag meteorological revisions. Retain source retrieval dates and run IDs when investigating changed historical values. Review table retention, source policies, credential ACLs and compute costs before enabling ongoing unattended execution.

## Reproduce aggregate evidence and Python figures

After publication, export reviewed aggregates using local OAuth:

```powershell
python -m pip install -e '.[databricks,visuals]'
python scripts/export_evidence.py --profile portfolio --warehouse-id <warehouse-id>
python scripts/plot_evidence.py
```

The export includes all seven dashboard SQL datasets and four validation/summary queries. It checks that the active publication did not change while reading them; otherwise it refuses the export. Local JSON files live under ignored `data/evidence/`. The plotted PNGs are publication artifacts under `docs/assets/`. Review the scope, numbers and source dates before replacing committed evidence. The AI/BI dashboard remains access-controlled inside the owner's workspace.
