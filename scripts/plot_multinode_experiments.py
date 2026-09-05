#!/usr/bin/env python3

import argparse
import csv
import math
import sys
from pathlib import Path

import run_multinode_experiments


PLOT_SPECS = (
    (
        "average_wait",
        "Mean average wait by cluster shape",
        "Wait time (simulated time units)",
        "average_wait.png",
    ),
    (
        "p95_wait",
        "Mean p95 wait by cluster shape",
        "Wait time (simulated time units)",
        "p95_wait.png",
    ),
    (
        "cpu_utilization_percent",
        "Mean CPU utilization by cluster shape",
        "CPU utilization (%)",
        "cpu_utilization.png",
    ),
)

POLICY_COLORS = {
    "fcfs": "#4C78A8",
    "sjf": "#F58518",
    "backfill": "#54A24B",
}

STRING_COLUMNS = {"load_condition", "cluster_shape", "policy"}
INTEGER_COLUMNS = {
    "submission_time_scale",
    "node_count",
    "cpus_per_node",
    "total_cpus",
    "seed_count",
}


def read_summary(path):
    try:
        input_file = path.open(encoding="utf-8", newline="")
    except OSError as error:
        raise ValueError(
            f"could not open aggregate CSV '{path}': {error}"
        ) from error

    with input_file:
        reader = csv.DictReader(input_file)
        if reader.fieldnames != run_multinode_experiments.SUMMARY_HEADER:
            raise ValueError(f"unexpected aggregate CSV header in: {path}")

        rows = []
        seen = set()
        condition_factors = dict(
            run_multinode_experiments.LOAD_CONDITIONS
        )
        shape_by_label = {
            shape.label: shape
            for shape in run_multinode_experiments.CLUSTER_SHAPES
        }

        for line_number, row in enumerate(reader, start=2):
            if None in row or any(
                row[column] is None
                for column in run_multinode_experiments.SUMMARY_HEADER
            ):
                raise ValueError(
                    f"malformed aggregate row on line {line_number} in: {path}"
                )

            try:
                parsed_row = {}
                for column in run_multinode_experiments.SUMMARY_HEADER:
                    value = row[column]
                    if column in STRING_COLUMNS:
                        parsed_row[column] = value
                    elif column in INTEGER_COLUMNS:
                        parsed_row[column] = int(value)
                    else:
                        parsed_row[column] = float(value)
            except (TypeError, ValueError) as error:
                raise ValueError(
                    f"non-numeric aggregate value on line {line_number} "
                    f"in: {path}"
                ) from error

            numeric_values = (
                value
                for column, value in parsed_row.items()
                if column not in STRING_COLUMNS
            )
            if not all(math.isfinite(value) for value in numeric_values):
                raise ValueError(
                    f"non-finite aggregate value on line {line_number} "
                    f"in: {path}"
                )

            condition = parsed_row["load_condition"]
            shape_label = parsed_row["cluster_shape"]
            policy = parsed_row["policy"]
            node_count = parsed_row["node_count"]
            cpus_per_node = parsed_row["cpus_per_node"]
            key = (
                condition,
                shape_label,
                node_count,
                cpus_per_node,
                policy,
            )

            if key in seen:
                raise ValueError(
                    "duplicate aggregate row for "
                    f"{condition}/{shape_label}/{policy} "
                    f"in: {path}"
                )
            seen.add(key)

            if condition not in condition_factors:
                raise ValueError(
                    f"unexpected load condition on line {line_number} "
                    f"in: {path}"
                )
            if policy not in run_multinode_experiments.POLICIES:
                raise ValueError(
                    f"unexpected policy on line {line_number} in: {path}"
                )
            shape = shape_by_label.get(shape_label)
            if shape is None:
                raise ValueError(
                    f"unexpected cluster shape on line {line_number} in: {path}"
                )
            if (node_count, cpus_per_node) != (
                shape.node_count,
                shape.cpus_per_node,
            ):
                raise ValueError(
                    f"incorrect dimensions for cluster shape on line "
                    f"{line_number} in: {path}"
                )
            if (
                parsed_row["submission_time_scale"]
                != condition_factors[condition]
            ):
                raise ValueError(
                    f"incorrect scale factor on line {line_number} in: {path}"
                )
            if (
                parsed_row["total_cpus"]
                != run_multinode_experiments.TOTAL_CPUS
                or node_count * cpus_per_node
                != run_multinode_experiments.TOTAL_CPUS
            ):
                raise ValueError(
                    f"incorrect total CPU count on line {line_number} in: {path}"
                )
            if parsed_row["seed_count"] != len(
                run_multinode_experiments.SEEDS
            ):
                raise ValueError(
                    f"incorrect seed count on line {line_number} in: {path}"
                )

            for column, value in parsed_row.items():
                if column.endswith("_std") and value < 0:
                    raise ValueError(
                        f"negative sample standard deviation on line "
                        f"{line_number} in: {path}"
                    )

            utilization = parsed_row["cpu_utilization_percent_mean"]
            if utilization < 0 or utilization > 100:
                raise ValueError(
                    f"CPU utilization outside 0-100 on line "
                    f"{line_number} in: {path}"
                )

            rows.append(parsed_row)

    expected = {
        (
            condition,
            shape.label,
            shape.node_count,
            shape.cpus_per_node,
            policy,
        )
        for condition, _scale_factor in (
            run_multinode_experiments.LOAD_CONDITIONS
        )
        for shape in run_multinode_experiments.CLUSTER_SHAPES
        for policy in run_multinode_experiments.POLICIES
    }
    if seen != expected:
        raise ValueError(
            f"aggregate CSV must contain all {len(expected)} "
            "condition/cluster-shape/policy combinations"
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
        (
            row["load_condition"],
            row["cluster_shape"],
            row["node_count"],
            row["cpus_per_node"],
            row["policy"],
        ): row
        for row in rows
    }
    conditions = [
        condition
        for condition, _scale_factor in (
            run_multinode_experiments.LOAD_CONDITIONS
        )
    ]
    shapes = list(run_multinode_experiments.CLUSTER_SHAPES)
    shape_labels = [
        f"{shape.node_count}\N{MULTIPLICATION SIGN}{shape.cpus_per_node}"
        for shape in shapes
    ]
    x_positions = list(range(len(shapes)))
    bar_width = 0.24

    generated_paths = []
    for metric_name, title, y_label, filename in PLOT_SPECS:
        share_y_axis = metric_name == "cpu_utilization_percent"
        figure, axes = pyplot.subplots(
            1,
            len(conditions),
            figsize=(15, 5),
            sharey=share_y_axis,
        )

        for condition_index, condition in enumerate(conditions):
            axis = axes[condition_index]

            for policy_index, policy in enumerate(
                run_multinode_experiments.POLICIES
            ):
                offset = (policy_index - 1) * bar_width
                means = [
                    row_by_key[
                        (
                            condition,
                            shape.label,
                            shape.node_count,
                            shape.cpus_per_node,
                            policy,
                        )
                    ][f"{metric_name}_mean"]
                    for shape in shapes
                ]
                sample_stds = [
                    row_by_key[
                        (
                            condition,
                            shape.label,
                            shape.node_count,
                            shape.cpus_per_node,
                            policy,
                        )
                    ][f"{metric_name}_std"]
                    for shape in shapes
                ]
                axis.bar(
                    [position + offset for position in x_positions],
                    means,
                    width=bar_width,
                    yerr=sample_stds,
                    capsize=4,
                    label=(
                        policy.upper()
                        if policy != "backfill"
                        else "Backfill"
                    ),
                    color=POLICY_COLORS[policy],
                    edgecolor="white",
                    linewidth=0.6,
                )

            axis.set_title(condition.title())
            axis.set_xlabel(
                "Cluster shape (nodes \N{MULTIPLICATION SIGN} CPUs per node)"
            )
            axis.set_xticks(x_positions, shape_labels)
            axis.set_ylabel(y_label)
            if share_y_axis:
                axis.set_ylim(0, 100)
            elif all(
                row_by_key[
                    (
                        condition,
                        shape.label,
                        shape.node_count,
                        shape.cpus_per_node,
                        policy,
                    )
                ][f"{metric_name}_{suffix}"] == 0
                for shape in shapes
                for policy in run_multinode_experiments.POLICIES
                for suffix in ("mean", "std")
            ):
                axis.set_ylim(0, 1)
                axis.text(
                    0.5,
                    0.5,
                    "All means and standard deviations are 0",
                    ha="center",
                    va="center",
                    transform=axis.transAxes,
                )
            else:
                axis.set_ylim(bottom=0)
            axis.grid(axis="y", alpha=0.25)

        handles, labels = axes[0].get_legend_handles_labels()
        figure.suptitle(title)
        figure.legend(
            handles,
            labels,
            loc="upper center",
            bbox_to_anchor=(0.5, 0.94),
            ncol=len(run_multinode_experiments.POLICIES),
            frameon=False,
        )
        figure.tight_layout(rect=(0, 0, 1, 0.88))

        output_path = output_directory / filename
        figure.savefig(output_path, dpi=160)
        pyplot.close(figure)
        generated_paths.append(output_path)

    return generated_paths


def parse_arguments():
    parser = argparse.ArgumentParser(
        description="Plot aggregate multi-node experiment metrics."
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

    for output_path in generated_paths:
        print(f"Wrote {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
