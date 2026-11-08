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

int sign(float value) { return (value > 0.0f) - (value < 0.0f); }

}

float Player::approach(float value, float target, float max_move) {
    return value > target ? std::max(value - max_move, target) : std::min(value + max_move, target);
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
    machine_.set_callbacks(1, {[this] { return climb_update(); }, {},
                               [this] { climb_begin(); }, [this] { climb_end(); }});
    machine_.set_callbacks(2, {[this] { const int state = dash_update(); emit("dash_update"); return state; }, [this] { return dash_coroutine(); },
                               [this] { dash_begin(); }, [this] { dash_end(); }});
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
    for (std::size_t i = 0; i < world_.spikes.size(); ++i) {
        const auto* spike = world_.spikes[i];
        if (!spike || std::find(world_.spikes.begin(), world_.spikes.begin() + i, spike) != world_.spikes.begin() + i)
            throw std::invalid_argument("Null or duplicate static spike");
        collide_check(actor_.body, spike->body(), actor_.body.position);
    }
}

Hitbox Player::hurtbox() const {
    return state_.ducking ? Hitbox{8.0f, 4.0f, {-4.0f, -6.0f}} : Hitbox{8.0f, 9.0f, {-4.0f, -11.0f}};
}

void Player::request_state(int state) {
    if (state != 0) throw std::invalid_argument("Only Normal state is supported");
    machine_.set_state(state);
}

bool Player::die(Vec2 direction) {
    if (updating_) throw std::logic_error("Death cannot be requested from a read-only observer");
    finite(direction);
    return die_immediate(direction);
}

bool Player::die_immediate(Vec2 direction) {
    if (death_.dead) return false;
    death_.dead = true;
    death_.depth = -1000000;
    state_.speed = {};
    machine_.locked = true;
    actor_.body.collidable = false;
    death_.direction = direction;
    death_.events.push_back(DeathEvent::corpse_created);
    death_.events.push_back(DeathEvent::corpse_added);
    death_.removed = true;
    death_.events.push_back(DeathEvent::player_removed);
    return true;
}

bool Player::overlaps_spike(Vec2 at) const {
    for (const auto* spike : world_.spikes)
        if (collide_check(actor_.body, spike->body(), at)) return true;
    return false;
}

bool Player::jump_thru_boost_blocked_check() const {
    const auto pos = actor_.body.position;
    return overlaps_spike({pos.x, pos.y - 2.0f});
}

