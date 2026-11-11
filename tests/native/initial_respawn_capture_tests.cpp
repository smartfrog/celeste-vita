#include "capture_policy.hpp"
#include "guest_automatic_observer.hpp"
#include "session_profile.hpp"
#include "assets.hpp"
#include <algorithm>
#include <iomanip>
#include <iostream>
#include <limits>
#include <sstream>

using namespace celeste::diagnostic;

namespace {
void expect(bool condition,const char* message) { if(!condition) throw std::runtime_error(message); }
template<class F> void rejects(F action) {
    try { action(); } catch(const std::runtime_error&) { return; }
    throw std::runtime_error("Missing capture must fail");
}
void legacy_policies_parameterized() {
    for(bool automatic:{false,true}) {
        expect(select_capture_policy(automatic,true,false)==CapturePolicy::wall_jump,"Explicit WallJump must take precedence");
        expect(select_capture_policy(automatic,false,true)==CapturePolicy::climb,"Explicit Climb must take precedence");
    }
    expect(select_capture_policy(false,false,false)==CapturePolicy::spawn,"Legacy default must retain spawn capture");
    expect(select_capture_policy(true,false,false)==CapturePolicy::initial_respawn,"Automatic default must wait for initial respawn");
}
void missing_export_rejected() { InitialRespawnCapture capture;rejects([&]{capture.require_complete();}); }
std::string snapshot(const Session& session) {
    const auto& life=*session.lifecycle();
    const auto& p=session.player();
    const auto& pose=session.presentation()->pose();
    const auto& stats=life.stats();
    std::ostringstream out;
    out<<std::setprecision(std::numeric_limits<float>::max_digits10)<<life.context().clock.frame_counter<<' '
       <<life.random().calls()<<' '<<life.time_active()<<' '<<life.raw_time_active()<<' '<<life.phase()<<' '
       <<p.actor().body.position.x<<' '<<p.actor().body.position.y<<' '<<p.state().speed.x<<' '<<p.state().speed.y<<' '
       <<p.state_machine().state()<<' '<<p.death().dead<<' '<<stats.jumps<<' '<<stats.reloads<<' '<<stats.room_deaths<<' '
       <<stats.save_deaths<<' '<<stats.respawn_callbacks<<' '<<stats.wipe_callbacks<<' '<<stats.session_time<<' '
       <<pose.animation<<' '<<pose.animation_frame<<' '<<pose.timer<<' '<<pose.wave<<' '<<pose.scale.x<<' '<<pose.scale.y;
    for(const auto node:pose.hair_nodes) out<<' '<<node.x<<' '<<node.y;
    return out.str();
}
void actual_room(const char* mask_path,const char* spike_path,const char* player_path) {
    const auto mask=read_asset(mask_path,4'000'512),spikes=read_asset(spike_path,8192),frames=read_asset(player_path,65'536);
    Room room(parse_mask(mask,checksum(mask)),parse_spikes(spikes,checksum(spikes)));
    const auto assets=parse_player_assets(frames,checksum(frames));
    auto session=make_session(room.world,&assets.bank);
    auto baseline=make_session(room.world,&assets.bank);
    GuestAutomaticObserver observer(session);
    GuestAutomaticReplay replay;
    Controller controller;
    InitialRespawnCapture capture,missing,empty_export;
    bool saw_wipe=false,saw_respawn=false,saw_dead=false,saw_wrong_phase=false;
    unsigned selected_frame=0,requests=0;
    expect(!initial_respawn_ready(session,0,false) && !capture.request(session,0,false),"Frame0 Respawn14/wipe cannot capture");
    session.lifecycle()->draw();baseline.lifecycle()->draw();
    for(unsigned sample_frame=0;!session.exiting();++sample_frame) {
        const auto sample=controller.sample(replay.next(sample_frame));
        session.step(sample);baseline.step(sample);
        std::cout<<observer.observe(sample_frame,sample,session)<<'\n';
        if(!session.exiting()) {
            const unsigned render_frame=sample_frame+1;
            const auto& life=*session.lifecycle();
            const bool ready=initial_respawn_ready(session,render_frame,sample.reset);
            if(life.wipe()) { saw_wipe=true;expect(!ready,"Active wipe cannot capture"); }
            if(session.player().state_machine().state()==14) { saw_respawn=true;expect(!ready,"Respawn14 cannot capture"); }
            if(session.player().death().dead) { saw_dead=true;expect(!ready,"Dead Player cannot capture"); }
            if(std::string_view(life.phase())!="live") { saw_wrong_phase=true;expect(!ready,"Wrong lifecycle phase cannot capture"); }
            if(life.stats().reloads) expect(!ready,"Later reload cannot masquerade as initial respawn");
            if(ready) {
                expect(!initial_respawn_ready(session,render_frame,true),"Reset sample cannot capture");
                expect(!initial_respawn_ready(life,render_frame,1,false),"Manual reset history cannot capture");
            }
            const bool requested=capture.request(session,render_frame,sample.reset);
            if(requested) {
                ++requests;selected_frame=render_frame;
                expect(ready && missing.request(session,render_frame,false) && empty_export.request(session,render_frame,false),"Capture must select the first eligible actual state");
                rejects([&]{empty_export.confirm_export({});});
            }
            const auto draws=session.lifecycle()->draw();baseline.lifecycle()->draw();
            if(requested) {
                const auto body=session.presentation()->pose().frame;
                expect(std::count_if(draws.begin(),draws.end(),[&](const auto& d){return d.frame==body;})==1,"Selected frame must contain one actual body draw");
                capture.confirm_export("closed fresh export");
                rejects([&]{capture.confirm_export("duplicate export");});
                const auto& stats=life.stats();
                std::cout<<"initial_respawn_capture frame="<<render_frame<<" sample_frame="<<sample_frame
                    <<" state="<<session.player().state_machine().state()<<" dead="<<session.player().death().dead
                    <<" resets="<<session.resets()<<" wipe_active="<<(life.wipe()!=nullptr)<<" phase="<<life.phase()
                    <<" loads="<<stats.loads<<" reloads="<<stats.reloads<<" respawn_callbacks="<<stats.respawn_callbacks
                    <<" wipe_callbacks="<<stats.wipe_callbacks<<" pending_corpses="<<life.pending_corpse()
                    <<" committed_corpses="<<life.committed_corpse()<<" body_draws=1\n";
            }
        }
        expect(snapshot(session)==snapshot(baseline),"Capture observation must not change input/steps/hair/RNG/game state");
    }
    capture.require_complete();rejects([&]{missing.require_complete();});
    expect(requests==1 && selected_frame>0,"Exactly one positive actual frame must be selected");
    expect(saw_wipe && saw_respawn && saw_dead && saw_wrong_phase,"Actual stream must exercise invalid capture phases");
    expect(observer.complete(session) && observer.samples()==365,"Unchanged automatic scenario must still complete");
    std::cout<<observer.completion_record(session)<<'\n';
}
}
int main(int argc,char** argv) {
    try {
        if(argc==4) {actual_room(argv[1],argv[2],argv[3]);return 0;}
        if(argc!=1) throw std::invalid_argument("Expected mask hazards player paths or no arguments");
        legacy_policies_parameterized();missing_export_rejected();
        std::cout<<"capture policy cases=2 failed=0\n";
    } catch(const std::exception& error) {std::cerr<<error.what()<<'\n';return 1;}
}
