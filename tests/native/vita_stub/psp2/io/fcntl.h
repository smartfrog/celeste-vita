#pragma once

#include <psp2/types.h>

enum {
    SCE_O_WRONLY = 0x0002,
    SCE_O_CREAT = 0x0200,
    SCE_O_TRUNC = 0x0400,
    SCE_O_EXCL = 0x0800,
};

extern "C" SceUID sceIoOpen(const char* path, int flags, SceMode mode);
extern "C" int sceIoClose(SceUID fd);
extern "C" SceSSize sceIoWrite(SceUID fd, const void* buffer, SceSize size);
