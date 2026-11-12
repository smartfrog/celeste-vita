#include "draw_order.hpp"
#include <algorithm>
#include <stdexcept>
#include <type_traits>

namespace celeste::draw_order {
namespace {
constexpr int background_tiles_depth = 10000;
constexpr int particle_back_depth = 8000;
constexpr int particle_mid_depth = -8000;
constexpr int solid_tiles_depth = -10000;
constexpr int particle_front_depth = -50000;
constexpr int player_intro_band = -1000000;
constexpr int player_depth = 0;
constexpr int scene_helper_depth = 0;
constexpr int wind_depth = 0;
constexpr int spikes_depth = -1;
constexpr int jumpthru_depth = -60;
constexpr int strawberry_depth = -100;
constexpr int spring_depth = -8501;
constexpr int decal_background_depth = 9000;
constexpr int decal_foreground_depth = -10500;
constexpr int hud_depth = -5000;
constexpr unsigned player_sequence = 2;
constexpr std::uint64_t structural_identity_base = 0x5000'0000'0000'0000ull;

DrawOwner structural(OwnerKind kind,std::uint64_t identity,int band,unsigned sequence,
                      bool visible=true,bool hud_excluded=false) {
    return DrawOwner{kind,structural_identity_base|identity,-1,nullptr,band,sequence,visible,hud_excluded,false};
}

OwnerKind entity_kind(const RoomEntity& entity) {
    return std::visit([](const auto& object) -> OwnerKind {
        using T=std::decay_t<decltype(object)>;
        if constexpr(std::is_same_v<T,RoomSceneHelper>) return OwnerKind::scene_helper;
        else if constexpr(std::is_same_v<T,RoomWind>) return OwnerKind::wind;
        else if constexpr(std::is_same_v<T,StaticSpike>) return OwnerKind::spikes;
        else if constexpr(std::is_same_v<T,RoomJumpThru>) return OwnerKind::jumpthru_platform;
        else if constexpr(std::is_same_v<T,RoomSpring>) return OwnerKind::spring;
        else return OwnerKind::strawberry;
    },entity.object);
}
int entity_band(OwnerKind kind) {
    switch(kind) {
    case OwnerKind::scene_helper: return scene_helper_depth;
    case OwnerKind::wind: return wind_depth;
    case OwnerKind::spikes: return spikes_depth;
    case OwnerKind::jumpthru_platform: return jumpthru_depth;
    case OwnerKind::strawberry: return strawberry_depth;
    case OwnerKind::spring: return spring_depth;
    default: throw std::logic_error("Owner kind is not a room entity");
    }
}
}

RosterSnapshot snapshot(const FirstRoomSession& session,const RoomDefinition* initial_room) {
    if(!initial_room) throw std::invalid_argument("The draw roster requires the authored initial room");
    RosterSnapshot state;
    state.roster=session.room_roster();
    state.initial_room=initial_room;
    state.player_intro_placement=!state.roster.empty() && state.roster.back().player!=nullptr;
    return state;
}

void validate_authored_decals(const std::vector<AuthoredDecalOwners>& authored_decals) {
    std::vector<std::uint64_t> authored_identities;
    for(const auto& group:authored_decals) {
        if(!group.room || std::count_if(authored_decals.begin(),authored_decals.end(),[&](const AuthoredDecalOwners& other) {
            return other.room && other.room->name==group.room->name;
        })!=1) throw std::logic_error("Authored decal metadata must bind each room exactly once");
        for(const auto& owner:group.owners) {
            if(owner.kind!=OwnerKind::decal || !owner.room || owner.room->name!=group.room->name || owner.authored_id<0 ||
               !owner.visible || owner.hud_excluded || !owner.identity)
                throw std::logic_error("Invalid authored decal owner binding");
            if(owner.sort_depth_band!=decal_background_depth && owner.sort_depth_band!=decal_foreground_depth)
                throw std::logic_error("Authored decal depth must match the observed SOURCE layers");
            if(std::find(authored_identities.begin(),authored_identities.end(),owner.identity)!=authored_identities.end())
                throw std::logic_error("Every authored draw owner must hold a distinct stable identity");
            authored_identities.push_back(owner.identity);
            if(std::count_if(group.owners.begin(),group.owners.end(),[&](const DrawOwner& other) {
                return other.sort_depth_band==owner.sort_depth_band && other.authored_id==owner.authored_id;
            })!=1) throw std::logic_error("Authored decal metadata binds one ordinal twice");
        }
        for(const bool background:{true,false}) {
            const int expected=background?group.background_count:group.foreground_count;
            if(expected<0) continue;
            const int band=background?decal_background_depth:decal_foreground_depth;
            if(std::count_if(group.owners.begin(),group.owners.end(),[&](const DrawOwner& owner) {
                return owner.sort_depth_band==band;
            })!=expected) throw std::logic_error("Incomplete authored decal layer coverage");
            for(const auto& owner:group.owners) if(owner.sort_depth_band==band && owner.authored_id>=expected)
                throw std::logic_error("Authored decal ordinal exceeds its layer count");
        }
    }
}

DrawProjection project(const RosterSnapshot& state,const std::vector<AuthoredDecalOwners>& authored_decals) {
    if(!state.initial_room) throw std::logic_error("The draw roster requires the authored initial room");
    if(std::count_if(state.roster.begin(),state.roster.end(),[](const RoomRosterEntry& entry) { return entry.player; })!=1)
        throw std::logic_error("The draw roster requires exactly one Player owner");
    validate_authored_decals(authored_decals);
    std::vector<std::uint64_t> authored_identities;
    for(const auto& group:authored_decals) for(const auto& owner:group.owners) authored_identities.push_back(owner.identity);
    std::vector<const RoomRuntime*> rooms;
    for(const auto& entry:state.roster) {
        if(!entry.room) continue;
        if(std::find(rooms.begin(),rooms.end(),entry.room)==rooms.end()) rooms.push_back(entry.room);
    }

    DrawProjection projection;
    projection.live.push_back(structural(OwnerKind::background_tiles,1,background_tiles_depth,0));
    projection.live.push_back(structural(OwnerKind::particle_system_back,2,particle_back_depth,0));
    projection.live.push_back(structural(OwnerKind::particle_system_mid,3,particle_mid_depth,0));
    projection.live.push_back(structural(OwnerKind::solid_tiles,4,solid_tiles_depth,0));
    projection.live.push_back(structural(OwnerKind::particle_system_front,5,particle_front_depth,0));
    projection.live.push_back(structural(OwnerKind::hud_display,6,hud_depth,0,false,true));

    unsigned spikes_sequence=0,jumpthru_sequence=0,strawberry_sequence=0,spring_sequence=0,later_wind_sequence=3;
    for(const auto& entry:state.roster) {
        if(entry.player) {
            projection.live.push_back(DrawOwner{OwnerKind::player,entry.player->object_identity(),-1,nullptr,
                state.player_intro_placement?player_intro_band:player_depth,player_sequence,true,false,false});
            continue;
        }
        if(!entry.room || !entry.entity) throw std::logic_error("Roster entries must own a room entity or the Player");
        for(const auto& other:projection.live)
            if(other.identity==entry.entity->object_identity)
                throw std::logic_error("A room entity was published to the draw roster twice");
        const auto kind=entity_kind(*entry.entity);
        unsigned sequence;
        switch(kind) {
        case OwnerKind::scene_helper: sequence=0; break;
        case OwnerKind::wind: sequence=entry.room->definition.name==state.initial_room->name ? 1 : later_wind_sequence++; break;
        case OwnerKind::spikes: sequence=spikes_sequence++; break;
        case OwnerKind::jumpthru_platform: sequence=jumpthru_sequence++; break;
        case OwnerKind::strawberry: sequence=strawberry_sequence++; break;
        case OwnerKind::spring: sequence=spring_sequence++; break;
        default: throw std::logic_error("Unexpected owner kind for a room entity");
        }
        projection.live.push_back(DrawOwner{kind,entry.entity->object_identity,entry.entity->authored_id,
            &entry.room->definition,entity_band(kind),sequence,true,false,false});
    }

    for(const auto& owner:projection.live)
        if(std::find(authored_identities.begin(),authored_identities.end(),owner.identity)!=authored_identities.end())
            throw std::logic_error("Authored decal identity aliases a global, Player or room entity owner");
    unsigned background_sequence=0,foreground_sequence=0;
    for(const auto* room:rooms) {
        const auto authored=std::find_if(authored_decals.begin(),authored_decals.end(),
            [&](const AuthoredDecalOwners& entry) { return entry.room && entry.room->name==room->definition.name; });
        if(authored==authored_decals.end()) {
            projection.decal_gap_rooms.push_back(&room->definition);
            continue;
        }
        for(const auto& owner:authored->owners) {
            auto projected=owner;
            projected.room=&room->definition;
            projected.sequence=owner.sort_depth_band>0?background_sequence++:foreground_sequence++;
            projection.live.push_back(std::move(projected));
        }
    }

    for(std::size_t i=0;i<projection.live.size();++i)
        for(std::size_t j=i+1;j<projection.live.size();++j)
            if(projection.live[i].identity==projection.live[j].identity)
                throw std::logic_error("Every draw owner must hold a distinct stable identity");
    std::stable_sort(projection.live.begin(),projection.live.end(),[](const DrawOwner& left,const DrawOwner& right) {
        return left.sort_depth_band!=right.sort_depth_band ? left.sort_depth_band>right.sort_depth_band : left.sequence<right.sequence;
    });
    for(std::size_t i=0;i<projection.live.size();++i)
        if(projection.live[i].visible && !projection.live[i].hud_excluded) projection.dispatch.push_back(i);
    return projection;
}
}
