#!/usr/bin/env python3
"""Convert GTAPF result files into ASPRILO visualizer input.

Example:

    cd /path/to/mapf-study
    python3 make_asprilo_visualization.py --scenario 22/0

This writes files like:

    22/0/generated/asprilo/f1.agents.asprilo.lp
    22/0/generated/asprilo/f2.agents.asprilo.lp
    22/0/generated/asprilo/combined.asprilo.lp

The output contains ASPRILO-style `init/2` atoms for the grid and robots,
visual markers for GTAPF pod/shelf/corridor cells, plus `occurs/3` atoms
for robot movement.
"""

from __future__ import annotations

import argparse
import re
from collections import Counter, defaultdict, deque
from pathlib import Path
from typing import Dict, Iterable, List, Tuple


FACT_RE = re.compile(r"^\s*([A-Za-z_][A-Za-z0-9_]*)\((.*)\)\.\s*$")


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
    with path.open("r", encoding="utf-8", errors="replace") as handle:
        for line in handle:
            match = FACT_RE.match(line)
            if match:
                yield match.group(1), split_args(match.group(2))


def read_map(map_file: Path) -> Tuple[List[int], List[Tuple[int, int]], List[int], int]:
    vertices = []
    edges = []
    pods = []
    for pred, args in iter_facts(map_file):
        if pred == "vertice" and len(args) == 1 and isinstance(args[0], int):
            vertices.append(args[0])
        elif pred == "pods" and len(args) == 1 and isinstance(args[0], int):
            pods.append(args[0])
        elif pred == "edge" and len(args) == 2:
            src, dst = args
            if isinstance(src, int) and isinstance(dst, int):
                edges.append((src, dst))

    differences = [abs(dst - src) for src, dst in edges if abs(dst - src) > 1]
    if not differences:
        raise SystemExit(f"Could not infer grid width from {map_file}")

    columns = Counter(differences).most_common(1)[0][0]
    return sorted(vertices), edges, sorted(pods), columns


def read_agents(agents_file: Path) -> Dict[int, int]:
    starts = {}
    for pred, args in iter_facts(agents_file):
        if pred == "agent" and len(args) >= 2:
            robot, start = args[0], args[1]
            if isinstance(robot, int) and isinstance(start, int):
                starts[robot] = start
    return starts


def result_sort_key(path: Path):
    match = re.match(r"f(\d+)\.agents\.result$", path.name)
    if match:
        return int(match.group(1)), path.name
    return 10**9, path.name


def list_result_files(generated_dir: Path) -> List[Path]:
    result_files = []
    listed_names = set()
    outs_file = generated_dir / "outs.txt"

    if outs_file.exists():
        for line in outs_file.read_text(encoding="utf-8", errors="replace").splitlines():
            agent_file = line.strip()
            if not agent_file:
                continue
            result_file = generated_dir / f"{agent_file}.result"
            listed_names.add(result_file.name)
            if result_file.exists():
                result_files.append(result_file)

    extras = sorted(
        (
            path for path in generated_dir.glob("*.result")
            if not path.name.startswith("__") and path.name not in listed_names
        ),
        key=result_sort_key,
    )
    result_files.extend(extras)
    return result_files


