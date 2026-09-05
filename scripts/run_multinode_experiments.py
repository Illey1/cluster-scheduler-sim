#!/usr/bin/env python3

import argparse
import csv
import math
import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

import analyze_results
import generate_workload
import run_experiments


JOB_COUNT = 200
TOTAL_CPUS = 32
SEEDS = tuple(range(1, 11))
LOAD_CONDITIONS = (
    ("light", 4),
    ("moderate", 2),
    ("heavy", 1),
)
POLICIES = ("fcfs", "sjf", "backfill")


@dataclass(frozen=True)
class ClusterShape:
    label: str
    node_count: int
    cpus_per_node: int

    @property
    def total_cpus(self):
        return self.node_count * self.cpus_per_node


CLUSTER_SHAPES = (
    ClusterShape("1x32", 1, 32),
    ClusterShape("2x16", 2, 16),
    ClusterShape("4x8", 4, 8),
)

AGGREGATED_METRICS = run_experiments.AGGREGATED_METRICS

RUN_METRICS_HEADER = [
    "seed",
    "load_condition",
    "submission_time_scale",
    "cluster_shape",
    "node_count",
    "cpus_per_node",
    "total_cpus",
    "policy",
    "jobs_completed",
    "average_wait",
    "median_wait",
    "p95_wait",
    "average_turnaround",
    "throughput",
    "cpu_utilization_percent",
]

SUMMARY_HEADER = [
    "load_condition",
    "submission_time_scale",
    "cluster_shape",
    "node_count",
    "cpus_per_node",
    "total_cpus",
    "policy",
    "seed_count",
]
for metric_name in AGGREGATED_METRICS:
    SUMMARY_HEADER.extend([f"{metric_name}_mean", f"{metric_name}_std"])

INTEGER_COLUMNS = {
    "seed",
    "submission_time_scale",
    "node_count",
    "cpus_per_node",
    "total_cpus",
    "jobs_completed",
    "p95_wait",
    "seed_count",
}
TEXT_COLUMNS = {"load_condition", "cluster_shape", "policy"}


def validate_cluster_shapes(cluster_shapes=CLUSTER_SHAPES):
    if not cluster_shapes:
        raise ValueError("experiment must define at least one cluster shape")

    labels = set()
    dimensions = set()
    for shape in cluster_shapes:
        if not shape.label:
            raise ValueError("cluster shape label must not be empty")
        if shape.label in labels:
            raise ValueError(f"duplicate cluster shape label: {shape.label}")
        labels.add(shape.label)

        dimensions_key = (shape.node_count, shape.cpus_per_node)
        if dimensions_key in dimensions:
            raise ValueError(
                "duplicate cluster shape dimensions: "
                f"{shape.node_count}x{shape.cpus_per_node}"
            )
        dimensions.add(dimensions_key)

        if shape.node_count <= 0 or shape.cpus_per_node <= 0:
            raise ValueError(
                f"cluster shape {shape.label} must use positive dimensions"
            )
        if shape.total_cpus != TOTAL_CPUS:
            raise ValueError(
                f"cluster shape {shape.label} has {shape.total_cpus} CPUs; "
                f"expected {TOTAL_CPUS}"
            )


def job_composition(jobs):
    return tuple(sorted(
        (job_id, runtime, cpus)
        for job_id, _submission_time, runtime, cpus in jobs
    ))


def job_workload_signature(jobs):
    return tuple(sorted(tuple(job) for job in jobs))


def validate_jobs_fit_shapes(jobs, cluster_shapes=CLUSTER_SHAPES):
    validate_cluster_shapes(cluster_shapes)
    for shape in cluster_shapes:
        for job_id, _submission_time, _runtime, requested_cpus in jobs:
            if requested_cpus <= 0 or requested_cpus > shape.cpus_per_node:
                raise ValueError(
                    f"Job {job_id} requests {requested_cpus} CPUs and cannot "
                    f"fit an empty {shape.label} node"
                )


