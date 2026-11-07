#include "movement.hpp"

#include <cfenv>
#include <cmath>
#include <cstring>
#include <iostream>
#include <limits>
#include <stdexcept>
#include <string>

using namespace celeste;

namespace {

void expect(bool condition, const std::string& message) {
    if (!condition) throw std::runtime_error(message);
}

template<typename Exception, typename Action>
void expect_throws(Action action) {
    try { action(); }
    catch (const Exception&) { return; }
    throw std::runtime_error("Expected exception was not thrown");
}

void rounding_ties_parameterized() {
    struct Example { float value; std::int32_t expected; };
    for (const auto example : {Example{0.5f, 0}, {-0.5f, 0}, {1.5f, 2}, {-1.5f, -2},
                               {2.5f, 2}, {-2.5f, -2}, {3.5f, 4}, {-3.5f, -4}}) {
        expect(round_to_even(example.value) == example.expected, "Incorrect ties-to-even rounding");
    }
}

void rounding_neighbors_parameterized() {
    struct Example { float value; std::int32_t expected; };
    for (const auto example : {Example{std::nextafter(0.5f, 0.0f), 0},
                               {std::nextafter(0.5f, 1.0f), 1},
                               {std::nextafter(-0.5f, 0.0f), 0},
                               {std::nextafter(-0.5f, -1.0f), -1},
                               {2147483520.0f, 2147483520}, {-2147483648.0f, INT32_MIN}}) {
        expect(round_to_even(example.value) == example.expected, "Incorrect promoted-float rounding");
    }
}

void rounding_invalid_parameterized() {
    for (float value : {std::numeric_limits<float>::infinity(), -std::numeric_limits<float>::infinity(),
                        std::numeric_limits<float>::quiet_NaN(), 2147483648.0f, -2147483904.0f}) {
        expect_throws<std::invalid_argument>([&] { round_to_even(value); });
    }
}

void rounding_does_not_use_ambient_tie_mode() {
    const int previous = std::fegetround();
    expect(std::fesetround(FE_UPWARD) == 0, "Cannot set rounding mode");
    try { expect(round_to_even(-1.5f) == -2, "Rounding depends on ambient mode"); }
    catch (...) { std::fesetround(previous); throw; }
    expect(std::fesetround(previous) == 0, "Cannot restore rounding mode");
}

void strict_edges_and_negative_offsets_parameterized() {
    Body query{{-10.0f, -10.0f}, Hitbox{2.0f, 3.0f, {-4.0f, -5.0f}}};
    Body target{{-12.0f, -15.0f}, Hitbox{2.0f, 3.0f}};
    struct Example { Vec2 at; bool expected; };
    for (const auto example : {Example{{-10.0f, -10.0f}, false}, {{-9.75f, -10.0f}, true},
                               {{-9.75f, -7.0f}, false}, {{-9.75f, -7.25f}, true}}) {
        expect(collide_check(query, target, example.at) == example.expected, "Incorrect strict hitbox edges");
    }
}

void hitbox_edge_grouping() {
    Body query{{-16777216.0f, 0.0f}, Hitbox{1.0f, 1.0f, {16777216.0f, 0.0f}}};
    Body target{{0.0f, 0.0f}, Hitbox{1.0f, 1.0f}};
    expect(!collide_check(query, target, query.position), "Right edge must use (offset + width) + position");
}

void zero_width_source_behavior() {
    Body query{{0.5f, 0.0f}, Hitbox{0.0f, 1.0f}};
    Body target{{0.0f, 0.0f}, Hitbox{1.0f, 1.0f}};
    expect(collide_check(query, target, query.position), "Do not add a non-source empty-box optimization");
}

void ordered_first_hit_parameterized() {
    Body query{{}, Hitbox{1.0f, 1.0f}};
    Body first{{1.0f, 0.0f}, Hitbox{1.0f, 1.0f}};
    Body second = first;
    for (bool reverse : {false, true}) {
        StaticWorld world;
        world.solids = reverse ? std::vector<Body*>{&second, &first} : std::vector<Body*>{&first, &second};
        expect(world.first_solid(query, {1.0f, 0.0f}) == (reverse ? &second : &first), "First hit lost world order");
    }
}

void collision_exclusions_parameterized() {
    for (int exclusion : {0, 1, 2, 3}) {
        Body query{{}, Hitbox{1.0f, 1.0f}};
        Body target = query;
        Body* candidate = &target;
        if (exclusion == 0) candidate = &query;
        if (exclusion == 1) target.collider.reset();
        if (exclusion == 2) query.collider.reset();
        if (exclusion == 3) target.collidable = false;
        expect(!collide_check(query, *candidate, {}), "An excluded body collided");
    }
}

void querying_body_may_be_noncollidable() {
    Body query{{}, Hitbox{1.0f, 1.0f}, false};
    Body target{{}, Hitbox{1.0f, 1.0f}};
    expect(collide_check(query, target, {}), "Querying Collidable flag must not exclude collisions");
}

void queries_preserve_position() {
    Body query{{-2.0f, -3.0f}, Hitbox{1.0f, 1.0f}};
    Body target{{2.0f, 3.0f}, Hitbox{1.0f, 1.0f}};
    StaticWorld world{{&target}, {&target}};
    expect(world.first_solid(query, target.position) == &target, "Missing proposed-position hit");
    expect(query.position.x == -2.0f && query.position.y == -3.0f, "Query changed current position");
}

void outside_excludes_only_currently_overlapping_target() {
    Body query{{0.0f, 1.5f}, Hitbox{1.0f, 1.0f}};
    Body overlapping{{0.0f, 1.0f}, Hitbox{1.0f, 2.0f}};
    Body outside{{0.0f, 2.5f}, Hitbox{1.0f, 1.0f}};
    StaticWorld world{{}, {&overlapping, &outside}};
    expect(world.first_outside_jump_thru(query, {0.0f, 2.5f}) == &outside, "Outside must test each target separately");
}

void invalid_geometry_parameterized() {
    for (int invalid : {0, 1, 2, 3, 4}) {
        Body query{{}, Hitbox{1.0f, 1.0f}};
        Body target = query;
        if (invalid == 0) target.position.x = std::numeric_limits<float>::quiet_NaN();
        if (invalid == 1) target.collider->width = -1.0f;
        if (invalid == 2) target.collider->height = std::numeric_limits<float>::infinity();
        if (invalid == 3) target.collider->offset.x = std::numeric_limits<float>::infinity();
        if (invalid == 4) {
            target.collider->offset.x = std::numeric_limits<float>::max();
            target.collider->width = std::numeric_limits<float>::max();
        }
        expect_throws<std::invalid_argument>([&] { collide_check(query, target, {}); });
    }
}

void null_world_entry_is_rejected() {
    Body query{{}, Hitbox{1.0f, 1.0f}};
    StaticWorld world{{nullptr}, {}};
    expect_throws<std::invalid_argument>([&] { world.first_solid(query, {}); });
}

void invalid_proposed_edges_are_rejected_without_candidates() {
    const float large = std::numeric_limits<float>::max();
    Body query{{-large, 0.0f}, Hitbox{0.0f, 1.0f, {large, 0.0f}}};
    StaticWorld world;
    expect_throws<std::invalid_argument>([&] { world.first_solid(query, {large, 0.0f}); });
}

std::uint32_t bits(float value) {
    std::uint32_t result;
    std::memcpy(&result, &value, sizeof(result));
    return result;
}

void expect_vector(Vec2 actual, Vec2 expected, const std::string& message) {
    expect(bits(actual.x) == bits(expected.x) && bits(actual.y) == bits(expected.y), message);
}

void movement_ties_parameterized() {
    struct Example { float amount; float position; float remainder; };
    for (const auto example : {Example{0.5f, 0.0f, 0.5f}, {-0.5f, 0.0f, -0.5f},
                               {1.5f, 2.0f, -0.5f}, {-1.5f, -2.0f, 0.5f}}) {
        for (bool horizontal : {true, false}) {
            StaticWorld world;
            Actor actor(world, {}, Hitbox{1.0f, 1.0f});
            bool hit = horizontal ? actor.move_h(example.amount) : actor.move_v(example.amount);
            expect(!hit, "Free fractional movement returned a collision");
            expect_vector(actor.body.position, horizontal ? Vec2{example.position, 0.0f} : Vec2{0.0f, example.position}, "Tie position");
            expect_vector(actor.position_remainder(), horizontal ? Vec2{example.remainder, 0.0f} : Vec2{0.0f, example.remainder}, "Tie remainder");
        }
    }
}

void fractions_accumulate_as_float32() {
    StaticWorld world;
    Actor actor(world);
    for (int i = 0; i < 6; ++i) actor.move_h(0.1f);
    expect(bits(actor.position_remainder().x) == 0xbecccccc, "Fractional additions were regrouped or promoted");
    expect_vector(actor.body.position, {1.0f, 0.0f}, "Accumulated fractional position");
}

void signed_remainder_reverses() {
    StaticWorld world;
    Actor actor(world);
    actor.move_h(0.75f);
    actor.move_h(-0.5f);
    expect_vector(actor.body.position, {}, "Reversal position");
    expect_vector(actor.position_remainder(), {0.25f, 0.0f}, "Reversal remainder");
}

void exact_moves_preserve_remainders_parameterized() {
    for (bool horizontal : {true, false}) {
        StaticWorld world;
        Actor actor(world);
        if (horizontal) { actor.move_h(0.25f); actor.move_h_exact(-2); actor.move_h_exact(0); }
        else { actor.move_v(-0.25f); actor.move_v_exact(2); actor.move_v_exact(0); }
        expect_vector(actor.position_remainder(), horizontal ? Vec2{0.25f, 0.0f} : Vec2{0.0f, -0.25f}, "Exact moved remainder");
    }
}

void partial_travel_callback_payload_parameterized() {
    for (bool horizontal : {true, false}) {
        Body obstacle{horizontal ? Vec2{2.0f, 0.0f} : Vec2{0.0f, 2.0f}, Hitbox{1.0f, 1.0f}};
        Body pusher{{100.0f, 100.0f}, Hitbox{1.0f, 1.0f}};
        StaticWorld world{{&obstacle}, {}};
        Actor actor(world, {}, Hitbox{1.0f, 1.0f});
        int calls = 0;
        Collision callback = [&](CollisionData data) {
            ++calls;
            expect(data.hit == &obstacle && data.pusher == &pusher, "Callback identity");
            expect_vector(data.direction, horizontal ? Vec2{1.0f, 0.0f} : Vec2{0.0f, 1.0f}, "Callback direction");
            expect_vector(data.moved, data.direction, "Callback moved amount");
            expect_vector(data.target_position, horizontal ? Vec2{4.0f, 0.0f} : Vec2{0.0f, 4.0f}, "Callback original intended position");
            expect_vector(actor.body.position, data.moved, "Query position not restored before callback");
            expect_vector(actor.position_remainder(), {}, "Remainder was not cleared before callback");
        };
        bool hit = horizontal ? actor.move_h(4.25f, callback, &pusher) : actor.move_v(4.25f, callback, &pusher);
        expect(hit && calls == 1, "Collision return or callback count");
    }
}

void negative_payload_keeps_signed_zero() {
    Body obstacle{{1.0f, 0.0f}, Hitbox{1.0f, 1.0f}};
    StaticWorld world{{&obstacle}, {}};
    Actor actor(world, {4.0f, 0.0f}, Hitbox{1.0f, 1.0f});
    bool called = false;
    actor.move_h(-4.25f, [&](CollisionData data) {
        called = true;
        expect_vector(data.direction, {-1.0f, -0.0f}, "Negative direction zero sign");
        expect_vector(data.moved, {-2.0f, -0.0f}, "Negative moved zero sign");
        expect_vector(data.target_position, {}, "Negative target");
    });
    expect(called, "Negative collision callback missing");
}

void callback_mutation_is_not_restored_parameterized() {
    for (bool horizontal : {true, false}) {
        Body obstacle{horizontal ? Vec2{2.0f, 0.0f} : Vec2{0.0f, 2.0f}, Hitbox{1.0f, 1.0f}};
        StaticWorld world{{&obstacle}, {}};
        Actor actor(world, {}, Hitbox{1.0f, 1.0f});
        Collision callback = [&](CollisionData) {
            actor.body.position = {-7.0f, 9.0f};
            actor.move_h(0.25f);
            actor.move_v(-0.25f);
        };
        if (horizontal) actor.move_h(4.25f, callback); else actor.move_v(4.25f, callback);
        expect_vector(actor.body.position, {-7.0f, 9.0f}, "Callback position mutation was overwritten");
        expect_vector(actor.position_remainder(), {0.25f, -0.25f}, "Callback remainder mutation was overwritten");
    }
}

void callback_reentry_keeps_nested_remainder() {
    Body obstacle{{2.0f, 0.0f}, Hitbox{1.0f, 1.0f}};
    StaticWorld world{{&obstacle}, {}};
    Actor actor(world, {}, Hitbox{1.0f, 1.0f});
    bool nested_hit = true;
    actor.move_h(4.25f, [&](CollisionData data) {
        data.hit->collidable = false;
        nested_hit = actor.move_h(1.25f);
    });
    expect(!nested_hit, "Reentrant move did not observe target mutation");
    expect_vector(actor.body.position, {2.0f, 0.0f}, "Reentrant position lost");
    expect_vector(actor.position_remainder(), {0.25f, 0.0f}, "Reentrant remainder lost");
}

void reentrant_collision_order() {
    Body first{{2.0f, 0.0f}, Hitbox{1.0f, 1.0f}};
    Body second = first;
    StaticWorld world{{&first, &second}, {}};
    Actor actor(world, {}, Hitbox{1.0f, 1.0f});
    std::vector<Body*> hits;
    actor.move_h(4.25f, [&](CollisionData data) {
        hits.push_back(data.hit);
        data.hit->collidable = false;
        expect(actor.move_h(1.25f, [&](CollisionData nested) {
            hits.push_back(nested.hit);
            expect_vector(nested.target_position, {2.0f, 0.0f}, "Nested intended target");
            expect_vector(nested.moved, {}, "Nested moved distance");
        }), "Nested collision return");
        expect_vector(data.target_position, {4.0f, 0.0f}, "Outer payload mutated by reentry");
    });
    expect(hits == std::vector<Body*>{&first, &second}, "Nested callback order or identity");
}

void callback_exception_propagates_without_restoration() {
    Body obstacle{{1.0f, 0.0f}, Hitbox{1.0f, 1.0f}};
    StaticWorld world{{&obstacle}, {}};
    Actor actor(world, {}, Hitbox{1.0f, 1.0f});
    expect_throws<std::runtime_error>([&] {
        actor.move_h(2.25f, [&](CollisionData) {
            actor.body.position = {-5.0f, 0.0f};
            throw std::runtime_error("Synthetic callback failure");
        });
    });
    expect_vector(actor.body.position, {-5.0f, 0.0f}, "Exception restored callback position");
    expect_vector(actor.position_remainder(), {}, "Exception restored cleared remainder");
}

void collision_without_callback() {
    Body obstacle{{1.0f, 0.0f}, Hitbox{1.0f, 1.0f}};
    StaticWorld world{{&obstacle}, {}};
    Actor actor(world, {}, Hitbox{1.0f, 1.0f});
    expect(actor.move_h(2.25f), "Collision requires a callback");
    expect_vector(actor.position_remainder(), {}, "No-callback collision kept remainder");
}

void one_way_motion_parameterized() {
    struct Example { Vec2 start; int amount; bool ignore; bool expected_hit; float expected_y; };
    for (const auto example : {Example{{0.0f, 3.0f}, -4, false, false, -1.0f},
                               {{0.0f, -1.0f}, 4, false, true, 0.0f},
                               {{0.0f, -1.0f}, 4, true, false, 3.0f},
                               {{0.0f, 1.5f}, 3, false, false, 4.5f}}) {
        Body platform{{0.0f, 1.0f}, Hitbox{3.0f, 2.0f}};
        StaticWorld world{{}, {&platform}};
        Actor actor(world, example.start, Hitbox{1.0f, 1.0f});
        actor.ignore_jump_thrus = example.ignore;
        expect(actor.move_v_exact(example.amount) == example.expected_hit, "One-way return");
        expect_vector(actor.body.position, {0.0f, example.expected_y}, "One-way position");
    }
}

void solids_precede_jump_thrus() {
    Body solid{{0.0f, 1.0f}, Hitbox{3.0f, 1.0f}};
    Body jump = solid;
    StaticWorld world{{&solid}, {&jump}};
    Actor actor(world, {}, Hitbox{1.0f, 1.0f});
    Body* hit = nullptr;
    actor.move_v_exact(2, [&](CollisionData data) { hit = data.hit; });
    expect(hit == &solid, "JumpThru took precedence over Solid");
}

void horizontal_ignores_jump_thrus() {
    Body platform{{0.0f, 1.0f}, Hitbox{1.0f, 1.0f}};
    StaticWorld world{{}, {&platform}};
    Actor actor(world, {-2.0f, 1.0f}, Hitbox{1.0f, 1.0f});
    expect(!actor.move_h_exact(4), "JumpThru blocks horizontal movement");
    expect_vector(actor.body.position, {2.0f, 1.0f}, "Horizontal one-way pass");
}

void horizontal_before_vertical_step() {
    Body wall{{2.0f, 0.0f}, Hitbox{1.0f, 1.0f}};
    Body floor{{1.0f, 2.0f}, Hitbox{1.0f, 1.0f}};
    StaticWorld world{{&wall, &floor}, {}};
    Actor actor(world, {}, Hitbox{1.0f, 1.0f});
    std::vector<Body*> hits;
    Collision callback = [&](CollisionData data) { hits.push_back(data.hit); };
    actor.move_h(3.25f, callback);
    actor.move_v(3.25f, callback);
    expect(hits == std::vector<Body*>{&wall, &floor}, "Combined step must execute H before V");
    expect_vector(actor.body.position, {1.0f, 1.0f}, "H/V corner position");
}

void invalid_movement_is_rejected_before_mutation_parameterized() {
    for (float invalid : {std::numeric_limits<float>::quiet_NaN(), std::numeric_limits<float>::infinity(), 2147483648.0f}) {
        StaticWorld world;
        Actor actor(world);
        actor.move_h(0.25f);
        expect_throws<std::invalid_argument>([&] { actor.move_h(invalid); });
        expect_vector(actor.position_remainder(), {0.25f, 0.0f}, "Invalid input mutated remainder");
        expect_vector(actor.body.position, {}, "Invalid input mutated position");
    }
}

void invalid_actor_position_is_rejected() {
    StaticWorld world;
    Actor actor(world);
    actor.body.position.x = std::numeric_limits<float>::quiet_NaN();
    expect_throws<std::invalid_argument>([&] { actor.move_h_exact(0); });
}

}

