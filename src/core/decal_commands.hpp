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
    struct BannerFamily {
        unsigned family=0;
        float speed=0,amplitude=0;
        int slice_size=0;
        float increment=0;
        bool ease_down=false;
        float offset=0;
        bool only_if_windy=false;
        int frame_count=1;
    };
    std::vector<AtlasFrame> families;
    std::vector<StaticDecalOwner> owners;
    std::vector<DeferredDecalOwner> deferred;
    std::vector<BannerFamily> banners;
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
    int slice=-1;
};

struct DecalProjection {
    std::vector<DecalCommand> commands;
    std::vector<DeferredDecalOwner> deferred;
};

struct DecalGeometry {
    std::array<std::array<std::int32_t,5>,4> vertices;
    bool finite=true;
};
DecalGeometry project_geometry(const DecalCommand& command,int sheet_width,int sheet_height);
DecalProjection project(const draw_order::DrawProjection& drawn,const StaticDecalCatalog& catalog,
                        const std::vector<const RoomRuntime*>* rooms=nullptr);

}
