#include "movement.hpp"

#include <cmath>
#include <limits>
#include <stdexcept>
#include <utility>

namespace celeste {

static_assert(sizeof(float) == 4 && std::numeric_limits<float>::is_iec559);

namespace {

Vec2 add(Vec2 a, Vec2 b) { return {a.x + b.x, a.y + b.y}; }
Vec2 scale(Vec2 value, float amount) { return {value.x * amount, value.y * amount}; }

void require_finite(Vec2 value) {
    if (!std::isfinite(value.x) || !std::isfinite(value.y)) {
        throw std::invalid_argument("Position, offsets and computed edges must be finite");
    }
}

struct Edges {
    float left;
    float right;
    float top;
    float bottom;
};

Edges edges(const Hitbox& hitbox, Vec2 position) {
    require_finite(position);
    require_finite(hitbox.offset);
    if (!std::isfinite(hitbox.width) || !std::isfinite(hitbox.height) || hitbox.width < 0.0f || hitbox.height < 0.0f) {
        throw std::invalid_argument("Hitbox dimensions must be finite and nonnegative");
    }
    const Edges result{hitbox.offset.x + position.x, (hitbox.offset.x + hitbox.width) + position.x,
                       hitbox.offset.y + position.y, (hitbox.offset.y + hitbox.height) + position.y};
    require_finite({result.left, result.right});
    require_finite({result.top, result.bottom});
    return result;
}

void validate_body(const Body& body) {
    require_finite(body.position);
    if (body.collider) edges(*body.collider, body.position);
}

void validate_at(const Body& body, Vec2 at) {
    validate_body(body);
    require_finite(at);
    if (body.collider) edges(*body.collider, at);
}

Body* first(const std::vector<Body*>& candidates, const Body& query, Vec2 at, bool outside) {
    validate_at(query, at);
    for (Body* candidate : candidates) {
        if (!candidate) throw std::invalid_argument("World lists cannot contain null body pointers");
        if ((!outside || !collide_check(query, *candidate, query.position)) && collide_check(query, *candidate, at)) {
            return candidate;
        }
    }
    return nullptr;
}

}

std::int32_t round_to_even(float value) {
    if (!std::isfinite(value)) throw std::invalid_argument("Movement must be finite");
    const double promoted = static_cast<double>(value);
    const double lower = std::floor(promoted);
    const double fraction = promoted - lower;
    const double rounded = fraction > 0.5 || (fraction == 0.5 && std::fmod(lower, 2.0) != 0.0)
        ? lower + 1.0 : lower;
    if (rounded < std::numeric_limits<std::int32_t>::min() || rounded > std::numeric_limits<std::int32_t>::max()) {
        throw std::invalid_argument("Rounded movement is outside int32 range");
    }
    return static_cast<std::int32_t>(rounded);
}

bool collide_check(const Body& query, const Body& target, Vec2 at) {
    validate_at(query, at);
    validate_body(target);
    if (!query.collider || !target.collider || &query == &target || !target.collidable) return false;
    const Edges a = edges(*query.collider, at);
    const Edges b = edges(*target.collider, target.position);
    return a.left < b.right && a.right > b.left && a.bottom > b.top && a.top < b.bottom;
}

Body* StaticWorld::first_solid(const Body& query, Vec2 at) const {
    return first(solids, query, at, false);
}

Body* StaticWorld::first_outside_jump_thru(const Body& query, Vec2 at) const {
    return first(jump_thrus, query, at, true);
}

Actor::Actor(const StaticWorld& world, Vec2 position, std::optional<Hitbox> collider)
    : body{position, collider, true}, world_(world) {
    validate_body(body);
}

Vec2 Actor::position_remainder() const { return remainder_; }

bool Actor::move_h(float amount, Collision callback, Body* pusher) {
    return move(amount, true, std::move(callback), pusher);
}

bool Actor::move_v(float amount, Collision callback, Body* pusher) {
    return move(amount, false, std::move(callback), pusher);
}

bool Actor::move_h_exact(std::int32_t amount, Collision callback, Body* pusher) {
    return move_exact(amount, true, std::move(callback), pusher);
}

bool Actor::move_v_exact(std::int32_t amount, Collision callback, Body* pusher) {
    return move_exact(amount, false, std::move(callback), pusher);
}

bool Actor::move(float amount, bool horizontal, Collision callback, Body* pusher) {
    validate_body(body);
    if (!std::isfinite(amount)) throw std::invalid_argument("Movement must be finite");
    float& counter = horizontal ? remainder_.x : remainder_.y;
    const float accumulated = counter + amount;
    const std::int32_t pixels = round_to_even(accumulated);
    counter = accumulated;
    if (pixels == 0) return false;
    counter -= static_cast<float>(pixels);
    return move_exact(pixels, horizontal, std::move(callback), pusher);
}

bool Actor::move_exact(std::int32_t amount, bool horizontal, Collision callback, Body* pusher) {
    validate_body(body);
    const Vec2 unit = horizontal ? Vec2{1.0f, 0.0f} : Vec2{0.0f, 1.0f};
    const Vec2 target = add(body.position, scale(unit, static_cast<float>(amount)));
    validate_at(body, target);
    const int sign = (amount > 0) - (amount < 0);
    const Vec2 direction = scale(unit, static_cast<float>(sign));
    std::int32_t moved = 0;
    while (amount != 0) {
        const Vec2 at = add(body.position, direction);
        Body* hit = world_.first_solid(body, at);
        if (!hit && !horizontal && amount > 0 && !ignore_jump_thrus) {
            hit = world_.first_outside_jump_thru(body, at);
        }
        if (hit) {
            (horizontal ? remainder_.x : remainder_.y) = 0.0f;
            if (callback) callback({direction, scale(unit, static_cast<float>(moved)), target, hit, pusher});
            return true;
        }
        moved += sign;
        amount -= sign;
        (horizontal ? body.position.x : body.position.y) += static_cast<float>(sign);
    }
    return false;
}

}
