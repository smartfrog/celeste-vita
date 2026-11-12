#include "decal_commands.hpp"
#include <algorithm>
#include <cmath>
#include <stdexcept>

namespace celeste::decal_commands {
namespace {
void validate_frame(const AtlasFrame& frame) {
    if(frame.sheet.empty() || frame.x<0 || frame.y<0 || frame.width<=0 || frame.height<=0 ||
       frame.width>4096 || frame.height>4096 || frame.x>4096-frame.width || frame.y>4096-frame.height ||
       !std::isfinite(frame.offset_x) || !std::isfinite(frame.offset_y) ||
       std::abs(frame.offset_x)>4096 || std::abs(frame.offset_y)>4096 ||
       frame.frame_width<=0 || frame.frame_height<=0 || frame.texture.empty())
        throw std::invalid_argument("Invalid static decal atlas frame");
}
void validate_catalog(const StaticDecalCatalog& catalog) {
    if(catalog.families.empty() || catalog.owners.empty() || catalog.deferred.empty())
        throw std::invalid_argument("Incomplete static decal descriptor catalog");
    for(const auto& frame:catalog.families) validate_frame(frame);
    std::vector<std::uint64_t> identities;
    const auto add_identity=[&](std::uint64_t identity) {
        if(!identity) throw std::invalid_argument("Static decal descriptor identity is unset");
        if(std::find(identities.begin(),identities.end(),identity)!=identities.end())
            throw std::invalid_argument("Duplicate or aliased static decal descriptor identity");
        identities.push_back(identity);
    };
    for(const auto& owner:catalog.owners) {
        if(owner.room.empty() || owner.ordinal<0 || owner.family>=catalog.families.size() || owner.texture.empty())
            throw std::invalid_argument("Invalid static decal descriptor");
        if(catalog.families[owner.family].texture!=owner.texture)
            throw std::invalid_argument("Static decal descriptor is not bound to its atlas key");
        add_identity(owner.identity);
    }
    for(const auto& deferred:catalog.deferred) {
        if(deferred.room.empty() || deferred.ordinal<0 || deferred.texture.empty())
            throw std::invalid_argument("Invalid deferred decal descriptor");
        add_identity(deferred.identity);
    }
}
const StaticDecalOwner& static_descriptor(const StaticDecalCatalog& catalog,std::uint64_t identity) {
    const auto match=std::find_if(catalog.owners.begin(),catalog.owners.end(),
        [&](const StaticDecalOwner& owner) { return owner.identity==identity; });
    if(match==catalog.owners.end()) throw std::invalid_argument("A static decal owner has no descriptor");
    return *match;
}
const DeferredDecalOwner& deferred_descriptor(const StaticDecalCatalog& catalog,std::uint64_t identity) {
    const auto match=std::find_if(catalog.deferred.begin(),catalog.deferred.end(),
        [&](const DeferredDecalOwner& owner) { return owner.identity==identity; });
    if(match==catalog.deferred.end()) throw std::invalid_argument("A Banner decal owner has no deferred descriptor");
    return *match;
}
void validate_owner(const draw_order::DrawOwner& owner) {
    if(!owner.room || owner.authored_id<0 || owner.texture.empty())
        throw std::invalid_argument("Invalid decal draw owner binding");
    if(owner.sort_depth_band!=9000 && owner.sort_depth_band!=-10500)
        throw std::invalid_argument("Decal draw owner is outside the observed SOURCE layers");
    if(!std::isfinite(owner.position.x) || !std::isfinite(owner.position.y) ||
       !std::isfinite(owner.scale.x) || !std::isfinite(owner.scale.y))
        throw std::invalid_argument("Nonfinite static decal geometry");
}
void match_static(const draw_order::DrawOwner& owner,const StaticDecalOwner& descriptor) {
    if(descriptor.room!=owner.room->name || descriptor.background!=(owner.sort_depth_band>0) ||
       descriptor.ordinal!=owner.authored_id || descriptor.texture!=owner.texture)
        throw std::invalid_argument("Static decal descriptor differs from its live owner");
    if(owner.scale.x!=1 && owner.scale.x!=-1) throw std::invalid_argument("Unsupported static decal X scale");
    if(owner.scale.y!=1 && owner.scale.y!=-1) throw std::invalid_argument("Unsupported static decal Y scale");
}
void match_deferred(const draw_order::DrawOwner& owner,const DeferredDecalOwner& descriptor) {
    if(descriptor.room!=owner.room->name || descriptor.background!=(owner.sort_depth_band>0) ||
       descriptor.ordinal!=owner.authored_id || descriptor.texture!=owner.texture)
        throw std::invalid_argument("Deferred decal descriptor differs from its live Banner owner");
}
}
DecalProjection project(const draw_order::DrawProjection& drawn,const StaticDecalCatalog& catalog) {
    validate_catalog(catalog);
    DecalProjection result;
    std::vector<std::size_t> dispatched;
    for(const auto index:drawn.dispatch) {
        if(index>=drawn.live.size()) throw std::invalid_argument("Decal dispatch index is out of range");
        if(std::find(dispatched.begin(),dispatched.end(),index)!=dispatched.end())
            throw std::invalid_argument("A decal owner is dispatched twice");
        dispatched.push_back(index);
        const auto& owner=drawn.live[index];
        if(owner.kind!=draw_order::OwnerKind::decal) continue;
        validate_owner(owner);
        if(owner.banner) {
            const auto& descriptor=deferred_descriptor(catalog,owner.identity);
            match_deferred(owner,descriptor);
            result.deferred.push_back(descriptor);
            continue;
        }
        const auto& descriptor=static_descriptor(catalog,owner.identity);
        match_static(owner,descriptor);
        const auto& frame=catalog.families[descriptor.family];
        DecalCommand command;
        command.identity=owner.identity;
        command.room=descriptor.room;
        command.background=descriptor.background;
        command.ordinal=descriptor.ordinal;
        command.texture=descriptor.texture;
        command.sheet=frame.sheet;
        command.source_x=frame.x;
        command.source_y=frame.y;
        command.source_width=frame.width;
        command.source_height=frame.height;
        command.position=owner.position;
        command.origin={float(frame.frame_width)*0.5f+frame.offset_x,
                        float(frame.frame_height)*0.5f+frame.offset_y};
        command.scale=owner.scale;
        command.rotation=0;
        command.effects="None";
        result.commands.push_back(std::move(command));
    }
    return result;
}
}
