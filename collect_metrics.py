#!/usr/bin/env python3
"""Collect metrics for one GTAPF scenario into a CSV file.

Expected workflow:

    cd /path/to/mapf-study/22
    PROBS="0" bash ../test_asp

    cd /path/to/mapf-study
    python3 collect_metrics.py --scenario 22/0 --csv experiment_results.csv

The script reads original input files from:

    22/0/0.map
    22/0/0.agents

and generated output files from:

    22/0/generated/

It appends one row per scenario.  The first column is named `scenario_name`,
using this format:

    22_0_168v_177e_4a
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


def iter_facts(path: Path) -> Iterable[Tuple[str, List[object]]]:
    if not path.exists():
        return
    with path.open("r", encoding="utf-8", errors="replace") as handle:
        for line in handle:
            match = FACT_RE.match(line)
            if match:
                yield match.group(1), split_args(match.group(2))


def count_predicate(path: Path, predicate: str) -> int:
    return sum(1 for pred, _args in iter_facts(path) if pred == predicate)


def read_runtime_seconds(path: Path) -> str:
    if not path.exists():
        return ""
    match = TIME_RE.search(path.read_text(encoding="utf-8", errors="replace"))
    return match.group(1) if match else ""


def safe_max(values: List[int]):
    return max(values) if values else ""


def sort_key(value):
    return (0, value) if isinstance(value, int) else (1, str(value))


def format_node(value) -> str:
    return str(value)


def format_path(nodes: List[object]) -> str:
    return "->".join(format_node(node) for node in nodes)


def collect_scenario(root: Path, scenario: str) -> Dict[str, object]:
    try:
        benchmark, instance = scenario.split("/", 1)
    except ValueError as exc:
        raise SystemExit("Use --scenario like 22/0 or 33/2") from exc

    scenario_dir = root / benchmark / instance
    generated_dir = scenario_dir / "generated"

    map_file = scenario_dir / f"{instance}.map"
    agents_file = scenario_dir / f"{instance}.agents"
    abstract_map = generated_dir / "__tmp.map"
    time_file = generated_dir / f"time_{instance}.txt"
    result_files = sorted(
        path for path in generated_dir.glob("*.result")
        if not path.name.startswith("__")
    )

    total_agents = count_predicate(agents_file, "agent")
    total_tasks = count_predicate(agents_file, "task")
    map_vertices = count_predicate(map_file, "vertice")
    map_edges = count_predicate(map_file, "edge")
    pods = count_predicate(map_file, "pods")
    abstract_vertices = count_predicate(abstract_map, "vertice")
    abstract_edges = count_predicate(abstract_map, "edge")

    move_count = 0
    stay_count = 0
    at_count = 0
    path_count = 0
    visited_count = 0

    action_times: List[int] = []
    at_times: List[int] = []
    repair_times: List[int] = []

    per_agent_moves = defaultdict(int)
    per_agent_waits = defaultdict(int)
    per_agent_repair_cost = defaultdict(int)
    per_agent_visited = defaultdict(int)

    repair_segments = set()
    at_positions = defaultdict(dict)
    repair_path_points = defaultdict(dict)

    for result_file in result_files:
        for pred, args in iter_facts(result_file):
            if pred == "move" and len(args) == 3:
                robot, _loc, time = args
                move_count += 1
                per_agent_moves[robot] += 1
                action_times.append(int(time))
            elif pred == "stay" and len(args) == 3:
                robot, _loc, time = args
                stay_count += 1
                per_agent_waits[robot] += 1
                action_times.append(int(time))
            elif pred == "at" and len(args) == 3:
                robot, loc, time = args
                at_count += 1
                at_times.append(int(time))
                at_positions[(result_file.name, robot)][int(time)] = loc
            elif pred == "path" and len(args) == 4:
                robot, loc, time, index = args
                path_count += 1
                repair_segments.add((result_file.name, robot, index))
                repair_times.append(int(time))
                per_agent_repair_cost[robot] = max(per_agent_repair_cost[robot], int(time))
                repair_path_points[(result_file.name, robot, int(index))][int(time)] = loc
            elif pred == "visited" and len(args) == 4:
                robot = args[0]
                visited_count += 1
                per_agent_visited[robot] += 1

    abstract_makespan = safe_max(at_times)
    if abstract_makespan == "" and action_times:
        abstract_makespan = max(action_times) + 1

    repair_makespan = safe_max(repair_times)
    makespan_candidates = [x for x in [abstract_makespan, repair_makespan] if isinstance(x, int)]
    observed_makespan = max(makespan_candidates) if makespan_candidates else ""

    sum_of_costs = move_count
    total_waits = stay_count
    repair_cost = sum(per_agent_repair_cost.values())
    concrete_cost_proxy = sum_of_costs + repair_cost

    dimension = f"{map_vertices}v_{map_edges}e"
    scenario_name = f"{benchmark}_{instance}_{dimension}_{total_agents}a"

    agents = sorted(set(per_agent_moves) | set(per_agent_waits) | set(per_agent_repair_cost) | set(per_agent_visited))
    per_agent_costs = ";".join(
        f"{agent}:move={per_agent_moves[agent]}:wait={per_agent_waits[agent]}:"
        f"repair={per_agent_repair_cost[agent]}:visited={per_agent_visited[agent]}"
        for agent in agents
    )

    abstract_transition_details = []
    for (result_name, robot), positions in sorted(
        at_positions.items(),
        key=lambda item: (item[0][0], sort_key(item[0][1])),
    ):
        for time in sorted(positions):
            if time + 1 in positions:
                abstract_transition_details.append(
                    f"{result_name}:r{robot}:t{time}:{positions[time]}->{positions[time + 1]}"
                )

    repair_path_details = []
    repair_lengths = []
    for (result_name, robot, index), points in sorted(
        repair_path_points.items(),
        key=lambda item: (item[0][0], sort_key(item[0][1]), item[0][2]),
    ):
        ordered_times = sorted(points)
        path_nodes = [points[time] for time in ordered_times]
        if not path_nodes:
            continue

        abstract_positions = at_positions.get((result_name, robot), {})
        abstract_start = abstract_positions.get(index, path_nodes[0])
        abstract_end = abstract_positions.get(index + 1, path_nodes[-1])
        repair_steps = max(ordered_times) if ordered_times else 0
        repair_lengths.append(repair_steps)
        repair_path_details.append(
            f"{result_name}:r{robot}:t{index}:"
            f"abstract={abstract_start}->{abstract_end}:"
            f"repair={format_path(path_nodes)}:"
            f"steps={repair_steps}"
        )

    longest_repair_steps = max(repair_lengths) if repair_lengths else ""
    longest_repair_detail = ""
    if repair_path_details and repair_lengths:
        longest_index = repair_lengths.index(max(repair_lengths))
        longest_repair_detail = repair_path_details[longest_index]

    return {
        "scenario_name": scenario_name,
        "scenario": scenario,
        "benchmark": benchmark,
        "instance": instance,
        "dimension": dimension,
        "total_agents": total_agents,
        "total_tasks": total_tasks,
        "map_vertices": map_vertices,
        "map_edges": map_edges,
        "pods": pods,
        "abstract_vertices": abstract_vertices,
        "abstract_edges": abstract_edges,
        "runtime_seconds": read_runtime_seconds(time_file),
        "result_files": len(result_files),
        "abstract_makespan": abstract_makespan,
        "repair_makespan": repair_makespan,
        "observed_makespan": observed_makespan,
        "sum_of_costs": sum_of_costs,
        "repair_cost": repair_cost,
        "concrete_cost_proxy": concrete_cost_proxy,
        "total_waits": total_waits,
        "move_count": move_count,
        "stay_count": stay_count,
        "at_count": at_count,
        "path_count": path_count,
        "visited_count": visited_count,
        "repair_segments": len(repair_segments),
        "abstract_transitions": ";".join(abstract_transition_details),
        "repair_path_details": ";".join(repair_path_details),
        "longest_repair_steps": longest_repair_steps,
        "longest_repair_detail": longest_repair_detail,
        "per_agent_costs": per_agent_costs,
        "generated_dir": str(generated_dir),
    }


def append_csv(csv_path: Path, row: Dict[str, object]) -> None:
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    if csv_path.exists():
        with csv_path.open("r", newline="", encoding="utf-8") as handle:
            reader = csv.DictReader(handle)
            existing_rows = list(reader)
            existing_fields = reader.fieldnames or []
        fieldnames = list(existing_fields)
        for field in row:
            if field not in fieldnames:
                fieldnames.append(field)
        if fieldnames != existing_fields:
            with csv_path.open("w", newline="", encoding="utf-8") as handle:
                writer = csv.DictWriter(handle, fieldnames=fieldnames)
                writer.writeheader()
                writer.writerows(existing_rows)
                writer.writerow(row)
            return

    write_header = not csv_path.exists()
    with csv_path.open("a", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(row.keys()))
        if write_header:
            writer.writeheader()
        writer.writerow(row)


def main() -> None:
    parser = argparse.ArgumentParser(description="Collect one GTAPF scenario's metrics into a CSV")
    parser.add_argument("--root", default=".", help="mapf-study repo root")
    parser.add_argument("--scenario", required=True, help="Scenario such as 22/0 or 33/2")
    parser.add_argument("--csv", default="experiment_results.csv", help="CSV path")
    args = parser.parse_args()

    root = Path(args.root).expanduser().resolve()
    csv_path = Path(args.csv).expanduser()
    if not csv_path.is_absolute():
        csv_path = root / csv_path

    row = collect_scenario(root, args.scenario)
    append_csv(csv_path, row)
    print(f"Appended {row['scenario_name']} to {csv_path}")


if __name__ == "__main__":
    main()