bool Player::check_hazards() {
    const auto saved = actor_.body.collider;
    actor_.body.collider = hurtbox();
    for (std::size_t i = 0; i < world_.spikes.size(); ++i) {
        hazard_frame_.checked.push_back(i);
        const auto& spike = *world_.spikes[i];
        if (!collide_check(actor_.body, spike.body(), actor_.body.position)) continue;
        hazard_frame_.overlaps.push_back(i);
        const auto& box = *actor_.body.collider;
        const auto& target = *spike.body().collider;
        const bool lethal = spike.direction() == SpikeDirection::up
            ? state_.speed.y >= 0.0f && actor_.body.position.y + (box.offset.y + box.height) <=
                spike.body().position.y + (target.offset.y + target.height)
            : state_.speed.x >= 0.0f;
        if (lethal) die_immediate(spike.direction() == SpikeDirection::up ? Vec2{0.0f, -1.0f} : Vec2{-1.0f, 0.0f});
        if (death_.dead) {
            actor_.body.collider = saved;
            return true;
        }
    }
    actor_.body.collider = saved;
    return false;
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
void Player::normal_end() {
    state_.wall_boost_timer = 0.0f;
    state_.wall_speed_retention_timer = 0.0f;
    state_.hop_wait_x = 0;
}

int Player::normal_update() {
    auto& s = state_;
    auto& pos = actor_.body.position;
    if (grab_check() && !tired() && !s.ducking && s.speed.y >= 0.0f && sign(s.speed.x) != -s.facing) {
        if (climb_check(s.facing)) {
            set_ducking(false);
            return 1;
        }
        if (input_.y < 1) {
            for (int i = 1; i <= 2; ++i) {
                if (!world_.collision.first_solid(actor_.body, {pos.x, pos.y - static_cast<float>(i)}) && climb_check(s.facing, -i)) {
                    actor_.move_v_exact(-i);
                    set_ducking(false);
                    return 1;
                }
            }
        }
    }
    if (can_dash()) {
        add_static_lift_boost();
        return start_dash();
    }
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
        if ((s.move_x == s.facing || (s.move_x == 0 && grab_check())) && input_.y != 1) {
            if (s.speed.y >= 0.0f && s.wall_slide_timer > 0.0f && climb_bounds_check(s.facing) &&
                world_.collision.first_solid(actor_.body, {pos.x + static_cast<float>(s.facing), pos.y}) && can_unduck(pos)) {
                set_ducking(false);
                s.wall_slide_dir = s.facing;
            }
            if (s.wall_slide_dir != 0) target = 160.0f + (20.0f - 160.0f) * (s.wall_slide_timer / 1.2f);
        }
        const float multiplier = std::abs(s.speed.y) < 40.0f && (jump_.check() || s.auto_jump) ? 0.5f : 1.0f;
        s.speed.y = approach(s.speed.y, target, 900.0f * multiplier * delta_);
    }
    if (s.var_jump_timer > 0.0f) {
        if (jump_.check() || s.auto_jump) s.speed.y = std::min(s.speed.y, s.var_jump_speed);
        else s.var_jump_timer = 0.0f;
    }
    if (jump_.pressed()) {
        if (s.jump_grace_timer > 0.0f) jump();
        else if (can_unduck(pos)) {
            for (int dir : {1, -1}) {
                if (wall_jump_check(dir)) {
                    if (s.facing == dir && grab_check() && s.stamina > 0.0f) climb_jump();
                    else if (dash_attacking() && super_wall_jump_angle_check()) super_wall_jump(-dir);
                    else wall_jump(-dir);
                    break;
                }
            }
        }
    }
    return 0;
}

void Player::collide_h(CollisionData data) {
    emit("collision_h", &data);
    state_.can_curve_dash = false;
    if (machine_.state() == 2) {
        const auto pos = actor_.body.position;
        const float dir = static_cast<float>(sign(state_.speed.x));
        Body duck_probe{{}, ducked, true};
        if (state_.on_ground && !world_.collision.first_solid(duck_probe, {pos.x + dir, pos.y})) {
            set_ducking(true);
            emit("collided_h", &data);
            return;
        }
        if (state_.speed.y == 0.0f && state_.speed.x != 0.0f) {
            for (int i = 1; i <= 4; ++i) {
                for (int side : {1, -1}) {
                    const Vec2 add{dir, static_cast<float>(i * side)};
                    const Vec2 at{pos.x + add.x, pos.y + add.y};
                    if (!world_.collision.first_solid(actor_.body, at) &&
                        world_.collision.first_solid(actor_.body, {at.x, at.y - static_cast<float>(side)}) && !dash_correct_check(add)) {
                        actor_.move_v_exact(i * side);
                        actor_.move_h_exact(sign(state_.speed.x));
                        emit("collided_h", &data);
                        return;
                    }
                }
            }
        }
    }
    if (state_.wall_speed_retention_timer <= 0.0f) {
        state_.wall_speed_retained = state_.speed.x;
        state_.wall_speed_retention_timer = 0.06f;
    }
    state_.speed.x = 0.0f;
    state_.dash_attack_timer = 0.0f;
    state_.glider_boost_timer = 0.0f;
    emit("collided_h", &data);
}

