#include "csv_io.h"
#include "event.h"
#include "simulation.h"

#include <filesystem>
#include <fstream>
#include <functional>
#include <iostream>
#include <queue>
#include <sstream>
#include <stdexcept>
#include <string>
#include <vector>

namespace {

void check(bool condition, const std::string& message) {
    if (!condition) {
        throw std::runtime_error(message);
    }
}

SimulationResult simulate(
    const std::vector<Job>& jobs, int total_cpus,
    SchedulingPolicy policy = SchedulingPolicy::Fcfs) {
    std::ostringstream ignored_log;
    return run_simulation(jobs, total_cpus, ignored_log, policy);
}

const JobResult& find_result(const SimulationResult& simulation, int job_id) {
    for (const JobResult& result : simulation.job_results) {
        if (result.job.id() == job_id) {
            return result;
        }
    }

    throw std::runtime_error("missing result for Job "
                             + std::to_string(job_id));
}

void check_times(const SimulationResult& simulation, int job_id,
                 int start_time, int completion_time, int wait_time) {
    const JobResult& result = find_result(simulation, job_id);
    check(result.start_time == start_time,
          "unexpected start time for Job " + std::to_string(job_id));
    check(result.completion_time == completion_time,
          "unexpected completion time for Job " + std::to_string(job_id));
    check(result.wait_time() == wait_time,
          "unexpected wait time for Job " + std::to_string(job_id));
}

void expect_error_containing(const std::function<void()>& action,
                             const std::string& expected_text) {
    try {
        action();
    } catch (const std::exception& error) {
        check(std::string(error.what()).find(expected_text) != std::string::npos,
              "error did not contain: " + expected_text);
        return;
    }

    throw std::runtime_error("expected an exception containing: "
                             + expected_text);
}

std::filesystem::path write_test_csv(const std::string& name,
                                     const std::string& contents) {
    const std::filesystem::path path =
        std::filesystem::temp_directory_path() / name;
    std::ofstream output(path);
    check(static_cast<bool>(output), "could not create test CSV");
    output << contents;
    check(static_cast<bool>(output), "could not write test CSV");
    return path;
}

void test_idle_job_starts_immediately() {
    const SimulationResult simulation = simulate({Job(1, 5, 3, 2)}, 8);

    check_times(simulation, 1, 5, 8, 0);
}

void test_job_waits_until_cpus_are_released() {
    const SimulationResult simulation = simulate({
        Job(1, 0, 10, 8),
        Job(2, 2, 4, 4)
    }, 8);

    check_times(simulation, 2, 10, 14, 8);
}

void test_multiple_waiting_jobs_keep_fcfs_order() {
    const SimulationResult simulation = simulate({
        Job(1, 0, 4, 4),
        Job(2, 1, 5, 4),
        Job(3, 2, 1, 4)
    }, 4);

    check_times(simulation, 2, 4, 9, 3);
    check_times(simulation, 3, 9, 10, 7);
}

void test_head_of_line_blocking() {
    const SimulationResult simulation = simulate({
        Job(1, 0, 10, 6),
        Job(2, 1, 5, 8),
        Job(3, 2, 2, 2)
    }, 8);

    check_times(simulation, 2, 10, 15, 9);
    check_times(simulation, 3, 15, 17, 13);
}

void test_cpus_are_restored() {
    const SimulationResult simulation = simulate({
        Job(1, 0, 3, 4),
        Job(2, 0, 5, 4),
        Job(3, 1, 2, 4)
    }, 8);

    check(simulation.available_cpus == 8,
          "not all CPUs were restored");
}

void test_completion_precedes_same_time_arrival() {
    std::priority_queue<Event, std::vector<Event>, EventCompare> events;
    events.push({5, EventType::Arrival, Job(2, 5, 1, 4)});
    events.push({5, EventType::Completion, Job(1, 0, 5, 4)});

    check(events.top().type == EventType::Completion,
          "arrival was ordered before completion");

    const SimulationResult simulation = simulate({
        Job(1, 0, 5, 4),
        Job(2, 5, 1, 4)
    }, 4);
    check_times(simulation, 2, 5, 6, 0);
}

void test_same_time_arrivals_use_job_id() {
    const SimulationResult simulation = simulate({
        Job(2, 0, 1, 4),
        Job(1, 0, 5, 4)
    }, 4);

    check_times(simulation, 1, 0, 5, 0);
    check_times(simulation, 2, 5, 6, 5);
}

void test_oversized_job_is_rejected() {
    expect_error_containing([] {
        simulate({Job(7, 0, 1, 12)}, 8);
    }, "Job 7 requests 12 CPUs, exceeding node capacity of 8");
}

void test_duplicate_job_ids_are_rejected() {
    expect_error_containing([] {
        simulate({
            Job(3, 0, 1, 2),
            Job(3, 1, 1, 2)
        }, 8);
    }, "duplicate job ID: 3");
}

void test_zero_runtime_job_completes_deterministically() {
    const SimulationResult simulation = simulate({
        Job(2, 0, 2, 4),
        Job(1, 0, 0, 4)
    }, 4);

    check_times(simulation, 1, 0, 0, 0);
    check_times(simulation, 2, 0, 2, 0);
    check(simulation.available_cpus == 4,
          "zero-runtime job did not release its CPUs");
}

std::vector<Job> policy_comparison_workload() {
    return {
        Job(1, 0, 10, 8),
        Job(2, 1, 8, 8),
        Job(3, 2, 2, 8)
    };
}

void test_sjf_chooses_shorter_waiting_job() {
    const SimulationResult simulation = simulate(
        policy_comparison_workload(), 8,
        SchedulingPolicy::ShortestJobFirst);

    check_times(simulation, 3, 10, 12, 8);
    check_times(simulation, 2, 12, 20, 11);
}

void test_fcfs_and_sjf_produce_different_ordering() {
    const std::vector<Job> jobs = policy_comparison_workload();
    const SimulationResult fcfs = simulate(jobs, 8, SchedulingPolicy::Fcfs);
    const SimulationResult sjf = simulate(
        jobs, 8, SchedulingPolicy::ShortestJobFirst);

    check_times(fcfs, 2, 10, 18, 9);
    check_times(fcfs, 3, 18, 20, 16);
    check_times(sjf, 3, 10, 12, 8);
    check(find_result(fcfs, 3).start_time != find_result(sjf, 3).start_time,
          "FCFS and SJF produced the same ordering");
}

void test_sjf_runtime_tie_uses_submission_time() {
    const SimulationResult simulation = simulate({
        Job(1, 0, 10, 8),
        Job(2, 1, 3, 8),
        Job(3, 2, 3, 8)
    }, 8, SchedulingPolicy::ShortestJobFirst);

    check_times(simulation, 2, 10, 13, 9);
    check_times(simulation, 3, 13, 16, 11);
}

void test_sjf_runtime_and_submission_tie_uses_job_id() {
    const SimulationResult simulation = simulate({
        Job(3, 1, 3, 8),
        Job(1, 0, 10, 8),
        Job(2, 1, 3, 8)
    }, 8, SchedulingPolicy::ShortestJobFirst);

    check_times(simulation, 2, 10, 13, 9);
    check_times(simulation, 3, 13, 16, 12);
}

void test_sjf_does_not_skip_blocked_highest_priority_job() {
    const SimulationResult simulation = simulate({
        Job(1, 0, 10, 4),
        Job(2, 1, 2, 8),
        Job(3, 2, 5, 2)
    }, 8, SchedulingPolicy::ShortestJobFirst);

    check_times(simulation, 2, 10, 12, 9);
    check_times(simulation, 3, 12, 17, 10);
}

void test_sjf_restores_all_cpus() {
    const SimulationResult simulation = simulate(
        policy_comparison_workload(), 8,
        SchedulingPolicy::ShortestJobFirst);

    check(simulation.available_cpus == 8,
          "SJF did not restore all CPUs");
}

void test_policy_names_are_parsed_and_validated() {
    check(parse_scheduling_policy("fcfs") == SchedulingPolicy::Fcfs,
          "fcfs policy name was not parsed");
    check(parse_scheduling_policy("sjf")
              == SchedulingPolicy::ShortestJobFirst,
          "sjf policy name was not parsed");
    expect_error_containing([] {
        parse_scheduling_policy("unknown");
    }, "unknown scheduling policy: unknown");
}

void test_valid_csv_is_parsed() {
    const std::filesystem::path path = write_test_csv(
        "cluster-scheduler-valid.csv",
        "job_id,submission_time,requested_runtime,requested_cpus\n"
        "1,0,10,6\n"
        "2,2,4,4\n");

    const std::vector<Job> jobs = read_jobs_from_csv(path.string());
    std::filesystem::remove(path);

    check(jobs.size() == 2, "valid CSV did not produce two jobs");
    check(jobs[1].id() == 2 && jobs[1].submission_time() == 2
              && jobs[1].requested_runtime() == 4
              && jobs[1].requested_cpus() == 4,
          "valid CSV produced incorrect job values");
}

void test_malformed_csv_row_is_rejected() {
    const std::filesystem::path path = write_test_csv(
        "cluster-scheduler-malformed.csv",
        "job_id,submission_time,requested_runtime,requested_cpus\n"
        "1,0,broken,4\n");

    expect_error_containing([&path] {
        read_jobs_from_csv(path.string());
    }, "malformed workload row 2");
    std::filesystem::remove(path);
}

void test_incorrect_csv_header_is_rejected() {
    const std::filesystem::path path = write_test_csv(
        "cluster-scheduler-header.csv",
        "id,submission_time,requested_runtime,requested_cpus\n"
        "1,0,10,4\n");

    expect_error_containing([&path] {
        read_jobs_from_csv(path.string());
    }, "unexpected workload header");
    std::filesystem::remove(path);
}

void test_invalid_csv_values_are_rejected() {
    const std::filesystem::path path = write_test_csv(
        "cluster-scheduler-values.csv",
        "job_id,submission_time,requested_runtime,requested_cpus\n"
        "1,0,-1,4\n");

    expect_error_containing([&path] {
        read_jobs_from_csv(path.string());
    }, "invalid workload row 2");
    std::filesystem::remove(path);
}

struct TestCase {
    const char* name;
    void (*function)();
};

}  // namespace

