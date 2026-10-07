# Databricks notebook source
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path.cwd().parent / "src"))
from energy_platform.spark_pipeline import publish

for name, default in [
    ("catalog", "workspace"),
    ("schema", "energy_platform"),
    ("ingestion_run_id", ""),
]:
    dbutils.widgets.text(name, default)
catalog, schema, run_id = [
    dbutils.widgets.get(x) for x in ["catalog", "schema", "ingestion_run_id"]
]
release_id = publish(spark, run_id, catalog, schema)
dbutils.notebook.exit(json.dumps({"published_release": release_id, "ingestion_run_id": run_id}))
