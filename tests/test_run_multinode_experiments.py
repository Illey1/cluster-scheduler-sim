import csv
import math
import statistics
import subprocess
import sys
import tempfile
import unittest
from collections import Counter
from pathlib import Path
from unittest import mock


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIRECTORY = REPOSITORY_ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS_DIRECTORY))

import generate_workload
import run_experiments
import run_multinode_experiments


BASE_JOBS = [
    [1, 0, 3, 1],
    [2, 1, 4, 2],
    [3, 1, 5, 4],
    [4, 4, 6, 8],
]


def complete_run_rows():
    rows = []
    for seed in run_multinode_experiments.SEEDS:
        for condition, scale_factor in (
            run_multinode_experiments.LOAD_CONDITIONS
        ):
            for shape in run_multinode_experiments.CLUSTER_SHAPES:
                for policy in run_multinode_experiments.POLICIES:
                    rows.append({
                        "seed": seed,
                        "load_condition": condition,
                        "submission_time_scale": scale_factor,
                        "cluster_shape": shape.label,
                        "node_count": shape.node_count,
                        "cpus_per_node": shape.cpus_per_node,
                        "total_cpus": shape.total_cpus,
                        "policy": policy,
                        "jobs_completed": (
                            run_multinode_experiments.JOB_COUNT
                        ),
                        "average_wait": float(seed),
                        "median_wait": float(seed + 1),
                        "p95_wait": seed + 2,
                        "average_turnaround": float(seed + 3),
                        "throughput": seed / 100,
                        "cpu_utilization_percent": float(seed + 50),
                    })
    return rows


class MultinodeExperimentConfigurationTests(unittest.TestCase):
    def test_cluster_shapes_have_exactly_32_aggregate_cpus(self):
        shapes = run_multinode_experiments.CLUSTER_SHAPES

        self.assertEqual(
            [
                (shape.label, shape.node_count, shape.cpus_per_node)
                for shape in shapes
            ],
            [("1x32", 1, 32), ("2x16", 2, 16), ("4x8", 4, 8)],
        )
        self.assertTrue(all(
            shape.total_cpus == run_multinode_experiments.TOTAL_CPUS == 32
            for shape in shapes
        ))
        run_multinode_experiments.validate_cluster_shapes()

    def test_invalid_cluster_capacity_is_rejected(self):
        invalid_shape = run_multinode_experiments.ClusterShape(
            "1x31", 1, 31
        )

        with self.assertRaisesRegex(ValueError, "expected 32"):
            run_multinode_experiments.validate_cluster_shapes(
                (invalid_shape,)
            )

    def test_all_generated_jobs_fit_an_empty_node_in_every_shape(self):
        for seed in run_multinode_experiments.SEEDS:
            with self.subTest(seed=seed):
                jobs = generate_workload.generate_jobs(
                    run_multinode_experiments.JOB_COUNT, seed
                )
                run_multinode_experiments.validate_jobs_fit_shapes(jobs)
                self.assertTrue(all(
                    job[3] <= shape.cpus_per_node
                    for job in jobs
                    for shape in run_multinode_experiments.CLUSTER_SHAPES
                ))

    def test_job_that_fits_total_capacity_but_not_smallest_node_is_rejected(self):
        jobs = [[1, 0, 1, 9]]

        with self.assertRaisesRegex(ValueError, "cannot fit an empty 4x8 node"):
            run_multinode_experiments.validate_jobs_fit_shapes(jobs)


