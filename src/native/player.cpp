#include "player.hpp"

#include <algorithm>
#include <cmath>
#include <stdexcept>
#include <utility>

namespace celeste {

namespace {

constexpr Hitbox standing{8.0f, 11.0f, {-4.0f, -11.0f}};
constexpr Hitbox ducked{8.0f, 6.0f, {-4.0f, -6.0f}};

void finite(Vec2 value) {
    if (!std::isfinite(value.x) || !std::isfinite(value.y)) throw std::invalid_argument("Player values must be finite");
}

Vec2 truncated_spawn(Vec2 spawn) {
    finite(spawn);
    if (spawn.x < -2147483648.0f || spawn.x >= 2147483648.0f || spawn.y < -2147483648.0f || spawn.y >= 2147483648.0f)
        throw std::invalid_argument("Player spawn must fit int32");
    return {static_cast<float>(static_cast<std::int32_t>(spawn.x)), static_cast<float>(static_cast<std::int32_t>(spawn.y))};
}

float approach(float value, float target, float max_move) {
    return value > target ? std::max(value - max_move, target) : std::min(value + max_move, target);
}

int sign(float value) { return (value > 0.0f) - (value < 0.0f); }

}

Player::Player(const PlayerWorld& world, Vec2 spawn, Vec2 initial_speed, PlayerProfile profile)
    : world_(world), actor_(world.collision, truncated_spawn(spawn), standing) {
    if (profile != PlayerProfile::default_static) throw std::invalid_argument("Unsupported Player profile");
    finite(initial_speed);
    validate_world();
    state_.speed = initial_speed;
    state_.previous_position = actor_.body.position;
    machine_.set_callbacks(0, {[this] { return normal_update(); }, {},
                               [this] { normal_begin(); }, [this] { normal_end(); }});
    machine_.added(true);
}

void Player::validate_world() const {
    if (world_.bounds_left >= world_.bounds_right)
        throw std::invalid_argument("Invalid fixture bounds");
    for (const auto* list : {&world_.collision.solids, &world_.collision.jump_thrus}) {
        for (const Body* body : *list) {
            if (!body) throw std::invalid_argument("Null Player platform");
            collide_check(actor_.body, *body, actor_.body.position);
        }
    }
    for (const Body* safe : world_.safe_ground) {
        if (!safe || (std::find(world_.collision.solids.begin(), world_.collision.solids.end(), safe) == world_.collision.solids.end() &&
                      std::find(world_.collision.jump_thrus.begin(), world_.collision.jump_thrus.end(), safe) == world_.collision.jump_thrus.end()))
            throw std::invalid_argument("Safe ground must belong to the static world");
    }
}

Hitbox Player::hurtbox() const {
    return state_.ducking ? Hitbox{8.0f, 4.0f, {-4.0f, -6.0f}} : Hitbox{8.0f, 9.0f, {-4.0f, -11.0f}};
}

void Player::request_state(int state) {
    if (state != 0) throw std::invalid_argument("Only Normal state is supported");
    machine_.set_state(state);
}

void Player::emit(const char* phase, const CollisionData* collision) const {
    if (observer_) observer_(phase, collision);
}

void Player::set_ducking(bool value) {
    state_.ducking = value;
    actor_.body.collider = value ? ducked : standing;
}

bool Player::can_unduck(Vec2 at) const {
    if (!state_.ducking) return true;
    Body probe{at, standing, true};
    return world_.collision.first_solid(probe, at) == nullptr;
}

bool Player::climb_bounds_check(int dir) const {
    const auto& body = actor_.body;
    const auto& box = *body.collider;
    return box.offset.x + body.position.x + static_cast<float>(dir * 2) >= world_.bounds_left &&
           (box.offset.x + box.width) + body.position.x + static_cast<float>(dir * 2) < world_.bounds_right;
}

void Player::normal_begin() { state_.max_fall = 160.0f; }
void Player::normal_end() { state_.wall_speed_retention_timer = 0.0f; }

void Player::jump() {
    jump_.consume_buffer();
    state_.jump_grace_timer = 0.0f;
    state_.var_jump_timer = 0.2f;
    state_.wall_slide_timer = 1.2f;
    state_.speed.x += 40.0f * static_cast<float>(state_.move_x);
    state_.speed.y = -105.0f;
    // Preserve zero LiftBoost addition (including signed-zero behavior) and its launched reset.
    state_.speed.x += 0.0f;
    state_.speed.y += 0.0f;
    state_.var_jump_speed = state_.speed.y;
    state_.launched = false;
}

int Player::normal_update() {
    auto& s = state_;
    auto& pos = actor_.body.position;
    if (s.ducking) {
        if (s.on_ground && input_.y != 1) {
            if (can_unduck(pos)) set_ducking(false);
            else if (s.speed.x == 0.0f) {
                for (int offset = 4; offset > 0; --offset) {
                    if (can_unduck({pos.x + static_cast<float>(offset), pos.y})) {
                        actor_.move_h(50.0f * delta_);
                        break;
                    }
                    if (can_unduck({pos.x - static_cast<float>(offset), pos.y})) {
                        actor_.move_h(-50.0f * delta_);
                        break;
                    }
                }
            }
        }
    } else if (s.on_ground && input_.y == 1 && s.speed.y >= 0.0f) set_ducking(true);

    if (s.ducking && s.on_ground) s.speed.x = approach(s.speed.x, 0.0f, 500.0f * delta_);
    else {
        const float multiplier = s.on_ground ? 1.0f : 0.65f;
        const float acceleration = std::abs(s.speed.x) > 90.0f && sign(s.speed.x) == s.move_x ? 400.0f : 1000.0f;
        s.speed.x = approach(s.speed.x, 90.0f * static_cast<float>(s.move_x), acceleration * multiplier * delta_);
    }
    if (input_.y == 1 && s.speed.y >= 160.0f) s.max_fall = approach(s.max_fall, 240.0f, 300.0f * delta_);
    else s.max_fall = approach(s.max_fall, 160.0f, 300.0f * delta_);
    if (!s.on_ground) {
        float target = s.max_fall;
        if (s.move_x == s.facing && input_.y != 1) {
            if (s.speed.y >= 0.0f && s.wall_slide_timer > 0.0f && climb_bounds_check(s.facing) &&
                world_.collision.first_solid(actor_.body, {pos.x + static_cast<float>(s.facing), pos.y}) && can_unduck(pos)) {
                set_ducking(false);
                s.wall_slide_dir = s.facing;
            }
            if (s.wall_slide_dir != 0) target = 160.0f + (20.0f - 160.0f) * (s.wall_slide_timer / 1.2f);
        }
        const float multiplier = std::abs(s.speed.y) < 40.0f && jump_.check() ? 0.5f : 1.0f;
        s.speed.y = approach(s.speed.y, target, 900.0f * multiplier * delta_);
    }
    if (s.var_jump_timer > 0.0f) {
        if (jump_.check()) s.speed.y = std::min(s.speed.y, s.var_jump_speed);
        else s.var_jump_timer = 0.0f;
    }
    if (jump_.pressed()) {
        if (s.jump_grace_timer > 0.0f) jump();
        else if (can_unduck(pos)) {
            for (int dir : {1, -1}) {
                if (climb_bounds_check(dir) && world_.collision.first_solid(actor_.body, {pos.x + 1.0f * static_cast<float>(dir) * 3.0f, pos.y}))
                    throw std::invalid_argument("Eligible WallJump is outside the Normal ground/coyote profile");
            }
        }
    }
    return 0;
}

void Player::collide_h(CollisionData data) {
    emit("collision_h", &data);
    if (state_.wall_speed_retention_timer <= 0.0f) {
        state_.wall_speed_retained = state_.speed.x;
        state_.wall_speed_retention_timer = 0.06f;
    }
    state_.speed.x = 0.0f;
    emit("collided_h", &data);
}

void Player::collide_v(CollisionData data) {
    emit("collision_v", &data);
    auto& s = state_;
    auto& pos = actor_.body.position;
    if (s.speed.y < 0.0f) {
        if (s.speed.x <= 0.01f) {
            for (int offset = 1; offset <= 4; ++offset) {
                const Vec2 candidate{pos.x - static_cast<float>(offset), pos.y - 1.0f};
                if (!world_.collision.first_solid(actor_.body, candidate)) {
                    pos = candidate;
                    emit("collided_v", &data);
                    return;
                }
            }
        }
        if (s.speed.x >= -0.01f) {
            for (int offset = 1; offset <= 4; ++offset) {
                const Vec2 candidate{pos.x + static_cast<float>(offset), pos.y - 1.0f};
                if (!world_.collision.first_solid(actor_.body, candidate)) {
                    pos = candidate;
                    emit("collided_v", &data);
                    return;
                }
            }
        }
        if (s.var_jump_timer < 0.15f) s.var_jump_timer = 0.0f;
    }
    s.speed.y = 0.0f;
    emit("collided_v", &data);
}

void Player::frame(float delta_time, PlayerInput input, PlayerObserver observer) {
    if (updating_) throw std::logic_error("Recursive Player frame is unsupported");
    if (!std::isfinite(delta_time) || delta_time < 0.0f || !std::isfinite(1000.0f * delta_time) ||
        input.x < -1 || input.x > 1 || input.y < -1 || input.y > 1)
        throw std::invalid_argument("Invalid Player frame input");
    if (input.grab || input.dash || input.jump.debug_override_pressed)
        throw std::invalid_argument("Grab, Dash and debug override are outside the supported profile");
    validate_world();
    finite(state_.speed);
    finite(actor_.body.position);
    updating_ = true;
    observer_ = std::move(observer);
    try {
        delta_ = delta_time;
        input_ = input;
        auto& s = state_;
        auto& pos = actor_.body.position;
        jump_.sample = input.jump;
        jump_.update(delta_);
        emit("input");
        s.previous_position = pos;
        Body* ground = nullptr;
        if (s.speed.y >= 0.0f) {
            ground = world_.collision.first_solid(actor_.body, {pos.x, pos.y + 1.0f});
            if (!ground) ground = world_.collision.first_outside_jump_thru(actor_.body, {pos.x, pos.y + 1.0f});
        }
        s.on_ground = ground != nullptr;
        s.on_safe_ground = ground && std::find(world_.safe_ground.begin(), world_.safe_ground.end(), ground) != world_.safe_ground.end();
        emit("ground");
        if (s.wall_slide_dir != 0) {
            s.wall_slide_timer = std::max(s.wall_slide_timer - delta_, 0.0f);
            s.wall_slide_dir = 0;
        }
        if (s.on_ground) {
            s.stamina = 110.0f;
            s.wall_slide_timer = 1.2f;
            s.jump_grace_timer = 0.1f;
            if (s.dashes < 1) s.dashes = 1;
        } else if (s.jump_grace_timer > 0.0f) s.jump_grace_timer -= delta_;
        if (s.var_jump_timer > 0.0f) s.var_jump_timer -= delta_;
        s.move_x = input.x;
        if (s.move_x != 0) s.facing = s.move_x;
        if (s.wall_speed_retention_timer > 0.0f) {
            if (sign(s.speed.x) == -sign(s.wall_speed_retained)) s.wall_speed_retention_timer = 0.0f;
            else if (!world_.collision.first_solid(actor_.body, {pos.x + static_cast<float>(sign(s.wall_speed_retained)), pos.y})) {
                s.speed.x = s.wall_speed_retained;
                s.wall_speed_retention_timer = 0.0f;
            } else s.wall_speed_retention_timer -= delta_;
        }
        emit("preamble");
        machine_.update(delta_, delta_);
        emit("normal");
        if (!s.on_ground && s.speed.y <= 0.0f) {
            for (const Body* platform : world_.collision.jump_thrus) {
                if (collide_check(actor_.body, *platform, pos)) {
                    actor_.move_v(-40.0f * delta_);
                    break;
                }
            }
        }
        emit("boost");
        if (s.speed.y > 0.0f && can_unduck(pos) && !s.on_ground && s.jump_grace_timer <= 0.0f) set_ducking(false);
        emit("unduck");
        actor_.move_h(s.speed.x * delta_, [this](CollisionData data) { collide_h(data); });
        emit("horizontal");
        actor_.move_v(s.speed.y * delta_, [this](CollisionData data) { collide_v(data); });
        emit("vertical");
        emit("hazards");
        s.was_on_ground = s.on_ground;
        emit("complete");
    } catch (...) {
        observer_ = {};
        updating_ = false;
        throw;
    }
    observer_ = {};
    updating_ = false;
}

}
