#!/usr/bin/env python3
"""Analyze GTAF/GTAPF generated result files into CSV metrics.

Run after manual experiments, for example:

    cd /path/to/mapf-study
    python3 analyze_results.py --root . --out experiment_metrics.csv

It parses files like:

    22/0/f1.agents.result
    22/1/f2.agents.result

and extracts makespan, sum of costs, per-agent movement counts, waits,
repair-path segments, and visited counts.
"""

from __future__ import annotations

import argparse
import csv
import re
from collections import defaultdict
from pathlib import Path
from typing import Dict, Iterable, List, Tuple

FACT_RE = re.compile(r"^\s*([A-Za-z_][A-Za-z0-9_]*)\((.*)\)\.\s*$")
TIME_RE = re.compile(r"Time:\s*(\d+)")


def parse_arg(value: str):
    value = value.strip()
    if re.fullmatch(r"-?\d+", value):
        return int(value)
    return value


def split_args(arg_text: str) -> List[object]:
    if not arg_text.strip():
        return []
    return [parse_arg(part) for part in arg_text.split(",")]


def iter_facts(path: Path) -> Iterable[Tuple[str, Tuple[object, ...]]]:
    with path.open("r", encoding="utf-8", errors="replace") as handle:
        for line in handle:
            match = FACT_RE.match(line)
            if match:
                yield match.group(1), tuple(split_args(match.group(2)))


def read_runtime(instance_dir: Path, instance: str) -> str:
    time_file = instance_dir / f"time_{instance}.txt"
    if not time_file.exists():
        return ""
    match = TIME_RE.search(time_file.read_text(encoding="utf-8", errors="replace"))
    return match.group(1) if match else ""


