#!/usr/bin/env python3

import argparse
import csv
import os
import statistics
import subprocess
import sys
from pathlib import Path

import analyze_results
import generate_workload


JOB_COUNT = 200
TOTAL_CPUS = 8
SEEDS = tuple(range(1, 11))
LOAD_CONDITIONS = (
    ("light", 8),
    ("moderate", 4),
    ("heavy", 2),
)
POLICIES = ("fcfs", "sjf", "backfill")

RUN_METRICS_HEADER = [
    "seed",
    "load_condition",
    "submission_time_scale",
    "policy",
    "jobs_completed",
    "average_wait",
    "median_wait",
    "p95_wait",
    "average_turnaround",
    "throughput",
    "cpu_utilization_percent",
]

AGGREGATED_METRICS = (
    "jobs_completed",
    "average_wait",
    "median_wait",
    "p95_wait",
    "average_turnaround",
    "throughput",
    "cpu_utilization_percent",
)

SUMMARY_HEADER = [
    "load_condition",
    "submission_time_scale",
    "policy",
    "seed_count",
]
for metric_name in AGGREGATED_METRICS:
    SUMMARY_HEADER.extend([f"{metric_name}_mean", f"{metric_name}_std"])

INTEGER_COLUMNS = {
    "seed",
    "submission_time_scale",
    "jobs_completed",
    "p95_wait",
    "seed_count",
}


def scale_submission_times(jobs, scale_factor):
    if scale_factor <= 0:
        raise ValueError("submission-time scale factor must be positive")

    return [
        [job_id, submission_time * scale_factor, runtime, cpus]
        for job_id, submission_time, runtime, cpus in jobs
    ]


def job_characteristics(jobs):
    return tuple(
        (job_id, runtime, cpus)
        for job_id, _submission_time, runtime, cpus in jobs
    )


def validate_simulator_executable(simulator_path):
    if not simulator_path.is_file():
        raise ValueError(f"simulator executable not found: {simulator_path}")
    if not os.access(simulator_path, os.X_OK):
        raise ValueError(f"simulator is not executable: {simulator_path}")


