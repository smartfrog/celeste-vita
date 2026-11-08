#include "player.hpp"

#include <iostream>
#include <cmath>
#include <stdexcept>
#include <string>

using namespace celeste;

namespace {
void expect(bool condition, const char* message) { if (!condition) throw std::runtime_error(message); }

PlayerInput dash(int x = 1, int y = 0) {
    PlayerInput input;
    input.dash_button = {true, true}; input.aim_x = x; input.aim_y = y;
    return input;
}

void entry() {
    PlayerWorld world;
    Player player(world);
    player.frame(0.0f, dash());
    expect(player.state_machine().state() == 2 && player.state().dashes == 0 && player.state().speed.x == 0.0f,
           "Dash press must spend inventory and enter Dash before launch");
}

void freeze_crossing_updates_both_buttons() {
    PlayerWorld world;
    Player player(world);
    player.frame(0.0f, dash());
    auto input = dash(0, -1); input.jump = {true, true};
    player.frame(0.06f, input);
    expect(player.clock().freeze_timer == 0.0f && player.state().started_dashing && player.state().dash_dir.y == 0.0f,
           "Crossing tick must remain frozen");
    expect(player.jump_button().buffer_counter() == 0.08f && player.dash_button().buffer_counter() == 0.08f,
           "Both inputs must update inside freeze");
}

void release_inside_freeze_clears_buffer() {
    PlayerWorld world;
    Player player(world);
    player.frame(0.0f, dash());
    auto input = dash(); input.jump = {true, true};
    player.frame(0.02f, input);
    input.jump = {false, false, true}; input.dash_button = {false, false, true};
    player.frame(0.03f, input);
    expect(player.jump_button().buffer_counter() == 0.0f && player.dash_button().buffer_counter() == 0.0f,
           "Release must clear both freeze-time buffers");
}

void aim_is_independent_and_launch_is_delayed() {
    PlayerWorld world;
    Player player(world);
    player.frame(0.0f, dash());
    player.frame(0.05f);
    PlayerInput input; input.x = 1; input.aim_y = -1;
    bool update_before_launch = false;
    player.frame(0.0f, input, [&](const char* phase, const CollisionData*) {
        if (std::string(phase) == "dash_update") update_before_launch = player.state().speed.y == 0.0f && player.state().dash_dir.y == 0.0f;
    });
    expect(update_before_launch && player.state().speed.x == 0.0f && player.state().speed.y == -240.0f,
           "DashUpdate must precede launch with the latest independent aim");
}

void wait_crossing_consumes_tick() {
    PlayerWorld world;
    Player player(world);
    player.frame(0.0f, dash(0, -1)); player.frame(0.05f); player.frame(0.0f, dash(0, -1));
    player.frame(0.15f);
    expect(player.state_machine().state() == 2, "Wait zero crossing must not resume coroutine");
    player.frame(0.0f);
    expect(player.state_machine().state() == 0 && player.state().auto_jump && player.state().speed.y == -120.0f,
           "Exit must retain upward 160*.75 and AutoJump");
}

void all_directions_parameterized() {
    for (int x : {-1, 0, 1}) for (int y : {-1, 0, 1}) {
        PlayerWorld world; Player player(world);
        player.frame(0.0f, dash(x, y)); player.frame(0.05f); player.frame(0.0f, dash(x, y));
        const float scale = x && y ? 1.0f / std::sqrt(2.0f) : 1.0f;
        expect(player.state().speed.x == (x == 0 && y == 0 ? 240.0f : float(x) * scale * 240.0f) &&
               player.state().speed.y == float(y) * scale * 240.0f, "Digital 8-way/default-facing launch");
    }
}
}

int main() {
    try {
        entry(); freeze_crossing_updates_both_buttons(); release_inside_freeze_clears_buffer();
        aim_is_independent_and_launch_is_delayed(); wait_crossing_consumes_tick(); all_directions_parameterized();
        std::cout << "PASS: bounded dash entry/clock/aim/wait\n";
        return 0;
    } catch (const std::exception& error) {
        std::cerr << error.what() << '\n';
        return 1;
    }
}
