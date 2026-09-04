#include "csv_io.h"
#include "job.h"
#include "simulation.h"

#include <exception>
#include <iostream>
#include <limits>
#include <stdexcept>
#include <string>
#include <vector>

namespace {

struct CommandLineOptions {
    std::string workload_path;
    std::string result_path;
    SchedulingPolicy policy = SchedulingPolicy::Fcfs;
    int node_count = 1;
    int cpus_per_node = 8;
};

int parse_positive_integer(const std::string& text,
                           const std::string& option_name) {
    std::size_t parsed_characters = 0;
    long long value = 0;

    try {
        value = std::stoll(text, &parsed_characters);
    } catch (const std::invalid_argument&) {
        throw std::invalid_argument(
            option_name + " must be a positive integer");
    } catch (const std::out_of_range&) {
        throw std::invalid_argument(
            option_name + " must be a positive integer");
    }

    if (parsed_characters != text.size() || value <= 0
        || value > std::numeric_limits<int>::max()) {
        throw std::invalid_argument(
            option_name + " must be a positive integer");
    }

    return static_cast<int>(value);
}

CommandLineOptions parse_arguments(int argc, char* argv[]) {
    CommandLineOptions options{argv[1], argv[2]};
    int next_argument = 3;

    if (next_argument < argc
        && std::string(argv[next_argument]).rfind("--", 0) != 0) {
        options.policy = parse_scheduling_policy(argv[next_argument]);
        ++next_argument;
    }

    while (next_argument < argc) {
        const std::string option_name = argv[next_argument];
        if (option_name != "--nodes" && option_name != "--cpus-per-node") {
            throw std::invalid_argument("unknown option: " + option_name);
        }
        if (next_argument + 1 >= argc) {
            throw std::invalid_argument(
                "missing value for option: " + option_name);
        }

        const int value = parse_positive_integer(
            argv[next_argument + 1], option_name);
        if (option_name == "--nodes") {
            options.node_count = value;
        } else {
            options.cpus_per_node = value;
        }
        next_argument += 2;
    }

    return options;
}

void print_usage(const char* program_name) {
    std::cerr << "Usage: " << program_name
              << " <workload.csv> <results.csv> [fcfs|sjf|backfill]"
              << " [--nodes N] [--cpus-per-node N]\n";
}

}  // namespace

int main(int argc, char* argv[]) {
    if (argc < 3) {
        print_usage(argv[0]);
        return 1;
    }

    try {
        const CommandLineOptions options = parse_arguments(argc, argv);
        const std::vector<Job> jobs = read_jobs_from_csv(options.workload_path);
        const SimulationResult simulation =
            run_simulation(jobs, options.node_count, options.cpus_per_node,
                           std::cout, options.policy);

        std::cout << "Simulation finished at time " << simulation.final_time
                  << "; " << simulation.available_cpus << '/'
                  << static_cast<long long>(options.node_count)
                         * options.cpus_per_node
                  << " CPUs available across " << options.node_count << ' '
                  << (options.node_count == 1 ? "node" : "nodes") << '\n';

        write_results_to_csv(options.result_path, simulation.job_results);
        std::cout << "Wrote " << simulation.job_results.size()
                  << " job results to "
                  << options.result_path << '\n';
    } catch (const std::exception& error) {
        std::cerr << "Error: " << error.what() << '\n';
        return 1;
    }

    return 0;
}
