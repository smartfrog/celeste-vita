#pragma once
#include "terrain.hpp"
#include "draw_order.hpp"
#include <algorithm>
#include <cmath>
#include <iomanip>
#include <limits>
#include <ostream>

namespace native_test {
inline void write_terrain_catalog(std::ostream& stream,const celeste::terrain::Catalog& catalog) {
    stream<<"{\"event\":\"terrain-catalog\",\"sheets\":[";
    bool first=true;
    for(const auto& sheet:catalog.sheets()) {
        if(!first) stream<<',';
        first=false;
        stream<<"{\"name\":"<<std::quoted(sheet.name)<<",\"dimensions\":["<<sheet.width<<','<<sheet.height<<"]}";
    }
    stream<<"],\"materials\":[";first=true;
    for(const auto& material:catalog.materials()) {
        if(!first) stream<<',';
        first=false;
        stream<<"{\"sourceAtlasPath\":"<<std::quoted(material.source)<<",\"sheet\":"<<material.sheet
            <<",\"sourceRectangle\":["<<material.u<<','<<material.v<<','<<material.width<<','<<material.height
            <<"],\"color\":[255,255,255,255],\"origin\":[0,0],\"scale\":[1,1],\"rotation\":0,\"alpha\":1}";
    }
    stream<<"]}\n";
    if(!stream) throw std::runtime_error("Failed writing terrain catalog descriptors");
}
inline void write_terrain_draw(std::ostream& stream,int tick,const celeste::terrain::Catalog& catalog,
                               celeste::Vec2 camera,const celeste::draw_order::DrawProjection& roster) {
    using namespace celeste::draw_order;
    const auto window=catalog.window(camera);
    std::array<const DrawOwner*,2> owners{};
    for(std::size_t i=0;i<roster.live.size();++i) {
        const auto& owner=roster.live[i];
        if(owner.kind!=OwnerKind::background_tiles && owner.kind!=OwnerKind::solid_tiles) continue;
        const unsigned layer=owner.kind==OwnerKind::background_tiles?0:1;
        if(owners[layer] || owner.room || !owner.identity || !owner.visible || owner.hud_excluded ||
            owner.sort_depth_band!=(layer==0?10000:-10000) || std::count(roster.dispatch.begin(),roster.dispatch.end(),i)!=1)
            throw std::invalid_argument("Invalid global terrain owner/dispatch binding");
        owners[layer]=&owner;
    }
    if(!owners[0] || !owners[1] || owners[0]->identity==owners[1]->identity)
        throw std::invalid_argument("Expected two distinct persistent terrain owners");
    stream<<std::setprecision(std::numeric_limits<float>::max_digits10)<<std::boolalpha;
    for(unsigned layer=0;layer<2;++layer) {
        stream<<"{\"event\":\"terrain-draw\",\"tick\":"<<tick<<",\"layer\":\""<<(layer==0?"B":"F")
            <<"\",\"owner\":"<<owners[layer]->identity<<",\"depth\":"<<owners[layer]->sort_depth_band
            <<",\"camera\":["<<camera.x<<','<<camera.y<<"],\"renderCamera\":["<<std::floor(camera.x)<<','<<std::floor(camera.y)
            <<"],\"viewport\":[320,180],\"window\":["<<window.left<<','<<window.top<<','<<window.right<<','<<window.bottom
            <<"],\"outsideCatalog\":"<<window.outside_catalog<<",\"commands\":[";
        bool first=true;
        catalog.project(layer==0,camera,{320,180},[&](const auto& command) {
            if(!first) stream<<',';
            first=false;
            stream<<'['<<command.material<<','<<command.position.x<<','<<command.position.y<<']';
        });
        stream<<"]}\n";
    }
    if(!stream) throw std::runtime_error("Failed writing terrain window commands");
}
}
