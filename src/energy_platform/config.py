"""Versioned source selection; weather stations are equal-weight proxies."""

from datetime import date, datetime, timedelta, timezone

REGIONS = {
    "ERCO": {
        "name": "ERCOT",
        "timezone": "America/Chicago",
        "locations": [
            ("austin", 30.2672, -97.7431),
            ("dallas", 32.7767, -96.7970),
            ("houston", 29.7604, -95.3698),
        ],
    },
    "CISO": {
        "name": "CAISO",
        "timezone": "America/Los_Angeles",
        "locations": [
            ("sacramento", 38.5816, -121.4944),
            ("los_angeles", 34.0522, -118.2437),
            ("san_diego", 32.7157, -117.1611),
        ],
    },
    "NYIS": {
        "name": "NYISO",
        "timezone": "America/New_York",
        "locations": [
            ("new_york", 40.7128, -74.0060),
            ("albany", 42.6526, -73.7562),
            ("buffalo", 42.8864, -78.8784),
        ],
    },
}
WEATHER_VARIABLES = ("T2M", "WS10M", "ALLSKY_SFC_SW_DWN")
WEATHER_MODEL = "nasa_power_merra2_ceres"
FUELS = {
    "COL": "Coal",
    "NG": "Natural gas",
    "NUC": "Nuclear",
    "OIL": "Petroleum",
    "OTH": "Other",
    "SUN": "Solar",
    "WAT": "Hydro",
    "WND": "Wind",
    "BAT": "Battery storage",
    "PS": "Pumped storage",
    "UES": "Unknown storage",
    "OES": "Other storage",
    "GEO": "Geothermal",
    "SNB": "Solar with battery",
    "WNB": "Wind with battery",
    "UNK": "Unknown",
}


def validate_window(start: str, end: str) -> tuple[date, date]:
    """All project windows are half-open [start, end) UTC dates."""
    left, right = date.fromisoformat(start), date.fromisoformat(end)
    if left >= right:
        raise ValueError("start_date must precede end_date")
    return left, right


def month_windows(start: str, end: str):
    left, right = validate_window(start, end)
    while left < right:
        next_month = date(
            left.year + (left.month == 12), 1 if left.month == 12 else left.month + 1, 1
        )
        stop = min(next_month, right)
        yield left, stop
        left = stop


def daily_window(today: date | None = None):
    cutoff = (today or datetime.now(timezone.utc).date()) - timedelta(days=7)
    return (cutoff - timedelta(days=14)).isoformat(), cutoff.isoformat()


def year_windows(start: str, end: str):
    left, right = validate_window(start, end)
    while left < right:
        stop = min(date(left.year + 1, 1, 1), right)
        yield left, stop
        left = stop
