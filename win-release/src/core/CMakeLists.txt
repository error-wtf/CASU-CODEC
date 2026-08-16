# casu_core — shared library (placeholder for the port).
# Real WP-CORE-* implementation lands here in Phase B.
add_library(casu_core STATIC dummy.cpp)
target_include_directories(casu_core PUBLIC ${CMAKE_CURRENT_SOURCE_DIR})
target_compile_features(casu_core PUBLIC cxx_std_20)
