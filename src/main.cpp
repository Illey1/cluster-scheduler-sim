#include "csv_io.h"
#include "job.h"
#include "simulation.h"

#include <exception>
#include <iostream>
#include <vector>

int main(int argc, char* argv[]) {
    if (argc != 3 && argc != 4) {
        std::cerr << "Usage: " << argv[0]
                  << " <workload.csv> <results.csv> [fcfs|sjf|backfill]\n";
        return 1;
    }

    try {
        const SchedulingPolicy policy = argc == 4
            ? parse_scheduling_policy(argv[3])
            : SchedulingPolicy::Fcfs;
        const std::vector<Job> jobs = read_jobs_from_csv(argv[1]);
        const SimulationResult simulation =
            run_simulation(jobs, 8, std::cout, policy);

        std::cout << "Simulation finished at time " << simulation.final_time
                  << "; " << simulation.available_cpus << "/8"
                  << " CPUs available\n";

        write_results_to_csv(argv[2], simulation.job_results);
        std::cout << "Wrote " << simulation.job_results.size()
                  << " job results to "
                  << argv[2] << '\n';
    } catch (const std::exception& error) {
        std::cerr << "Error: " << error.what() << '\n';
        return 1;
    }

    return 0;
}
