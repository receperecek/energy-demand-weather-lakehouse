"""Deterministic record normalization, explicit rejection reasons, and source lineage."""

import math
from datetime import datetime, timedelta, timezone

from .config import FUELS, REGIONS, WEATHER_VARIABLES


def number(value):
    if value is None or value == "":
        return None
    try:
        result = float(value)
        return result if math.isfinite(result) else None
    except (TypeError, ValueError):
        return None


def hour(value):
    try:
        dt = datetime.fromisoformat(value)
    except (ValueError, TypeError):
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    dt = dt.astimezone(timezone.utc)
    if dt.minute or dt.second or dt.microsecond:
        return None
    return dt.replace(tzinfo=None)


def energy_record(raw, source, snapshot):
    timestamp = hour(raw.get("period"))
    if timestamp is not None:
        timestamp -= timedelta(hours=1)
    value = number(raw.get("value"))
    region = raw.get("respondent")
    kind = raw.get("type") if source == "region-data" else raw.get("fueltype")
    reasons = []
    if region not in REGIONS:
        reasons.append("unknown_region")
    if timestamp is None:
        reasons.append("invalid_hour")
    if value is None:
        reasons.append("missing_or_invalid_value")
    if raw.get("value-units") != "megawatthours":
        reasons.append("unexpected_unit")
    if source == "region-data" and kind not in {"D", "NG"}:
        reasons.append("unknown_metric")
    if source == "fuel-type-data" and kind not in FUELS:
        reasons.append("unknown_fuel")
    if kind == "D" and value is not None and value <= 0:
        reasons.append("nonpositive_demand")
    # Negative net generation can represent consumption; retain and flag it.
    return {
        "region_code": region,
        "hour_utc": timestamp,
        "metric_code": kind,
        "value_mwh": value,
        "negative_net_generation": kind != "D" and value is not None and value < 0,
        "source_sha256": snapshot["payload_sha256"],
        "retrieved_at": snapshot["retrieved_at"],
        "quality_reasons": reasons,
        "source": source,
    }


def weather_records(snapshot):
    wrapper = snapshot["payload"]
    payload = wrapper["payload"]
    hourly = payload["properties"]["parameter"]
    units = payload.get("parameters", {})
    unit_ok = (
        units.get("T2M", {}).get("units") == "C"
        and units.get("WS10M", {}).get("units") == "m/s"
        and units.get("ALLSKY_SFC_SW_DWN", {}).get("units") == "Wh/m^2"
    )
    fill = payload["header"]["fill_value"]
    result = []
    for period in sorted(hourly["T2M"]):
        values = [
            None if hourly[v][period] == fill else number(hourly[v][period])
            for v in WEATHER_VARIABLES
        ]
        try:
            timestamp = datetime.strptime(period, "%Y%m%d%H")
        except (ValueError, TypeError):
            timestamp = None
        reasons = []
        if timestamp is None:
            reasons.append("invalid_hour")
        if any(v is None for v in values):
            reasons.append("missing_weather")
        if not unit_ok:
            reasons.append("unexpected_weather_unit")
        if values[0] is not None and not -90 <= values[0] <= 60:
            reasons.append("implausible_temperature")
        if values[1] is not None and values[1] < 0:
            reasons.append("negative_wind")
        if values[2] is not None and values[2] < 0:
            reasons.append("negative_radiation")
        result.append(
            {
                "region_code": wrapper["region_code"],
                "location_id": wrapper["location_id"],
                "hour_utc": timestamp,
                "temperature_c": values[0],
                "wind_speed_ms": values[1],
                "shortwave_wm2": values[2],
                "weather_model": wrapper["weather_model"],
                "source_sha256": snapshot["payload_sha256"],
                "retrieved_at": snapshot["retrieved_at"],
                "quality_reasons": reasons,
            }
        )
    return result


def latest_unique(records, key_fields):
    """Resolve source revisions by acquisition time, fail on same-time conflicts."""
    latest = {}
    for record in records:
        key = tuple(record[k] for k in key_fields)
        old = latest.get(key)
        if old is None or record["retrieved_at"] > old["retrieved_at"]:
            latest[key] = record
        elif record["retrieved_at"] == old["retrieved_at"] and record != old:
            raise ValueError("Conflicting records share the same acquisition timestamp")
    return list(latest.values())
