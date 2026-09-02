#!/usr/bin/env python3

import argparse
import csv
import random
import sys
from pathlib import Path


HEADER = [
    "job_id",
    "submission_time",
    "requested_runtime",
    "requested_cpus",
]
CPU_CHOICES = [1, 2, 4, 8]


def positive_job_count(value):
    try:
        job_count = int(value)
    except ValueError as error:
        raise argparse.ArgumentTypeError("--jobs must be an integer") from error

    if job_count <= 0:
        raise argparse.ArgumentTypeError("--jobs must be greater than zero")

    return job_count


def generate_jobs(job_count, seed):
    random_generator = random.Random(seed)
    jobs = []
    submission_time = 0

    for job_id in range(1, job_count + 1):
        submission_time += random_generator.randint(0, 3)
        requested_runtime = random_generator.randint(1, 20)
        requested_cpus = random_generator.choice(CPU_CHOICES)

        jobs.append([
            job_id,
            submission_time,
            requested_runtime,
            requested_cpus,
        ])

    return jobs


def write_workload(output_path, jobs):
    with output_path.open("w", encoding="utf-8", newline="") as output_file:
        writer = csv.writer(output_file, lineterminator="\n")
        writer.writerow(HEADER)
        writer.writerows(jobs)


def parse_arguments():
    parser = argparse.ArgumentParser(
        description="Generate a synthetic workload for cluster-scheduler-sim."
    )
    parser.add_argument("--jobs", type=positive_job_count, required=True)
    parser.add_argument("--seed", type=int, required=True)
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args()


def main():
    arguments = parse_arguments()
    jobs = generate_jobs(arguments.jobs, arguments.seed)

    try:
        write_workload(arguments.output, jobs)
    except OSError as error:
        print(
            f"Error: could not write workload '{arguments.output}': {error}",
            file=sys.stderr,
        )
        return 1

    print(f"Wrote {arguments.jobs} jobs to {arguments.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
