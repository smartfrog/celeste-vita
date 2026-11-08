#include "hazards.hpp"

#include <cmath>
#include <stdexcept>

namespace celeste {

StaticSpike::StaticSpike(Vec2 position, int size, SpikeDirection direction, bool collidable)
    : direction_(direction) {
    if (!std::isfinite(position.x) || !std::isfinite(position.y) || size <= 0 ||
        (direction != SpikeDirection::up && direction != SpikeDirection::left))
        throw std::invalid_argument("Invalid static Up/Left spike");
    body_ = {position, direction == SpikeDirection::up
        ? Hitbox{static_cast<float>(size), 3.0f, {0.0f, -3.0f}}
        : Hitbox{3.0f, static_cast<float>(size), {-3.0f, 0.0f}}, collidable};
}

}
