"""Acquire immutable sanitized source snapshots on local disk or a UC Volume."""

import argparse
import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path

from .clients import eia_pages, weather_payload
from .config import REGIONS, month_windows, validate_window, year_windows
from .security import sanitize


def store(root, source, start, end, payload):
    content = json.dumps(
        sanitize(payload), ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode()
    digest = hashlib.sha256(content).hexdigest()
    directory = Path(root) / source / f"{start}_{end}"
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{digest}.json"
    if not path.exists():
        envelope = {
            "source": source,
            "window_start": str(start),
            "window_end": str(end),
            "retrieved_at": datetime.now(timezone.utc).isoformat(),
            "payload_sha256": digest,
            "payload": sanitize(payload),
        }
        temporary = path.with_suffix(".tmp")
        temporary.write_text(json.dumps(envelope, ensure_ascii=False), encoding="utf-8")
        temporary.replace(path)
    return path


def acquire(root, start, end, api_key, include_weather=True):
    validate_window(start, end)
    paths = []
    for left, right in month_windows(start, end):
        for route in ("region-data", "fuel-type-data"):
            for offset, payload in eia_pages(route, left, right, api_key):
                paths.append(store(root, route, left, right, payload))
    if include_weather:
        for left, right in year_windows(start, end):
            for region, meta in REGIONS.items():
                for location in meta["locations"]:
                    payload = weather_payload(location, left, right)
                    payload["region_code"] = region
                    paths.append(store(root, "weather", left, right, payload))
    # Only a complete collection becomes visible to the transformation step.
    run = {
        "start_date": start,
        "end_date": end,
        "completed_at": datetime.now(timezone.utc).isoformat(),
        "files": [str(p.relative_to(root)).replace("\\", "/") for p in paths],
    }
    run_dir = Path(root) / "_runs"
    run_dir.mkdir(exist_ok=True)
    run_id = hashlib.sha256(json.dumps(run, sort_keys=True).encode()).hexdigest()
    (run_dir / f"{run_id}.json").write_text(json.dumps(run), encoding="utf-8")
    return run_id, run


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--start", required=True)
    parser.add_argument("--end", required=True, help="Exclusive UTC end date")
    parser.add_argument("--raw-root", default="data/raw")
    args = parser.parse_args()
    run_id, run = acquire(
        Path(args.raw_root), args.start, args.end, os.environ.get("EIA_API_KEY", "")
    )
    print(json.dumps({"run_id": run_id, "source_files": len(run["files"])}))
