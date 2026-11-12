#include "draw_order.hpp"
#include "lifecycle_fixture.hpp"
#include <algorithm>
#include <iostream>
#include <memory>
#include <stdexcept>
#include <string>
#include <vector>

using namespace celeste;
using namespace celeste::draw_order;
namespace {
void require(bool condition,const char* message) { if(!condition) throw std::runtime_error(message); }

RoomDefinition first_room() {
    return {"1",{0,0,320,180},49,{19,144},{
        {RoomObjectKind::spike_up,7,{64,144},8},
        {RoomObjectKind::spike_up,8,{160,144},32},
        {RoomObjectKind::spike_up,9,{200,144},48},
        {RoomObjectKind::spike_up,10,{240,144},48},
        {RoomObjectKind::spike_left,11,{300,128},16}}};
}
RoomDefinition second_room() {
    return {"2",{240,-184,320,180},50,{264,-24},{
        {RoomObjectKind::jump_thru,7,{248,-24},40},
        {RoomObjectKind::spike_up,8,{400,-72},40},
        {RoomObjectKind::spike_up,9,{432,-24},16},
        {RoomObjectKind::strawberry,11,{336,-144},0},
        {RoomObjectKind::spring,12,{360,-40},0},
        {RoomObjectKind::spike_up,14,{448,-16},16}}};
}

std::vector<AuthoredDecalOwners> first_room_decals(const RoomDefinition& room) {
    AuthoredDecalOwners authored{&room,{}};
    for(int i=0;i<20;++i) authored.owners.push_back({OwnerKind::decal,(1ull<<32)|uint64_t(i+1),i,&room,9000,unsigned(i),true,false,false});
    for(int i=20;i<25;++i) authored.owners.push_back({OwnerKind::decal,(1ull<<32)|(1ull<<31)|uint64_t(i+1),i,&room,9000,unsigned(i),true,false,true});
    for(int i=0;i<2;++i) authored.owners.push_back({OwnerKind::decal,(2ull<<32)|uint64_t(i+1),i,&room,-10500,unsigned(i),true,false,false});
    for(int i=2;i<4;++i) authored.owners.push_back({OwnerKind::decal,(2ull<<32)|(1ull<<31)|uint64_t(i+1),i,&room,-10500,unsigned(i),true,false,true});
    return {authored};
}

std::vector<OwnerKind> live_kinds(const DrawProjection& projection) {
    std::vector<OwnerKind> kinds;
    for(const auto& owner:projection.live) kinds.push_back(owner.kind);
    return kinds;
}
std::size_t position_of(const DrawProjection& projection,OwnerKind kind,std::size_t occurrence=0) {
    std::size_t seen=0;
    for(std::size_t i=0;i<projection.live.size();++i)
        if(projection.live[i].kind==kind && seen++==occurrence) return i;
    throw std::runtime_error("Owner kind is missing from the live projection");
}

void initial_room_projection_matches_source_owner_order() {
    native_test::LifecycleFixture fixture;
    const auto room=first_room();
    RoomCatalog catalog({room,second_room()});
    FirstRoomSession session(fixture.world,fixture.frames,false,1,&catalog);
    const auto projection=project(snapshot(session,&room),first_room_decals(room));
    const std::vector<OwnerKind> expected{
        OwnerKind::background_tiles,
        OwnerKind::decal,OwnerKind::decal,OwnerKind::decal,OwnerKind::decal,OwnerKind::decal,
        OwnerKind::decal,OwnerKind::decal,OwnerKind::decal,OwnerKind::decal,OwnerKind::decal,
        OwnerKind::decal,OwnerKind::decal,OwnerKind::decal,OwnerKind::decal,OwnerKind::decal,
        OwnerKind::decal,OwnerKind::decal,OwnerKind::decal,OwnerKind::decal,OwnerKind::decal,
        OwnerKind::decal,OwnerKind::decal,OwnerKind::decal,OwnerKind::decal,OwnerKind::decal,
        OwnerKind::particle_system_back,
        OwnerKind::scene_helper,
        OwnerKind::wind,
        OwnerKind::spikes,OwnerKind::spikes,OwnerKind::spikes,OwnerKind::spikes,OwnerKind::spikes,
        OwnerKind::hud_display,
        OwnerKind::particle_system_mid,
        OwnerKind::solid_tiles,
        OwnerKind::decal,OwnerKind::decal,OwnerKind::decal,OwnerKind::decal,
        OwnerKind::particle_system_front,
        OwnerKind::player};
    require(live_kinds(projection)==expected,"Initial-room draw owner order must match the observed SOURCE roster order");
    require(projection.live.size()==43,"Initial-room live owner count must include every observed SOURCE owner");
    require(projection.dispatch.size()==42,"Dispatch must keep exactly the visible non-HUD owners");
}

void hud_display_stays_in_roster_but_is_excluded_from_dispatch() {
    native_test::LifecycleFixture fixture;
    const auto room=first_room();
    RoomCatalog catalog({room,second_room()});
    FirstRoomSession session(fixture.world,fixture.frames,false,1,&catalog);
    const auto projection=project(snapshot(session,&room),first_room_decals(room));
    const auto position=position_of(projection,OwnerKind::hud_display);
    require(!projection.live[position].visible && projection.live[position].hud_excluded,
        "The HUD display owner must be recorded invisible and HUD-excluded");
    for(const auto index:projection.dispatch)
        require(projection.live[index].kind!=OwnerKind::hud_display,"The HUD filter must exclude the HUD display owner");
    for(std::size_t i=0;i<projection.live.size();++i)
        require(projection.live[i].visible || projection.live[i].kind==OwnerKind::hud_display,
            "Only the HUD display owner may be invisible on this bounded route");
}

void intro_player_keeps_source_intro_depth_and_draws_last() {
    native_test::LifecycleFixture fixture;
    const auto room=first_room();
    RoomCatalog catalog({room,second_room()});
    FirstRoomSession session(fixture.world,fixture.frames,false,1,&catalog);
    const auto projection=project(snapshot(session,&room),first_room_decals(room));
    const auto& player=projection.live.back();
    require(player.kind==OwnerKind::player && player.sort_depth_band==-1000000,
        "The intro-state Player owner must retain the observed SOURCE intro depth");
    require(session.player().state_machine().state()==14,"Fixture must actually observe the intro state");
}

struct TwoRoomFixture {
    Body floor{{320,-40},Hitbox{100,8,{}},true};
    StaticWorld collision{{&floor},{}};
    RoomDefinition room1=first_room(),room2=second_room();
    std::unique_ptr<RoomRuntime> outgoing,current;
    PlayerWorld world;
    Player player{world};
    TwoRoomFixture() {
        outgoing=std::make_unique<RoomRuntime>(room1,collision,true);
        current=std::make_unique<RoomRuntime>(room2,collision);
    }
};
RosterSnapshot two_room_snapshot(bool intro_depth) {
    static TwoRoomFixture fixture;
    RosterSnapshot snapshot_data;
    snapshot_data.initial_room=&fixture.room1;
    snapshot_data.player_intro_placement=intro_depth;
    for(const auto* room:{fixture.outgoing.get(),fixture.current.get()})
        for(const auto& entity:room->entities) snapshot_data.roster.push_back({room,entity.get(),nullptr});
    snapshot_data.roster.push_back({nullptr,nullptr,&fixture.player});
    return snapshot_data;
}
RosterSnapshot second_room_only_snapshot() {
    static TwoRoomFixture fixture;
    RosterSnapshot snapshot_data;
    snapshot_data.initial_room=&fixture.room1;
    for(const auto& entity:fixture.current->entities) snapshot_data.roster.push_back({fixture.current.get(),entity.get(),nullptr});
    snapshot_data.roster.push_back({nullptr,nullptr,&fixture.player});
    return snapshot_data;
}

void player_joins_depth_zero_after_initial_winds_and_before_later_winds() {
    const auto projection=project(two_room_snapshot(false),{});
    const std::vector<OwnerKind> expected{OwnerKind::scene_helper,OwnerKind::wind,
        OwnerKind::player,OwnerKind::wind};
    std::vector<OwnerKind> depth_zero;
    for(const auto& owner:projection.live) if(owner.sort_depth_band==0) depth_zero.push_back(owner.kind);
    require(depth_zero==expected,"Depth-zero owners must keep the observed SOURCE tie order");
    const auto& player=projection.live[position_of(projection,OwnerKind::player)];
    require(player.sort_depth_band==0,"A non-intro Player owner must draw at the observed SOURCE depth");
}

void destination_entities_draw_between_particle_systems_and_solid_tiles() {
    const auto projection=project(two_room_snapshot(false),{});
    const auto spikes=position_of(projection,OwnerKind::spikes,5);
    const auto jumpthru=position_of(projection,OwnerKind::jumpthru_platform);
    const auto strawberry=position_of(projection,OwnerKind::strawberry);
    const auto hud=position_of(projection,OwnerKind::hud_display);
    const auto mid=position_of(projection,OwnerKind::particle_system_mid);
    const auto spring=position_of(projection,OwnerKind::spring);
    const auto tiles=position_of(projection,OwnerKind::solid_tiles);
    require(spikes<jumpthru && jumpthru<strawberry && strawberry<hud && hud<mid && mid<spring && spring<tiles,
        "Destination owners must keep the observed SOURCE depth order Spikes<Jumpthru<Strawberry<HUD<mid<Spring<SolidTiles");
    require(projection.live[spring].sort_depth_band==-8501,"The Spring owner must use the observed SOURCE draw depth");
}

void outgoing_room_owners_are_retained_until_unload() {
    const auto room=first_room();
    auto projection=project(two_room_snapshot(false),first_room_decals(room));
    unsigned room1_decals=0,room1_spikes=0,room2_spikes=0;
    for(const auto& owner:projection.live) {
        if(owner.kind!=OwnerKind::decal && owner.kind!=OwnerKind::spikes) continue;
        const bool first=owner.room && owner.room->name=="1";
        if(owner.kind==OwnerKind::decal && first) ++room1_decals;
        else if(owner.kind==OwnerKind::spikes) first ? ++room1_spikes : ++room2_spikes;
    }
    require(room1_decals==29 && room1_spikes==5 && room2_spikes==3,
        "Outgoing room owners must stay live beside the incoming room owners");
    require(projection.decal_gap_rooms.size()==1 && projection.decal_gap_rooms.front()->name=="2",
        "Rooms without authored decal metadata must be reported as an explicit gap");
    require(std::count_if(projection.live.begin(),projection.live.end(),
        [](const DrawOwner& owner) { return owner.kind==OwnerKind::player; })==1,
        "The Player owner must appear exactly once across both rooms");
}

void banner_decals_sequence_after_statics_within_each_layer() {
    native_test::LifecycleFixture fixture;
    const auto room=first_room();
    RoomCatalog catalog({room,second_room()});
    FirstRoomSession session(fixture.world,fixture.frames,false,1,&catalog);
    const auto projection=project(snapshot(session,&room),first_room_decals(room));
    int previous_background_sequence=-1,previous_foreground_sequence=-1;
    bool foreground=false;
    for(const auto& owner:projection.live) {
        if(owner.kind!=OwnerKind::decal) continue;
        if(owner.sort_depth_band==9000) { require(int(owner.sequence)>previous_background_sequence,"Background decals must keep authored order"); previous_background_sequence=int(owner.sequence); }
        else { foreground=true; require(int(owner.sequence)>previous_foreground_sequence,"Foreground decals must keep authored order"); previous_foreground_sequence=int(owner.sequence); }
        if(owner.banner) require(owner.authored_id>=20 || (owner.sort_depth_band==-10500 && owner.authored_id>=2),
            "Banner owners must be authored after the static members of their layer");
    }
    require(foreground,"Both authored decal layers must be projected");
}

void owner_identities_are_stable_and_bound_to_native_objects() {
    native_test::LifecycleFixture fixture;
    const auto room=first_room();
    RoomCatalog catalog({room,second_room()});
    FirstRoomSession session(fixture.world,fixture.frames,false,1,&catalog);
    const auto first=project(snapshot(session,&room),first_room_decals(room));
    const auto second=project(snapshot(session,&room),first_room_decals(room));
    require(first.live.size()==second.live.size(),"Repeated projection must be deterministic");
    for(std::size_t i=0;i<first.live.size();++i)
        require(first.live[i].identity==second.live[i].identity,"Owner identities must be stable across projections");
    require(first.live[position_of(first,OwnerKind::player)].identity==session.player().object_identity(),
        "The Player owner identity must be the native Player object identity");
    const auto& spike=first.live[position_of(first,OwnerKind::spikes)];
    require(spike.identity!=0 && spike.authored_id==7,"Room entity owners must expose their authored identity");
}

void duplicate_player_ownership_is_rejected() {
    auto snapshot_data=two_room_snapshot(false);
    snapshot_data.roster.push_back({nullptr,nullptr,snapshot_data.roster.back().player});
    try { project(snapshot_data,{}); }
    catch(const std::logic_error&) { return; }
    throw std::runtime_error("A duplicated Player owner must reject");
}
void post_unload_wind_stays_after_player() {
    const auto projection=project(second_room_only_snapshot(),{});
    std::vector<OwnerKind> depth_zero;
    for(const auto& owner:projection.live) if(owner.sort_depth_band==0) depth_zero.push_back(owner.kind);
    const std::vector<OwnerKind> expected{OwnerKind::player,OwnerKind::wind};
    require(depth_zero==expected,"After the initial room unloads the surviving Wind must keep its later chronology");
}
void duplicate_roster_entity_is_rejected() {
    auto snapshot_data=two_room_snapshot(false);
    for(const auto& entry:snapshot_data.roster) if(entry.entity) {
        snapshot_data.roster.push_back(entry);
        try { project(snapshot_data,{}); }
        catch(const std::logic_error&) { return; }
        throw std::runtime_error("A duplicated room entity owner must reject");
    }
    throw std::runtime_error("Fixture must contain a room entity");
}
void duplicate_authored_decal_group_is_rejected() {
    auto snapshot_data=two_room_snapshot(false);
    const auto room=snapshot_data.initial_room;
    auto decals=first_room_decals(*room);
    decals.push_back(decals.front());
    try { project(snapshot_data,decals); }
    catch(const std::logic_error&) { return; }
    throw std::runtime_error("Duplicate authored decal metadata for one room must reject");
}
void aliased_decal_owner_identity_is_rejected() {
    auto snapshot_data=two_room_snapshot(false);
    auto decals=first_room_decals(*snapshot_data.initial_room);
    auto aliased=decals.front().owners.back();
    aliased.authored_id=decals.front().owners.front().authored_id==aliased.authored_id
        ? aliased.authored_id+1 : aliased.authored_id;
    aliased.identity=decals.front().owners.front().identity;
    decals.front().owners.push_back(aliased);
    try { project(snapshot_data,decals); }
    catch(const std::logic_error&) { return; }
    throw std::runtime_error("Aliased draw owner identities must reject");
}
void duplicate_authored_decal_ordinal_is_rejected() {
    auto snapshot_data=two_room_snapshot(false);
    auto decals=first_room_decals(*snapshot_data.initial_room);
    auto repeated=decals.front().owners.front();
    repeated.identity=0x7fff'ffff'ffff'ffffull;
    decals.front().owners.push_back(repeated);
    try { project(snapshot_data,decals); }
    catch(const std::logic_error&) { return; }
    throw std::runtime_error("One authored decal ordinal bound twice must reject");
}
void missing_initial_room_binding_is_rejected() {
    auto snapshot_data=two_room_snapshot(false);
    snapshot_data.initial_room=nullptr;
    try { project(snapshot_data,{}); }
    catch(const std::logic_error&) { return; }
    throw std::runtime_error("A missing authored initial-room binding must reject");
}
}
int main() {
    try {
        initial_room_projection_matches_source_owner_order();
        hud_display_stays_in_roster_but_is_excluded_from_dispatch();
        intro_player_keeps_source_intro_depth_and_draws_last();
        player_joins_depth_zero_after_initial_winds_and_before_later_winds();
        destination_entities_draw_between_particle_systems_and_solid_tiles();
        outgoing_room_owners_are_retained_until_unload();
        banner_decals_sequence_after_statics_within_each_layer();
        owner_identities_are_stable_and_bound_to_native_objects();
        duplicate_player_ownership_is_rejected();
        post_unload_wind_stays_after_player();
        duplicate_roster_entity_is_rejected();
        duplicate_authored_decal_group_is_rejected();
        aliased_decal_owner_identity_is_rejected();
        duplicate_authored_decal_ordinal_is_rejected();
        missing_initial_room_binding_is_rejected();
        std::cout<<"16 draw owner projection behaviors passed\n";
        return 0;
    } catch(const std::exception& error) { std::cerr<<error.what()<<'\n';return 1; }
}
