#include "diagnostic.hpp"
#include <algorithm>
#include <stdexcept>

namespace celeste::diagnostic {
Sample Controller::sample(Controls controls) {
    Sample result;
    result.player.x = int(controls.right) - int(controls.left);
    result.player.y = int(controls.down) - int(controls.up);
    result.player.jump = {controls.cross, controls.cross && !previous_.cross};
    result.reset = controls.triangle && !previous_.triangle;
    result.exit = controls.start;
    previous_ = controls;
    return result;
}
Viewport letterbox(int width, int height) {
    if (width <= 0 || height <= 0) throw std::invalid_argument("Invalid display size");
    const int scale = std::min(width / 320, height / 180);
    if (!scale) throw std::invalid_argument("Display smaller than logical room");
    return {(width - 320*scale)/2, (height - 180*scale)/2, 320*scale, 180*scale};
}
Session::Session(const PlayerWorld& world, Vec2 spawn)
    : world_(world), spawn_(spawn), player_(std::make_unique<Player>(world, spawn)) {}
void Session::step(const Sample& sample) {
    if (exiting_) return;
    if (sample.exit) { exiting_ = true; return; }
    if (sample.reset) {
        auto fresh = std::make_unique<Player>(world_, spawn_);
        player_ = std::move(fresh);
        ++resets_;
        return;
    }
    if (!player_->death().dead) player_->frame(1.0f / 60.0f, sample.player);
}
}
