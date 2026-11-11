#include "trails.hpp"
#include "source_math.hpp"
#include <algorithm>
#include <cmath>
#include <stdexcept>

namespace celeste {

int PlayerTrails::add(const PlayerProjection& player,const PlayerPose& pose) {
    if(!std::isfinite(player.position.x) || !std::isfinite(player.position.y) ||
       !std::isfinite(pose.scale.x) || !std::isfinite(pose.scale.y) || (player.facing!=1 && player.facing!=-1))
        throw std::invalid_argument("Invalid trail creation pose");
    manager_created_=true;
    for(unsigned i=0;i<capacity;++i) if(!slots_[i].occupied) {
        auto& slot=slots_[i];
        slot={};
        slot.position=player.position;
        slot.scale={std::abs(pose.scale.x)*float(player.facing),pose.scale.y};
        slot.order=next_order_++;
        slot.occupied=true;
        return int(i);
    }
    return -1;
}

void PlayerTrails::update(float dt) {
    if(!std::isfinite(dt) || dt<0) throw std::invalid_argument("Invalid trail delta");
    if(manager_created_) manager_committed_=true;
    for(auto& slot:slots_) {
        if(slot.removing) slot={};
        if(!slot.occupied) continue;
        slot.committed=true;
        if(slot.percent>=1.f) slot.removing=true;
        slot.percent+=dt;
    }
}

void PlayerTrails::before_render(PlayerPresentation& presentation,const PlayerProjection& player,const Capture& capture) {
    if(!capture) throw std::invalid_argument("Trail capture backend is required");
    if(!manager_committed_) return;
    for(unsigned i=0;i<capacity;++i) {
        auto& slot=slots_[i];
        if(!slot.occupied || slot.drawn) continue;
        const Vec2 offset{float(i%8*64+32)-slot.position.x,float(i/8*64+32)-slot.position.y};
        capture(i,presentation.trail_capture(player,offset,slot.scale));
        slot.drawn=true;
    }
}

std::vector<unsigned> PlayerTrails::render_order() const {
    std::vector<unsigned> result;
    for(unsigned i=0;i<capacity;++i) if(slots_[i].occupied && slots_[i].committed) result.push_back(i);
    std::sort(result.begin(),result.end(),[this](unsigned a,unsigned b){return slots_[a].order<slots_[b].order;});
    return result;
}

unsigned PlayerTrails::count() const {
    return unsigned(std::count_if(slots_.begin(),slots_.end(),[](const TrailSnapshot& s){return s.occupied;}));
}

PresentationColor PlayerTrails::faded_color(const TrailSnapshot& slot) {
    const float amount=0.75f*(1.f-source_math::cube_out(slot.percent));
    const auto byte=[amount](std::uint8_t value) { return std::uint8_t(std::clamp(float(value)*amount,0.f,255.f)); };
    return {byte(slot.color.r),byte(slot.color.g),byte(slot.color.b),byte(slot.color.a)};
}

void PlayerTrails::clear() {
    slots_={};
    ++generation_;
}

}
