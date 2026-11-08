#pragma once

#include "movement.hpp"
#include <array>
#include <string>
#include <string_view>

namespace celeste {

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
    unsigned calls() const { return calls_; }
private:
    std::array<std::int32_t,56> values_{};
    int index_ = 0, partner_ = 21;
    unsigned calls_ = 0;
};

enum class PlayerCosmeticPhase {
    scene_tick, ground, duck_turn, components, jump, duck, stand, fast_fall, landing,
    select, hair_color, after_update
};

struct PlayerProjection {
    Vec2 position, speed, dash_direction;
    int facing = 1, state = 0, move_x = 0, raw_x = 0, raw_y = 0, climb_move = 0, wall_slide = 0;
    int dashes = 1;
    bool on_ground = false, ducking = false, dash_attacking = false, tired = false;
    std::function<bool(Vec2)> solid_body, solid_point, jump_thru_body;
};

struct PlayerDraw {
    unsigned frame;
    Vec2 position, origin, scale;
    float rotation;
    PresentationColor color;
};

struct PlayerPose {
    std::string animation, last_animation;
    unsigned animation_frame = 0, frame = 0;
    float timer = 0, rate = 1, rotation = 0, wave = 0;
    Vec2 scale{1,1};
    std::array<Vec2,4> hair_nodes{};
    PresentationColor hair_color{172,50,50,255};
    float hair_flash_timer = 0, idle_timer = 0, highest_air_y = 0;
    int last_dashes = 1, hair_facing = 1;
    bool fast_jump = false, flash = false, animating = false;
    unsigned frame_callbacks = 0, change_callbacks = 0, last_callbacks = 0;
    std::uint32_t callback_hash = 2166136261u;
};

class PlayerPresentation final {
public:
    PlayerPresentation(const PlayerFrameBank& bank, Vec2 spawn, std::int32_t diagnostic_seed = 0);
    void reset(Vec2 spawn);
    void observe(PlayerCosmeticPhase phase, const PlayerProjection& player, float delta_time);
    std::vector<PlayerDraw> draw(const PlayerProjection& player);
    const PlayerPose& pose() const { return pose_; }
    unsigned random_calls() const { return random_.calls(); }
    float scene_time() const { return scene_time_; }
    std::int32_t diagnostic_seed() const { return diagnostic_seed_; }
private:
    const PlayerFrameBank& bank_;
    const std::int32_t diagnostic_seed_;
    PresentationRandom random_;
    PlayerPose pose_;
    float scene_time_ = 0;
    void play(std::string_view id);
    void set_frame(unsigned frame);
    void callback(std::string_view kind, std::string_view animation);
    void update_animation(float delta_time);
    void select(const PlayerProjection& player);
};

class Player;
struct PlayerWorld;
struct PlayerInput;
PlayerProjection project_player(const Player& player, const PlayerWorld& world, const PlayerInput& input);

}
