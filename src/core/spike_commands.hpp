#pragma once
#include "decal_commands.hpp"
#include "draw_order.hpp"
#include "lifecycle.hpp"
#include <array>
#include <cstdint>
#include <string>
#include <string_view>
#include <vector>

namespace celeste::spike_commands {

inline constexpr std::size_t catalog_byte_limit=8'192;

struct Catalog {
    std::array<decal_commands::AtlasFrame,2> frames{};
    std::array<std::string,3> provenance{};
};

struct Command {
    std::uint64_t identity=0;
    std::string room;
    int authored_id=-1;
    SpikeDirection direction=SpikeDirection::up;
    int piece=0;
    std::string texture,sheet;
    int source_x=0,source_y=0,source_width=0,source_height=0;
    Vec2 position{},origin{},scale{1,1};
    PresentationColor color{};
    float rotation=0;
    std::string effects="None";
};

Catalog parse(std::string_view text,std::uint32_t expected_checksum);
std::vector<Command> project(const draw_order::DrawProjection& drawn,
                             const std::vector<RoomRosterEntry>& roster,
                             const Catalog& catalog);

}
