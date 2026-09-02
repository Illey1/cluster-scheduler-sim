import csv
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
GENERATOR = REPOSITORY_ROOT / "scripts" / "generate_workload.py"
EXPECTED_HEADER = [
    "job_id",
    "submission_time",
    "requested_runtime",
    "requested_cpus",
]


def run_generator(job_count, seed, output_path):
    return subprocess.run(
        [
            sys.executable,
            str(GENERATOR),
            "--jobs",
            str(job_count),
            "--seed",
            str(seed),
            "--output",
            str(output_path),
        ],
        capture_output=True,
        text=True,
        check=False,
    )


class WorkloadGeneratorTests(unittest.TestCase):
    def test_generated_workload_has_valid_values(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            output_path = Path(temporary_directory) / "workload.csv"
            process = run_generator(50, 42, output_path)

            self.assertEqual(process.returncode, 0, process.stderr)

            with output_path.open(encoding="utf-8", newline="") as input_file:
                reader = csv.DictReader(input_file)
                rows = list(reader)

            self.assertEqual(reader.fieldnames, EXPECTED_HEADER)
            self.assertEqual(len(rows), 50)

            job_ids = [int(row["job_id"]) for row in rows]
            submission_times = [int(row["submission_time"]) for row in rows]
            runtimes = [int(row["requested_runtime"]) for row in rows]
            cpu_requests = [int(row["requested_cpus"]) for row in rows]

            self.assertEqual(job_ids, list(range(1, 51)))
            self.assertEqual(len(job_ids), len(set(job_ids)))
            self.assertTrue(all(time >= 0 for time in submission_times))
            self.assertEqual(submission_times, sorted(submission_times))
            self.assertTrue(all(1 <= runtime <= 20 for runtime in runtimes))
            self.assertTrue(all(cpus in {1, 2, 4, 8} for cpus in cpu_requests))

    def test_same_seed_produces_identical_bytes(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            first_path = Path(temporary_directory) / "first.csv"
            second_path = Path(temporary_directory) / "second.csv"

            first_process = run_generator(25, 123, first_path)
            second_process = run_generator(25, 123, second_path)

            self.assertEqual(first_process.returncode, 0, first_process.stderr)
            self.assertEqual(second_process.returncode, 0, second_process.stderr)
            self.assertEqual(first_path.read_bytes(), second_path.read_bytes())

    def test_nonpositive_job_count_is_rejected(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            output_path = Path(temporary_directory) / "workload.csv"
            process = run_generator(0, 42, output_path)

            self.assertNotEqual(process.returncode, 0)
            self.assertIn("--jobs must be greater than zero", process.stderr)
            self.assertFalse(output_path.exists())

    def test_unusable_output_path_reports_error(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            output_path = (
                Path(temporary_directory) / "missing-directory" / "workload.csv"
            )
            process = run_generator(10, 42, output_path)

            self.assertEqual(process.returncode, 1)
            self.assertIn("could not write workload", process.stderr)
            self.assertFalse(output_path.exists())


if __name__ == "__main__":
    unittest.main()
