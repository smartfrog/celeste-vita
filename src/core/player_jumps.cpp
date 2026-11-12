#include "player.hpp"
#include "presentation.hpp"
#include "source_math.hpp"

#include <cmath>

namespace celeste {

namespace {
constexpr float pi = 3.14159265358979323846f;
}
using source_math::angle_to_vector;

bool Player::super_wall_jump_angle_check() const {
    return std::abs(state_.dash_dir.x) <= 0.2f && state_.dash_dir.y <= -0.75f;
}

void Player::begin_jump(JumpKind kind, float var_time) {
    jump_kind_ = kind;
    ++jump_count_;
    jump_.consume_buffer();
    state_.jump_grace_timer = 0.0f;
    state_.var_jump_timer = var_time;
    state_.auto_jump = false;
    state_.dash_attack_timer = 0.0f;
    state_.glider_boost_timer = 0.0f;
    state_.wall_slide_timer = 1.2f;
    state_.wall_boost_timer = 0.0f;
    cosmetic(PlayerCosmeticPhase::jump);
}

void Player::jump() {
    begin_jump(JumpKind::jump, 0.2f);
    state_.speed.x += 40.0f * static_cast<float>(state_.move_x);
    state_.speed.y = -105.0f;
    add_static_lift_boost();
    state_.var_jump_speed = state_.speed.y;
    state_.launched = false;
}

void Player::climb_jump() {
    if (!state_.on_ground) {
        state_.stamina -= 27.5f;
        cosmetic(PlayerCosmeticPhase::sweat_jump);
    }
    jump();
    jump_kind_ = JumpKind::climb_jump;
    if (state_.move_x == 0) {
        state_.wall_boost_dir = -state_.facing;
        state_.wall_boost_timer = 0.2f;
    }
}

void Player::add_static_lift_boost() {
    // Zero LiftBoost addition must retain its signed-zero behavior.
    state_.speed.x += 0.0f;
    state_.speed.y += 0.0f;
}

void Player::super_jump() {
    begin_jump(JumpKind::super_jump, 0.2f);
    state_.speed = {260.0f * static_cast<float>(state_.facing), -105.0f};
    add_static_lift_boost();
    state_.glider_boost_timer = 0.55f;
    if (state_.ducking) {
        set_ducking(false);
        state_.speed.x *= 1.25f;
        state_.speed.y *= 0.5f;
        state_.glider_boost_dir = angle_to_vector(pi * -3.0f / 16.0f, 1.0f);
    } else state_.glider_boost_dir = angle_to_vector(-pi / 4.0f, 1.0f);
    state_.var_jump_speed = state_.speed.y;
    state_.launched = true;
}

void Player::wall_jump(int dir) {
    set_ducking(false);
    begin_jump(JumpKind::wall_jump, 0.2f);
    state_.low_friction_stop_timer = 0.15f;
    if (state_.move_x != 0) {
        state_.force_move_x = dir;
        state_.force_move_x_timer = 0.16f;
    }
    state_.speed = {130.0f * static_cast<float>(dir), -105.0f};
    add_static_lift_boost();
    state_.var_jump_speed = state_.speed.y;
    state_.launched = false;
}

void Player::super_wall_jump(int dir) {
    set_ducking(false);
    begin_jump(JumpKind::super_wall_jump, 0.25f);
    state_.glider_boost_timer = 0.55f;
    state_.glider_boost_dir = {-0.0f, -1.0f};
    state_.speed = {170.0f * static_cast<float>(dir), -160.0f};
    add_static_lift_boost();
    state_.var_jump_speed = state_.speed.y;
    state_.launched = true;
}

}