void Player::collide_v(CollisionData data) {
    emit("collision_v", &data);
    auto& s = state_;
    auto& pos = actor_.body.position;
    s.can_curve_dash = false;
    if (s.speed.y > 0.0f) {
        if (machine_.state() == 2 && !s.dash_started_on_ground) {
            for (int dir : {-1, 1}) {
                if ((dir == -1 && s.speed.x > 0.01f) || (dir == 1 && s.speed.x < -0.01f)) continue;
                for (int i = 1; i <= 4; ++i) {
                    if (!on_ground({pos.x + static_cast<float>(i * dir), pos.y})) {
                        actor_.move_h_exact(i * dir);
                        actor_.move_v_exact(1);
                        emit("collided_v", &data);
                        return;
                    }
                }
            }
        }
        if (s.dash_dir.x != 0.0f && s.dash_dir.y > 0.0f && s.speed.y > 0.0f) {
            s.dash_dir.x = static_cast<float>(sign(s.dash_dir.x));
            s.dash_dir.y = 0.0f;
            s.speed.y = 0.0f;
            s.speed.x *= 1.2f;
            set_ducking(true);
        }
    }
    if (s.speed.y < 0.0f) {
        const int reach = dash_attacking() && std::abs(s.speed.x) < 0.01f ? 5 : 4;
        if (s.speed.x <= 0.01f) {
            for (int offset = 1; offset <= reach; ++offset) {
                const Vec2 candidate{pos.x - static_cast<float>(offset), pos.y - 1.0f};
                if (!world_.collision.first_solid(actor_.body, candidate)) {
                    pos = candidate;
                    emit("collided_v", &data);
                    return;
                }
            }
        }
        if (s.speed.x >= -0.01f) {
            for (int offset = 1; offset <= reach; ++offset) {
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
    s.dash_attack_timer = 0.0f;
    s.glider_boost_timer = 0.0f;
    emit("collided_v", &data);
}

void Player::frame(float delta_time, PlayerInput input, PlayerObserver observer) {
    if (updating_) throw std::logic_error("Recursive Player frame is unsupported");
    if (death_.removed) throw std::invalid_argument("Removed Player cannot simulate another frame");
    if (!std::isfinite(delta_time) || delta_time < 0.0f || !std::isfinite(1000.0f * delta_time) ||
        input.x < -1 || input.x > 1 || input.y < -1 || input.y > 1 ||
        input.aim_x < -1 || input.aim_x > 1 || input.aim_y < -1 || input.aim_y > 1)
        throw std::invalid_argument("Invalid Player frame input");
    if (input.dash || input.jump.debug_override_pressed || input.dash_button.debug_override_pressed)
        throw std::invalid_argument("Unresolved legacy Dash and debug override are outside the supported profile");
    validate_world();
    finite(state_.speed);
    finite(actor_.body.position);
    updating_ = true;
    observer_ = std::move(observer);
    try {
        clock_.sample(delta_time);
        delta_ = clock_.delta;
        hazard_frame_ = {};
        input_ = input;
        auto& s = state_;
        auto& pos = actor_.body.position;
        jump_.sample = input.jump;
        jump_.update(delta_);
        dash_.sample = input.dash_button;
        dash_.sample.disabled = input.jump.disabled;
        dash_.update(delta_);
        emit("input");
        if (!clock_.simulate()) {
            emit("freeze");
            observer_ = {};
            updating_ = false;
            return;
        }
        s.previous_position = pos;
        if (s.glider_boost_timer > 0.0f) s.glider_boost_timer -= delta_;
        if (s.low_friction_stop_timer > 0.0f) s.low_friction_stop_timer -= delta_;
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
        if (s.wall_boost_timer > 0.0f) {
            s.wall_boost_timer -= delta_;
            if (s.move_x == s.wall_boost_dir) {
                s.speed.x = 130.0f * static_cast<float>(s.move_x);
                s.stamina += 27.5f;
                s.wall_boost_timer = 0.0f;
            }
        }
        if (s.on_ground && machine_.state() != 1) {
            s.auto_jump = false;
            s.stamina = 110.0f;
            s.wall_slide_timer = 1.2f;
        }
        if (s.dash_attack_timer > 0.0f) s.dash_attack_timer -= delta_;
        if (s.on_ground) {
            s.jump_grace_timer = 0.1f;
        } else if (s.jump_grace_timer > 0.0f) s.jump_grace_timer -= delta_;
        if (s.dash_cooldown_timer > 0.0f) s.dash_cooldown_timer -= delta_;
        if (s.dash_refill_cooldown_timer > 0.0f) s.dash_refill_cooldown_timer -= delta_;
        else if (s.on_ground) {
            hazard_frame_.refill_checked = true;
            if (!overlaps_spike(pos)) {
                hazard_frame_.refill_called = true;
                if (s.dashes < 1) s.dashes = 1;
            }
        }
        if (s.var_jump_timer > 0.0f) s.var_jump_timer -= delta_;
        if (s.force_move_x_timer > 0.0f) {
            s.force_move_x_timer -= delta_;
            s.move_x = s.force_move_x;
        } else {
            s.move_x = input.x;
            s.climb_hop_solid = nullptr;
        }
        if (s.climb_hop_solid && !s.climb_hop_solid->collidable) s.climb_hop_solid = nullptr;
        else if (s.climb_hop_solid && (s.climb_hop_solid->position.x != s.climb_hop_solid_position.x ||
                                      s.climb_hop_solid->position.y != s.climb_hop_solid_position.y))
            throw std::invalid_argument("Hop solid moved outside the static Player profile");
        if (s.move_x != 0 && machine_.state() != 1) s.facing = s.move_x;
        if (input.aim_x == 0 && input.aim_y == 0) s.last_aim = {1.0f * static_cast<float>(s.facing), 0.0f * static_cast<float>(s.facing)};
        else {
            const float scale = input.aim_x != 0 && input.aim_y != 0 ? 1.0f / std::sqrt(2.0f) : 1.0f;
            s.last_aim = {static_cast<float>(input.aim_x) * scale, static_cast<float>(input.aim_y) * scale};
        }
        if (s.wall_speed_retention_timer > 0.0f) {
            if (sign(s.speed.x) == -sign(s.wall_speed_retained)) s.wall_speed_retention_timer = 0.0f;
            else if (!world_.collision.first_solid(actor_.body, {pos.x + static_cast<float>(sign(s.wall_speed_retained)), pos.y})) {
                s.speed.x = s.wall_speed_retained;
                s.wall_speed_retention_timer = 0.0f;
            } else s.wall_speed_retention_timer -= delta_;
        }
        if (s.hop_wait_x != 0) {
            if (sign(s.speed.x) == -s.hop_wait_x || s.speed.y > 0.0f) s.hop_wait_x = 0;
            else if (!world_.collision.first_solid(actor_.body, {pos.x + static_cast<float>(s.hop_wait_x), pos.y})) {
                s.low_friction_stop_timer = 0.15f;
                s.speed.x = s.hop_wait_speed;
                s.hop_wait_x = 0;
            }
        }
        emit("preamble");
        machine_.update(delta_, delta_);
        emit("normal");
        if (!s.on_ground && s.speed.y <= 0.0f) {
            for (const Body* platform : world_.collision.jump_thrus) {
                if (collide_check(actor_.body, *platform, pos)) {
                    hazard_frame_.boost_checked = true;
                    hazard_frame_.boost_blocked = jump_thru_boost_blocked_check();
                    if (!hazard_frame_.boost_blocked) actor_.move_v(-40.0f * delta_);
                    break;
                }
            }
        }
        emit("boost");
        if (!s.on_ground && dash_attacking() && s.dash_dir.y == 0.0f &&
            (world_.collision.first_solid(actor_.body, {pos.x, pos.y + 3.0f}) ||
             world_.collision.first_outside_jump_thru(actor_.body, {pos.x, pos.y + 3.0f})) && !dash_correct_check({0.0f, 3.0f}))
            actor_.move_v_exact(3);
        if (s.speed.y > 0.0f && can_unduck(pos) && !s.on_ground && s.jump_grace_timer <= 0.0f) set_ducking(false);
        emit("unduck");
        actor_.move_h(s.speed.x * delta_, [this](CollisionData data) { collide_h(data); });
        emit("horizontal");
        actor_.move_v(s.speed.y * delta_, [this](CollisionData data) { collide_v(data); });
        emit("vertical");
        if (check_hazards()) emit("removed");
        else {
            emit("hazards");
            s.was_on_ground = s.on_ground;
            emit("complete");
        }
    } catch (...) {
        observer_ = {};
        updating_ = false;
        throw;
    }
    observer_ = {};
    updating_ = false;
}

}
