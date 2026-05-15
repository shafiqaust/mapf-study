# GTAPF Debug Framework

This folder is for controlled experiments that test whether GTAPF has trouble when:

- the corridor is long but the number of agents is low
- the corridor is short but the number of agents is high
- both corridor length and agent count change together

The framework creates four controlled cases:

| Case | Grid width | Tunnel length | Agents | Purpose |
| --- | --- | --- | --- | --- |
| `short_low` | 100 | 20, or 20% | 2 | easy baseline |
| `long_low` | 100 | 70, or 70% | 2 | isolates long-tunnel abstraction cost |
| `short_high` | 100 | 20, or 20% | 12 | isolates crowding/conflict cost |
| `long_high` | 100 | 70, or 70% | 12 | combined stress case |

## Run Everything

From the repo root:

```bash
cd /Users/shafiq/MSC/NMSU_PhD/mapf-study
python3 debug/debug_framework.py all
```

This will:

1. create the debug scenarios under `debug/scenarios/`
2. run the normal `test_asp` pipeline on each scenario
3. store detailed metrics in `debug/results/debug_results.csv`
4. store per-scenario JSON details in `debug/results/details/`
5. store the solver log in `debug/results/logs/`

## Run Only One Case

```bash
cd /Users/shafiq/MSC/NMSU_PhD/mapf-study
python3 debug/debug_framework.py all --cases long_low
```

More examples:

```bash
python3 debug/debug_framework.py all --cases short_high
python3 debug/debug_framework.py all --cases long_low short_high
python3 debug/debug_framework.py all --cases long_high --timeout-seconds 600
python3 debug/debug_framework.py generate
python3 debug/debug_framework.py collect
```

## Parameter Sweep

The sweep mode generates many tunnel cases with random grid sizes.
By default it uses:

- agents: `2 10 20 25 30 35`
- tunnel ratios: `50 60 70 80`
- one random grid sample per agent/ratio pair
- random grid widths from `80` to `160`
- random odd grid heights from `15` to `25`

List the cases first:

```bash
python3 debug/debug_framework.py sweep-list --samples 1
```

Generate only:

```bash
python3 debug/debug_framework.py sweep-generate --samples 1
```

Run and collect:

```bash
python3 debug/debug_framework.py sweep-all --samples 1 --timeout-seconds 1800 --keep-going
```

Use custom agents, ratios, and grid sizes:

```bash
python3 debug/debug_framework.py sweep-all \
  --agent-counts 2 10 20 25 30 35 \
  --ratios 50 60 70 80 \
  --samples 2 \
  --min-width 100 \
  --max-width 200 \
  --timeout-seconds 1800 \
  --keep-going
```

If you need a zero-agent baseline, include `0` explicitly:

```bash
python3 debug/debug_framework.py sweep-all --agent-counts 0 2 10 20 25 30 35 --ratios 50 60 70 80
```

## Main CSV

The main output file is:

```text
debug/results/debug_results.csv
```

Important columns include:

- `scenario_name`
- `corridor_case`
- `agent_case`
- `grid_width`
- `grid_height`
- `tunnel_target_ratio`
- `tunnel_width_ratio`
- `tunnel_width_percent`
- `configured_tunnel_length`
- `configured_corridor_length`
- `solver_status`
- `solver_log_path`
- `total_agents`
- `agent_density`
- `corridor_node_count`
- `longest_corridor_component`
- `abstract_vertices`
- `abstract_edges`
- `compression_ratio`
- `abstract_makespan`
- `repair_makespan`
- `observed_makespan`
- `sum_of_costs`
- `repair_cost`
- `total_waits`
- `repair_segments`
- `longest_repair_steps`
- `abstract_plan_details`
- `abstract_transitions`
- `repair_path_details`
- `repair_path_details_readable`
- `move_details`
- `stay_details`
- `visited_details`
- `per_agent_costs`

These columns are meant for charts that compare long corridor cost, high-agent conflict cost, and the combined case.
