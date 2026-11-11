#include "guest_automatic_replay.hpp"
#include "guest_automatic_observer.hpp"
#include "session_profile.hpp"
#include "assets.hpp"
#include <iostream>
#include <stdexcept>

using namespace celeste::diagnostic;

namespace {
void expect(bool value,const char* message) { if(!value) throw std::runtime_error(message); }
template<class F> void rejects(F action) {
    try { action(); } catch(const std::invalid_argument&) { return; }
    throw std::runtime_error("Expected invalid_argument");
}
void raw_edges_and_exit() {
    GuestAutomaticReplay replay;
    Controller controller;
    unsigned presses=0,exits=0;
    for(unsigned frame=0;frame<guest_automatic_samples;++frame) {
        const auto controls=replay.next(frame);
        expect(!controls.up && !controls.down && !controls.triangle && !controls.square && !controls.l,
               "Automatic fixture may only supply raw Left/Right/C and terminal Start");
        const auto sample=controller.sample(controls);
        presses+=sample.player.jump.pressed;
        exits+=sample.exit;
        expect(!sample.reset && (!sample.exit || frame==364),"No reset or early exit");
    }
    expect(presses==5 && exits==1,"Held C must preserve original source edges, not synthesize actual Jumps");
}
void skipped_tick_rejected() { GuestAutomaticReplay replay; rejects([&]{replay.next(1);}); }
void duplicate_tick_rejected() { GuestAutomaticReplay replay; replay.next(0); rejects([&]{replay.next(0);}); }
void exhausted_fixture_rejected() {
    GuestAutomaticReplay replay;
    for(unsigned frame=0;frame<guest_automatic_samples;++frame) replay.next(frame);
    rejects([&]{replay.next(guest_automatic_samples);});
}
void actual_room(const char* mask_path,const char* spike_path,const char* player_path,const std::string& mode) {
    const auto mask=read_asset(mask_path,4'000'512),spikes=read_asset(spike_path,8192),frames=read_asset(player_path,65'536);
    Room room(parse_mask(mask,checksum(mask)),parse_spikes(spikes,checksum(spikes)));
    const auto assets=parse_player_assets(frames,checksum(frames));
    if(mode=="manual-session") {
        Session manual(room.world,{19,144},&assets.bank,0);
        rejects([&]{GuestAutomaticObserver observer(manual);});
        std::cout<<"legacy manual Session correctly rejected by automatic observer\n";
        return;
    }
    if(mode!="normal" && mode!="no-jump" && mode!="manual-reset") throw std::invalid_argument("Unknown automatic test mode");
    auto session=make_session(room.world,&assets.bank);
    expect(automatic_session_profile && session.lifecycle(),"Guest automatic must select the production FirstRoomSession constructor");
    GuestAutomaticObserver observer(session);
    Controller controller;
    GuestAutomaticReplay replay;
    session.lifecycle()->draw();
    for(unsigned frame=0;!session.exiting();++frame) {
        auto controls=replay.next(frame);
        if(mode=="no-jump") controls.cross=false;
        if(mode=="manual-reset" && frame==10) controls.triangle=true;
        const auto sample=controller.sample(controls);
        const auto clock=session.lifecycle()->context().clock.frame_counter;
        session.step(sample);
        std::cout<<observer.observe(frame,sample,session)<<'\n';
        if(session.exiting()) expect(session.lifecycle()->context().clock.frame_counter==clock,"Exit must not execute an extra Scene update");
        else session.lifecycle()->draw();
    }
    std::cout<<observer.completion_record(session)<<'\n';
    expect(observer.complete(session)==(mode=="normal"),"Completion must depend on observed actual lifecycle, not sample count");
    expect(observer.samples()==365,"Exactly 365 samples");
    if(mode=="normal") {
        const auto& stats=session.lifecycle()->stats();
        expect(stats.reloads==2 && stats.room_deaths==2 && stats.save_deaths==2 && stats.jumps==3,
               "Actual Session must complete both automatic cycles and its third Jump");
        expect(!session.player().death().dead && session.player().state_machine().state()==0,"Final Player must be alive in Normal");
        expect(session.resets()==0,"Automatic scenario must never reset manually");
    }
}
}
int main(int argc,char** argv) {
    try {
        if(argc==4 || argc==5) { actual_room(argv[1],argv[2],argv[3],argc==5 ? argv[4] : "normal");return 0; }
        if(argc!=1) throw std::invalid_argument("Expected mask hazards player and optional negative mode");
        for(auto test:{raw_edges_and_exit,skipped_tick_rejected,duplicate_tick_rejected,exhausted_fixture_rejected}) test();
        std::cout<<"guest automatic input cases=4 failed=0\n";
    } catch(const std::exception& error) { std::cerr<<error.what()<<'\n';return 1; }
}
