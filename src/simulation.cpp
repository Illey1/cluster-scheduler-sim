#include "simulation.h"

#include "event.h"
#include "node.h"

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

void start_waiting_jobs(std::queue<Job>& waiting_jobs, int current_time,
                        Node& node, EventQueue& future_events,
                        std::vector<JobResult>& job_results,
                        std::ostream& event_log) {
    while (!waiting_jobs.empty() && node.can_run(waiting_jobs.front())) {
        const Job job = waiting_jobs.front();
        start_job(
            job, current_time, node, future_events, job_results, event_log);
        waiting_jobs.pop();
    }
}

}  // namespace

SimulationResult run_simulation(const std::vector<Job>& jobs, int total_cpus,
                                std::ostream& event_log) {
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

    std::queue<Job> waiting_jobs;
    std::vector<JobResult> job_results;
    int current_time = 0;

    while (!future_events.empty()) {
        const Event event = future_events.top();
        future_events.pop();
        current_time = event.time;

        if (event.type == EventType::Arrival) {
            event_log << "time " << current_time << ": Job "
                      << event.job.id() << " arrived\n";

            if (!waiting_jobs.empty()) {
                const int first_waiting_job_id = waiting_jobs.front().id();
                waiting_jobs.push(event.job);

                event_log << "time " << current_time << ": Job "
                          << event.job.id() << " waiting behind Job "
                          << first_waiting_job_id << "; requested "
                          << event.job.requested_cpus() << " CPUs, "
                          << node.available_cpus() << '/' << node.total_cpus()
                          << " available\n";
                continue;
            }

            if (!node.can_run(event.job)) {
                waiting_jobs.push(event.job);

                event_log << "time " << current_time << ": Job "
                          << event.job.id() << " waiting; requested "
                          << event.job.requested_cpus() << " CPUs, "
                          << node.available_cpus() << '/' << node.total_cpus()
                          << " available\n";
                continue;
            }

            start_job(event.job, current_time, node, future_events,
                      job_results, event_log);
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
                               future_events, job_results, event_log);
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
