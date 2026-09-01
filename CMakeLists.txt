cmake_minimum_required(VERSION 3.16)

project(cluster-scheduler-sim LANGUAGES CXX)

add_executable(cluster-scheduler-sim
    src/csv_io.cpp
    src/main.cpp
)

target_compile_features(cluster-scheduler-sim PRIVATE cxx_std_20)
set_target_properties(cluster-scheduler-sim PROPERTIES
    CXX_EXTENSIONS OFF
)
