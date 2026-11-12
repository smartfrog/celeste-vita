#include "jumpthru_commands.hpp"
#include "asset_text.hpp"
#include <algorithm>
#include <cmath>
#include <stdexcept>

namespace celeste::jumpthru_commands {
namespace {
void validate(const decal_commands::AtlasFrame& frame) {
    if(frame.texture!="objects/jumpthru/wood" || frame.sheet!="Gameplay0" ||
       frame.x<0 || frame.y<0 || frame.width!=24 || frame.height<=8 || frame.height>16 ||
       frame.x>4096-frame.width || frame.y>4096-frame.height ||
       frame.frame_width!=24 || frame.frame_height!=16 || frame.offset_x!=0 || frame.offset_y!=0)
        throw std::invalid_argument("Unsupported bounded JumpThru material/trim");
}
}
Catalog parse(std::string_view text,std::uint32_t expected_checksum) {
    using namespace asset_text;
    integrity(text,1024,expected_checksum);
    if(take(text)!="CJTC1" ||
       take(text)!="256d58907b477c9c7f42bbcd5813fe7486f0881b91d504a622cf2f5582c4019e" ||
       take(text)!="45847f23970911b07541e4bc367cbd156f3b4b1846b63b33d3fed9c7b65ebf6b" ||
       take(text)!="aa87a22589821fc3781672126e68f2195fb46348f261013d8a01c070b53821d3" ||
       take(text)!="1f23b1f35544a3751ffec170b0230c7c9513000ab1549f78ebb9cb9f4203c8d9" ||
       take(text)!="b75f913d315bd641c35a4990d9041b238c0d9ef3f8b1247ec557de8a9defc1cc")
        throw std::invalid_argument("JumpThru catalog provenance changed");
    Catalog catalog;
    auto row=take(text);auto& frame=catalog.wood;
    frame.sheet=std::string(take(row,' '));
    frame.x=integer(take(row,' '));frame.y=integer(take(row,' '));
    frame.width=integer(take(row,' '));frame.height=integer(take(row,' '));
    frame.offset_x=float(integer(take(row,' ')));frame.offset_y=float(integer(take(row,' ')));
    frame.frame_width=integer(take(row,' '));frame.frame_height=integer(take(row,' '));
    frame.texture=std::string(row);
    if(!text.empty()) throw std::invalid_argument("Trailing JumpThru catalog data");
    validate(frame);
    return catalog;
}
std::vector<Command> project(const draw_order::DrawProjection& drawn,const Catalog& catalog,
                             const std::vector<const RoomRuntime*>& rooms) {
    validate(catalog.wood);
    std::vector<Command> result;
    std::vector<std::uint64_t> dispatched;
    for(std::size_t dispatch=0;dispatch<drawn.dispatch.size();++dispatch) {
        const auto index=drawn.dispatch[dispatch];
        if(index>=drawn.live.size()) throw std::invalid_argument("JumpThru dispatch index out of range");
        const auto& owner=drawn.live[index];
        if(owner.kind!=draw_order::OwnerKind::jumpthru_platform) continue;
        if(!owner.identity || !owner.room || !owner.visible || owner.hud_excluded || owner.sort_depth_band!=-60 ||
           std::find(dispatched.begin(),dispatched.end(),owner.identity)!=dispatched.end())
            throw std::invalid_argument("Invalid JumpThru dispatch owner");
        dispatched.push_back(owner.identity);
        const RoomEntity* entity=nullptr;const RoomRuntime* instance=nullptr;
        for(const auto* room:rooms) {
            if(!room) throw std::invalid_argument("Null JumpThru room instance");
            for(const auto& candidate:room->entities) if(candidate->object_identity==owner.identity) {
                if(entity) throw std::invalid_argument("Ambiguous JumpThru room instance");
                entity=candidate.get();instance=room;
            }
        }
        if(!entity || &instance->definition!=owner.room || entity->authored_id!=owner.authored_id || !entity->present ||
           !std::holds_alternative<RoomJumpThru>(entity->object))
            throw std::invalid_argument("JumpThru owner does not bind its actual native room entity");
        const auto& body=std::get<RoomJumpThru>(entity->object).body;
        if(!body.collider || !std::isfinite(body.collider->width) || body.collider->width<8 || body.collider->width>136 ||
           int(body.collider->width)%8 || body.collider->width!=float(int(body.collider->width)) ||
           !std::isfinite(body.position.x) || !std::isfinite(body.position.y))
            throw std::invalid_argument("Invalid JumpThru command body");
        const auto& cells=instance->jump_thru_visual(owner.identity).cells;
        if(cells.size()!=std::size_t(body.collider->width/8)) throw std::invalid_argument("Missing JumpThru visual cells");
        const auto& frame=catalog.wood;
        for(unsigned piece=0;piece<cells.size();++piece) {
            const auto [column,row]=cells[piece];
            if(column<0 || column>2 || row<0 || row>1 || column!=(piece==0?0:piece+1==cells.size()?2:1))
                throw std::invalid_argument("Invalid JumpThru visual variant");
            decal_commands::DecalCommand image;
            image.identity=owner.identity;image.room=owner.room->name;image.texture=frame.texture;image.sheet=frame.sheet;
            image.source_x=frame.x+column*8;image.source_y=std::min(frame.y+row*8,frame.y+frame.height);
            image.source_width=8;image.source_height=std::max(0,std::min(8,frame.y+frame.height-image.source_y));
            image.position={body.position.x+float(piece*8),body.position.y};
            result.push_back({std::move(image),entity->authored_id,piece,dispatch});
        }
    }
    return result;
}
}
