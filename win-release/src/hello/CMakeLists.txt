# STEP-001 gate: a Hello-Windows executable (PE32+) that runs under Wine.
add_executable(casu_hello main.cpp)
target_compile_features(casu_hello PRIVATE cxx_std_20)
