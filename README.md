# cluster-scheduler-sim

A small C++ simulator for learning how jobs can be scheduled on compute-cluster nodes. It is inspired by submitting jobs to managed clusters.

## Behavior

The program processes manually defined job arrivals and completions in simulated-time order. A node allocates CPUs when a job starts and releases them when it completes. The simulated clock jumps directly to each event time.

Jobs that cannot start immediately wait in a strict First-Come, First-Served queue. If the first waiting job cannot fit, smaller jobs behind it do not run early.

## Build

```sh
cmake -S . -B build
cmake --build build
```

## Run the example

```sh
./build/cluster-scheduler-sim
```
