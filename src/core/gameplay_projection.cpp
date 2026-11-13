#include "gameplay_projection.hpp"
#include <algorithm>
#include <stdexcept>

namespace celeste::gameplay_projection {
Frame project(const FirstRoomSession& session,const RoomDefinition& initial_room,
              const std::vector<draw_order::AuthoredDecalOwners>& authored,const Catalogs& catalogs) {
    Frame frame;
    frame.projection=draw_order::project(draw_order::snapshot(session,&initial_room),authored);
    const auto& projection=frame.projection;
    std::vector<const RoomRuntime*> rooms;
    if(catalogs.complete_decals || catalogs.jumpthrus || catalogs.springs) for(const auto& entry:session.room_roster())
        if(entry.room && std::find(rooms.begin(),rooms.end(),entry.room)==rooms.end()) rooms.push_back(entry.room);
    if(catalogs.springs) frame.springs=spring_commands::project(projection,*catalogs.springs,rooms);
    if(catalogs.jumpthrus) frame.jumpthrus=jumpthru_commands::project(projection,*catalogs.jumpthrus,rooms);
    if(catalogs.decals) frame.decals=decal_commands::project(projection,*catalogs.decals,catalogs.complete_decals?&rooms:nullptr);
    if(catalogs.spikes) frame.spikes=spike_commands::project(projection,session.room_roster(),*catalogs.spikes);
    if(catalogs.strawberries) frame.strawberries=strawberry_commands::project(projection,session.room_roster(),*catalogs.strawberries);
    if(catalogs.particles) frame.particles=particle_commands::project(projection,session.visual_dust(),*catalogs.particles);
    return frame;
}
gameplay_commands::Schedule assemble(const FirstRoomSession& session,const Frame& frame,
    const terrain::Catalog& terrain_catalog,const PlayerFrameBank& bank,const std::vector<LogicalPlayerFrame>& mapping,
    const std::vector<PlayerDraw>& cached) {
    const std::string phase=session.phase();
    if(phase!="live" && phase!="respawn14") throw std::runtime_error("Unsupported gameplay lifecycle phase: "+phase);
    gameplay_commands::CachedPlayer player{session.player().object_identity(),phase=="live",bank,mapping,cached};
    std::uint64_t background=0,foreground=0;
    gameplay_commands::Inputs inputs;
    for(const auto& owner:frame.projection.live) {
        using Kind=draw_order::OwnerKind;
        using Reason=gameplay_commands::EmptyReason;
        if(owner.kind==Kind::background_tiles) background=owner.identity;
        if(owner.kind==Kind::solid_tiles) foreground=owner.identity;
        if(owner.kind==Kind::scene_helper) inputs.empty.push_back({owner.identity,Reason::scene_helper_has_no_capture_calls});
        if(owner.kind==Kind::wind) inputs.empty.push_back({owner.identity,Reason::wind_has_no_capture_calls});
        if(owner.kind==Kind::particle_system_back || owner.kind==Kind::particle_system_front)
            inputs.empty.push_back({owner.identity,Reason::particle_system_has_no_active_images});
    }
    gameplay_commands::TerrainInput terrain{terrain_catalog,background,foreground,session.camera()};
    inputs.sheets=&terrain_catalog.sheets();inputs.terrain=&terrain;inputs.player=&player;
    inputs.decals=&frame.decals;inputs.spikes=&frame.spikes;inputs.jumpthrus=&frame.jumpthrus;
    inputs.strawberries=&frame.strawberries;inputs.springs=&frame.springs;inputs.particles=&frame.particles;
    return gameplay_commands::assemble(frame.projection,inputs);
}
}