int main() {
    struct Test { const char* name; void (*run)(); };
    const Test tests[] = {
        {"rounding_ties_parameterized", rounding_ties_parameterized},
        {"rounding_neighbors_parameterized", rounding_neighbors_parameterized},
        {"rounding_invalid_parameterized", rounding_invalid_parameterized},
        {"rounding_does_not_use_ambient_tie_mode", rounding_does_not_use_ambient_tie_mode},
        {"strict_edges_and_negative_offsets_parameterized", strict_edges_and_negative_offsets_parameterized},
        {"hitbox_edge_grouping", hitbox_edge_grouping},
        {"zero_width_source_behavior", zero_width_source_behavior},
        {"ordered_first_hit_parameterized", ordered_first_hit_parameterized},
        {"collision_exclusions_parameterized", collision_exclusions_parameterized},
        {"querying_body_may_be_noncollidable", querying_body_may_be_noncollidable},
        {"queries_preserve_position", queries_preserve_position},
        {"outside_excludes_only_currently_overlapping_target", outside_excludes_only_currently_overlapping_target},
        {"invalid_geometry_parameterized", invalid_geometry_parameterized},
        {"null_world_entry_is_rejected", null_world_entry_is_rejected},
        {"invalid_proposed_edges_are_rejected_without_candidates", invalid_proposed_edges_are_rejected_without_candidates},
        {"movement_ties_parameterized", movement_ties_parameterized},
        {"fractions_accumulate_as_float32", fractions_accumulate_as_float32},
        {"signed_remainder_reverses", signed_remainder_reverses},
        {"exact_moves_preserve_remainders_parameterized", exact_moves_preserve_remainders_parameterized},
        {"partial_travel_callback_payload_parameterized", partial_travel_callback_payload_parameterized},
        {"negative_payload_keeps_signed_zero", negative_payload_keeps_signed_zero},
        {"callback_mutation_is_not_restored_parameterized", callback_mutation_is_not_restored_parameterized},
        {"callback_reentry_keeps_nested_remainder", callback_reentry_keeps_nested_remainder},
        {"reentrant_collision_order", reentrant_collision_order},
        {"callback_exception_propagates_without_restoration", callback_exception_propagates_without_restoration},
        {"collision_without_callback", collision_without_callback},
        {"one_way_motion_parameterized", one_way_motion_parameterized},
        {"solids_precede_jump_thrus", solids_precede_jump_thrus},
        {"horizontal_ignores_jump_thrus", horizontal_ignores_jump_thrus},
        {"horizontal_before_vertical_step", horizontal_before_vertical_step},
        {"invalid_movement_is_rejected_before_mutation_parameterized", invalid_movement_is_rejected_before_mutation_parameterized},
        {"invalid_actor_position_is_rejected", invalid_actor_position_is_rejected},
    };
    int failures = 0;
    for (const auto& test : tests) {
        try { test.run(); std::cout << "PASS " << test.name << '\n'; }
        catch (const std::exception& error) { ++failures; std::cerr << "FAIL " << test.name << ": " << error.what() << '\n'; }
    }
    return failures == 0 ? 0 : 1;
}
