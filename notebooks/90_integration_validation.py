# Databricks notebook source
"""Cloud integration checks in a newly-created disposable validation schema."""

import hashlib
import json
import sys
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path.cwd().parent / "src"))
from energy_platform.config import REGIONS, WEATHER_MODEL
from energy_platform.ingest import store
from energy_platform.spark_pipeline import build_silver, publish

# Never reuse the business schema for destructive fixture checks.
schema = "energy_validation_" + uuid.uuid4().hex[:12]
ns = "workspace." + schema
spark.sql(f"CREATE SCHEMA {ns}")
spark.sql(f"CREATE VOLUME {ns}.raw")
root = Path("/Volumes/workspace/" + schema + "/raw")
left, right = "2024-03-09", "2024-03-11"
hours = [datetime(2024, 3, 9) + timedelta(hours=i) for i in range(48)]
fake_credential = "fixture" + "-sensitive"
energy = []
fuels = []
for region in REGIONS:
    for timestamp in hours:
        base = {
            "period": (timestamp + timedelta(hours=1)).strftime("%Y-%m-%dT%H"),
            "respondent": region,
            "value-units": "megawatthours",
        }
        energy.extend(
            [{**base, "type": "D", "value": "1100"}, {**base, "type": "NG", "value": "1000"}]
        )
        fuels.extend(
            [
                {**base, "fueltype": code, "value": value}
                for code, value in [("NG", "700"), ("SUN", "200"), ("WND", "100")]
            ]
        )
weather = []
for region, meta in REGIONS.items():
    for name, lat, lon in meta["locations"]:
        hourly = {
            code: {t.strftime("%Y%m%d%H"): value for t in hours}
            for code, value in [("T2M", 20), ("WS10M", 3), ("ALLSKY_SFC_SW_DWN", 100)]
        }
        weather.append(
            {
                "region_code": region,
                "location_id": name,
                "weather_model": WEATHER_MODEL,
                "payload": {
                    "header": {"fill_value": -999.0, "time_standard": "UTC"},
                    "properties": {"parameter": hourly},
                    "parameters": {
                        "T2M": {"units": "C"},
                        "WS10M": {"units": "m/s"},
                        "ALLSKY_SFC_SW_DWN": {"units": "Wh/m^2"},
                    },
                },
            }
        )


def collection(energy_rows, fuel_rows):
    paths = [
        store(
            root,
            "region-data",
            left,
            right,
            {"request": {"api_key": fake_credential}, "response": {"data": energy_rows}},
        ),
        store(root, "fuel-type-data", left, right, {"response": {"data": fuel_rows}}),
    ]
    paths.extend(store(root, "weather", left, right, payload) for payload in weather)
    manifest = {
        "start_date": left,
        "end_date": right,
        "completed_at": datetime.now(timezone.utc).isoformat(),
        "files": [str(path.relative_to(root)) for path in paths],
    }
    run = hashlib.sha256(json.dumps(manifest, sort_keys=True).encode()).hexdigest()
    (root / "_runs").mkdir(exist_ok=True)
    (root / "_runs" / f"{run}.json").write_text(json.dumps(manifest), encoding="utf-8")
    return run, paths


run, paths = collection(energy, fuels)
assert all(fake_credential not in p.read_text(encoding="utf-8") for p in paths)
build_silver(spark, root, run, "workspace", schema)
initial = spark.table(ns + ".silver_energy").count()
bronze = spark.table(ns + ".bronze_source_snapshots").count()
build_silver(spark, root, run, "workspace", schema)
assert spark.table(ns + ".silver_energy").count() == initial == 720
assert spark.table(ns + ".bronze_source_snapshots").count() == bronze == 11
assert spark.table(ns + ".silver_weather").count() == 432

revised = [dict(row) for row in energy]
revised[0]["value"] = "1200"
revised[2]["value"] = None
revised_fuels = [
    row
    for row in fuels
    if not (
        row["respondent"] == "ERCO"
        and row["period"] == "2024-03-09T01"
        and row["fueltype"] == "SUN"
    )
]
new_run, _ = collection(revised, revised_fuels)
build_silver(spark, root, new_run, "workspace", schema)
assert (
    spark.sql(
        f"SELECT value_mwh FROM {ns}.silver_energy WHERE region_code='ERCO' AND hour_utc='2024-03-09 00:00:00' AND metric_code='D'"
    ).first()[0]
    == 1200
)
assert (
    spark.sql(
        f"SELECT is_valid FROM {ns}.silver_energy WHERE region_code='ERCO' AND hour_utc='2024-03-09 01:00:00' AND metric_code='D'"
    ).first()[0]
    is False
)
assert spark.table(ns + ".silver_energy").count() == 719
assert spark.table(ns + ".quarantine_records").count() == 1
build_silver(spark, root, new_run, "workspace", schema)
assert spark.table(ns + ".quarantine_records").count() == 1
assert spark.table(ns + ".silver_energy").count() == 719

models = ["gold_hourly", "gold_daily", "gold_priority", "gold_quality", "gold_fuel_daily"]
for model in models:
    spark.sql(f"CREATE TABLE {ns}.{model} USING DELTA AS SELECT 1 AS fixture_value")
first_release = publish(spark, new_run, "workspace", schema)
assert all(spark.table(ns + ".v_" + model).count() == 1 for model in models)
# Deliberately remove only a fixture candidate, so copying fails after four new copies.
spark.sql(f"DROP TABLE {ns}.gold_fuel_daily")
try:
    publish(spark, new_run, "workspace", schema)
except Exception:
    pass
else:
    raise AssertionError("Expected an incomplete publication to fail")
active = spark.sql(f"SELECT release_id FROM {ns}.publication_state WHERE slot='active'").first()[0]
assert active == first_release
assert all(spark.table(ns + ".v_" + model).count() == 1 for model in models)
spark.sql(f"CREATE TABLE {ns}.gold_fuel_daily USING DELTA AS SELECT 1 AS fixture_value")
next_release = publish(spark, new_run, "workspace", schema)
assert next_release != first_release
assert all(spark.table(ns + ".v_" + model).count() == 1 for model in models)
spark.sql(
    f"CREATE OR REPLACE TABLE {ns}.gold_hourly USING DELTA AS SELECT 1 AS fixture_value, 2 AS added_column"
)
publish(spark, new_run, "workspace", schema)
assert spark.table(ns + ".v_gold_hourly").select("added_column").first()[0] == 2

dbutils.notebook.exit(
    json.dumps(
        {
            "passed": True,
            "validation_schema": schema,
            "checks": [
                "credential_echo_removed",
                "silver_replay_unique",
                "bronze_replay_unique",
                "revision_replacement",
                "invalid_revision_replaces_valid",
                "bounded_missing_key_deletion",
                "quarantine_replay_unique",
                "failed_publication_keeps_previous_release",
                "retry_uses_new_release_id",
                "additive_publication_schema_evolution",
            ],
        }
    )
)
