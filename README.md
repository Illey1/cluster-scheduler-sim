# cluster-scheduler-sim

A small C++ simulator for learning how jobs can be scheduled on compute-cluster nodes. It is inspired by submitting jobs to managed clusters, but it is not an implementation or accurate simulation of SLURM.

## What currently works

The program processes manually defined job arrivals and completions in simulated-time order. A node allocates CPUs when a job starts and releases them when it completes. The simulated clock jumps directly to each event time.

There is no waiting queue or scheduler yet. An arriving job that cannot start immediately is reported and discarded.

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
time 0: Job 1 arrived
time 0: Job 1 started; 4/8 CPUs available
time 3: Job 2 arrived
time 3: Job 2 started; 0/8 CPUs available
time 8: Job 2 completed; 4/8 CPUs available
time 8: Job 3 arrived
time 8: Job 3 started; 0/8 CPUs available
time 10: Job 1 completed; 4/8 CPUs available
time 10: Job 3 completed; 8/8 CPUs available
Simulation finished at time 10; 8/8 CPUs available
```
