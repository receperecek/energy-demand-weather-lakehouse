"""Bronze lineage and authoritative bounded-window Delta merges."""

import hashlib
import json
import re
import uuid
from pathlib import Path

from .config import REGIONS, validate_window
from .normalize import energy_record, weather_records


def namespace(catalog, schema):
    if not all(re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", x) for x in (catalog, schema)):
        raise ValueError("Invalid catalog or schema identifier")
    return f"{catalog}.{schema}"


def build_silver(spark, root, run_id, catalog="workspace", schema="energy_platform"):
    from delta.tables import DeltaTable
    from pyspark.sql import Window
    from pyspark.sql import functions as F

    ns = namespace(catalog, schema)
    spark.conf.set("spark.sql.session.timeZone", "UTC")
    root = Path(root)
    if not re.fullmatch(r"[a-f0-9]{64}", run_id):
        raise ValueError("Invalid run ID")
    manifest = json.loads((root / "_runs" / f"{run_id}.json").read_text(encoding="utf-8"))
    if hashlib.sha256(json.dumps(manifest, sort_keys=True).encode()).hexdigest() != run_id:
        raise ValueError("Completion manifest integrity check failed")
    left, right = validate_window(manifest["start_date"], manifest["end_date"])
    stage = root / "_normalized" / run_id
    stage.mkdir(parents=True, exist_ok=True)
    handles = {
        name: (stage / f"{name}.jsonl").open("w", encoding="utf-8")
        for name in ("energy", "weather", "bronze", "quarantine")
    }
    counts = {name: 0 for name in handles}

    def emit(name, row):
        handles[name].write(
            json.dumps(row, default=lambda x: x.isoformat(), ensure_ascii=False) + "\n"
        )
        counts[name] += 1

    try:
        for relative in manifest["files"]:
            path = (root / relative).resolve()
            if not path.is_relative_to(root.resolve()):
                raise ValueError("Manifest path escapes raw volume")
            snapshot = json.loads(path.read_text(encoding="utf-8"))
            encoded = json.dumps(
                snapshot["payload"], ensure_ascii=False, sort_keys=True, separators=(",", ":")
            ).encode()
            if hashlib.sha256(encoded).hexdigest() != snapshot["payload_sha256"]:
                raise ValueError("Source snapshot integrity check failed")
            emit(
                "bronze",
                {
                    "source": snapshot["source"],
                    "source_sha256": snapshot["payload_sha256"],
                    "retrieved_at": snapshot["retrieved_at"],
                    "window_start": snapshot["window_start"],
                    "window_end": snapshot["window_end"],
                    "source_path": relative,
                    "payload_json": json.dumps(snapshot["payload"], ensure_ascii=False),
                    "ingestion_run_id": run_id,
                },
            )
            source = snapshot["source"]
            records = (
                weather_records(snapshot)
                if source == "weather"
                else (
                    energy_record(raw, source, snapshot)
                    for raw in snapshot["payload"]["response"]["data"]
                )
            )
            for record in records:
                if record["hour_utc"] is not None and not left <= record["hour_utc"].date() < right:
                    record["quality_reasons"].append("outside_requested_window")
                valid_key = record["hour_utc"] is not None and record["region_code"] in REGIONS
                if not valid_key or record["quality_reasons"]:
                    emit(
                        "quarantine",
                        {
                            "ingestion_run_id": run_id,
                            "source": source,
                            "source_path": relative,
                            "reasons": record["quality_reasons"],
                            "record_json": json.dumps(record, default=str),
                        },
                    )
                # Invalid measurements with known keys replace previous measurements as invalid.
                if valid_key and "outside_requested_window" not in record["quality_reasons"]:
                    record["is_valid"] = not record["quality_reasons"]
                    record["ingestion_run_id"] = run_id
                    emit("weather" if source == "weather" else "energy", record)
    finally:
        for handle in handles.values():
            handle.close()
    if not counts["energy"] or not counts["weather"]:
        raise ValueError("A complete energy and weather collection is required")
    schemas = {
        "energy": "region_code STRING, hour_utc TIMESTAMP, metric_code STRING, value_mwh DOUBLE, negative_net_generation BOOLEAN, source_sha256 STRING, retrieved_at TIMESTAMP, quality_reasons ARRAY<STRING>, source STRING, is_valid BOOLEAN, ingestion_run_id STRING",
        "weather": "region_code STRING, location_id STRING, hour_utc TIMESTAMP, temperature_c DOUBLE, wind_speed_ms DOUBLE, shortwave_wm2 DOUBLE, weather_model STRING, source_sha256 STRING, retrieved_at TIMESTAMP, quality_reasons ARRAY<STRING>, is_valid BOOLEAN, ingestion_run_id STRING",
        "bronze": "source STRING, source_sha256 STRING, retrieved_at TIMESTAMP, window_start STRING, window_end STRING, source_path STRING, payload_json STRING, ingestion_run_id STRING",
        "quarantine": "ingestion_run_id STRING, source STRING, source_path STRING, reasons ARRAY<STRING>, record_json STRING",
    }
    frames = {
        name: spark.read.schema(ddl).json(str(stage / f"{name}.jsonl"))
        for name, ddl in schemas.items()
    }
    spark.sql(f"CREATE SCHEMA IF NOT EXISTS {ns}")
    for name, keys in [
        ("energy", ["source", "region_code", "hour_utc", "metric_code"]),
        ("weather", ["region_code", "location_id", "hour_utc", "weather_model"]),
    ]:
        df = frames[name]
        columns = (
            ["value_mwh", "is_valid"]
            if name == "energy"
            else ["temperature_c", "wind_speed_ms", "shortwave_wm2", "is_valid"]
        )
        conflicts = (
            df.groupBy(*keys, "retrieved_at")
            .agg(F.countDistinct(F.struct(*columns)).alias("variants"))
            .filter("variants > 1")
        )
        if conflicts.limit(1).count():
            raise ValueError("Conflicting same-time source observations")
        ordering = Window.partitionBy(*keys).orderBy(
            F.col("retrieved_at").desc(), F.col("source_sha256").desc()
        )
        df = df.withColumn("_rank", F.row_number().over(ordering)).filter("_rank = 1").drop("_rank")
        if df.select("region_code").distinct().count() != len(REGIONS):
            raise ValueError("A selected region has no source records")
        target = f"{ns}.silver_{name}"
        if not spark.catalog.tableExists(target):
            df.write.format("delta").mode("error").saveAsTable(target)
        else:
            condition = " AND ".join(f"t.{k} = s.{k}" for k in keys)
            # A fully acquired window is authoritative: omitted keys are removed in that window.
            window = f"t.hour_utc >= TIMESTAMP '{left} 00:00:00' AND t.hour_utc < TIMESTAMP '{right} 00:00:00'"
            (
                DeltaTable.forName(spark, target)
                .alias("t")
                .merge(df.alias("s"), condition)
                .whenMatchedUpdateAll()
                .whenNotMatchedInsertAll()
                .whenNotMatchedBySourceDelete(condition=window)
                .execute()
            )
    bronze = frames["bronze"].dropDuplicates(["source", "source_sha256"])
    target = f"{ns}.bronze_source_snapshots"
    if not spark.catalog.tableExists(target):
        bronze.write.format("delta").saveAsTable(target)
    else:
        (
            DeltaTable.forName(spark, target)
            .alias("t")
            .merge(bronze.alias("s"), "t.source = s.source AND t.source_sha256 = s.source_sha256")
            .whenNotMatchedInsertAll()
            .execute()
        )
    if counts["quarantine"]:
        if spark.catalog.tableExists(f"{ns}.quarantine_records"):
            spark.sql(f"DELETE FROM {ns}.quarantine_records WHERE ingestion_run_id = '{run_id}'")
        frames["quarantine"].write.format("delta").mode("append").saveAsTable(
            f"{ns}.quarantine_records"
        )
    spark.sql(
        f"CREATE TABLE IF NOT EXISTS {ns}.pipeline_runs (ingestion_run_id STRING, start_date DATE, end_date DATE, energy_rows BIGINT, weather_rows BIGINT, quarantined_rows BIGINT, completed_at TIMESTAMP) USING DELTA"
    )
    spark.sql(f"DELETE FROM {ns}.pipeline_runs WHERE ingestion_run_id = '{run_id}'")
    spark.sql(
        f"INSERT INTO {ns}.pipeline_runs VALUES ('{run_id}', DATE '{left}', DATE '{right}', {counts['energy']}, {counts['weather']}, {counts['quarantine']}, current_timestamp())"
    )
    return counts


def publish(spark, run_id, catalog="workspace", schema="energy_platform"):
    """Write release copies, then switch one pointer after all copies succeed."""
    if not re.fullmatch(r"[a-f0-9]{64}", run_id):
        raise ValueError("Invalid release ID")
    from pyspark.sql import functions as F

    ns = namespace(catalog, schema)
    # Every attempt receives a new immutable release, including retries of the same ingestion.
    release_id = uuid.uuid4().hex
    spark.sql(
        f"CREATE TABLE IF NOT EXISTS {ns}.publication_state (slot STRING, release_id STRING, published_at TIMESTAMP) USING DELTA"
    )
    for model in ["gold_hourly", "gold_daily", "gold_priority", "gold_quality", "gold_fuel_daily"]:
        target = f"{ns}.published_{model}"
        frame = (
            spark.table(f"{ns}.{model}")
            .withColumn("release_id", F.lit(release_id))
            .withColumn("publication_ingestion_run_id", F.lit(run_id))
        )
        if spark.catalog.tableExists(target):
            frame.write.format("delta").option("mergeSchema", "true").mode("append").saveAsTable(
                target
            )
        else:
            frame.write.format("delta").saveAsTable(target)
        spark.sql(
            f"CREATE OR REPLACE VIEW {ns}.v_{model} AS SELECT p.* EXCEPT(release_id) FROM {target} p JOIN {ns}.publication_state s ON p.release_id=s.release_id AND s.slot='active'"
        )
    spark.sql(
        f"MERGE INTO {ns}.publication_state t USING (SELECT 'active' AS slot, '{release_id}' AS release_id, current_timestamp() AS published_at) s ON t.slot=s.slot WHEN MATCHED THEN UPDATE SET * WHEN NOT MATCHED THEN INSERT *"
    )
    return release_id
