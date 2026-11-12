#include "rooms.hpp"
#include "draw_order.hpp"
#include "source_math.hpp"
#include <algorithm>
#include <cmath>
#include <stdexcept>

namespace celeste {
bool RoomBounds::contains(Vec2 p) const { return p.x>=float(x) && p.y>=float(y) && p.x<float(std::int64_t(x)+width) && p.y<float(std::int64_t(y)+height); }
RoomCatalog::RoomCatalog(std::vector<RoomDefinition> rooms) : rooms_(std::move(rooms)) {
    if(rooms_.size()!=2 || rooms_[0].name==rooms_[1].name) throw std::invalid_argument("Room catalog requires two distinct rooms");
    for(const auto& room:rooms_) {
        if(room.name.empty() || room.bounds.width!=320 || room.bounds.height!=180 ||
           room.bounds.x>INT32_MAX-320 || room.bounds.y<INT32_MIN+24 || room.bounds.y>INT32_MAX-184 || !room.bounds.contains(room.spawn))
            throw std::invalid_argument("Unsupported bounded room definition");
        std::vector<int> ids;
        for(const auto& object:room.objects) {
            if(object.id<0 || !std::isfinite(object.position.x) || !std::isfinite(object.position.y) ||
               std::find(ids.begin(),ids.end(),object.id)!=ids.end()) throw std::invalid_argument("Invalid room object identity/position");
            if((object.kind==RoomObjectKind::spike_up || object.kind==RoomObjectKind::spike_left || object.kind==RoomObjectKind::jump_thru) &&
               (object.size<=0 || object.size>136 || object.size%8!=0)) throw std::invalid_argument("Invalid bounded room object size");
            ids.push_back(object.id);
        }
    }
}
const RoomDefinition* RoomCatalog::at(Vec2 point) const {
    if(!std::isfinite(point.x) || !std::isfinite(point.y)) throw std::invalid_argument("Invalid room lookup");
    for(const auto& room:rooms_) if(room.bounds.contains(point)) return &room;
    return nullptr;
}
void RoomWind::update(float delta) {
    if(speed.x!=0 || speed.y!=0) throw std::runtime_error("Unsupported nonzero wind outside the no-wind profile");
    speed.x=source_math::approach(speed.x,0,1000.f*delta);
    speed.y=source_math::approach(speed.y,0,1000.f*delta);
}
RoomEntity::RoomEntity(int id,RoomObject value) : authored_id(id),object(std::move(value)) {}
int RoomEntity::tag() const { return std::holds_alternative<RoomWind>(object) ? 4 : 0; }
int RoomEntity::depth() const {
    if(std::holds_alternative<StaticSpike>(object)) return -1;
    if(std::holds_alternative<RoomJumpThru>(object)) return -60;
    if(std::holds_alternative<RoomStrawberry>(object)) return -100;
    if(std::holds_alternative<RoomSpring>(object)) return -9999;
    return 0;
}
Vec2 RoomEntity::position() const {
    return std::visit([](const auto& value)->Vec2 {
        using T=std::decay_t<decltype(value)>;
        if constexpr(std::is_same_v<T,StaticSpike>) return value.body().position;
        else if constexpr(std::is_same_v<T,RoomWind>) return {};
        else if constexpr(std::is_same_v<T,RoomSceneHelper>) return value.position;
        else return value.body.position;
    },object);
}
const Body* RoomEntity::body() const {
    return std::visit([](const auto& value)->const Body* {
        using T=std::decay_t<decltype(value)>;
        if constexpr(std::is_same_v<T,StaticSpike>) return &value.body();
        else if constexpr(std::is_same_v<T,RoomSceneHelper> || std::is_same_v<T,RoomWind>) return nullptr;
        else return &value.body;
    },object);
}
void RoomEntity::update(float delta) {
    if(!std::isfinite(delta) || delta<0) throw std::invalid_argument("Invalid room entity delta");
    ++updates;
    if(auto* wind=std::get_if<RoomWind>(&object)) wind->update(delta);
    if(auto* spring=std::get_if<RoomSpring>(&object)) ++spring->updates;
    if(auto* berry=std::get_if<RoomStrawberry>(&object)) {
        ++berry->updates;
        berry->wobble+=delta*4.f;
        berry->light_y=float(std::sin(double(berry->wobble)))*2.f;
        berry->sprite_timer+=delta;
        if(berry->sprite_timer>=0.1f) {
            berry->sprite_timer-=0.1f;
            berry->sprite_frame=(berry->sprite_frame+1)%36;
            if(berry->sprite_frame==35) throw std::runtime_error("Unsupported Strawberry.OnAnimate pulse beyond the bounded route");
        }
        berry->light_alpha_multiplier=source_math::approach(berry->light_alpha_multiplier,1,delta*4.f);
    }
}
RoomRuntime::RoomRuntime(const RoomDefinition& data,const StaticWorld& collision,bool initial,
                         const draw_order::AuthoredDecalOwners* visual_owners) : definition(data),scoped_random(data.load_seed) {
    if(visual_owners) {
        if(visual_owners->room!=&data) throw std::invalid_argument("Visual metadata must bind the exact room definition");
        if(visual_owners->background_count<0 || visual_owners->foreground_count<0)
            throw std::invalid_argument("Visual initialization requires complete authored layer counts");
        draw_order::validate_authored_decals({*visual_owners});
        for(const auto& owner:visual_owners->owners)
            if(owner.room!=&data || (owner.identity&0xffff'0000'0000'0000ull)!=0x6000'0000'0000'0000ull)
                throw std::invalid_argument("Visual metadata owner identity/binding is outside the authored namespace");
    }
    scoped_random.observer=[this](const char* operation,unsigned calls) { random_events.emplace_back(operation,calls); };
    if(initial) entities.push_back(std::make_unique<RoomEntity>(-1,RoomSceneHelper{}));
    entities.push_back(std::make_unique<RoomEntity>(-2,RoomWind{}));
    for(const auto& object:data.objects) {
        RoomObject value;
        std::vector<std::pair<int,int>> image_cells;
        switch(object.kind) {
        case RoomObjectKind::spike_up: case RoomObjectKind::spike_left:
            value=StaticSpike(object.position,object.size,object.kind==RoomObjectKind::spike_up ? SpikeDirection::up : SpikeDirection::left);
            for(int i=0;i<object.size/8;++i) image_cells.emplace_back(scoped_random.next(1),0);
            break;
        case RoomObjectKind::jump_thru:
            value=RoomJumpThru{Body{object.position,Hitbox{float(object.size),5,{}},true}};
            break;
        case RoomObjectKind::spring: {
            RoomSpring spring{Body{object.position,Hitbox{16,6,{-8,-6}},true}};
            const Vec2 at{object.position.x,object.position.y+1};
            spring.attached=collision.first_solid(spring.body,at);
            if(!spring.attached) spring.attached=collision.first_outside_jump_thru(spring.body,at);
            if(!spring.attached) throw std::runtime_error("Unsupported unattached destination Spring");
            value=spring;
            break;
        }
        case RoomObjectKind::strawberry:
            value=RoomStrawberry{Body{object.position,Hitbox{14,14,{-7,-7}},true}};
            break;
        default: throw std::invalid_argument("Unsupported room object kind");
        }
        entities.push_back(std::make_unique<RoomEntity>(object.id,std::move(value)));
        entities.back()->image_cells=std::move(image_cells);
    }
    if(visual_owners) {
        PresentationRandom visual_random(scoped_random);
        visual_random.observer={};
        auto added=visual_owners->owners;
        std::sort(added.begin(),added.end(),[](const auto& left,const auto& right) {
            return left.authored_id<right.authored_id;
        });
        for(const bool background:{false,true}) for(const auto& owner:added)
            if(owner.banner && owner.sort_depth_band==(background?9000:-10500))
                banners_.push_back({owner.identity,float(visual_random.next_double())});
    }
    for(const auto& entity:entities) if(const auto* platform=std::get_if<RoomJumpThru>(&entity->object)) {
        const int columns=int(platform->body.collider->width)/8;
        for(int i=0;i<columns;++i) {
            int x=0,y=0;
            if(i==0) y=collision.first_solid(platform->body,{platform->body.position.x-1,platform->body.position.y}) ? 0 : 1;
            else if(i==columns-1) {
                x=2;y=collision.first_solid(platform->body,{platform->body.position.x+1,platform->body.position.y}) ? 0 : 1;
            } else { x=1+scoped_random.next(1);y=scoped_random.next(2); }
            entity->image_cells.emplace_back(x,y);
        }
    }
}
float RoomRuntime::banner_phase(std::uint64_t authored_identity) const {
    const auto found=std::find_if(banners_.begin(),banners_.end(),[&](const BannerState& banner) { return banner.authored_identity==authored_identity; });
    if(found==banners_.end()) throw std::logic_error("Missing room-instance Banner phase");
    return found->sine_timer;
}
void RoomRuntime::update_banners(float delta) {
    if(!std::isfinite(delta) || delta<0) throw std::invalid_argument("Invalid Banner update delta");
    for(auto& banner:banners_) banner.sine_timer+=delta*1.f;
}
void RoomRuntime::update(float delta,bool transitioning) {
    if(!std::isfinite(delta) || delta<0) throw std::invalid_argument("Invalid room update delta");
    if(!transitioning) update_banners(delta);
    for(const auto& entity:entities) if(entity->present && entity->should_update(transitioning)) entity->update(delta);
}
}
