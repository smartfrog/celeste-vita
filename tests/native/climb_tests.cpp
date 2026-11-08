#include "player.hpp"

#include <iostream>
#include <stdexcept>

using namespace celeste;

namespace {
void expect(bool condition, const char* message) {
    if (!condition) throw std::runtime_error(message);
}

void descending_grab_enters_climb() {
    Body wall{{4.0f, -100.0f}, Hitbox{8.0f, 200.0f, {}}, true};
    PlayerWorld world{{{&wall}, {}}, {}};
    Player player(world, {}, {0.0f, 50.0f});
    PlayerInput input;
    input.grab = true;
    player.frame(0.0f, input);
    expect(player.state_machine().state() == 1, "Descending held Grab must enter Climb");
    expect(player.state().speed.y == 10.0f, "ClimbBegin scales entry speed");
}

void point_hitbox_edges_parameterized() {
    Body wall{{-10.5f, -20.25f}, Hitbox{2.5f, 3.5f, {}}, true};
    StaticWorld world{{&wall}, {}};
    struct Probe { Vec2 point; bool hit; };
    for (const auto& probe : {Probe{{-10.5f, -20.25f}, true}, Probe{{-8.0f, -20.25f}, false},
                             Probe{{-10.5f, -16.75f}, false}, Probe{{-10.500001f, -20.25f}, false}})
        expect(world.solid_at_point(probe.point) == probe.hit, "Point Hitbox bounds must be half-open");
}

void point_grid_cells_parameterized() {
    TileGrid grid(2, 2, {1, 0, 0, 1}, 2.5f, 3.5f, {.25f, .5f});
    Body wall{{-10.5f, -20.25f}, {}, true, &grid};
    StaticWorld world{{&wall}, {}};
    struct Probe { Vec2 point; bool hit; };
    for (const auto& probe : {Probe{{-10.25f, -19.75f}, true}, Probe{{-7.75f, -19.75f}, false},
                             Probe{{-7.75f, -16.25f}, true}, Probe{{-5.25f, -16.25f}, false}, Probe{{-7.75f, -12.75f}, false}})
        expect(world.solid_at_point(probe.point) == probe.hit, "Point Grid bounds/cells must preserve negative-world fractional origins");
}

void disabled_grab_does_not_enter_climb() {
    Body wall{{4.0f, -100.0f}, Hitbox{8.0f, 200.0f, {}}, true};
    PlayerWorld world{{{&wall}, {}}, {}};
    Player player(world);
    PlayerInput input;
    input.grab = true;
    input.jump.disabled = true;
    player.frame(0.0f, input);
    expect(player.state_machine().state() == 0 && !player.grab_held(), "MInput disabled must gate held Grab");
}
}

int main() {
    try {
        descending_grab_enters_climb();
        point_hitbox_edges_parameterized();
        point_grid_cells_parameterized();
        disabled_grab_does_not_enter_climb();
    }
    catch (const std::exception& error) { std::cerr << error.what() << '\n'; return 1; }
    return 0;
}
