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

void validate_jobs(const std::vector<Job>& jobs, int total_cpus) {
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

        if (job.requested_cpus() > total_cpus) {
            throw std::invalid_argument(
                "Job " + std::to_string(job.id()) + " requests "
                + std::to_string(job.requested_cpus())
                + " CPUs, exceeding node capacity of "
                + std::to_string(total_cpus));
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
              << " started; " << node.available_cpus() << '/'
              << node.total_cpus() << " CPUs available\n";

    future_events.push({
        completion_time,
        EventType::Completion,
        job
    });
    job_results.push_back({job, current_time, completion_time});
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

void start_waiting_jobs(std::vector<Job>& waiting_jobs, int current_time,
                        Node& node, EventQueue& future_events,
                        std::vector<JobResult>& job_results,
                        std::ostream& event_log,
                        SchedulingPolicy policy) {
    while (!waiting_jobs.empty()) {
        const auto next_job = highest_priority_job(waiting_jobs, policy);

        // Skipping a blocked highest-priority job here would be backfilling.
        if (!node.can_run(*next_job)) {
            break;
        }

        const Job job = *next_job;
        waiting_jobs.erase(next_job);
        start_job(
            job, current_time, node, future_events, job_results, event_log);
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

    throw std::invalid_argument(
        "unknown scheduling policy: " + policy_name
        + " (expected fcfs or sjf)");
}

SimulationResult run_simulation(const std::vector<Job>& jobs, int total_cpus,
                                std::ostream& event_log,
                                SchedulingPolicy policy) {
    Node node(0, total_cpus);
    validate_jobs(jobs, total_cpus);

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
            start_waiting_jobs(waiting_jobs, current_time, node,
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
                          << " CPUs, " << node.available_cpus() << '/'
                          << node.total_cpus() << " available\n";
            }
        } else {
            if (!node.release(event.job)) {
                throw std::logic_error(
                    "could not release CPUs for Job "
                    + std::to_string(event.job.id()));
            }

            event_log << "time " << current_time << ": Job "
                      << event.job.id() << " completed; "
                      << node.available_cpus() << '/' << node.total_cpus()
                      << " CPUs available\n";

            start_waiting_jobs(waiting_jobs, current_time, node,
                               future_events, job_results, event_log, policy);
        }
    }

    if (!waiting_jobs.empty() || job_results.size() != jobs.size()) {
        throw std::logic_error(
            "simulation ended before all jobs completed");
    }

    return {
        std::move(job_results),
        current_time,
        node.available_cpus()
    };
}
