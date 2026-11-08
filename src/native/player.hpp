#pragma once

#include "input.hpp"
#include "movement.hpp"
#include "scheduling.hpp"

namespace celeste {

enum class PlayerProfile { default_static };

struct PlayerWorld {
    StaticWorld collision;
    std::vector<Body*> safe_ground;
    std::int32_t bounds_left = -10000;
    std::int32_t bounds_right = 10000;
};

struct PlayerInput {
    int x = 0;
    int y = 0;
    ButtonSample jump{};
    bool grab = false;
    bool dash = false;
};

struct PlayerState {
    Vec2 speed{};
    Vec2 previous_position{};
    int facing = 1;
    int move_x = 0;
    bool on_ground = false;
    bool was_on_ground = false;
    bool on_safe_ground = false;
    bool ducking = false;
    float jump_grace_timer = 0.0f;
    float var_jump_timer = 0.0f;
    float var_jump_speed = 0.0f;
    float max_fall = 0.0f;
    float wall_slide_timer = 1.2f;
    int wall_slide_dir = 0;
    float wall_speed_retention_timer = 0.0f;
    float wall_speed_retained = 0.0f;
    float stamina = 110.0f;
    int dashes = 1;
    bool launched = false;
};

using PlayerObserver = std::function<void(const char*, const CollisionData*)>;

class Player final {
public:
    explicit Player(const PlayerWorld& world, Vec2 spawn = {}, Vec2 initial_speed = {},
                    PlayerProfile profile = PlayerProfile::default_static);
    Player(const Player&) = delete;
    Player& operator=(const Player&) = delete;

    const Actor& actor() const { return actor_; }
    const PlayerState& state() const { return state_; }
    const VirtualButton& jump_button() const { return jump_; }
    const StateMachine& state_machine() const { return machine_; }
    Hitbox hurtbox() const;
    void request_state(int state);
    void frame(float delta_time, PlayerInput input = {}, PlayerObserver observer = {});

private:
    const PlayerWorld& world_;
    Actor actor_;
    PlayerState state_;
    StateMachine machine_{26};
    VirtualButton jump_{0.08f};
    PlayerInput input_{};
    float delta_ = 0.0f;
    PlayerObserver observer_;
    bool updating_ = false;

    void validate_world() const;
    void emit(const char* phase, const CollisionData* collision = nullptr) const;
    void set_ducking(bool value);
    bool can_unduck(Vec2 at) const;
    bool climb_bounds_check(int dir) const;
    void normal_begin();
    void normal_end();
    int normal_update();
    void jump();
    void collide_h(CollisionData data);
    void collide_v(CollisionData data);
};

}
