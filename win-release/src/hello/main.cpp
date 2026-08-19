#include <cstdio>
#include <windows.h>

int main() {
    const char* msg = "CASU/MPCASU Windows Port - STEP-001 toolchain OK\n";
    printf("%s", msg);
    OutputDebugStringA(msg);
    return 0;
}
