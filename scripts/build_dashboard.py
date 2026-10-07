"""Generate an original, portable Databricks AI/BI dashboard definition."""

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATASETS = {
    "monthly_demand": (
        "Monthly demand",
        """SELECT region_code,region_name,date_trunc('month',local_date)::date AS month,
        avg(complete_day_demand_mwh)/1000 AS mean_day_demand_gwh,count(*) AS complete_days
        FROM v_gold_daily WHERE demand_day_complete AND local_date>='2024-01-01' AND local_date<'2026-01-01'
        GROUP BY 1,2,3""",
    ),
    "hour_profile": (
        "Local-hour demand pattern",
        """SELECT region_code,region_name,hour_of_day,
        CASE WHEN day_of_week IN (1,7) THEN 'Weekend' ELSE 'Weekday' END AS day_type,
        concat(region_name,' / ',CASE WHEN day_of_week IN (1,7) THEN 'Weekend' ELSE 'Weekday' END) AS profile_series,
        avg(demand_mwh)/1000 AS mean_hour_demand_gwh,count(demand_mwh) AS valid_hours
        FROM v_gold_hourly WHERE local_date>='2024-01-01' AND local_date<'2026-01-01'
        GROUP BY 1,2,3,4,5""",
    ),
    "daily": (
        "Demand and weather context",
        """SELECT region_code,region_name,local_date,
        complete_day_demand_mwh/1000 AS demand_gwh,
        CASE WHEN complete_weather_hours=calendar_hours THEN mean_proxy_temperature_c END AS temperature_c,
        observed_wind_solar_share*100 AS wind_solar_pct,
        100.0*eligible_generation_hours/calendar_hours AS share_coverage_pct,
        high_demand_candidate_hours,demand_day_complete
        FROM v_gold_daily WHERE local_date>='2024-01-01' AND local_date<'2026-01-01'""",
    ),
    "monthly_share": (
        "Energy-weighted generation share",
        """SELECT region_code,region_name,date_trunc('month',local_date)::date AS month,
        100.0*sum(eligible_wind_solar_mwh)/nullif(sum(eligible_net_generation_mwh),0) AS wind_solar_pct,
        100.0*sum(eligible_generation_hours)/sum(scoped_hours) AS eligible_hours_pct
        FROM v_gold_daily WHERE local_date>='2024-01-01' AND local_date<'2026-01-01' GROUP BY 1,2,3""",
    ),
    "fuel_mix": (
        "Reported generation by fuel",
        """SELECT region_code,region_name,fuel_code,
        sum(observed_generation_mwh)/1000 AS generation_gwh,sum(reported_hours) AS reported_hours,
        sum(negative_generation_hours) AS negative_hours
        FROM v_gold_fuel_daily WHERE local_date>='2024-01-01' AND local_date<'2026-01-01' GROUP BY 1,2,3""",
    ),
    "quality": (
        "Daily source coverage",
        """SELECT region_code,region_name,utc_date,expected_hours,
        100.0*observed_demand_hours/expected_hours AS demand_coverage_pct,
        100.0*complete_weather_hours/expected_hours AS weather_coverage_pct,
        100.0*generation_share_eligible_hours/expected_hours AS share_eligible_pct,
        max_generation_gap_mwh,invalid_energy_records,negative_generation_records
        FROM v_gold_quality WHERE utc_date>='2024-01-01' AND utc_date<'2026-01-01'""",
    ),
    "review": (
        "Investigation queue",
        """SELECT region_code,region_name,local_date,review_priority,
        peak_hour_demand_mwh/1000 AS peak_hour_gwh,high_demand_candidate_hours,
        max_demand_deviation_score,demand_day_complete,complete_weather_hours,calendar_hours
        FROM v_gold_priority WHERE local_date>='2024-01-01' AND local_date<'2026-01-01'
        AND review_priority<>'ROUTINE' ORDER BY local_date DESC""",
    ),
}


def text(name, body, x, y, width, height):
    return {
        "widget": {"name": name, "textbox_spec": body},
        "position": {"x": x, "y": y, "width": width, "height": height},
    }


def query(dataset, fields):
    return {
        "name": "main_query",
        "query": {
            "datasetName": dataset,
            "fields": [{"name": f, "expression": f"`{f}`"} for f in fields],
            "disaggregated": True,
        },
    }


