#include "simulation.h"

#include "event.h"
#include "node.h"

#include <algorithm>
#include <ostream>
#include <queue>
#include <set>
#include <stdexcept>
#include <string>
#include <utility>
#include <vector>

namespace {

using EventQueue = std::priority_queue<Event, std::vector<Event>, EventCompare>;

void validate_cluster_configuration(int node_count, int cpus_per_node) {
    if (node_count <= 0) {
        throw std::invalid_argument("node count must be positive");
    }

    if (cpus_per_node <= 0) {
        throw std::invalid_argument("CPUs per node must be positive");
    }
}

void validate_jobs(const std::vector<Job>& jobs, int cpus_per_node) {
    std::set<int> job_ids;

    for (const Job& job : jobs) {
        if (!job_ids.insert(job.id()).second) {
            throw std::invalid_argument(
                "duplicate job ID: " + std::to_string(job.id()));
        }

        if (job.submission_time() < 0 || job.requested_runtime() < 0
            || job.requested_cpus() <= 0) {
            throw std::invalid_argument(
                "Job " + std::to_string(job.id())
                + " has invalid time or CPU values");
        }

        if (job.requested_cpus() > cpus_per_node) {
            throw std::invalid_argument(
                "Job " + std::to_string(job.id()) + " requests "
                + std::to_string(job.requested_cpus())
                + " CPUs, exceeding node capacity of "
                + std::to_string(cpus_per_node));
        }
    }
}

void start_job(const Job& job, int current_time, Node& node,
               EventQueue& future_events,
               std::vector<JobResult>& job_results,
               std::ostream& event_log) {
    if (!node.allocate(job)) {
        throw std::logic_error(
            "could not allocate CPUs for Job " + std::to_string(job.id()));
    }

    const int completion_time = current_time + job.requested_runtime();

    event_log << "time " << current_time << ": Job " << job.id()
              << " started on node " << node.id() << "; "
              << node.available_cpus() << '/' << node.total_cpus()
              << " CPUs available on node\n";

    future_events.push({
        completion_time,
        EventType::Completion,
        job,
        node.id()
    });
    job_results.push_back({job, node.id(), current_time, completion_time});
}

bool has_higher_priority(const Job& left, const Job& right,
                         SchedulingPolicy policy) {
    if (policy == SchedulingPolicy::ShortestJobFirst
        && left.requested_runtime() != right.requested_runtime()) {
        return left.requested_runtime() < right.requested_runtime();
    }

    if (left.submission_time() != right.submission_time()) {
        return left.submission_time() < right.submission_time();
    }

    return left.id() < right.id();
}

std::vector<Job>::iterator highest_priority_job(
    std::vector<Job>& waiting_jobs, SchedulingPolicy policy) {
    return std::min_element(
        waiting_jobs.begin(), waiting_jobs.end(),
        [policy](const Job& left, const Job& right) {
            return has_higher_priority(left, right, policy);
        });
}

std::vector<Node>::iterator first_fitting_node(
    std::vector<Node>& nodes, const Job& job) {
    return std::find_if(
        nodes.begin(), nodes.end(),
        [&job](const Node& node) {
            return node.can_run(job);
        });
}

bool can_run_on_any_node(const Job& job, const std::vector<Node>& nodes) {
    return std::any_of(
        nodes.begin(), nodes.end(),
        [&job](const Node& node) {
            return node.can_run(job);
        });
}

std::vector<Job>::iterator first_fitting_fcfs_job(
    std::vector<Job>& waiting_jobs, const std::vector<Node>& nodes) {
    auto selected_job = waiting_jobs.end();

    // This greedy scan uses only current CPU availability; it does not reserve
    // a future start time for an earlier blocked job.
    for (auto job = waiting_jobs.begin(); job != waiting_jobs.end(); ++job) {
        if (can_run_on_any_node(*job, nodes)
            && (selected_job == waiting_jobs.end()
                || has_higher_priority(
                    *job, *selected_job, SchedulingPolicy::Fcfs))) {
            selected_job = job;
        }
    }

    return selected_job;
}

void start_waiting_jobs(std::vector<Job>& waiting_jobs, int current_time,
                        std::vector<Node>& nodes, EventQueue& future_events,
                        std::vector<JobResult>& job_results,
                        std::ostream& event_log,
                        SchedulingPolicy policy) {
    while (!waiting_jobs.empty()) {
        auto next_job = highest_priority_job(waiting_jobs, policy);
        auto target_node = first_fitting_node(nodes, *next_job);

        if (target_node == nodes.end()) {
            if (policy != SchedulingPolicy::Backfill) {
                break;
            }

            next_job = first_fitting_fcfs_job(waiting_jobs, nodes);
            if (next_job == waiting_jobs.end()) {
                break;
            }

            target_node = first_fitting_node(nodes, *next_job);
            if (target_node == nodes.end()) {
                throw std::logic_error(
                    "selected backfill job has no fitting node");
            }
        }

        const Job job = *next_job;
        waiting_jobs.erase(next_job);
        start_job(
            job, current_time, *target_node,
            future_events, job_results, event_log);
    }
}

}  // namespace

