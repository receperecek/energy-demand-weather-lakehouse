"""Export aggregate evidence using local OAuth; refuse a mixed publication snapshot."""

import argparse
import json
import re
import time
from datetime import datetime, timezone
from pathlib import Path

from databricks.sdk import WorkspaceClient

ROOT = Path(__file__).resolve().parents[1]
SCOPE = "local_date>='2024-01-01' AND local_date<'2026-01-01'"
EXTRA_QUERIES = {
    "annual_summary": f"""SELECT region_code,year(local_date) AS year,
        count(*) AS scoped_days,count_if(demand_day_complete) AS complete_days,
        sum(complete_day_demand_mwh)/1000000 AS complete_demand_twh,
        sum(eligible_wind_solar_mwh)/nullif(sum(eligible_net_generation_mwh),0)*100 AS wind_solar_pct,
        100.0*sum(eligible_generation_hours)/sum(scoped_hours) AS eligible_hours_pct,
        100.0*sum(complete_weather_hours)/sum(scoped_hours) AS weather_hours_pct,
        max(peak_hour_demand_mwh)/1000 AS peak_hour_gwh
        FROM v_gold_daily WHERE {SCOPE} GROUP BY 1,2 ORDER BY 1,2""",
    "dst_contract": """SELECT region_code,local_date,calendar_hours,scoped_hours,
        valid_demand_hours,demand_day_complete FROM v_gold_daily
        WHERE local_date IN ('2024-03-10','2024-11-03','2025-03-09','2025-11-02')
        ORDER BY 1,2""",
    "grain_check": """SELECT count(*) AS rows,count(DISTINCT struct(region_code,hour_utc)) AS unique_keys,
        min(hour_utc) AS first_interval_start,max(hour_utc) AS last_interval_start
        FROM v_gold_hourly""",
    "quality_summary": """SELECT region_code,sum(expected_hours) AS expected_hours,
        sum(observed_demand_hours) AS demand_hours,sum(complete_weather_hours) AS weather_hours,
        sum(generation_share_eligible_hours) AS share_eligible_hours,
        sum(invalid_energy_records) AS invalid_energy_records,
        sum(negative_generation_records) AS negative_generation_records,
        max(max_generation_gap_mwh) AS largest_fuel_gap_mwh
        FROM v_gold_quality WHERE utc_date>='2024-01-01' AND utc_date<'2026-01-01'
        GROUP BY 1 ORDER BY 1""",
}


def execute(client, warehouse, query):
    result = client.statement_execution.execute_statement(
        warehouse_id=warehouse, statement=query, wait_timeout="50s"
    )
    deadline = time.monotonic() + 300
    while result.status.state.value in {"PENDING", "RUNNING"}:
        if time.monotonic() > deadline:
            client.statement_execution.cancel_execution(result.statement_id)
            raise RuntimeError("Evidence query exceeded five minutes")
        time.sleep(2)
        result = client.statement_execution.get_statement(result.statement_id)
    if result.status.state.value != "SUCCEEDED":
        raise RuntimeError("Evidence query failed; inspect authorized warehouse query history")
    columns = [column.name for column in result.manifest.schema.columns]
    rows = list(result.result.data_array or [])
    chunk = result.result.next_chunk_index
    while chunk is not None:
        response = client.statement_execution.get_statement_result_chunk_n(
            result.statement_id, chunk
        )
        rows.extend(response.data_array or [])
        chunk = response.next_chunk_index
    return {"columns": columns, "rows": rows, "row_count": len(rows), "query": query}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--profile", default="portfolio")
    parser.add_argument("--warehouse-id", required=True)
    parser.add_argument("--catalog", default="workspace")
    parser.add_argument("--schema", default="energy_platform")
    parser.add_argument("--output-dir", type=Path, default=ROOT / "data" / "evidence")
    args = parser.parse_args()
    if not all(re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", x) for x in (args.catalog, args.schema)):
        raise ValueError("Invalid namespace")
    ns = args.catalog + "." + args.schema
    client = WorkspaceClient(profile=args.profile)
    pointer_query = f"SELECT release_id FROM {ns}.publication_state WHERE slot='active'"
    before = execute(client, args.warehouse_id, pointer_query)["rows"]
    if len(before) != 1:
        raise RuntimeError("Exactly one active publication is required")
    dashboard = json.loads((ROOT / "dashboards" / "energy.lvdash.json").read_text())
    queries = {d["name"]: d["query"] for d in dashboard["datasets"]} | EXTRA_QUERIES
    results = {}
    for name, query in queries.items():
        qualified = re.sub(r"\b(FROM|JOIN)\s+(v_gold_\w+)", rf"\1 {ns}.\2", query, flags=re.I)
        results[name] = execute(client, args.warehouse_id, qualified)
        # Store portable SQL, without owner/workspace identifiers.
        results[name]["query"] = query
        print(f"{name}: {results[name]['row_count']} aggregate rows", flush=True)
    if execute(client, args.warehouse_id, pointer_query)["rows"] != before:
        raise RuntimeError("Publication changed during export; retry")
    args.output_dir.mkdir(parents=True, exist_ok=True)
    for name, result in results.items():
        (args.output_dir / f"{name}.json").write_text(
            json.dumps(result, indent=2), encoding="utf-8"
        )
    metadata = {
        "exported_at_utc": datetime.now(timezone.utc).isoformat(),
        "release_id": before[0][0],
        "scope": "Local calendar years 2024–2025; ERCO, CISO, NYIS",
        "sources": ["U.S. EIA", "NASA POWER"],
        "timestamp_convention": "UTC interval start; EIA hour-ending labels shifted minus one hour",
    }
    (args.output_dir / "metadata.json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
