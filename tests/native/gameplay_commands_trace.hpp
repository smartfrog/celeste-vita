#pragma once
#include "gameplay_commands.hpp"
#include <iomanip>
#include <limits>
#include <ostream>
#include <stdexcept>

namespace native_test {
inline const char* gameplay_component(celeste::gameplay_commands::Component component) {
    using C=celeste::gameplay_commands::Component;
    switch(component) {
    case C::direct:return nullptr;
    case C::tile_grid:return "TileGrid";
    case C::decal_image:return "DecalImage";
    case C::banner:return "Banner";
    case C::image:return "Image";
    case C::player_hair:return "PlayerHair";
    case C::player_sprite:return "PlayerSprite";
    case C::sprite:return "Sprite";
    }
    throw std::invalid_argument("Unknown gameplay component");
}
inline const char* gameplay_empty(celeste::gameplay_commands::EmptyReason reason) {
    using R=celeste::gameplay_commands::EmptyReason;
    switch(reason) {
    case R::scene_helper_has_no_capture_calls:return "scene-helper-no-capture-calls";
    case R::wind_has_no_capture_calls:return "wind-no-capture-calls";
    case R::particle_system_has_no_active_images:return "particle-system-no-active-images";
    }
    throw std::invalid_argument("Unknown gameplay empty policy");
}
inline const char* gameplay_kind(celeste::draw_order::OwnerKind kind) {
    using K=celeste::draw_order::OwnerKind;
    switch(kind) {
    case K::background_tiles:return "BackgroundTiles";
    case K::solid_tiles:return "SolidTiles";
    case K::player:return "Player";
    case K::decal:return "Decal";
    case K::spikes:return "Spikes";
    case K::jumpthru_platform:return "JumpthruPlatform";
    case K::strawberry:return "Strawberry";
    case K::spring:return "Spring";
    case K::particle_system_back:case K::particle_system_mid:case K::particle_system_front:return "ParticleSystem";
    case K::scene_helper:return "Entity";
    case K::wind:return "WindController";
    case K::hud_display:return "TotalStrawberriesDisplay";
    }
    throw std::invalid_argument("Unknown gameplay owner kind");
}
inline void write_logical_vec(std::ostream& stream,celeste::Vec2 value) { stream<<'['<<value.x<<','<<value.y<<']'; }
template<class Image> void write_image_descriptor(std::ostream& stream,const Image& image) {
    stream<<",\"texture\":"<<std::quoted(image.texture)<<",\"sheet\":"<<std::quoted(image.sheet)
        <<",\"sourceRectangle\":["<<image.source_x<<','<<image.source_y<<','<<image.source_width<<','<<image.source_height<<"],\"position\":";
    write_logical_vec(stream,image.position);stream<<",\"origin\":";write_logical_vec(stream,image.origin);
    stream<<",\"scale\":";write_logical_vec(stream,image.scale);
    stream<<",\"color\":["<<unsigned(image.color.r)<<','<<unsigned(image.color.g)<<','<<unsigned(image.color.b)<<','<<unsigned(image.color.a)
        <<"],\"rotation\":"<<image.rotation<<",\"effects\":"<<std::quoted(image.effects);
}
inline void write_image_geometry(std::ostream& stream,const celeste::decal_commands::DecalGeometry& geometry,int width,int height) {
    stream<<",\"dimensions\":["<<width<<','<<height<<"],\"finiteGeometry\":"<<geometry.finite<<",\"verticesFloat32Bits\":[";
    for(std::size_t vertex=0;vertex<geometry.vertices.size();++vertex) {
        if(vertex) stream<<',';
        stream<<'[';
        for(std::size_t field=0;field<geometry.vertices[vertex].size();++field) {
            if(field) stream<<',';
            stream<<geometry.vertices[vertex][field];
        }
        stream<<']';
    }
    stream<<']';
}
inline void write_gameplay_schedule(std::ostream& stream,int tick,const celeste::gameplay_commands::Schedule& schedule) {
    stream<<std::setprecision(std::numeric_limits<float>::max_digits10)<<std::boolalpha;
    stream<<"{\"event\":\"gameplay-dispatch\",\"tick\":"<<tick<<",\"ranges\":[";
    bool first=true;
    for(const auto& range:schedule.ranges()) {
        if(!first) stream<<',';
        first=false;
        stream<<"{\"ownerIdentity\":"<<range.identity<<",\"kind\":"<<std::quoted(gameplay_kind(range.kind))
            <<",\"room\":"<<std::quoted(range.room)<<",\"authoredId\":"<<range.authored_id<<",\"background\":"<<range.background
            <<",\"begin\":"<<range.begin<<",\"end\":"<<range.end<<",\"emptyReason\":";
        if(range.empty) stream<<std::quoted(gameplay_empty(*range.empty));else stream<<"null";
        stream<<'}';
    }
    stream<<"],\"excluded\":[";first=true;
    for(const auto& excluded:schedule.excluded()) {
        if(!first) stream<<',';
        first=false;
        stream<<"{\"ownerIdentity\":"<<excluded.identity<<",\"reason\":\"hud-outside-gameplay-capture\"}";
    }
    stream<<"]}\n";
    std::size_t words=0;
    for(std::size_t index=0;index<schedule.commands().size();++index) {
        const auto& command=schedule.commands()[index];
        stream<<"{\"event\":\"gameplay-command\",\"tick\":"<<tick<<",\"index\":"<<index
            <<",\"ownerIdentity\":"<<command.image.identity<<",\"dispatchIndex\":"<<command.dispatch_index
            <<",\"piece\":"<<command.piece<<",\"componentType\":";
        if(const auto component=gameplay_component(command.component)) stream<<std::quoted(component);else stream<<"null";
        write_image_descriptor(stream,command.image);
        stream<<",\"clipping\":\"atlas source rectangle; GPU scissor not observed\"";
        write_image_geometry(stream,command.geometry,command.sheet_width,command.sheet_height);
        stream<<"}\n";
        for(const auto& vertex:command.geometry.vertices) words+=vertex.size();
    }
    stream<<"{\"event\":\"gameplay-frame\",\"tick\":"<<tick<<",\"commands\":"<<schedule.commands().size()
        <<",\"geometryWords\":"<<words<<",\"renderCalls\":1}\n";
    if(!stream) throw std::runtime_error("Failed writing immutable gameplay schedule");
}
}
