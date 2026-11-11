#include "lifecycle.hpp"
#include "lifecycle_fixture.hpp"
#include <iostream>
#include <stdexcept>
#include <limits>
#include <type_traits>

using namespace celeste;

namespace {
static_assert(!std::is_move_constructible_v<FirstRoomSession>);
static_assert(!std::is_move_constructible_v<Player>);
static_assert(!std::is_move_constructible_v<PlayerPresentation>);
void require(bool condition, const char* message) {
    if (!condition) throw std::runtime_error(message);
}
using Fixture=native_test::LifecycleFixture;
void automatic_cycles_parameterized() {
    for (bool checkpoint : {false,true}) {
        Fixture f;
        FirstRoomSession session(f.world,f.frames,checkpoint);
        const auto* clock=&session.context().clock;
        const auto* jump=&session.context().jump;
        const auto* random=&session.random();
        bool previous=false;
        for (unsigned cycle=0;cycle<2;++cycle) {
            const auto* old_player=&session.player();
            const auto* old_presentation=&session.presentation();
            const auto* old_spike=session.world().spikes.front();
            for (unsigned guard=0;session.player().state_machine().state()==14 && guard<60;++guard) {
                session.step(1.f/60,{});
                session.draw();
            }
            require(session.player().state_machine().state()==0,"Respawn tween must invoke Normal callback");
            const auto jumps=session.stats().jumps;
            for (unsigned guard=0;!session.player().death().dead && guard<180;++guard) {
                PlayerInput input; input.x=1;
                input.jump={guard==0,guard==0 && !previous,guard!=0 && previous};
                previous=input.jump.held;
                session.step(1.f/60,input); session.draw();
            }
            require(session.stats().jumps==jumps+1,"First action must execute an actual Jump");
            require(session.player().death().dead && session.pending_corpse(),"Hazard must defer corpse ownership");
            const auto removed_frame=session.player().clock().frame_counter;
            for (unsigned guard=0;session.stats().reloads==cycle && guard<240;++guard) {
                session.step(1.f/60,{}); session.draw();
            }
            require(session.stats().reloads==cycle+1 && session.player().state_machine().state()==14,"Wipe callback must reconstruct Respawn14 automatically");
            require(&session.player()!=old_player && &session.presentation()!=old_presentation && session.world().spikes.front()!=old_spike,
                    "Reload must reconstruct Player, presentation/hair and room hazards, not teleport old instances");
            require(session.context().clock.frame_counter>removed_frame,"Persistent clock must advance while removed Player is not framed");
            require(&session.context().clock==clock && &session.context().jump==jump && &session.random()==random,"Global clock/input/RNG identities must survive Reload");
            require(session.world().collision.solids.front()==&f.floor,"Global collision must survive Reload");
            require(session.stats().session_deaths==(checkpoint ? cycle+1 : 0),"Only source first-level/default Reload resets session deaths");
            require(session.stats().room_deaths==cycle+1 && session.stats().save_deaths==cycle+1,"Room/save death counts must not reset");
            require(session.stats().corpse_adds==cycle+1 && session.stats().corpse_commits==cycle+1 && session.stats().corpse_removes==cycle+1,
                    "Deferred corpse ownership must commit and unload exactly once");
        }
    }
}
void invalid_scene_delta_parameterized() {
    for(float delta:{-1.f,std::numeric_limits<float>::infinity(),std::numeric_limits<float>::quiet_NaN(),100000000.f}) {
        Fixture f;
        FirstRoomSession session(f.world,f.frames);
        try { session.step(delta,{}); }
        catch(const std::invalid_argument&) {
            require(session.context().clock.frame_counter==0 && session.time_active()==0,"Invalid delta must fail before mutating Scene/input clocks");
            continue;
        }
        throw std::runtime_error("Invalid Scene delta was accepted");
    }
}
void borrowed_player_rejects_duplicate_sampled_update() {
    Fixture f;
    PlayerFrameContext context;
    Player player(f.world,{19,144},{},PlayerProfile::default_static,&context);
    context.sample(1.f/60,{});
    player.update_sampled({});
    try { player.update_sampled({}); }
    catch(const std::logic_error&) { return; }
    throw std::runtime_error("Borrowed Player updated twice from one sample");
}
void moving_global_solid_is_rejected() {
    Fixture f;
    FirstRoomSession session(f.world,f.frames);
    f.floor.position.x+=1;
    try { session.step(1.f/60,{}); }
    catch(const std::invalid_argument&) {
        require(session.context().clock.frame_counter==0,"Unsupported moving world must fail before the frame");
        return;
    }
    throw std::runtime_error("Moving global Solid was accepted");
}
void normal_callback_retains_committed_foreground_slot_until_next_scene_boundary() {
    Fixture f;
    FirstRoomSession session(f.world,f.frames);
    for(int tick=0;tick<36;++tick) session.step(1.f/60,{});
    require(session.player().state_machine().state()==0 && session.foreground_owner(),
            "Depth changes during a tween must not sort the committed EntityList during Update");
    session.step(1.f/60,{});
    require(!session.foreground_owner(),"Next BeforeUpdate must sort Normal back behind foreground tiles");
}
}
int main() {
    try {
        automatic_cycles_parameterized(); invalid_scene_delta_parameterized(); borrowed_player_rejects_duplicate_sampled_update();
        moving_global_solid_is_rejected();
        normal_callback_retains_committed_foreground_slot_until_next_scene_boundary();
        std::cout<<"automatic lifecycle and context guards passed\n";
    }
    catch (const std::exception& error) { std::cerr<<error.what()<<'\n'; return 1; }
}