def run_simulator(simulator_path, workload_path, result_path, policy):
    try:
        process = subprocess.run(
            [
                str(simulator_path),
                str(workload_path),
                str(result_path),
                policy,
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            text=True,
            check=False,
        )
    except OSError as error:
        raise ValueError(
            f"could not run simulator '{simulator_path}': {error}"
        ) from error

    if process.returncode != 0:
        detail = process.stderr.strip() or "no error message"
        raise ValueError(
            f"simulator failed for {policy} on '{workload_path}' "
            f"with exit status {process.returncode}: {detail}"
        )


def make_run_row(seed, condition, scale_factor, summary):
    row = {
        "seed": seed,
        "load_condition": condition,
        "submission_time_scale": scale_factor,
        "policy": summary["policy"],
    }
    for metric_name in AGGREGATED_METRICS:
        value = summary[metric_name]
        if metric_name in {"jobs_completed", "p95_wait"}:
            row[metric_name] = int(value)
        else:
            # Published run-level values are the source for aggregation.
            row[metric_name] = round(float(value), 6)
    return row


def validate_complete_design(run_rows):
    expected = {
        (seed, condition, policy)
        for seed in SEEDS
        for condition, _scale_factor in LOAD_CONDITIONS
        for policy in POLICIES
    }
    observed = set()
    condition_factors = dict(LOAD_CONDITIONS)

    for row in run_rows:
        key = (
            int(row["seed"]),
            str(row["load_condition"]),
            str(row["policy"]),
        )
        if key in observed:
            raise ValueError(
                "duplicate experiment row for "
                f"seed={key[0]}, condition={key[1]}, policy={key[2]}"
            )
        observed.add(key)

        condition = key[1]
        if condition not in condition_factors:
            raise ValueError(f"unexpected load condition: {condition}")
        if int(row["submission_time_scale"]) != condition_factors[condition]:
            raise ValueError(f"incorrect scale factor for condition: {condition}")
        if int(row["jobs_completed"]) != JOB_COUNT:
            raise ValueError(
                f"expected {JOB_COUNT} completed jobs for "
                f"seed={key[0]}, condition={condition}, policy={key[2]}"
            )

    if observed != expected:
        missing = sorted(expected - observed)
        extra = sorted(observed - expected)
        raise ValueError(
            "incomplete experiment design: "
            f"missing {len(missing)} rows and found {len(extra)} unexpected rows"
        )


def mean_and_sample_std(values):
    return statistics.mean(values), statistics.stdev(values)


def aggregate_run_metrics(run_rows):
    validate_complete_design(run_rows)
    aggregate_rows = []

    for condition, scale_factor in LOAD_CONDITIONS:
        for policy in POLICIES:
            matching_rows = [
                row
                for row in run_rows
                if row["load_condition"] == condition
                and row["policy"] == policy
            ]
            aggregate_row = {
                "load_condition": condition,
                "submission_time_scale": scale_factor,
                "policy": policy,
                "seed_count": len(matching_rows),
            }

            for metric_name in AGGREGATED_METRICS:
                values = [float(row[metric_name]) for row in matching_rows]
                mean, sample_std = mean_and_sample_std(values)
                aggregate_row[f"{metric_name}_mean"] = mean
                aggregate_row[f"{metric_name}_std"] = sample_std

            aggregate_rows.append(aggregate_row)

    return aggregate_rows


def format_csv_value(column, value):
    if column in {"load_condition", "policy"}:
        return str(value)
    if column in INTEGER_COLUMNS:
        return str(int(value))
    return f"{float(value):.6f}"


def write_rows(path, header, rows):
    try:
        with path.open("w", encoding="utf-8", newline="") as output_file:
            writer = csv.DictWriter(
                output_file,
                fieldnames=header,
                lineterminator="\n",
            )
            writer.writeheader()
            for row in rows:
                writer.writerow({
                    column: format_csv_value(column, row[column])
                    for column in header
                })
    except OSError as error:
        raise ValueError(f"could not write experiment CSV '{path}': {error}") \
            from error


def run_experiment(simulator_path, output_directory):
    validate_simulator_executable(simulator_path)

    try:
        output_directory.mkdir(parents=True, exist_ok=True)
        raw_directory = output_directory / "raw"
        raw_directory.mkdir(exist_ok=True)
    except OSError as error:
        raise ValueError(
            f"could not create experiment output directory "
            f"'{output_directory}': {error}"
        ) from error

    run_rows = []

    for seed in SEEDS:
        base_jobs = generate_workload.generate_jobs(JOB_COUNT, seed)
        base_characteristics = job_characteristics(base_jobs)
        seed_directory = raw_directory / f"seed-{seed:02d}"
        seed_directory.mkdir(parents=True, exist_ok=True)
        generate_workload.write_workload(
            seed_directory / "base.csv",
            base_jobs,
        )

        for condition, scale_factor in LOAD_CONDITIONS:
            scaled_jobs = scale_submission_times(base_jobs, scale_factor)
            if job_characteristics(scaled_jobs) != base_characteristics:
                raise ValueError(
                    f"job characteristics changed while scaling seed {seed}"
                )

            condition_directory = seed_directory / condition
            condition_directory.mkdir(exist_ok=True)
            workload_path = condition_directory / "workload.csv"
            generate_workload.write_workload(workload_path, scaled_jobs)

            labeled_results = []
            for policy in POLICIES:
                result_path = condition_directory / f"{policy}.csv"
                run_simulator(
                    simulator_path,
                    workload_path,
                    result_path,
                    policy,
                )
                labeled_results.append((policy, result_path))

            # This analyzes all policies together, so the Milestone 9 analyzer
            # verifies that each policy received the same submitted workload.
            summaries = analyze_results.analyze_result_files(
                labeled_results,
                TOTAL_CPUS,
            )
            run_rows.extend(
                make_run_row(seed, condition, scale_factor, summary)
                for summary in summaries
            )

    validate_complete_design(run_rows)
    aggregate_rows = aggregate_run_metrics(run_rows)
    write_rows(output_directory / "run_metrics.csv", RUN_METRICS_HEADER, run_rows)
    write_rows(output_directory / "summary.csv", SUMMARY_HEADER, aggregate_rows)
    return run_rows, aggregate_rows


def parse_arguments():
    parser = argparse.ArgumentParser(
        description="Run the fixed multi-seed scheduler experiment."
    )
    parser.add_argument("--simulator", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    return parser.parse_args()


def main():
    arguments = parse_arguments()
    simulator_path = arguments.simulator.expanduser().resolve()
    output_directory = arguments.output_dir.expanduser().resolve()

    try:
        run_rows, aggregate_rows = run_experiment(
            simulator_path,
            output_directory,
        )
    except (OSError, ValueError) as error:
        print(f"Error: {error}", file=sys.stderr)
        return 1

    print(f"Completed {len(run_rows)} simulations.")
    print(f"Wrote run metrics to {output_directory / 'run_metrics.csv'}")
    print(f"Wrote {len(aggregate_rows)} aggregate rows to "
          f"{output_directory / 'summary.csv'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
