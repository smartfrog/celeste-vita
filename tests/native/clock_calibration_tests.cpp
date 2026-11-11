#include "clock_calibration.hpp"
#include <iostream>
#include <limits>
#include <stdexcept>
#include <string>

using namespace celeste::diagnostic;
namespace {
void expect(bool value,const char* message) {if(!value) throw std::runtime_error(message);}
template<class F> void rejects(F action,const char* message) {
    try {action();} catch(const std::runtime_error&) {return;}throw std::runtime_error(message);
}
void exact_bracket_boundaries_pass() {
    const auto result=validate_calibration_window({100,1000000,1100},{100100,1100000,101100},100000);
    expect(result.process_min_us==99000 && result.process_max_us==101000 && result.rtc_elapsed_us==100000,"Calibration must preserve bracket bounds");
}
void tolerance_boundaries_parameterized() {
    for(auto delta:{std::uint64_t{99008},std::uint64_t{101012}})
        validate_calibration_window({0,0,0},{100000,delta,100000},100000);
}
void invalid_calibration_windows_parameterized() {
    struct Case {CalibrationEndpoint begin,end;std::uint64_t wait;};
    for(const auto item:{Case{{1,0,0},{100000,100000,100000},100000},
                         Case{{0,0,1001},{100000,100000,100000},100000},
                         Case{{0,200,0},{100000,100,100000},100000},
                         Case{{100001,0,100001},{100000,100000,100000},100000},
                         Case{{0,0,0},{98997,100000,98997},100000},
                         Case{{0,0,0},{100000,98997,100000},100000},
                         Case{{0,0,0},{100000,101013,100000},100000}})
        rejects([&]{validate_calibration_window(item.begin,item.end,item.wait);},"Bad clock window must be rejected");
}
void scheduler_overshoot_has_no_upper_bound() {
    constexpr auto limit=std::numeric_limits<std::uint64_t>::max();
    const auto result=validate_calibration_window({0,0,0},{limit,limit,limit},100000);
    expect(result.rtc_elapsed_us==limit,"Scheduler overshoot must not invent an upper target duration");
}
void injected_calibration_waits_before_game_only() {
    std::uint64_t process=1000;unsigned waits=0,reads=0;
    const auto result=calibrate_clock([&]{++reads;return process++;},[&]{return process;},[&](unsigned us){++waits;process+=us;});
    expect(waits==4 && reads==80 && result.max_read_gap_us==1,"Calibration must run exact 64 reads and eight bracketed endpoints");
    expect(result.windows[3].requested_us==1000000,"Calibration must include the one-second block");
}
void injected_api_failure_is_not_swallowed() {
    std::uint64_t process=0;
    rejects([&]{calibrate_clock([&]{return process++;},[&]{return process;},[](unsigned){throw std::runtime_error("wait API failed");});},"Wait failure must abort calibration");
}
void back_to_back_clock_regression_is_fatal() {
    unsigned reads=0;
    rejects([&]{calibrate_clock([&]{return std::uint64_t(++reads==64 ? 0 : reads);},[]{return std::uint64_t{0};},[](unsigned){});},"Read regression must abort calibration");
}
void rtc_conversion_overflow_parameterized() {
    constexpr auto limit=std::numeric_limits<std::uint64_t>::max();
    for(const auto item:{std::pair<std::uint64_t,unsigned>{limit/1000000+1,0},{limit/1000000,999999},{0,1000000}})
        rejects([&]{rtc_microseconds(item.first,item.second);},"RTC conversion must reject invalid microseconds or overflow");
}
void rtc_conversion_preserves_exact_microseconds() {
    expect(rtc_microseconds(123,456789)==123456789,"RTC conversion must retain integer microseconds");
}
void rtc_regression_between_windows_is_fatal() {
    std::uint64_t process=2000000;unsigned references=0;
    rejects([&]{calibrate_clock([&]{return process++;},[&]{return ++references>=3 ? process-1000000 : process;},[&](unsigned us){process+=us;});},"RTC regression between windows must not be hidden by individually valid waits");
}
void invalid_first_endpoint_fails_before_wait() {
    unsigned reads=0,waits=0;
    rejects([&]{calibrate_clock([&]{return std::uint64_t(++reads==66 ? 0 : reads);},[]{return std::uint64_t{100};},[&](unsigned){++waits;});},"Invalid first endpoint must fail");
    expect(waits==0,"Invalid first endpoint must be rejected before any blocking wait");
}
}
int main() {
    unsigned failed=0;
    for(auto test:{exact_bracket_boundaries_pass,tolerance_boundaries_parameterized,invalid_calibration_windows_parameterized,scheduler_overshoot_has_no_upper_bound,
                  injected_calibration_waits_before_game_only,injected_api_failure_is_not_swallowed,back_to_back_clock_regression_is_fatal,
                  rtc_conversion_overflow_parameterized,rtc_conversion_preserves_exact_microseconds,rtc_regression_between_windows_is_fatal,
                  invalid_first_endpoint_fails_before_wait}) {
        try {test();} catch(const std::exception& error) {std::cerr<<error.what()<<'\n';++failed;}
    }
    std::cout<<"clock calibration cases=11 failed="<<failed<<'\n';return failed ? 1 : 0;
}
