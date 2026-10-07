"""Reproduce portfolio figures from inspected warehouse aggregate exports."""

import argparse
import json
from datetime import datetime
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.dates as mdates
import matplotlib.pyplot as plt

ROOT = Path(__file__).resolve().parents[1]
COLORS = {"ERCO": "#2864A0", "CISO": "#BA7424", "NYIS": "#627C46"}
NAMES = {"ERCO": "ERCOT", "CISO": "CAISO", "NYIS": "NYISO"}
STYLES = {"ERCO": "-", "CISO": "--", "NYIS": "-."}


def read_rows(directory, name):
    payload = json.loads((directory / f"{name}.json").read_text(encoding="utf-8"))
    return [dict(zip(payload["columns"], row, strict=True)) for row in payload["rows"]]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input-dir", type=Path, default=ROOT / "data" / "evidence")
    parser.add_argument("--output-dir", type=Path, default=ROOT / "docs" / "assets")
    args = parser.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    plt.rcParams.update(
        {
            "font.family": "DejaVu Sans",
            "font.size": 11,
            "axes.spines.top": False,
            "axes.spines.right": False,
            "axes.labelcolor": "#333333",
            "text.color": "#222222",
            "axes.edgecolor": "#B0B0B0",
            "grid.color": "#E5E5E5",
            "grid.linewidth": 0.7,
        }
    )
    demand = read_rows(args.input_dir, "monthly_demand")
    share = read_rows(args.input_dir, "monthly_share")
    profiles = read_rows(args.input_dir, "hour_profile")
    fig, axes = plt.subplots(1, 2, figsize=(14, 5.6))
    for code in COLORS:
        for ax, rows, field in [
            (axes[0], demand, "mean_day_demand_gwh"),
            (axes[1], share, "wind_solar_pct"),
        ]:
            selected = sorted(
                (r for r in rows if r["region_code"] == code), key=lambda r: r["month"]
            )
            ax.plot(
                [datetime.fromisoformat(r["month"]) for r in selected],
                [float(r[field]) if r[field] is not None else float("nan") for r in selected],
                color=COLORS[code],
                linestyle=STYLES[code],
                linewidth=2,
                label=NAMES[code],
            )
            ax.grid(axis="y")
            ax.set_ylim(bottom=0)
            ticks = [
                datetime(2024, 1, 1),
                datetime(2024, 7, 1),
                datetime(2025, 1, 1),
                datetime(2025, 7, 1),
                datetime(2025, 12, 1),
            ]
            ax.set_xticks(ticks)
            ax.xaxis.set_major_formatter(mdates.DateFormatter("%b %y"))
    axes[0].set(title="Monthly electricity demand", ylabel="Mean complete-day demand · GWh")
    axes[1].set(title="Wind + solar in net generation", ylabel="Energy-weighted share · %")
    axes[1].set_ylim(0, 100)
    axes[0].legend(loc="upper left", frameon=False, ncol=3, fontsize=10)
    fig.suptitle(
        "Demand patterns & generation composition",
        fontsize=19,
        fontweight="bold",
        x=0.06,
        ha="left",
    )
    fig.text(
        0.06, 0.89, "ERCOT · CAISO · NYISO   |   local calendar years 2024–2025", color="#666666"
    )
    fig.text(
        0.06,
        0.025,
        "Sources: U.S. EIA; project calculations. Demand uses complete local days. Shares use reconciled hours only.\n"
        "Eligible-hour coverage and exact denominators: docs/analysis.md. No provider endorsement.",
        fontsize=9,
        color="#666666",
    )
    fig.subplots_adjust(left=0.065, right=0.97, bottom=0.19, top=0.79, wspace=0.24)
    fig.savefig(args.output_dir / "overview.png", dpi=180, facecolor="white")
    plt.close(fig)
    fig, axes = plt.subplots(1, 3, figsize=(14, 5.4), sharey=True)
    for ax, code in zip(axes, COLORS, strict=True):
        for day_type, style in [("Weekday", "-"), ("Weekend", "--")]:
            rows = sorted(
                (r for r in profiles if r["region_code"] == code and r["day_type"] == day_type),
                key=lambda r: int(r["hour_of_day"]),
            )
            ax.plot(
                [int(r["hour_of_day"]) for r in rows],
                [float(r["mean_hour_demand_gwh"]) for r in rows],
                color=COLORS[code],
                linestyle=style,
                linewidth=2,
                label=day_type,
            )
        ax.set(title=NAMES[code], xlabel="Local interval-start hour", xlim=(0, 23), ylim=(0, None))
        ax.set_xticks([0, 6, 12, 18, 23])
        ax.grid(axis="y")
        ax.legend(frameon=False, fontsize=10)
    axes[0].set_ylabel("Mean hourly energy demand · GWh")
    fig.suptitle("Local-hour demand schedules", x=0.06, ha="left", fontsize=19, fontweight="bold")
    fig.text(
        0.06,
        0.025,
        "Sources: U.S. EIA; project calculations. 2024–2025 valid hourly observations. Shared scale across regions.\n"
        "UTC keys retain the repeated autumn DST hour. Weekday/weekend differences are descriptive.",
        fontsize=9,
        color="#666666",
    )
    fig.subplots_adjust(left=0.065, right=0.97, bottom=0.22, top=0.8, wspace=0.16)
    fig.savefig(args.output_dir / "hourly-profiles.png", dpi=180, facecolor="white")
    plt.close(fig)
    daily = read_rows(args.input_dir, "daily")
    fig, axes = plt.subplots(1, 3, figsize=(14, 5.4), sharex=True, sharey=True)
    for ax, code in zip(axes, COLORS, strict=True):
        rows = [
            r
            for r in daily
            if r["region_code"] == code
            and r["demand_gwh"] is not None
            and r["temperature_c"] is not None
        ]
        ax.scatter(
            [float(r["temperature_c"]) for r in rows],
            [float(r["demand_gwh"]) for r in rows],
            color=COLORS[code],
            s=9,
            alpha=0.3,
            edgecolors="none",
        )
        ax.set(
            title=f"{NAMES[code]} · {len(rows):,} complete days",
            xlabel="Three-city weather proxy · °C",
            ylim=(0, None),
        )
        ax.grid(axis="y")
    axes[0].set_ylabel("Complete-day demand · GWh")
    fig.suptitle(
        "Temperature and demand: descriptive context",
        x=0.06,
        ha="left",
        fontsize=19,
        fontweight="bold",
    )
    fig.text(
        0.06,
        0.025,
        "Sources: U.S. EIA and NASA POWER; project calculations. Local dates 2024–2025; complete demand and weather days only.\n"
        "Equal-weight grid proxies do not represent every load centre. Seasonality and other factors confound this relationship.",
        fontsize=9,
        color="#666666",
    )
    fig.subplots_adjust(left=0.065, right=0.97, bottom=0.22, top=0.8, wspace=0.16)
    fig.savefig(args.output_dir / "weather-context.png", dpi=180, facecolor="white")
    plt.close(fig)
    print("Rendered 3 figures from source-backed aggregate evidence")


if __name__ == "__main__":
    main()
