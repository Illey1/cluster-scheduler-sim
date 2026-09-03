#!/usr/bin/env python3

import argparse
import csv
import sys
from pathlib import Path

import run_experiments


PLOT_SPECS = (
    (
        "average_wait",
        "Mean average wait time",
        "Wait time (simulated time units)",
        "average_wait.png",
    ),
    (
        "p95_wait",
        "Mean p95 wait time",
        "Wait time (simulated time units)",
        "p95_wait.png",
    ),
    (
        "cpu_utilization_percent",
        "Mean CPU utilization",
        "CPU utilization (%)",
        "cpu_utilization.png",
    ),
)

POLICY_COLORS = {
    "fcfs": "#4C78A8",
    "sjf": "#F58518",
    "backfill": "#54A24B",
}


def read_summary(path):
    try:
        input_file = path.open(encoding="utf-8", newline="")
    except OSError as error:
        raise ValueError(f"could not open aggregate CSV '{path}': {error}") \
            from error

    with input_file:
        reader = csv.DictReader(input_file)
        if reader.fieldnames != run_experiments.SUMMARY_HEADER:
            raise ValueError(f"unexpected aggregate CSV header in: {path}")

        rows = []
        seen = set()

        for line_number, row in enumerate(reader, start=2):
            try:
                parsed_row = {
                    column: (
                        row[column]
                        if column in {"load_condition", "policy"}
                        else float(row[column])
                    )
                    for column in run_experiments.SUMMARY_HEADER
                }
            except (TypeError, ValueError) as error:
                raise ValueError(
                    f"non-numeric aggregate value on line {line_number} "
                    f"in: {path}"
                ) from error

            key = (parsed_row["load_condition"], parsed_row["policy"])
            if key in seen:
                raise ValueError(
                    f"duplicate aggregate row for {key[0]}/{key[1]} in: {path}"
                )
            seen.add(key)
            rows.append(parsed_row)

    expected = {
        (condition, policy)
        for condition, _scale_factor in run_experiments.LOAD_CONDITIONS
        for policy in run_experiments.POLICIES
    }
    if seen != expected:
        raise ValueError(
            f"aggregate CSV must contain all {len(expected)} "
            "condition/policy combinations"
        )

    return rows


def plot_summaries(rows, output_directory):
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as pyplot
    except ImportError as error:
        raise ValueError(
            "plotting requires matplotlib; install the documented dependency"
        ) from error

    output_directory.mkdir(parents=True, exist_ok=True)
    row_by_key = {
        (row["load_condition"], row["policy"]): row
        for row in rows
    }
    condition_names = [
        condition for condition, _scale_factor in run_experiments.LOAD_CONDITIONS
    ]
    x_positions = list(range(len(condition_names)))
    bar_width = 0.24

    generated_paths = []
    for metric_name, title, y_label, filename in PLOT_SPECS:
        figure, axes = pyplot.subplots(figsize=(8, 5))

        for policy_index, policy in enumerate(run_experiments.POLICIES):
            offset = (policy_index - 1) * bar_width
            means = [
                row_by_key[(condition, policy)][f"{metric_name}_mean"]
                for condition in condition_names
            ]
            sample_stds = [
                row_by_key[(condition, policy)][f"{metric_name}_std"]
                for condition in condition_names
            ]
            axes.bar(
                [position + offset for position in x_positions],
                means,
                width=bar_width,
                yerr=sample_stds,
                capsize=4,
                label=policy.upper() if policy != "backfill" else "Backfill",
                color=POLICY_COLORS[policy],
                edgecolor="white",
                linewidth=0.6,
            )

        axes.set_title(title)
        axes.set_xlabel("Workload-pressure condition")
        axes.set_ylabel(y_label)
        axes.set_xticks(x_positions, [name.title() for name in condition_names])
        axes.set_ylim(bottom=0)
        axes.grid(axis="y", alpha=0.25)
        axes.legend(frameon=False)
        figure.tight_layout()

        output_path = output_directory / filename
        figure.savefig(output_path, dpi=160)
        pyplot.close(figure)
        generated_paths.append(output_path)

    return generated_paths


def parse_arguments():
    parser = argparse.ArgumentParser(
        description="Plot aggregate scheduler experiment metrics."
    )
    parser.add_argument("--summary", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    return parser.parse_args()


def main():
    arguments = parse_arguments()

    try:
        rows = read_summary(arguments.summary)
        generated_paths = plot_summaries(rows, arguments.output_dir)
    except (OSError, ValueError) as error:
        print(f"Error: {error}", file=sys.stderr)
        return 1

    for path in generated_paths:
        print(f"Wrote {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
