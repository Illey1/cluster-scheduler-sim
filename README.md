# cluster-scheduler-sim

A small C++ simulator for learning how jobs can be scheduled on compute-cluster nodes. It is inspired by submitting jobs to managed clusters.

## Behavior

The program loads jobs from CSV and processes their arrivals and completions in simulated-time order on one 8-CPU node. The simulated clock jumps directly to each event time.

Jobs that cannot start immediately wait in a strict First-Come, First-Served queue. If the first waiting job cannot fit, smaller jobs behind it do not run early.

## Build

```sh
cmake -S . -B build
cmake --build build
```

## Run the example

```sh
./build/cluster-scheduler-sim workloads/example.csv results.csv
```

## Generate a workload

```sh
python3 scripts/generate_workload.py \
    --jobs 100 \
    --seed 42 \
    --output workloads/generated.csv
```

The generator creates synthetic workloads using simple random integer ranges. A seed makes the generated CSV reproducible.

## Workload CSV

The input file contains one job per row:

```text
job_id,submission_time,requested_runtime,requested_cpus
1,0,10,6
```

All values are integers, and simulated times use the same arbitrary time unit.

## Result CSV

The output contains one row per completed job:

```text
job_id,submission_time,start_time,completion_time,requested_runtime,requested_cpus,wait_time
```

Wait time is the difference between a job's start time and submission time.
