#!/usr/bin/env python3
"""Debug-only mutations for generated GTAPF abstract maps."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path


EDGE_RE = re.compile(r"^\s*edge\((-?\d+),(-?\d+)\)\.\s*$")


def node_col(node: int, width: int) -> int:
    return node % width


def crosses_cut(left: int, right: int, width: int, cut_col: int) -> bool:
    left_col = node_col(left, width)
    right_col = node_col(right, width)
    return (left_col <= cut_col < right_col) or (right_col <= cut_col < left_col)


def remove_abstract_bridge(abstract_map: Path, metadata: dict) -> dict:
    width = int(metadata["grid_width"])
    cut_col = metadata.get("tunnel_gap_col")
    if cut_col in ("", None):
        cut_col = (int(metadata["tunnel_start_col"]) + int(metadata["tunnel_end_col"])) // 2
    cut_col = int(cut_col)

    kept = []
    removed = []
    for line in abstract_map.read_text(encoding="utf-8", errors="replace").splitlines():
        match = EDGE_RE.match(line)
        if match:
            src = int(match.group(1))
            dst = int(match.group(2))
            if crosses_cut(src, dst, width, cut_col):
                removed.append(line)
                continue
        kept.append(line)

    abstract_map.write_text("\n".join(kept) + "\n", encoding="utf-8")
    return {
        "abstract_mutation": "remove_abstract_bridge",
        "abstract_bridge_cut_col": cut_col,
        "abstract_removed_edge_count": len(removed),
        "abstract_removed_edges_preview": removed[:20],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Apply debug-only abstract-map mutations")
    parser.add_argument("abstract_map", type=Path)
    parser.add_argument("metadata", type=Path)
    parser.add_argument("--summary", type=Path, default=Path("__tmp.abstract_mutation.json"))
    args = parser.parse_args()

    metadata = json.loads(args.metadata.read_text(encoding="utf-8"))
    mutation = metadata.get("graph_mutation", "")
    if mutation != "remove_abstract_bridge":
        return

    summary = remove_abstract_bridge(args.abstract_map, metadata)
    args.summary.write_text(json.dumps(summary, indent=2, sort_keys=True), encoding="utf-8")


if __name__ == "__main__":
    main()
