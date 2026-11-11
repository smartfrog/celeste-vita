#include "player.hpp"
#include "rooms.hpp"
#include "lifecycle_fixture.hpp"
#include <iostream>
#include <stdexcept>

using namespace celeste;
namespace {
void require(bool condition,const char* message) { if(!condition) throw std::runtime_error(message); }
void up_transition_preserves_actor_and_resets_source_fields() {
    PlayerWorld world;
    Player player(world,{10,5},{35,-60});
    const auto* actor=&player.actor();
    player.before_up_transition();
    require(&player.actor()==actor,"Up transition must retain the Actor");
    const auto& state=player.state();
    require(state.speed.x==0 && state.speed.y==-105 && state.var_jump_speed==-105,"BeforeUpTransition must set source launch speed");
    require(state.auto_jump && state.auto_jump_timer==0 && state.var_jump_timer==0.2f && state.dash_cooldown_timer==0.2f,"BeforeUpTransition must set source jump/Dash timers");
}
void transition_movement_uses_exact_position_and_clears_remainder_at_target() {
    PlayerWorld world;
    Player player(world,{10,5},{0,-60});
    player.frame(1.f/60);
    player.before_up_transition();
    const Vec2 target{10,-9};
    unsigned updates=0;
    while(!player.transition_to(target,1.f/60) && ++updates<100) {}
    require(updates<100,"Transition must reach its actual target");
    require(player.actor().body.position.x==target.x && player.actor().body.position.y==target.y,"Transition movement must reach the target without teleporting");
    require(player.actor().position_remainder().x==0 && player.actor().position_remainder().y==0,"Reaching the target must clear both remainders");
}
void ground_query_is_velocity_independent() {
    Body platform{{0,0},Hitbox{40,5,{}},true};
    PlayerWorld world;world.collision.jump_thrus={&platform};world.safe_ground={&platform};
    Player player(world,{10,0},{0,-105});
    require(player.ground_query(),"OnGround query must see a JumpThru even while rising");
    require(!player.state().on_ground,"Ground query must not overwrite the cached update state");
}
RoomDefinition first_room() { return {"1",{0,0,320,180},49,{19,144},{}}; }
RoomDefinition second_room() { return {"2",{240,-184,320,180},50,{264,-24},{}}; }
void catalog_uses_normalized_world_coordinates() {
    RoomCatalog rooms({first_room(),second_room()});
    const auto* target=rooms.at({276,-12.5f});
    require(target && target->name=="2" && target->bounds.y==-184,"Neighbor lookup must use world coordinates");
    require(rooms.at({276,-4})==nullptr,"Normalized 180px rooms must retain the authored four-pixel gap");
}
void catalog_rejects_duplicate_authored_ids() {
    auto incoming=second_room();incoming.objects={{RoomObjectKind::spike_up,7,{400,-72},40},{RoomObjectKind::spike_up,7,{432,-24},16}};
    try { RoomCatalog rooms({first_room(),incoming}); }
    catch(const std::invalid_argument&) { return; }
    throw std::runtime_error("Duplicate authored room identity must reject");
}
void transition_tag_filter_does_not_update_strawberry() {
    auto incoming=second_room();incoming.objects={{RoomObjectKind::strawberry,11,{336,-144},0}};
    StaticWorld collision;RoomRuntime room(incoming,collision);
    room.update(1.f/60,true);
    const auto& wind=*room.entities[0];
    const auto& berry=std::get<RoomStrawberry>(room.entities[1]->object);
    require(wind.updates==1 && berry.updates==0 && berry.wobble==0,"TransitionUpdate must exclude destination Strawberry");
}
void normal_update_advances_strawberry_components() {
    auto incoming=second_room();incoming.objects={{RoomObjectKind::strawberry,11,{336,-144},0}};
    StaticWorld collision;RoomRuntime room(incoming,collision);
    room.update(0.1f,false);
    const auto& berry=std::get<RoomStrawberry>(room.entities[1]->object);
    require(berry.updates==1 && berry.wobble==0.4f && berry.sprite_frame==1,"Normal updates must advance reached Strawberry sprite/wobble state");
}
void unattached_spring_is_not_silently_supported() {
    auto incoming=second_room();incoming.objects={{RoomObjectKind::spring,12,{360,-40},0}};
    try { StaticWorld collision;RoomRuntime room(incoming,collision); }
    catch(const std::runtime_error& error) { require(std::string(error.what()).find("unattached")!=std::string::npos,"Spring must reject at attachment");return; }
    throw std::runtime_error("An unattached Spring must reject");
}
void unsupported_room_death_fails_before_mutation() {
    PlayerWorld world;world.death_supported=false;Player player(world);
    try { player.die({}); }
    catch(const std::runtime_error&) { require(!player.death().dead,"Rejected Room2 death must not partially mutate the Player");return; }
    throw std::runtime_error("Unproved Room2 death must reject");
}
void dash_crossing_is_guarded_by_actual_player_state() {
    PlayerWorld world;Player player(world);PlayerInput input;input.dash_button={true,true,false};input.aim_y=-1;
    player.frame(0,input);
    try { player.before_up_transition(); }
    catch(const std::runtime_error&) { require(player.state_machine().state()==2,"Guard must inspect actual Dash state");return; }
    throw std::runtime_error("Unproved Dash crossing must reject");
}
void inactive_tagged_entity_still_updates_during_transition() {
    auto incoming=second_room();StaticWorld collision;RoomRuntime room(incoming,collision);
    room.entities[0]->active=false;
    room.update(1.f/60,true);
    require(room.entities[0]->updates==1,"Original TransitionUpdate branch does not check entity Active");
}
void spring_attaches_to_actual_solid_and_keeps_idle_wiggler() {
    auto incoming=second_room();incoming.objects={{RoomObjectKind::spring,12,{360,-40},0}};
    Body floor{{320,-40},Hitbox{100,8,{}},true};StaticWorld collision{{&floor},{}};
    RoomRuntime room(incoming,collision);room.update(0.1f,false);
    const auto& spring=std::get<RoomSpring>(room.entities[1]->object);
    require(spring.attached==&floor && spring.wiggler==0 && spring.updates==1,"Idle Spring must retain its real platform attachment without starting the wiggler");
}
void future_strawberry_pulse_remains_guarded() {
    auto incoming=second_room();incoming.objects={{RoomObjectKind::strawberry,11,{336,-144},0}};
    StaticWorld collision;RoomRuntime room(incoming,collision);
    try { for(unsigned i=0;i<36;++i) room.update(0.1f,false); }
    catch(const std::runtime_error& error) { require(std::string(error.what()).find("OnAnimate pulse")!=std::string::npos,"Pulse must fail at its reached callback");return; }
    throw std::runtime_error("Unproved Strawberry pulse must reject");
}
void five_phase_observer_samples_one_clock_and_rejects_reentry() {
    native_test::LifecycleFixture fixture;FirstRoomSession session(fixture.world,fixture.frames);
    unsigned phases=0;bool rejected=false;
    session.step(1.f/60,{},[&](SessionPhase phase,const FirstRoomSession& observed) {
        ++phases;require(observed.context().clock.frame_counter==1,"Observer must not sample another frame");
        if(phase==SessionPhase::before_frame) {
            try { session.step(1.f/60,{}); }
            catch(const std::logic_error&) { rejected=true; }
        }
    });
    require(phases==5 && rejected,"Five read-only phases must not permit recursive simulation");
}
void freeze_crossing_is_guarded_without_dash_state() {
    PlayerWorld world;PlayerFrameContext context;Player player(world,{},{},PlayerProfile::default_static,&context);
    context.clock.freeze(0.05f);
    try { player.before_up_transition(); }
    catch(const std::runtime_error&) { require(player.state_machine().state()==0 && context.clock.freeze_timer>0,"Freeze guard must not depend on a Dash state");return; }
    throw std::runtime_error("Unproved freeze crossing must reject");
}
}
int main() {
    try {
        up_transition_preserves_actor_and_resets_source_fields();
        transition_movement_uses_exact_position_and_clears_remainder_at_target();
        ground_query_is_velocity_independent();
        catalog_uses_normalized_world_coordinates();
        catalog_rejects_duplicate_authored_ids();
        transition_tag_filter_does_not_update_strawberry();
        normal_update_advances_strawberry_components();
        unattached_spring_is_not_silently_supported();
        unsupported_room_death_fails_before_mutation();
        dash_crossing_is_guarded_by_actual_player_state();
        inactive_tagged_entity_still_updates_during_transition();
        spring_attaches_to_actual_solid_and_keeps_idle_wiggler();
        future_strawberry_pulse_remains_guarded();
        five_phase_observer_samples_one_clock_and_rejects_reentry();
        freeze_crossing_is_guarded_without_dash_state();
        std::cout<<"15 room transition behaviors passed\n";
    } catch(const std::exception& error) { std::cerr<<error.what()<<'\n';return 1; }
}
