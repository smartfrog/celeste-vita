#pragma once
#include "decal_commands.hpp"

namespace celeste::spring_commands {
struct Catalog {
    decal_commands::AtlasFrame idle;
    std::string idle_texture;
};
struct Command {
    decal_commands::DecalCommand image;
    int authored_id=-1;
    unsigned piece=0;
    std::size_t dispatch_index=0;
};
std::vector<Command> project(const draw_order::DrawProjection& drawn,const Catalog& catalog,
                             const std::vector<const RoomRuntime*>& rooms);
}
