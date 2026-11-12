#include "particle_commands.hpp"
#include "atlas_frame_text.hpp"
#include <cmath>
#include <set>

namespace celeste::particle_commands {
namespace {
void validate(const Catalog& catalog) {
    for(const auto& pin:catalog.provenance)
        if(pin.size()!=64 || pin.find_first_not_of("0123456789abcdef")!=std::string::npos)
            throw std::invalid_argument("Invalid Dust provenance pin");
    std::set<std::string> textures;
    for(const auto& frame:catalog.frames) {
        atlas_frame_text::validate(frame);
        if(!textures.insert(frame.texture).second) throw std::invalid_argument("Duplicate Dust texture");
    }
}
}
Catalog parse(std::string_view text,std::uint32_t expected_checksum) {
    using asset_text::take;
    using asset_text::integer;
    asset_text::integrity(text,catalog_byte_limit,expected_checksum);
    if(take(text)!="CDUS1") throw std::invalid_argument("Wrong Dust catalog version");
    Catalog result;
    for(auto& pin:result.provenance) pin=std::string(take(text));
    if(take(text)!="Dust 4") throw std::invalid_argument("Unsupported Dust material type/count");
    for(unsigned index=0;index<result.frames.size();++index) {
        auto row=take(text);
        if(integer(take(row,' '))!=int(index)) throw std::invalid_argument("Unordered Dust frame");
        result.frames[index]=atlas_frame_text::parse(row);
    }
    if(!text.empty()) throw std::invalid_argument("Trailing Dust catalog data");
    validate(result);
    return result;
}
std::vector<Command> project(const draw_order::DrawProjection& drawn,const DustParticles& particles,const Catalog& catalog) {
    validate(catalog);
    const draw_order::DrawOwner* owner=nullptr;
    std::set<std::size_t> dispatched;
    std::set<std::uint64_t> identities;
    for(const auto& entry:drawn.live)
        if(!entry.identity || !identities.insert(entry.identity).second) throw std::invalid_argument("Aliased particle draw identity");
    for(const auto index:drawn.dispatch) {
        if(index>=drawn.live.size() || !dispatched.insert(index).second) throw std::invalid_argument("Invalid particle dispatch");
        const auto& entry=drawn.live[index];
        if(entry.kind!=draw_order::OwnerKind::particle_system_mid) continue;
        if(owner || entry.identity!=draw_order::level_particles_identity || entry.sort_depth_band!=-8000 || entry.room ||
           entry.authored_id!=-1 || !entry.visible || entry.hud_excluded)
            throw std::invalid_argument("Invalid Level.Particles owner");
        owner=&entry;
    }
    if(!owner) throw std::invalid_argument("Missing Level.Particles owner");
    std::vector<Command> commands;
    for(unsigned slot=0;slot<particles.slots().size();++slot) {
        const auto& particle=particles.slots()[slot];
        if(!particle.active) continue;
        if(!particle.generation || !std::isfinite(particle.position.x) || !std::isfinite(particle.position.y) ||
           particle.position.x < -2147483648.f || particle.position.x>=2147483648.f ||
           particle.position.y < -2147483648.f || particle.position.y>=2147483648.f)
            throw std::invalid_argument("Invalid Dust render state");
        const auto& frame=catalog.frames.at(particle.source);
        Command command;
        command.identity=owner->identity;command.slot=slot;command.generation=particle.generation;
        command.texture=frame.texture;command.sheet=frame.sheet;
        command.source_x=frame.x;command.source_y=frame.y;command.source_width=frame.width;command.source_height=frame.height;
        command.position={float(int(particle.position.x)),float(int(particle.position.y))};
        command.origin={frame.frame_width*0.5f,frame.frame_height*0.5f};
        command.scale={particle.size,particle.size};command.rotation=particle.rotation;
        commands.push_back(std::move(command));
    }
    return commands;
}
}
