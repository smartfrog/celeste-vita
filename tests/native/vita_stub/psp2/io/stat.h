#pragma once

#include <psp2/types.h>

struct SceIoStat {
    int mode;
};

extern "C" int sceIoGetstat(const char* path, SceIoStat* status);
