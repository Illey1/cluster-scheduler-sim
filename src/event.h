#pragma once

#include "job.h"

enum class EventType {
    Arrival,
    Completion
};

struct Event {
    int time;
    EventType type;
    Job job;
};

struct EventCompare {
    bool operator()(const Event& left, const Event& right) const {
        if (left.time != right.time) {
            return left.time > right.time;
        }

        // Completing work first makes its CPUs available to arrivals at the
        // same simulated time.
        if (left.type != right.type) {
            return left.type == EventType::Arrival;
        }

        return left.job.id() > right.job.id();
    }
};
