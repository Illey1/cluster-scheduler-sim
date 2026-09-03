import csv
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIRECTORY = REPOSITORY_ROOT / "scripts"
ANALYZER = SCRIPTS_DIRECTORY / "analyze_results.py"
sys.path.insert(0, str(SCRIPTS_DIRECTORY))

import analyze_results


HAND_CALCULABLE_ROWS = [
    [1, 0, 0, 10, 10, 4, 0],
    [2, 1, 10, 14, 4, 4, 9],
    [3, 2, 10, 12, 2, 2, 8],
]


def write_result_csv(path, rows, header=None):
    with path.open("w", encoding="utf-8", newline="") as output_file:
        writer = csv.writer(output_file, lineterminator="\n")
        writer.writerow(header or analyze_results.RESULT_HEADER)
        writer.writerows(rows)


class AnalyzeResultsTests(unittest.TestCase):
    def test_hand_calculable_metrics(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            path = Path(temporary_directory) / "results.csv"
            write_result_csv(path, HAND_CALCULABLE_ROWS)

            rows = analyze_results.read_result_file(path, 8)
            metrics = analyze_results.calculate_metrics(rows, 8)

            self.assertEqual(metrics["jobs_completed"], 3)
            self.assertAlmostEqual(metrics["average_wait"], 17 / 3)
            self.assertEqual(metrics["median_wait"], 8)
            self.assertEqual(metrics["p95_wait"], 9)
            self.assertEqual(metrics["average_turnaround"], 11)
            self.assertAlmostEqual(metrics["throughput"], 3 / 14)
            self.assertAlmostEqual(
                metrics["cpu_utilization_percent"], 100 * 60 / 112
            )

    def test_same_workload_files_are_accepted(self):
        alternate_schedule = [
            [1, 0, 0, 10, 10, 4, 0],
            [3, 2, 10, 12, 2, 2, 8],
            [2, 1, 12, 16, 4, 4, 11],
        ]

        with tempfile.TemporaryDirectory() as temporary_directory:
            first_path = Path(temporary_directory) / "first.csv"
            second_path = Path(temporary_directory) / "second.csv"
            write_result_csv(first_path, HAND_CALCULABLE_ROWS)
            write_result_csv(second_path, alternate_schedule)

            summaries = analyze_results.analyze_result_files(
                [("first", first_path), ("second", second_path)], 8
            )

            self.assertEqual([summary["policy"] for summary in summaries],
                             ["first", "second"])

    def test_different_workloads_are_rejected(self):
        different_workload = [row.copy() for row in HAND_CALCULABLE_ROWS]
        different_workload[2][5] = 4

        with tempfile.TemporaryDirectory() as temporary_directory:
            first_path = Path(temporary_directory) / "first.csv"
            second_path = Path(temporary_directory) / "second.csv"
            write_result_csv(first_path, HAND_CALCULABLE_ROWS)
            write_result_csv(second_path, different_workload)

            with self.assertRaisesRegex(ValueError, "same workload"):
                analyze_results.analyze_result_files(
                    [("first", first_path), ("second", second_path)], 8
                )

    def test_inconsistent_wait_time_is_rejected(self):
        rows = [HAND_CALCULABLE_ROWS[1].copy()]
        rows[0][6] = 8

        with tempfile.TemporaryDirectory() as temporary_directory:
            path = Path(temporary_directory) / "results.csv"
            write_result_csv(path, rows)

            with self.assertRaisesRegex(ValueError, "wait time is inconsistent"):
                analyze_results.read_result_file(path, 8)

    def test_runtime_completion_inconsistency_is_rejected(self):
        rows = [HAND_CALCULABLE_ROWS[1].copy()]
        rows[0][4] = 5

        with tempfile.TemporaryDirectory() as temporary_directory:
            path = Path(temporary_directory) / "results.csv"
            write_result_csv(path, rows)

            with self.assertRaisesRegex(ValueError, "runtime does not match"):
                analyze_results.read_result_file(path, 8)

    def test_duplicate_job_ids_are_rejected(self):
        rows = [HAND_CALCULABLE_ROWS[0], HAND_CALCULABLE_ROWS[0]]

        with tempfile.TemporaryDirectory() as temporary_directory:
            path = Path(temporary_directory) / "results.csv"
            write_result_csv(path, rows)

            with self.assertRaisesRegex(ValueError, "duplicate job ID 1"):
                analyze_results.read_result_file(path, 8)

    def test_empty_result_data_is_rejected(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            path = Path(temporary_directory) / "results.csv"
            write_result_csv(path, [])

            with self.assertRaisesRegex(ValueError, "contains no job rows"):
                analyze_results.read_result_file(path, 8)

    def test_invalid_total_cpu_count_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "greater than zero"):
            analyze_results.calculate_metrics([], 0)

    def test_nonpositive_measurement_duration_is_rejected(self):
        rows = [dict(zip(
            analyze_results.RESULT_HEADER,
            [1, 0, 0, 0, 0, 1, 0],
        ))]

        with self.assertRaisesRegex(ValueError, "duration.*greater than zero"):
            analyze_results.calculate_metrics(rows, 8)

    def test_incorrect_header_is_rejected(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            path = Path(temporary_directory) / "results.csv"
            write_result_csv(path, HAND_CALCULABLE_ROWS, ["job_id", "wait_time"])

            with self.assertRaisesRegex(ValueError, "unexpected result header"):
                analyze_results.read_result_file(path, 8)

    def test_noninteger_field_is_rejected(self):
        rows = [HAND_CALCULABLE_ROWS[0].copy()]
        rows[0][2] = "later"

        with tempfile.TemporaryDirectory() as temporary_directory:
            path = Path(temporary_directory) / "results.csv"
            write_result_csv(path, rows)

            with self.assertRaisesRegex(ValueError, "all fields must be integers"):
                analyze_results.read_result_file(path, 8)

    def test_invalid_cpu_request_is_rejected(self):
        rows = [HAND_CALCULABLE_ROWS[0].copy()]
        rows[0][5] = 9

        with tempfile.TemporaryDirectory() as temporary_directory:
            path = Path(temporary_directory) / "results.csv"
            write_result_csv(path, rows)

            with self.assertRaisesRegex(ValueError, "between 1 and 8"):
                analyze_results.read_result_file(path, 8)

    def test_duplicate_labels_are_rejected(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            path = Path(temporary_directory) / "results.csv"
            write_result_csv(path, HAND_CALCULABLE_ROWS)

            with self.assertRaisesRegex(ValueError, "duplicate result label"):
                analyze_results.analyze_result_files(
                    [("same", path), ("same", path)], 8
                )

    def test_cli_writes_summary_csv(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            result_path = Path(temporary_directory) / "results.csv"
            summary_path = Path(temporary_directory) / "summary.csv"
            write_result_csv(result_path, HAND_CALCULABLE_ROWS)

            process = subprocess.run(
                [
                    sys.executable,
                    str(ANALYZER),
                    "--total-cpus",
                    "8",
                    "--result",
                    f"test={result_path}",
                    "--output",
                    str(summary_path),
                ],
                capture_output=True,
                text=True,
                check=False,
            )

            self.assertEqual(process.returncode, 0, process.stderr)
            with summary_path.open(encoding="utf-8", newline="") as input_file:
                rows = list(csv.reader(input_file))
            self.assertEqual(rows[0], analyze_results.SUMMARY_HEADER)
            self.assertEqual(rows[1][0], "test")


if __name__ == "__main__":
    unittest.main()
