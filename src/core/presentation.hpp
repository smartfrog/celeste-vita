#pragma once

#include "movement.hpp"
#include "object_identity.hpp"
#include <array>
#include <string>
#include <string_view>

namespace celeste {
class Player;

struct PresentationColor {
    std::uint8_t r = 255, g = 255, b = 255, a = 255;
};

struct PlayerFrame {
    std::string name;
    unsigned page;
    int u, v, width, height, trim_x, trim_y, frame_width, frame_height;
    Vec2 hair_offset;
    int hair_frame;
    bool has_hair;
};

struct PlayerAnimation {
    std::string id;
    float delay;
    std::string next;
    std::vector<unsigned> frames;
};

struct PlayerFrameBank {
    unsigned pages = 0;
    std::vector<PlayerFrame> frames;
    std::vector<PlayerAnimation> animations;
    std::array<unsigned,3> bangs{};
    unsigned hair = 0;
    const PlayerAnimation& animation(std::string_view id) const;
    void validate() const;
};

class PresentationRandom final {
public:
    explicit PresentationRandom(std::int32_t seed);
    double next_double();
    int next(int maximum);
    std::function<void(const char*,unsigned)> observer;
    unsigned calls() const { return calls_; }
    std::array<std::int32_t,58> state_words() const;
    std::uint64_t object_identity() const { return object_identity_; }
    std::int32_t initial_seed() const { return initial_seed_; }
private:
    const std::uint64_t object_identity_=next_object_identity();
    const std::int32_t initial_seed_;
    std::array<std::int32_t,56> values_{};
    int index_ = 0, partner_ = 21;
    unsigned calls_ = 0;
    double sample();
};

enum class PlayerCosmeticPhase {
    scene_tick, ground, duck_turn, components, jump, duck, stand, fast_fall, landing,
    select, hair_color, after_update, respawn_complete, dash_trail, climb_hop,
    sweat_climb, sweat_end, sweat_jump
};

struct PlayerProjection {
    Vec2 position, speed, dash_direction;
    int facing = 1, state = 0, move_x = 0, raw_x = 0, raw_y = 0, climb_move = 0, wall_slide = 0;
    int dashes = 1;
    float stamina = 110, climb_no_move_timer = 0;
    bool on_ground = false, ducking = false, dash_attacking = false, tired = false;
    std::function<bool(Vec2)> solid_body, solid_point, jump_thru_body;
};

struct PlayerDraw {
    unsigned frame;
    Vec2 position, origin, scale;
    float rotation;
    PresentationColor color;
};

struct PlayerAnimationTrack {
    std::string animation, last_animation;
    unsigned animation_frame = 0, frame = 0;
    float timer = 0, rate = 1;
    bool animating = false;
    unsigned frame_callbacks = 0, change_callbacks = 0, last_callbacks = 0;
    std::uint32_t callback_hash = 2166136261u;
};

struct PlayerPose : PlayerAnimationTrack {
    float rotation = 0, wave = 0;
    Vec2 scale{1,1};
    std::array<Vec2,4> hair_nodes{};
    PresentationColor hair_color{172,50,50,255};
    PresentationColor sprite_color{};
    float hair_flash_timer = 0, idle_timer = 0, highest_air_y = 0;
    int last_dashes = 1, hair_facing = 1;
    bool fast_jump = false, flash = false;
};

class PlayerPresentation final {
public:
    PlayerPresentation(const PlayerFrameBank& bank, Vec2 spawn, std::int32_t diagnostic_seed = 0,
                       PresentationRandom* random = nullptr, const float* level_time = nullptr);
    PlayerPresentation(const PlayerPresentation&)=delete;
    PlayerPresentation& operator=(const PlayerPresentation&)=delete;
    void reset(Vec2 spawn);
    void observe(PlayerCosmeticPhase phase, const PlayerProjection& player, float delta_time);
    std::vector<PlayerDraw> draw(const PlayerProjection& player);
    std::vector<PlayerDraw> trail_capture(const PlayerProjection& player, Vec2 offset, Vec2 body_scale);
    void play_animation(std::string_view id) { play(id); }
    void corpse_render(float scale, float rotation, int facing);
    void corpse_color(PresentationColor initial);
    const PlayerPose& pose() const { return pose_; }
    const PlayerAnimationTrack& sweat_pose() const { return sweat_; }
    PlayerDraw sweat_draw(const PlayerProjection& player);
    unsigned random_calls() const { return random_.calls(); }
    float scene_time() const { return level_time_ ? *level_time_ : scene_time_; }
    std::int32_t diagnostic_seed() const { return diagnostic_seed_; }
    std::uint64_t object_identity() const { return object_identity_; }
    void simulate_hair_motion(bool value) { simulate_hair_motion_=value; }
    bool hair_motion_simulated() const { return simulate_hair_motion_; }
    void bind_player_owner(const Player& player);
    const Player* player_owner() const { return player_owner_; }
private:
    const Player* player_owner_=nullptr;
    const std::uint64_t object_identity_=next_object_identity();
    bool simulate_hair_motion_=true;
    const PlayerFrameBank& bank_;
    const std::int32_t diagnostic_seed_;
    PresentationRandom owned_random_;
    PresentationRandom& random_;
    PlayerPose pose_;
    PlayerAnimationTrack sweat_;
    Vec2 sweat_scale_{1,1};
    bool sweat_animations_ = false, sweat_frame_ = false;
    float scene_time_ = 0;
    const float* level_time_;
    void play(std::string_view id);
    void play(PlayerAnimationTrack& track, std::string_view id, bool restart = false);
    void set_frame(PlayerAnimationTrack& track, unsigned frame);
    void callback(PlayerAnimationTrack& track, std::string_view kind, std::string_view animation);
    void update_animation(PlayerAnimationTrack& track, float delta_time);
    void select_sweat(const PlayerProjection& player);
    void select(const PlayerProjection& player);
    std::vector<PlayerDraw> hair_draws();
};

std::vector<PlayerDraw> death_effect_draws(const PlayerFrameBank& bank, Vec2 position, PresentationColor color, float ease);

class Player;
struct PlayerWorld;
struct PlayerInput;
PlayerProjection project_player(const Player& player, const PlayerWorld& world, const PlayerInput& input);

}
