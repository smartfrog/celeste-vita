#include "diagnostic.hpp"
#include <algorithm>
#include <stdexcept>

namespace celeste::diagnostic {
const char* jump_kind_name(JumpKind kind) {
    switch (kind) {
    case JumpKind::none: return "None";
    case JumpKind::jump: return "Jump";
    case JumpKind::super_jump: return "SuperJump";
    case JumpKind::wall_jump: return "WallJump";
    case JumpKind::super_wall_jump: return "SuperWallJump";
    case JumpKind::climb_jump: return "ClimbJump";
    }
    throw std::invalid_argument("Unknown jump kind");
}
Sample Controller::make_sample(const Controls& controls, int x, int y, int aim_x, int aim_y) {
    Sample result;
    result.player.x = x;
    result.player.y = y;
    result.player.jump = {controls.cross, controls.cross && !previous_.cross, !controls.cross && previous_.cross};
    result.player.aim_x = aim_x;
    result.player.aim_y = aim_y;
    result.player.dash_button = {controls.square, controls.square && !previous_.square, !controls.square && previous_.square};
    result.player.grab = controls.l;
    result.reset = controls.triangle && !previous_.triangle;
    result.exit = controls.start;
    return result;
}
Sample Controller::sample(Controls controls) {
    const int x = int(controls.right) - int(controls.left);
    const int y = int(controls.down) - int(controls.up);
    const auto result = make_sample(controls, x, y, x, y);
    previous_ = controls;
    return result;
}
Sample Controller::sample_analog(const AnalogControls& controls) {
    const auto stick = normalize_vita_stick(controls.stick);
    const auto resolved = directions_.update(
        {controls.buttons.left, controls.buttons.right, controls.buttons.up, controls.buttons.down}, stick);
    const auto result = make_sample(controls.buttons, resolved.move_x, resolved.move_y, resolved.aim_x, resolved.aim_y);
    previous_ = controls.buttons;
    return result;
}
Viewport letterbox(int width, int height) {
    if (width <= 0 || height <= 0) throw std::invalid_argument("Invalid display size");
    const int scale = std::min(width / 320, height / 180);
    if (!scale) throw std::invalid_argument("Display smaller than logical room");
    return {(width - 320*scale)/2, (height - 180*scale)/2, 320*scale, 180*scale};
}
Session::Session(const PlayerWorld& world, Vec2 spawn, const PlayerFrameBank* bank, std::int32_t diagnostic_seed)
    : world_(world), spawn_(spawn), player_(std::make_unique<Player>(world, spawn)),
      presentation_(bank ? std::make_unique<PlayerPresentation>(*bank,player_->actor().body.position,diagnostic_seed) : nullptr) {}
Session::Session(const PlayerWorld& world,const PlayerFrameBank& bank,bool checkpoint,std::int32_t seed)
    : world_(world),spawn_{19,144},automatic_(std::make_unique<FirstRoomSession>(world,bank,checkpoint,seed)),
      automatic_bank_(&bank),hit_checkpoint_(checkpoint),diagnostic_seed_(seed) {}
PlayerProjection Session::projection() const { return automatic_ ? automatic_->projection() : project_player(*player_,world_,presentation_input_); }
void Session::step(const Sample& sample) {
    if (exiting_) return;
    if (sample.exit) { exiting_ = true; return; }
    if (automatic_) {
        if(sample.reset) {
            automatic_=std::make_unique<FirstRoomSession>(world_,*automatic_bank_,hit_checkpoint_,diagnostic_seed_);
            ++resets_;
        } else automatic_->step(1.f/60.f,sample.player);
        return;
    }
    if (sample.reset) {
        auto fresh = std::make_unique<Player>(world_, spawn_);
        player_ = std::move(fresh);
        if(presentation_) presentation_->reset(player_->actor().body.position);
        trails_.clear();
        presentation_input_={};
        ++resets_;
        return;
    }
    presentation_input_=sample.player;
    if (!player_->death().dead) player_->frame(1.0f / 60.0f, sample.player,{},
        presentation_ ? PlayerCosmeticObserver{[this](PlayerCosmeticPhase phase) {
            if(phase==PlayerCosmeticPhase::scene_tick) trails_.update(player_->clock().delta);
            if(phase==PlayerCosmeticPhase::dash_trail) trails_.add(projection(),presentation_->pose());
            presentation_->observe(phase,projection(),player_->clock().delta);
        }} : PlayerCosmeticObserver{});
}
}
