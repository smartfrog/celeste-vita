#include "lifecycle.hpp"
#include "source_math.hpp"
#include <algorithm>
#include <stdexcept>

namespace celeste {
std::vector<const RoomEntity*> FirstRoomSession::pending_room_entities() const {
    std::vector<const RoomEntity*> result;
    if(incoming_room_) for(const auto& entity:incoming_room_->entities) result.push_back(entity.get());
    return result;
}
void FirstRoomSession::bind_room_world() {
    world_.spikes.clear();
    world_.ordered_colliders.clear();
    world_.collision.jump_thrus.clear();
    world_.safe_ground=world_.collision.solids;
    for(auto* room:{outgoing_room_.get(),current_room_.get()}) if(room)
        for(const auto& entity:room->entities) if(entity->present) {
            if(auto* spike=std::get_if<StaticSpike>(&entity->object)) {
                world_.spikes.push_back(spike);world_.ordered_colliders.push_back({spike,nullptr,nullptr});
            }
            if(auto* spring=std::get_if<RoomSpring>(&entity->object)) world_.ordered_colliders.push_back({nullptr,&spring->body,"Unsupported Spring.OnCollide contact"});
            if(auto* berry=std::get_if<RoomStrawberry>(&entity->object)) world_.ordered_colliders.push_back({nullptr,&berry->body,"Unsupported Strawberry.OnPlayer collection"});
            if(auto* platform=std::get_if<RoomJumpThru>(&entity->object)) {
                world_.collision.jump_thrus.push_back(&platform->body);
                world_.safe_ground.push_back(&platform->body);
            }
        }
    const auto& bounds=current_room_->definition.bounds;
    world_.bounds_left=bounds.x;world_.bounds_right=bounds.x+bounds.width;
    world_.death_supported=&current_room_->definition==&catalog_->first();
}

void FirstRoomSession::publish_room_roster() {
    room_roster_.clear();
    for(const auto* room:{outgoing_room_.get(),current_room_.get()}) if(room)
        for(const auto& entity:room->entities) if(entity->present) room_roster_.push_back({room,entity.get(),nullptr});
    room_roster_.push_back({nullptr,nullptr,player_.get()});
    const auto depth=[this](const RoomRosterEntry& value) { return value.entity ? value.entity->depth() : (player_->state_machine().state()==14 ? -1000000 : 0); };
    const auto birth=[](const RoomRosterEntry& value) { return value.entity ? value.entity->object_identity : value.player->object_identity(); };
    std::stable_sort(room_roster_.begin(),room_roster_.end(),[&](const auto& left,const auto& right) {
        return depth(left)!=depth(right) ? depth(left)>depth(right) : birth(left)<birth(right);
    });
}

void FirstRoomSession::enforce_room_bounds() {
    const auto& room=current_room_->definition;
    const auto& body=player_->actor().body;
    const auto& box=*body.collider;
    const Vec2 center{body.position.x+box.offset.x+box.width/2.f,body.position.y+box.offset.y+box.height/2.f};
    if(body.position.x+box.offset.x<float(room.bounds.x) || body.position.x+box.offset.x+box.width>float(room.bounds.x+room.bounds.width))
        throw std::runtime_error("Unsupported horizontal boundary outside the bounded route");
    if(center.y<float(room.bounds.y)) {
        const auto* target=catalog_->at({center.x,center.y-12.f});
        if(target && target!=&room) {
            if(&room!=&catalog_->first()) throw std::runtime_error("Unsupported additional room transition");
            player_->before_up_transition();
            pending_room_=target;
        } else if(body.position.y+box.offset.y<float(room.bounds.y-24))
            throw std::runtime_error("Unsupported upper room boundary clamp outside the bounded route");
    }
    const auto* below=catalog_->at({center.x,center.y+12.f});
    if(body.position.y>float(room.bounds.y+room.bounds.height) && below && below!=&room &&
       !world_.collision.first_solid(body,{body.position.x,body.position.y+4.f}))
        throw std::runtime_error("Unsupported downward transition outside the bounded route");
    if(body.position.y+box.offset.y>float(room.bounds.y+room.bounds.height+4)) {
        if(&room!=&catalog_->first()) throw std::runtime_error("Unsupported Room2 fall death/reload");
        player_->die({});
        queue_corpse();
    }
}

void FirstRoomSession::start_room_transition() {
    if(transition_ || !pending_room_ || player_->death().dead) throw std::logic_error("Invalid pending room transition");
    transition_=std::make_unique<RoomTransition>(pending_room_);
    pending_room_=nullptr;
    transition_->routine.replace(std::make_shared<Iterator>([this] { return transition_step(); }));
}

IteratorStep FirstRoomSession::transition_step() {
    auto& transition=*transition_;
    if(!transition.loaded) {
        if((player_->scene_tag()&(16|32))==0) throw std::runtime_error("Player must retain its persistent tag");
        for(const auto& entity:current_room_->entities) if((entity->tag()&(16|32))==0) transition.outgoing.push_back(entity.get());
        incoming_room_=std::make_unique<RoomRuntime>(*transition.destination,world_.collision,false,visual_owners(*transition.destination));
        for(const auto& event:incoming_room_->random_events) random_events_.push_back({"room-load",event.first,event.second,incoming_room_->definition.name});
        previous_bounds_=current_room_->definition.bounds;
        for(const auto& entity:current_room_->entities) if(std::holds_alternative<RoomWind>(entity->object)) entity->present=false;
        outgoing_room_=std::move(current_room_);
        current_room_=std::move(incoming_room_);
        stats_.room_deaths=0;
        stats_.scoped_room_random_calls+=current_room_->scoped_random.calls();
        ++stats_.loads;
        bind_room_world();
        publish_room_roster();
        transition.camera_from=camera_;
        const auto& bounds=current_room_->definition.bounds;
        transition.camera_to={float(bounds.x),float(bounds.y)};
        transition.player_to=player_->actor().body.position;
        if(transition.player_to.x<bounds.x || transition.player_to.x>=bounds.x+bounds.width)
            throw std::runtime_error("Transition target is outside the incoming horizontal bounds");
        while(transition.player_to.y>=float(bounds.y+bounds.height-4)) transition.player_to.y-=1;
        transition.loaded=true;
    } else if(!transition.camera_finished) {
        transition.camera_at=source_math::approach(transition.camera_at,1,context_.clock.delta/next_transition_duration_);
        const float ease=source_math::cube_out(transition.camera_at);
        camera_=transition.camera_at>0.9f ? transition.camera_to : Vec2{
            transition.camera_from.x+(transition.camera_to.x-transition.camera_from.x)*ease,
            transition.camera_from.y+(transition.camera_to.y-transition.camera_from.y)*ease};
        if(transition.camera_at>=1) transition.camera_finished=true;
    }
    const bool reached=player_->transition_to(transition.player_to,context_.clock.delta);
    presentation_->observe(PlayerCosmeticPhase::hair_color,projection(),context_.clock.delta);
    presentation_->simulate_hair_motion(false);
    if(!reached || transition.camera_at<1) return Yield{std::monostate{}};
    for(const auto& entity:outgoing_room_->entities) entity->present=false;
    bind_room_world();
    publish_room_roster();
    transition.outgoing.clear();
    outgoing_room_.reset();
    respawn_point_=current_room_->definition.spawn;
    player_->on_transition();
    chaser_history_.clear();
    next_transition_duration_=0.65f;
    transition.complete=true;
    return std::nullopt;
}

void FirstRoomSession::update_room_transition() {
    transition_->routine.update(context_.clock.delta,context_.clock.raw_delta);
    if(transition_->complete) transition_.reset();
}
}
