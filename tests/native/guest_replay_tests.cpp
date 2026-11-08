#include "guest_replay.hpp"
#include "assets.hpp"
#include <iostream>
#include <stdexcept>

using namespace celeste::diagnostic;

namespace {
void expect(bool value, const char* message) { if (!value) throw std::runtime_error(message); }
template<class F> void rejects(F action) {
    try { action(); } catch (const std::invalid_argument&) { return; }
    throw std::runtime_error("Expected invalid_argument");
}
unsigned bits(Controls c) {
    return (c.left?0x80u:0u)|(c.right?0x20u:0u)|(c.up?0x10u:0u)|(c.down?0x40u:0u)|
        (c.cross?0x4000u:0u)|(c.triangle?0x1000u:0u)|(c.start?8u:0u)|(c.square?0x8000u:0u)|(c.l?0x100u:0u);
}
void authoritative_changes() {
    const unsigned frames[]{118,120,124,132,134,136,144,148,162,164,166,168,171,173,175,190,192,243,245,247,249};
    const unsigned buttons[]{0x80,0x4080,0x80,0x180,0x100,0x110,0x100,0,0x1000,0,0x4000,0,0x10,0x8010,0x10,0,0x20,0,0x1000,0,8};
    GuestReplay replay;
    unsigned index=0, previous=0;
    for(unsigned frame=0;frame<guest_replay_frames;++frame) {
        const auto current=bits(replay.next(frame));
        if(current!=previous) {
            expect(index<21 && frames[index]==frame && buttons[index]==current,"Recorded raw input changes differ");
            ++index;
        }
        previous=current;
    }
    expect(index==21,"All recorded changes must execute");
}
void neutral_startup() {
    GuestReplay replay;
    for(unsigned frame=0;frame<118;++frame) expect(bits(replay.next(frame))==0,"No input before first event");
}
void rising_edges_and_terminal_start() {
    GuestReplay replay;
    Controller controller;
    unsigned jumps=0,resets=0,dashes=0,exits=0;
    for(unsigned frame=0;frame<guest_replay_frames;++frame) {
        const auto sample=controller.sample(replay.next(frame));
        jumps+=sample.player.jump.pressed; resets+=sample.reset; dashes+=sample.player.dash_button.pressed; exits+=sample.exit;
        expect(!sample.exit || frame==249,"Start only at bounded end");
    }
    expect(jumps==2 && resets==2 && dashes==1 && exits==1,"Edges must not repeat while held");
}
void skipped_tick_rejected() { GuestReplay replay; rejects([&]{replay.next(1);}); }
void duplicate_tick_rejected() { GuestReplay replay; replay.next(0); rejects([&]{replay.next(0);}); }
void exhausted_replay_rejected() {
    GuestReplay replay;
    for(unsigned frame=0;frame<guest_replay_frames;++frame) replay.next(frame);
    rejects([&]{replay.next(guest_replay_frames);});
}
void frozen_ticks_still_sample_release() {
    GuestReplay replay;
    Controller controller;
    for(unsigned frame=0;frame<=178;++frame) {
        const auto sample=controller.sample(replay.next(frame));
        if(frame==175) expect(sample.player.dash_button.released && !sample.player.dash_button.held,"Square release during freeze");
        if(frame>175) expect(!sample.player.dash_button.released,"Frozen release must not repeat");
    }
}
void actual_room(const char* mask_path,const char* spike_path,const char* player_path) {
    const auto mask=read_asset(mask_path,4'000'512),spikes=read_asset(spike_path,8192),frames=read_asset(player_path,65'536);
    Room room(parse_mask(mask,checksum(mask)),parse_spikes(spikes,checksum(spikes)));
    const auto assets=parse_player_assets(frames,checksum(frames));
    Session session(room.world,{19,144},&assets.bank,0);
    Controller controller;
    GuestReplay replay;
    bool jump=false,climb=false,drain=false,held=false,release=false,land=false,freeze=false,thaw=false,launch=false,dash_done=false,death=false,reset=false;
    unsigned samples=0;
    for(unsigned frame=0;frame<guest_replay_frames;++frame) {
        const auto sample=controller.sample(replay.next(frame));
        ++samples;
        const bool frozen=session.player().clock().freeze_timer>0;
        session.step(sample);
        const auto& p=session.player();
        session.presentation()->draw(session.projection());
        jump=jump || p.jump_count()>0;
        climb=climb || p.state_machine().state()==1;
        drain=drain || (climb && p.state().stamina<109 && p.state().speed.y<0 && session.presentation()->pose().animation_frame>0);
        held=held || (drain && sample.player.grab && sample.player.y==0 && p.state().speed.y==0);
        release=release || (held && !sample.player.grab && p.state_machine().state()==0);
        land=land || (release && p.state().on_ground);
        freeze=freeze || p.clock().freeze_timer>0;
        thaw=thaw || (frozen && p.clock().freeze_timer<=0);
        launch=launch || p.state().dash_events>0;
        dash_done=dash_done || (launch && p.state_machine().state()==0);
        death=death || p.death().dead;
        reset=reset || (death && sample.reset && !p.death().dead && session.resets()==2);
        if(frame==175) expect(frozen && sample.player.dash_button.released,"Real frozen tick must sample release");
        if(frame==143) expect(drain && p.state_machine().state()==1 && p.grab_held(),"Original moving Climb capture condition");
        if(session.exiting()) expect(frame==249,"Guest exit frame");
    }
    expect(samples==250 && session.exiting() && jump && climb && drain && held && release && land && freeze && thaw && launch && dash_done && death && reset,"Actual native scenario must complete, not synthetic state");
    std::cout<<"actual guest fixture samples="<<samples<<" exit=249 Jump Climb drain hold release land Dash freeze thaw launch death Triangle Start verified\n";
}
}
int main(int argc,char** argv) {
    try {
        if(argc==4) { actual_room(argv[1],argv[2],argv[3]); return 0; }
        if(argc!=1) throw std::invalid_argument("Expected mask hazards player paths or no arguments");
        for(auto test:{authoritative_changes,neutral_startup,rising_edges_and_terminal_start,skipped_tick_rejected,duplicate_tick_rejected,exhausted_replay_rejected,frozen_ticks_still_sample_release}) test();
        std::cout<<"guest replay cases=7 failed=0\n";
        return 0;
    } catch(const std::exception& error) { std::cerr<<error.what()<<'\n'; return 1; }
}
