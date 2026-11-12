#include "strawberry_commands.hpp"
#include "atlas_frame_text.hpp"
#include <algorithm>
#include <cmath>
#include <set>

namespace celeste::strawberry_commands {
namespace {
void validate_catalog(const Catalog& catalog) {
    for(const auto& pin:catalog.provenance)
        if(pin.size()!=64 || pin.find_first_not_of("0123456789abcdef")!=std::string::npos)
            throw std::invalid_argument("Invalid Strawberry provenance pin");
    std::set<std::string> textures;
    for(const auto& frame:catalog.frames) {
        atlas_frame_text::validate(frame);
        if(!textures.insert(frame.texture).second) throw std::invalid_argument("Duplicate Strawberry atlas key");
    }
    for(const auto frame:catalog.idle)
        if(frame>=catalog.frames.size()) throw std::invalid_argument("Strawberry idle texture index is out of range");
}
const RoomRosterEntry& roster_entity(const std::vector<RoomRosterEntry>& roster,std::uint64_t identity) {
    const RoomRosterEntry* match=nullptr;
    for(const auto& entry:roster) if(entry.entity && entry.entity->object_identity==identity) {
        if(match) throw std::invalid_argument("Aliased Strawberry roster identity");
        match=&entry;
    }
    if(!match) throw std::invalid_argument("Dispatched Strawberry has no roster entity");
    return *match;
}
}
Catalog parse(std::string_view text,std::uint32_t expected_checksum) {
    using asset_text::take;
    using asset_text::integer;
    asset_text::integrity(text,catalog_byte_limit,expected_checksum);
    if(take(text)!="CSTR1") throw std::invalid_argument("Wrong Strawberry catalog version");
    Catalog result;
    for(auto& pin:result.provenance) pin=std::string(take(text));
    if(take(text)!="idle 36") throw std::invalid_argument("Unsupported Strawberry animation");
    auto sequence=take(text);
    for(std::size_t index=0;index<result.idle.size();++index)
        result.idle[index]=unsigned(integer(index+1==result.idle.size()?sequence:take(sequence,' ')));
    if(integer(take(text))!=8) throw std::invalid_argument("Strawberry catalog requires eight frames");
    for(std::size_t index=0;index<result.frames.size();++index) {
        auto row=take(text);
        if(integer(take(row,' '))!=int(index)) throw std::invalid_argument("Unordered Strawberry frame index");
        result.frames[index]=atlas_frame_text::parse(row);
    }
    if(!text.empty()) throw std::invalid_argument("Trailing Strawberry catalog data");
    validate_catalog(result);
    return result;
}
std::vector<Command> project(const draw_order::DrawProjection& drawn,
                             const std::vector<RoomRosterEntry>& roster,const Catalog& catalog) {
    validate_catalog(catalog);
    std::vector<Command> commands;
    std::set<std::size_t> dispatched;
    std::set<std::uint64_t> identities;
    for(const auto index:drawn.dispatch) {
        if(index>=drawn.live.size() || !dispatched.insert(index).second)
            throw std::invalid_argument("Invalid or duplicate Strawberry dispatch index");
        const auto& owner=drawn.live[index];
        if(owner.kind!=draw_order::OwnerKind::strawberry) continue;
        if(!identities.insert(owner.identity).second) throw std::invalid_argument("Aliased Strawberry draw owner identity");
        if(!owner.identity || owner.authored_id<0 || !owner.room || !owner.visible || owner.hud_excluded ||
           owner.scale.x!=1 || owner.scale.y!=1)
            throw std::invalid_argument("Invalid Strawberry draw owner binding");
        const auto& entry=roster_entity(roster,owner.identity);
        if(!entry.room || owner.room!=&entry.room->definition || owner.authored_id!=entry.entity->authored_id || !entry.entity->present)
            throw std::invalid_argument("Strawberry draw owner differs from its live roster entity");
        const auto* berry=std::get_if<RoomStrawberry>(&entry.entity->object);
        if(!berry) throw std::invalid_argument("Strawberry owner has no Strawberry visual state");
        if(berry->sprite_frame>=35) throw std::invalid_argument("Unsupported Strawberry pulse/animation branch");
        const auto at=berry->body.position;
        if(!std::isfinite(at.x) || !std::isfinite(at.y) || !std::isfinite(berry->light_y))
            throw std::invalid_argument("Nonfinite Strawberry Sprite position");
        Command command;
        command.identity=owner.identity;command.room=entry.room->definition.name;command.authored_id=owner.authored_id;
        command.animation_frame=berry->sprite_frame;command.texture_frame=catalog.idle[berry->sprite_frame];
        const auto& frame=catalog.frames[command.texture_frame];
        command.texture=frame.texture;command.sheet=frame.sheet;
        command.source_x=frame.x;command.source_y=frame.y;command.source_width=frame.width;command.source_height=frame.height;
        command.position={at.x,at.y+berry->light_y};
        command.origin={frame.frame_width*0.5f+frame.offset_x,frame.frame_height*0.5f+frame.offset_y};
        commands.push_back(std::move(command));
    }
    return commands;
}
}
