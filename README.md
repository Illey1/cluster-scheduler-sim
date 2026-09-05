# cluster-scheduler-sim

`cluster-scheduler-sim` is a C++ discrete-event simulator for comparing batch scheduling policies across configurable CPU nodes.

## Build

```sh
cmake -S . -B build
cmake --build build
```

## Usage

```sh
./build/cluster-scheduler-sim workloads/example.csv results.csv fcfs
```

Available policies are `fcfs`, `sjf`, and `backfill`. The default configuration is one node with eight CPUs.

For a multi-node run:

```sh
./build/cluster-scheduler-sim workloads/multinode.csv results.csv backfill \
    --nodes 4 --cpus-per-node 8
```

## Workloads

Workloads use this CSV schema:

```text
job_id,submission_time,requested_runtime,requested_cpus
```

Generate a reproducible synthetic workload:

```sh
python3 scripts/generate_workload.py --jobs 100 --seed 42 --output workload.csv
```

## Scheduling

| Policy | Behavior |
| --- | --- |
| FCFS | Runs waiting jobs in submission order. |
| SJF | Prioritizes the shortest requested runtime. |
| Backfill | Allows later jobs to run when an earlier job is blocked and they fit. |

Jobs run on a single node and are placed using first-fit.

## Experiments

The repository contains two reproducible studies:

- A [90-run single-node study](experiments/README.md) comparing policies across workload-pressure levels.
- A [270-run fixed-capacity multi-node study](experiments/multinode/README.md) comparing `1×32`, `2×16`, and `4×8` cluster shapes.

Scheduler differences were small under light contention. Under heavier contention, backfill reduced average wait and maintained higher CPU utilization than FCFS. In the multi-node study, splitting the same 32 CPUs across more nodes increased heavy-load wait times, with FCFS affected most strongly.

## Tests

```sh
ctest --test-dir build --output-on-failure
python3 -m unittest discover -s tests -p 'test_*.py'
```

The simulator currently models homogeneous CPU-only nodes with non-preemptive jobs and synthetic workloads.
