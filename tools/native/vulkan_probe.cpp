// Isolate driver/ggml initialization from WordArc's GUI process.
#include "ggml-backend.h"
#include "ggml-vulkan.h"
#include <cstdio>
#ifdef _WIN32
#include <windows.h>
#endif
int main() {
#ifdef _WIN32
    SetConsoleOutputCP(CP_UTF8);
    SetErrorMode(SEM_FAILCRITICALERRORS | SEM_NOGPFAULTERRORBOX);
#endif
    auto reg = ggml_backend_vk_reg();
    if (!reg) return 1;
    for (size_t i = 0; i < ggml_backend_reg_dev_count(reg); ++i) {
        auto dev = ggml_backend_reg_dev_get(reg, i);
        size_t free = 0, total = 0;
        ggml_backend_dev_memory(dev, &free, &total);
        printf("%zu\t%d\t%zu\t%s\n", i, int(ggml_backend_dev_type(dev)),
               total, ggml_backend_dev_description(dev));
    }
    return 0;
}
