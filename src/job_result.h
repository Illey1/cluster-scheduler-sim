#pragma once

#include "job.h"

struct JobResult {
    Job job;
    int start_time;
    int completion_time;

    int wait_time() const {
        return start_time - job.submission_time();
    }
};
