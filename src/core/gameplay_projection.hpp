#pragma once
#include "gameplay_commands.hpp"

namespace celeste::gameplay_projection {
struct Catalogs {
    const decal_commands::StaticDecalCatalog* decals=nullptr;
    const terrain::Catalog* terrain=nullptr;
    bool complete_decals=true;
    const spike_commands::Catalog* spikes=nullptr;
    const jumpthru_commands::Catalog* jumpthrus=nullptr;
    const strawberry_commands::Catalog* strawberries=nullptr;
    const spring_commands::Catalog* springs=nullptr;
    const particle_commands::Catalog* particles=nullptr;
};
struct Frame {
    draw_order::DrawProjection projection;
    decal_commands::DecalProjection decals;
    std::vector<spike_commands::Command> spikes;
    std::vector<jumpthru_commands::Command> jumpthrus;
    std::vector<strawberry_commands::Command> strawberries;
    std::vector<spring_commands::Command> springs;
    std::vector<particle_commands::Command> particles;
};
Frame project(const FirstRoomSession& session,const RoomDefinition& initial_room,
              const std::vector<draw_order::AuthoredDecalOwners>& authored,const Catalogs& catalogs);
gameplay_commands::Schedule assemble(const FirstRoomSession& session,const Frame& frame,
    const terrain::Catalog& terrain,const PlayerFrameBank& bank,const std::vector<LogicalPlayerFrame>& mapping,
    const std::vector<PlayerDraw>& cached);
}