SchedulingPolicy parse_scheduling_policy(const std::string& policy_name) {
    if (policy_name == "fcfs") {
        return SchedulingPolicy::Fcfs;
    }

    if (policy_name == "sjf") {
        return SchedulingPolicy::ShortestJobFirst;
    }

    if (policy_name == "backfill") {
        return SchedulingPolicy::Backfill;
    }

    throw std::invalid_argument(
        "unknown scheduling policy: " + policy_name
        + " (expected fcfs, sjf, or backfill)");
}

SimulationResult run_simulation(const std::vector<Job>& jobs, int node_count,
                                int cpus_per_node,
                                std::ostream& event_log,
                                SchedulingPolicy policy) {
    validate_cluster_configuration(node_count, cpus_per_node);
    validate_jobs(jobs, cpus_per_node);

    std::vector<Node> nodes;
    nodes.reserve(static_cast<std::vector<Node>::size_type>(node_count));
    for (int node_id = 0; node_id < node_count; ++node_id) {
        nodes.emplace_back(node_id, cpus_per_node);
    }

    EventQueue future_events;
    for (const Job& job : jobs) {
        future_events.push({
            job.submission_time(),
            EventType::Arrival,
            job
        });
    }

    std::vector<Job> waiting_jobs;
    std::vector<JobResult> job_results;
    int current_time = 0;

    while (!future_events.empty()) {
        const Event event = future_events.top();
        future_events.pop();
        current_time = event.time;

        if (event.type == EventType::Arrival) {
            event_log << "time " << current_time << ": Job "
                      << event.job.id() << " arrived\n";

            waiting_jobs.push_back(event.job);
            start_waiting_jobs(waiting_jobs, current_time, nodes,
                               future_events, job_results, event_log, policy);

            const auto waiting_job = std::find_if(
                waiting_jobs.begin(), waiting_jobs.end(),
                [&event](const Job& job) {
                    return job.id() == event.job.id();
                });

            if (waiting_job != waiting_jobs.end()) {
                const auto first_job =
                    highest_priority_job(waiting_jobs, policy);

                event_log << "time " << current_time << ": Job "
                          << event.job.id() << " waiting";
                if (first_job->id() != event.job.id()) {
                    event_log << " behind Job " << first_job->id();
                }
                event_log << "; requested " << event.job.requested_cpus()
                          << " CPUs\n";
            }
        } else {
            if (event.node_id < 0
                || static_cast<std::vector<Node>::size_type>(event.node_id)
                    >= nodes.size()) {
                throw std::logic_error(
                    "completion event has an invalid node ID for Job "
                    + std::to_string(event.job.id()));
            }

            Node& node = nodes[
                static_cast<std::vector<Node>::size_type>(event.node_id)];
            if (node.id() != event.node_id || !node.release(event.job)) {
                throw std::logic_error(
                    "could not release CPUs from node "
                    + std::to_string(event.node_id) + " for Job "
                    + std::to_string(event.job.id()));
            }

            event_log << "time " << current_time << ": Job "
                      << event.job.id() << " completed on node "
                      << node.id() << "; "
                      << node.available_cpus() << '/' << node.total_cpus()
                      << " CPUs available on node\n";

            start_waiting_jobs(waiting_jobs, current_time, nodes,
                               future_events, job_results, event_log, policy);
        }
    }

    if (!waiting_jobs.empty() || job_results.size() != jobs.size()) {
        throw std::logic_error(
            "simulation ended before all jobs completed");
    }

    std::vector<int> available_cpus_by_node;
    available_cpus_by_node.reserve(nodes.size());
    long long total_available_cpus = 0;
    for (const Node& node : nodes) {
        available_cpus_by_node.push_back(node.available_cpus());
        total_available_cpus += node.available_cpus();
    }

    return {
        std::move(job_results),
        current_time,
        total_available_cpus,
        std::move(available_cpus_by_node)
    };
}

SimulationResult run_simulation(const std::vector<Job>& jobs, int total_cpus,
                                std::ostream& event_log,
                                SchedulingPolicy policy) {
    return run_simulation(jobs, 1, total_cpus, event_log, policy);
}