def analyze_result_file(path: Path, root: Path) -> Dict[str, object]:
    instance_dir = path.parent
    instance = instance_dir.name
    benchmark = instance_dir.parent.name
    rel = path.relative_to(root)

    move_by_agent = defaultdict(int)
    stay_by_agent = defaultdict(int)
    at_times_by_agent = defaultdict(list)
    path_times_by_agent_index = defaultdict(list)
    path_vertices_by_agent_index = defaultdict(set)
    visited_by_agent = defaultdict(int)

    move_count = 0
    stay_count = 0
    at_count = 0
    path_count = 0
    visited_count = 0
    max_action_time = -1
    max_at_time = -1
    max_path_time = -1
    max_index = -1

    for pred, args in iter_facts(path):
        if pred == "move" and len(args) == 3:
            robot, _loc, t = args
            move_count += 1
            move_by_agent[robot] += 1
            max_action_time = max(max_action_time, int(t))
        elif pred == "stay" and len(args) == 3:
            robot, _loc, t = args
            stay_count += 1
            stay_by_agent[robot] += 1
            max_action_time = max(max_action_time, int(t))
        elif pred == "at" and len(args) == 3:
            robot, _loc, t = args
            at_count += 1
            at_times_by_agent[robot].append(int(t))
            max_at_time = max(max_at_time, int(t))
        elif pred == "path" and len(args) == 4:
            robot, loc, t, idx = args
            path_count += 1
            key = (robot, idx)
            path_times_by_agent_index[key].append(int(t))
            path_vertices_by_agent_index[key].add(loc)
            max_path_time = max(max_path_time, int(t))
            max_index = max(max_index, int(idx))
        elif pred == "visited" and len(args) == 4:
            robot = args[0]
            visited_count += 1
            visited_by_agent[robot] += 1

    agents = sorted(set(move_by_agent) | set(stay_by_agent) | set(at_times_by_agent) | {k[0] for k in path_times_by_agent_index})

    # Abstract makespan: normal MAPF plan horizon from at/3 if present.
    # If at/3 is absent, action time + 1 is the conservative horizon.
    abstract_makespan = max_at_time if max_at_time >= 0 else (max_action_time + 1 if max_action_time >= 0 else "")

    # Repair makespan: maximum local time inside inserted path/4 segments.
    repair_makespan = max_path_time if max_path_time >= 0 else ""

    # Combined horizon is a descriptive upper signal, not a formal synchronized makespan.
    numeric_makespans = [x for x in [abstract_makespan, repair_makespan] if isinstance(x, int)]
    observed_makespan = max(numeric_makespans) if numeric_makespans else ""

    # Sum of costs in the abstract plan: count real move actions, not waits.
    abstract_sum_of_costs = sum(move_by_agent.values())

    # Wait cost is recorded separately so you can plot congestion/waiting.
    total_waits = sum(stay_by_agent.values())

    # Repair path cost: for each repair segment, path/4 has one atom per vertex/time.
    # Moving through k listed time points costs max(t), equivalent to len(segment)-1
    # when the segment starts at t=0 and is contiguous.
    repair_sum_of_costs = 0
    repair_segments = 0
    for key, times in path_times_by_agent_index.items():
        if not times:
            continue
        repair_segments += 1
        repair_sum_of_costs += max(times)

    # A practical concrete cost proxy: abstract moves plus inserted repair movement.
    # Keep abstract and repair columns separate for more careful analysis.
    concrete_cost_proxy = abstract_sum_of_costs + repair_sum_of_costs

    per_agent_move = ";".join(f"{agent}:{move_by_agent[agent]}" for agent in agents)
    per_agent_wait = ";".join(f"{agent}:{stay_by_agent[agent]}" for agent in agents)
    per_agent_visited = ";".join(f"{agent}:{visited_by_agent[agent]}" for agent in agents)

    return {
        "benchmark": benchmark,
        "instance": instance,
        "result_file": str(rel),
        "task_file": path.name.replace(".result", ""),
        "runtime_seconds": read_runtime(instance_dir, instance),
        "agents_in_result": len(agents),
        "abstract_makespan": abstract_makespan,
        "repair_makespan": repair_makespan,
        "observed_makespan": observed_makespan,
        "abstract_sum_of_costs": abstract_sum_of_costs,
        "repair_sum_of_costs": repair_sum_of_costs,
        "concrete_cost_proxy": concrete_cost_proxy,
        "total_waits": total_waits,
        "move_count": move_count,
        "stay_count": stay_count,
        "at_count": at_count,
        "path_count": path_count,
        "visited_count": visited_count,
        "repair_segments": repair_segments,
        "max_repair_index": max_index if max_index >= 0 else "",
        "per_agent_move_cost": per_agent_move,
        "per_agent_waits": per_agent_wait,
        "per_agent_visited": per_agent_visited,
    }


def find_result_files(root: Path) -> List[Path]:
    return sorted(root.glob("*/*/*.result"))


def write_csv(path: Path, rows: List[Dict[str, object]]) -> None:
    fieldnames = [
        "benchmark",
        "instance",
        "result_file",
        "task_file",
        "runtime_seconds",
        "agents_in_result",
        "abstract_makespan",
        "repair_makespan",
        "observed_makespan",
        "abstract_sum_of_costs",
        "repair_sum_of_costs",
        "concrete_cost_proxy",
        "total_waits",
        "move_count",
        "stay_count",
        "at_count",
        "path_count",
        "visited_count",
        "repair_segments",
        "max_repair_index",
        "per_agent_move_cost",
        "per_agent_waits",
        "per_agent_visited",
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def main() -> None:
    parser = argparse.ArgumentParser(description="Analyze GTAF/GTAPF .result files into CSV metrics")
    parser.add_argument("--root", default=".", help="mapf-study repository root")
    parser.add_argument("--out", default="experiment_metrics.csv", help="output CSV file")
    args = parser.parse_args()

    root = Path(args.root).expanduser().resolve()
    out = Path(args.out).expanduser()
    if not out.is_absolute():
        out = root / out

    result_files = find_result_files(root)
    rows = [analyze_result_file(path, root) for path in result_files]
    write_csv(out, rows)

    print(f"Found {len(result_files)} result files")
    print(f"Wrote {out}")


if __name__ == "__main__":
    main()
