#pragma once

#include "job.h"
#include "job_result.h"

#include <iosfwd>
#include <vector>

struct SimulationResult {
    std::vector<JobResult> job_results;
    int final_time;
    int available_cpus;
};

SimulationResult run_simulation(const std::vector<Job>& jobs, int total_cpus,
                                std::ostream& event_log);
