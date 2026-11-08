#pragma once

#include "player.hpp"
#include <memory>

namespace celeste::diagnostic {

struct Controls {
    bool left = false, right = false, up = false, down = false;
    bool cross = false, triangle = false, start = false;
};

struct Sample {
    PlayerInput player;
    bool reset = false, exit = false;
};

class Controller final {
public:
    Sample sample(Controls controls);
private:
    Controls previous_;
};

struct Viewport { int x, y, width, height; };
Viewport letterbox(int width, int height);

class Session final {
public:
    explicit Session(const PlayerWorld& world, Vec2 spawn = {19, 144});
    void step(const Sample& sample);
    const Player& player() const { return *player_; }
    unsigned resets() const { return resets_; }
    bool exiting() const { return exiting_; }
private:
    const PlayerWorld& world_;
    const Vec2 spawn_;
    std::unique_ptr<Player> player_;
    unsigned resets_ = 0;
    bool exiting_ = false;
};

}
