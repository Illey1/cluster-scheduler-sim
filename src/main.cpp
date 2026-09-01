#include "event.h"
#include "job.h"
#include "node.h"

#include <iostream>
#include <queue>
#include <vector>

using EventQueue = std::priority_queue<Event, std::vector<Event>, EventCompare>;

bool start_job(const Job& job, int current_time, Node& node,
               EventQueue& future_events) {
    if (!node.allocate(job)) {
        return false;
    }

    std::cout << "time " << current_time << ": Job " << job.id()
              << " started; " << node.available_cpus() << '/'
              << node.total_cpus() << " CPUs available\n";

    future_events.push({
        current_time + job.requested_runtime(),
        EventType::Completion,
        job
    });

    return true;
}

bool start_waiting_jobs(std::queue<Job>& waiting_jobs, int current_time,
                        Node& node, EventQueue& future_events) {
    while (!waiting_jobs.empty() && node.can_run(waiting_jobs.front())) {
        const Job job = waiting_jobs.front();

        if (!start_job(job, current_time, node, future_events)) {
            return false;
        }

        waiting_jobs.pop();
    }

    return true;
}

int main() {
    Node node(0, 8);

    const Job job1(1, 0, 10, 6);
    const Job job2(2, 2, 4, 4);
    const Job job3(3, 3, 3, 2);

    EventQueue future_events;
    future_events.push({job1.submission_time(), EventType::Arrival, job1});
    future_events.push({job2.submission_time(), EventType::Arrival, job2});
    future_events.push({job3.submission_time(), EventType::Arrival, job3});

    std::queue<Job> waiting_jobs;
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
                          << " waiting behind Job " << first_waiting_job_id
                          << "; requested " << event.job.requested_cpus()
                          << " CPUs, " << node.available_cpus() << '/'
                          << node.total_cpus() << " available\n";
                continue;
            }

            if (!node.can_run(event.job)) {
                waiting_jobs.push(event.job);

                std::cout << "time " << current_time << ": Job "
                          << event.job.id() << " waiting; requested "
                          << event.job.requested_cpus() << " CPUs, "
                          << node.available_cpus() << '/' << node.total_cpus()
                          << " available\n";
                continue;
            }

            if (!start_job(event.job, current_time, node, future_events)) {
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

            if (!start_waiting_jobs(
                    waiting_jobs, current_time, node, future_events)) {
                std::cerr << "Could not start a waiting job\n";
                return 1;
            }
        }
    }

    std::cout << "Simulation finished at time " << current_time << "; "
              << node.available_cpus() << '/' << node.total_cpus()
              << " CPUs available\n";

    return 0;
}
