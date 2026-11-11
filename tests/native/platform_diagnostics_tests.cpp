#include "platform_diagnostics.hpp"
#include <iostream>
#include <stdexcept>
#include <string>

using namespace celeste::diagnostic;
namespace {
std::uint64_t ticks=1000000;
int rtc_status=0,conversion_status=0,wait_status=0;
time_t seconds=1;
unsigned microsecond=0,waits=0;
void reset() {ticks=1000000;rtc_status=conversion_status=wait_status=0;seconds=1;microsecond=waits=0;}
void expect(bool value,const char* message) {if(!value) throw std::runtime_error(message);}
template<class F> void rejects(F action,const char* cause) {
    try {action();} catch(const std::runtime_error& error) {expect(std::string(error.what()).find(cause)!=std::string::npos,"API error cause missing");return;}
    throw std::runtime_error("API error must propagate");
}
void rtc_api_errors_parameterized() {
    for(unsigned failure=0;failure<4;++failure) {
        reset();
        if(failure==0) rtc_status=-13;
        if(failure==1) conversion_status=-5;
        if(failure==2) seconds=-1;
        if(failure==3) microsecond=1000000;
        rejects(rtc_now_us,failure==0 ? "sceRtcGetCurrentClock failed code=-13" : failure==1 ? "sceRtcGetTime_t failed code=-5" : failure==2 ? "before epoch" : "invalid or overflow");
    }
}
void rtc_uses_checked_integer_conversion() {
    reset();seconds=123;microsecond=456789;
    expect(rtc_now_us()==123456789,"RTC API must retain exact validated timestamp");
}
void wait_api_failure_aborts_before_game() {
    reset();wait_status=-5;rejects(calibrate_platform_clock,"sceKernelDelayThread calibration failed code=-5");
    expect(waits==1,"Calibration failure must not run later waits");
}
void successful_calibration_record_binds_run_and_revision() {
    reset();
    const auto calibration=calibrate_platform_clock();
    const auto outputs=normal_output_paths(std::string(40,'a'),77,0);
    const auto record=calibration_record(outputs,calibration);
    const std::string text(record.text.data(),record.size);
    for(const auto& field:{"run_id="+outputs.run_id,"revision="+outputs.revision,std::string("blocked_elapsed_check=passed"),std::string("suspend_validated=0 hardware_perf_proof=0"),std::string("window3:requested_us=1000000"),std::string("read_call_overhead_claim=0")})
        expect(text.find(field)!=std::string::npos,"Calibration record must retain provenance, criteria and limits");
    expect(waits==4 && record.size<record.text.size(),"Calibration must use exactly four waits and bounded record storage");
}
}
extern "C" std::uint64_t sceKernelGetProcessTimeWide() {return ticks;}
extern "C" int sceRtcGetCurrentClock(SceDateTime* date,int zone) {
    expect(zone==0,"RTC reference must use timezone zero");date->microsecond=microsecond;return rtc_status;
}
extern "C" int sceRtcGetTime_t(const SceDateTime*,time_t* output) {*output=seconds;return conversion_status;}
extern "C" int sceKernelDelayThread(unsigned delay) {
    ++waits;if(wait_status<0) return wait_status;ticks+=delay;seconds=time_t(ticks/1000000);microsecond=unsigned(ticks%1000000);return 0;
}
int main() {
    unsigned failed=0;
    for(auto test:{rtc_api_errors_parameterized,rtc_uses_checked_integer_conversion,wait_api_failure_aborts_before_game,successful_calibration_record_binds_run_and_revision}) {
        try {test();} catch(const std::exception& error) {std::cerr<<error.what()<<'\n';++failed;}
    }
    std::cout<<"platform diagnostics cases=4 failed="<<failed<<'\n';return failed ? 1 : 0;
}
