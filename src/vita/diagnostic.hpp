#pragma once

#include "directional_input.hpp"
#include "player.hpp"
#include "presentation.hpp"
#include "lifecycle.hpp"
#include <memory>

namespace celeste::diagnostic {

struct Controls {
    bool left = false, right = false, up = false, down = false;
    bool cross = false, triangle = false, start = false;
    bool square = false;
    bool l = false;
};

struct AnalogControls {
    Controls buttons;
    StickReading stick;
};

struct Sample {
    PlayerInput player;
    bool reset = false, exit = false;
};

class Controller final {
public:
    Sample sample(Controls controls);
    Sample sample_analog(const AnalogControls& controls);
private:
    Sample make_sample(const Controls& controls, int x, int y, int aim_x, int aim_y);
    Controls previous_;
    DirectionalResolver directions_;
};

struct Viewport { int x, y, width, height; };
Viewport letterbox(int width, int height);
const char* jump_kind_name(JumpKind kind);

class Session final {
public:
    explicit Session(const PlayerWorld& world, Vec2 spawn = {19, 144}, const PlayerFrameBank* bank = nullptr,
                      std::int32_t diagnostic_seed = 0);
    Session(const PlayerWorld& world, const PlayerFrameBank& bank, bool hit_checkpoint=false, std::int32_t diagnostic_seed=0);
    void step(const Sample& sample);
    const Player& player() const { return automatic_ ? automatic_->player() : *player_; }
    unsigned jump_count() const { return automatic_ ? automatic_->stats().jumps : player_->jump_count(); }
    FirstRoomSession* lifecycle() { return automatic_.get(); }
    const FirstRoomSession* lifecycle() const { return automatic_.get(); }
    unsigned resets() const { return resets_; }
    bool exiting() const { return exiting_; }
    PlayerPresentation* presentation() { return automatic_ ? &automatic_->presentation() : presentation_.get(); }
    const PlayerPresentation* presentation() const { return automatic_ ? &automatic_->presentation() : presentation_.get(); }
    PlayerProjection projection() const;
    PlayerTrails& trails() { return automatic_ ? automatic_->trails() : trails_; }
    const PlayerTrails& trails() const { return automatic_ ? automatic_->trails() : trails_; }
private:
    const PlayerWorld& world_;
    const Vec2 spawn_;
    std::unique_ptr<Player> player_;
    std::unique_ptr<PlayerPresentation> presentation_;
    PlayerTrails trails_;
    std::unique_ptr<FirstRoomSession> automatic_;
    const PlayerFrameBank* automatic_bank_=nullptr;
    bool hit_checkpoint_=false;
    std::int32_t diagnostic_seed_=0;
    PlayerInput presentation_input_{};
    unsigned resets_ = 0;
    bool exiting_ = false;
};

}
