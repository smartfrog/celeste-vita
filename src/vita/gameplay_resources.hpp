#pragma once
#include "assets.hpp"
#include "gameplay_bridge.hpp"
#include <map>

namespace celeste::diagnostic {
struct GameplayFilePin {
    std::string name;
    std::size_t bytes;
    std::uint32_t checksum;
};
using GameplayReader=std::function<std::string(const std::string&,std::size_t)>;
class GameplayResources final {
public:
    GameplayResources(const std::vector<GameplayFilePin>& pins,const GameplayReader& read);
    GameplayResources(const GameplayResources&)=delete;
    GameplayResources& operator=(const GameplayResources&)=delete;
    GameplayResources(GameplayResources&&)=delete;
    GameplayResources& operator=(GameplayResources&&)=delete;
    gameplay_commands::Schedule schedule(Session& session) const;
    command_preflight::ReadyFrame prepare(unsigned frame,Session& session) const;
    const Room room;
    const PlayerAssets player;
    const RoomCatalog catalog;
    const std::vector<draw_order::AuthoredDecalOwners> authored;
    const decal_commands::StaticDecalCatalog decals;
    const terrain::Catalog terrain;
    const spike_commands::Catalog spikes;
    const jumpthru_commands::Catalog jumpthrus;
    const strawberry_commands::Catalog strawberries;
    const spring_commands::Catalog springs;
    const particle_commands::Catalog particles;
    const std::vector<LogicalPlayerFrame> mapping;
    const command_preflight::MaterialTable materials;
    const std::vector<gameplay_bridge::PagePixels> pixels;
private:
    using Files=std::map<std::string,std::string>;
    explicit GameplayResources(Files files);
    static Files read_files(const std::vector<GameplayFilePin>& pins,const GameplayReader& read);
};
}
