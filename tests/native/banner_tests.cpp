#include "draw_order.hpp"
#include "lifecycle_fixture.hpp"
#include <algorithm>
#include <iostream>
#include <limits>
#include <stdexcept>

using namespace celeste;
using namespace celeste::draw_order;
namespace {
void require(bool condition,const char* message) { if(!condition) throw std::runtime_error(message); }
RoomDefinition first_room(int seed=49) {
    native_test::LifecycleFixture fixture;
    RoomDefinition room{"1",{0,0,320,180},seed,{19,144},{}};
    for(const auto& spike:fixture.spikes) {
        const bool up=spike.direction()==SpikeDirection::up;
        room.objects.push_back({up?RoomObjectKind::spike_up:RoomObjectKind::spike_left,
            int(room.objects.size()),spike.body().position,int(up?spike.body().collider->width:spike.body().collider->height)});
    }
    return room;
}
RoomDefinition second_room(int seed=50) {
    return {"2",{240,-184,320,180},seed,{264,-24},{
        {RoomObjectKind::jump_thru,0,{248,-24},40},
        {RoomObjectKind::spike_up,1,{400,-72},40},
        {RoomObjectKind::spike_up,2,{432,-24},16},
        {RoomObjectKind::spike_up,3,{448,-16},16}}};
}
AuthoredDecalOwners visual_owners(const RoomDefinition& room,int background,int foreground) {
    AuthoredDecalOwners result{&room,{},background,foreground};
    for(const bool back:{true,false}) for(int ordinal=0;ordinal<(back?background:foreground);++ordinal)
        result.owners.push_back({OwnerKind::decal,0x6000000000000000ull | (std::uint64_t(back?1:2)<<24) | std::uint64_t(ordinal+1),
            ordinal,&room,back?9000:-10500,unsigned(ordinal),true,false,true,"fixture_banner"});
    return result;
}
void initialization_uses_detached_constructor_boundary_parameterized() {
    for(const int seed:{49,50,12345}) {
        const auto definition=seed==50?second_room(seed):first_room(seed);
        auto metadata=visual_owners(definition,seed==50?4:5,seed==50?0:2);
        std::reverse(metadata.owners.begin(),metadata.owners.end());
        StaticWorld collision;
        RoomRuntime baseline(definition,collision);
        RoomRuntime room(definition,collision,false,&metadata);
        PresentationRandom expected(seed);
        unsigned constructor_calls=0;
        for(const auto& object:definition.objects)
            if(object.kind==RoomObjectKind::spike_up || object.kind==RoomObjectKind::spike_left)
                for(int piece=0;piece<object.size/8;++piece) { expected.next(1);++constructor_calls; }
        require(constructor_calls==(seed==50?9u:19u),"Fixture must reach the actual constructor boundary");
        std::vector<DrawOwner> added=metadata.owners;
        std::sort(added.begin(),added.end(),[](const DrawOwner& a,const DrawOwner& b) {
            return a.sort_depth_band!=b.sort_depth_band ? a.sort_depth_band<b.sort_depth_band : a.authored_id<b.authored_id;
        });
        require(room.banners().size()==added.size(),"Every Banner must have one room-owned phase");
        for(const auto& owner:added)
            require(room.banner_phase(owner.identity)==float(expected.next_double()),"Banner phases must follow foreground then background Added order");
        require(room.scoped_random.state_words()==baseline.scoped_random.state_words() && room.scoped_random.calls()==baseline.scoped_random.calls(),
            "Detached visual initialization must not advance the physical generator");
        require(room.random_events==baseline.random_events,"The copied observer must not publish visual draws as physical RNG events");
        require(room.scoped_random.calls()==(seed==50?15u:19u),"JumpThru Awake must retain its unchanged physical consumption");
    }
}
void normal_update_uses_repeated_source_float_addition() {
    const auto definition=first_room();auto metadata=visual_owners(definition,1,0);
    StaticWorld collision;RoomRuntime room(definition,collision,false,&metadata);
    const auto identity=metadata.owners.front().identity;
    float expected=room.banner_phase(identity);
    for(int frame=0;frame<257;++frame) {
        const float delta=frame%2==0?1.f/60:0.007f;
        expected+=delta*1.f;
        room.update(delta,false);
        require(room.banner_phase(identity)==expected,"Normal Banner update must add the sampled Source float delta exactly once");
    }
}
void transition_update_pauses_banner_phase() {
    const auto definition=second_room();auto metadata=visual_owners(definition,4,0);
    StaticWorld collision;RoomRuntime room(definition,collision,false,&metadata);
    const auto identity=metadata.owners.front().identity;const auto initial=room.banner_phase(identity);
    room.update(0.1f,true);
    require(room.banner_phase(identity)==initial,"Transition tag filtering must pause Banner components");
}
struct SessionFixture {
    native_test::LifecycleFixture physical;
    RoomCatalog catalog{{first_room(),second_room()}};
    std::vector<AuthoredDecalOwners> visual{visual_owners(catalog.definitions()[0],5,2),visual_owners(catalog.definitions()[1],4,0)};
    SessionFixture() {
        for(auto& owner:visual[1].owners) owner.identity|=std::uint64_t(2)<<32;
    }
};
const RoomRuntime& first_instance(const FirstRoomSession& session) {
    for(const auto& entry:session.room_roster()) if(entry.room) return *entry.room;
    throw std::runtime_error("Session room instance missing");
}
void session_initializes_before_the_first_update() {
    SessionFixture fixture;
    FirstRoomSession session(fixture.physical.world,fixture.physical.frames,false,7,&fixture.catalog,&fixture.visual);
    const auto& instance=first_instance(session);
    require(instance.banners().size()==7,"The actual room load must initialize visual owners before the first frame");
    const auto identity=fixture.visual.front().owners.front().identity;
    const float initial=instance.banner_phase(identity);
    session.step(0.007f,{});
    require(instance.banner_phase(identity)==initial+session.context().clock.delta,"The actual catalog branch must update banners once with sampled delta");
}
void repeated_draw_does_not_advance_banner_phase() {
    SessionFixture fixture;
    FirstRoomSession session(fixture.physical.world,fixture.physical.frames,false,7,&fixture.catalog,&fixture.visual);
    session.step(1.f/60,{});
    const auto& room=first_instance(session);const auto identity=fixture.visual.front().owners.front().identity;
    const auto before=room.banner_phase(identity);const auto random=session.random().state_words();
    session.draw();session.draw();
    require(room.banner_phase(identity)==before && session.random().state_words()==random,"Repeated drawing must not advance Banner phases or global RNG");
}
void natural_dash_freeze_pauses_banner_phase() {
    SessionFixture fixture;
    FirstRoomSession session(fixture.physical.world,fixture.physical.frames,false,7,&fixture.catalog,&fixture.visual);
    for(unsigned frame=0;frame<40;++frame) session.step(1.f/60,{});
    PlayerInput dash;dash.dash_button={true,true,false};dash.aim_x=1;
    session.step(1.f/60,dash);
    require(session.context().clock.freeze_timer>0,"Actual Dash must enter the natural freeze path");
    const auto& room=first_instance(session);const auto identity=fixture.visual.front().owners.front().identity;
    const auto before=room.banner_phase(identity);
    session.step(1.f/60,{});
    require(!session.scene_ran() && room.banner_phase(identity)==before,"A frozen sampled frame must not update Banner phases");
}
void natural_corpse_frames_pause_then_reload_new_banner_owners() {
    SessionFixture fixture;
    FirstRoomSession session(fixture.physical.world,fixture.physical.frames,false,7,&fixture.catalog,&fixture.visual);
    const auto identity=fixture.visual.front().owners.front().identity;
    const float initial=first_instance(session).banner_phase(identity);
    const auto old_scope=first_instance(session).scoped_random.object_identity();
    for(unsigned frame=0;frame<40;++frame) session.step(1.f/60,{});
    for(unsigned frame=0;!session.player().death().dead && frame<180;++frame) {
        PlayerInput input;input.x=1;input.jump={frame==0,frame==0,frame==1};
        session.step(1.f/60,input);
    }
    require(session.pending_corpse(),"Natural hazard contact must queue the corpse");
    const float at_death=first_instance(session).banner_phase(identity);
    require(at_death>initial,"Banner must have advanced before hazard contact");
    unsigned committed_frames=0,frozen_frames=0;
    for(unsigned frame=0;session.stats().reloads==0 && frame<240;++frame) {
        session.step(1.f/60,{});
        if(session.stats().reloads==0) {
            require(first_instance(session).banner_phase(identity)==at_death,"Committed corpse and freeze frames must pause room Banner phases");
            committed_frames+=session.committed_corpse();frozen_frames+=!session.scene_ran();
        }
    }
    require(committed_frames>0 && frozen_frames>0 && session.stats().reloads==1,"Natural death must traverse committed corpse, freeze and reload");
    const auto& replacement=first_instance(session);
    require(replacement.scoped_random.object_identity()!=old_scope && replacement.banner_phase(identity)==initial,
        "Reload must create fresh room-instance phases even for the same authored metadata identity");
}
void missing_banner_phase_rejects() {
    const auto definition=first_room();StaticWorld collision;RoomRuntime room(definition,collision);
    try { room.banner_phase(1); }
    catch(const std::logic_error&) { return; }
    throw std::runtime_error("Missing Banner phase must not silently become zero");
}
void invalid_banner_delta_rejects_before_mutation_parameterized() {
    for(const float delta:{-1.f,std::numeric_limits<float>::infinity(),std::numeric_limits<float>::quiet_NaN()}) {
        const auto definition=first_room();auto metadata=visual_owners(definition,1,0);
        StaticWorld collision;RoomRuntime room(definition,collision,false,&metadata);
        const auto identity=metadata.owners.front().identity;const auto before=room.banner_phase(identity);
        try { room.update_banners(delta); }
        catch(const std::invalid_argument&) { require(room.banner_phase(identity)==before,"Invalid delta must not mutate phase");continue; }
        throw std::runtime_error("Invalid Banner delta must reject");
    }
}
void aliased_metadata_identity_rejects() {
    const auto definition=first_room();auto metadata=visual_owners(definition,2,0);
    metadata.owners[1].identity=metadata.owners[0].identity;
    try { StaticWorld collision;RoomRuntime room(definition,collision,false,&metadata); }
    catch(const std::logic_error&) { return; }
    throw std::runtime_error("Aliased Banner metadata identities must reject");
}
void physical_namespace_metadata_identity_rejects() {
    const auto definition=first_room();auto metadata=visual_owners(definition,1,0);metadata.owners.front().identity=1;
    try { StaticWorld collision;RoomRuntime room(definition,collision,false,&metadata); }
    catch(const std::invalid_argument&) { return; }
    throw std::runtime_error("Visual metadata must not alias physical/global identity namespaces");
}
void foreign_same_name_room_metadata_rejects() {
    SessionFixture fixture;const auto alias=fixture.catalog.first();fixture.visual.front().room=&alias;
    try { FirstRoomSession session(fixture.physical.world,fixture.physical.frames,false,7,&fixture.catalog,&fixture.visual); }
    catch(const std::invalid_argument&) { return; }
    throw std::runtime_error("Room-name equality must not accept foreign metadata bindings");
}
void unknown_owner_kind_rejects() {
    const auto definition=first_room();auto metadata=visual_owners(definition,1,0);metadata.owners.front().kind=OwnerKind::player;
    try { StaticWorld collision;RoomRuntime room(definition,collision,false,&metadata); }
    catch(const std::logic_error&) { return; }
    throw std::runtime_error("Unknown visual owner metadata must reject");
}
void static_owners_do_not_consume_visual_random_draws() {
    const auto definition=first_room();auto metadata=visual_owners(definition,3,2);
    metadata.owners[0].banner=false;metadata.owners[3].banner=false;
    StaticWorld collision;RoomRuntime room(definition,collision,false,&metadata);
    PresentationRandom expected(definition.load_seed);
    for(unsigned piece=0;piece<19;++piece) expected.next(1);
    for(const unsigned index:{4u,1u,2u})
        require(room.banner_phase(metadata.owners[index].identity)==float(expected.next_double()),"Static owners must not shift Banner Added random draws");
    require(room.banners().size()==3,"Only classified Banner owners may hold phases");
}
void visual_updates_leave_global_random_and_physical_simulation_unchanged() {
    SessionFixture fixture;
    FirstRoomSession baseline(fixture.physical.world,fixture.physical.frames,false,7,&fixture.catalog);
    FirstRoomSession visual(fixture.physical.world,fixture.physical.frames,false,7,&fixture.catalog,&fixture.visual);
    for(unsigned frame=0;frame<240;++frame) {
        PlayerInput input;
        if(frame>=40 && frame<100) { input.x=1;input.jump={frame==40,frame==40,frame==41}; }
        baseline.step(1.f/60,input);visual.step(1.f/60,input);
        require(baseline.random().state_words()==visual.random().state_words() && baseline.random().calls()==visual.random().calls(),
            "Visual initialization and updates must leave global random consumption unchanged");
        require(baseline.player().actor().body.position.x==visual.player().actor().body.position.x &&
                baseline.player().actor().body.position.y==visual.player().actor().body.position.y &&
                baseline.player().state_machine().state()==visual.player().state_machine().state() &&
                baseline.stats().scoped_room_random_calls==visual.stats().scoped_room_random_calls &&
                baseline.room_roster().size()==visual.room_roster().size(),"Visual owners must not enter or alter the physical simulation roster");
    }
}
}
int main() {
    try {
        initialization_uses_detached_constructor_boundary_parameterized();
        normal_update_uses_repeated_source_float_addition();
        transition_update_pauses_banner_phase();
        session_initializes_before_the_first_update();
        repeated_draw_does_not_advance_banner_phase();
        natural_dash_freeze_pauses_banner_phase();
        natural_corpse_frames_pause_then_reload_new_banner_owners();
        missing_banner_phase_rejects();
        invalid_banner_delta_rejects_before_mutation_parameterized();
        aliased_metadata_identity_rejects();
        physical_namespace_metadata_identity_rejects();
        foreign_same_name_room_metadata_rejects();
        unknown_owner_kind_rejects();
        static_owners_do_not_consume_visual_random_draws();
        visual_updates_leave_global_random_and_physical_simulation_unchanged();
        std::cout<<"15 Banner initialization/update behaviors passed\n";
    } catch(const std::exception& error) { std::cerr<<error.what()<<'\n';return 1; }
}
