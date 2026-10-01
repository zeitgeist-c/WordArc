cmake_minimum_required(VERSION 3.19)
project(wordarc_vulkan_probe LANGUAGES CXX)
add_executable(wordarc-vulkan-probe vulkan_probe.cpp)
target_include_directories(wordarc-vulkan-probe PRIVATE "${WHISPER_SOURCE}/ggml/include")
target_link_libraries(wordarc-vulkan-probe PRIVATE
    "${WHISPER_BUILD}/ggml/src/Release/ggml-base.lib"
    "${WHISPER_BUILD}/ggml/src/ggml-vulkan/Release/ggml-vulkan.lib")
set_property(TARGET wordarc-vulkan-probe PROPERTY MSVC_RUNTIME_LIBRARY MultiThreaded)
