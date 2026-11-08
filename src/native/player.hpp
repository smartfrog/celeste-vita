#pragma once

#include "input.hpp"
#include "hazards.hpp"
#include "movement.hpp"
#include "scheduling.hpp"

namespace celeste {

enum class PlayerProfile { default_static };

struct PlayerWorld {
    StaticWorld collision;
    std::vector<Body*> safe_ground;
    std::int32_t bounds_left = -10000;
    std::int32_t bounds_right = 10000;
    std::vector<const StaticSpike*> spikes;
};

struct PlayerInput {
    int x = 0;
    int y = 0;
    ButtonSample jump{};
    bool grab = false;
    bool dash = false;
    ButtonSample dash_button{};
    int aim_x = 0;
    int aim_y = 0;
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
    Vec2 before_dash_speed{}, dash_dir{}, last_aim{}, glider_boost_dir{};
    bool started_dashing = false, dash_started_on_ground = false, called_dash_events = false;
    bool can_curve_dash = false, auto_jump = false;
    float auto_jump_timer = 0.0f;
    float dash_cooldown_timer = 0.0f, dash_refill_cooldown_timer = 0.0f, dash_attack_timer = 0.0f;
    float glider_boost_timer = 0.0f, dash_trail_timer = 0.0f;
    int dash_trail_counter = 0;
    unsigned dash_events = 0;
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
    const VirtualButton& dash_button() const { return dash_; }
    const FrameClock& clock() const { return clock_; }
    const StateMachine& state_machine() const { return machine_; }
    Hitbox hurtbox() const;
    const PlayerDeath& death() const { return death_; }
    const HazardFrame& hazard_frame() const { return hazard_frame_; }
    bool die(Vec2 direction);
    void request_state(int state);
    void frame(float delta_time, PlayerInput input = {}, PlayerObserver observer = {});

private:
    const PlayerWorld& world_;
    Actor actor_;
    PlayerState state_;
    StateMachine machine_{26};
    VirtualButton jump_{0.08f};
    VirtualButton dash_{0.08f};
    FrameClock clock_;
    PlayerInput input_{};
    float delta_ = 0.0f;
    PlayerObserver observer_;
    bool updating_ = false;
    PlayerDeath death_;
    HazardFrame hazard_frame_;

    void validate_world() const;
    void emit(const char* phase, const CollisionData* collision = nullptr) const;
    void set_ducking(bool value);
    bool can_unduck(Vec2 at) const;
    bool climb_bounds_check(int dir) const;
    void normal_begin();
    void normal_end();
    int normal_update();
    void jump();
    void dash_begin();
    void dash_end();
    int dash_update();
    IteratorPtr dash_coroutine();
    void call_dash_events();
    bool dash_attacking() const;
    bool dash_correct_check(Vec2 add) const;
    bool on_ground(Vec2 at) const;
    bool wall_jump_check(int dir) const;
    void collide_h(CollisionData data);
    void collide_v(CollisionData data);
    bool overlaps_spike(Vec2 at) const;
    bool jump_thru_boost_blocked_check() const;
    bool check_hazards();
    bool die_immediate(Vec2 direction);
};

}
