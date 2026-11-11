#pragma once

enum {
    SCE_CTRL_START=8, SCE_CTRL_UP=0x10, SCE_CTRL_RIGHT=0x20, SCE_CTRL_DOWN=0x40, SCE_CTRL_LEFT=0x80,
    SCE_CTRL_LTRIGGER=0x100, SCE_CTRL_TRIANGLE=0x1000, SCE_CTRL_CROSS=0x4000, SCE_CTRL_SQUARE=0x8000,
    SCE_CTRL_MODE_ANALOG=1, SCE_CTRL_INTERCEPTED=0x00010000, SCE_CTRL_PSBUTTON=SCE_CTRL_INTERCEPTED
};
struct SceCtrlData { unsigned buttons; unsigned char lx,ly; };
extern "C" int sceCtrlSetSamplingMode(int mode);
extern "C" int sceCtrlPeekBufferPositive(int port,SceCtrlData* data,int count);
