#pragma once
#include <cstdint>
#include <ctime>
struct SceDateTime {
    std::uint16_t year,month,day,hour,minute,second;
    std::uint32_t microsecond;
};
extern "C" int sceRtcGetCurrentClock(SceDateTime* time,int time_zone);
extern "C" int sceRtcGetTime_t(const SceDateTime* time,time_t* seconds);
