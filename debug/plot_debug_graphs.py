#!/usr/bin/env python3
"""Create comparison SVG graphs from debug_results.csv.

This script uses only the Python standard library, so it should run on the lab
machine without installing matplotlib.
"""

from __future__ import annotations

import argparse
import csv
import html
from pathlib import Path
from typing import Dict, Iterable, List, Sequence, Tuple


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CSV = REPO_ROOT / "debug" / "results" / "debug_results.csv"
DEFAULT_OUT_DIR = REPO_ROOT / "debug" / "results" / "graphs"

LONG_PROOF_CASES = [
    "cause_01_long_tunnel",
    "cause_03_head_on_traffic",
    "cause_06_large_repair_overhead",
    "cause_07_abstraction_compression",
    "cause_10_misleading_abstract_makespan",
]

MISSING_PATH_CASES = [
    "mpa_success_connected_short",
    "mpa_fail_long_missing_connector",
]

LABELS = {
    "cause_01_long_tunnel": "C01 long tunnel",
    "cause_03_head_on_traffic": "C03 head-on",
    "cause_06_large_repair_overhead": "C06 repair overhead",
    "cause_07_abstraction_compression": "C07 compression",
    "cause_10_misleading_abstract_makespan": "C10 misleading makespan",
    "mpa_success_connected_short": "MPA success",
    "mpa_fail_long_missing_connector": "MPA fail connector",
}

COLORS = [
    "#2f6bff",
    "#ff9f1c",
    "#2ec4b6",
    "#e71d36",
    "#7b2cbf",
    "#5c677d",
]


def read_rows(csv_path: Path) -> List[Dict[str, str]]:
    if not csv_path.exists():
        raise SystemExit(f"Missing CSV: {csv_path}")
    with csv_path.open("r", newline="", encoding="utf-8", errors="replace") as handle:
        return list(csv.DictReader(handle))


def numeric(row: Dict[str, str], key: str) -> float:
    value = row.get(key, "")
    if value in ("", None):
        return 0.0
    try:
        return float(value)
    except ValueError:
        return 0.0


def select_rows(rows: Sequence[Dict[str, str]], names: Sequence[str]) -> List[Dict[str, str]]:
    by_name = {row.get("scenario_name", ""): row for row in rows}
    return [by_name[name] for name in names if name in by_name]


def label_for(row: Dict[str, str]) -> str:
    name = row.get("scenario_name", "")
    return LABELS.get(name, name)


def max_value(series: Sequence[Tuple[str, Sequence[float]]]) -> float:
    values = [value for _name, items in series for value in items]
    return max(values) if values else 1.0


def svg_header(width: int, height: int) -> List[str]:
    return [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
        '<rect width="100%" height="100%" fill="#ffffff"/>',
        '<style>',
        'text{font-family:Arial,Helvetica,sans-serif;fill:#1f2937}',
        '.title{font-size:22px;font-weight:700}',
        '.axis{stroke:#374151;stroke-width:1.2}',
        '.grid{stroke:#e5e7eb;stroke-width:1}',
        '.tick{font-size:11px;fill:#6b7280}',
        '.label{font-size:12px}',
        '.legend{font-size:12px}',
        '</style>',
    ]


