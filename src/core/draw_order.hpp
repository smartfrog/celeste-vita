#pragma once
#include "lifecycle.hpp"
#include <cstdint>
#include <vector>

namespace celeste::draw_order {

enum class OwnerKind {
    background_tiles, decal, particle_system_back, scene_helper, wind, hud_display, player,
    spikes, jumpthru_platform, strawberry, spring, particle_system_mid, solid_tiles, particle_system_front
};

struct DrawOwner {
    OwnerKind kind;
    std::uint64_t identity=0;
    int authored_id=-1;
    const RoomDefinition* room=nullptr;
    // Placement band reproducing the published SOURCE draw-roster order: entities sort by
    // actualDepth groups with a per-group insertion tie, but the roster itself re-sorts one
    // frame after a Depth change (tick 35: the Player's current Depth is already 0 while its
    // published placement still uses the intro band). This band claims roster placement only,
    // never the entity's current Depth property. The HUD owner band is an ordering band placed
    // between the Strawberry and mid-particle groups, not a claimed SOURCE Depth constant.
    int sort_depth_band=0;
    unsigned sequence=0;
    bool visible=true;
    bool hud_excluded=false;
    bool banner=false;
    std::string texture={};
    Vec2 position{},scale{1,1};
};

struct AuthoredDecalOwners {
    const RoomDefinition* room=nullptr;
    std::vector<DrawOwner> owners;
    int background_count=-1,foreground_count=-1;
};

struct RosterSnapshot {
    std::vector<RoomRosterEntry> roster;
    const RoomDefinition* initial_room=nullptr;
    // Derived from the published roster (Player still last), mirroring the SOURCE deferred
    // EntityList re-sort rather than the Player's current state machine state.
    bool player_intro_placement=false;
};

struct DrawProjection {
    std::vector<DrawOwner> live;
    std::vector<std::size_t> dispatch;
    std::vector<const RoomDefinition*> decal_gap_rooms;
};

RosterSnapshot snapshot(const FirstRoomSession& session,const RoomDefinition* initial_room);
DrawProjection project(const RosterSnapshot& state,const std::vector<AuthoredDecalOwners>& authored_decals);

}
