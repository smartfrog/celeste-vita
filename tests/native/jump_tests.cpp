#include "player.hpp"

#include <iostream>
#include <stdexcept>

using namespace celeste;

namespace {
void expect(bool condition, const char* message) { if (!condition) throw std::runtime_error(message); }
PlayerInput dash(int x, int y, int move = 0, bool duck = false) {
    PlayerInput input;
    input.x = move; input.y = duck ? 1 : 0;
    input.aim_x = x; input.aim_y = y; input.dash_button = {true, true};
    return input;
}
void buffered_prelaunch_super_parameterized() {
    for (int facing : {-1, 1}) for (bool duck : {false, true}) {
        Body floor{{-1000.0f, 0.0f}, Hitbox{2000.0f, 8.0f, {}}, true};
        PlayerWorld world{{{&floor}, {}}, {&floor}};
        Player player(world);
        player.frame(0.0f, dash(facing, 0, facing, duck));
        PlayerInput jump; jump.jump = {true, true};
        player.frame(0.05f, jump);
        jump.jump.pressed = false;
        player.frame(0.0f, jump);
        expect(player.state_machine().state() == 0 && !player.state_machine().coroutine().active, "Super jump cancels Dash coroutine");
        expect(player.state().speed.x == float(facing) * (duck ? 325.0f : 260.0f) && player.state().speed.y == (duck ? -52.5f : -105.0f), "Super launch speed");
        expect(player.state().launched && !player.state().ducking && player.state().var_jump_timer == 0.2f, "Super jump bookkeeping");
        expect(player.jump_button().buffer_counter() == 0.0f && player.state().dash_attack_timer == 0.0f, "Super consumes buffer/attack");
    }
}
void up_dash_wall_bounce() {
    Body wall{{8.0f, -200.0f}, Hitbox{8.0f, 200.0f, {}}, true};
    PlayerWorld world{{{&wall}, {}}, {&wall}};
    Player player(world, {0.0f, -100.0f});
    player.frame(0.0f, dash(0, -1)); player.frame(0.05f);
    PlayerInput up; up.aim_y = -1;
    player.frame(0.0f, up);
    up.jump = {true, true}; player.frame(0.0f, up);
    expect(player.state_machine().state() == 0 && player.state().speed.x == -170.0f && player.state().speed.y == -160.0f, "Upward dash uses five-pixel SuperWallJump reach");
    expect(player.state().var_jump_timer == 0.25f && player.state().launched, "SuperWallJump bookkeeping");
}
}
int main() {
    try {
        buffered_prelaunch_super_parameterized(); up_dash_wall_bounce();
        std::cout << "PASS: bounded jump family\n";
        return 0;
    } catch (const std::exception& error) { std::cerr << error.what() << '\n'; return 1; }
}
