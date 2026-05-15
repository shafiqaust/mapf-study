#!/usr/bin/env python3
"""Generate and run controlled GTAPF debug experiments.

The normal benchmark cases mix many effects together.  These controlled cases
reuse warehouse-style maps and vary corridor length and agent density directly.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import random
import re
import shutil
import subprocess
import sys
import time
from collections import Counter, defaultdict, deque
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Set, Tuple


REPO_ROOT = Path(__file__).resolve().parents[1]
DEBUG_ROOT = Path(__file__).resolve().parent
SCENARIOS_ROOT = DEBUG_ROOT / "scenarios"
RESULTS_ROOT = DEBUG_ROOT / "results"
DETAILS_ROOT = RESULTS_ROOT / "details"
LOGS_ROOT = RESULTS_ROOT / "logs"
CSV_PATH = RESULTS_ROOT / "debug_results.csv"

FACT_RE = re.compile(r"^\s*([A-Za-z_][A-Za-z0-9_]*)\((.*)\)\.\s*$")
DETAIL_SEPARATOR = "\n"
DEFAULT_SWEEP_AGENT_COUNTS = [2, 10, 20, 25, 30, 35]
DEFAULT_SWEEP_RATIOS = [0.50, 0.60, 0.70, 0.80]
DEFAULT_SWEEP_SEED = 7
TARGET_CAUSE_FLAGS = {
    "long_tunnel_ratio": "long_tunnel_risk",
    "high_agent_density": "high_agent_density_risk",
    "opposite_direction_head_on_traffic": "head_on_traffic_risk",
    "single_lane_bottleneck": "single_lane_bottleneck_risk",
    "high_wait_congestion": "wait_congestion_risk",
    "large_repair_overhead": "repair_overhead_risk",
    "large_abstraction_compression": "abstraction_compression_risk",
    "shared_store_depot_pressure": "shared_store_depot_risk",
    "duplicate_goal_pressure": "duplicate_goal_risk",
    "misleading_abstract_makespan": "misleading_abstract_makespan_risk",
    "missing_path_abstraction": "path_abstraction_missing_risk",
}


@dataclass(frozen=True)
class ScenarioSpec:
    name: str
    grid_width: int
    grid_height: int
    tunnel_length: int
    tunnel_target_ratio: float
    agent_count: int
    corridor_case: str
    agent_case: str
    description: str
    target_failure_cause: str = ""
    target_failure_hypothesis: str = ""
    duplicate_goal_limit: int = 0
    force_shared_store_depot: bool = False
    debug_suite: str = ""
    base_sweep_name: str = ""
    cause_case_name: str = ""
    cause_number: str = ""
    proof_role: str = ""
    expected_outcome: str = ""
    expected_missing_abstraction: bool = False
    graph_mutation: str = ""


SCENARIOS: Dict[str, ScenarioSpec] = {
    "short_low": ScenarioSpec(
        name="short_low",
        grid_width=100,
        grid_height=15,
        tunnel_length=20,
        tunnel_target_ratio=0.20,
        agent_count=2,
        corridor_case="short",
        agent_case="low",
        description="Short tunnel with low traffic; baseline case.",
    ),
    "long_low": ScenarioSpec(
        name="long_low",
        grid_width=100,
        grid_height=15,
        tunnel_length=70,
        tunnel_target_ratio=0.70,
        agent_count=2,
        corridor_case="long",
        agent_case="low",
        description="Long tunnel is 70 percent of grid width with low traffic.",
    ),
    "short_high": ScenarioSpec(
        name="short_high",
        grid_width=100,
        grid_height=15,
        tunnel_length=20,
        tunnel_target_ratio=0.20,
        agent_count=12,
        corridor_case="short",
        agent_case="high",
        description="Short tunnel with high traffic; isolates agent conflict density.",
    ),
    "long_high": ScenarioSpec(
        name="long_high",
        grid_width=100,
        grid_height=15,
        tunnel_length=70,
        tunnel_target_ratio=0.70,
        agent_count=12,
        corridor_case="long",
        agent_case="high",
        description="Long tunnel is 70 percent of grid width with high traffic.",
    ),
}


CAUSE_SCENARIOS: Dict[str, ScenarioSpec] = {
    "cause_01_long_tunnel": ScenarioSpec(
        name="cause_01_long_tunnel",
        grid_width=120,
        grid_height=17,
        tunnel_length=84,
        tunnel_target_ratio=0.70,
        agent_count=2,
        corridor_case="long",
        agent_case="low",
        description="Cause 01: long tunnel with low traffic.",
        target_failure_cause="long_tunnel_ratio",
        target_failure_hypothesis="A long tunnel makes one abstract step hide many concrete cells.",
    ),
    "cause_02_high_agent_density": ScenarioSpec(
        name="cause_02_high_agent_density",
        grid_width=80,
        grid_height=17,
        tunnel_length=40,
        tunnel_target_ratio=0.50,
        agent_count=35,
        corridor_case="short",
        agent_case="very_high",
        description="Cause 02: many agents per tunnel node.",
        target_failure_cause="high_agent_density",
        target_failure_hypothesis="High agents-per-tunnel-node increases conflicts and waiting.",
    ),
    "cause_03_head_on_traffic": ScenarioSpec(
        name="cause_03_head_on_traffic",
        grid_width=100,
        grid_height=17,
        tunnel_length=70,
        tunnel_target_ratio=0.70,
        agent_count=20,
        corridor_case="long",
        agent_case="high",
        description="Cause 03: agents start from both sides and meet head-on.",
        target_failure_cause="opposite_direction_head_on_traffic",
        target_failure_hypothesis="Opposite-direction traffic creates swap and vertex conflicts inside the tunnel.",
    ),
    "cause_04_single_lane_bottleneck": ScenarioSpec(
        name="cause_04_single_lane_bottleneck",
        grid_width=100,
        grid_height=15,
        tunnel_length=60,
        tunnel_target_ratio=0.60,
        agent_count=30,
        corridor_case="medium",
        agent_case="high",
        description="Cause 04: many agents must pass through a one-cell-wide tunnel.",
        target_failure_cause="single_lane_bottleneck",
        target_failure_hypothesis="Tunnel capacity is one robot per time step, but bottleneck load is high.",
    ),
    "cause_05_high_waiting_cost": ScenarioSpec(
        name="cause_05_high_waiting_cost",
        grid_width=90,
        grid_height=17,
        tunnel_length=63,
        tunnel_target_ratio=0.70,
        agent_count=35,
        corridor_case="long",
        agent_case="very_high",
        description="Cause 05: dense bidirectional traffic should create large wait ratio.",
        target_failure_cause="high_wait_congestion",
        target_failure_hypothesis="Many agents in a long single-lane tunnel should increase stay actions and wait ratio.",
    ),
    "cause_06_large_repair_overhead": ScenarioSpec(
        name="cause_06_large_repair_overhead",
        grid_width=140,
        grid_height=17,
        tunnel_length=112,
        tunnel_target_ratio=0.80,
        agent_count=4,
        corridor_case="very_long",
        agent_case="low",
        description="Cause 06: very long tunnel should make repair much longer than abstract movement.",
        target_failure_cause="large_repair_overhead",
        target_failure_hypothesis="The abstract move is short, but the inserted concrete path spans most of the tunnel.",
    ),
    "cause_07_abstraction_compression": ScenarioSpec(
        name="cause_07_abstraction_compression",
        grid_width=160,
        grid_height=25,
        tunnel_length=128,
        tunnel_target_ratio=0.80,
        agent_count=10,
        corridor_case="very_long",
        agent_case="medium",
        description="Cause 07: large map area compressed into fewer abstract nodes.",
        target_failure_cause="large_abstraction_compression",
        target_failure_hypothesis="Large compression ratio means the high-level graph hides much concrete structure.",
    ),
    "cause_08_shared_store_depot": ScenarioSpec(
        name="cause_08_shared_store_depot",
        grid_width=100,
        grid_height=17,
        tunnel_length=60,
        tunnel_target_ratio=0.60,
        agent_count=30,
        corridor_case="medium",
        agent_case="high",
        description="Cause 08: many agents share the same store/depot endpoints.",
        target_failure_cause="shared_store_depot_pressure",
        target_failure_hypothesis="Shared store/depot nodes create repeated local congestion.",
        force_shared_store_depot=True,
    ),
    "cause_09_duplicate_goals": ScenarioSpec(
        name="cause_09_duplicate_goals",
        grid_width=100,
        grid_height=17,
        tunnel_length=60,
        tunnel_target_ratio=0.60,
        agent_count=30,
        corridor_case="medium",
        agent_case="high",
        description="Cause 09: many agents target the same small set of pod goals.",
        target_failure_cause="duplicate_goal_pressure",
        target_failure_hypothesis="Duplicate goals create goal-area contention and repeated repair conflicts.",
        duplicate_goal_limit=4,
    ),
    "cause_10_misleading_abstract_makespan": ScenarioSpec(
        name="cause_10_misleading_abstract_makespan",
        grid_width=150,
        grid_height=19,
        tunnel_length=120,
        tunnel_target_ratio=0.80,
        agent_count=20,
        corridor_case="very_long",
        agent_case="high",
        description="Cause 10: abstract makespan may look small while repaired execution is large.",
        target_failure_cause="misleading_abstract_makespan",
        target_failure_hypothesis="Compare abstract_makespan with repair_makespan and observed_makespan.",
    ),
}


PATH_ABSTRACTION_PROOF_SCENARIOS: Dict[str, ScenarioSpec] = {
    "path_abs_success_control": ScenarioSpec(
        name="path_abs_success_control",
        grid_width=80,
        grid_height=15,
        tunnel_length=40,
        tunnel_target_ratio=0.50,
        agent_count=2,
        corridor_case="short",
        agent_case="low",
        description="Success control: connected tunnel, low traffic, abstract path should exist.",
        target_failure_cause="missing_path_abstraction",
        target_failure_hypothesis="The connected control should produce abstract plan details and repair path details.",
        debug_suite="path_abstraction_proof",
        proof_role="success_control",
        expected_outcome="success",
        expected_missing_abstraction=False,
    ),
    "path_abs_fail_broken_long_low": ScenarioSpec(
        name="path_abs_fail_broken_long_low",
        grid_width=100,
        grid_height=15,
        tunnel_length=70,
        tunnel_target_ratio=0.70,
        agent_count=2,
        corridor_case="long",
        agent_case="low",
        description="Fail case 1: the long tunnel has a middle gap, so no complete abstract path should be usable.",
        target_failure_cause="missing_path_abstraction",
        target_failure_hypothesis="Breaking the middle of the tunnel should remove the start-to-goal path evidence.",
        debug_suite="path_abstraction_proof",
        proof_role="fail_missing_abstraction_low_agents",
        expected_outcome="fail",
        expected_missing_abstraction=True,
        graph_mutation="break_tunnel_middle",
    ),
    "path_abs_fail_broken_long_high": ScenarioSpec(
        name="path_abs_fail_broken_long_high",
        grid_width=100,
        grid_height=15,
        tunnel_length=70,
        tunnel_target_ratio=0.70,
        agent_count=20,
        corridor_case="long",
        agent_case="high",
        description="Fail case 2: the same missing tunnel bridge with many agents.",
        target_failure_cause="missing_path_abstraction",
        target_failure_hypothesis="With many agents and a broken tunnel, the abstract path evidence should still be missing.",
        debug_suite="path_abstraction_proof",
        proof_role="fail_missing_abstraction_high_agents",
        expected_outcome="fail",
        expected_missing_abstraction=True,
        graph_mutation="break_tunnel_middle",
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


def scenario_dir(spec: ScenarioSpec) -> Path:
    return SCENARIOS_ROOT / spec.name


def corridor_case_for_ratio(ratio: float) -> str:
    if ratio >= 0.80:
        return "very_long"
    if ratio >= 0.70:
        return "long"
    if ratio >= 0.60:
        return "medium"
    return "short"


def agent_case_for_count(agent_count: int) -> str:
    if agent_count <= 0:
        return "zero"
    if agent_count <= 2:
        return "low"
    if agent_count < 20:
        return "medium"
    if agent_count < 35:
        return "high"
    return "very_high"


def normalize_ratio(value: float) -> float:
    ratio = float(value)
    if ratio > 1:
        ratio = ratio / 100.0
    if ratio <= 0 or ratio >= 1:
        raise SystemExit(f"Tunnel ratio must be between 0 and 1, got {value}.")
    return ratio


def odd_between(rng: random.Random, minimum: int, maximum: int) -> int:
    choices = [value for value in range(minimum, maximum + 1) if value % 2 == 1]
    if not choices:
        raise SystemExit("Grid height range must contain at least one odd value.")
    return rng.choice(choices)


def random_width(rng: random.Random, minimum: int, maximum: int) -> int:
    low = ((minimum + 9) // 10) * 10
    high = (maximum // 10) * 10
    if low > high:
        raise SystemExit("Grid width range must contain at least one multiple of 10.")
    return rng.choice(list(range(low, high + 1, 10)))


def build_sweep_specs(
    agent_counts: Sequence[int],
    ratios: Sequence[float],
    samples: int,
    min_width: int,
    max_width: int,
    min_height: int,
    max_height: int,
    seed: int,
) -> Dict[str, ScenarioSpec]:
    rng = random.Random(seed)
    specs: Dict[str, ScenarioSpec] = {}
    normalized_ratios = [normalize_ratio(ratio) for ratio in ratios]

    for ratio in normalized_ratios:
        ratio_percent = int(round(ratio * 100))
        for agent_count in agent_counts:
            if agent_count < 0:
                raise SystemExit("Agent counts cannot be negative.")
            for sample in range(1, samples + 1):
                width = random_width(rng, min_width, max_width)
                height = odd_between(rng, min_height, max_height)
                tunnel_length = int(round(width * ratio))
                name = f"sweep_r{ratio_percent:02d}_w{width}_h{height}_a{agent_count:02d}_s{sample:02d}"
                specs[name] = ScenarioSpec(
                    name=name,
                    grid_width=width,
                    grid_height=height,
                    tunnel_length=tunnel_length,
                    tunnel_target_ratio=ratio,
                    agent_count=agent_count,
                    corridor_case=corridor_case_for_ratio(ratio),
                    agent_case=agent_case_for_count(agent_count),
                    description=(
                        f"Random-width tunnel sweep: tunnel is {ratio_percent}% "
                        f"of grid width {width}, with {agent_count} agents."
                    ),
                )

    return specs


def cause_number_from_name(cause_name: str) -> str:
    match = re.search(r"cause_(\d+)", cause_name)
    return match.group(1) if match else cause_name


def build_cause_sweep_specs(
    base_specs: Dict[str, ScenarioSpec],
    cause_names: Sequence[str],
) -> Dict[str, ScenarioSpec]:
    specs: Dict[str, ScenarioSpec] = {}
    for cause_name in cause_names:
        cause_spec = CAUSE_SCENARIOS[cause_name]
        cause_number = cause_number_from_name(cause_name)
        for base_spec in base_specs.values():
            base_slug = base_spec.name.replace("sweep_", "")
            name = f"matrix_c{cause_number}_{base_slug}"
            ratio_percent = int(round(base_spec.tunnel_target_ratio * 100))
            specs[name] = ScenarioSpec(
                name=name,
                grid_width=base_spec.grid_width,
                grid_height=base_spec.grid_height,
                tunnel_length=base_spec.tunnel_length,
                tunnel_target_ratio=base_spec.tunnel_target_ratio,
                agent_count=base_spec.agent_count,
                corridor_case=base_spec.corridor_case,
                agent_case=base_spec.agent_case,
                description=(
                    f"Cause matrix {cause_number}: {cause_spec.target_failure_cause} "
                    f"tested on tunnel ratio {ratio_percent}% with {base_spec.agent_count} agents."
                ),
                target_failure_cause=cause_spec.target_failure_cause,
                target_failure_hypothesis=cause_spec.target_failure_hypothesis,
                duplicate_goal_limit=cause_spec.duplicate_goal_limit,
                force_shared_store_depot=cause_spec.force_shared_store_depot,
                debug_suite="cause_sweep_matrix",
                base_sweep_name=base_spec.name,
                cause_case_name=cause_name,
                cause_number=cause_number,
            )
    return specs


def infer_grid_columns(vertices: Set[int], edges: Set[Tuple[int, int]]) -> int:
    differences = Counter(abs(dst - src) for src, dst in edges if abs(dst - src) > 1)
    if differences:
        return differences.most_common(1)[0][0]
    if vertices:
        return max(vertices) + 1
    return 1


def node_column(node: int, columns: int) -> int:
    return node % columns if columns else node


def node_row(node: int, columns: int) -> int:
    return node // columns if columns else 0


def side_sorted(nodes: Iterable[int], columns: int, side: str) -> List[int]:
    if side == "left":
        return sorted(nodes, key=lambda node: (node_column(node, columns), node_row(node, columns), node))
    if side == "right":
        return sorted(nodes, key=lambda node: (-node_column(node, columns), node_row(node, columns), node))
    raise ValueError(f"Unknown side: {side}")


def choose_unique(candidates: Sequence[int], count: int, used: Set[int]) -> List[int]:
    chosen = []
    for node in candidates:
        if node in used:
            continue
        chosen.append(node)
        used.add(node)
        if len(chosen) == count:
            break
    if len(chosen) < count:
        raise SystemExit(f"Only found {len(chosen)} unique nodes, but needed {count}.")
    return chosen


def cell_id(row: int, column: int, width: int) -> int:
    return row * width + column


def add_edge(edges: Set[Tuple[int, int]], left: int, right: int) -> None:
    edges.add((left, right))
    edges.add((right, left))


def tunnel_bounds(spec: ScenarioSpec) -> Tuple[int, int, int]:
    tunnel_length = int(round(spec.grid_width * spec.tunnel_target_ratio))
    tunnel_length = min(spec.grid_width - 2, max(3, tunnel_length))
    start_col = (spec.grid_width - tunnel_length) // 2
    end_col = start_col + tunnel_length - 1
    return start_col, end_col, tunnel_length


def tunnel_cells(spec: ScenarioSpec) -> Tuple[Set[Tuple[int, int]], Set[Tuple[int, int]]]:
    width = spec.grid_width
    height = spec.grid_height
    tunnel_row = height // 2
    start_col, end_col, _tunnel_length = tunnel_bounds(spec)
    chamber_half_height = 2

    aisle_cells: Set[Tuple[int, int]] = set()
    pod_cells: Set[Tuple[int, int]] = set()

    for column in range(start_col, end_col + 1):
        aisle_cells.add((tunnel_row, column))
        if tunnel_row - 1 >= 0:
            pod_cells.add((tunnel_row - 1, column))
        if tunnel_row + 1 < height:
            pod_cells.add((tunnel_row + 1, column))

    chamber_rows = range(
        max(0, tunnel_row - chamber_half_height),
        min(height, tunnel_row + chamber_half_height + 1),
    )
    for row in chamber_rows:
        left_stop = start_col + 1 if row == tunnel_row else start_col
        right_start = end_col if row == tunnel_row else end_col + 1
        for column in range(0, left_stop):
            aisle_cells.add((row, column))
        for column in range(right_start, width):
            aisle_cells.add((row, column))

    pod_cells.difference_update(aisle_cells)
    if spec.graph_mutation == "break_tunnel_middle":
        gap_col = (start_col + end_col) // 2
        for row in (tunnel_row - 1, tunnel_row, tunnel_row + 1):
            aisle_cells.discard((row, gap_col))
            pod_cells.discard((row, gap_col))
    return aisle_cells, pod_cells


def build_tunnel_graph(spec: ScenarioSpec) -> Tuple[Set[int], Set[Tuple[int, int]], Set[int], Dict[str, int]]:
    width = spec.grid_width
    tunnel_row = spec.grid_height // 2
    start_col, end_col, tunnel_length = tunnel_bounds(spec)
    aisle_cells, pod_cells = tunnel_cells(spec)

    vertices = {cell_id(row, col, width) for row, col in aisle_cells | pod_cells}
    pods = {cell_id(row, col, width) for row, col in pod_cells}
    edges: Set[Tuple[int, int]] = set()

    for row, col in aisle_cells:
        current = cell_id(row, col, width)
        for drow, dcol in ((0, 1), (1, 0)):
            neighbor = (row + drow, col + dcol)
            if neighbor in aisle_cells:
                add_edge(edges, current, cell_id(neighbor[0], neighbor[1], width))

    for row, col in pod_cells:
        if row == tunnel_row - 1:
            aisle = (tunnel_row, col)
        elif row == tunnel_row + 1:
            aisle = (tunnel_row, col)
        else:
            continue
        if aisle in aisle_cells:
            add_edge(edges, cell_id(row, col, width), cell_id(aisle[0], aisle[1], width))

    metadata = {
        "grid_width": width,
        "grid_height": spec.grid_height,
        "tunnel_row": tunnel_row,
        "tunnel_start_col": start_col,
        "tunnel_end_col": end_col,
        "tunnel_length": tunnel_length,
        "tunnel_width_ratio": round(tunnel_length / float(width), 6),
        "left_station": cell_id(tunnel_row, max(0, start_col - 1), width),
        "right_station": cell_id(tunnel_row, min(width - 1, end_col + 1), width),
        "graph_mutation": spec.graph_mutation,
        "tunnel_gap_col": (start_col + end_col) // 2 if spec.graph_mutation == "break_tunnel_middle" else "",
    }
    return vertices, edges, pods, metadata


def make_map_lines(vertices: Set[int], edges: Set[Tuple[int, int]], pods: Set[int]) -> List[str]:
    outgoing = defaultdict(list)
    for src, dst in sorted(edges):
        outgoing[src].append(dst)

    lines: List[str] = []
    for vertex in sorted(vertices):
        lines.append(f"vertice({vertex}).")
        if vertex in pods:
            lines.append(f"pods({vertex}).")
        for dst in outgoing.get(vertex, []):
            lines.append(f"edge({vertex},{dst}).")
    return lines


def candidate_cells_for_side(spec: ScenarioSpec, side: str) -> List[Tuple[int, int]]:
    tunnel_row = spec.grid_height // 2
    start_col, end_col, _tunnel_length = tunnel_bounds(spec)
    rows = list(range(max(0, tunnel_row - 2), min(spec.grid_height, tunnel_row + 3)))

    if side == "left":
        columns = list(range(max(0, start_col - 1), -1, -1))
    elif side == "right":
        columns = list(range(min(spec.grid_width - 1, end_col + 1), spec.grid_width))
    else:
        raise ValueError(f"Unknown side: {side}")

    return [(row, col) for col in columns for row in rows]


def goal_pods_for_side(spec: ScenarioSpec, side: str) -> List[int]:
    width = spec.grid_width
    tunnel_row = spec.grid_height // 2
    start_col, end_col, _tunnel_length = tunnel_bounds(spec)
    pod_rows = [tunnel_row - 1, tunnel_row + 1]
    goals: List[int] = []

    if side == "left_to_right":
        columns = list(range(end_col, start_col - 1, -1))
    elif side == "right_to_left":
        columns = list(range(start_col, end_col + 1))
    else:
        raise ValueError(f"Unknown side: {side}")

    for column in columns:
        for row in pod_rows:
            if 0 <= row < spec.grid_height:
                goals.append(cell_id(row, column, width))
    return goals


def make_agents_lines(spec: ScenarioSpec, pods: Set[int], metadata: Dict[str, int]) -> List[str]:
    if spec.agent_count <= 0:
        return []

    width = spec.grid_width
    left_count = (spec.agent_count + 1) // 2
    right_count = spec.agent_count - left_count
    used_starts: Set[int] = set()

    left_candidates = [cell_id(row, col, width) for row, col in candidate_cells_for_side(spec, "left")]
    right_candidates = [cell_id(row, col, width) for row, col in candidate_cells_for_side(spec, "right")]
    left_starts = choose_unique(left_candidates, left_count, used_starts)
    right_starts = choose_unique(right_candidates, right_count, used_starts)

    left_goals = [goal for goal in goal_pods_for_side(spec, "right_to_left") if goal in pods]
    right_goals = [goal for goal in goal_pods_for_side(spec, "left_to_right") if goal in pods]
    if not left_goals or not right_goals:
        raise SystemExit("The tunnel generator did not create enough pod goals.")
    if spec.duplicate_goal_limit > 0:
        left_goals = left_goals[:spec.duplicate_goal_limit]
        right_goals = right_goals[:spec.duplicate_goal_limit]

    left_station = metadata["left_station"]
    right_station = metadata["right_station"]
    shared_station = left_station

    lines: List[str] = []
    starts = left_starts + right_starts
    sides = ["left"] * left_count + ["right"] * right_count
    for robot_id, start in enumerate(starts, start=1):
        lines.append(f"agent({robot_id},{start},a).")

    lines.append("group(1,0).")

    left_goal_index = 0
    right_goal_index = 0
    for robot_id, side in enumerate(sides, start=1):
        if side == "left":
            goal = right_goals[right_goal_index % len(right_goals)]
            right_goal_index += 1
            store = shared_station if spec.force_shared_store_depot else left_station
            depot = shared_station if spec.force_shared_store_depot else right_station
        else:
            goal = left_goals[left_goal_index % len(left_goals)]
            left_goal_index += 1
            store = shared_station if spec.force_shared_store_depot else right_station
            depot = shared_station if spec.force_shared_store_depot else left_station

        lines.append(f"task({robot_id},1,{goal},a).")
        lines.append(f"store({robot_id},{store}).")
        lines.append(f"depot({robot_id},{depot}).")

    return lines


def make_ins_lines(spec: ScenarioSpec) -> List[str]:
    aisle_cells, pod_cells = tunnel_cells(spec)
    lines = []
    for row in range(spec.grid_height):
        chars = []
        for col in range(spec.grid_width):
            if (row, col) in pod_cells:
                chars.append("|")
            elif (row, col) in aisle_cells:
                chars.append(".")
            else:
                chars.append("#")
        lines.append("".join(chars))
    return lines


def write_metadata(
    spec: ScenarioSpec,
    vertices: Set[int],
    edges: Set[Tuple[int, int]],
    pods: Set[int],
    tunnel_metadata: Dict[str, int],
) -> None:
    metadata = asdict(spec)
    metadata.update(
        {
            "map_vertices": len(vertices),
            "map_edges": len(edges),
            "pods": len(pods),
            "agent_density": round(spec.agent_count / float(tunnel_metadata["tunnel_length"]), 6),
            "target_failure_cause": spec.target_failure_cause,
            "target_failure_hypothesis": spec.target_failure_hypothesis,
            "duplicate_goal_limit": spec.duplicate_goal_limit,
            "force_shared_store_depot": int(spec.force_shared_store_depot),
            "hypothesis": (
                "Longer corridors should increase abstraction repair length; "
                "more agents per corridor node should increase waits and conflict handling."
            ),
        }
    )
    metadata.update(tunnel_metadata)
    path = scenario_dir(spec) / "metadata.json"
    path.write_text(json.dumps(metadata, indent=2, sort_keys=True), encoding="utf-8")


def generate_scenario(spec: ScenarioSpec) -> None:
    path = scenario_dir(spec)
    vertices, edges, pods, tunnel_metadata = build_tunnel_graph(spec)

    path.mkdir(parents=True, exist_ok=True)
    generated_dir = path / "generated"
    if generated_dir.exists():
        shutil.rmtree(generated_dir)
    write_lines(path / f"{spec.name}.map", make_map_lines(vertices, edges, pods))
    write_lines(path / f"{spec.name}.ins", make_ins_lines(spec))
    write_lines(path / f"{spec.name}.agents", make_agents_lines(spec, pods, tunnel_metadata))
    write_metadata(spec, vertices, edges, pods, tunnel_metadata)


def generate_scenarios(case_names: Sequence[str]) -> None:
    for name in case_names:
        generate_scenario(SCENARIOS[name])
        print(f"Generated {SCENARIOS[name].name} in {scenario_dir(SCENARIOS[name])}")


def generate_specs(specs: Dict[str, ScenarioSpec]) -> None:
    for spec in specs.values():
        generate_scenario(spec)
        print(f"Generated {spec.name} in {scenario_dir(spec)}")


def run_status_path(case_name: str) -> Path:
    return SCENARIOS_ROOT / case_name / "run_status.json"


def write_run_status(case_names: Sequence[str], status: str, returncode: int, log_path: Path, message: str = "") -> None:
    payload = {
        "status": status,
        "returncode": returncode,
        "log_path": str(log_path),
        "message": message,
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
    }
    for case_name in case_names:
        path = run_status_path(case_name)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def run_solver(case_names: Sequence[str], timeout_seconds: int = 0) -> Path:
    SCENARIOS_ROOT.mkdir(parents=True, exist_ok=True)
    LOGS_ROOT.mkdir(parents=True, exist_ok=True)

    env = os.environ.copy()
    env["PROBS"] = " ".join(case_names)
    env["PDIR"] = "../../../../"

    timestamp = time.strftime("%Y%m%d_%H%M%S")
    slug = "_".join(case_names)
    if len(slug) > 80:
        slug = f"{len(case_names)}_cases"
    log_path = LOGS_ROOT / f"debug_run_{timestamp}_{slug}.log"
    command = ["bash", "../../test_asp"]

    print(f"Running: PROBS=\"{env['PROBS']}\" PDIR=\"{env['PDIR']}\" bash ../../test_asp")
    print(f"Log: {log_path}")

    with log_path.open("w", encoding="utf-8", errors="replace") as log_file:
        try:
            completed = subprocess.run(
                command,
                cwd=str(SCENARIOS_ROOT),
                env=env,
                text=True,
                stdout=log_file,
                stderr=subprocess.STDOUT,
                timeout=timeout_seconds if timeout_seconds > 0 else None,
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            log_file.write(f"\nTimed out after {timeout_seconds} seconds.\n")
            write_run_status(case_names, "timed_out", -1, log_path, f"Timed out after {timeout_seconds} seconds.")
            raise SystemExit(f"test_asp timed out after {timeout_seconds} seconds. See {log_path}") from exc

    if completed.returncode != 0:
        write_run_status(case_names, "failed", completed.returncode, log_path)
        raise SystemExit(f"test_asp failed with exit code {completed.returncode}. See {log_path}")

    write_run_status(case_names, "completed", completed.returncode, log_path)
    return log_path


def run_cases_individually(case_names: Sequence[str], timeout_seconds: int = 0, keep_going: bool = False) -> None:
    for case_name in case_names:
        try:
            run_solver([case_name], timeout_seconds=timeout_seconds)
        except SystemExit as exc:
            if not keep_going:
                raise
            print(exc)


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


def to_float(value) -> Optional[float]:
    if value == "" or value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def ratio_or_blank(numerator, denominator):
    numerator_value = to_float(numerator)
    denominator_value = to_float(denominator)
    if numerator_value is None or denominator_value in (None, 0):
        return ""
    return round(numerator_value / denominator_value, 6)


def is_reachable(graph: Dict[int, Set[int]], start: int, goal: int) -> bool:
    if start not in graph or goal not in graph:
        return False
    seen = {start}
    queue = deque([start])
    while queue:
        node = queue.popleft()
        if node == goal:
            return True
        for neighbor in graph.get(node, set()):
            if neighbor not in seen:
                seen.add(neighbor)
                queue.append(neighbor)
    return False


def parse_agent_task_metrics(
    agents_file: Path,
    metadata: Dict[str, object],
    graph: Optional[Dict[int, Set[int]]] = None,
) -> Dict[str, object]:
    agents: Dict[object, object] = {}
    tasks = []
    stores = {}
    depots = {}

    for pred, args in iter_facts(agents_file):
        if pred == "agent" and len(args) >= 2:
            agents[args[0]] = args[1]
        elif pred == "task" and len(args) >= 3:
            tasks.append((args[0], args[2]))
        elif pred == "store" and len(args) >= 2:
            stores[args[0]] = args[1]
        elif pred == "depot" and len(args) >= 2:
            depots[args[0]] = args[1]

    width = int(metadata.get("grid_width", 0) or 0)
    tunnel_start = int(metadata.get("tunnel_start_col", -1) or -1)
    tunnel_end = int(metadata.get("tunnel_end_col", -1) or -1)

    left_agents = 0
    right_agents = 0
    inside_tunnel_agents = 0
    unknown_side_agents = 0
    if width > 0 and tunnel_start >= 0 and tunnel_end >= 0:
        for start in agents.values():
            if not isinstance(start, int):
                unknown_side_agents += 1
                continue
            column = start % width
            if column < tunnel_start:
                left_agents += 1
            elif column > tunnel_end:
                right_agents += 1
            else:
                inside_tunnel_agents += 1
    else:
        unknown_side_agents = len(agents)

    goal_counts = Counter(goal for _task_id, goal in tasks)
    start_counts = Counter(agents.values())
    store_counts = Counter(stores.values())
    depot_counts = Counter(depots.values())
    unreachable_details = []
    reachable_pairs = 0
    unreachable_pairs = 0
    if graph is not None:
        for task_id, goal in tasks:
            start = agents.get(task_id)
            if isinstance(start, int) and isinstance(goal, int) and is_reachable(graph, start, goal):
                reachable_pairs += 1
            else:
                unreachable_pairs += 1
                unreachable_details.append(f"robot {task_id}: start {start} cannot reach goal {goal}")

    return {
        "left_agent_count": left_agents,
        "right_agent_count": right_agents,
        "inside_tunnel_agent_count": inside_tunnel_agents,
        "unknown_side_agent_count": unknown_side_agents,
        "opposing_agent_pair_count": left_agents * right_agents,
        "same_side_pair_count": (left_agents * max(0, left_agents - 1) // 2)
        + (right_agents * max(0, right_agents - 1) // 2),
        "unique_start_count": len(start_counts),
        "duplicate_start_count": sum(max(0, count - 1) for count in start_counts.values()),
        "unique_goal_count": len(goal_counts),
        "duplicate_goal_count": sum(max(0, count - 1) for count in goal_counts.values()),
        "max_agents_per_goal": max(goal_counts.values()) if goal_counts else 0,
        "unique_store_count": len(store_counts),
        "unique_depot_count": len(depot_counts),
        "max_agents_per_store": max(store_counts.values()) if store_counts else 0,
        "max_agents_per_depot": max(depot_counts.values()) if depot_counts else 0,
        "start_goal_pair_count": len(tasks),
        "start_goal_reachable_count": reachable_pairs,
        "start_goal_unreachable_count": unreachable_pairs,
        "start_goal_unreachable_details": DETAIL_SEPARATOR.join(unreachable_details),
    }


def build_failure_evidence(row: Dict[str, object]) -> Dict[str, object]:
    total_agents = int(to_float(row.get("total_agents")) or 0)
    tunnel_length = int(to_float(row.get("configured_tunnel_length")) or 0)
    tunnel_ratio = to_float(row.get("tunnel_width_ratio")) or 0.0
    agent_density = to_float(row.get("agent_density")) or 0.0
    opposing_pairs = int(to_float(row.get("opposing_agent_pair_count")) or 0)
    left_agents = int(to_float(row.get("left_agent_count")) or 0)
    right_agents = int(to_float(row.get("right_agent_count")) or 0)
    result_files = int(to_float(row.get("result_files")) or 0)
    total_waits = int(to_float(row.get("total_waits")) or 0)
    move_count = int(to_float(row.get("move_count")) or 0)
    stay_count = int(to_float(row.get("stay_count")) or 0)
    at_count = int(to_float(row.get("at_count")) or 0)
    path_count = int(to_float(row.get("path_count")) or 0)
    repair_segments = int(to_float(row.get("repair_segments")) or 0)
    abstract_vertices = int(to_float(row.get("abstract_vertices")) or 0)
    start_goal_unreachable = int(to_float(row.get("start_goal_unreachable_count")) or 0)
    longest_repair_steps = to_float(row.get("longest_repair_steps"))
    abstract_makespan = to_float(row.get("abstract_makespan"))
    repair_makespan = to_float(row.get("repair_makespan"))
    observed_makespan = to_float(row.get("observed_makespan"))
    sum_of_costs = to_float(row.get("sum_of_costs"))
    repair_cost = to_float(row.get("repair_cost"))
    compression_ratio = to_float(row.get("compression_ratio"))
    solver_status = str(row.get("solver_status", ""))
    runtime_seconds = str(row.get("runtime_seconds", ""))
    solver_was_run = bool(solver_status or runtime_seconds)

    action_count = move_count + stay_count
    wait_ratio = ratio_or_blank(total_waits, action_count)
    repair_makespan_gap = ""
    if repair_makespan is not None and abstract_makespan is not None:
        repair_makespan_gap = int(repair_makespan - abstract_makespan)

    evidence = {
        "tunnel_lane_count": 1,
        "tunnel_entry_count": 2,
        "tunnel_bottleneck_capacity": 1,
        "agents_per_tunnel_node": round(agent_density, 6),
        "agents_per_tunnel_percent": round(agent_density * 100, 2),
        "opposing_pair_pressure": ratio_or_blank(opposing_pairs, tunnel_length),
        "bottleneck_load": total_agents,
        "bottleneck_load_per_lane": total_agents,
        "wait_ratio": wait_ratio,
        "waits_per_agent": ratio_or_blank(total_waits, total_agents),
        "moves_per_agent": ratio_or_blank(move_count, total_agents),
        "repair_segments_per_agent": ratio_or_blank(repair_segments, total_agents),
        "repair_cost_per_agent": ratio_or_blank(repair_cost, total_agents),
        "cost_per_agent": ratio_or_blank(sum_of_costs, total_agents),
        "repair_cost_ratio": ratio_or_blank(repair_cost, sum_of_costs),
        "repair_makespan_gap": repair_makespan_gap,
        "repair_overhead_ratio": ratio_or_blank(repair_makespan, abstract_makespan),
        "longest_repair_to_tunnel_ratio": ratio_or_blank(longest_repair_steps, tunnel_length),
        "observed_makespan_per_agent": ratio_or_blank(observed_makespan, total_agents),
        "abstract_compression_risk_value": compression_ratio if compression_ratio is not None else "",
        "abstract_plan_present": int(at_count > 0 and result_files > 0),
        "repair_path_present": int(path_count > 0 and result_files > 0),
    }

    flags = {
        "long_tunnel_risk": tunnel_ratio >= 0.70,
        "very_long_tunnel_risk": tunnel_ratio >= 0.80,
        "high_agent_density_risk": agent_density >= 0.25,
        "very_high_agent_density_risk": agent_density >= 0.40,
        "head_on_traffic_risk": left_agents > 0 and right_agents > 0 and opposing_pairs > 0,
        "high_head_on_pressure_risk": (to_float(evidence["opposing_pair_pressure"]) or 0) >= 1.0,
        "single_lane_bottleneck_risk": total_agents > 2,
        "duplicate_goal_risk": int(to_float(row.get("duplicate_goal_count")) or 0) > 0,
        "shared_store_depot_risk": int(to_float(row.get("max_agents_per_store")) or 0) > 1
        or int(to_float(row.get("max_agents_per_depot")) or 0) > 1,
        "abstraction_compression_risk": compression_ratio is not None and compression_ratio >= 2.0,
        "repair_overhead_risk": (to_float(evidence["repair_overhead_ratio"]) or 0) >= 2.0
        or (to_float(evidence["longest_repair_to_tunnel_ratio"]) or 0) >= 0.50,
        "misleading_abstract_makespan_risk": repair_makespan is not None
        and abstract_makespan is not None
        and repair_makespan > abstract_makespan,
        "abstract_graph_missing_risk": solver_was_run and abstract_vertices == 0,
        "missing_abstract_plan_risk": solver_was_run and (result_files == 0 or at_count == 0),
        "missing_repair_path_risk": solver_was_run and (result_files == 0 or path_count == 0),
        "concrete_start_goal_unreachable_risk": start_goal_unreachable > 0,
        "wait_congestion_risk": (to_float(wait_ratio) or 0) >= 0.30,
        "timeout_or_failed_risk": solver_status in {"timed_out", "failed"},
        "missing_result_risk": solver_was_run and result_files == 0,
    }
    flags["path_abstraction_missing_risk"] = (
        flags["abstract_graph_missing_risk"]
        or flags["missing_abstract_plan_risk"]
        or flags["concrete_start_goal_unreachable_risk"]
    )

    causes = []
    if flags["long_tunnel_risk"]:
        causes.append("long_tunnel_ratio")
    if flags["very_long_tunnel_risk"]:
        causes.append("very_long_tunnel_ratio")
    if flags["high_agent_density_risk"]:
        causes.append("high_agent_density")
    if flags["head_on_traffic_risk"]:
        causes.append("opposite_direction_head_on_traffic")
    if flags["high_head_on_pressure_risk"]:
        causes.append("high_head_on_pair_pressure")
    if flags["single_lane_bottleneck_risk"]:
        causes.append("single_lane_bottleneck")
    if flags["duplicate_goal_risk"]:
        causes.append("duplicate_goal_pressure")
    if flags["shared_store_depot_risk"]:
        causes.append("shared_store_depot_pressure")
    if flags["abstraction_compression_risk"]:
        causes.append("large_abstraction_compression")
    if flags["repair_overhead_risk"]:
        causes.append("large_repair_overhead")
    if flags["misleading_abstract_makespan_risk"]:
        causes.append("misleading_abstract_makespan")
    if flags["path_abstraction_missing_risk"]:
        causes.append("missing_path_abstraction")
    if flags["wait_congestion_risk"]:
        causes.append("high_wait_congestion")
    if flags["timeout_or_failed_risk"]:
        causes.append("solver_timeout_or_failure")
    if flags["missing_result_risk"]:
        causes.append("missing_result_files")

    evidence.update({name: int(value) for name, value in flags.items()})
    target_cause = str(row.get("target_failure_cause", ""))
    target_flag = TARGET_CAUSE_FLAGS.get(target_cause, "")
    evidence["target_failure_flag"] = target_flag
    evidence["target_failure_triggered"] = int(bool(target_flag and flags.get(target_flag)))
    evidence["failure_risk_score"] = sum(1 for value in flags.values() if value)
    evidence["likely_failure_causes"] = ";".join(causes)
    evidence["failure_evidence_summary"] = (
        f"ratio={round(tunnel_ratio, 3)};agents={total_agents};density={round(agent_density, 3)};"
        f"opposing_pairs={opposing_pairs};wait_ratio={wait_ratio};"
        f"repair_overhead={evidence['repair_overhead_ratio']};status={solver_status or 'not_run'}"
    )
    return evidence


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


def format_visited_records(records: List[Tuple[str, object, object, object, int]]) -> str:
    by_result_robot = defaultdict(list)
    for result_name, robot, real_goal, abstract_goal, time_value in records:
        by_result_robot[(result_name, robot)].append((time_value, real_goal, abstract_goal))

    details = []
    for (result_name, robot), visits in sorted(
        by_result_robot.items(),
        key=lambda item: (item[0][0], sort_key(item[0][1])),
    ):
        pieces = [
            f"time {time_value} visited real {real_goal} abstract {abstract_goal}"
            for time_value, real_goal, abstract_goal in sorted(visits)
        ]
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
    visited_records = []

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
                robot, real_goal, abstract_goal, time_value = args
                visited_count += 1
                per_agent_visited[robot] += 1
                visited_records.append((result_file.name, robot, real_goal, abstract_goal, int(time_value)))

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
        "abstract_plan_robot_count": len(abstract_plan_details),
        "abstract_transition_count": len(abstract_transition_details),
        "repair_path_detail_count": len(repair_path_details),
        "abstract_plan_details": DETAIL_SEPARATOR.join(abstract_plan_details),
        "abstract_transitions": DETAIL_SEPARATOR.join(abstract_transition_details),
        "repair_path_details": DETAIL_SEPARATOR.join(repair_path_details),
        "repair_path_details_readable": DETAIL_SEPARATOR.join(repair_path_details_readable),
        "move_details": format_action_records(move_records, "move_to"),
        "stay_details": format_action_records(stay_records, "stay_at"),
        "visited_details": format_visited_records(visited_records),
        "per_agent_costs": per_agent_costs,
    }


def collect_scenario(spec: ScenarioSpec) -> Dict[str, object]:
    path = scenario_dir(spec)
    map_file = path / f"{spec.name}.map"
    agents_file = path / f"{spec.name}.agents"
    metadata_file = path / "metadata.json"
    generated_dir = path / "generated"
    abstract_map = generated_dir / "__tmp.map"
    time_file = generated_dir / f"time_{spec.name}.txt"
    metadata = {}
    if metadata_file.exists():
        metadata = json.loads(metadata_file.read_text(encoding="utf-8"))
    run_status = {}
    status_file = run_status_path(spec.name)
    if status_file.exists():
        run_status = json.loads(status_file.read_text(encoding="utf-8"))

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
    agent_task_metrics = parse_agent_task_metrics(agents_file, metadata, graph)
    row: Dict[str, object] = {
        "scenario_name": spec.name,
        "scenario_path": str(path.relative_to(REPO_ROOT)),
        "corridor_case": spec.corridor_case,
        "agent_case": spec.agent_case,
        "description": spec.description,
        "debug_suite": metadata.get("debug_suite", spec.debug_suite),
        "base_sweep_name": metadata.get("base_sweep_name", spec.base_sweep_name),
        "cause_case_name": metadata.get("cause_case_name", spec.cause_case_name),
        "cause_number": metadata.get("cause_number", spec.cause_number),
        "proof_role": metadata.get("proof_role", spec.proof_role),
        "expected_outcome": metadata.get("expected_outcome", spec.expected_outcome),
        "expected_missing_abstraction": metadata.get(
            "expected_missing_abstraction",
            int(spec.expected_missing_abstraction),
        ),
        "target_failure_cause": metadata.get("target_failure_cause", spec.target_failure_cause),
        "target_failure_hypothesis": metadata.get("target_failure_hypothesis", spec.target_failure_hypothesis),
        "duplicate_goal_limit": metadata.get("duplicate_goal_limit", spec.duplicate_goal_limit),
        "force_shared_store_depot": metadata.get("force_shared_store_depot", int(spec.force_shared_store_depot)),
        "graph_mutation": metadata.get("graph_mutation", spec.graph_mutation),
        "tunnel_gap_col": metadata.get("tunnel_gap_col", ""),
        "grid_width": metadata.get("grid_width", spec.grid_width),
        "grid_height": metadata.get("grid_height", spec.grid_height),
        "tunnel_target_ratio": metadata.get("tunnel_target_ratio", spec.tunnel_target_ratio),
        "tunnel_width_ratio": metadata.get("tunnel_width_ratio", ""),
        "tunnel_width_percent": round(float(metadata.get("tunnel_width_ratio", 0)) * 100, 2)
        if metadata.get("tunnel_width_ratio", "") != "" else "",
        "configured_corridor_length": metadata.get("tunnel_length", spec.tunnel_length),
        "configured_tunnel_length": metadata.get("tunnel_length", spec.tunnel_length),
        "tunnel_start_col": metadata.get("tunnel_start_col", ""),
        "tunnel_end_col": metadata.get("tunnel_end_col", ""),
        "tunnel_row": metadata.get("tunnel_row", ""),
        "left_station": metadata.get("left_station", ""),
        "right_station": metadata.get("right_station", ""),
        "total_agents": spec.agent_count,
        "agent_density": round(spec.agent_count / float(metadata.get("tunnel_length", spec.tunnel_length)), 6),
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
        "solver_status": run_status.get("status", ""),
        "solver_returncode": run_status.get("returncode", ""),
        "solver_log_path": run_status.get("log_path", ""),
        "solver_message": run_status.get("message", ""),
        "generated_dir": str(generated_dir),
    }
    row.update(agent_task_metrics)
    row.update(result_metrics)
    row.update(build_failure_evidence(row))
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
    collect_specs({name: SCENARIOS[name] for name in case_names})


def collect_cause_scenarios(case_names: Sequence[str]) -> None:
    collect_specs({name: CAUSE_SCENARIOS[name] for name in case_names})


def collect_path_abs_scenarios(case_names: Sequence[str]) -> None:
    collect_specs({name: PATH_ABSTRACTION_PROOF_SCENARIOS[name] for name in case_names})


def collect_specs(specs: Dict[str, ScenarioSpec]) -> None:
    DETAILS_ROOT.mkdir(parents=True, exist_ok=True)
    rows = []
    for name, spec in specs.items():
        row = collect_scenario(spec)
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


def selected_cause_cases(values: Sequence[str]) -> List[str]:
    if not values:
        return list(CAUSE_SCENARIOS)
    names: List[str] = []
    for value in values:
        if value == "all":
            names.extend(CAUSE_SCENARIOS)
        elif value in CAUSE_SCENARIOS:
            names.append(value)
        else:
            valid = ", ".join(CAUSE_SCENARIOS)
            raise SystemExit(f"Unknown cause scenario {value!r}. Valid cases: {valid}")
    deduped = []
    seen = set()
    for name in names:
        if name not in seen:
            deduped.append(name)
            seen.add(name)
    return deduped


def selected_path_abs_cases(values: Sequence[str]) -> List[str]:
    if not values:
        return list(PATH_ABSTRACTION_PROOF_SCENARIOS)
    names: List[str] = []
    for value in values:
        if value == "all":
            names.extend(PATH_ABSTRACTION_PROOF_SCENARIOS)
        elif value in PATH_ABSTRACTION_PROOF_SCENARIOS:
            names.append(value)
        else:
            valid = ", ".join(PATH_ABSTRACTION_PROOF_SCENARIOS)
            raise SystemExit(f"Unknown path abstraction scenario {value!r}. Valid cases: {valid}")
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


def add_cause_argument(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--cases",
        nargs="*",
        default=["all"],
        help="Cause scenarios to use. Use all or one/more cause_XX names.",
    )


def add_path_abs_argument(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--cases",
        nargs="*",
        default=["all"],
        help="Path abstraction proof cases to use. Use all or one/more path_abs_* names.",
    )


def add_sweep_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--agent-counts",
        nargs="*",
        type=int,
        default=DEFAULT_SWEEP_AGENT_COUNTS,
        help="Agent counts for the sweep. Default: 2 10 20 25 30 35",
    )
    parser.add_argument(
        "--ratios",
        nargs="*",
        type=float,
        default=DEFAULT_SWEEP_RATIOS,
        help="Tunnel ratios as fractions or percents. Default: 50 60 70 80",
    )
    parser.add_argument("--samples", type=int, default=1, help="Random grid samples per agent/ratio pair")
    parser.add_argument("--min-width", type=int, default=80, help="Minimum random grid width")
    parser.add_argument("--max-width", type=int, default=160, help="Maximum random grid width")
    parser.add_argument("--min-height", type=int, default=15, help="Minimum random grid height")
    parser.add_argument("--max-height", type=int, default=25, help="Maximum random grid height")
    parser.add_argument("--seed", type=int, default=DEFAULT_SWEEP_SEED, help="Random seed for reproducible grid sizes")


def add_cause_sweep_arguments(parser: argparse.ArgumentParser) -> None:
    add_sweep_arguments(parser)
    parser.add_argument(
        "--cause-cases",
        nargs="*",
        default=["all"],
        help="Cause scenarios to cross with the sweep. Use all or one/more cause_XX names.",
    )


def sweep_specs_from_args(args) -> Dict[str, ScenarioSpec]:
    return build_sweep_specs(
        agent_counts=args.agent_counts,
        ratios=args.ratios,
        samples=args.samples,
        min_width=args.min_width,
        max_width=args.max_width,
        min_height=args.min_height,
        max_height=args.max_height,
        seed=args.seed,
    )


def cause_sweep_specs_from_args(args) -> Dict[str, ScenarioSpec]:
    base_specs = sweep_specs_from_args(args)
    cause_names = selected_cause_cases(args.cause_cases)
    return build_cause_sweep_specs(base_specs, cause_names)


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
    run_parser.add_argument("--timeout-seconds", type=int, default=0, help="Stop the solver after this many seconds; 0 means no timeout")

    collect_parser = subparsers.add_parser("collect", help="Collect metrics from existing debug generated folders")
    add_case_argument(collect_parser)

    all_parser = subparsers.add_parser("all", help="Generate, run, and collect debug metrics")
    add_case_argument(all_parser)
    all_parser.add_argument("--timeout-seconds", type=int, default=0, help="Stop the solver after this many seconds; 0 means no timeout")

    path_abs_list_parser = subparsers.add_parser("path-abs-list", help="List the one-success two-failure path abstraction proof cases")
    add_path_abs_argument(path_abs_list_parser)

    path_abs_generate_parser = subparsers.add_parser("path-abs-generate", help="Generate path abstraction proof scenarios")
    add_path_abs_argument(path_abs_generate_parser)

    path_abs_run_parser = subparsers.add_parser("path-abs-run", help="Run path abstraction proof scenarios one by one")
    add_path_abs_argument(path_abs_run_parser)
    path_abs_run_parser.add_argument("--timeout-seconds", type=int, default=0, help="Stop each scenario after this many seconds; 0 means no timeout")
    path_abs_run_parser.add_argument("--keep-going", action="store_true", help="Continue to the next scenario if one fails or times out")
    path_abs_run_parser.add_argument("--no-collect", action="store_true", help="Do not collect CSV metrics after running")

    path_abs_collect_parser = subparsers.add_parser("path-abs-collect", help="Collect metrics from path abstraction proof scenarios")
    add_path_abs_argument(path_abs_collect_parser)

    path_abs_all_parser = subparsers.add_parser("path-abs-all", help="Generate, run, and collect path abstraction proof scenarios")
    add_path_abs_argument(path_abs_all_parser)
    path_abs_all_parser.add_argument("--timeout-seconds", type=int, default=0, help="Stop each scenario after this many seconds; 0 means no timeout")
    path_abs_all_parser.add_argument("--keep-going", action="store_true", help="Continue to the next scenario if one fails or times out")

    cause_list_parser = subparsers.add_parser("cause-list", help="List the 10 targeted failure-cause scenarios")
    add_cause_argument(cause_list_parser)

    cause_generate_parser = subparsers.add_parser("cause-generate", help="Generate the 10 targeted failure-cause scenarios")
    add_cause_argument(cause_generate_parser)

    cause_run_parser = subparsers.add_parser("cause-run", help="Run targeted failure-cause scenarios one by one")
    add_cause_argument(cause_run_parser)
    cause_run_parser.add_argument("--timeout-seconds", type=int, default=0, help="Stop each scenario after this many seconds; 0 means no timeout")
    cause_run_parser.add_argument("--keep-going", action="store_true", help="Continue to the next scenario if one fails or times out")
    cause_run_parser.add_argument("--no-collect", action="store_true", help="Do not collect CSV metrics after running")

    cause_collect_parser = subparsers.add_parser("cause-collect", help="Collect metrics from targeted failure-cause scenarios")
    add_cause_argument(cause_collect_parser)

    cause_all_parser = subparsers.add_parser("cause-all", help="Generate, run, and collect the 10 targeted failure-cause scenarios")
    add_cause_argument(cause_all_parser)
    cause_all_parser.add_argument("--timeout-seconds", type=int, default=0, help="Stop each scenario after this many seconds; 0 means no timeout")
    cause_all_parser.add_argument("--keep-going", action="store_true", help="Continue to the next scenario if one fails or times out")

    sweep_list_parser = subparsers.add_parser("sweep-list", help="List generated parameter-sweep cases")
    add_sweep_arguments(sweep_list_parser)

    sweep_generate_parser = subparsers.add_parser("sweep-generate", help="Generate parameter-sweep scenario files")
    add_sweep_arguments(sweep_generate_parser)

    sweep_run_parser = subparsers.add_parser("sweep-run", help="Run generated parameter-sweep scenarios one by one")
    add_sweep_arguments(sweep_run_parser)
    sweep_run_parser.add_argument("--timeout-seconds", type=int, default=0, help="Stop each scenario after this many seconds; 0 means no timeout")
    sweep_run_parser.add_argument("--keep-going", action="store_true", help="Continue to the next scenario if one fails or times out")
    sweep_run_parser.add_argument("--no-collect", action="store_true", help="Do not collect CSV metrics after running")

    sweep_collect_parser = subparsers.add_parser("sweep-collect", help="Collect metrics from parameter-sweep scenarios")
    add_sweep_arguments(sweep_collect_parser)

    sweep_all_parser = subparsers.add_parser("sweep-all", help="Generate, run, and collect parameter-sweep metrics")
    add_sweep_arguments(sweep_all_parser)
    sweep_all_parser.add_argument("--timeout-seconds", type=int, default=0, help="Stop each scenario after this many seconds; 0 means no timeout")
    sweep_all_parser.add_argument("--keep-going", action="store_true", help="Continue to the next scenario if one fails or times out")

    cause_sweep_list_parser = subparsers.add_parser("cause-sweep-list", help="List every failure cause crossed with every sweep case")
    add_cause_sweep_arguments(cause_sweep_list_parser)

    cause_sweep_generate_parser = subparsers.add_parser("cause-sweep-generate", help="Generate every failure cause crossed with every sweep case")
    add_cause_sweep_arguments(cause_sweep_generate_parser)

    cause_sweep_run_parser = subparsers.add_parser("cause-sweep-run", help="Run every failure cause crossed with every sweep case one by one")
    add_cause_sweep_arguments(cause_sweep_run_parser)
    cause_sweep_run_parser.add_argument("--timeout-seconds", type=int, default=0, help="Stop each scenario after this many seconds; 0 means no timeout")
    cause_sweep_run_parser.add_argument("--keep-going", action="store_true", help="Continue to the next scenario if one fails or times out")
    cause_sweep_run_parser.add_argument("--no-collect", action="store_true", help="Do not collect CSV metrics after running")

    cause_sweep_collect_parser = subparsers.add_parser("cause-sweep-collect", help="Collect metrics from every cause-by-sweep scenario")
    add_cause_sweep_arguments(cause_sweep_collect_parser)

    cause_sweep_all_parser = subparsers.add_parser("cause-sweep-all", help="Generate, run, and collect every cause-by-sweep scenario")
    add_cause_sweep_arguments(cause_sweep_all_parser)
    cause_sweep_all_parser.add_argument("--timeout-seconds", type=int, default=0, help="Stop each scenario after this many seconds; 0 means no timeout")
    cause_sweep_all_parser.add_argument("--keep-going", action="store_true", help="Continue to the next scenario if one fails or times out")

    args = parser.parse_args()

    if args.command == "list":
        for spec in SCENARIOS.values():
            print(
                f"{spec.name}: corridor={spec.corridor_case}({spec.tunnel_length}/{spec.grid_width}), "
                f"agents={spec.agent_case}({spec.agent_count})"
        )
        return

    if args.command.startswith("path-abs-"):
        cases = selected_path_abs_cases(args.cases)
        specs = {name: PATH_ABSTRACTION_PROOF_SCENARIOS[name] for name in cases}
        if args.command == "path-abs-list":
            for spec in specs.values():
                print(
                    f"{spec.name}: role={spec.proof_role}, expected={spec.expected_outcome}, "
                    f"mutation={spec.graph_mutation or 'none'}, ratio={spec.tunnel_target_ratio:.2f}, "
                    f"agents={spec.agent_count}"
                )
        elif args.command == "path-abs-generate":
            generate_specs(specs)
        elif args.command == "path-abs-run":
            run_cases_individually(cases, timeout_seconds=args.timeout_seconds, keep_going=args.keep_going)
            if not args.no_collect:
                collect_path_abs_scenarios(cases)
        elif args.command == "path-abs-collect":
            collect_path_abs_scenarios(cases)
        elif args.command == "path-abs-all":
            generate_specs(specs)
            run_cases_individually(cases, timeout_seconds=args.timeout_seconds, keep_going=args.keep_going)
            collect_path_abs_scenarios(cases)
        return

    if args.command == "cause-sweep-list":
        specs = cause_sweep_specs_from_args(args)
        for spec in specs.values():
            print(
                f"{spec.name}: cause={spec.target_failure_cause}, base={spec.base_sweep_name}, "
                f"width={spec.grid_width}, height={spec.grid_height}, "
                f"ratio={spec.tunnel_target_ratio:.2f}, agents={spec.agent_count}"
            )
        print(f"Total cause-by-sweep scenarios: {len(specs)}")
        return

    if args.command.startswith("cause-sweep-"):
        specs = cause_sweep_specs_from_args(args)
        case_names = list(specs)
        if args.command == "cause-sweep-generate":
            generate_specs(specs)
        elif args.command == "cause-sweep-run":
            run_cases_individually(case_names, timeout_seconds=args.timeout_seconds, keep_going=args.keep_going)
            if not args.no_collect:
                collect_specs(specs)
        elif args.command == "cause-sweep-collect":
            collect_specs(specs)
        elif args.command == "cause-sweep-all":
            generate_specs(specs)
            run_cases_individually(case_names, timeout_seconds=args.timeout_seconds, keep_going=args.keep_going)
            collect_specs(specs)
        return

    if args.command.startswith("cause-"):
        cases = selected_cause_cases(args.cases)
        specs = {name: CAUSE_SCENARIOS[name] for name in cases}
        if args.command == "cause-list":
            for spec in specs.values():
                print(
                    f"{spec.name}: cause={spec.target_failure_cause}, "
                    f"width={spec.grid_width}, ratio={spec.tunnel_target_ratio:.2f}, "
                    f"agents={spec.agent_count}"
                )
        elif args.command == "cause-generate":
            generate_specs(specs)
        elif args.command == "cause-run":
            run_cases_individually(cases, timeout_seconds=args.timeout_seconds, keep_going=args.keep_going)
            if not args.no_collect:
                collect_cause_scenarios(cases)
        elif args.command == "cause-collect":
            collect_cause_scenarios(cases)
        elif args.command == "cause-all":
            generate_specs(specs)
            run_cases_individually(cases, timeout_seconds=args.timeout_seconds, keep_going=args.keep_going)
            collect_cause_scenarios(cases)
        return

    if args.command == "sweep-list":
        specs = sweep_specs_from_args(args)
        for spec in specs.values():
            print(
                f"{spec.name}: width={spec.grid_width}, height={spec.grid_height}, "
                f"ratio={spec.tunnel_target_ratio:.2f}, tunnel={round(spec.grid_width * spec.tunnel_target_ratio)}, "
                f"agents={spec.agent_count}"
            )
        return

    if args.command.startswith("sweep-"):
        specs = sweep_specs_from_args(args)
        case_names = list(specs)
        if args.command == "sweep-generate":
            generate_specs(specs)
        elif args.command == "sweep-run":
            run_cases_individually(case_names, timeout_seconds=args.timeout_seconds, keep_going=args.keep_going)
            if not args.no_collect:
                collect_specs(specs)
        elif args.command == "sweep-collect":
            collect_specs(specs)
        elif args.command == "sweep-all":
            generate_specs(specs)
            run_cases_individually(case_names, timeout_seconds=args.timeout_seconds, keep_going=args.keep_going)
            collect_specs(specs)
        return

    cases = selected_cases(args.cases)
    if args.command == "generate":
        generate_scenarios(cases)
    elif args.command == "run":
        run_solver(cases, timeout_seconds=args.timeout_seconds)
        if not args.no_collect:
            collect_scenarios(cases)
    elif args.command == "collect":
        collect_scenarios(cases)
    elif args.command == "all":
        generate_scenarios(cases)
        run_solver(cases, timeout_seconds=args.timeout_seconds)
        collect_scenarios(cases)
    else:
        parser.print_help()
        sys.exit(2)


if __name__ == "__main__":
    main()
