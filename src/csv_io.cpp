#include "csv_io.h"

#include <fstream>
#include <sstream>
#include <stdexcept>
#include <string>

namespace {

const std::string workload_header =
    "job_id,submission_time,requested_runtime,requested_cpus";

void remove_trailing_carriage_return(std::string& line) {
    if (!line.empty() && line.back() == '\r') {
        line.pop_back();
    }
}

Job parse_job_row(const std::string& line, int line_number) {
    std::istringstream row(line);
    int job_id;
    int submission_time;
    int requested_runtime;
    int requested_cpus;
    char first_comma;
    char second_comma;
    char third_comma;

    if (!(row >> job_id >> first_comma
              >> submission_time >> second_comma
              >> requested_runtime >> third_comma
              >> requested_cpus)
        || first_comma != ','
        || second_comma != ','
        || third_comma != ',') {
        throw std::runtime_error(
            "malformed workload row " + std::to_string(line_number)
            + ": expected four comma-separated integers");
    }

    row >> std::ws;
    if (!row.eof()) {
        throw std::runtime_error(
            "malformed workload row " + std::to_string(line_number)
            + ": unexpected data after requested_cpus");
    }

    if (submission_time < 0 || requested_runtime < 0
        || requested_cpus <= 0) {
        throw std::runtime_error(
            "invalid workload row " + std::to_string(line_number)
            + ": times must be nonnegative and requested_cpus must be positive");
    }

    return Job(job_id, submission_time, requested_runtime, requested_cpus);
}

}  // namespace

std::vector<Job> read_jobs_from_csv(const std::string& input_path) {
    std::ifstream input(input_path);
    if (!input) {
        throw std::runtime_error("could not open workload file: " + input_path);
    }

    std::string header;
    if (!std::getline(input, header)) {
        throw std::runtime_error("workload file is empty: " + input_path);
    }

    remove_trailing_carriage_return(header);
    if (header != workload_header) {
        throw std::runtime_error(
            "unexpected workload header in: " + input_path);
    }

    std::vector<Job> jobs;
    std::string line;
    int line_number = 1;

    while (std::getline(input, line)) {
        ++line_number;
        remove_trailing_carriage_return(line);

        if (line.empty()) {
            continue;
        }

        jobs.push_back(parse_job_row(line, line_number));
    }

    if (!input.eof()) {
        throw std::runtime_error("could not read workload file: " + input_path);
    }

    return jobs;
}

void write_results_to_csv(const std::string& output_path,
                          const std::vector<JobResult>& results) {
    std::ofstream output(output_path);
    if (!output) {
        throw std::runtime_error("could not open result file: " + output_path);
    }

    output << "job_id,submission_time,start_time,completion_time,"
              "requested_runtime,requested_cpus,wait_time\n";

    for (const JobResult& result : results) {
        output << result.job.id() << ','
               << result.job.submission_time() << ','
               << result.start_time << ','
               << result.completion_time << ','
               << result.job.requested_runtime() << ','
               << result.job.requested_cpus() << ','
               << result.wait_time() << '\n';
    }

    if (!output) {
        throw std::runtime_error("could not write result file: " + output_path);
    }
}
