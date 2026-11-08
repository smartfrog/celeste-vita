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

class TileGrid final {
public:
    TileGrid(std::int32_t columns, std::int32_t rows, std::vector<std::uint8_t> cells,
             float cell_width = 8.0f, float cell_height = 8.0f, Vec2 offset = {});
    std::int32_t columns() const { return columns_; }
    std::int32_t rows() const { return rows_; }
    float cell_width() const { return cell_width_; }
    float cell_height() const { return cell_height_; }
    float width() const { return cell_width_ * static_cast<float>(columns_); }
    float height() const { return cell_height_ * static_cast<float>(rows_); }
    Vec2 offset() const { return offset_; }
    bool at(std::int32_t x, std::int32_t y) const;

private:
    const std::int32_t columns_, rows_;
    const std::vector<std::uint8_t> cells_;
    const float cell_width_, cell_height_;
    const Vec2 offset_;
};

struct Body {
    Vec2 position{};
    std::optional<Hitbox> collider;
    bool collidable = true;
    const TileGrid* grid = nullptr;
};

std::int32_t round_to_even(float value);
bool collide_check(const Body& query, const Body& target, Vec2 at);

struct StaticWorld {
    std::vector<Body*> solids;
    std::vector<Body*> jump_thrus;

    Body* first_solid(const Body& query, Vec2 at) const;
    bool solid_at_point(Vec2 point) const;
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
