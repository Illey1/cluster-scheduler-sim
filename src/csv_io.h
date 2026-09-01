#pragma once

#include "job.h"
#include "job_result.h"

#include <string>
#include <vector>

std::vector<Job> read_jobs_from_csv(const std::string& input_path);

void write_results_to_csv(const std::string& output_path,
                          const std::vector<JobResult>& results);
