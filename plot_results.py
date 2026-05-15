#!/usr/bin/env python3
"""Create simple charts from experiment_results.csv.

Run from the mapf-study repo root:

    python3 plot_results.py --csv experiment_results.csv

Outputs are written to:

    plots/
"""

from __future__ import annotations

import argparse
import csv
from pathlib import Path


def read_rows(csv_path: Path):
    with csv_path.open("r", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def numeric(row, key):
    value = row.get(key, "")
    if value in ("", None):
        return 0.0
    return float(value)


def main() -> None:
    parser = argparse.ArgumentParser(description="Plot GTAPF experiment CSV metrics")
    parser.add_argument("--csv", default="experiment_results.csv", help="Input CSV file")
    parser.add_argument("--out-dir", default="plots", help="Directory for PNG plots")
    args = parser.parse_args()

    csv_path = Path(args.csv).expanduser().resolve()
    out_dir = Path(args.out_dir).expanduser()
    if not out_dir.is_absolute():
        out_dir = csv_path.parent / out_dir
    out_dir.mkdir(parents=True, exist_ok=True)

    try:
        import matplotlib.pyplot as plt
    except ImportError as exc:
        raise SystemExit(
            "matplotlib is not installed. Install it without sudo using:\n"
            "  python3 -m pip install --user matplotlib"
        ) from exc

    rows = read_rows(csv_path)
    if not rows:
        raise SystemExit(f"No rows found in {csv_path}")

    labels = [row["scenario_name"] for row in rows]

    plots = [
        ("observed_makespan", "Observed Makespan", "observed_makespan_by_scenario.png"),
        ("abstract_makespan", "Abstract Makespan", "abstract_makespan_by_scenario.png"),
        ("sum_of_costs", "Sum of Costs", "sum_of_costs_by_scenario.png"),
        ("concrete_cost_proxy", "Concrete Cost Proxy", "concrete_cost_proxy_by_scenario.png"),
        ("total_waits", "Total Waits", "total_waits_by_scenario.png"),
        ("runtime_seconds", "Runtime Seconds", "runtime_by_scenario.png"),
    ]

    for key, title, filename in plots:
        values = [numeric(row, key) for row in rows]
        plt.figure(figsize=(max(9, len(labels) * 0.9), 5))
        plt.bar(labels, values)
        plt.xticks(rotation=35, ha="right")
        plt.ylabel(title)
        plt.title(title)
        plt.tight_layout()
        plt.savefig(out_dir / filename, dpi=200)
        plt.close()

    # A compact comparison chart for makespan vs cost.
    x = [numeric(row, "observed_makespan") for row in rows]
    y = [numeric(row, "sum_of_costs") for row in rows]
    plt.figure(figsize=(7, 5))
    plt.scatter(x, y)
    for label, px, py in zip(labels, x, y):
        plt.annotate(label, (px, py), fontsize=8, xytext=(4, 4), textcoords="offset points")
    plt.xlabel("Observed Makespan")
    plt.ylabel("Sum of Costs")
    plt.title("Makespan vs Sum of Costs")
    plt.tight_layout()
    plt.savefig(out_dir / "makespan_vs_sum_of_costs.png", dpi=200)
    plt.close()

    print(f"Wrote plots to {out_dir}")


if __name__ == "__main__":
    main()
