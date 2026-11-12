#include "spring_commands.hpp"
#include "atlas_frame_text.hpp"
#include <algorithm>
#include <cmath>
#include <stdexcept>

namespace celeste::spring_commands {
namespace {
void validate(const Catalog& catalog) {
    const auto& frame=catalog.idle;
    atlas_frame_text::validate(frame);
    if(catalog.idle_texture.empty() || frame.texture!=catalog.idle_texture ||
       frame.offset_x>0 || frame.offset_y>0 || std::floor(frame.offset_x)!=frame.offset_x || std::floor(frame.offset_y)!=frame.offset_y ||
       -frame.offset_x>frame.frame_width-frame.width || -frame.offset_y>frame.frame_height-frame.height)
        throw std::invalid_argument("Unsupported Spring idle material/trim");
}
void validate(const RoomSpring& spring) {
    const auto& body=spring.body;
    if(!spring.attached || spring.wiggler!=0 || !body.collidable || !body.collider ||
       body.collider->width!=16 || body.collider->height!=6 || body.collider->offset.x!=-8 || body.collider->offset.y!=-6 ||
       !std::isfinite(body.position.x) || !std::isfinite(body.position.y))
        throw std::invalid_argument("Unsupported non-idle floor Spring");
}
}
Catalog parse(std::string_view text,std::uint32_t expected_checksum) {
    using asset_text::take;
    asset_text::integrity(text,catalog_byte_limit,expected_checksum);
    if(take(text)!="CSPR1") throw std::invalid_argument("Wrong Spring catalog version");
    for(const auto pin:provenance)
        if(take(text)!=pin) throw std::invalid_argument("Spring catalog provenance changed");
    if(take(text)!="floor idle 0 0" || take(text)!="1")
        throw std::invalid_argument("Unsupported Spring orientation/animation/frame/wiggler");
    Catalog result;
    result.idle=atlas_frame_text::parse(take(text));
    result.idle_texture="objects/spring/00";
    if(!text.empty()) throw std::invalid_argument("Trailing Spring catalog data");
    if(result.idle.sheet!="Gameplay0") throw std::invalid_argument("Unsupported Spring command sheet");
    validate(result);
    return result;
}
std::vector<Command> project(const draw_order::DrawProjection& drawn,const Catalog& catalog,
                             const std::vector<const RoomRuntime*>& rooms) {
    validate(catalog);
    for(const auto* room:rooms) if(!room) throw std::invalid_argument("Null Spring room instance");
    std::vector<Command> result;
    std::vector<std::uint64_t> dispatched;
    for(std::size_t dispatch=0;dispatch<drawn.dispatch.size();++dispatch) {
        const auto index=drawn.dispatch[dispatch];
        if(index>=drawn.live.size()) throw std::invalid_argument("Spring dispatch index out of range");
        const auto& owner=drawn.live[index];
        if(owner.kind!=draw_order::OwnerKind::spring) continue;
        if(!owner.identity || !owner.room || owner.authored_id<0 || !owner.visible || owner.hud_excluded || owner.banner ||
           owner.sort_depth_band!=-8501 || owner.scale.x!=1 || owner.scale.y!=1 ||
           std::find(dispatched.begin(),dispatched.end(),owner.identity)!=dispatched.end())
            throw std::invalid_argument("Invalid Spring dispatch owner");
        dispatched.push_back(owner.identity);
        const RoomEntity* entity=nullptr;const RoomRuntime* instance=nullptr;
        for(const auto* room:rooms) for(const auto& candidate:room->entities) if(candidate->object_identity==owner.identity) {
            if(entity) throw std::invalid_argument("Ambiguous Spring room instance");
            entity=candidate.get();instance=room;
        }
        if(!entity || &instance->definition!=owner.room || entity->authored_id!=owner.authored_id || !entity->present ||
           !std::holds_alternative<RoomSpring>(entity->object))
            throw std::invalid_argument("Spring owner does not bind its actual native room entity");
        const RoomObjectDefinition* authored=nullptr;
        for(const auto& object:instance->definition.objects) if(object.id==entity->authored_id) {
            if(authored) throw std::invalid_argument("Ambiguous authored Spring identity");
            authored=&object;
        }
        if(!authored || authored->kind!=RoomObjectKind::spring)
            throw std::invalid_argument("Spring owner does not bind an authored floor Spring");
        const auto& spring=std::get<RoomSpring>(entity->object);
        validate(spring);
        const auto& frame=catalog.idle;
        decal_commands::DecalCommand image;
        image.identity=owner.identity;image.room=owner.room->name;image.texture=frame.texture;image.sheet=frame.sheet;
        image.source_x=frame.x;image.source_y=frame.y;image.source_width=frame.width;image.source_height=frame.height;
        image.origin={float(frame.frame_width)/2.f+frame.offset_x,float(frame.frame_height)+frame.offset_y};
        image.color={0,0,0,255};
        unsigned piece=0;
        for(int x=-1;x<=1;++x) for(int y=-1;y<=1;++y) if(x!=0 || y!=0) {
            image.position={spring.body.position.x+float(x),spring.body.position.y+float(y)};
            result.push_back({image,entity->authored_id,piece++,dispatch});
        }
        image.position=spring.body.position;image.color={255,255,255,255};
        result.push_back({std::move(image),entity->authored_id,piece,dispatch});
    }
    return result;
}
}