def chart(
    name, dataset, title, kind, xfield, yfield, color, x, y, width=3, height=6, xscale="temporal"
):
    fields = [xfield, yfield] + ([color] if color else [])
    encodings = {
        "x": {
            "fieldName": xfield,
            "scale": {"type": xscale},
            "displayName": xfield.replace("_", " ").title(),
        },
        "y": {
            "fieldName": yfield,
            "scale": {"type": "quantitative"},
            "displayName": yfield.replace("_", " ").title(),
        },
    }
    if color:
        encodings["color"] = {
            "fieldName": color,
            "scale": {"type": "categorical"},
            "displayName": color.replace("_", " ").title(),
        }
    return {
        "widget": {
            "name": name,
            "queries": [query(dataset, fields)],
            "spec": {
                "version": 3,
                "widgetType": kind,
                "encodings": encodings,
                "frame": {"showTitle": True, "title": title},
            },
        },
        "position": {"x": x, "y": y, "width": width, "height": height},
    }


def table(name, dataset, title, columns, x, y, width=6, height=6):
    encoded = []
    for i, (field, kind) in enumerate(columns):
        encoded.append(
            {
                "fieldName": field,
                "type": kind,
                "displayAs": "number" if kind in ("float", "integer") else kind,
                "visible": True,
                "order": i,
                "title": field.replace("_", " ").title(),
                "displayName": field,
                "allowSearch": kind == "string",
                "alignContent": "left" if kind == "string" else "right",
                "allowHTML": False,
            }
        )
    return {
        "widget": {
            "name": name,
            "queries": [query(dataset, [c[0] for c in columns])],
            "spec": {
                "version": 1,
                "widgetType": "table",
                "encodings": {"columns": encoded},
                "itemsPerPage": 25,
                "frame": {"showTitle": True, "title": title},
            },
        },
        "position": {"x": x, "y": y, "width": width, "height": height},
    }


def region_filter(name, datasets):
    queries = [
        {
            "name": f"region_{d}",
            "query": {
                "datasetName": d,
                "fields": [{"name": "region_code", "expression": "`region_code`"}],
                "disaggregated": False,
            },
        }
        for d in datasets
    ]
    return {
        "widget": {
            "name": name,
            "queries": queries,
            "spec": {
                "version": 2,
                "widgetType": "filter-multi-select",
                "encodings": {
                    "fields": [
                        {
                            "fieldName": "region_code",
                            "displayName": "Region",
                            "queryName": q["name"],
                        }
                        for q in queries
                    ]
                },
                "frame": {"showTitle": True, "title": "Balancing authority"},
            },
        },
        "position": {"x": 0, "y": 2, "width": 2, "height": 2},
    }


