# Databricks notebook source
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path.cwd().parent / "src"))
from energy_platform.spark_pipeline import build_silver

for name, default in [
    ("catalog", "workspace"),
    ("schema", "energy_platform"),
    ("ingestion_run_id", ""),
]:
    dbutils.widgets.text(name, default)
catalog, schema, run_id = [
    dbutils.widgets.get(x) for x in ["catalog", "schema", "ingestion_run_id"]
]
counts = build_silver(spark, f"/Volumes/{catalog}/{schema}/raw", run_id, catalog, schema)
dbutils.notebook.exit(json.dumps(counts))
