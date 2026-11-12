#pragma once
#include "presentation.hpp"

namespace celeste {

struct DustParticle {
    Vec2 position, speed;
    int source;
    float size, life, rotation, spin;
};

enum class DustParticleType { dust };

struct VisualDustParticle : DustParticle {
    DustParticle birth{};
    float start_size=0, start_life=0;
    std::uint64_t generation=0;
    bool active=false;
};

class DustParticles final {
public:
    static constexpr unsigned capacity=400;
    void add(const DustParticle& birth,DustParticleType type);
    void update(float raw_delta);
    void clear();
    void clear_outside(float left,float top,float right,float bottom);
    const std::array<VisualDustParticle,capacity>& slots() const { return slots_; }
private:
    std::array<VisualDustParticle,capacity> slots_{};
    unsigned next_slot_=0;
};

}
