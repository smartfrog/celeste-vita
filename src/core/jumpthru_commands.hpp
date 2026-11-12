#pragma once
#include "decal_commands.hpp"
#include <string_view>

namespace celeste::jumpthru_commands {
struct Catalog { decal_commands::AtlasFrame wood; };
struct Command {
    decal_commands::DecalCommand image;
    int authored_id=-1;
    unsigned piece=0;
    std::size_t dispatch_index=0;
};
Catalog parse(std::string_view text,std::uint32_t expected_checksum);
std::vector<Command> project(const draw_order::DrawProjection& drawn,const Catalog& catalog,
                             const std::vector<const RoomRuntime*>& rooms);
}