def build_workload_matrix(base_jobs):
    validate_jobs_fit_shapes(base_jobs)
    workload_matrix = {}

    for condition, scale_factor in LOAD_CONDITIONS:
        scaled_jobs = run_experiments.scale_submission_times(
            base_jobs, scale_factor
        )
        for shape in CLUSTER_SHAPES:
            workload_matrix[(condition, shape.label)] = [
                list(job) for job in scaled_jobs
            ]

    validate_workload_matrix(base_jobs, workload_matrix)
    return workload_matrix


def validate_workload_matrix(base_jobs, workload_matrix):
    validate_jobs_fit_shapes(base_jobs)
    expected_keys = {
        (condition, shape.label)
        for condition, _scale_factor in LOAD_CONDITIONS
        for shape in CLUSTER_SHAPES
    }
    observed_keys = set(workload_matrix)
    if observed_keys != expected_keys:
        missing = sorted(expected_keys - observed_keys)
        extra = sorted(observed_keys - expected_keys)
        raise ValueError(
            "incomplete workload matrix: "
            f"missing {len(missing)} variants and found {len(extra)} extras"
        )

    base_composition = job_composition(base_jobs)
    for condition, scale_factor in LOAD_CONDITIONS:
        expected_jobs = run_experiments.scale_submission_times(
            base_jobs, scale_factor
        )
        expected_signature = job_workload_signature(expected_jobs)
        condition_signatures = set()

        for shape in CLUSTER_SHAPES:
            jobs = workload_matrix[(condition, shape.label)]
            if job_composition(jobs) != base_composition:
                raise ValueError(
                    f"job composition changed for {condition}/{shape.label}"
                )
            signature = job_workload_signature(jobs)
            if signature != expected_signature:
                raise ValueError(
                    f"submission times are not scaled by {scale_factor} for "
                    f"{condition}/{shape.label}"
                )
            validate_jobs_fit_shapes(jobs, (shape,))
            condition_signatures.add(signature)

        if len(condition_signatures) != 1:
            raise ValueError(
                f"workloads differ across cluster shapes for {condition}"
            )


def validate_simulator_executable(simulator_path):
    if not simulator_path.is_file():
        raise ValueError(f"simulator executable not found: {simulator_path}")
    if not os.access(simulator_path, os.X_OK):
        raise ValueError(f"simulator is not executable: {simulator_path}")


