#include "player.hpp"

#include <algorithm>

namespace celeste {

bool Player::grab_check() const { return input_.grab && !input_.jump.disabled; }

bool Player::climb_check(int dir, int y_add) const {
    const auto pos = actor_.body.position;
    return climb_bounds_check(dir) && world_.collision.first_solid(actor_.body,
        {pos.x + static_cast<float>(dir * 2), pos.y + static_cast<float>(y_add)});
}

void Player::climb_begin() {
    auto& s = state_;
    auto& pos = actor_.body.position;
    s.auto_jump = false;
    s.speed.x = 0.0f;
    s.speed.y *= 0.2f;
    s.wall_slide_timer = 1.2f;
    s.climb_no_move_timer = 0.1f;
    s.wall_boost_timer = 0.0f;
    s.last_climb_move = 0;
    for (int i = 0; i < 2; ++i) {
        if (world_.collision.first_solid(actor_.body, {pos.x + static_cast<float>(s.facing), pos.y})) break;
        pos.x += 1.0f * static_cast<float>(s.facing);
    }
}

void Player::climb_end() { state_.wall_speed_retention_timer = 0.0f; }

bool Player::slip_check(float add_y) const {
    const auto pos = actor_.body.position;
    const auto box = *actor_.body.collider;
    const float x = state_.facing == 1 ? (box.offset.x + box.width) + pos.x : (box.offset.x + pos.x) - 1.0f;
    const Vec2 point{x, (box.offset.y + pos.y) + (4.0f + add_y)};
    if (!world_.collision.solid_at_point(point))
        return !world_.collision.solid_at_point({point.x, point.y + (-4.0f + add_y)});
    return false;
}

bool Player::climb_hop_blocked_check() const {
    const auto pos = actor_.body.position;
    if (overlaps_spike({pos.x + 1.0f * static_cast<float>(state_.facing) * 8.0f, pos.y})) return true;
    return world_.collision.first_solid(actor_.body, {pos.x, pos.y - 1.0f * 6.0f});
}

void Player::climb_hop() {
    auto& s = state_;
    const auto pos = actor_.body.position;
    s.climb_hop_solid = world_.collision.first_solid(actor_.body, {pos.x + 1.0f * static_cast<float>(s.facing), pos.y});
    if (s.climb_hop_solid) {
        s.climb_hop_solid_position = s.climb_hop_solid->position;
        s.hop_wait_x = s.facing;
        s.hop_wait_speed = static_cast<float>(s.facing) * 100.0f;
    } else {
        s.hop_wait_x = 0;
        s.speed.x = static_cast<float>(s.facing) * 100.0f;
    }
    s.low_friction_stop_timer = 0.15f;
    s.speed.y = std::min(s.speed.y, -120.0f);
    s.force_move_x = 0;
    s.force_move_x_timer = 0.2f;
}

int Player::climb_update() {
    auto& s = state_;
    const auto pos = actor_.body.position;
    s.climb_no_move_timer -= delta_;
    if (s.on_ground) s.stamina = 110.0f;
    if (jump_.pressed() && (!s.ducking || can_unduck(pos))) {
        if (s.move_x == -s.facing) wall_jump(-s.facing);
        else climb_jump();
        return 0;
    }
    if (can_dash()) {
        add_static_lift_boost();
        return start_dash();
    }
    if (!grab_check()) {
        add_static_lift_boost();
        return 0;
    }
    if (!world_.collision.first_solid(actor_.body, {pos.x + 1.0f * static_cast<float>(s.facing), pos.y})) {
        if (s.speed.y < 0.0f) climb_hop();
        return 0;
    }
    float target = 0.0f;
    bool slip = false;
    if (s.climb_no_move_timer <= 0.0f) {
        if (input_.y == -1) {
            target = -45.0f;
            if (world_.collision.first_solid(actor_.body, {pos.x, pos.y - 1.0f}) || (climb_hop_blocked_check() && slip_check(-1.0f))) {
                if (s.speed.y < 0.0f) s.speed.y = 0.0f;
                target = 0.0f;
                slip = true;
            } else if (slip_check()) {
                climb_hop();
                return 0;
            }
        } else if (input_.y == 1) {
            target = 80.0f;
            if (s.on_ground) {
                if (s.speed.y > 0.0f) s.speed.y = 0.0f;
                target = 0.0f;
            }
        } else slip = true;
    } else slip = true;
    s.last_climb_move = (target > 0.0f) - (target < 0.0f);
    if (slip && slip_check()) target = 30.0f;
    s.speed.y = approach(s.speed.y, target, 900.0f * delta_);
    if (input_.y != 1 && s.speed.y > 0.0f && !world_.collision.first_solid(actor_.body, {pos.x + static_cast<float>(s.facing), pos.y + 1.0f}))
        s.speed.y = 0.0f;
    if (s.climb_no_move_timer <= 0.0f) {
        if (s.last_climb_move == -1) s.stamina -= 45.454544f * delta_;
        else if (s.last_climb_move == 0) s.stamina -= 10.0f * delta_;
    }
    if (s.stamina <= 0.0f) {
        add_static_lift_boost();
        return 0;
    }
    return 1;
}

}
