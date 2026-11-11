#pragma once
#include "guest_record.hpp"
#include <array>
#include <cstdint>
#include <limits>
#include <stdexcept>

namespace celeste::diagnostic {

struct CalibrationEndpoint {std::uint64_t process_lo,rtc_us,process_hi;};
struct CalibrationWindow {
    std::uint64_t requested_us,process_min_us,process_max_us,rtc_elapsed_us;
    CalibrationEndpoint begin,end;
};
struct ClockCalibration {std::array<CalibrationWindow,4> windows{};std::uint64_t max_read_gap_us=0;};

inline std::uint64_t rtc_microseconds(std::uint64_t seconds,unsigned microsecond) {
    if(microsecond>=1000000 || seconds>(std::numeric_limits<std::uint64_t>::max()-microsecond)/1000000)
        throw std::runtime_error("RTC microsecond conversion invalid or overflow");
    return seconds*1000000+microsecond;
}
inline std::uint64_t calibration_tolerance(std::uint64_t us) noexcept {return us/100+2;}
inline bool calibration_endpoint_valid(CalibrationEndpoint endpoint) noexcept {
    return endpoint.process_hi>=endpoint.process_lo && endpoint.process_hi-endpoint.process_lo<=1000;
}
inline CalibrationWindow validate_calibration_window(CalibrationEndpoint begin,CalibrationEndpoint end,std::uint64_t requested_us) {
    const auto fail=[&](const char* reason) {
        throw std::runtime_error(bounded_guest_record<768>("Calibration failure context exceeds bound",
            "Clock calibration failed reason=%s requested_us=%llu p0_lo=%llu rtc0=%llu p0_hi=%llu p1_lo=%llu rtc1=%llu p1_hi=%llu bracket_max_us=1000 tolerance=1percent_plus_2us blocked_elapsed_check=failed suspend_validated=0 hardware_perf_proof=0",
            reason,static_cast<unsigned long long>(requested_us),static_cast<unsigned long long>(begin.process_lo),static_cast<unsigned long long>(begin.rtc_us),
            static_cast<unsigned long long>(begin.process_hi),static_cast<unsigned long long>(end.process_lo),static_cast<unsigned long long>(end.rtc_us),static_cast<unsigned long long>(end.process_hi)));
    };
    for(const auto endpoint:{begin,end}) if(!calibration_endpoint_valid(endpoint)) fail("endpoint_regression_or_bracket");
    if(end.process_lo<begin.process_hi || end.rtc_us<begin.rtc_us)
        fail("process_or_RTC_regression");
    CalibrationWindow result{requested_us,end.process_lo-begin.process_hi,end.process_hi-begin.process_lo,end.rtc_us-begin.rtc_us,begin,end};
    const auto tolerance=calibration_tolerance(result.rtc_elapsed_us);
    if((result.rtc_elapsed_us<result.process_min_us && result.process_min_us-result.rtc_elapsed_us>tolerance) ||
       (result.rtc_elapsed_us>result.process_max_us && result.rtc_elapsed_us-result.process_max_us>tolerance))
        fail("RTC_elapsed_outside_tolerance");
    const auto wait_tolerance=calibration_tolerance(requested_us);
    if(requested_us<=wait_tolerance || result.process_min_us<requested_us-wait_tolerance || result.rtc_elapsed_us<requested_us-wait_tolerance)
        fail("blocked_wait_too_short");
    return result;
}
template<class ProcessNow,class RtcNow,class Wait> ClockCalibration calibrate_clock(ProcessNow process_now,RtcNow rtc_now,Wait wait) {
    ClockCalibration result;
    auto previous=process_now();
    for(unsigned i=1;i<64;++i) {
        const auto current=process_now();
        if(current<previous) throw std::runtime_error("Calibration back-to-back process clock regression");
        if(current-previous>result.max_read_gap_us) result.max_read_gap_us=current-previous;
        previous=current;
    }
    std::uint64_t previous_rtc=0;
    bool have_rtc=false;
    const auto endpoint=[&] {
        const auto lo=process_now();
        if(lo<previous) throw std::runtime_error("Calibration process clock regressed across endpoints");
        const auto rtc=rtc_now(),hi=process_now();
        if(!calibration_endpoint_valid({lo,rtc,hi})) throw std::runtime_error("Calibration endpoint regression or RTC bracket exceeds 1000us");
        if(have_rtc && rtc<previous_rtc) throw std::runtime_error("Calibration RTC regression across endpoints");
        previous_rtc=rtc;have_rtc=true;
        previous=hi;
        return CalibrationEndpoint{lo,rtc,hi};
    };
    constexpr std::array<unsigned,4> waits{100000,100000,100000,1000000};
    for(unsigned i=0;i<waits.size();++i) {
        const auto begin=endpoint();wait(waits[i]);const auto end=endpoint();
        result.windows[i]=validate_calibration_window(begin,end,waits[i]);
    }
    return result;
}

}