def run_simulator(simulator_path, workload_path, result_path, policy, shape):
    try:
        process = subprocess.run(
            [
                str(simulator_path),
                str(workload_path),
                str(result_path),
                policy,
                "--nodes",
                str(shape.node_count),
                "--cpus-per-node",
                str(shape.cpus_per_node),
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
            f"simulator failed for {shape.label}/{policy} on "
            f"'{workload_path}' with exit status {process.returncode}: "
            f"{detail}"
        )


def make_run_row(seed, condition, scale_factor, shape, policy, summary):
    row = {
        "seed": seed,
        "load_condition": condition,
        "submission_time_scale": scale_factor,
        "cluster_shape": shape.label,
        "node_count": shape.node_count,
        "cpus_per_node": shape.cpus_per_node,
        "total_cpus": shape.total_cpus,
        "policy": policy,
    }
    for metric_name in AGGREGATED_METRICS:
        value = summary[metric_name]
        if metric_name in {"jobs_completed", "p95_wait"}:
            row[metric_name] = int(value)
        else:
            row[metric_name] = round(float(value), 6)
    return row


def expected_run_keys():
    return {
        (seed, condition, shape.label, shape.node_count,
         shape.cpus_per_node, policy)
        for seed in SEEDS
        for condition, _scale_factor in LOAD_CONDITIONS
        for shape in CLUSTER_SHAPES
        for policy in POLICIES
    }


def validate_complete_design(run_rows):
    expected = expected_run_keys()
    observed = set()
    condition_factors = dict(LOAD_CONDITIONS)
    shape_by_label = {shape.label: shape for shape in CLUSTER_SHAPES}

    for row in run_rows:
        try:
            seed = int(row["seed"])
            condition = str(row["load_condition"])
            scale_factor = int(row["submission_time_scale"])
            label = str(row["cluster_shape"])
            node_count = int(row["node_count"])
            cpus_per_node = int(row["cpus_per_node"])
            total_cpus = int(row["total_cpus"])
            policy = str(row["policy"])
            jobs_completed = int(row["jobs_completed"])
        except (KeyError, TypeError, ValueError) as error:
            raise ValueError("experiment row has invalid design fields") from error

        key = (
            seed,
            condition,
            label,
            node_count,
            cpus_per_node,
            policy,
        )
        if key in observed:
            raise ValueError(
                "duplicate experiment row for "
                f"seed={seed}, condition={condition}, shape={label}, "
                f"policy={policy}"
            )
        observed.add(key)

        if condition not in condition_factors:
            raise ValueError(f"unexpected load condition: {condition}")
        if scale_factor != condition_factors[condition]:
            raise ValueError(f"incorrect scale factor for condition: {condition}")

        shape = shape_by_label.get(label)
        if shape is None:
            raise ValueError(f"unexpected cluster shape: {label}")
        if (node_count, cpus_per_node) != (
            shape.node_count, shape.cpus_per_node
        ):
            raise ValueError(f"incorrect dimensions for cluster shape: {label}")
        if total_cpus != node_count * cpus_per_node or total_cpus != TOTAL_CPUS:
            raise ValueError(f"incorrect total CPU count for cluster shape: {label}")
        if policy not in POLICIES:
            raise ValueError(f"unexpected scheduling policy: {policy}")
        if jobs_completed != JOB_COUNT:
            raise ValueError(
                f"expected {JOB_COUNT} completed jobs for seed={seed}, "
                f"condition={condition}, shape={label}, policy={policy}"
            )

        for metric_name in AGGREGATED_METRICS:
            try:
                metric_value = float(row[metric_name])
            except (KeyError, TypeError, ValueError) as error:
                raise ValueError(
                    f"invalid {metric_name} for seed={seed}, "
                    f"condition={condition}, shape={label}, policy={policy}"
                ) from error
            if not math.isfinite(metric_value):
                raise ValueError(
                    f"non-finite {metric_name} for seed={seed}, "
                    f"condition={condition}, shape={label}, policy={policy}"
                )

        utilization = float(row["cpu_utilization_percent"])
        if utilization < 0 or utilization > 100:
            raise ValueError(
                f"CPU utilization outside [0, 100] for seed={seed}, "
                f"condition={condition}, shape={label}, policy={policy}"
            )

    if observed != expected:
        missing = sorted(expected - observed)
        extra = sorted(observed - expected)
        raise ValueError(
            "incomplete experiment design: "
            f"missing {len(missing)} rows and found {len(extra)} unexpected rows"
        )


def aggregate_run_metrics(run_rows):
    validate_complete_design(run_rows)
    aggregate_rows = []
    expected_seeds = set(SEEDS)

    for condition, scale_factor in LOAD_CONDITIONS:
        for shape in CLUSTER_SHAPES:
            for policy in POLICIES:
                matching_rows = [
                    row
                    for row in run_rows
                    if row["load_condition"] == condition
                    and row["cluster_shape"] == shape.label
                    and row["policy"] == policy
                ]
                observed_seeds = {int(row["seed"]) for row in matching_rows}
                if observed_seeds != expected_seeds:
                    raise ValueError(
                        f"aggregate group {condition}/{shape.label}/{policy} "
                        "does not contain all ten seeds"
                    )

                aggregate_row = {
                    "load_condition": condition,
                    "submission_time_scale": scale_factor,
                    "cluster_shape": shape.label,
                    "node_count": shape.node_count,
                    "cpus_per_node": shape.cpus_per_node,
                    "total_cpus": shape.total_cpus,
                    "policy": policy,
                    "seed_count": len(matching_rows),
                }
                for metric_name in AGGREGATED_METRICS:
                    values = [
                        float(row[metric_name]) for row in matching_rows
                    ]
                    mean, sample_std = run_experiments.mean_and_sample_std(
                        values
                    )
                    aggregate_row[f"{metric_name}_mean"] = mean
                    aggregate_row[f"{metric_name}_std"] = sample_std

                aggregate_rows.append(aggregate_row)

    if len(aggregate_rows) != 27:
        raise ValueError(
            f"expected 27 aggregate groups, found {len(aggregate_rows)}"
        )
    return aggregate_rows


def format_csv_value(column, value):
    if column in TEXT_COLUMNS:
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
        raise ValueError(
            f"could not write experiment CSV '{path}': {error}"
        ) from error


def analyze_result_matrix(labeled_results, expected_jobs):
    summaries = analyze_results.analyze_result_files(
        labeled_results, TOTAL_CPUS
    )
    first_results = analyze_results.read_result_file(
        labeled_results[0][1], TOTAL_CPUS
    )
    if analyze_results.workload_signature(first_results) != (
        job_workload_signature(expected_jobs)
    ):
        raise ValueError("simulator results do not match the generated workload")
    return summaries


def run_experiment(simulator_path, output_directory):
    validate_simulator_executable(simulator_path)
    validate_cluster_shapes()

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
        workload_matrix = build_workload_matrix(base_jobs)
        seed_directory = raw_directory / f"seed-{seed:02d}"
        seed_directory.mkdir(parents=True, exist_ok=True)
        generate_workload.write_workload(seed_directory / "base.csv", base_jobs)

        for condition, scale_factor in LOAD_CONDITIONS:
            condition_directory = seed_directory / condition
            condition_directory.mkdir(exist_ok=True)
            workload_path = condition_directory / "workload.csv"
            scaled_jobs = workload_matrix[
                (condition, CLUSTER_SHAPES[0].label)
            ]
            generate_workload.write_workload(workload_path, scaled_jobs)

            labeled_results = []
            run_metadata = {}
            for shape in CLUSTER_SHAPES:
                shape_directory = condition_directory / shape.label
                shape_directory.mkdir(exist_ok=True)
                for policy in POLICIES:
                    result_path = shape_directory / f"{policy}.csv"
                    run_simulator(
                        simulator_path,
                        workload_path,
                        result_path,
                        policy,
                        shape,
                    )
                    label = f"{shape.label}/{policy}"
                    labeled_results.append((label, result_path))
                    run_metadata[label] = (shape, policy)

            # One nine-file comparison verifies identical submitted workloads
            # across every shape and policy for this seed/load condition.
            summaries = analyze_result_matrix(labeled_results, scaled_jobs)
            for summary in summaries:
                shape, policy = run_metadata[summary["policy"]]
                run_rows.append(make_run_row(
                    seed,
                    condition,
                    scale_factor,
                    shape,
                    policy,
                    summary,
                ))

    validate_complete_design(run_rows)
    aggregate_rows = aggregate_run_metrics(run_rows)
    write_rows(output_directory / "run_metrics.csv", RUN_METRICS_HEADER, run_rows)
    write_rows(output_directory / "summary.csv", SUMMARY_HEADER, aggregate_rows)
    return run_rows, aggregate_rows


def parse_arguments():
    parser = argparse.ArgumentParser(
        description=(
            "Run the fixed-capacity multi-node scheduler experiment."
        )
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
            simulator_path, output_directory
        )
    except (OSError, ValueError) as error:
        print(f"Error: {error}", file=sys.stderr)
        return 1

    print(f"Completed {len(run_rows)} simulations.")
    print(f"Wrote run metrics to {output_directory / 'run_metrics.csv'}")
    print(
        f"Wrote {len(aggregate_rows)} aggregate rows to "
        f"{output_directory / 'summary.csv'}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
