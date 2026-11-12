#pragma once
#include "decal_commands.hpp"

namespace celeste::spring_commands {
inline constexpr std::size_t catalog_byte_limit=2048;
inline constexpr std::array<std::string_view,7> provenance{{
    "36a931e162387df599b88df84d851541be25001d24a5114084c6d06c461939d7",
    "5095f3b86a78844a4076e1744b28e8ee493923baa920bb06b3497d7f253ebfee",
    "7aea400b2428df2708b31c844f0dd15b797c419a4a63f945a473127ab3c4c210",
    "45847f23970911b07541e4bc367cbd156f3b4b1846b63b33d3fed9c7b65ebf6b",
    "aa87a22589821fc3781672126e68f2195fb46348f261013d8a01c070b53821d3",
    "1f23b1f35544a3751ffec170b0230c7c9513000ab1549f78ebb9cb9f4203c8d9",
    "b75f913d315bd641c35a4990d9041b238c0d9ef3f8b1247ec557de8a9defc1cc"}};
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
Catalog parse(std::string_view text,std::uint32_t expected_checksum);
std::vector<Command> project(const draw_order::DrawProjection& drawn,const Catalog& catalog,
                             const std::vector<const RoomRuntime*>& rooms);
}
