#include "guest_file_fixture.hpp"
#include "assets.hpp"
#include <cstdarg>
#include <cstdio>
#include <filesystem>
#include <iostream>

FILE* simulated_stderr=stderr;
#undef stderr
#define stderr simulated_stderr
#define main diagnostic_entry
#include "../../src/vita/app.cpp"
#undef main
#undef stderr

namespace {
enum class Fault {none,open,buffer,buffer_and_close,format,format_and_close,newline,flush,close};
Fault fault=Fault::none;
Fault emergency_fault=Fault::none;
FILE* watched=nullptr;
FILE* tty=nullptr;
std::string log_file,asset_file,tty_file;
bool reset_on_asset_open=false;
bool caller_probe=false;
unsigned log_closes=0;
unsigned unexpected_calls=0;
[[noreturn]] void unexpected_runtime_call() {++unexpected_calls;throw std::runtime_error("Unexpected game/SDK call in caller error probe");}
bool format_failed(FILE* file) {
    return (file==watched && (fault==Fault::format || fault==Fault::format_and_close)) || (file==tty && emergency_fault==Fault::format);
}
void expect(bool value,const char* message) {if(!value) throw std::runtime_error(message);}
template<class F> void rejects(F action,const std::string& cause) {
    try {action();} catch(const std::runtime_error& error) {
        expect(std::string(error.what()).find(cause)!=std::string::npos,"Failure must retain operation/path context");return;
    }
    throw std::runtime_error("Expected checked log failure");
}
std::string fresh_path(const char* suffix) {
    for(unsigned i=0;i<10000;++i) {
        const auto path=std::string(CELESTE_APP_LOG_TEST_DIRECTORY)+"/app-log-"+std::to_string(i)+suffix;
        if(!std::filesystem::exists(path)) return path;
    }
    throw std::runtime_error("Owned log test paths exhausted");
}
std::string bytes(const std::string& path) {return read_asset(path.c_str(),65536);}
void setup() {
    guest_test::reset();fault=emergency_fault=Fault::none;watched=nullptr;reset_on_asset_open=caller_probe=false;log_closes=unexpected_calls=0;
    normal_outputs=normal_output_paths(revision,77,0);normal_capture_closed=false;normal_ready_written=false;measuring_frame=false;
    log_file=fresh_path(".log");asset_file=fresh_path(".asset");normal_outputs.log=log_file;
    auto* claim=std::fopen(log_file.c_str(),"w+x");expect(claim,"Synthetic exclusive claim must open");
    expect(std::fputs("normal_run_claimed\n",claim)>=0 && std::fclose(claim)==0,"Synthetic claim must close");
    auto* asset=std::fopen(asset_file.c_str(),"w+x");expect(asset,"Synthetic asset must open");
    expect(std::fputs("synthetic asset read churn\n",asset)>=0 && std::fclose(asset)==0,"Synthetic asset must close");
    tty_file=fresh_path(".tty");tty=std::fopen(tty_file.c_str(),"w+x");expect(tty,"Synthetic TTY must open");
    normal_log=open_app_log(log_file.c_str());watched=normal_log;simulated_stderr=normal_log;
}
void cleanup() {
    fault=emergency_fault=Fault::none;reset_on_asset_open=caller_probe=false;
    close_app_log(normal_log,log_file.c_str());watched=nullptr;
    expect(std::fclose(tty)==0,"Synthetic TTY must close");tty=nullptr;simulated_stderr=nullptr;
}
void owned_stream_survives_asset_stdio_and_global_reset() {
    setup();log("bootstrap revision=%s",revision);reset_on_asset_open=true;
    expect(bytes(asset_file)=="synthetic asset read churn\n","Real read_asset must exercise fopen/fread/fclose");
    for(const char* text:{"assets ready","frame_saved frame=36","input frame=301","frame_metrics reason=periodic","frame_metrics reason=Start_final"}) log("%s",text);
    cleanup();const auto text=bytes(log_file);
    for(const char* expected:{"normal_run_claimed","bootstrap revision=","assets ready","frame_saved frame=36","input frame=301","reason=periodic","reason=Start_final"})
        expect(text.find(expected)!=std::string::npos,"Global-stderr-reset test double must not divert owned normal log after actual asset stdio");
}
void append_preserves_claim_bytes() {
    setup();log("sentinel");cleanup();expect(bytes(log_file)=="normal_run_claimed\nsentinel\n","Opening owned normal log must append, never truncate its exclusive claim");
}
void open_failure_is_checked() {
    setup();close_app_log(normal_log,log_file.c_str());fault=Fault::open;
    rejects([&]{normal_log=open_app_log(log_file.c_str());},"open failed: "+log_file);expect(!normal_log,"Failed open must not transfer ownership");cleanup();
}
void buffer_failure_closes_once() {
    setup();close_app_log(normal_log,log_file.c_str());const auto before=log_closes;fault=Fault::buffer;
    rejects([&]{normal_log=open_app_log(log_file.c_str());},"buffer setup failed: "+log_file);
    expect(!normal_log && log_closes==before+1,"Failed buffer setup must close only the newly opened stream");cleanup();
}
void buffer_setup_and_cleanup_failure_keep_both_causes() {
    setup();close_app_log(normal_log,log_file.c_str());const auto before=log_closes;fault=Fault::buffer_and_close;
    rejects([&]{normal_log=open_app_log(log_file.c_str());},"buffer setup failed: "+log_file+"; cleanup close failed");
    expect(!normal_log && log_closes==before+1,"Failed setup cleanup must not leak or transfer the closed stream");cleanup();
}
void open_failure_persists_without_borrowing_stderr() {
    setup();close_app_log(normal_log,log_file.c_str());fault=Fault::open;simulated_stderr=tty;
    std::string cause;
    try {normal_log=open_app_log(log_file.c_str());} catch(const std::exception& error) {cause=error.what();}
    expect(!cause.empty() && finish_normal_log(cause)==1,"Open failure must take the independent failure path without using stderr");
    expect(guest_test::stored.at(normal_outputs.failure).data.find("open failed: "+log_file)!=std::string::npos,"SCE receipt must retain the owned-stream open failure");
    cleanup();expect(bytes(tty_file).empty(),"A failed owned open must not borrow the global stderr channel");
}
void write_failures_are_checked_parameterized() {
    for(const auto item:{std::pair<Fault,const char*>{Fault::format,"format"},{Fault::newline,"newline"},{Fault::flush,"flush"}}) {
        setup();fault=item.first;rejects([&]{log("input frame=%u",301u);},std::string(item.second)+" failed: "+log_file);cleanup();
    }
}
void close_failure_releases_pointer_once() {
    setup();fault=Fault::close;
    rejects([&]{close_app_log(normal_log,log_file.c_str());},"close failed: "+log_file);
    expect(!normal_log && log_closes==1,"Failed close must release ownership, never retry or close another stream");
    close_app_log(normal_log,log_file.c_str());expect(log_closes==1,"Explicit second close must not close anything");cleanup();
}
void fatal_log_failure_still_persists_independent_sce_receipt() {
    setup();fault=Fault::format;const auto status=finish_normal_log("asset read failed");
    expect(status==2 && !normal_log,"Fatal log error must still close owned stream and report diagnostic failure");
    const auto& receipt=guest_test::stored.at(normal_outputs.failure).data;
    expect(receipt.find("asset read failed")!=std::string::npos && receipt.find("format failed: "+log_file)!=std::string::npos,"SCE failure must retain original and logging errors independently of stdio");
    expect(guest_test::stored.at(normal_outputs.ready).data.find("failed")!=std::string::npos,"Independent failure readiness must close");cleanup();
}
void close_failure_is_recorded_independently() {
    setup();fault=Fault::close;expect(finish_normal_log({})==2,"Close failure cannot become a clean exit");
    expect(guest_test::stored.at(normal_outputs.failure).data.find("close failed: "+log_file)!=std::string::npos,"Close failure context must reach independent receipt");cleanup();
}
void fatal_route_stays_owned_after_global_reset() {
    setup();simulated_stderr=tty;expect(finish_normal_log("synthetic FATAL") == 1,"Primary application error must retain exit status");
    expect(bytes(log_file).find("FATAL: synthetic FATAL")!=std::string::npos,"Fatal route must not write global stderr after reset");cleanup();
}
void ready_update_survives_asset_stdio_churn() {
    setup();signal("ready",0);reset_on_asset_open=true;bytes(asset_file);normal_capture_closed=true;signal("sampled",301);
    const auto& ready=guest_test::stored.at(normal_outputs.ready).data;
    expect(ready.find("frame=301")!=std::string::npos && ready.find("capture_outcome=fresh_closed")!=std::string::npos,"SCE readiness must reflect the latest explicit event despite unrelated stdio churn");cleanup();
}
void legacy_profile_keeps_stderr_routing() {
    setup();simulated_stderr=tty;log("legacy profile unchanged");cleanup();
    expect(bytes(log_file)=="normal_run_claimed\n" && bytes(tty_file)=="legacy profile unchanged\n","Non-normal profile must retain checked stderr routing, not the normal owned stream");
}
void independent_failure_io_errors_propagate_parameterized() {
    for(unsigned failure=0;failure<4;++failure) {
        setup();
        if(failure==0) guest_test::stored[normal_outputs.failure]={"prior failure preserved"};
        if(failure==1) {guest_test::open_error=guest_test::error(13);guest_test::fail_open=1;}
        if(failure==2) guest_test::write_error=1;
        if(failure==3) guest_test::close_error=guest_test::error(5);
        rejects([&]{finish_normal_log("original application error");},"original application error; independent failure receipt also failed:");
        expect(!normal_log,"Receipt IO failure cannot leak the owned stdio log");
        if(failure==0) expect(guest_test::stored.at(normal_outputs.failure).data=="prior failure preserved","Independent failure collision must preserve all previous bytes");
        cleanup();
    }
}
void setup_caller_probe() {
    setup();close_app_log(normal_log,log_file.c_str());log_closes=0;
    caller_probe=true;fault=Fault::format_and_close;simulated_stderr=tty;
    guest_test::open_error=guest_test::error(13);guest_test::fail_open=2;
}
std::string caller_failure_context() {
    return "Normal app log format failed: "+normal_outputs.log+
        "; fatal log also failed: Normal app log format failed: "+normal_outputs.log+
        "; Normal app log close failed: "+normal_outputs.log+
        "; independent failure receipt also failed: Guest output open failed: "+normal_outputs.failure+
        " code="+std::to_string(guest_test::error(13));
}
void caller_reports_full_context_to_emergency_before_returning_two() {
    setup_caller_probe();const auto status=normal_application();
    expect(status==2,"Successful emergency reporting must retain terminal diagnostic-output status 2");
    expect(!normal_log && log_closes==1 && unexpected_calls==0,"Caller must release its failed owned stream exactly once, before any gameplay");
    expect(guest_test::stored.find(normal_outputs.failure)==guest_test::stored.end(),"Injected independent receipt open must actually fail");
    expect(bytes(tty_file).find(caller_failure_context())!=std::string::npos,"Caller must emit the entire original/log/close/receipt operation and path context to independent emergency output");
    cleanup();
}
void caller_emergency_errors_propagate_full_context_parameterized() {
    for(const auto item:{std::pair<Fault,const char*>{Fault::format,"format"},{Fault::newline,"newline"},{Fault::flush,"flush"}}) {
        setup_caller_probe();emergency_fault=item.first;
        std::string reported;
        try {normal_application();} catch(const std::runtime_error& error) {reported=error.what();}
        expect(!reported.empty(),"Failed emergency output must propagate, never silently return status 2");
        expect(reported==caller_failure_context()+"; emergency stderr "+item.second+" failed","Emergency failure must retain the complete caller error context and failed emergency operation");
        expect(!normal_log && log_closes==1 && unexpected_calls==0,"Even emergency failure must never retry close or enter gameplay");
        cleanup();
    }
}
}
extern "C" FILE* __real_fopen(const char*,const char*);
extern "C" int __real_fclose(FILE*);
extern "C" int __real_setvbuf(FILE*,char*,int,std::size_t);
extern "C" int __real_vfprintf(FILE*,const char*,va_list);
extern "C" int __wrap_fprintf(FILE* file,const char* format,...) {
    va_list args;va_start(args,format);const auto result=format_failed(file) ? -1 : __real_vfprintf(file,format,args);va_end(args);return result;
}
#ifdef __GLIBC__
extern "C" int __real___vfprintf_chk(FILE*,int,const char*,va_list);
extern "C" int __wrap___vfprintf_chk(FILE* file,int flag,const char* format,va_list args) {return format_failed(file) ? -1 : __real___vfprintf_chk(file,flag,format,args);}
extern "C" int __wrap___fprintf_chk(FILE* file,int flag,const char* format,...) {
    va_list args;va_start(args,format);const auto result=format_failed(file) ? -1 : __real___vfprintf_chk(file,flag,format,args);va_end(args);return result;
}
#endif
extern "C" int __real_fputc(int,FILE*);
extern "C" int __real_fflush(FILE*);
extern "C" FILE* __wrap_fopen(const char* path,const char* mode) {
    if(caller_probe && path==normal_outputs.log && std::string_view(mode)=="a") {
        watched=__real_fopen(log_file.c_str(),mode);return watched;
    }
    if(path==log_file && std::string_view(mode)=="a" && fault==Fault::open) return nullptr;
    auto* file=__real_fopen(path,mode);
    if(path==log_file && std::string_view(mode)=="a") watched=file;
    if(path==asset_file && reset_on_asset_open) simulated_stderr=tty;
    return file;
}
extern "C" int __wrap_fclose(FILE* file) {if(file==watched) {++log_closes;watched=nullptr;const auto result=__real_fclose(file);return fault==Fault::close || fault==Fault::buffer_and_close || fault==Fault::format_and_close ? EOF : result;}return __real_fclose(file);}
extern "C" int __wrap_setvbuf(FILE* file,char* buffer,int mode,std::size_t size) {return file==watched && (fault==Fault::buffer || fault==Fault::buffer_and_close) ? -1 : __real_setvbuf(file,buffer,mode,size);}
extern "C" int __wrap_vfprintf(FILE* file,const char* format,va_list args) {return format_failed(file) ? -1 : __real_vfprintf(file,format,args);}
extern "C" int __wrap_fputc(int value,FILE* file) {return (file==watched && fault==Fault::newline) || (file==tty && emergency_fault==Fault::newline) ? EOF : __real_fputc(value,file);}
extern "C" int __wrap_fflush(FILE* file) {return (file==watched && fault==Fault::flush) || (file==tty && emergency_fault==Fault::flush) ? EOF : __real_fflush(file);}
extern "C" std::uint64_t sceKernelGetProcessTimeWide() {return 1000;}
extern "C" int sceKernelDelayThread(unsigned) {unexpected_runtime_call();}
extern "C" int sceRtcGetCurrentClock(SceDateTime*,int) {unexpected_runtime_call();}
extern "C" int sceRtcGetTime_t(const SceDateTime*,time_t*) {unexpected_runtime_call();}
extern "C" int sceCtrlSetSamplingMode(int) {unexpected_runtime_call();}
extern "C" int sceCtrlPeekBufferPositive(int,SceCtrlData*,int) {unexpected_runtime_call();}
namespace celeste::diagnostic {
void initialize_graphics() {unexpected_runtime_call();}
void finish_graphics() {unexpected_runtime_call();}
void load_textures(const VisualAssets&) {unexpected_runtime_call();}
void load_player_textures(const PlayerAssets&) {unexpected_runtime_call();}
void load_decal_textures(const DecalAssets&) {unexpected_runtime_call();}
std::string draw(const Room&,const Player&,const char*,unsigned,unsigned,const VisualAssets*,PlayerRender*,const DecalAssets*,const NormalOutputPaths*) {unexpected_runtime_call();}
}
int main() {
    if constexpr(!normal_initial_respawn_profile) {
        try {legacy_profile_keeps_stderr_routing();std::cout<<"legacy app log cases=1 failed=0\n";return 0;}
        catch(const std::exception& error) {std::cerr<<error.what()<<'\n';return 1;}
    }
    unsigned failed=0;
    for(auto test:{owned_stream_survives_asset_stdio_and_global_reset,append_preserves_claim_bytes,open_failure_is_checked,buffer_failure_closes_once,
                  buffer_setup_and_cleanup_failure_keep_both_causes,open_failure_persists_without_borrowing_stderr,
                  write_failures_are_checked_parameterized,close_failure_releases_pointer_once,fatal_log_failure_still_persists_independent_sce_receipt,
                  close_failure_is_recorded_independently,fatal_route_stays_owned_after_global_reset,ready_update_survives_asset_stdio_churn,
                  independent_failure_io_errors_propagate_parameterized,caller_reports_full_context_to_emergency_before_returning_two,
                  caller_emergency_errors_propagate_full_context_parameterized}) {
        try {test();} catch(const std::exception& error) {std::cerr<<error.what()<<'\n';++failed;}
    }
    std::cout<<"app log cases=15 failed="<<failed<<"; global-stderr reset is a host test double, not Vita TLS proof\n";return failed ? 1 : 0;
}
