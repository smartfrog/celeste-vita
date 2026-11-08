#include "movement.hpp"
#include "player.hpp"

#include <cmath>
#include <iostream>
#include <limits>
#include <stdexcept>
#include <string>

using namespace celeste;

namespace {
void expect(bool value, const std::string& message) {
    if (!value) throw std::runtime_error(message);
}
template<typename Action> void rejects(Action action) {
    try { action(); } catch (const std::invalid_argument&) { return; }
    throw std::runtime_error("Expected invalid_argument");
}

void strict_tile_edges_parameterized() {
    const TileGrid grid(1, 1, {1});
    const Body target{{}, {}, true, &grid};
    const Body query{{}, Hitbox{1, 1}};
    struct Example { Vec2 at; bool hit; };
    for (const auto e : {Example{{-1, 0}, false}, {{0, -1}, false}, {{8, 0}, false}, {{0, 8}, false},
                         {{-1, -1}, false}, {{7, 7}, true}, {{0, 0}, true}})
        expect(collide_check(query, target, e.at) == e.hit, "Incorrect strict tile boundary");
}

void negative_fraction_truncation_parameterized() {
    const TileGrid grid(1, 1, {1});
    const Body target{{-8, 0}, {}, true, &grid};
    const Body query{{}, Hitbox{1, 1}};
    for (float x : {-0.5f, -1.0f})
        expect(collide_check(query, target, {x, 0}) == (x == -1), "Bounds must truncate, not floor");
}

void composed_offsets() {
    const TileGrid grid(1, 1, {1}, 4, 6, {-3, 2});
    const Body target{{10, -10}, {}, true, &grid};
    const Body query{{}, Hitbox{2, 2, {-1, -1}}};
    expect(collide_check(query, target, {8, -7}), "Body and collider offsets must compose");
}

void sparse_chunk_boundary_parameterized() {
    std::vector<std::uint8_t> cells(51); cells[50] = 1;
    const TileGrid grid(51, 1, cells);
    const Body target{{}, {}, true, &grid};
    struct Example { float x, width; bool hit; };
    for (const auto e : {Example{392, 8, false}, {400, 8, true}, {407, 10, true}, {408, 8, false}, {-8, 8, false}}) {
        const Body query{{}, Hitbox{e.width, 1}};
        expect(collide_check(query, target, {e.x, 0}) == e.hit, "Sparse/clipped cell range mismatch");
    }
}

void fractional_and_empty_dimensions_parameterized() {
    const TileGrid grid(2, 2, {1, 1, 1, 1});
    const Body target{{}, {}, true, &grid};
    struct Example { float size; bool hit; };
    for (const auto e : {Example{0, true}, {0.9f, true}, {1.9f, true}}) {
        const Body query{{}, Hitbox{e.size, e.size}};
        expect(collide_check(query, target, {4.5f, 4.5f}) == e.hit, "Preserve source zero/fraction rectangle behavior");
    }
}

void empty_grids_parameterized() {
    for (int axis : {0, 1}) {
        const TileGrid grid(axis, 1 - axis, {});
        const Body target{{}, {}, true, &grid};
        const Body query{{}, Hitbox{2, 2}};
        expect(!collide_check(query, target, {-1, -1}), "Empty Grid must scan no cells");
    }
}

void checked_indexer_parameterized() {
    const TileGrid grid(1, 1, {1});
    for (const auto p : {Vec2{0, 0}, {-1, 0}, {1, 0}, {0, -1}, {0, 1}})
        expect(grid.at(static_cast<int>(p.x), static_cast<int>(p.y)) == (p.x == 0 && p.y == 0), "Checked indexer mismatch");
}

void invalid_storage_parameterized() {
    for (int kind = 0; kind < 8; ++kind) rejects([&] {
        const float nan = std::numeric_limits<float>::quiet_NaN();
        if (kind == 0) TileGrid(-1, 1, {});
        if (kind == 1) TileGrid(2, 2, {1});
        if (kind == 2) TileGrid(1, 1, {2});
        if (kind == 3) TileGrid(1, 1, {1}, 0);
        if (kind == 4) TileGrid(1, 1, {1}, 8, nan);
        if (kind == 5) TileGrid(1, 1, {1}, 8, 8, {nan, 0});
        if (kind == 6) TileGrid(2, 1, {1, 1}, std::numeric_limits<float>::max());
        if (kind == 7) TileGrid(INT32_MAX, INT32_MAX, {});
    });
}

void invalid_body_shapes_parameterized() {
    const TileGrid grid(1, 1, {1});
    for (bool query_grid : {false, true}) {
        Body query{{}, Hitbox{1, 1}};
        Body target{{}, {}, true, &grid};
        if (query_grid) query.grid = &grid;
        else target.collider = Hitbox{1, 1};
        rejects([&] { collide_check(query, target, {}); });
    }
}

void grid_query_is_not_supported() {
    const TileGrid grid(1, 1, {1});
    const Body query{{}, {}, true, &grid};
    const Body target{{}, Hitbox{1, 1}};
    rejects([&] { collide_check(query, target, {}); });
}

void unsafe_integer_math_parameterized() {
    const TileGrid grid(1, 1, {1});
    for (int kind = 0; kind < 6; ++kind) {
        Body target{{}, {}, true, &grid};
        Body query{{}, Hitbox{1, 1}};
        Vec2 at{};
        if (kind == 0) at.x = 2147483648.0f;
        if (kind == 1) target.position.y = 2147483648.0f;
        if (kind == 2) query.collider->width = 2147483648.0f;
        if (kind == 3) { at.x = 2147483520.0f; query.collider->width = 256; }
        if (kind == 4) target.position.x = std::numeric_limits<float>::infinity();
        if (kind == 5) at.x = std::numeric_limits<float>::quiet_NaN();
        rejects([&] { collide_check(query, target, at); });
    }
}

void cell_range_overflow_is_rejected() {
    const TileGrid grid(1, 1, {1}, 1.0e-30f, 1.0e-30f);
    const Body target{{}, {}, true, &grid};
    const Body query{{}, Hitbox{2, 2}};
    rejects([&] { collide_check(query, target, {-1, -1}); });
}

void actor_grid_query_is_rejected_before_subpixel_accumulation() {
    const TileGrid grid(1, 1, {1});
    const StaticWorld world;
    Actor actor(world);
    actor.body.grid = &grid;
    rejects([&] { actor.move_h(0.25f); });
    expect(actor.position_remainder().x == 0, "Invalid query mutated remainder");
}

void actor_grid_collision_parameterized() {
    const TileGrid grid(1, 1, {1});
    for (bool horizontal : {false, true}) {
        Body target{{2, 2}, {}, true, &grid};
        StaticWorld world{{&target}, {}};
        Actor actor(world, horizontal ? Vec2{0, 2} : Vec2{2, 0}, Hitbox{1, 1});
        Body* hit = nullptr;
        const auto callback = [&](CollisionData d) { hit = d.hit; };
        if (horizontal) actor.move_h(0.25f); else actor.move_v(0.25f);
        const bool blocked = horizontal ? actor.move_h(3, callback) : actor.move_v(3, callback);
        expect(blocked && hit == &target, "Actor callback lost Grid body identity");
        expect((horizontal ? actor.body.position.x : actor.body.position.y) == 1, "Actor Grid travel mismatch");
        expect((horizontal ? actor.position_remainder().x : actor.position_remainder().y) == 0, "Blocked remainder not cleared");
    }
}

void ordered_mixed_targets_parameterized() {
    const TileGrid grid(1, 1, {1});
    Body tiled{{}, {}, true, &grid};
    Body boxed{{}, Hitbox{8, 8}};
    const Body query{{}, Hitbox{1, 1}};
    for (bool reverse : {false, true}) {
        StaticWorld world{reverse ? std::vector<Body*>{&tiled, &boxed} : std::vector<Body*>{&boxed, &tiled}, {}};
        expect(world.first_solid(query, {}) == (reverse ? &tiled : &boxed), "Mixed world order changed");
    }
}

void player_ground_movement_on_grid() {
    const TileGrid grid(10, 1, std::vector<std::uint8_t>(10, 1));
    Body target{{-16, 144}, {}, true, &grid};
    PlayerWorld world{{{&target}, {}}, {&target}};
    Player player(world, {19, 144});
    PlayerInput input; input.x = 1;
    for (int i = 0; i < 10; ++i) player.frame(1.0f / 60.0f, input);
    expect(player.state().on_ground && player.state().on_safe_ground, "Grid safe-ground identity lost");
    expect(player.actor().body.position.x > 19 && player.actor().body.position.y == 144, "Player did not walk on Grid");
}
}

int main() {
    try {
        strict_tile_edges_parameterized(); negative_fraction_truncation_parameterized(); composed_offsets();
        sparse_chunk_boundary_parameterized(); fractional_and_empty_dimensions_parameterized(); empty_grids_parameterized();
        checked_indexer_parameterized(); invalid_storage_parameterized(); invalid_body_shapes_parameterized(); grid_query_is_not_supported();
        unsafe_integer_math_parameterized(); cell_range_overflow_is_rejected(); actor_grid_query_is_rejected_before_subpixel_accumulation();
        actor_grid_collision_parameterized(); ordered_mixed_targets_parameterized(); player_ground_movement_on_grid();
        std::cout << "Grid unit tests passed\n";
        return 0;
    } catch (const std::exception& error) { std::cerr << error.what() << '\n'; return 1; }
}
