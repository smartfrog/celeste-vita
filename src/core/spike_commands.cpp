#include "spike_commands.hpp"
#include "asset_text.hpp"
#include <algorithm>
#include <cmath>
#include <stdexcept>

namespace celeste::spike_commands {
namespace {
using asset_text::take;
using asset_text::integer;

bool identity(std::string_view value) {
    return !value.empty() && value.size()<=192 && value.front()!='/' &&
        value.find("..")==std::string_view::npos &&
        value.find_first_not_of("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_/.\\-")==std::string_view::npos;
}
void validate_frame(const decal_commands::AtlasFrame& frame) {
    if(frame.sheet.empty() || frame.sheet.size()>64 ||
       frame.sheet.find_first_not_of("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_")!=std::string::npos ||
       !identity(frame.texture) || frame.x<0 || frame.y<0 || frame.width<=0 || frame.height<=0 ||
       frame.x>4096-frame.width || frame.y>4096-frame.height ||
       !std::isfinite(frame.offset_x) || !std::isfinite(frame.offset_y) ||
       std::abs(frame.offset_x)>4096 || std::abs(frame.offset_y)>4096 ||
       frame.frame_width<=0 || frame.frame_height<=0 ||
       frame.frame_width>4096 || frame.frame_height>4096)
        throw std::invalid_argument("Invalid spike atlas frame");
}
void validate_catalog(const Catalog& catalog) {
    validate_frame(catalog.frames[0]);
    validate_frame(catalog.frames[1]);
    for(const auto& pin:catalog.provenance)
        if(pin.size()!=64 || pin.find_first_not_of("0123456789abcdef")!=std::string::npos)
            throw std::invalid_argument("Invalid spike catalog provenance pin");
    if(catalog.frames[0].texture==catalog.frames[1].texture)
        throw std::invalid_argument("Duplicate spike atlas key");
}
int direction_index(SpikeDirection direction) {
    if(direction==SpikeDirection::up) return 0;
    if(direction==SpikeDirection::left) return 1;
    throw std::invalid_argument("Unsupported spike direction outside the bounded Up/Left projection");
}
const RoomRosterEntry& roster_entity(const std::vector<RoomRosterEntry>& roster,std::uint64_t identity_value) {
    const RoomRosterEntry* match=nullptr;
    for(const auto& entry:roster) if(entry.entity && entry.entity->object_identity==identity_value) {
        if(match) throw std::invalid_argument("Aliased spike roster identity");
        match=&entry;
    }
    if(!match) throw std::invalid_argument("A dispatched spike has no roster entity");
    return *match;
}
void validate_owner(const draw_order::DrawOwner& owner) {
    if(owner.kind!=draw_order::OwnerKind::spikes || !owner.identity || owner.authored_id<0 || !owner.room ||
       !owner.visible || owner.hud_excluded || owner.scale.x!=1 || owner.scale.y!=1)
        throw std::invalid_argument("Invalid spike draw owner binding");
}
}

Catalog parse(std::string_view text,std::uint32_t expected_checksum) {
    asset_text::integrity(text,catalog_byte_limit,expected_checksum);
    if(take(text)!="CSPK1") throw std::invalid_argument("Wrong spike catalog version");
    Catalog result;
    for(auto& pin:result.provenance) {
        const auto value=take(text);
        if(value.size()!=64 || value.find_first_not_of("0123456789abcdef")!=std::string_view::npos)
            throw std::invalid_argument("Invalid spike catalog provenance pin");
        pin=std::string(value);
    }
    if(integer(take(text))!=2) throw std::invalid_argument("Spike catalog requires the two bounded Up/Left frames");
    for(int index=0;index<2;++index) {
        auto row=take(text);
        const auto direction=take(row,' ');
        if(direction!=(index==0?"up":"left")) throw std::invalid_argument("Unknown or unordered spike catalog direction");
        auto& frame=result.frames[std::size_t(index)];
        frame.sheet=std::string(take(row,' '));
        frame.x=integer(take(row,' '));
        frame.y=integer(take(row,' '));
        frame.width=integer(take(row,' '));
        frame.height=integer(take(row,' '));
        frame.offset_x=float(integer(take(row,' ')));
        frame.offset_y=float(integer(take(row,' ')));
        frame.frame_width=integer(take(row,' '));
        frame.frame_height=integer(take(row,' '));
        frame.texture=std::string(row);
        validate_frame(frame);
    }
    if(result.frames[0].texture==result.frames[1].texture)
        throw std::invalid_argument("Duplicate spike atlas key");
    if(!text.empty()) throw std::invalid_argument("Trailing spike catalog data");
    return result;
}

std::vector<Command> project(const draw_order::DrawProjection& drawn,
                             const std::vector<RoomRosterEntry>& roster,const Catalog& catalog) {
    validate_catalog(catalog);
    std::vector<Command> commands;
    std::vector<std::size_t> dispatched;
    for(const auto index:drawn.dispatch) {
        if(index>=drawn.live.size()) throw std::invalid_argument("Spike dispatch index is out of range");
        if(std::find(dispatched.begin(),dispatched.end(),index)!=dispatched.end())
            throw std::invalid_argument("A spike owner is dispatched twice");
        dispatched.push_back(index);
        const auto& owner=drawn.live[index];
        if(owner.kind!=draw_order::OwnerKind::spikes) continue;
        validate_owner(owner);
        const auto& entry=roster_entity(roster,owner.identity);
        if(!entry.room || owner.room!=&entry.room->definition || entry.entity->authored_id!=owner.authored_id)
            throw std::invalid_argument("Spike draw owner differs from its live roster entity");
        const auto* spike=std::get_if<StaticSpike>(&entry.entity->object);
        if(!spike) throw std::invalid_argument("A spike owner does not hold a static spike entity");
        const int frame_index=direction_index(spike->direction());
        const auto& frame=catalog.frames[std::size_t(frame_index)];
        const auto& body=spike->body();
        if(!body.collider) throw std::invalid_argument("A spike owner has no collider size");
        const float size=spike->direction()==SpikeDirection::up ? body.collider->width : body.collider->height;
        if(!std::isfinite(size) || size<=0 || size>136 || std::fmod(size,8.f)!=0)
            throw std::invalid_argument("Unsupported spike piece size");
        const auto at=entry.entity->position();
        if(!std::isfinite(at.x) || !std::isfinite(at.y))
            throw std::invalid_argument("Nonfinite spike world position");
        const int pieces=int(size)/8;
        if(entry.entity->image_cells.size()!=std::size_t(pieces))
            throw std::invalid_argument("Spike image cells differ from the authored piece count");
        for(int piece=0;piece<pieces;++piece) {
            const auto cell=entry.entity->image_cells[std::size_t(piece)];
            if(cell.first!=0 || cell.second!=0)
                throw std::invalid_argument("Invalid spike image cell outside the singleton source family");
            Command command;
            command.identity=owner.identity;
            command.room=entry.room->definition.name;
            command.authored_id=owner.authored_id;
            command.direction=spike->direction();
            command.piece=piece;
            command.texture=frame.texture;
            command.sheet=frame.sheet;
            command.source_x=frame.x;
            command.source_y=frame.y;
            command.source_width=frame.width;
            command.source_height=frame.height;
            if(spike->direction()==SpikeDirection::up) {
                command.position={at.x+(float(piece)+0.5f)*8.f,at.y+1.f};
                command.origin={frame.frame_width*0.5f+frame.offset_x,frame.frame_height*1.f+frame.offset_y};
            } else {
                command.position={at.x+1.f,at.y+(float(piece)+0.5f)*8.f};
                command.origin={frame.frame_width*1.f+frame.offset_x,frame.frame_height*0.5f+frame.offset_y};
            }
            commands.push_back(std::move(command));
        }
    }
    return commands;
}
}
