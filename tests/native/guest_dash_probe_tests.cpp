#include "guest_dash_probe_observer.hpp"
#include "lifecycle_fixture.hpp"
#include <iostream>

using namespace celeste;
using namespace celeste::diagnostic;
namespace {
void require(bool value,const char* message) {if(!value) throw std::runtime_error(message);}
template<class F> void rejects(F action) {
    try {action();}catch(const std::exception&){return;}
    throw std::runtime_error("Expected Dash probe contract rejection");
}
struct Run {
    native_test::LifecycleFixture fixture;
    Session session{fixture.world,fixture.frames};
    GuestDashProbeObserver observer{session,"test-revision",std::string(64,'a')};
    Controller controller;
    bool exported=false;
    std::string synthetic_export(unsigned frame) const {
        return "frame_saved path=ux0:data/celeste_native_room-test-revision-dash-probe.ppm revision=test-revision probe_fixture=first_room_dash_trails_v1 probe_fixture_sha256="+
            std::string(64,'a')+" frame="+std::to_string(frame)+" capture=dash_trails stage=after_draw_glFinish_GL_BACK_RGBA_CPU_before_swap native_probe_checks=1 trail_probe=diagnostic_rgba_fbo other_captured_tiles_preserved=1";
    }
    std::string step(unsigned frame,bool capture=true,bool close_export=true) {
        auto controls=dash_probe_controls(frame);controls.start=frame==359;
        const auto sample=controller.sample(controls);session.step(sample);
        const auto record=observer.observe(frame,controls,sample,session);
        if(!session.exiting() && capture) session.trails().before_render(*session.presentation(),session.projection(),[](unsigned,const auto&){});
        const auto counts=probe_trail_counts(session);
        if(close_export && !exported && counts.committed==3 && counts.captured==3) {
            observer.confirm_export(synthetic_export(frame+1),session);exported=true;
        }
        return record;
    }
    void all(bool capture=true,bool close_export=true) {for(unsigned frame=0;frame<360;++frame) step(frame,capture,close_export);}
    unsigned three_captured() {
        for(unsigned frame=0;frame<100;++frame) {
            step(frame,true,false);
            const auto counts=probe_trail_counts(session);
            if(counts.committed==3 && counts.captured==3) return frame+1;
        }
        throw std::runtime_error("Fixture never produced three captured trails");
    }
};
void actual_samples_and_terminal_no_step() {
    Run run;
    for(unsigned frame=0;frame<360;++frame) {
        const auto line=run.step(frame);
        require(probe_record_field(line,"frame",std::to_string(frame)),"Every ordered observed sample must be recorded");
        require(probe_record_field(line,"dash",frame==40 ? "1" : "0"),"Observed Dash input must match the unchanged fixture");
        require(probe_record_field(line,"aim_y",frame>=40 && frame<60 ? "-1" : "0"),"Observed aim must match actual Controller sampling");
    }
    require(run.observer.complete(run.session),"Real input-driven Session must complete the logical probe gates");
    require(run.session.lifecycle()->context().clock.frame_counter==359,"Terminal sample must not advance the clock");
}
void observation_order_parameterized() {
    for(unsigned bad:{1u,360u}) {Run run;rejects([&]{run.step(bad);});}
}
void duplicate_observation() {Run run;run.step(0);rejects([&]{run.step(0);});}
void wrong_raw_controls() {
    Run run;Controls controls;controls.square=true;
    const auto sample=run.controller.sample(controls);run.session.step(sample);
    rejects([&]{run.observer.observe(0,controls,sample,run.session);});
}
void wrong_sample_aim() {
    Run run;Controls controls;auto sample=run.controller.sample(controls);sample.player.aim_x=1;run.session.step(sample);
    rejects([&]{run.observer.observe(0,controls,sample,run.session);});
}
void unexpected_reset() {
    Run run;Controls controls;controls.triangle=true;const auto sample=run.controller.sample(controls);run.session.step(sample);
    rejects([&]{run.observer.observe(0,controls,sample,run.session);});
}
void terminal_extra_clock_step() {
    Run run;for(unsigned frame=0;frame<359;++frame) run.step(frame);
    Controls controls;controls.start=true;const auto terminal=run.controller.sample(controls);
    run.session.step({});run.session.step(terminal);
    rejects([&]{run.observer.observe(359,controls,terminal,run.session);});
}
void clock_step_after_terminal_cannot_complete() {
    Run run;run.all();run.session.lifecycle()->step(1.f/60,{});
    require(!run.observer.complete(run.session),"Completion must recheck the final observed clock");
}
void missing_capture_cannot_complete() {Run run;run.all(false,false);require(!run.observer.complete(run.session),"Uncaptured trails cannot complete a probe");}
void missing_fresh_export_cannot_complete() {Run run;run.all(true,false);require(!run.observer.complete(run.session),"Sample count alone cannot complete a probe");}
void incomplete_native_export_parameterized() {
    for(const char* field:{"native_probe_checks=1","revision=test-revision","probe_fixture_sha256=","stage=after_draw_glFinish_GL_BACK_RGBA_CPU_before_swap",
                          "trail_probe=diagnostic_rgba_fbo","other_captured_tiles_preserved=1"}) {
        Run run;const auto frame=run.three_captured();auto receipt=run.synthetic_export(frame);
        receipt.erase(receipt.find(field),std::string(field).size());
        rejects([&]{run.observer.confirm_export(receipt,run.session);});
    }
}
void mismatched_native_export_parameterized() {
    for(const auto& field:{std::pair<const char*,const char*>{"frame=","frame=0 ignored_frame="},
                          {"revision=test-revision","revision=old-revision"},{"probe_fixture=first_room_dash_trails_v1","probe_fixture=wrong"},
                          {"capture=dash_trails","capture=spawn"},{"-dash-probe.ppm",".ppm"},
                          {"native_probe_checks=1","native_probe_checks=0 native_probe_checks=1"}}) {
        Run run;const auto frame=run.three_captured();auto receipt=run.synthetic_export(frame);
        receipt.replace(receipt.find(field.first),std::string(field.first).size(),field.second);
        rejects([&]{run.observer.confirm_export(receipt,run.session);});
    }
}
void repeated_export_is_rejected() {
    Run run;const auto frame=run.three_captured();const auto receipt=run.synthetic_export(frame);
    run.observer.confirm_export(receipt,run.session);rejects([&]{run.observer.confirm_export(receipt,run.session);});
}
void no_three_trails_export_is_rejected() {Run run;run.step(0);rejects([&]{run.observer.confirm_export(run.synthetic_export(1),run.session);});}
void diagnostic_record_cannot_confirm_a_normal_export() {
    Run run;const auto frame=run.three_captured();
    const auto diagnostic="guest_dash_probe_diagnostic path=ux0:data/celeste_native_room-test-revision-dash-probe-diagnostic.trail.rgba revision=test-revision frame="+
        std::to_string(frame)+" diagnostic_only=1 accepted_frame=0 fresh_export=0 native_probe_checks=0 full_completion=0";
    rejects([&]{run.observer.confirm_export(diagnostic,run.session);});
}
void teardown_and_log_close_gates_parameterized() {
    for(unsigned stop:{0u,1u,2u,3u}) {
        Run run;run.all();GuestDashProbeCompletion completion;
        if(stop>=1) completion.record_run(run.observer,run.session);
        if(stop>=2) completion.graphics_finished();
        if(stop>=3) completion.logged();
        rejects([&]{completion.closed_receipt();});
    }
}
void completion_requires_valid_run() {Run run;run.all(true,false);GuestDashProbeCompletion completion;rejects([&]{completion.record_run(run.observer,run.session);});}
void completion_log_requires_teardown() {Run run;run.all();GuestDashProbeCompletion completion;completion.record_run(run.observer,run.session);rejects([&]{completion.log_record();});}
void completion_requires_logged_summary() {
    Run run;run.all();GuestDashProbeCompletion completion;completion.record_run(run.observer,run.session);completion.graphics_finished();
    rejects([&]{completion.log_closed();});
}
void successful_closed_receipt() {
    Run run;run.all();GuestDashProbeCompletion completion;completion.record_run(run.observer,run.session);completion.graphics_finished();
    require(probe_record_field(completion.log_record(),"full_completion","1"),"Verified completion must be logged after teardown");
    completion.logged();completion.log_closed();const auto receipt=completion.closed_receipt();
    for(const auto& field:{std::pair<const char*,const char*>{"samples","360"},{"exit_frame","359"},{"graphics_teardown","1"},{"log_closed","1"},{"capture","dash_trails"},{"status","0"}})
        require(probe_record_field(receipt,field.first,field.second),"Closed receipt is missing its logical completion evidence");
    require(receipt.size()<=1024,"Closed receipt must stay bounded");
}
void mode_specific_paths_do_not_collide() {
    require(dash_probe_receipt_path("complete","r")=="ux0:data/celeste_native_room-complete-r-dash-probe.txt","Probe completion needs its own mode suffix");
    require(dash_probe_receipt_path("failure","r")=="ux0:data/celeste_native_room-failure-r-dash-probe.txt","Probe failure needs its own mode suffix");
}
}
int main() {
    try {
        actual_samples_and_terminal_no_step();observation_order_parameterized();duplicate_observation();wrong_raw_controls();wrong_sample_aim();
        unexpected_reset();terminal_extra_clock_step();clock_step_after_terminal_cannot_complete();missing_capture_cannot_complete();missing_fresh_export_cannot_complete();
        incomplete_native_export_parameterized();mismatched_native_export_parameterized();repeated_export_is_rejected();no_three_trails_export_is_rejected();diagnostic_record_cannot_confirm_a_normal_export();
        teardown_and_log_close_gates_parameterized();completion_requires_valid_run();completion_log_requires_teardown();completion_requires_logged_summary();successful_closed_receipt();mode_specific_paths_do_not_collide();
        std::cout<<"Dash probe producer gates passed; synthetic host exports are not GPU proof\n";
    }catch(const std::exception& error){std::cerr<<error.what()<<'\n';return 1;}
}
