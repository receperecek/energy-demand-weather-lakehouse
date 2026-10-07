import json
import tempfile
import unittest
from datetime import date, datetime
from pathlib import Path
from unittest.mock import patch

from energy_platform.clients import SourceError, eia_pages, get_json, weather_payload
from energy_platform.config import daily_window, month_windows, validate_window
from energy_platform.ingest import store
from energy_platform.normalize import energy_record, hour, latest_unique, number, weather_records
from energy_platform.security import sanitize


class ContractTests(unittest.TestCase):
    def test_month_windows_cover_leap_year_without_overlap(self):
        windows = list(month_windows("2024-01-15", "2024-03-05"))
        self.assertEqual(
            windows,
            [
                (date(2024, 1, 15), date(2024, 2, 1)),
                (date(2024, 2, 1), date(2024, 3, 1)),
                (date(2024, 3, 1), date(2024, 3, 5)),
            ],
        )
        self.assertEqual(sum((b - a).days for a, b in windows), 50)

    def test_invalid_window_fails(self):
        with self.assertRaises(ValueError):
            validate_window("2024-01-01", "2024-01-01")

    def test_daily_window_respects_weather_lag(self):
        self.assertEqual(daily_window(date(2026, 10, 7)), ("2026-09-16", "2026-09-30"))

    def test_pagination_is_complete_and_exclusive_end_is_converted(self):
        seen = []

        def fetch(url, params):
            seen.append(params)
            return {
                "response": {
                    "total": "3",
                    "data": [{"a": 1}, {"a": 2}] if params["offset"] == 0 else [{"a": 3}],
                }
            }

        pages = list(
            eia_pages(
                "region-data", date(2024, 2, 1), date(2024, 3, 1), "fixture", fetch, page_size=2
            )
        )
        self.assertEqual([p[0] for p in pages], [0, 2])
        self.assertEqual(seen[0]["start"], "2024-02-01T01")
        self.assertEqual(seen[0]["end"], "2024-03-01T00")
        self.assertEqual(seen[0]["sort[2][column]"], "type")

    def test_changed_pagination_fails(self):
        def fetch(url, params):
            return {"response": {"total": 3 if params["offset"] == 0 else 4, "data": [{"a": 1}]}}

        with self.assertRaises(SourceError):
            list(
                eia_pages(
                    "region-data", date(2024, 1, 1), date(2024, 1, 2), "fixture", fetch, page_size=1
                )
            )

    def test_truncated_pagination_fails(self):
        def fetch(url, params):
            return {"response": {"total": 4, "data": []}}

        with self.assertRaises(SourceError):
            list(eia_pages("region-data", date(2024, 1, 1), date(2024, 1, 2), "fixture", fetch))

    def test_missing_key_fails_before_network(self):
        with self.assertRaises(ValueError):
            list(eia_pages("region-data", date(2024, 1, 1), date(2024, 1, 2), ""))

    def test_credentials_and_eia_echo_are_removed(self):
        payload = {
            "request": {"params": {"api_key": "fixture-sensitive"}},
            "nested": {"token": "fixture-sensitive"},
            "url": "https://example.org/data?api_key=fixture-sensitive&x=1",
            "response": {"data": [{"value": "42"}]},
        }
        cleaned = sanitize(payload)
        self.assertNotIn("fixture-sensitive", json.dumps(cleaned))
        self.assertNotIn("request", cleaned)
        self.assertEqual(cleaned["response"]["data"][0]["value"], "42")

    def test_http_errors_never_include_key(self):
        import urllib.error

        error = urllib.error.HTTPError(
            "https://example.org?api_key=fixture-sensitive", 403, "Forbidden", {}, None
        )
        with patch("urllib.request.urlopen", side_effect=error):
            with self.assertRaises(SourceError) as caught:
                get_json("https://example.org", {"api_key": "fixture-sensitive"})
        self.assertNotIn("fixture-sensitive", str(caught.exception))

    def test_repeat_snapshot_has_one_content_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            a = store(
                tmp,
                "region-data",
                "2024-01-01",
                "2024-01-02",
                {"request": {"api_key": "fixture-sensitive"}, "data": [1]},
            )
            b = store(tmp, "region-data", "2024-01-01", "2024-01-02", {"data": [1]})
            self.assertEqual(a, b)
            self.assertEqual(len(list(Path(tmp).rglob("*.json"))), 1)
            self.assertNotIn("fixture-sensitive", a.read_text())

    def test_finite_numbers_only(self):
        for value in [None, "", "NaN", "Infinity", "bad"]:
            self.assertIsNone(number(value))
        self.assertEqual(number("-10"), -10)

    def test_utc_hour_normalization(self):
        self.assertEqual(hour("2024-01-01T01:00:00+01:00"), datetime(2024, 1, 1))
        self.assertIsNone(hour("2024-01-01T00:15"))

    def make_energy(self, kind="D", value="100", source="region-data"):
        raw = {
            "period": "2024-01-01T00",
            "respondent": "ERCO",
            "value": value,
            "value-units": "megawatthours",
        }
        raw["type" if source == "region-data" else "fueltype"] = kind
        return energy_record(
            raw,
            source,
            {"payload_sha256": "fixture-sha", "retrieved_at": "2026-10-01T00:00:00+00:00"},
        )

    def test_negative_net_generation_is_retained(self):
        record = self.make_energy("NG", "-5")
        self.assertEqual(record["quality_reasons"], [])
        self.assertTrue(record["negative_net_generation"])

    def test_eia_hour_ending_maps_to_previous_interval_start(self):
        self.assertEqual(self.make_energy()["hour_utc"], datetime(2023, 12, 31, 23))
        self.assertEqual(
            self.make_energy("SUN", "10", "fuel-type-data")["hour_utc"],
            datetime(2023, 12, 31, 23),
        )

    def test_nonpositive_demand_is_flagged(self):
        self.assertIn("nonpositive_demand", self.make_energy("D", "0")["quality_reasons"])

    def test_unknown_fuel_is_visible(self):
        self.assertIn(
            "unknown_fuel", self.make_energy("NEW", "10", "fuel-type-data")["quality_reasons"]
        )

    def test_new_revision_replaces_previous(self):
        old = self.make_energy()
        new = {**old, "value_mwh": 120, "retrieved_at": "2026-10-02T00:00:00+00:00"}
        self.assertEqual(
            latest_unique([new, old], ["region_code", "hour_utc", "metric_code"]), [new]
        )

    def test_same_time_conflicting_values_fail(self):
        old = self.make_energy()
        new = {**old, "value_mwh": 120}
        with self.assertRaises(ValueError):
            latest_unique([old, new], ["region_code", "hour_utc", "metric_code"])

    def test_weather_missing_hours_fail(self):
        def fetch(url, params):
            return {"utc_offset_seconds": 0, "hourly": {"time": ["2024-01-01T00:00"]}}

        with self.assertRaises(SourceError):
            weather_payload(("a", 1, 1), date(2024, 1, 1), date(2024, 1, 2), fetch)

    def test_nasa_fill_value_is_missing_not_a_temperature(self):
        payload = {
            "properties": {
                "parameter": {
                    "T2M": {"2024010100": -999.0},
                    "WS10M": {"2024010100": 2},
                    "ALLSKY_SFC_SW_DWN": {"2024010100": 0},
                }
            },
            "header": {"fill_value": -999.0},
            "parameters": {
                "T2M": {"units": "C"},
                "WS10M": {"units": "m/s"},
                "ALLSKY_SFC_SW_DWN": {"units": "Wh/m^2"},
            },
        }
        snapshot = {
            "payload": {
                "payload": payload,
                "region_code": "ERCO",
                "location_id": "austin",
                "weather_model": "nasa_power_merra2_ceres",
            },
            "payload_sha256": "fixture-sha",
            "retrieved_at": "2026-10-01T00:00:00+00:00",
        }
        record = weather_records(snapshot)[0]
        self.assertIsNone(record["temperature_c"])
        self.assertIn("missing_weather", record["quality_reasons"])
        self.assertEqual(record["hour_utc"], datetime(2024, 1, 1))

    def test_weather_rejects_shifted_utc_keys_even_with_expected_length(self):
        values = {f"20240102{h:02d}": 1 for h in range(24)}

        def fetch(url, params):
            return {
                "header": {"time_standard": "UTC"},
                "properties": {
                    "parameter": dict.fromkeys(["T2M", "WS10M", "ALLSKY_SFC_SW_DWN"], values)
                },
            }

        with self.assertRaises(SourceError):
            weather_payload(("a", 1, 1), date(2024, 1, 1), date(2024, 1, 2), fetch)


if __name__ == "__main__":
    unittest.main()
