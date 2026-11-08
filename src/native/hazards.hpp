#pragma once

#include "movement.hpp"

namespace celeste {

enum class SpikeDirection { up, left };

class StaticSpike final {
public:
    StaticSpike(Vec2 position, int size, SpikeDirection direction, bool collidable = true);
    const Body& body() const { return body_; }
    SpikeDirection direction() const { return direction_; }

private:
    Body body_;
    SpikeDirection direction_;
};

enum class DeathEvent { corpse_created, corpse_added, player_removed };

struct PlayerDeath {
    bool dead = false;
    int depth = 0;
    Vec2 direction{};
    bool removed = false;
    std::vector<DeathEvent> events;
};

struct HazardFrame {
    bool refill_checked = false;
    bool refill_called = false;
    bool boost_checked = false;
    bool boost_blocked = false;
    std::vector<std::size_t> checked;
    std::vector<std::size_t> overlaps;
};

}
