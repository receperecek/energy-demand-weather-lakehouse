# Databricks notebook source
import sys
from pathlib import Path

sys.path.insert(0, str(Path.cwd().parent / "src"))
import json

from energy_platform.config import daily_window
from energy_platform.ingest import acquire
from energy_platform.spark_pipeline import namespace

for name, default in [
    ("catalog", "workspace"),
    ("schema", "energy_platform"),
    ("secret_scope", "energy-platform"),
    ("start_date", ""),
    ("end_date", ""),
]:
    dbutils.widgets.text(name, default)
catalog, schema = [dbutils.widgets.get(x) for x in ["catalog", "schema"]]
namespace(catalog, schema)
start, end = [dbutils.widgets.get(x) for x in ["start_date", "end_date"]]
if not start and not end:
    start, end = daily_window()
key = dbutils.secrets.get(dbutils.widgets.get("secret_scope"), "eia-api-key")
run_id, manifest = acquire(Path(f"/Volumes/{catalog}/{schema}/raw"), start, end, key)
dbutils.jobs.taskValues.set(key="ingestion_run_id", value=run_id)
dbutils.notebook.exit(
    json.dumps({"ingestion_run_id": run_id, "source_files": len(manifest["files"])})
)
