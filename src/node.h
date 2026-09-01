#pragma once

#include "job.h"

#include <stdexcept>

class Node {
public:
    Node(int id, int total_cpus)
        : id_(id), total_cpus_(total_cpus), available_cpus_(total_cpus) {
        if (total_cpus < 0) {
            throw std::invalid_argument("total CPU count cannot be negative");
        }
    }

    int id() const { return id_; }
    int total_cpus() const { return total_cpus_; }
    int available_cpus() const { return available_cpus_; }

    bool can_run(const Job& job) const {
        return job.requested_cpus() >= 0
            && job.requested_cpus() <= available_cpus_;
    }

    bool allocate(const Job& job) {
        if (!can_run(job)) {
            return false;
        }

        available_cpus_ -= job.requested_cpus();
        return true;
    }

    bool release(const Job& job) {
        const int released_cpus = job.requested_cpus();
        if (released_cpus < 0
            || released_cpus > total_cpus_ - available_cpus_) {
            return false;
        }

        available_cpus_ += released_cpus;
        return true;
    }

private:
    int id_;
    int total_cpus_;
    int available_cpus_;
};
