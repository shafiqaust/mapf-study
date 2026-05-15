# GTAPF Debug Framework

This folder is for controlled experiments that test whether GTAPF has trouble when:

- the corridor is long but the number of agents is low
- the corridor is short but the number of agents is high
- both corridor length and agent count change together

The framework creates four synthetic cases:

| Case | Corridor | Agents | Purpose |
| --- | --- | --- | --- |
| `short_low` | short | low | easy baseline |
| `long_low` | long | low | isolates long-corridor abstraction cost |
| `short_high` | short | high | isolates crowding/conflict cost |
| `long_high` | long | high | combined stress case |

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
python3 debug/debug_framework.py generate
python3 debug/debug_framework.py collect
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
- `configured_corridor_length`
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
- `repair_path_details_readable`
- `per_agent_costs`

These columns are meant for charts that compare long corridor cost, high-agent conflict cost, and the combined case.
