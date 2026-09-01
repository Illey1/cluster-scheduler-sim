#include "event.h"
#include "job.h"
#include "node.h"

#include <iostream>
#include <queue>
#include <vector>

int main() {
    Node node(0, 8);

    const Job job1(1, 0, 10, 4);
    const Job job2(2, 3, 5, 4);
    const Job job3(3, 8, 2, 4);

    std::priority_queue<Event, std::vector<Event>, EventCompare> future_events;
    future_events.push({job1.submission_time(), EventType::Arrival, job1});
    future_events.push({job2.submission_time(), EventType::Arrival, job2});
    future_events.push({job3.submission_time(), EventType::Arrival, job3});

    int current_time = 0;

    while (!future_events.empty()) {
        const Event event = future_events.top();
        future_events.pop();
        current_time = event.time;

        if (event.type == EventType::Arrival) {
            std::cout << "time " << current_time << ": Job "
                      << event.job.id() << " arrived\n";

            if (!node.allocate(event.job)) {
                std::cout << "time " << current_time << ": Job "
                          << event.job.id()
                          << " cannot start; waiting is not implemented\n";
                continue;
            }

            std::cout << "time " << current_time << ": Job "
                      << event.job.id() << " started; "
                      << node.available_cpus() << '/' << node.total_cpus()
                      << " CPUs available\n";

            future_events.push({
                current_time + event.job.requested_runtime(),
                EventType::Completion,
                event.job
            });
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
        }
    }

    std::cout << "Simulation finished at time " << current_time << "; "
              << node.available_cpus() << '/' << node.total_cpus()
              << " CPUs available\n";

    return 0;
}
