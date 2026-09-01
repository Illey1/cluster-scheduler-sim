#pragma once

class Job {
public:
    Job(int id, int submission_time, int requested_runtime, int requested_cpus)
        : id_(id),
          submission_time_(submission_time),
          requested_runtime_(requested_runtime),
          requested_cpus_(requested_cpus) {}

    int id() const { return id_; }
    int submission_time() const { return submission_time_; }
    int requested_runtime() const { return requested_runtime_; }
    int requested_cpus() const { return requested_cpus_; }

private:
    int id_;
    int submission_time_;
    int requested_runtime_;
    int requested_cpus_;
};
