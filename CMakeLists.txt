cmake_minimum_required(VERSION 3.16)

project(cluster-scheduler-sim LANGUAGES CXX)

add_library(cluster-scheduler-core
    src/csv_io.cpp
    src/simulation.cpp
)

target_include_directories(cluster-scheduler-core PUBLIC src)
target_compile_features(cluster-scheduler-core PUBLIC cxx_std_20)
set_target_properties(cluster-scheduler-core PROPERTIES
    CXX_EXTENSIONS OFF
)

add_executable(cluster-scheduler-sim
    src/main.cpp
)

target_link_libraries(cluster-scheduler-sim PRIVATE cluster-scheduler-core)
set_target_properties(cluster-scheduler-sim PROPERTIES
    CXX_EXTENSIONS OFF
)

enable_testing()

add_executable(cluster-scheduler-tests
    tests/test_main.cpp
)

target_link_libraries(cluster-scheduler-tests PRIVATE cluster-scheduler-core)
set_target_properties(cluster-scheduler-tests PROPERTIES
    CXX_EXTENSIONS OFF
)

add_test(NAME cluster-scheduler-tests COMMAND cluster-scheduler-tests)

add_test(
    NAME cluster-scheduler-cli-default
    COMMAND cluster-scheduler-sim
        ${CMAKE_CURRENT_SOURCE_DIR}/workloads/example.csv
        ${CMAKE_CURRENT_BINARY_DIR}/cli-default-results.csv
)

add_test(
    NAME cluster-scheduler-cli-multinode
    COMMAND cluster-scheduler-sim
        ${CMAKE_CURRENT_SOURCE_DIR}/workloads/multinode.csv
        ${CMAKE_CURRENT_BINARY_DIR}/cli-multinode-results.csv
        backfill --nodes 2 --cpus-per-node 4
)
