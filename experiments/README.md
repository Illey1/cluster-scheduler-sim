# Scheduler policy experiment

## Question

How do FCFS, non-preemptive SJF, and greedy backfilling behave as the same jobs compete more heavily for one 8-CPU node?

## Setup

The experiment uses 200 synthetic jobs for each seed from 1 through 10. For a given seed, job IDs, runtimes, and CPU requests are generated once and held fixed. Only submission times change:

| Condition | Submission-time scale |
|---|---:|
| Light | 8 |
| Moderate | 4 |
| Heavy | 2 |

Each scaled workload is run under all three policies, producing 90 simulations. Scaling preserves simultaneous arrivals because zero-length arrival gaps remain zero. The condition names express relative workload pressure, not target utilization levels.

[`run_metrics.csv`](run_metrics.csv) contains one row per simulation. [`summary.csv`](summary.csv) reports the mean and sample standard deviation across the ten seeds for every condition and policy. Metrics retain the definitions and validation in [`analyze_results.py`](../scripts/analyze_results.py); every within-condition policy comparison passes its same-workload check.

## Results

The three plotted metrics are shown as mean ± sample standard deviation across seeds.

| Condition | Policy | Average wait | P95 wait | CPU utilization (%) |
|---|---|---:|---:|---:|
| Light | FCFS | 5.30 ± 2.04 | 26.70 ± 9.21 | 41.89 ± 2.94 |
| Light | SJF | 3.97 ± 1.08 | 20.20 ± 3.99 | 41.89 ± 2.94 |
| Light | Backfill | 4.11 ± 1.49 | 21.60 ± 7.88 | 41.89 ± 2.95 |
| Moderate | FCFS | 80.83 ± 33.53 | 156.20 ± 57.93 | 74.35 ± 3.63 |
| Moderate | SJF | 35.71 ± 14.75 | 192.10 ± 116.91 | 76.68 ± 3.92 |
| Moderate | Backfill | 27.36 ± 10.49 | 93.10 ± 36.24 | 80.81 ± 5.36 |
| Heavy | FCFS | 337.02 ± 56.09 | 649.20 ± 71.55 | 77.12 ± 1.86 |
| Heavy | SJF | 191.34 ± 32.18 | 833.00 ± 94.32 | 80.91 ± 2.19 |
| Heavy | Backfill | 147.02 ± 35.37 | 467.50 ± 72.70 | 93.96 ± 3.10 |

Under light pressure, all policies have a median wait of zero and nearly identical utilization and throughput. Differences become clearer as submissions are compressed. FCFS has the highest mean wait in every moderate and heavy seed, while backfill has the highest utilization in every moderate and heavy seed. This pattern is consistent with FCFS head-of-line blocking leaving capacity unused when the first waiting job cannot fit.

SJF has much lower moderate and heavy median wait than FCFS or backfill, but its p95 is higher than FCFS under those conditions. Under heavy pressure, SJF has the highest p95 in every seed. Favoring short jobs therefore helps the center of the wait distribution here while allowing some jobs to wait much longer.

Backfill has the lowest moderate and heavy mean and p95 wait, but it does not dominate every metric: SJF retains substantially lower median wait, and backfill's heavy median varies widely across seeds. The p95 measurements do not reveal a systematic downside from the lack of reservations in these workloads. Backfill p95 never exceeds FCFS p95, although it exceeds SJF p95 in some light and moderate seeds.

Throughput and CPU utilization are not independent confirmations. Within a seed and condition, every policy completes the same jobs and consumes the same total requested CPU-time, so both metrics are strongly influenced by the policy's makespan.

## Figures

- [`average_wait.png`](figures/average_wait.png)
- [`p95_wait.png`](figures/p95_wait.png)
- [`cpu_utilization.png`](figures/cpu_utilization.png)

Error bars show one sample standard deviation across seeds.

## Reproduce

The experiment driver uses the Python standard library. Matplotlib is required only for the plotting command.

```sh
cmake -S . -B build
cmake --build build
python3 scripts/run_experiments.py \
    --simulator ./build/cluster-scheduler-sim \
    --output-dir experiments
python3 -m pip install -r requirements.txt
python3 scripts/plot_experiments.py \
    --summary experiments/summary.csv \
    --output-dir experiments/figures
```

Raw workloads and per-job results are regenerated under `experiments/raw/` and ignored by Git.

## Limitations

This is a descriptive experiment on one 8-CPU node using synthetic workloads, fixed known runtimes, CPU-only requests, and non-preemptive jobs. Greedy backfill has no reservations, SJF knows requested runtimes, and p95 does not directly measure the single worst wait or prove absence of starvation. The ten seeds characterize this declared generator and these load factors; they do not establish statistical significance or production-cluster realism.