FOOTER = "Sources: [U.S. EIA](https://www.eia.gov/opendata/) and [NASA POWER](https://power.larc.nasa.gov/). Project calculations; no provider endorsement. Weather is an equal-weight three-city grid proxy. Historical scope: local calendar years 2024–2025. Consumer views select the latest tested release."
pages = [
    {
        "name": "demand",
        "displayName": "Demand patterns",
        "pageType": "PAGE_TYPE_CANVAS",
        "layout": [
            text(
                "demand_title",
                "# Electricity demand patterns\nCompare seasonal and local-hour behavior across ERCOT, CAISO and NYISO.",
                0,
                0,
                6,
                2,
            ),
            region_filter("demand_region", ["monthly_demand", "hour_profile", "daily"]),
            chart(
                "monthly_demand_chart",
                "monthly_demand",
                "Mean complete-day demand (GWh)",
                "line",
                "month",
                "mean_day_demand_gwh",
                "region_name",
                0,
                4,
            ),
            chart(
                "hour_chart",
                "hour_profile",
                "Local-hour demand profile (GWh)",
                "line",
                "hour_of_day",
                "mean_hour_demand_gwh",
                "profile_series",
                3,
                4,
                xscale="quantitative",
            ),
            chart(
                "weather_chart",
                "daily",
                "Temperature and demand — descriptive association",
                "scatter",
                "temperature_c",
                "demand_gwh",
                "region_name",
                0,
                10,
                xscale="quantitative",
            ),
            chart(
                "daily_chart",
                "daily",
                "Complete daily demand (GWh)",
                "line",
                "local_date",
                "demand_gwh",
                "region_name",
                3,
                10,
            ),
            text(
                "demand_note",
                "The temperature relationship is not causal. Compare within regions and seasons before interpreting it. Incomplete demand days remain null. The repeated local hour at autumn DST is preserved in UTC.",
                0,
                16,
                6,
                2,
            ),
            text("demand_source", FOOTER, 0, 18, 6, 2),
        ],
    },
    {
        "name": "generation",
        "displayName": "Generation composition",
        "pageType": "PAGE_TYPE_CANVAS",
        "layout": [
            text(
                "mix_title",
                "# Generation composition\nReported net generation, source-category detail and eligible wind + solar shares.",
                0,
                0,
                6,
                2,
            ),
            region_filter("mix_region", ["monthly_share", "fuel_mix"]),
            chart(
                "share_chart",
                "monthly_share",
                "Energy-weighted wind + solar share (%)",
                "line",
                "month",
                "wind_solar_pct",
                "region_name",
                0,
                4,
            ),
            chart(
                "share_coverage",
                "monthly_share",
                "Hours eligible for the share metric (%)",
                "line",
                "month",
                "eligible_hours_pct",
                "region_name",
                3,
                4,
            ),
            chart(
                "fuels_chart",
                "fuel_mix",
                "Reported net generation by fuel (GWh)",
                "bar",
                "fuel_code",
                "generation_gwh",
                "region_name",
                0,
                10,
                width=6,
                xscale="categorical",
            ),
            table(
                "fuel_table",
                "fuel_mix",
                "Category coverage and signed generation",
                [
                    ("region_name", "string"),
                    ("fuel_code", "string"),
                    ("generation_gwh", "float"),
                    ("reported_hours", "integer"),
                    ("negative_hours", "integer"),
                ],
                0,
                16,
            ),
            text(
                "mix_note",
                "SUN/WND are pure solar/wind; SNB/WNB are hybrid source categories. BAT/PS can be negative because net storage generation can include consumption. Missing source categories are not inferred as zero. Shares require fuel/total reconciliation within max(1 MWh, 1%).",
                0,
                22,
                6,
                2,
            ),
            text("mix_source", FOOTER, 0, 24, 6, 2),
        ],
    },
    {
        "name": "quality",
        "displayName": "Quality and review",
        "pageType": "PAGE_TYPE_CANVAS",
        "layout": [
            text(
                "quality_title",
                "# Coverage and investigation\nAssess the evidence before acting on a pattern.",
                0,
                0,
                6,
                2,
            ),
            region_filter("quality_region", ["quality", "review"]),
            chart(
                "demand_coverage",
                "quality",
                "Valid demand coverage (%)",
                "line",
                "utc_date",
                "demand_coverage_pct",
                "region_name",
                0,
                4,
            ),
            chart(
                "weather_coverage",
                "quality",
                "Complete three-point weather coverage (%)",
                "line",
                "utc_date",
                "weather_coverage_pct",
                "region_name",
                3,
                4,
            ),
            table(
                "quality_table",
                "quality",
                "Source quality by UTC day",
                [
                    ("region_name", "string"),
                    ("utc_date", "date"),
                    ("demand_coverage_pct", "float"),
                    ("weather_coverage_pct", "float"),
                    ("share_eligible_pct", "float"),
                    ("invalid_energy_records", "integer"),
                    ("max_generation_gap_mwh", "float"),
                ],
                0,
                10,
            ),
            table(
                "review_table",
                "review",
                "Candidate investigation days",
                [
                    ("region_name", "string"),
                    ("local_date", "date"),
                    ("review_priority", "string"),
                    ("peak_hour_gwh", "float"),
                    ("high_demand_candidate_hours", "integer"),
                    ("max_demand_deviation_score", "float"),
                ],
                0,
                16,
            ),
            text(
                "quality_note",
                "A high-demand candidate exceeds a trailing same-weekday/same-local-hour reference by 3 sample standard deviations, with at least 4 preceding observations. It is an investigation heuristic, not a grid stress or blackout forecast.",
                0,
                22,
                6,
                2,
            ),
            text("quality_source", FOOTER, 0, 24, 6, 2),
        ],
    },
]


def main():
    target = ROOT / "dashboards" / "energy.lvdash.json"
    target.parent.mkdir(exist_ok=True)
    target.write_text(
        json.dumps(
            {
                "datasets": [
                    {"name": key, "displayName": label, "query": sql}
                    for key, (label, sql) in DATASETS.items()
                ],
                "pages": pages,
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    print("Generated dashboard with 7 reviewed SQL datasets and 3 pages")


if __name__ == "__main__":
    main()
