#pragma once
#include "clock_calibration.hpp"
#include "frame_metrics.hpp"
#include "normal_outputs.hpp"
#include <psp2/kernel/processmgr.h>
#include <psp2/kernel/threadmgr.h>
#include <psp2/rtc.h>

namespace celeste::diagnostic {

inline constexpr const char* process_clock_provenance="sceKernelGetProcessTimeWide_newlib_CLOCK_MONOTONIC_us";
inline std::uint64_t process_now_us() {return sceKernelGetProcessTimeWide();}
inline std::uint64_t rtc_now_us() {
    SceDateTime date{};
    const auto clock_status=sceRtcGetCurrentClock(&date,0);
    if(clock_status<0) throw std::runtime_error("sceRtcGetCurrentClock failed code="+std::to_string(clock_status));
    time_t seconds=0;
    const auto conversion_status=sceRtcGetTime_t(&date,&seconds);
    if(conversion_status<0) throw std::runtime_error("sceRtcGetTime_t failed code="+std::to_string(conversion_status));
    if(seconds<0) throw std::runtime_error("RTC seconds before epoch are invalid for calibration");
    return rtc_microseconds(static_cast<std::uint64_t>(seconds),date.microsecond);
}
inline ClockCalibration calibrate_platform_clock() {
    return calibrate_clock(process_now_us,rtc_now_us,[](unsigned us) {
        const auto status=sceKernelDelayThread(us);
        if(status<0) throw std::runtime_error("sceKernelDelayThread calibration failed code="+std::to_string(status));
    });
}
inline MetricSummary calibration_record(const NormalOutputPaths& paths,const ClockCalibration& calibration) {
    MetricSummary output;
    output.append("clock_calibration run_id=%s revision=%s clock=%s rtc_reference=separate_API_not_independent_hardware bracket_max_us=1000 tolerance=1percent_plus_2us wait_lower=requested_minus_1percent_plus_2us scheduler_overshoot_allowed=1 read_samples=64 max_read_gap_us=%llu read_call_overhead_claim=0 blocked_elapsed_check=passed suspend_validated=0 hardware_perf_proof=0 instrumented=1",
        paths.run_id.c_str(),paths.revision.c_str(),process_clock_provenance,static_cast<unsigned long long>(calibration.max_read_gap_us));
    for(unsigned i=0;i<calibration.windows.size();++i) {
        const auto& w=calibration.windows[i];
        output.append(" window%u:requested_us=%llu,p0_lo=%llu,rtc0=%llu,p0_hi=%llu,p1_lo=%llu,rtc1=%llu,p1_hi=%llu,process_min_us=%llu,process_max_us=%llu,rtc_elapsed_us=%llu",
            i,static_cast<unsigned long long>(w.requested_us),static_cast<unsigned long long>(w.begin.process_lo),static_cast<unsigned long long>(w.begin.rtc_us),
            static_cast<unsigned long long>(w.begin.process_hi),static_cast<unsigned long long>(w.end.process_lo),static_cast<unsigned long long>(w.end.rtc_us),
            static_cast<unsigned long long>(w.end.process_hi),static_cast<unsigned long long>(w.process_min_us),static_cast<unsigned long long>(w.process_max_us),static_cast<unsigned long long>(w.rtc_elapsed_us));
    }
    return output;
}

}
