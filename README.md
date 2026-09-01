# cluster-scheduler-sim

A small C++ simulator for learning how jobs can be scheduled on compute-cluster nodes. It is inspired by submitting jobs to managed clusters, but it is not an implementation or accurate simulation of SLURM.

## What currently works

The program defines a `Job` with a submission time, requested runtime, and CPU request. It also defines a `Node` with total and available CPU counts. The example constructs one of each and prints their values.

Scheduling and CPU allocation are not implemented yet.

## Build

```sh
cmake -S . -B build
cmake --build build
```

## Run the example

```sh
./build/cluster-scheduler-sim
```

Expected output:

```text
Job 1: submit=0, runtime=10, cpus=4
Node 0: total_cpus=8, available_cpus=8
```
