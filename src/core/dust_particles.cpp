#include "dust_particles.hpp"
#include "source_math.hpp"
#include <cmath>
#include <limits>
#include <stdexcept>

namespace celeste {
void DustParticles::add(const DustParticle& birth,DustParticleType type) {
    if(type!=DustParticleType::dust || birth.source<0 || birth.source>=4 ||
       !std::isfinite(birth.position.x) || !std::isfinite(birth.position.y) ||
       !std::isfinite(birth.speed.x) || !std::isfinite(birth.speed.y) ||
       !std::isfinite(birth.size) || birth.size<=0 || !std::isfinite(birth.life) || birth.life<=0 ||
       !std::isfinite(birth.rotation) || birth.spin!=0)
        throw std::invalid_argument("Unsupported Dust birth/type");
    auto& particle=slots_[next_slot_];
    if(particle.generation==std::numeric_limits<std::uint64_t>::max())
        throw std::overflow_error("Dust slot generation overflow");
    static_cast<DustParticle&>(particle)=birth;
    particle.birth=birth;
    particle.start_size=birth.size;particle.start_life=birth.life;
    ++particle.generation;particle.active=true;
    next_slot_=(next_slot_+1)%capacity;
}

void DustParticles::update(float raw_delta) {
    if(!std::isfinite(raw_delta) || raw_delta<0) throw std::invalid_argument("Invalid Dust delta");
    for(auto& particle:slots_) if(particle.active) {
        const float remaining=particle.life/particle.start_life;
        particle.life-=raw_delta;
        if(particle.life<=0) { particle.active=false;continue; }
        particle.rotation+=particle.spin*raw_delta;
        particle.position.x+=particle.speed.x*raw_delta;
        particle.position.y+=particle.speed.y*raw_delta;
        // Source Vector2 addition changes negative zero even with zero X acceleration.
        particle.speed.x+=0.f*raw_delta;
        particle.speed.y+=4.f*raw_delta;
        particle.size=particle.start_size*source_math::cube_out(remaining);
    }
}

void DustParticles::clear() { for(auto& particle:slots_) particle.active=false; }

void DustParticles::clear_outside(float left,float top,float right,float bottom) {
    if(!std::isfinite(left) || !std::isfinite(top) || !std::isfinite(right) || !std::isfinite(bottom) || left>=right || top>=bottom)
        throw std::invalid_argument("Invalid Dust clear rectangle");
    for(auto& particle:slots_) {
        const auto position=particle.position;
        if(!(position.x>left && position.y>top && position.x<right && position.y<bottom)) particle.active=false;
    }
}
}
