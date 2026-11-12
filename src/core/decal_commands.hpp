#pragma once
#include "draw_order.hpp"
#include "presentation.hpp"
#include <cstdint>
#include <string>
#include <vector>

namespace celeste::decal_commands {

struct AtlasFrame {
    std::string sheet;
    int x=0,y=0,width=0,height=0;
    float offset_x=0,offset_y=0;
    int frame_width=0,frame_height=0;
    std::string texture;
};

struct StaticDecalOwner {
    std::uint64_t identity=0;
    std::string room;
    bool background=false;
    int ordinal=-1;
    unsigned family=0;
    std::string texture;
};

struct DeferredDecalOwner {
    std::uint64_t identity=0;
    std::string room;
    bool background=false;
    int ordinal=-1;
    std::string texture;
};

struct StaticDecalCatalog {
    std::vector<AtlasFrame> families;
    std::vector<StaticDecalOwner> owners;
    std::vector<DeferredDecalOwner> deferred;
};

struct DecalCommand {
    std::uint64_t identity=0;
    std::string room;
    bool background=false;
    int ordinal=-1;
    std::string texture;
    std::string sheet;
    int source_x=0,source_y=0,source_width=0,source_height=0;
    Vec2 position{},origin{},scale{1,1};
    PresentationColor color{};
    float rotation=0;
    std::string effects="None";
};

struct DecalProjection {
    std::vector<DecalCommand> commands;
    std::vector<DeferredDecalOwner> deferred;
};

DecalProjection project(const draw_order::DrawProjection& drawn,const StaticDecalCatalog& catalog);

}