int main() {
    const std::vector<TestCase> tests = {
        {"idle job starts immediately", test_idle_job_starts_immediately},
        {"job waits for released CPUs", test_job_waits_until_cpus_are_released},
        {"multiple waiting jobs keep FCFS order",
         test_multiple_waiting_jobs_keep_fcfs_order},
        {"head-of-line blocking", test_head_of_line_blocking},
        {"CPUs are restored", test_cpus_are_restored},
        {"completion precedes same-time arrival",
         test_completion_precedes_same_time_arrival},
        {"same-time arrivals use job ID", test_same_time_arrivals_use_job_id},
        {"oversized job is rejected", test_oversized_job_is_rejected},
        {"duplicate job IDs are rejected",
         test_duplicate_job_ids_are_rejected},
        {"zero-runtime job is deterministic",
         test_zero_runtime_job_completes_deterministically},
        {"SJF chooses shorter waiting job",
         test_sjf_chooses_shorter_waiting_job},
        {"FCFS and SJF produce different ordering",
         test_fcfs_and_sjf_produce_different_ordering},
        {"SJF runtime tie uses submission time",
         test_sjf_runtime_tie_uses_submission_time},
        {"SJF runtime and submission tie uses job ID",
         test_sjf_runtime_and_submission_tie_uses_job_id},
        {"SJF does not skip blocked highest-priority job",
         test_sjf_does_not_skip_blocked_highest_priority_job},
        {"SJF restores all CPUs", test_sjf_restores_all_cpus},
        {"policy names are parsed and validated",
         test_policy_names_are_parsed_and_validated},
        {"valid CSV is parsed", test_valid_csv_is_parsed},
        {"malformed CSV row is rejected",
         test_malformed_csv_row_is_rejected},
        {"incorrect CSV header is rejected",
         test_incorrect_csv_header_is_rejected},
        {"invalid CSV values are rejected",
         test_invalid_csv_values_are_rejected}
    };

    int failed_tests = 0;

    for (const TestCase& test : tests) {
        try {
            test.function();
            std::cout << "[PASS] " << test.name << '\n';
        } catch (const std::exception& error) {
            ++failed_tests;
            std::cerr << "[FAIL] " << test.name << ": "
                      << error.what() << '\n';
        }
    }

    if (failed_tests != 0) {
        std::cerr << failed_tests << " test(s) failed\n";
        return 1;
    }

    std::cout << tests.size() << " test(s) passed\n";
    return 0;
}
