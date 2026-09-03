#!/usr/bin/env python3

import argparse
import csv
import math
import statistics
import sys
from pathlib import Path


RESULT_HEADER = [
    "job_id",
    "submission_time",
    "start_time",
    "completion_time",
    "requested_runtime",
    "requested_cpus",
    "wait_time",
]

SUMMARY_HEADER = [
    "policy",
    "jobs_completed",
    "average_wait",
    "median_wait",
    "p95_wait",
    "average_turnaround",
    "throughput",
    "cpu_utilization_percent",
]


def positive_integer(value):
    try:
        number = int(value)
    except ValueError as error:
        raise argparse.ArgumentTypeError("value must be an integer") from error

    if number <= 0:
        raise argparse.ArgumentTypeError("value must be greater than zero")

    return number


def parse_labeled_result(value):
    if "=" not in value:
        raise argparse.ArgumentTypeError(
            "result must use the form label=path"
        )

    label, path = value.split("=", 1)
    label = label.strip()
    path = path.strip()

    if not label or not path:
        raise argparse.ArgumentTypeError(
            "result must contain a nonempty label and path"
        )

    return label, Path(path)


def validate_total_cpus(total_cpus):
    if total_cpus <= 0:
        raise ValueError("total CPU count must be greater than zero")


def read_result_file(path, total_cpus):
    validate_total_cpus(total_cpus)

    try:
        input_file = path.open(encoding="utf-8", newline="")
    except OSError as error:
        raise ValueError(f"could not open result file '{path}': {error}") from error

    with input_file:
        reader = csv.reader(input_file)

        try:
            header = next(reader)
        except StopIteration as error:
            raise ValueError(f"result file is empty: {path}") from error

        if header != RESULT_HEADER:
            raise ValueError(f"unexpected result header in: {path}")

        results = []
        job_ids = set()

        for line_number, row in enumerate(reader, start=2):
            if len(row) != len(RESULT_HEADER):
                raise ValueError(
                    f"malformed result row {line_number} in '{path}': "
                    f"expected {len(RESULT_HEADER)} integer fields"
                )

            try:
                result = {
                    name: int(value)
                    for name, value in zip(RESULT_HEADER, row)
                }
            except ValueError as error:
                raise ValueError(
                    f"malformed result row {line_number} in '{path}': "
                    "all fields must be integers"
                ) from error

            job_id = result["job_id"]
            if job_id in job_ids:
                raise ValueError(f"duplicate job ID {job_id} in: {path}")
            job_ids.add(job_id)

            submission_time = result["submission_time"]
            start_time = result["start_time"]
            completion_time = result["completion_time"]
            requested_runtime = result["requested_runtime"]
            requested_cpus = result["requested_cpus"]
            wait_time = result["wait_time"]

            if submission_time < 0:
                raise ValueError(
                    f"Job {job_id} has a negative submission time in: {path}"
                )
            if start_time < submission_time:
                raise ValueError(
                    f"Job {job_id} starts before submission in: {path}"
                )
            if completion_time < start_time:
                raise ValueError(
                    f"Job {job_id} completes before it starts in: {path}"
                )
            if requested_runtime < 0:
                raise ValueError(
                    f"Job {job_id} has a negative runtime in: {path}"
                )
            if completion_time - start_time != requested_runtime:
                raise ValueError(
                    f"Job {job_id} runtime does not match its start and "
                    f"completion times in: {path}"
                )
            if wait_time != start_time - submission_time:
                raise ValueError(
                    f"Job {job_id} stored wait time is inconsistent in: {path}"
                )
            if requested_cpus <= 0 or requested_cpus > total_cpus:
                raise ValueError(
                    f"Job {job_id} CPU request must be between 1 and "
                    f"{total_cpus} in: {path}"
                )

            results.append(result)

    if not results:
        raise ValueError(f"result file contains no job rows: {path}")

    return results


def workload_signature(results):
    return tuple(sorted(
        (
            result["job_id"],
            result["submission_time"],
            result["requested_runtime"],
            result["requested_cpus"],
        )
        for result in results
    ))


