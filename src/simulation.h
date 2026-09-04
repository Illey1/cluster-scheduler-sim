#pragma once

#include "job.h"
#include "job_result.h"

#include <iosfwd>
#include <string>
#include <vector>

enum class SchedulingPolicy {
    Fcfs,
    ShortestJobFirst,
    Backfill
};

struct SimulationResult {
    std::vector<JobResult> job_results;
    int final_time;
    long long available_cpus;
    std::vector<int> available_cpus_by_node;
};

SchedulingPolicy parse_scheduling_policy(const std::string& policy_name);

SimulationResult run_simulation(const std::vector<Job>& jobs, int total_cpus,
                                std::ostream& event_log,
                                SchedulingPolicy policy =
                                    SchedulingPolicy::Fcfs);

SimulationResult run_simulation(const std::vector<Job>& jobs, int node_count,
                                int cpus_per_node, std::ostream& event_log,
                                SchedulingPolicy policy =
                                    SchedulingPolicy::Fcfs);
