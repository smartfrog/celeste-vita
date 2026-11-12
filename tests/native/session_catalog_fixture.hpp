#pragma once
#include "assets.hpp"
#include "diagnostic.hpp"
#include "lifecycle_fixture.hpp"
#include <stdexcept>

namespace native_test {
inline celeste::RoomDefinition lifecycle_room_definition(const LifecycleFixture& physical) {
    celeste::RoomDefinition room{"1",{0,0,320,180},49,{19,144},{}};
    for(const auto& spike:physical.spikes) {
        const bool up=spike.direction()==celeste::SpikeDirection::up;
        room.objects.push_back({up?celeste::RoomObjectKind::spike_up:celeste::RoomObjectKind::spike_left,
            int(room.objects.size()),spike.body().position,int(up?spike.body().collider->width:spike.body().collider->height)});
    }
    return room;
}
struct SessionCatalogFixture {
    LifecycleFixture physical;
    celeste::RoomCatalog catalog{{lifecycle_room_definition(physical),
        {"2",{240,-184,320,180},50,{264,-24},{{celeste::RoomObjectKind::jump_thru,7,{248,-24},40},
            {celeste::RoomObjectKind::spike_up,8,{400,-72},40},
            {celeste::RoomObjectKind::spike_up,9,{432,-24},16},
            {celeste::RoomObjectKind::spike_up,10,{448,-16},16}}}}};
    std::vector<celeste::draw_order::AuthoredDecalOwners> owners;
    SessionCatalogFixture() {
        for(unsigned index=0;index<catalog.definitions().size();++index) {
            const auto& room=catalog.definitions()[index];
            celeste::draw_order::AuthoredDecalOwners metadata{&room,{},index==0?1:4,0};
            for(int ordinal=0;ordinal<metadata.background_count;++ordinal)
                metadata.owners.push_back({celeste::draw_order::OwnerKind::decal,
                    0x6000000000000000ull | (std::uint64_t(index+1)<<32) | std::uint64_t(ordinal+1),
                    ordinal,&room,9000,unsigned(ordinal),true,false,true,"fixture_banner"});
            owners.push_back(std::move(metadata));
        }
    }
};
inline const celeste::RoomRuntime& catalog_room(const celeste::FirstRoomSession& session,const celeste::RoomDefinition& definition) {
    for(const auto& entry:session.room_roster()) if(entry.room && &entry.room->definition==&definition) return *entry.room;
    throw std::runtime_error("Expected exact borrowed room definition in the live roster");
}
}