class MultinodeWorkloadInvariantTests(unittest.TestCase):
    def test_same_seed_preserves_composition_across_conditions_and_shapes(self):
        matrix = run_multinode_experiments.build_workload_matrix(BASE_JOBS)
        expected = run_multinode_experiments.job_composition(BASE_JOBS)

        self.assertTrue(all(
            run_multinode_experiments.job_composition(jobs) == expected
            for jobs in matrix.values()
        ))

    def test_same_seed_and_load_preserve_submission_times_across_shapes(self):
        matrix = run_multinode_experiments.build_workload_matrix(BASE_JOBS)

        for condition, _scale_factor in (
            run_multinode_experiments.LOAD_CONDITIONS
        ):
            with self.subTest(condition=condition):
                signatures = {
                    run_multinode_experiments.job_workload_signature(
                        matrix[(condition, shape.label)]
                    )
                    for shape in run_multinode_experiments.CLUSTER_SHAPES
                }
                self.assertEqual(len(signatures), 1)

    def test_load_scale_factors_are_applied_exactly_from_the_base(self):
        original_jobs = [list(job) for job in BASE_JOBS]
        matrix = run_multinode_experiments.build_workload_matrix(BASE_JOBS)
        expected_submission_times = {
            "light": [0, 4, 4, 16],
            "moderate": [0, 2, 2, 8],
            "heavy": [0, 1, 1, 4],
        }

        for condition, expected_times in expected_submission_times.items():
            jobs = matrix[(
                condition,
                run_multinode_experiments.CLUSTER_SHAPES[0].label,
            )]
            self.assertEqual([job[1] for job in jobs], expected_times)
        self.assertEqual(BASE_JOBS, original_jobs)

    def test_changed_composition_is_rejected(self):
        matrix = run_multinode_experiments.build_workload_matrix(BASE_JOBS)
        changed_matrix = {
            key: [list(job) for job in jobs]
            for key, jobs in matrix.items()
        }
        changed_matrix[("moderate", "2x16")][0][2] += 1

        with self.assertRaisesRegex(ValueError, "job composition changed"):
            run_multinode_experiments.validate_workload_matrix(
                BASE_JOBS, changed_matrix
            )

    def test_incorrect_scaled_submission_time_is_rejected(self):
        matrix = run_multinode_experiments.build_workload_matrix(BASE_JOBS)
        changed_matrix = {
            key: [list(job) for job in jobs]
            for key, jobs in matrix.items()
        }
        changed_matrix[("light", "4x8")][1][1] += 1

        with self.assertRaisesRegex(ValueError, "not scaled by 4"):
            run_multinode_experiments.validate_workload_matrix(
                BASE_JOBS, changed_matrix
            )

    def test_incomplete_workload_matrix_is_rejected(self):
        matrix = run_multinode_experiments.build_workload_matrix(BASE_JOBS)
        del matrix[("heavy", "4x8")]

        with self.assertRaisesRegex(ValueError, "incomplete workload matrix"):
            run_multinode_experiments.validate_workload_matrix(
                BASE_JOBS, matrix
            )


class MultinodeRunMatrixTests(unittest.TestCase):
    def test_expected_matrix_contains_270_unique_runs(self):
        keys = run_multinode_experiments.expected_run_keys()
        expected = {
            (
                seed,
                condition,
                shape.label,
                shape.node_count,
                shape.cpus_per_node,
                policy,
            )
            for seed in range(1, 11)
            for condition in ("light", "moderate", "heavy")
            for shape in run_multinode_experiments.CLUSTER_SHAPES
            for policy in ("fcfs", "sjf", "backfill")
        }

        self.assertEqual(keys, expected)
        self.assertEqual(len(keys), 270)

    def test_complete_matrix_is_accepted(self):
        rows = complete_run_rows()

        self.assertEqual(len(rows), 270)
        run_multinode_experiments.validate_complete_design(rows)

    def test_missing_run_is_rejected(self):
        rows = complete_run_rows()
        rows.pop()

        with self.assertRaisesRegex(ValueError, "incomplete experiment design"):
            run_multinode_experiments.validate_complete_design(rows)

    def test_duplicate_run_is_rejected_even_when_row_count_is_270(self):
        rows = complete_run_rows()
        rows[-1] = dict(rows[0])

        self.assertEqual(len(rows), 270)
        with self.assertRaisesRegex(ValueError, "duplicate experiment row"):
            run_multinode_experiments.validate_complete_design(rows)

    def test_invalid_design_metadata_is_rejected(self):
        cases = (
            (
                "unexpected shape",
                {"cluster_shape": "8x4", "node_count": 8,
                 "cpus_per_node": 4},
                "unexpected cluster shape",
            ),
            (
                "wrong shape dimensions",
                {"node_count": 2, "cpus_per_node": 16},
                "incorrect dimensions",
            ),
            (
                "wrong total",
                {"total_cpus": 31},
                "incorrect total CPU count",
            ),
            (
                "wrong scale",
                {"submission_time_scale": 3},
                "incorrect scale factor",
            ),
            (
                "unknown condition",
                {"load_condition": "extreme"},
                "unexpected load condition",
            ),
            (
                "unknown policy",
                {"policy": "random"},
                "unexpected scheduling policy",
            ),
            (
                "incomplete jobs",
                {"jobs_completed": 199},
                "expected 200 completed jobs",
            ),
        )

        for name, changes, message in cases:
            with self.subTest(case=name):
                rows = complete_run_rows()
                rows[0].update(changes)
                with self.assertRaisesRegex(ValueError, message):
                    run_multinode_experiments.validate_complete_design(rows)

    def test_invalid_utilization_and_nonfinite_metrics_are_rejected(self):
        cases = (
            ("over 100", "cpu_utilization_percent", 100.000001,
             "outside"),
            ("negative", "cpu_utilization_percent", -0.000001,
             "outside"),
            ("nan", "average_wait", math.nan, "non-finite"),
            ("infinity", "throughput", math.inf, "non-finite"),
        )

        for name, column, value, message in cases:
            with self.subTest(case=name):
                rows = complete_run_rows()
                rows[0][column] = value
                with self.assertRaisesRegex(ValueError, message):
                    run_multinode_experiments.validate_complete_design(rows)

    def test_aggregation_produces_27_groups_with_all_ten_seeds(self):
        aggregate_rows = run_multinode_experiments.aggregate_run_metrics(
            complete_run_rows()
        )
        keys = {
            (
                row["load_condition"],
                row["cluster_shape"],
                row["node_count"],
                row["cpus_per_node"],
                row["policy"],
            )
            for row in aggregate_rows
        }

        self.assertEqual(len(aggregate_rows), 27)
        self.assertEqual(len(keys), 27)
        self.assertTrue(all(
            row["seed_count"] == 10 for row in aggregate_rows
        ))

    def test_aggregation_uses_sample_standard_deviation(self):
        aggregate_rows = run_multinode_experiments.aggregate_run_metrics(
            complete_run_rows()
        )
        first_group = aggregate_rows[0]

        self.assertEqual(first_group["average_wait_mean"], 5.5)
        self.assertAlmostEqual(
            first_group["average_wait_std"],
            statistics.stdev(range(1, 11)),
        )


