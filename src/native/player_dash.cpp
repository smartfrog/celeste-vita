#include "player.hpp"

#include <cmath>
#include <stdexcept>

namespace celeste {

bool Player::dash_attacking() const { return state_.dash_attack_timer > 0.0f; }

bool Player::on_ground(Vec2 at) const {
    Body probe = actor_.body;
    probe.position = at;
    return world_.collision.first_solid(probe, {at.x, at.y + 1.0f}) ||
        (!actor_.ignore_jump_thrus && world_.collision.first_outside_jump_thru(probe, {at.x, at.y + 1.0f}));
}

bool Player::dash_correct_check(Vec2 add) const {
    Body probe{{}, hurtbox(), true};
    const auto pos = actor_.body.position;
    for (const auto* spike : world_.spikes)
        if (collide_check(probe, spike->body(), {pos.x + add.x, pos.y + add.y})) return true;
    return false;
}

bool Player::wall_jump_check(int dir) const {
    bool extended = dash_attacking() && state_.dash_dir.x == 0.0f && state_.dash_dir.y == -1.0f;
    if (extended && dir > 0) {
        const auto pos = actor_.body.position;
        for (const auto* spike : world_.spikes)
            if (spike->direction() == SpikeDirection::left && collide_check(actor_.body, spike->body(), {pos.x + static_cast<float>(dir) * 5.0f, pos.y})) {
                extended = false;
                break;
            }
    }
    const auto pos = actor_.body.position;
    return climb_bounds_check(dir) && world_.collision.first_solid(actor_.body,
        {pos.x + 1.0f * static_cast<float>(dir) * static_cast<float>(extended ? 5 : 3), pos.y});
}

void Player::call_dash_events() {
    if (state_.called_dash_events) return;
    state_.called_dash_events = true;
    ++state_.dash_events;
}

void Player::dash_begin() {
    auto& s = state_;
    s.called_dash_events = false;
    s.dash_started_on_ground = s.on_ground;
    s.launched = false;
    s.can_curve_dash = true;
    clock_.freeze(0.05f);
    s.dash_cooldown_timer = 0.2f;
    s.dash_refill_cooldown_timer = 0.1f;
    s.started_dashing = true;
    s.wall_slide_timer = 1.2f;
    s.dash_trail_timer = 0.0f;
    s.dash_trail_counter = 0;
    s.dash_attack_timer = 0.3f;
    s.glider_boost_timer = 0.55f;
    s.before_dash_speed = s.speed;
    s.speed = {};
    s.dash_dir = {};
    if (!s.on_ground && s.ducking && can_unduck(actor_.body.position)) set_ducking(false);
    else if (!s.ducking && input_.y == 1) set_ducking(true);
}

void Player::dash_end() { call_dash_events(); }

int Player::dash_update() {
    auto& s = state_;
    s.started_dashing = false;
    if (s.dash_trail_timer > 0.0f) {
        s.dash_trail_timer -= delta_;
        if (s.dash_trail_timer <= 0.0f) {
            --s.dash_trail_counter;
            if (s.dash_trail_counter > 0) s.dash_trail_timer = 0.1f;
        }
    }
    if (std::abs(s.dash_dir.y) < 0.1f) {
        for (const auto* platform : world_.collision.jump_thrus) {
            const auto pos = actor_.body.position;
            if (!collide_check(actor_.body, *platform, pos)) continue;
            const auto& box = *actor_.body.collider;
            const float bottom = pos.y + (box.offset.y + box.height);
            const float top = platform->position.y + (platform->grid ? platform->grid->offset().y : platform->collider->offset.y);
            if (bottom - top <= 6.0f && !dash_correct_check({0.0f, top - bottom}))
                actor_.move_v_exact(static_cast<std::int32_t>(top - bottom));
        }
        if (can_unduck(actor_.body.position) && jump_.pressed() && s.jump_grace_timer > 0.0f) {
            super_jump();
            return 0;
        }
    }
    if (jump_.pressed() && can_unduck(actor_.body.position)) {
        for (int dir : {1, -1}) {
            if (!wall_jump_check(dir)) continue;
            if (super_wall_jump_angle_check()) super_wall_jump(-dir);
            else wall_jump(-dir);
            return 0;
        }
    }
    return 2;
}

IteratorPtr Player::dash_coroutine() {
    return std::make_shared<Iterator>([this, stage = 0]() mutable -> IteratorStep {
        auto& s = state_;
        if (stage++ == 0) return Yield{std::monostate{}};
        if (stage == 2) {
            s.speed = {s.last_aim.x * 240.0f, s.last_aim.y * 240.0f};
            if (std::signbit(s.before_dash_speed.x) == std::signbit(s.speed.x) &&
                s.before_dash_speed.x != 0.0f && s.speed.x != 0.0f && std::abs(s.before_dash_speed.x) > std::abs(s.speed.x))
                s.speed.x = s.before_dash_speed.x;
            s.glider_boost_dir = s.dash_dir = s.last_aim;
            if (s.dash_dir.x != 0.0f) s.facing = s.dash_dir.x > 0.0f ? 1 : -1;
            call_dash_events();
            if (s.on_ground && s.dash_dir.x != 0.0f && s.dash_dir.y > 0.0f && s.speed.y > 0.0f) {
                s.dash_dir.x = s.dash_dir.x > 0.0f ? 1.0f : -1.0f;
                s.dash_dir.y = 0.0f;
                s.speed.y = 0.0f;
                s.speed.x *= 1.2f;
                set_ducking(true);
            }
            s.dash_trail_timer = 0.08f;
            s.dash_trail_counter = 1;
            return Yield{0.15f};
        }
        s.auto_jump = true;
        s.auto_jump_timer = 0.0f;
        if (s.dash_dir.y <= 0.0f) s.speed = {s.dash_dir.x * 160.0f, s.dash_dir.y * 160.0f};
        if (s.speed.y < 0.0f) s.speed.y *= 0.75f;
        machine_.set_state(0);
        return std::nullopt;
    });
}

}
