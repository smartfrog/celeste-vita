#pragma once

#include <cstdint>

extern "C" std::uint64_t sceKernelGetProcessTimeWide();
extern "C" int sceKernelExitProcess(int status);
