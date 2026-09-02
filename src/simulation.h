#pragma once

#include "job.h"
#include "job_result.h"

#include <iosfwd>
#include <string>
#include <vector>

enum class SchedulingPolicy {
    Fcfs,
    ShortestJobFirst
};

struct SimulationResult {
    std::vector<JobResult> job_results;
    int final_time;
    int available_cpus;
};

SchedulingPolicy parse_scheduling_policy(const std::string& policy_name);

SimulationResult run_simulation(const std::vector<Job>& jobs, int total_cpus,
                                std::ostream& event_log,
                                SchedulingPolicy policy =
                                    SchedulingPolicy::Fcfs);