def write_grouped_bar_svg(
    out_path: Path,
    title: str,
    labels: Sequence[str],
    series: Sequence[Tuple[str, Sequence[float]]],
    y_label: str,
) -> None:
    if not labels or not series:
        return

    width = max(900, 150 + len(labels) * 150)
    height = 560
    left = 80
    right = 30
    top = 70
    bottom = 145
    plot_w = width - left - right
    plot_h = height - top - bottom
    ymax = max(1.0, max_value(series) * 1.15)

    lines = svg_header(width, height)
    lines.append(f'<text class="title" x="{left}" y="36">{html.escape(title)}</text>')
    lines.append(f'<text class="label" x="{left}" y="56">{html.escape(y_label)}</text>')

    for tick in range(6):
        value = ymax * tick / 5.0
        y = top + plot_h - (value / ymax) * plot_h
        lines.append(f'<line class="grid" x1="{left}" y1="{y:.1f}" x2="{left + plot_w}" y2="{y:.1f}"/>')
        lines.append(f'<text class="tick" x="{left - 8}" y="{y + 4:.1f}" text-anchor="end">{value:.1f}</text>')

    lines.append(f'<line class="axis" x1="{left}" y1="{top}" x2="{left}" y2="{top + plot_h}"/>')
    lines.append(f'<line class="axis" x1="{left}" y1="{top + plot_h}" x2="{left + plot_w}" y2="{top + plot_h}"/>')

    group_w = plot_w / len(labels)
    inner_w = group_w * 0.78
    bar_w = inner_w / max(1, len(series))
    for group_index, label in enumerate(labels):
        group_x = left + group_index * group_w + (group_w - inner_w) / 2
        for series_index, (_name, values) in enumerate(series):
            value = values[group_index] if group_index < len(values) else 0.0
            bar_h = (value / ymax) * plot_h if ymax else 0
            x = group_x + series_index * bar_w
            y = top + plot_h - bar_h
            color = COLORS[series_index % len(COLORS)]
            lines.append(
                f'<rect x="{x:.1f}" y="{y:.1f}" width="{max(2, bar_w - 4):.1f}" '
                f'height="{bar_h:.1f}" fill="{color}" rx="2"/>'
            )
            if value > 0:
                lines.append(
                    f'<text class="tick" x="{x + bar_w / 2:.1f}" y="{y - 4:.1f}" '
                    f'text-anchor="middle">{value:.1f}</text>'
                )
        label_x = left + group_index * group_w + group_w / 2
        safe_label = html.escape(label)
        lines.append(
            f'<text class="tick" x="{label_x:.1f}" y="{top + plot_h + 22}" '
            f'text-anchor="end" transform="rotate(-28 {label_x:.1f},{top + plot_h + 22})">{safe_label}</text>'
        )

    legend_x = left
    legend_y = height - 35
    for index, (name, _values) in enumerate(series):
        x = legend_x + index * 190
        color = COLORS[index % len(COLORS)]
        lines.append(f'<rect x="{x}" y="{legend_y - 12}" width="14" height="14" fill="{color}" rx="2"/>')
        lines.append(f'<text class="legend" x="{x + 20}" y="{legend_y}">{html.escape(name)}</text>')

    lines.append("</svg>")
    out_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def values(rows: Sequence[Dict[str, str]], key: str) -> List[float]:
    return [numeric(row, key) for row in rows]


def write_long_proof_graphs(rows: Sequence[Dict[str, str]], out_dir: Path) -> List[Path]:
    selected = select_rows(rows, LONG_PROOF_CASES)
    labels = [label_for(row) for row in selected]
    written: List[Path] = []
    if not selected:
        return written

    charts = [
        (
            "long_proof_makespan.svg",
            "Long Tunnel Proof: Abstract vs Repair vs Observed Makespan",
            [
                ("abstract_makespan", values(selected, "abstract_makespan")),
                ("repair_makespan", values(selected, "repair_makespan")),
                ("observed_makespan", values(selected, "observed_makespan")),
            ],
            "time steps",
        ),
        (
            "long_proof_repair_gap.svg",
            "Long Tunnel Proof: Repair Makespan Gap",
            [("repair_makespan_gap", values(selected, "repair_makespan_gap"))],
            "repair_makespan - abstract_makespan",
        ),
        (
            "long_proof_repair_overhead.svg",
            "Long Tunnel Proof: Repair Overhead Ratio",
            [("repair_overhead_ratio", values(selected, "repair_overhead_ratio"))],
            "repair_makespan / abstract_makespan",
        ),
        (
            "long_proof_compression_vertices.svg",
            "Long Tunnel Proof: Concrete vs Abstract Vertices",
            [
                ("map_vertices", values(selected, "map_vertices")),
                ("abstract_vertices", values(selected, "abstract_vertices")),
            ],
            "vertex count",
        ),
        (
            "long_proof_pressure_risk.svg",
            "Long Tunnel Proof: Opposing Pressure and Risk Score",
            [
                ("opposing_pair_pressure", values(selected, "opposing_pair_pressure")),
                ("failure_risk_score", values(selected, "failure_risk_score")),
            ],
            "score",
        ),
    ]

    for filename, title, series, y_label in charts:
        path = out_dir / filename
        write_grouped_bar_svg(path, title, labels, series, y_label)
        written.append(path)
    return written


