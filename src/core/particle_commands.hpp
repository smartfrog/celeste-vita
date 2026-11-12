#pragma once
#include "decal_commands.hpp"
#include "dust_particles.hpp"

namespace celeste::particle_commands {
constexpr std::size_t catalog_byte_limit=2048;
struct Catalog {
    std::array<std::string,2> provenance;
    std::array<decal_commands::AtlasFrame,4> frames;
};
struct Command : decal_commands::DecalCommand {
    unsigned slot=0;
    std::uint64_t generation=0;
};
Catalog parse(std::string_view text,std::uint32_t expected_checksum);
std::vector<Command> project(const draw_order::DrawProjection& drawn,const DustParticles& particles,const Catalog& catalog);
}
