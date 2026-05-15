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

## Targeted Failure Causes

These commands build one rich scenario for each failure cause:

1. `cause_01_long_tunnel`
2. `cause_02_high_agent_density`
3. `cause_03_head_on_traffic`
4. `cause_04_single_lane_bottleneck`
5. `cause_05_high_waiting_cost`
6. `cause_06_large_repair_overhead`
7. `cause_07_abstraction_compression`
8. `cause_08_shared_store_depot`
9. `cause_09_duplicate_goals`
10. `cause_10_misleading_abstract_makespan`

List them:

```bash
python3 debug/debug_framework.py cause-list
```

Generate only:

```bash
python3 debug/debug_framework.py cause-generate
```

Run and collect:

```bash
python3 debug/debug_framework.py cause-all --timeout-seconds 1800 --keep-going
```

Run one cause only:

```bash
python3 debug/debug_framework.py cause-all --cases cause_09_duplicate_goals --timeout-seconds 1800 --keep-going
```

If the solver already ran, rebuild the CSV without rerunning:

```bash
python3 debug/debug_framework.py cause-collect
```

## Full Cause-By-Sweep Proof Matrix

Use this when every failure cause must be tested on every debug sweep scenario.

Default size:

- `10` failure causes
- `4` tunnel ratios: `50 60 70 80`
- `6` agent counts: `2 10 20 25 30 35`
- `1` random grid sample
- total: `10 x 4 x 6 x 1 = 240` scenarios

First, only list the scenarios:

```bash
python3 debug/debug_framework.py cause-sweep-list --samples 1
```

Generate only:

```bash
python3 debug/debug_framework.py cause-sweep-generate --samples 1
```

Run everything one by one and keep collecting evidence even if a case fails:

```bash
python3 debug/debug_framework.py cause-sweep-all --samples 1 --timeout-seconds 1800 --keep-going
```

If your solver run already finished, rebuild the CSV only:

```bash
python3 debug/debug_framework.py cause-sweep-collect --samples 1
```

To include the zero-agent baseline:

```bash
python3 debug/debug_framework.py cause-sweep-all \
  --agent-counts 0 2 10 20 25 30 35 \
  --ratios 50 60 70 80 \
  --samples 1 \
  --timeout-seconds 1800 \
  --keep-going
```

To run only one cause across every sweep scenario:

```bash
python3 debug/debug_framework.py cause-sweep-all \
  --cause-cases cause_01_long_tunnel \
  --samples 1 \
  --timeout-seconds 1800 \
  --keep-going
```

## Main CSV

The main output file is:

```text
debug/results/debug_results.csv
```

Important columns include:

- `scenario_name`
- `debug_suite`
- `base_sweep_name`
- `cause_case_name`
- `cause_number`
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
- `left_agent_count`
- `right_agent_count`
- `opposing_agent_pair_count`
- `agents_per_tunnel_node`
- `opposing_pair_pressure`
- `wait_ratio`
- `repair_overhead_ratio`
- `longest_repair_to_tunnel_ratio`
- `long_tunnel_risk`
- `high_agent_density_risk`
- `head_on_traffic_risk`
- `single_lane_bottleneck_risk`
- `abstraction_compression_risk`
- `repair_overhead_risk`
- `wait_congestion_risk`
- `timeout_or_failed_risk`
- `target_failure_flag`
- `target_failure_triggered`
- `failure_risk_score`
- `likely_failure_causes`
- `failure_evidence_summary`

These columns are meant for charts that compare long corridor cost, high-agent conflict cost, and the combined case.
