#include "job.h"
#include "node.h"

#include <iostream>

int main() {
    const Job job(1, 0, 10, 4);
    const Node node(0, 8);

    std::cout << "Job " << job.id()
              << ": submit=" << job.submission_time()
              << ", runtime=" << job.requested_runtime()
              << ", cpus=" << job.requested_cpus() << '\n';

    std::cout << "Node " << node.id()
              << ": total_cpus=" << node.total_cpus()
              << ", available_cpus=" << node.available_cpus() << '\n';

    return 0;
}
