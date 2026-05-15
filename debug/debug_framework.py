#!/usr/bin/env python3
"""Generate and run controlled GTAPF debug experiments.

The normal benchmark cases mix many effects together.  These synthetic cases
hold the map shape simple so we can compare corridor length and agent density
more directly.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import re
import subprocess
import sys
import time
from collections import Counter, defaultdict, deque
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Sequence, Set, Tuple


REPO_ROOT = Path(__file__).resolve().parents[1]
DEBUG_ROOT = Path(__file__).resolve().parent
SCENARIOS_ROOT = DEBUG_ROOT / "scenarios"
RESULTS_ROOT = DEBUG_ROOT / "results"
DETAILS_ROOT = RESULTS_ROOT / "details"
LOGS_ROOT = RESULTS_ROOT / "logs"
CSV_PATH = RESULTS_ROOT / "debug_results.csv"

FACT_RE = re.compile(r"^\s*([A-Za-z_][A-Za-z0-9_]*)\((.*)\)\.\s*$")
DETAIL_SEPARATOR = "\n"


@dataclass(frozen=True)
class ScenarioSpec:
    name: str
    corridor_length: int
    agent_count: int
    corridor_case: str
    agent_case: str
    description: str


SCENARIOS: Dict[str, ScenarioSpec] = {
    "short_low": ScenarioSpec(
        name="short_low",
        corridor_length=8,
        agent_count=2,
        corridor_case="short",
        agent_case="low",
        description="Short corridor with low traffic; baseline case.",
    ),
    "long_low": ScenarioSpec(
        name="long_low",
        corridor_length=36,
        agent_count=2,
        corridor_case="long",
        agent_case="low",
        description="Long corridor with low traffic; isolates long abstraction repair.",
    ),
    "short_high": ScenarioSpec(
        name="short_high",
        corridor_length=8,
        agent_count=12,
        corridor_case="short",
        agent_case="high",
        description="Short corridor with high traffic; isolates agent conflict density.",
    ),
    "long_high": ScenarioSpec(
        name="long_high",
        corridor_length=36,
        agent_count=12,
        corridor_case="long",
        agent_case="high",
        description="Long corridor with high traffic; combined stress case.",
    ),
}


def parse_atom_value(value: str):
    value = value.strip()
    if re.fullmatch(r"-?\d+", value):
        return int(value)
    return value


def split_args(arg_text: str) -> List[object]:
    if not arg_text.strip():
        return []
    return [parse_atom_value(part) for part in arg_text.split(",")]


def iter_facts(path: Path) -> Iterable[Tuple[str, List[object]]]:
    if not path.exists():
        return
    with path.open("r", encoding="utf-8", errors="replace") as handle:
        for line in handle:
            match = FACT_RE.match(line)
            if match:
                yield match.group(1), split_args(match.group(2))


def write_lines(path: Path, lines: Iterable[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for line in lines:
            handle.write(line)
            if not line.endswith("\n"):
                handle.write("\n")


def add_edge(edges: Set[Tuple[int, int]], left: int, right: int) -> None:
    edges.add((left, right))
    edges.add((right, left))


def scenario_dir(spec: ScenarioSpec) -> Path:
    return SCENARIOS_ROOT / spec.name


def build_scenario_graph(spec: ScenarioSpec) -> Tuple[Set[int], Set[Tuple[int, int]], Set[int], Dict[int, int]]:
    """Build a graph with one pod-lined corridor and side parking nodes."""

    length = spec.corridor_length
    vertices: Set[int] = set()
    edges: Set[Tuple[int, int]] = set()
    pods: Set[int] = set()
    starts: Dict[int, int] = {}

    corridor_nodes = list(range(length))
    vertices.update(corridor_nodes)

    for node in corridor_nodes[:-1]:
        add_edge(edges, node, node + 1)

    pod_base = 1000
    for corridor_node in corridor_nodes:
        pod_node = pod_base + corridor_node
        vertices.add(pod_node)
        pods.add(pod_node)
        add_edge(edges, corridor_node, pod_node)

    left_count = (spec.agent_count + 1) // 2
    for index in range(spec.agent_count):
        robot_id = index + 1
        if index < left_count:
            start_node = 2000 + index
            attach_to = 0
        else:
            start_node = 3000 + index
            attach_to = length - 1
        vertices.add(start_node)
        starts[robot_id] = start_node
        add_edge(edges, start_node, attach_to)

    return vertices, edges, pods, starts


def make_map_lines(vertices: Set[int], edges: Set[Tuple[int, int]], pods: Set[int]) -> List[str]:
    lines: List[str] = []
    for vertex in sorted(vertices):
        lines.append(f"vertice({vertex}).")
        if vertex in pods:
            lines.append(f"pods({vertex}).")
        for src, dst in sorted(edge for edge in edges if edge[0] == vertex):
            lines.append(f"edge({src},{dst}).")
    return lines


def make_agents_lines(spec: ScenarioSpec, starts: Dict[int, int]) -> List[str]:
    length = spec.corridor_length
    left_count = (spec.agent_count + 1) // 2
    lines: List[str] = []

    for robot_id in range(1, spec.agent_count + 1):
        lines.append(f"agent({robot_id},{starts[robot_id]},a).")

    lines.append("group(1,0).")

    for robot_id in range(1, spec.agent_count + 1):
        starts_on_left = robot_id <= left_count
        if starts_on_left:
            goal_offset = length - 1 - ((robot_id - 1) % min(3, length))
            store = 0
            depot = length - 1
        else:
            goal_offset = (robot_id - left_count - 1) % min(3, length)
            store = length - 1
            depot = 0

        goal_pod = 1000 + goal_offset
        lines.append(f"task({robot_id},1,{goal_pod},a).")
        lines.append(f"store({robot_id},{store}).")
        lines.append(f"depot({robot_id},{depot}).")

    return lines


def make_ins_lines(spec: ScenarioSpec) -> List[str]:
    length = spec.corridor_length
    left_agents = (spec.agent_count + 1) // 2
    right_agents = spec.agent_count - left_agents
    left_label = "L" * min(left_agents, 12)
    right_label = "R" * min(right_agents, 12)
    corridor = "." * length
    pods = "|" * length
    return [
        f"{left_label}{corridor}{right_label}",
        f"{' ' * len(left_label)}{pods}",
    ]


def write_metadata(spec: ScenarioSpec, vertices: Set[int], edges: Set[Tuple[int, int]], pods: Set[int]) -> None:
    metadata = asdict(spec)
    metadata.update(
        {
            "map_vertices": len(vertices),
            "map_edges": len(edges),
            "pods": len(pods),
            "agent_density": round(spec.agent_count / float(spec.corridor_length), 6),
            "hypothesis": (
                "Longer corridors should increase abstraction repair length; "
                "more agents per corridor node should increase waits and conflict handling."
            ),
        }
    )
    path = scenario_dir(spec) / "metadata.json"
    path.write_text(json.dumps(metadata, indent=2, sort_keys=True), encoding="utf-8")


def generate_scenario(spec: ScenarioSpec) -> None:
    path = scenario_dir(spec)
    vertices, edges, pods, starts = build_scenario_graph(spec)
    write_lines(path / f"{spec.name}.map", make_map_lines(vertices, edges, pods))
    write_lines(path / f"{spec.name}.agents", make_agents_lines(spec, starts))
    write_lines(path / f"{spec.name}.ins", make_ins_lines(spec))
    write_metadata(spec, vertices, edges, pods)


def generate_scenarios(case_names: Sequence[str]) -> None:
    for name in case_names:
        generate_scenario(SCENARIOS[name])
        print(f"Generated {SCENARIOS[name].name} in {scenario_dir(SCENARIOS[name])}")


def run_solver(case_names: Sequence[str]) -> Path:
    SCENARIOS_ROOT.mkdir(parents=True, exist_ok=True)
    LOGS_ROOT.mkdir(parents=True, exist_ok=True)

    env = os.environ.copy()
    env["PROBS"] = " ".join(case_names)
    env["PDIR"] = "../../../../"

    timestamp = time.strftime("%Y%m%d_%H%M%S")
    log_path = LOGS_ROOT / f"debug_run_{timestamp}.log"
    command = ["bash", "../../test_asp"]

    print(f"Running: PROBS=\"{env['PROBS']}\" PDIR=\"{env['PDIR']}\" bash ../../test_asp")
    print(f"Log: {log_path}")

    completed = subprocess.run(
        command,
        cwd=str(SCENARIOS_ROOT),
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )
    log_path.write_text(completed.stdout, encoding="utf-8", errors="replace")

    if completed.returncode != 0:
        print(completed.stdout)
        raise SystemExit(f"test_asp failed with exit code {completed.returncode}. See {log_path}")

    return log_path


def graph_from_map(map_file: Path) -> Tuple[Set[int], Set[Tuple[int, int]], Set[int]]:
    vertices: Set[int] = set()
    edges: Set[Tuple[int, int]] = set()
    pods: Set[int] = set()
    for pred, args in iter_facts(map_file):
        if pred == "vertice" and len(args) == 1 and isinstance(args[0], int):
            vertices.add(args[0])
        elif pred == "edge" and len(args) == 2 and all(isinstance(arg, int) for arg in args):
            edges.add((int(args[0]), int(args[1])))
        elif pred == "pods" and len(args) == 1 and isinstance(args[0], int):
            pods.add(args[0])
    return vertices, edges, pods


def count_predicate(path: Path, predicate: str) -> int:
    return sum(1 for pred, _args in iter_facts(path) if pred == predicate)


def adjacency(vertices: Set[int], edges: Set[Tuple[int, int]]) -> Dict[int, Set[int]]:
    graph: Dict[int, Set[int]] = {vertex: set() for vertex in vertices}
    for src, dst in edges:
        graph.setdefault(src, set()).add(dst)
    return graph


def p_vertices(graph: Dict[int, Set[int]], pods: Set[int]) -> Set[int]:
    result = set()
    for vertex, neighbors in graph.items():
        if vertex not in pods and neighbors.intersection(pods):
            result.add(vertex)
    return result


def connected_components(nodes: Set[int], graph: Dict[int, Set[int]]) -> List[Set[int]]:
    remaining = set(nodes)
    components: List[Set[int]] = []
    while remaining:
        start = remaining.pop()
        component = {start}
        queue = deque([start])
        while queue:
            node = queue.popleft()
            for neighbor in graph.get(node, set()):
                if neighbor in remaining:
                    remaining.remove(neighbor)
                    component.add(neighbor)
                    queue.append(neighbor)
        components.append(component)
    return components


def component_diameter(component: Set[int], graph: Dict[int, Set[int]]) -> int:
    if not component:
        return 0

    def farthest_from(start: int) -> Tuple[int, int]:
        seen = {start}
        queue = deque([(start, 0)])
        farthest = (start, 0)
        while queue:
            node, dist = queue.popleft()
            if dist > farthest[1]:
                farthest = (node, dist)
            for neighbor in graph.get(node, set()):
                if neighbor in component and neighbor not in seen:
                    seen.add(neighbor)
                    queue.append((neighbor, dist + 1))
        return farthest

    endpoint, _ = farthest_from(next(iter(component)))
    _, diameter = farthest_from(endpoint)
    return diameter


def safe_max(values: List[int]):
    return max(values) if values else ""


def sort_key(value):
    return (0, value) if isinstance(value, int) else (1, str(value))


def format_path(nodes: List[object]) -> str:
    return "->".join(str(node) for node in nodes)


def format_timed_plan(result_name: str, robot, positions: Dict[int, object]) -> str:
    steps = " -> ".join(
        f"time {time} at {positions[time]}"
        for time in sorted(positions)
    )
    return f"{result_name}: robot {robot}: {steps}"


def format_action_records(records: List[Tuple[str, object, object, int]], action_name: str) -> str:
    by_result_robot = defaultdict(list)
    for result_name, robot, loc, time_value in records:
        by_result_robot[(result_name, robot)].append((time_value, loc))

    details = []
    for (result_name, robot), actions in sorted(
        by_result_robot.items(),
        key=lambda item: (item[0][0], sort_key(item[0][1])),
    ):
        pieces = [f"time {time_value} {action_name} {loc}" for time_value, loc in sorted(actions)]
        details.append(f"{result_name}: robot {robot}: " + " -> ".join(pieces))
    return DETAIL_SEPARATOR.join(details)


def collect_result_metrics(generated_dir: Path) -> Dict[str, object]:
    result_files = sorted(
        path for path in generated_dir.glob("*.result")
        if not path.name.startswith("__")
    )

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
    move_records = []
    stay_records = []

    for result_file in result_files:
        for pred, args in iter_facts(result_file):
            if pred == "move" and len(args) == 3:
                robot, loc, time_value = args
                move_count += 1
                per_agent_moves[robot] += 1
                action_times.append(int(time_value))
                move_records.append((result_file.name, robot, loc, int(time_value)))
            elif pred == "stay" and len(args) == 3:
                robot, loc, time_value = args
                stay_count += 1
                per_agent_waits[robot] += 1
                action_times.append(int(time_value))
                stay_records.append((result_file.name, robot, loc, int(time_value)))
            elif pred == "at" and len(args) == 3:
                robot, loc, time_value = args
                at_count += 1
                at_times.append(int(time_value))
                at_positions[(result_file.name, robot)][int(time_value)] = loc
            elif pred == "path" and len(args) == 4:
                robot, loc, time_value, index = args
                path_count += 1
                repair_segments.add((result_file.name, robot, index))
                repair_times.append(int(time_value))
                per_agent_repair_cost[robot] = max(per_agent_repair_cost[robot], int(time_value))
                repair_path_points[(result_file.name, robot, int(index))][int(time_value)] = loc
            elif pred == "visited" and len(args) == 4:
                robot = args[0]
                visited_count += 1
                per_agent_visited[robot] += 1

    abstract_makespan = safe_max(at_times)
    if abstract_makespan == "" and action_times:
        abstract_makespan = max(action_times) + 1
    repair_makespan = safe_max(repair_times)
    makespan_candidates = [item for item in [abstract_makespan, repair_makespan] if isinstance(item, int)]
    observed_makespan = max(makespan_candidates) if makespan_candidates else ""

    agents = sorted(
        set(per_agent_moves) | set(per_agent_waits) | set(per_agent_repair_cost) | set(per_agent_visited),
        key=sort_key,
    )
    per_agent_costs = DETAIL_SEPARATOR.join(
        f"{agent}:move={per_agent_moves[agent]}:wait={per_agent_waits[agent]}:"
        f"repair={per_agent_repair_cost[agent]}:visited={per_agent_visited[agent]}"
        for agent in agents
    )

    abstract_plan_details = []
    abstract_transition_details = []
    for (result_name, robot), positions in sorted(
        at_positions.items(),
        key=lambda item: (item[0][0], sort_key(item[0][1])),
    ):
        abstract_plan_details.append(format_timed_plan(result_name, robot, positions))
        for time_value in sorted(positions):
            if time_value + 1 in positions:
                abstract_transition_details.append(
                    f"{result_name}:r{robot}:t{time_value}:{positions[time_value]}->{positions[time_value + 1]}"
                )

    repair_path_details = []
    repair_path_details_readable = []
    repair_lengths = []
    for (result_name, robot, index), points in sorted(
        repair_path_points.items(),
        key=lambda item: (item[0][0], sort_key(item[0][1]), item[0][2]),
    ):
        ordered_times = sorted(points)
        path_nodes = [points[time_value] for time_value in ordered_times]
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
        repair_path_details_readable.append(
            f"{result_name}: robot {robot}: time {index}: "
            f"abstract plan {abstract_start} -> {abstract_end}; "
            f"repair path {format_path(path_nodes)}; "
            f"steps {repair_steps}"
        )

    longest_repair_steps = max(repair_lengths) if repair_lengths else ""
    longest_repair_detail = ""
    if repair_path_details and repair_lengths:
        longest_index = repair_lengths.index(max(repair_lengths))
        longest_repair_detail = repair_path_details[longest_index]

    return {
        "result_files": len(result_files),
        "abstract_makespan": abstract_makespan,
        "repair_makespan": repair_makespan,
        "observed_makespan": observed_makespan,
        "sum_of_costs": move_count,
        "repair_cost": sum(per_agent_repair_cost.values()),
        "concrete_cost_proxy": move_count + sum(per_agent_repair_cost.values()),
        "total_waits": stay_count,
        "move_count": move_count,
        "stay_count": stay_count,
        "at_count": at_count,
        "path_count": path_count,
        "visited_count": visited_count,
        "repair_segments": len(repair_segments),
        "longest_repair_steps": longest_repair_steps,
        "longest_repair_detail": longest_repair_detail,
        "abstract_plan_details": DETAIL_SEPARATOR.join(abstract_plan_details),
        "abstract_transitions": DETAIL_SEPARATOR.join(abstract_transition_details),
        "repair_path_details": DETAIL_SEPARATOR.join(repair_path_details),
        "repair_path_details_readable": DETAIL_SEPARATOR.join(repair_path_details_readable),
        "move_details": format_action_records(move_records, "move_to"),
        "stay_details": format_action_records(stay_records, "stay_at"),
        "per_agent_costs": per_agent_costs,
    }


def collect_scenario(spec: ScenarioSpec) -> Dict[str, object]:
    path = scenario_dir(spec)
    map_file = path / f"{spec.name}.map"
    agents_file = path / f"{spec.name}.agents"
    generated_dir = path / "generated"
    abstract_map = generated_dir / "__tmp.map"
    time_file = generated_dir / f"time_{spec.name}.txt"

    vertices, edges, pods = graph_from_map(map_file)
    graph = adjacency(vertices, edges)
    corridor_nodes = p_vertices(graph, pods)
    corridor_components = connected_components(corridor_nodes, graph)
    component_sizes = [len(component) for component in corridor_components]
    component_diameters = [component_diameter(component, graph) for component in corridor_components]
    degrees = Counter(len(neighbors) for node, neighbors in graph.items() if node not in pods)

    abstract_vertices = count_predicate(abstract_map, "vertice")
    abstract_edges = count_predicate(abstract_map, "edge")
    egroup_count = count_predicate(abstract_map, "egroup")
    egroup_3_count = count_predicate(abstract_map, "egroup_3")
    compression_ratio = ""
    if abstract_vertices:
        compression_ratio = round(len(vertices) / float(abstract_vertices), 6)

    runtime_seconds = ""
    if time_file.exists():
        match = re.search(r"Time:\s*(\d+)", time_file.read_text(encoding="utf-8", errors="replace"))
        runtime_seconds = match.group(1) if match else ""

    result_metrics = collect_result_metrics(generated_dir)
    row: Dict[str, object] = {
        "scenario_name": spec.name,
        "scenario_path": str(path.relative_to(REPO_ROOT)),
        "corridor_case": spec.corridor_case,
        "agent_case": spec.agent_case,
        "description": spec.description,
        "configured_corridor_length": spec.corridor_length,
        "total_agents": spec.agent_count,
        "agent_density": round(spec.agent_count / float(spec.corridor_length), 6),
        "total_tasks": count_predicate(agents_file, "task"),
        "map_vertices": len(vertices),
        "map_edges": len(edges),
        "pods": len(pods),
        "corridor_node_count": len(corridor_nodes),
        "corridor_component_count": len(corridor_components),
        "largest_corridor_component": max(component_sizes) if component_sizes else 0,
        "longest_corridor_component": max(component_diameters) if component_diameters else 0,
        "junction_count": sum(1 for node, neighbors in graph.items() if node not in pods and len(neighbors) >= 3),
        "dead_end_count": sum(1 for node, neighbors in graph.items() if node not in pods and len(neighbors) <= 1),
        "degree_distribution": ";".join(f"degree_{degree}={count}" for degree, count in sorted(degrees.items())),
        "abstract_vertices": abstract_vertices,
        "abstract_edges": abstract_edges,
        "egroup_count": egroup_count,
        "egroup_3_count": egroup_3_count,
        "compression_ratio": compression_ratio,
        "runtime_seconds": runtime_seconds,
        "generated_dir": str(generated_dir),
    }
    row.update(result_metrics)
    return row


def merge_csv_rows(csv_path: Path, rows: Sequence[Dict[str, object]]) -> None:
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    existing_rows: List[Dict[str, object]] = []
    fieldnames: List[str] = []

    if csv_path.exists():
        with csv_path.open("r", newline="", encoding="utf-8") as handle:
            reader = csv.DictReader(handle)
            existing_rows = list(reader)
            fieldnames = list(reader.fieldnames or [])

    for row in rows:
        for field in row:
            if field not in fieldnames:
                fieldnames.append(field)

    new_names = {str(row.get("scenario_name", "")) for row in rows}
    kept_rows = []
    seen_names = set()
    for row in reversed(existing_rows):
        name = row.get("scenario_name", "")
        if name in new_names:
            continue
        if name and name in seen_names:
            continue
        if name:
            seen_names.add(name)
        kept_rows.append(row)
    kept_rows.reverse()

    with csv_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(kept_rows)
        writer.writerows(rows)


def collect_scenarios(case_names: Sequence[str]) -> None:
    DETAILS_ROOT.mkdir(parents=True, exist_ok=True)
    rows = []
    for name in case_names:
        row = collect_scenario(SCENARIOS[name])
        rows.append(row)
        detail_path = DETAILS_ROOT / f"{name}.json"
        detail_path.write_text(json.dumps(row, indent=2, sort_keys=True), encoding="utf-8")
        print(f"Collected {name}: makespan={row['observed_makespan']} longest_repair={row['longest_repair_steps']}")

    merge_csv_rows(CSV_PATH, rows)
    print(f"Saved debug CSV: {CSV_PATH}")


def selected_cases(values: Sequence[str]) -> List[str]:
    if not values:
        return list(SCENARIOS)
    names: List[str] = []
    for value in values:
        if value == "all":
            names.extend(SCENARIOS)
        elif value in SCENARIOS:
            names.append(value)
        else:
            valid = ", ".join(SCENARIOS)
            raise SystemExit(f"Unknown case {value!r}. Valid cases: {valid}")
    deduped = []
    seen = set()
    for name in names:
        if name not in seen:
            deduped.append(name)
            seen.add(name)
    return deduped


def add_case_argument(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--cases",
        nargs="*",
        default=["all"],
        help="Cases to use: all, short_low, long_low, short_high, long_high",
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Controlled GTAPF debug experiment framework")
    subparsers = parser.add_subparsers(dest="command", required=True)

    list_parser = subparsers.add_parser("list", help="List available debug cases")
    list_parser.set_defaults(_uses_cases=False)

    generate_parser = subparsers.add_parser("generate", help="Generate debug scenario files")
    add_case_argument(generate_parser)

    run_parser = subparsers.add_parser("run", help="Run test_asp on generated debug scenarios")
    add_case_argument(run_parser)
    run_parser.add_argument("--no-collect", action="store_true", help="Do not collect CSV metrics after running")

    collect_parser = subparsers.add_parser("collect", help="Collect metrics from existing debug generated folders")
    add_case_argument(collect_parser)

    all_parser = subparsers.add_parser("all", help="Generate, run, and collect debug metrics")
    add_case_argument(all_parser)

    args = parser.parse_args()

    if args.command == "list":
        for spec in SCENARIOS.values():
            print(
                f"{spec.name}: corridor={spec.corridor_case}({spec.corridor_length}), "
                f"agents={spec.agent_case}({spec.agent_count})"
            )
        return

    cases = selected_cases(args.cases)

    if args.command == "generate":
        generate_scenarios(cases)
    elif args.command == "run":
        run_solver(cases)
        if not args.no_collect:
            collect_scenarios(cases)
    elif args.command == "collect":
        collect_scenarios(cases)
    elif args.command == "all":
        generate_scenarios(cases)
        run_solver(cases)
        collect_scenarios(cases)
    else:
        parser.print_help()
        sys.exit(2)


if __name__ == "__main__":
    main()
