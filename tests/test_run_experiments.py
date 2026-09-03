import math
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIRECTORY = REPOSITORY_ROOT / "scripts"
EXPERIMENT_DRIVER = SCRIPTS_DIRECTORY / "run_experiments.py"
sys.path.insert(0, str(SCRIPTS_DIRECTORY))

import run_experiments


BASE_JOBS = [
    [1, 0, 3, 1],
    [2, 1, 4, 2],
    [3, 1, 5, 4],
    [4, 4, 6, 8],
]


def complete_run_rows():
    rows = []
    for seed in run_experiments.SEEDS:
        for condition, scale_factor in run_experiments.LOAD_CONDITIONS:
            for policy in run_experiments.POLICIES:
                rows.append({
                    "seed": seed,
                    "load_condition": condition,
                    "submission_time_scale": scale_factor,
                    "policy": policy,
                    "jobs_completed": run_experiments.JOB_COUNT,
                    "average_wait": float(seed),
                    "median_wait": float(seed + 1),
                    "p95_wait": seed + 2,
                    "average_turnaround": float(seed + 3),
                    "throughput": seed / 100,
                    "cpu_utilization_percent": float(seed + 50),
                })
    return rows


class ExperimentToolTests(unittest.TestCase):
    def test_scaling_changes_only_submission_times(self):
        scaled = run_experiments.scale_submission_times(BASE_JOBS, 8)

        self.assertEqual([job[1] for job in scaled], [0, 8, 8, 32])
        self.assertEqual(
            run_experiments.job_characteristics(scaled),
            run_experiments.job_characteristics(BASE_JOBS),
        )

    def test_scaling_preserves_runtimes_and_cpu_requests(self):
        scaled = run_experiments.scale_submission_times(BASE_JOBS, 4)

        self.assertEqual(
            [(job[2], job[3]) for job in scaled],
            [(job[2], job[3]) for job in BASE_JOBS],
        )

    def test_scaling_preserves_job_ids(self):
        scaled = run_experiments.scale_submission_times(BASE_JOBS, 2)

        self.assertEqual(
            [job[0] for job in scaled],
            [job[0] for job in BASE_JOBS],
        )

    def test_scaling_preserves_same_time_arrivals(self):
        scaled = run_experiments.scale_submission_times(BASE_JOBS, 8)

        self.assertEqual(scaled[1][1], scaled[2][1])

    def test_aggregation_calculates_mean(self):
        mean, _sample_std = run_experiments.mean_and_sample_std([1, 3, 8])

        self.assertEqual(mean, 4)

    def test_aggregation_calculates_sample_standard_deviation(self):
        _mean, sample_std = run_experiments.mean_and_sample_std([1, 3])

        self.assertAlmostEqual(sample_std, math.sqrt(2))

    def test_aggregation_contains_every_condition_and_policy(self):
        aggregate_rows = run_experiments.aggregate_run_metrics(
            complete_run_rows()
        )

        combinations = {
            (row["load_condition"], row["policy"])
            for row in aggregate_rows
        }
        expected = {
            (condition, policy)
            for condition, _factor in run_experiments.LOAD_CONDITIONS
            for policy in run_experiments.POLICIES
        }
        self.assertEqual(combinations, expected)
        self.assertEqual(len(aggregate_rows), 9)
        self.assertTrue(all(row["seed_count"] == 10 for row in aggregate_rows))

    def test_missing_simulator_is_rejected_cleanly(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            missing_simulator = Path(temporary_directory) / "missing-simulator"
            output_directory = Path(temporary_directory) / "output"
            process = subprocess.run(
                [
                    sys.executable,
                    str(EXPERIMENT_DRIVER),
                    "--simulator",
                    str(missing_simulator),
                    "--output-dir",
                    str(output_directory),
                ],
                capture_output=True,
                text=True,
                check=False,
            )

            self.assertEqual(process.returncode, 1)
            self.assertIn("simulator executable not found", process.stderr)
            self.assertFalse(output_directory.exists())


if __name__ == "__main__":
    unittest.main()
