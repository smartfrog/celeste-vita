#include "player.hpp"

#include <iostream>
#include <limits>
#include <stdexcept>
#include <string>

using namespace celeste;

namespace {

void expect(bool condition, const char* message) {
    if (!condition) throw std::runtime_error(message);
}

void up_hurtbox_bottom_parameterized() {
    for (int y : {2, 3}) {
        StaticSpike spike({-8, 0}, 16, SpikeDirection::up);
        PlayerWorld world;
        world.spikes = {&spike};
        Player player(world, {0, static_cast<float>(y)});
        player.frame(0);
        expect(player.death().dead == (y == 2), "Up predicate must use hurtbox bottom, not position or movement bottom");
    }
}

void spike_velocity_parameterized() {
    for (auto direction : {SpikeDirection::up, SpikeDirection::left}) {
        for (float speed : {-1.0f, 0.0f, 1.0f}) {
            StaticSpike spike(direction == SpikeDirection::up ? Vec2{-8, 0} : Vec2{4, -8}, 16, direction);
            PlayerWorld world;
            world.spikes = {&spike};
            Player p(world, {0, 2}, direction == SpikeDirection::up ? Vec2{0, speed} : Vec2{speed, 0});
            p.frame(0);
            expect(p.death().dead == (speed >= 0), "Zero qualifies; negative approach velocity must not kill");
        }
    }
}

void strict_edge_parameterized() {
    for (int x : {6, 7}) {
        StaticSpike spike({static_cast<float>(x), -8}, 16, SpikeDirection::left);
        PlayerWorld world;
        world.spikes = {&spike};
        Player p(world);
        p.frame(0);
        expect(p.death().dead == (x == 6), "Strict edge touch differs from one-pixel overlap");
    }
}

void noncollidable_spike_does_not_kill() {
    StaticSpike spike({4, -8}, 16, SpikeDirection::left, false);
    PlayerWorld world;
    world.spikes = {&spike};
    Player p(world);
    p.frame(0);
    expect(!p.death().dead && p.hazard_frame().overlaps.empty(), "PlayerCollider must respect target collidability");
}

void nonlethal_overlap_continues_in_order() {
    StaticSpike first({-8, 0}, 16, SpikeDirection::up);
    StaticSpike second({4, -8}, 16, SpikeDirection::left);
    StaticSpike third({4, -8}, 16, SpikeDirection::left);
    PlayerWorld world;
    world.spikes = {&first, &second, &third};
    Player p(world, {0, 2}, {0, -1});
    p.frame(0);
    expect(p.hazard_frame().checked == std::vector<std::size_t>{0, 1} &&
           p.hazard_frame().overlaps == std::vector<std::size_t>{0, 1}, "Continue after nonlethal overlap, stop after lethal second");
    expect(p.death().direction.x == -1, "Second overlap supplies death direction");
}

void movement_overlap_denies_refill_without_hurt() {
    Body floor{{-100, 0}, Hitbox{200, 8, {}}, true};
    StaticSpike spike({4, -1}, 1, SpikeDirection::left);
    PlayerWorld world{{{&floor}, {}}, {&floor}};
    world.spikes = {&spike};
    Player p(world);
    p.frame(0);
    expect(p.state().on_ground && p.hazard_frame().refill_checked && !p.hazard_frame().refill_called, "Movement overlap denies grounded refill call");
    expect(!p.death().dead && p.hazard_frame().overlaps.empty(), "Smaller hurtbox must miss movement-only overlap");
    expect(p.state().dashes == 1 && p.state().stamina == 110, "No invented depleted-state setup");
}

void grounded_clear_calls_refill() {
    Body floor{{-100, 0}, Hitbox{200, 8, {}}, true};
    PlayerWorld world{{{&floor}, {}}, {&floor}};
    Player p(world);
    p.frame(0);
    expect(p.hazard_frame().refill_called, "Clear grounded movement box calls RefillDash even when already full");
}

void duck_hurtbox_parameterized() {
    for (int y : {-10, -5, -2}) {
        Body floor{{-100, 0}, Hitbox{200, 8, {}}, true};
        StaticSpike spike({4, static_cast<float>(y)}, 1, SpikeDirection::left);
        PlayerWorld world{{{&floor}, {}}, {&floor}};
        world.spikes = {&spike};
        Player p(world);
        p.frame(0, {0, 1});
        expect(p.death().dead == (y == -5), "Duck hurtbox excludes standing top and movement bottom");
        expect(p.actor().body.collider->height == 6, "Duck movement collider restored on lethal and nonlethal paths");
    }
}

void ledge_boost_parameterized() {
    for (bool collidable : {false, true}) {
        Body platform{{-10, -4}, Hitbox{20, 8, {}}, true};
        StaticSpike spike({-8, -11}, 16, SpikeDirection::up, collidable);
        PlayerWorld world{{{}, {&platform}}, {&platform}};
        world.spikes = {&spike};
        Player p(world, {}, {0, -30});
        p.frame(0.025f);
        expect(p.hazard_frame().boost_checked && p.hazard_frame().boost_blocked == collidable, "Ledge blocker probes movement collider two pixels up");
        expect(p.actor().body.position.y == (collidable ? 0 : -1) && !p.death().dead, "Blocking is independent of ascending nonlethal predicate");
    }
}

void immediate_die_preserves_source_effects() {
    PlayerWorld world;
    Player p(world, {}, {13, -17});
    expect(p.die({-1, 0}), "First death succeeds");
    expect(p.death().dead && p.death().removed && p.death().depth == -1000000, "Immediate death flags/depth/removal");
    expect(p.state().speed.x == 0 && p.state().speed.y == 0 && p.state_machine().locked && !p.actor().body.collidable, "Death zeroes speed, locks state and disables collision");
    expect(p.death().direction.x == -1 && p.death().direction.y == 0, "Death direction retained at corpse boundary");
    expect(p.death().events == std::vector<DeathEvent>{DeathEvent::corpse_created, DeathEvent::corpse_added, DeathEvent::player_removed}, "Corpse creation/add precedes player removal");
}

void repeated_die_is_idempotent() {
    PlayerWorld world;
    Player p(world);
    p.die({-1, 0});
    expect(!p.die({0, -1}) && p.death().events.size() == 3 && p.death().direction.x == -1, "Rejected repeated death has no new events or direction");
}

void removed_frame_is_rejected_before_input() {
    PlayerWorld world;
    Player p(world);
    p.die({0, -1});
    bool observed = false;
    try { p.frame(0, {1}, [&](const char*, const CollisionData*) { observed = true; }); }
    catch (const std::invalid_argument&) { expect(!observed && p.state().move_x == 0, "No post-removal frame phase or input mutation"); return; }
    throw std::runtime_error("Removed frame accepted");
}

void lethal_frame_restores_and_skips_complete() {
    Body floor{{-100, 0}, Hitbox{200, 8, {}}, true};
    StaticSpike spike({4, -8}, 16, SpikeDirection::left);
    PlayerWorld world{{{&floor}, {}}, {&floor}};
    world.spikes = {&spike};
    Player p(world);
    std::vector<std::string> phases;
    p.frame(0, {}, [&](const char* phase, const CollisionData*) { phases.emplace_back(phase); });
    expect(p.state().on_ground && !p.state().was_on_ground && p.actor().body.collider->height == 11, "Lethal return restores collider and omits wasOnGround");
    expect(phases.back() == "removed" && phases.size() == 9, "Only post-death instrumentation follows lethal return");
}

void invalid_spike_parameterized() {
    for (int kind : {0, 1, 2}) {
        try {
            StaticSpike spike(kind == 0 ? Vec2{std::numeric_limits<float>::infinity(), 0} : Vec2{},
                              kind == 1 ? 0 : 8, kind == 2 ? static_cast<SpikeDirection>(99) : SpikeDirection::up);
        } catch (const std::invalid_argument&) { continue; }
        throw std::runtime_error("Invalid static spike accepted");
    }
}

void invalid_world_spike_parameterized() {
    for (bool duplicate : {false, true}) {
        StaticSpike spike({}, 8, SpikeDirection::up);
        PlayerWorld world;
        world.spikes = duplicate ? std::vector<const StaticSpike*>{&spike, &spike} : std::vector<const StaticSpike*>{nullptr};
        try { Player p(world); }
        catch (const std::invalid_argument&) { continue; }
        throw std::runtime_error("Null/duplicate spike accepted");
    }
}

void observer_cannot_request_death() {
    PlayerWorld world;
    Player p(world);
    bool rejected = false;
    p.frame(0, {}, [&](const char*, const CollisionData*) {
        try { p.die({0, -1}); }
        catch (const std::logic_error&) { rejected = true; }
    });
    expect(rejected && !p.death().dead, "Observer must remain read-only");
}

void nonfinite_death_direction_rejected_before_mutation() {
    PlayerWorld world;
    Player p(world);
    try { p.die({std::numeric_limits<float>::quiet_NaN(), 0}); }
    catch (const std::invalid_argument&) { expect(!p.death().dead && p.death().events.empty(), "Invalid death command has no effects"); return; }
    throw std::runtime_error("Nonfinite death direction accepted");
}

}

int main() {
    try {
        up_hurtbox_bottom_parameterized();
        spike_velocity_parameterized(); strict_edge_parameterized(); noncollidable_spike_does_not_kill();
        nonlethal_overlap_continues_in_order(); movement_overlap_denies_refill_without_hurt(); grounded_clear_calls_refill();
        duck_hurtbox_parameterized(); ledge_boost_parameterized(); immediate_die_preserves_source_effects();
        repeated_die_is_idempotent(); removed_frame_is_rejected_before_input(); lethal_frame_restores_and_skips_complete();
        invalid_spike_parameterized(); invalid_world_spike_parameterized();
        observer_cannot_request_death(); nonfinite_death_direction_rejected_before_mutation();
    }
    catch (const std::exception& error) { std::cerr << error.what() << '\n'; return 1; }
    std::cout << "Hazard tests passed\n";
}
