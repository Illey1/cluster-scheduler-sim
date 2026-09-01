#include "csv_io.h"
#include "event.h"
#include "job.h"
#include "job_result.h"
#include "node.h"

#include <exception>
#include <iostream>
#include <queue>
#include <vector>

using EventQueue = std::priority_queue<Event, std::vector<Event>, EventCompare>;

bool start_job(const Job& job, int current_time, Node& node,
               EventQueue& future_events,
               std::vector<JobResult>& results) {
    if (!node.allocate(job)) {
        return false;
    }

    const int completion_time = current_time + job.requested_runtime();

    std::cout << "time " << current_time << ": Job " << job.id()
              << " started; " << node.available_cpus() << '/'
              << node.total_cpus() << " CPUs available\n";

    future_events.push({
        completion_time,
        EventType::Completion,
        job
    });
    results.push_back({job, current_time, completion_time});

    return true;
}

bool start_waiting_jobs(std::queue<Job>& waiting_jobs, int current_time,
                        Node& node, EventQueue& future_events,
                        std::vector<JobResult>& results) {
    while (!waiting_jobs.empty() && node.can_run(waiting_jobs.front())) {
        const Job job = waiting_jobs.front();

        if (!start_job(job, current_time, node, future_events, results)) {
            return false;
        }

        waiting_jobs.pop();
    }

    return true;
}

int main(int argc, char* argv[]) {
    if (argc != 3) {
        std::cerr << "Usage: " << argv[0]
                  << " <workload.csv> <results.csv>\n";
        return 1;
    }

    try {
        const std::vector<Job> jobs = read_jobs_from_csv(argv[1]);
        Node node(0, 8);

        EventQueue future_events;
        for (const Job& job : jobs) {
            future_events.push({
                job.submission_time(),
                EventType::Arrival,
                job
            });
        }

        std::queue<Job> waiting_jobs;
        std::vector<JobResult> results;
        int current_time = 0;

        while (!future_events.empty()) {
            const Event event = future_events.top();
            future_events.pop();
            current_time = event.time;

            if (event.type == EventType::Arrival) {
                std::cout << "time " << current_time << ": Job "
                          << event.job.id() << " arrived\n";

                if (!waiting_jobs.empty()) {
                    const int first_waiting_job_id = waiting_jobs.front().id();
                    waiting_jobs.push(event.job);

                    std::cout << "time " << current_time << ": Job "
                              << event.job.id()
                              << " waiting behind Job "
                              << first_waiting_job_id << "; requested "
                              << event.job.requested_cpus() << " CPUs, "
                              << node.available_cpus() << '/'
                              << node.total_cpus() << " available\n";
                    continue;
                }

                if (!node.can_run(event.job)) {
                    waiting_jobs.push(event.job);

                    std::cout << "time " << current_time << ": Job "
                              << event.job.id() << " waiting; requested "
                              << event.job.requested_cpus() << " CPUs, "
                              << node.available_cpus() << '/'
                              << node.total_cpus() << " available\n";
                    continue;
                }

                if (!start_job(
                        event.job, current_time, node, future_events, results)) {
                    std::cerr << "Could not allocate CPUs for Job "
                              << event.job.id() << '\n';
                    return 1;
                }
            } else {
                if (!node.release(event.job)) {
                    std::cerr << "Could not release CPUs for Job "
                              << event.job.id() << '\n';
                    return 1;
                }

                std::cout << "time " << current_time << ": Job "
                          << event.job.id() << " completed; "
                          << node.available_cpus() << '/' << node.total_cpus()
                          << " CPUs available\n";

                if (!start_waiting_jobs(waiting_jobs, current_time, node,
                                        future_events, results)) {
                    std::cerr << "Could not start a waiting job\n";
                    return 1;
                }
            }
        }

        if (!waiting_jobs.empty() || results.size() != jobs.size()) {
            std::cerr << "Simulation ended with " << waiting_jobs.size()
                      << " job(s) still waiting\n";
            return 1;
        }

        std::cout << "Simulation finished at time " << current_time << "; "
                  << node.available_cpus() << '/' << node.total_cpus()
                  << " CPUs available\n";

        write_results_to_csv(argv[2], results);
        std::cout << "Wrote " << results.size() << " job results to "
                  << argv[2] << '\n';
    } catch (const std::exception& error) {
        std::cerr << "Error: " << error.what() << '\n';
        return 1;
    }

    return 0;
}