class MultinodeOrchestrationTests(unittest.TestCase):
    def test_simulator_command_passes_policy_and_cluster_shape_flags(self):
        shape = run_multinode_experiments.CLUSTER_SHAPES[-1]
        completed_process = subprocess.CompletedProcess(
            args=[], returncode=0, stdout="", stderr=""
        )

        with mock.patch.object(
            run_multinode_experiments.subprocess,
            "run",
            return_value=completed_process,
        ) as run:
            run_multinode_experiments.run_simulator(
                Path("/simulator"),
                Path("/workload.csv"),
                Path("/results.csv"),
                "backfill",
                shape,
            )

        run.assert_called_once_with(
            [
                "/simulator",
                "/workload.csv",
                "/results.csv",
                "backfill",
                "--nodes",
                "4",
                "--cpus-per-node",
                "8",
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            text=True,
            check=False,
        )

    def test_result_analysis_compares_all_nine_shape_policy_outputs(self):
        expected_jobs = [[1, 0, 3, 1]]

        with tempfile.TemporaryDirectory() as temporary_directory:
            result_path = Path(temporary_directory) / "result.csv"
            with result_path.open(
                "w", encoding="utf-8", newline=""
            ) as output_file:
                writer = csv.writer(output_file, lineterminator="\n")
                writer.writerow(
                    run_multinode_experiments.analyze_results.RESULT_HEADER
                )
                writer.writerow([1, 0, 0, 3, 3, 1, 0])

            labeled_results = [
                (f"{shape.label}/{policy}", result_path)
                for shape in run_multinode_experiments.CLUSTER_SHAPES
                for policy in run_multinode_experiments.POLICIES
            ]
            summaries = run_multinode_experiments.analyze_result_matrix(
                labeled_results, expected_jobs
            )

        self.assertEqual(len(summaries), 9)
        self.assertEqual(
            {summary["policy"] for summary in summaries},
            {label for label, _path in labeled_results},
        )

    def test_result_analysis_rejects_output_that_differs_from_generated_jobs(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            result_path = Path(temporary_directory) / "result.csv"
            with result_path.open(
                "w", encoding="utf-8", newline=""
            ) as output_file:
                writer = csv.writer(output_file, lineterminator="\n")
                writer.writerow(
                    run_multinode_experiments.analyze_results.RESULT_HEADER
                )
                writer.writerow([1, 0, 0, 3, 3, 1, 0])

            with self.assertRaisesRegex(
                ValueError, "do not match the generated workload"
            ):
                run_multinode_experiments.analyze_result_matrix(
                    [("1x32/fcfs", result_path)],
                    [[1, 0, 3, 2]],
                )

    def test_orchestration_generates_once_per_seed_and_reuses_each_workload(self):
        metric_summary = {
            "jobs_completed": run_multinode_experiments.JOB_COUNT,
            "average_wait": 1.0,
            "median_wait": 1.0,
            "p95_wait": 1,
            "average_turnaround": 2.0,
            "throughput": 0.5,
            "cpu_utilization_percent": 50.0,
        }

        def summarize(labeled_results, _expected_jobs):
            return [
                {**metric_summary, "policy": label}
                for label, _path in labeled_results
            ]

        with tempfile.TemporaryDirectory() as temporary_directory:
            output_directory = Path(temporary_directory) / "output"
            with (
                mock.patch.object(
                    run_multinode_experiments,
                    "validate_simulator_executable",
                ),
                mock.patch.object(
                    run_multinode_experiments.generate_workload,
                    "generate_jobs",
                    return_value=[list(job) for job in BASE_JOBS],
                ) as generate_jobs,
                mock.patch.object(
                    run_multinode_experiments.generate_workload,
                    "write_workload",
                ),
                mock.patch.object(
                    run_multinode_experiments,
                    "run_simulator",
                ) as run_simulator,
                mock.patch.object(
                    run_multinode_experiments,
                    "analyze_result_matrix",
                    side_effect=summarize,
                ) as analyze_matrix,
                mock.patch.object(
                    run_multinode_experiments,
                    "write_rows",
                ),
            ):
                run_rows, aggregate_rows = (
                    run_multinode_experiments.run_experiment(
                        Path("/simulator"), output_directory
                    )
                )

        self.assertEqual(generate_jobs.call_count, 10)
        self.assertEqual(
            [call.args for call in generate_jobs.call_args_list],
            [(200, seed) for seed in range(1, 11)],
        )
        self.assertEqual(run_simulator.call_count, 270)
        self.assertEqual(analyze_matrix.call_count, 30)
        self.assertTrue(all(
            len(call.args[0]) == 9
            for call in analyze_matrix.call_args_list
        ))

        workload_paths = Counter(
            call.args[1] for call in run_simulator.call_args_list
        )
        self.assertEqual(len(workload_paths), 30)
        self.assertEqual(set(workload_paths.values()), {9})

        shape_policy_counts = Counter(
            (call.args[4].label, call.args[3])
            for call in run_simulator.call_args_list
        )
        self.assertEqual(len(shape_policy_counts), 9)
        self.assertEqual(set(shape_policy_counts.values()), {30})
        self.assertEqual(len(run_rows), 270)
        self.assertEqual(len(aggregate_rows), 27)


class MultinodeCsvContractTests(unittest.TestCase):
    def test_run_and_summary_schemas_are_exact(self):
        self.assertEqual(
            run_multinode_experiments.RUN_METRICS_HEADER,
            [
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
            ],
        )

        expected_summary_header = [
            "load_condition",
            "submission_time_scale",
            "cluster_shape",
            "node_count",
            "cpus_per_node",
            "total_cpus",
            "policy",
            "seed_count",
        ]
        for metric_name in run_multinode_experiments.AGGREGATED_METRICS:
            expected_summary_header.extend([
                f"{metric_name}_mean",
                f"{metric_name}_std",
            ])
        self.assertEqual(
            run_multinode_experiments.SUMMARY_HEADER,
            expected_summary_header,
        )

    def test_csv_formatting_keeps_dimensions_integral_and_metrics_fixed(self):
        run_row = complete_run_rows()[0]
        summary_row = run_multinode_experiments.aggregate_run_metrics(
            complete_run_rows()
        )[0]

        with tempfile.TemporaryDirectory() as temporary_directory:
            directory = Path(temporary_directory)
            run_path = directory / "runs.csv"
            summary_path = directory / "summary.csv"
            run_multinode_experiments.write_rows(
                run_path,
                run_multinode_experiments.RUN_METRICS_HEADER,
                [run_row],
            )
            run_multinode_experiments.write_rows(
                summary_path,
                run_multinode_experiments.SUMMARY_HEADER,
                [summary_row],
            )

            with run_path.open(encoding="utf-8", newline="") as input_file:
                written_run = next(csv.DictReader(input_file))
            with summary_path.open(
                encoding="utf-8", newline=""
            ) as input_file:
                written_summary = next(csv.DictReader(input_file))

        self.assertEqual(written_run["node_count"], "1")
        self.assertEqual(written_run["cpus_per_node"], "32")
        self.assertEqual(written_run["total_cpus"], "32")
        self.assertEqual(written_run["jobs_completed"], "200")
        self.assertEqual(written_run["average_wait"], "1.000000")
        self.assertEqual(written_summary["seed_count"], "10")
        self.assertEqual(written_summary["average_wait_mean"], "5.500000")
        self.assertEqual(written_summary["jobs_completed_mean"], "200.000000")


class OriginalExperimentCompatibilityTests(unittest.TestCase):
    def test_original_single_node_experiment_contract_is_unchanged(self):
        self.assertEqual(run_experiments.JOB_COUNT, 200)
        self.assertEqual(run_experiments.TOTAL_CPUS, 8)
        self.assertEqual(run_experiments.SEEDS, tuple(range(1, 11)))
        self.assertEqual(
            run_experiments.LOAD_CONDITIONS,
            (("light", 8), ("moderate", 4), ("heavy", 2)),
        )
        self.assertEqual(
            run_experiments.POLICIES,
            ("fcfs", "sjf", "backfill"),
        )
        original_design = {
            (seed, condition, policy)
            for seed in run_experiments.SEEDS
            for condition, _scale in run_experiments.LOAD_CONDITIONS
            for policy in run_experiments.POLICIES
        }
        self.assertEqual(len(original_design), 90)


if __name__ == "__main__":
    unittest.main()