def node_to_xy(node: int, columns: int) -> Tuple[int, int]:
    return (node % columns) + 1, (node // columns) + 1


def shortest_path(graph: Dict[int, List[int]], source: int, target: int) -> List[int]:
    if source == target:
        return [source, target]

    queue = deque([source])
    previous = {source: None}

    while queue:
        node = queue.popleft()
        for neighbor in graph.get(node, []):
            if neighbor in previous:
                continue
            previous[neighbor] = node
            if neighbor == target:
                queue.clear()
                break
            queue.append(neighbor)

    if target not in previous:
        return [source, target]

    path = []
    node = target
    while node is not None:
        path.append(node)
        node = previous[node]
    return list(reversed(path))


def read_result_paths(result_file: Path, graph: Dict[int, List[int]]) -> Dict[int, List[int]]:
    at_positions = defaultdict(dict)
    points = defaultdict(dict)

    for pred, args in iter_facts(result_file):
        if pred == "at" and len(args) == 3:
            robot, loc, time = args
            if all(isinstance(value, int) for value in (robot, loc, time)):
                at_positions[robot][time] = loc
        elif pred == "path" and len(args) == 4:
            robot, loc, step, index = args
            if all(isinstance(value, int) for value in (robot, loc, step, index)):
                points[(robot, index)][step] = loc

    robot_paths = {}
    for robot, positions in sorted(at_positions.items()):
        full_path = []
        times = sorted(positions)
        for time in times:
            if time + 1 not in positions:
                continue

            segment_points = points.get((robot, time))
            if segment_points:
                segment = [segment_points[step] for step in sorted(segment_points)]
                if segment[-1] != positions[time + 1]:
                    connector = shortest_path(graph, segment[-1], positions[time + 1])
                    segment.extend(connector[1:])
            else:
                segment = shortest_path(graph, positions[time], positions[time + 1])

            if full_path and full_path[-1] == segment[0]:
                full_path.extend(segment[1:])
            else:
                full_path.extend(segment)

        if not full_path and times:
            full_path.append(positions[times[0]])
        robot_paths[robot] = full_path

    return robot_paths


def direction_between(src: int, dst: int, columns: int) -> Tuple[int, int]:
    sx, sy = node_to_xy(src, columns)
    dx, dy = node_to_xy(dst, columns)
    return dx - sx, dy - sy


def combine_result_paths(
    result_files: List[Path],
    graph: Dict[int, List[int]],
    starts: Dict[int, int],
) -> Dict[int, List[int]]:
    combined_paths = {robot: [start] for robot, start in starts.items()}

    for result_file in result_files:
        result_paths = read_result_paths(result_file, graph)
        robots = sorted(set(combined_paths) | set(result_paths))
        additions = {}

        for robot in robots:
            if robot not in combined_paths:
                start = result_paths.get(robot, [starts.get(robot, 0)])[0]
                combined_paths[robot] = [start]

            current = combined_paths[robot][-1]
            segment = result_paths.get(robot, [])
            if not segment:
                additions[robot] = []
            elif current == segment[0]:
                additions[robot] = segment[1:]
            else:
                connector = shortest_path(graph, current, segment[0])
                additions[robot] = connector[1:] + segment[1:]

        segment_duration = max((len(nodes) for nodes in additions.values()), default=0)
        for robot in robots:
            combined_paths[robot].extend(additions[robot])
            if segment_duration > len(additions[robot]):
                combined_paths[robot].extend(
                    [combined_paths[robot][-1]] * (segment_duration - len(additions[robot]))
                )

    return combined_paths


def write_visualization_paths(
    output_file: Path,
    map_file: Path,
    source_label: str,
    vertices: List[int],
    pods: List[int],
    columns: int,
    robot_paths: Dict[int, List[int]],
    highway_mode: str,
    pod_visual: str,
    corridor_visual: str,
) -> None:
    rows = (max(vertices) // columns) + 1 if vertices else 0
    vertex_set = set(vertices)
    pod_nodes = set(pods)
    corridor_nodes = vertex_set - pod_nodes
    missing_cells = sorted(set(range(rows * columns)) - vertex_set)

    highway_nodes = set()
    typed_visual_nodes = defaultdict(set)

    if corridor_visual == "highway":
        highway_nodes.update(corridor_nodes)

    if pod_visual == "highway":
        highway_nodes.update(pod_nodes)
    elif pod_visual != "none":
        typed_visual_nodes[pod_visual].update(pod_nodes)

    if highway_mode in ("pods", "pods-and-missing"):
        highway_nodes.update(pod_nodes)
    if highway_mode in ("missing", "pods-and-missing"):
        highway_nodes.update(missing_cells)

    visual_nodes = sorted(vertex_set | highway_nodes)

    output_file.parent.mkdir(parents=True, exist_ok=True)
    with output_file.open("w", encoding="utf-8") as handle:
        handle.write(f"% Generated from {source_label}\n")
        handle.write(f"% Map: {map_file}\n")
        handle.write(f"% Highway mode: {highway_mode}\n")
        handle.write(f"% Pod visual: {pod_visual}\n")
        handle.write(f"% Corridor visual: {corridor_visual}\n")
        handle.write(
            f"% Counts: corridors={len(corridor_nodes)}, "
            f"pods_or_shelves={len(pod_nodes)}, highways={len(highway_nodes)}, "
            f"icon_cells={sum(len(nodes) for nodes in typed_visual_nodes.values())}\n\n"
        )

        for node in visual_nodes:
            x, y = node_to_xy(node, columns)
            handle.write(f"init(object(node,{node + 1}),value(at,({x},{y}))).\n")

        if highway_nodes:
            handle.write("\n")
            for node in sorted(highway_nodes):
                x, y = node_to_xy(node, columns)
                handle.write(f"init(object(highway,{node + 1}),value(at,({x},{y}))).\n")

        for object_type, nodes in sorted(typed_visual_nodes.items()):
            if nodes:
                handle.write("\n")
                for node in sorted(nodes):
                    x, y = node_to_xy(node, columns)
                    handle.write(f"init(object({object_type},{node + 1}),value(at,({x},{y}))).\n")

        handle.write("\n")
        for robot in sorted(robot_paths):
            if not robot_paths[robot]:
                continue
            start_node = robot_paths[robot][0]
            x, y = node_to_xy(start_node, columns)
            handle.write(f"init(object(robot,{robot}),value(at,({x},{y}))).\n")

        handle.write("\n")
        for robot, nodes in sorted(robot_paths.items()):
            for time, (src, dst) in enumerate(zip(nodes, nodes[1:])):
                if src == dst:
                    continue
                dx, dy = direction_between(src, dst, columns)
                if abs(dx) + abs(dy) != 1:
                    handle.write(
                        f"% skipped non-adjacent step for robot {robot}: "
                        f"{src}->{dst} at generated time {time}\n"
                    )
                    continue
                handle.write(
                    f"occurs(object(robot,{robot}),action(move,({dx},{dy})),{time}).\n"
                )


def write_visualization(
    output_file: Path,
    map_file: Path,
    agents_file: Path,
    result_file: Path,
    highway_mode: str,
    pod_visual: str,
    corridor_visual: str,
) -> None:
    vertices, edges, pods, columns = read_map(map_file)
    graph = defaultdict(list)
    for src, dst in edges:
        graph[src].append(dst)
    starts = read_agents(agents_file)
    robot_paths = read_result_paths(result_file, graph)
    for robot, start in starts.items():
        robot_paths.setdefault(robot, [start])
    write_visualization_paths(
        output_file,
        map_file,
        str(result_file),
        vertices,
        pods,
        columns,
        robot_paths,
        highway_mode,
        pod_visual,
        corridor_visual,
    )


def write_combined_visualization(
    output_file: Path,
    map_file: Path,
    agents_file: Path,
    result_files: List[Path],
    highway_mode: str,
    pod_visual: str,
    corridor_visual: str,
) -> None:
    vertices, edges, pods, columns = read_map(map_file)
    graph = defaultdict(list)
    for src, dst in edges:
        graph[src].append(dst)
    starts = read_agents(agents_file)
    robot_paths = combine_result_paths(result_files, graph, starts)
    source_label = " + ".join(str(path) for path in result_files)
    write_visualization_paths(
        output_file,
        map_file,
        source_label,
        vertices,
        pods,
        columns,
        robot_paths,
        highway_mode,
        pod_visual,
        corridor_visual,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Create ASPRILO visualizer files for a GTAPF scenario")
    parser.add_argument("--root", default=".", help="mapf-study repo root")
    parser.add_argument("--scenario", required=True, help="Scenario such as 22/0")
    parser.add_argument("--result", help="Specific result file name, e.g. f2.agents.result")
    parser.add_argument("--out-dir", help="Output directory; default is SCENARIO/generated/asprilo")
    parser.add_argument("--combined", action="store_true", help="Also write one combined visualization file")
    parser.add_argument(
        "--highway-mode",
        choices=["none", "pods", "missing", "pods-and-missing"],
        default="missing",
        help="Extra GTAPF block/wall cells to mark as ASPRILO highways",
    )
    parser.add_argument(
        "--pod-visual",
        choices=["shelf", "checkpoint", "pickingStation", "chargingStation", "highway", "none"],
        default="shelf",
        help="How to draw GTAPF pod/shelf cells",
    )
    parser.add_argument(
        "--corridor-visual",
        choices=["highway", "none"],
        default="highway",
        help="How to draw traversable non-pod corridor cells",
    )
    args = parser.parse_args()

    root = Path(args.root).expanduser().resolve()
    benchmark, instance = args.scenario.split("/", 1)
    scenario_dir = root / benchmark / instance
    generated_dir = scenario_dir / "generated"
    map_file = scenario_dir / f"{instance}.map"
    agents_file = scenario_dir / f"{instance}.agents"

    out_dir = Path(args.out_dir).expanduser() if args.out_dir else generated_dir / "asprilo"
    if not out_dir.is_absolute():
        out_dir = root / out_dir

    if args.result:
        result_files = [generated_dir / args.result]
    else:
        result_files = list_result_files(generated_dir)

    if not result_files:
        raise SystemExit(f"No final .result files found in {generated_dir}")

    for result_file in result_files:
        if not result_file.exists():
            raise SystemExit(f"Missing result file: {result_file}")
        output_file = out_dir / result_file.name.replace(".result", ".asprilo.lp")
        write_visualization(
            output_file,
            map_file,
            agents_file,
            result_file,
            args.highway_mode,
            args.pod_visual,
            args.corridor_visual,
        )
        print(f"Wrote {output_file}")

    if args.combined and len(result_files) > 1:
        output_file = out_dir / "combined.asprilo.lp"
        write_combined_visualization(
            output_file,
            map_file,
            agents_file,
            result_files,
            args.highway_mode,
            args.pod_visual,
            args.corridor_visual,
        )
        print(f"Wrote {output_file}")


if __name__ == "__main__":
    main()