def write_missing_path_graphs(rows: Sequence[Dict[str, str]], out_dir: Path) -> List[Path]:
    selected = select_rows(rows, MISSING_PATH_CASES)
    labels = [label_for(row) for row in selected]
    written: List[Path] = []
    if not selected:
        return written

    charts = [
        (
            "missing_path_binary_evidence.svg",
            "Missing Path Abstraction: Control vs Missing Connector",
            [
                ("concrete reachable", values(selected, "concrete_start_goal_all_reachable")),
                ("abstract plan present", values(selected, "abstract_plan_present")),
                ("missing abstraction", values(selected, "path_abstraction_missing_risk")),
                ("target triggered", values(selected, "target_failure_triggered")),
            ],
            "0 = no, 1 = yes",
        ),
        (
            "missing_path_removed_edges.svg",
            "Missing Path Abstraction: Removed Abstract Connector Edges",
            [("abstract_removed_edge_count", values(selected, "abstract_removed_edge_count"))],
            "removed abstract edges",
        ),
        (
            "missing_path_result_files.svg",
            "Missing Path Abstraction: Output Files",
            [
                ("result_files", values(selected, "result_files")),
                ("repair_path_detail_count", values(selected, "repair_path_detail_count")),
            ],
            "count",
        ),
    ]

    for filename, title, series, y_label in charts:
        path = out_dir / filename
        write_grouped_bar_svg(path, title, labels, series, y_label)
        written.append(path)
    return written


def write_index(out_dir: Path, written: Sequence[Path]) -> None:
    lines = ["# Debug Comparison Graphs", ""]
    for path in written:
        lines.append(f"- `{path.name}`")
    lines.append("")
    lines.append("These SVG files are generated from `debug/results/debug_results.csv`.")
    (out_dir / "README.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Create SVG comparison graphs for GTAPF debug results")
    parser.add_argument("--csv", default=str(DEFAULT_CSV), help="Input debug_results.csv path")
    parser.add_argument("--out-dir", default=str(DEFAULT_OUT_DIR), help="Output directory for SVG graphs")
    parser.add_argument(
        "--mode",
        choices=["all", "long-proof", "missing-path"],
        default="all",
        help="Which graph group to create",
    )
    args = parser.parse_args()

    csv_path = Path(args.csv).expanduser()
    out_dir = Path(args.out_dir).expanduser()
    if not csv_path.is_absolute():
        csv_path = (Path.cwd() / csv_path).resolve()
    if not out_dir.is_absolute():
        out_dir = (Path.cwd() / out_dir).resolve()

    rows = read_rows(csv_path)
    out_dir.mkdir(parents=True, exist_ok=True)

    written: List[Path] = []
    if args.mode in ("all", "long-proof"):
        written.extend(write_long_proof_graphs(rows, out_dir))
    if args.mode in ("all", "missing-path"):
        written.extend(write_missing_path_graphs(rows, out_dir))

    if not written:
        raise SystemExit(
            "No matching rows found. Run long-proof-all and/or missing-path-all first, then rerun this script."
        )

    write_index(out_dir, written)
    print(f"Wrote {len(written)} SVG graph files to {out_dir}")


if __name__ == "__main__":
    main()
