#pragma once
#include "jumpthru_commands.hpp"
#include "player_draw_mapping.hpp"
#include "particle_commands.hpp"
#include "spike_commands.hpp"
#include "spring_commands.hpp"
#include "strawberry_commands.hpp"
#include "terrain.hpp"
#include <optional>

namespace celeste::gameplay_commands {
enum class Component { direct, tile_grid, decal_image, banner, image, player_hair, player_sprite, sprite };
enum class EmptyReason { scene_helper_has_no_capture_calls, wind_has_no_capture_calls, particle_system_has_no_active_images };
struct EmptyProducer { std::uint64_t identity; EmptyReason reason; };
struct CachedPlayer {
    std::uint64_t identity;
    bool live;
    const PlayerFrameBank& bank;
    const std::vector<LogicalPlayerFrame>& mapping;
    const std::vector<PlayerDraw>& draws;
};
struct TerrainInput {
    const terrain::Catalog& catalog;
    std::uint64_t background_identity,foreground_identity;
    Vec2 camera,viewport{320,180};
};
struct Inputs {
    const std::vector<terrain::Sheet>* sheets=nullptr;
    const decal_commands::DecalProjection* decals=nullptr;
    const std::vector<spike_commands::Command>* spikes=nullptr;
    const std::vector<jumpthru_commands::Command>* jumpthrus=nullptr;
    const std::vector<strawberry_commands::Command>* strawberries=nullptr;
    const std::vector<spring_commands::Command>* springs=nullptr;
    const std::vector<particle_commands::Command>* particles=nullptr;
    const CachedPlayer* player=nullptr;
    const TerrainInput* terrain=nullptr;
    std::vector<EmptyProducer> empty;
};
struct Command {
    decal_commands::DecalCommand image;
    Component component;
    unsigned piece;
    std::size_t dispatch_index;
    int sheet_width,sheet_height;
    decal_commands::DecalGeometry geometry;
};
struct DispatchRange {
    draw_order::OwnerKind kind;
    std::uint64_t identity;
    std::string room;
    int authored_id;
    bool background;
    std::size_t begin,end;
    std::optional<EmptyReason> empty;
};
enum class ExclusionReason { hud_outside_gameplay_capture };
struct ExcludedOwner { std::uint64_t identity; ExclusionReason reason; };
class Schedule final {
public:
    const std::vector<Command>& commands() const { return commands_; }
    const std::vector<DispatchRange>& ranges() const { return ranges_; }
    const std::vector<ExcludedOwner>& excluded() const { return excluded_; }
private:
    Schedule()=default;
    friend Schedule assemble(const draw_order::DrawProjection&,const Inputs&);
    std::vector<Command> commands_;
    std::vector<DispatchRange> ranges_;
    std::vector<ExcludedOwner> excluded_;
};
Schedule assemble(const draw_order::DrawProjection& projection,const Inputs& inputs);
}
