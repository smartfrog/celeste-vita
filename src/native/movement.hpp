#pragma once

#include <cstdint>
#include <functional>
#include <optional>
#include <vector>

namespace celeste {

struct Vec2 {
    float x = 0.0f;
    float y = 0.0f;
};

struct Hitbox {
    float width = 0.0f;
    float height = 0.0f;
    Vec2 offset{};
};

struct Body {
    Vec2 position{};
    std::optional<Hitbox> collider;
    bool collidable = true;
};

std::int32_t round_to_even(float value);
bool collide_check(const Body& query, const Body& target, Vec2 at);

struct StaticWorld {
    std::vector<Body*> solids;
    std::vector<Body*> jump_thrus;

    Body* first_solid(const Body& query, Vec2 at) const;
    Body* first_outside_jump_thru(const Body& query, Vec2 at) const;
};

struct CollisionData {
    Vec2 direction{};
    Vec2 moved{};
    Vec2 target_position{};
    Body* hit = nullptr;
    Body* pusher = nullptr;
};

using Collision = std::function<void(CollisionData)>;

class Actor final {
public:
    explicit Actor(const StaticWorld& world, Vec2 position = {}, std::optional<Hitbox> collider = std::nullopt);

    Body body;
    bool ignore_jump_thrus = false;

    Vec2 position_remainder() const;
    bool move_h(float amount, Collision on_collide = {}, Body* pusher = nullptr);
    bool move_v(float amount, Collision on_collide = {}, Body* pusher = nullptr);
    bool move_h_exact(std::int32_t amount, Collision on_collide = {}, Body* pusher = nullptr);
    bool move_v_exact(std::int32_t amount, Collision on_collide = {}, Body* pusher = nullptr);

private:
    const StaticWorld& world_;
    Vec2 remainder_{};
    bool move(float amount, bool horizontal, Collision on_collide, Body* pusher);
    bool move_exact(std::int32_t amount, bool horizontal, Collision on_collide, Body* pusher);
};

}
