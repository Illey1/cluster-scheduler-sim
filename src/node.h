#pragma once

class Node {
public:
    Node(int id, int total_cpus)
        : id_(id), total_cpus_(total_cpus), available_cpus_(total_cpus) {}

    int id() const { return id_; }
    int total_cpus() const { return total_cpus_; }
    int available_cpus() const { return available_cpus_; }

private:
    int id_;
    int total_cpus_;
    int available_cpus_;
};
