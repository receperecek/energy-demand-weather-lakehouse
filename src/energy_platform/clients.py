"""Bounded HTTP retries and complete EIA pagination; exceptions omit request URLs."""

import json
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import timedelta

from .config import REGIONS, WEATHER_MODEL, WEATHER_VARIABLES
from .security import sanitize


class SourceError(RuntimeError):
    pass


_LAST_REQUEST = {}
_REQUEST_COUNTS = {}


def throttle(base):
    """One request per second per host, at most 1,000 attempts per process and host."""
    host = urllib.parse.urlsplit(base).hostname
    count = _REQUEST_COUNTS.get(host, 0)
    if count >= 1000:
        raise SourceError("Per-process source request budget exhausted")
    pause = max(0, 1 - (time.monotonic() - _LAST_REQUEST.get(host, 0)))
    if pause:
        time.sleep(pause)
    _LAST_REQUEST[host] = time.monotonic()
    _REQUEST_COUNTS[host] = count + 1


def get_json(base: str, params: dict, attempts=4):
    request = urllib.request.Request(
        base + "?" + urllib.parse.urlencode(params, doseq=True),
        headers={"User-Agent": "energy-demand-weather-lakehouse/1.0"},
    )
    for attempt in range(attempts):
        throttle(base)
        try:
            with urllib.request.urlopen(request, timeout=60) as response:
                return sanitize(json.load(response))
        except urllib.error.HTTPError as error:
            if error.code not in {429, 500, 502, 503, 504} or attempt + 1 == attempts:
                raise SourceError(f"Source HTTP failure ({error.code})") from None
            try:
                pause = min(60, max(1, float(error.headers.get("Retry-After", 2**attempt))))
            except (TypeError, ValueError):
                pause = 2**attempt
            time.sleep(pause)
        except (urllib.error.URLError, TimeoutError, OSError):
            if attempt + 1 == attempts:
                raise SourceError("Source connection failed after bounded retries") from None
            time.sleep(2**attempt)
        except (ValueError, UnicodeError):
            raise SourceError("Source returned invalid JSON") from None


def eia_pages(route, start, end, api_key, fetch=get_json, page_size=5000):
    if not api_key:
        raise ValueError("EIA_API_KEY is required")
    params = {
        "api_key": api_key,
        "frequency": "hourly",
        "data[0]": "value",
        "facets[respondent][]": list(REGIONS),
        # EIA labels the END of each interval; the platform uses interval starts.
        "start": start.isoformat() + "T01",
        "end": end.isoformat() + "T00",
        "length": page_size,
        "sort[0][column]": "period",
        "sort[0][direction]": "asc",
        "sort[1][column]": "respondent",
        "sort[1][direction]": "asc",
    }
    facet = "type" if route == "region-data" else "fueltype"
    params.update({"sort[2][column]": facet, "sort[2][direction]": "asc"})
    if route == "region-data":
        params["facets[type][]"] = ["D", "NG"]
    offset = 0
    expected = None
    while True:
        params["offset"] = offset
        payload = fetch(f"https://api.eia.gov/v2/electricity/rto/{route}/data/", params.copy())
        body = payload.get("response", {})
        if "total" not in body or not isinstance(body.get("data"), list):
            raise SourceError("EIA response contract failed")
        total = int(body["total"])
        if expected is not None and total != expected:
            raise SourceError("EIA result changed during pagination; retry the window")
        expected = total
        rows = body["data"]
        if total > offset and not rows:
            raise SourceError("EIA returned an incomplete page")
        if len(rows) > page_size or offset + len(rows) > total:
            raise SourceError("EIA pagination count contract failed")
        yield offset, payload
        offset += len(rows)
        if offset >= total:
            break


def weather_payload(location, start, end, fetch=get_json):
    name, lat, lon = location
    payload = fetch(
        "https://power.larc.nasa.gov/api/temporal/hourly/point",
        {
            "latitude": lat,
            "longitude": lon,
            "start": start.strftime("%Y%m%d"),
            "end": (end - timedelta(days=1)).strftime("%Y%m%d"),
            "parameters": ",".join(WEATHER_VARIABLES),
            "community": "RE",
            "format": "JSON",
            "time-standard": "UTC",
        },
    )
    if payload.get("header", {}).get("time_standard") != "UTC":
        raise SourceError("Weather response must use UTC")
    hourly = payload.get("properties", {}).get("parameter", {})
    expected = {
        (start + timedelta(days=d)).strftime("%Y%m%d") + f"{h:02d}"
        for d in range((end - start).days)
        for h in range(24)
    }
    if any(set(hourly.get(v, {})) != expected for v in WEATHER_VARIABLES):
        raise SourceError("Weather response has incomplete or inconsistent hourly arrays")
    return {
        "location_id": name,
        "requested_latitude": lat,
        "requested_longitude": lon,
        "weather_model": WEATHER_MODEL,
        "payload": payload,
    }
