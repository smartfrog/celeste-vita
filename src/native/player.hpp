#pragma once

#include "input.hpp"
#include "hazards.hpp"
#include "movement.hpp"
#include "scheduling.hpp"
#include "object_identity.hpp"

namespace celeste {

enum class PlayerProfile { default_static };
enum class JumpKind { none, jump, super_jump, wall_jump, super_wall_jump, climb_jump };
struct PlayerColliderEntry {
    const StaticSpike* spike=nullptr;
    const Body* unsupported_body=nullptr;
    const char* unsupported_member=nullptr;
};

struct PlayerWorld {
    StaticWorld collision;
    std::vector<Body*> safe_ground;
    std::int32_t bounds_left = -10000;
    std::int32_t bounds_right = 10000;
    std::vector<const StaticSpike*> spikes;
    bool death_supported=true;
    std::vector<PlayerColliderEntry> ordered_colliders{};
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

struct PlayerFrameContext {
    FrameClock clock;
    VirtualButton jump{0.08f}, dash{0.08f};
    void sample(float raw_delta_time, const PlayerInput& input);
};

struct PlayerState {
    Vec2 speed{};
    Vec2 previous_position{};
    int facing = 1;
    int move_x = 0;
    int force_move_x = 0;
    float force_move_x_timer = 0.0f, low_friction_stop_timer = 0.0f;
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
    float climb_no_move_timer = 0.0f, wall_boost_timer = 0.0f;
    int last_climb_move = 0, wall_boost_dir = 0, hop_wait_x = 0;
    float hop_wait_speed = 0.0f;
    Body* climb_hop_solid = nullptr;
    Vec2 climb_hop_solid_position{};
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
enum class PlayerCosmeticPhase;
using PlayerCosmeticObserver = std::function<void(PlayerCosmeticPhase)>;

class Player final {
public:
    explicit Player(const PlayerWorld& world, Vec2 spawn = {}, Vec2 initial_speed = {},
                    PlayerProfile profile = PlayerProfile::default_static, PlayerFrameContext* context = nullptr);
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
    JumpKind jump_kind() const { return jump_kind_; }
    unsigned jump_count() const { return jump_count_; }
    bool tired() const { return (state_.wall_boost_timer > 0.0f ? state_.stamina + 27.5f : state_.stamina) < 20.0f; }
    bool grab_held() const { return grab_check(); }
    bool die(Vec2 direction);
    void request_state(int state);
    void frame(float delta_time, PlayerInput input = {}, PlayerObserver observer = {}, PlayerCosmeticObserver cosmetic = {});
    void update_sampled(PlayerInput input, PlayerCosmeticObserver cosmetic = {});
    void begin_respawn();
    void before_up_transition();
    bool transition_to(Vec2 target,float delta_time);
    void on_transition();
    bool ground_query() const;
    std::uint64_t object_identity() const { return object_identity_; }
    int scene_tag() const { return 16; }
    bool scene_active() const { return !death_.removed; }
    float intro_ease() const { return intro_ease_; }
    Vec2 dead_offset() const { return dead_offset_; }
    const Tween* respawn_tween() const { return respawn_tween_ && respawn_tween_->active ? respawn_tween_.get() : nullptr; }
    unsigned respawn_completions() const { return respawn_completions_; }

private:
    const std::uint64_t object_identity_=next_object_identity();
    const PlayerWorld& world_;
    Actor actor_;
    PlayerState state_;
    StateMachine machine_{26};
    PlayerFrameContext owned_context_;
    VirtualButton& jump_;
    VirtualButton& dash_;
    FrameClock& clock_;
    const bool borrowed_context_;
    std::uint64_t last_sampled_frame_;
    std::unique_ptr<Tween> respawn_tween_;
    float intro_ease_ = 0;
    Vec2 dead_offset_{};
    unsigned respawn_completions_ = 0;
    PlayerInput input_{};
    float delta_ = 0.0f;
    PlayerObserver observer_;
    PlayerCosmeticObserver cosmetic_;
    bool updating_ = false;
    PlayerDeath death_;
    HazardFrame hazard_frame_;
    JumpKind jump_kind_ = JumpKind::none;
    unsigned jump_count_ = 0;

    void validate_world() const;
    void emit(const char* phase, const CollisionData* collision = nullptr) const;
    void cosmetic(PlayerCosmeticPhase phase) const;
    void set_ducking(bool value);
    bool can_unduck(Vec2 at) const;
    bool climb_bounds_check(int dir) const;
    void normal_begin();
    void normal_end();
    int normal_update();
    void jump();
    void begin_jump(JumpKind kind, float var_time);
    void add_static_lift_boost();
    void super_jump();
    void wall_jump(int dir);
    void super_wall_jump(int dir);
    void climb_jump();
    bool grab_check() const;
    bool can_dash() const;
    int start_dash();
    static float approach(float value, float target, float max_move);
    bool climb_check(int dir, int y_add = 0) const;
    void climb_begin();
    void climb_end();
    int climb_update();
    void climb_hop();
    bool slip_check(float add_y = 0.0f) const;
    bool climb_hop_blocked_check() const;
    bool super_wall_jump_angle_check() const;
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
    void frame_impl(float delta_time, PlayerInput input, PlayerObserver observer, PlayerCosmeticObserver cosmetic, bool sampled);
};

}