def calculate_metrics(results, total_cpus):
    validate_total_cpus(total_cpus)
    if not results:
        raise ValueError("cannot calculate metrics for an empty result set")

    wait_times = [result["wait_time"] for result in results]
    turnaround_times = [
        result["completion_time"] - result["submission_time"]
        for result in results
    ]

    earliest_submission = min(
        result["submission_time"] for result in results
    )
    latest_completion = max(
        result["completion_time"] for result in results
    )
    # Makespan is the measured interval from the first submission to the final
    # completion, so idle time before the workload begins is not included.
    makespan = latest_completion - earliest_submission
    if makespan <= 0:
        raise ValueError("measurement duration must be greater than zero")

    sorted_wait_times = sorted(wait_times)
    # Nearest-rank p95 uses the value at 1-based rank ceil(0.95 * N).
    p95_rank = math.ceil(0.95 * len(sorted_wait_times))
    p95_wait = sorted_wait_times[p95_rank - 1]

    busy_cpu_time = sum(
        result["requested_cpus"] * result["requested_runtime"]
        for result in results
    )
    available_cpu_time = total_cpus * makespan

    return {
        "jobs_completed": len(results),
        "average_wait": float(statistics.mean(wait_times)),
        "median_wait": float(statistics.median(wait_times)),
        "p95_wait": p95_wait,
        "average_turnaround": float(statistics.mean(turnaround_times)),
        "throughput": len(results) / makespan,
        "cpu_utilization_percent": 100 * busy_cpu_time / available_cpu_time,
    }


def analyze_result_files(labeled_paths, total_cpus):
    validate_total_cpus(total_cpus)

    summaries = []
    labels = set()
    expected_workload = None

    for label, path in labeled_paths:
        if label in labels:
            raise ValueError(f"duplicate result label: {label}")
        labels.add(label)

        results = read_result_file(path, total_cpus)
        signature = workload_signature(results)

        if expected_workload is None:
            expected_workload = signature
        elif signature != expected_workload:
            raise ValueError(
                f"result file '{path}' does not represent the same workload"
            )

        summary = calculate_metrics(results, total_cpus)
        summary["policy"] = label
        summaries.append(summary)

    return summaries


def format_summary_value(column, value):
    if column in {"policy", "jobs_completed", "p95_wait"}:
        return str(value)
    return f"{value:.6f}"


def print_summary_table(summaries):
    rows = [
        [format_summary_value(column, summary[column]) for column in SUMMARY_HEADER]
        for summary in summaries
    ]
    widths = [
        max(len(column), *(len(row[index]) for row in rows))
        for index, column in enumerate(SUMMARY_HEADER)
    ]

    print("  ".join(
        column.ljust(widths[index])
        for index, column in enumerate(SUMMARY_HEADER)
    ))
    for row in rows:
        print("  ".join(
            value.ljust(widths[index])
            for index, value in enumerate(row)
        ))


def write_summary_csv(output_path, summaries):
    try:
        with output_path.open("w", encoding="utf-8", newline="") as output_file:
            writer = csv.writer(output_file, lineterminator="\n")
            writer.writerow(SUMMARY_HEADER)
            for summary in summaries:
                writer.writerow([
                    format_summary_value(column, summary[column])
                    for column in SUMMARY_HEADER
                ])
    except OSError as error:
        raise ValueError(
            f"could not write summary file '{output_path}': {error}"
        ) from error


def parse_arguments():
    parser = argparse.ArgumentParser(
        description="Calculate summary metrics from scheduler result CSV files."
    )
    parser.add_argument("--total-cpus", type=positive_integer, required=True)
    parser.add_argument(
        "--result",
        type=parse_labeled_result,
        action="append",
        required=True,
        metavar="LABEL=PATH",
    )
    parser.add_argument("--output", type=Path)
    return parser.parse_args()


def main():
    arguments = parse_arguments()

    try:
        summaries = analyze_result_files(arguments.result, arguments.total_cpus)
        print_summary_table(summaries)
        if arguments.output is not None:
            write_summary_csv(arguments.output, summaries)
    except ValueError as error:
        print(f"Error: {error}", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
