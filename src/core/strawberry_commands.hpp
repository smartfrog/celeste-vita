#pragma once
#include "decal_commands.hpp"
#include "lifecycle.hpp"
#include <string_view>

namespace celeste::strawberry_commands {
inline constexpr std::size_t catalog_byte_limit=8'192;
struct Catalog {
    std::array<decal_commands::AtlasFrame,8> frames{};
    std::array<unsigned,36> idle{};
    std::array<std::string,3> provenance{};
};
struct Command : decal_commands::DecalCommand {
    int authored_id=-1;
    unsigned animation_frame=0,texture_frame=0;
};
Catalog parse(std::string_view text,std::uint32_t expected_checksum);
std::vector<Command> project(const draw_order::DrawProjection& drawn,
                             const std::vector<RoomRosterEntry>& roster,const Catalog& catalog);
}
