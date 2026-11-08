#include "player.hpp"

#include <cmath>
#include <iostream>
#include <limits>
#include <stdexcept>
#include <string>
#include <utility>

using namespace celeste;

namespace {

void expect(bool condition, const char* message) {
    if (!condition) throw std::runtime_error(message);
}

template<typename Action>
void invalid(Action action) {
    try { action(); }
    catch (const std::invalid_argument&) { return; }
    throw std::runtime_error("Expected invalid_argument");
}

struct Grounded {
    Body floor{{-1000.0f, 0.0f}, Hitbox{2000.0f, 8.0f, {}}, true};
    PlayerWorld world{{{&floor}, {}}, {&floor}};
};

PlayerInput press(int x = 0, int y = 0) { return {x, y, {true, true}}; }
PlayerInput held(int x = 0, int y = 0) { return {x, y, {true}}; }

void grounded_jump_consumes_buffer() {
    Grounded g;
    Player p(g.world);
    p.frame(1.0f / 60.0f, press(1));
    expect(p.state().speed.y == -105.0f && p.state().var_jump_timer == 0.2f, "Ground jump values");
    expect(p.state().jump_grace_timer == 0.0f, "Jump must clear coyote grace");
    expect(!p.jump_button().consumed() && p.jump_button().buffer_counter() == 0.0f && p.jump_button().pressed(), "Jump must consume buffer, not raw press");
}

void initialization_truncates_and_begins_normal() {
    PlayerWorld w;
    Player p(w, {-3.75f, 5.75f});
    expect(p.actor().body.position.x == -3.0f && p.actor().body.position.y == 5.0f, "Source spawn truncation");
    expect(p.state().previous_position.x == -3.0f && p.state().facing == 1, "Initial previous/facing");
    expect(p.state().max_fall == 160.0f && p.state_machine().state() == 0 && p.state_machine().previous_state() == -1, "NormalBegin lifecycle");
    expect(p.state().stamina == 110.0f && p.state().dashes == 1 && !p.state().launched, "Default inventory/invariants");
    expect(p.actor().body.collider->height == 11.0f && p.hurtbox().height == 9.0f && p.hurtbox().offset.y == -11.0f, "Standing collider identities");
}

void run_reverse() {
    Grounded g;
    Player p(g.world);
    p.frame(0.1f, {1});
    expect(p.state().speed.x == 90.0f, "Run speed");
    p.frame(0.1f, {-1});
    expect(p.state().speed.x == -10.0f && p.state().facing == -1, "Reverse acceleration/facing");
}

void jump_overspeed() {
    Grounded g;
    Player p(g.world, {}, {90.0f, 0.0f});
    p.frame(1.0f / 60.0f, press(1));
    expect(p.state().speed.x == 130.0f, "Jump adds horizontal overspeed");
    p.frame(1.0f / 60.0f, held(1));
    expect(p.state().speed.x == 130.0f - 400.0f * 0.65f * (1.0f / 60.0f), "Air overspeed uses reduction, not acceleration");
}

void coyote_expiry_parameterized() {
    for (float delta : {std::nextafter(0.1f, 0.0f), 0.1f, std::nextafter(0.1f, 1.0f)}) {
        Body floor{{-10.0f, 0.0f}, Hitbox{14.0f, 8.0f, {}}, true};
        PlayerWorld w{{{&floor}, {}}, {&floor}};
        Player p(w, {}, {90.0f, 0.0f});
        p.frame(0.1f, {1});
        p.frame(delta, press(1));
        expect((p.state().speed.y == -105.0f) == (delta < 0.1f), "Coyote must require strictly positive grace");
    }
}

void buffered_landing_uses_next_ground_snapshot() {
    Grounded g;
    Player p(g.world, {0.0f, -4.0f}, {0.0f, 120.0f});
    p.frame(1.0f / 60.0f, press());
    p.frame(1.0f / 60.0f, held());
    expect(p.actor().body.position.y == 0.0f && !p.state().on_ground && p.state().jump_grace_timer == 0.0f, "Landing must not immediately refresh grace");
    p.frame(1.0f / 60.0f, held());
    expect(p.state().speed.y == -105.0f && p.jump_button().buffer_counter() == 0.0f, "Held buffer must jump on next ground snapshot");
}

void release_clears_landing_buffer() {
    Grounded g;
    Player p(g.world, {0.0f, -4.0f}, {0.0f, 120.0f});
    p.frame(1.0f / 60.0f, press());
    p.frame(1.0f / 60.0f, {0, 0, {false, false, true}});
    p.frame(1.0f / 60.0f);
    expect(p.state().on_ground && p.state().speed.y == 0.0f && p.jump_button().buffer_counter() == 0.0f, "Released buffer must not jump after landing");
}

void held_released_apex_parameterized() {
    for (bool hold : {false, true}) {
        Grounded g;
        Player p(g.world);
        p.frame(0.1f, press());
        p.frame(0.1f, {0, 0, {hold, false, !hold}});
        if (hold) p.frame(0.1f, held());
        expect(p.state().speed.y == -15.0f, "Apex setup");
        p.frame(0.02f, {0, 0, {hold}});
        expect(p.state().speed.y == (hold ? -6.0f : 3.0f), "Held apex must use half gravity");
    }
}

void fastfall_entry_and_recovery() {
    PlayerWorld w;
    Player p(w, {0.0f, -100.0f}, {0.0f, 160.0f});
    p.frame(0.1f, {0, 1});
    expect(p.state().max_fall == 190.0f && p.state().speed.y == 190.0f, "Fastfall must approach max fall");
    p.frame(0.1f, {0, 1});
    p.frame(0.1f);
    expect(p.state().max_fall == 190.0f && p.state().speed.y == 190.0f, "Fastfall recovery must approach ordinary terminal speed");
}

void jumpthru_overlap_boost() {
    Body platform{{-20.0f, -6.0f}, Hitbox{40.0f, 4.0f, {}}, true};
    PlayerWorld w{{{}, {&platform}}, {&platform}};
    Player p(w, {0.0f, -3.0f}, {0.0f, -60.0f});
    float before = 0.0f, after = 0.0f;
    p.frame(1.0f / 60.0f, {}, [&](const char* phase, const CollisionData*) {
        if (std::string(phase) == "normal") before = p.actor().body.position.y;
        if (std::string(phase) == "boost") after = p.actor().body.position.y;
    });
    expect(!p.state().on_ground && after == before - 1.0f, "Upward overlap boost must occur before velocity movement");
}

void jumpthru_descent_and_unsafe_ground() {
    Body platform{{-20.0f, 0.0f}, Hitbox{40.0f, 8.0f, {}}, true};
    PlayerWorld w{{{}, {&platform}}, {}};
    Player p(w, {0.0f, -4.0f}, {0.0f, 120.0f});
    p.frame(1.0f / 60.0f);
    p.frame(1.0f / 60.0f);
    p.frame(1.0f / 60.0f);
    expect(p.state().on_ground && !p.state().on_safe_ground && p.actor().body.position.y == 0.0f, "JumpThru descent/safety");
}

void solid_ground_has_priority() {
    Body solid{{-20.0f, 0.0f}, Hitbox{40.0f, 8.0f, {}}, true};
    Body jump = solid;
    PlayerWorld w{{{&solid}, {&jump}}, {&jump}};
    Player p(w);
    p.frame(0.0f);
    expect(p.state().on_ground && !p.state().on_safe_ground, "Solid ground must win before safe JumpThru");
}

void duck_jump_keeps_duck_colliders() {
    Grounded g;
    Player p(g.world);
    p.frame(1.0f / 60.0f, press(1, 1));
    expect(p.state().ducking && p.state().speed.y == -105.0f && p.state().speed.x == 40.0f, "Jump itself must not unduck");
    expect(p.actor().body.collider->height == 6.0f && p.hurtbox().height == 4.0f && p.hurtbox().offset.y == -6.0f, "Duck collider identities");
}

void blocked_stand_assist_parameterized() {
    for (float width : {0.0f, 4.0f}) {
        Grounded g;
        Body ceiling{{0.0f, -11.0f}, Hitbox{width, 5.0f, {}}, true};
        g.world.collision.solids.push_back(&ceiling);
        Player p(g.world);
        p.frame(1.0f / 60.0f, {0, 1});
        p.frame(1.0f / 60.0f);
        expect(p.state().ducking && p.actor().body.position.x == (width == 0.0f ? 1.0f : -1.0f), "Right-before-left stand assist");
        expect(p.actor().position_remainder().x != 0.0f, "Stand assist must use MoveH subpixels");
    }
}

void ceiling_correction_priority_parameterized() {
    for (float left : {0.0f, -4.0f}) {
        Body ceiling{{left, -12.0f}, Hitbox{left == 0.0f ? 0.0f : 4.0f, 1.0f, {}}, true};
        PlayerWorld w{{{&ceiling}, {}}, {&ceiling}};
        Player p(w, {}, {0.0f, -105.0f});
        p.frame(1.0f / 60.0f);
        expect(p.actor().body.position.x == (left == 0.0f ? -4.0f : 4.0f) && p.actor().body.position.y == -1.0f, "Ceiling correction direct position/priority");
        expect(p.state().speed.y == -90.0f, "Correction must return before clearing speed");
    }
}

void headbump_strict_timer_parameterized() {
    for (float delta : {0.04f, 0.05f, 0.06f}) {
        Grounded g;
        Body ceiling{{-1000.0f, -13.0f}, Hitbox{2000.0f, 2.0f, {}}, true};
        g.world.collision.solids.push_back(&ceiling);
        Player p(g.world);
        p.frame(0.0f, press());
        p.frame(delta, held());
        const float remaining = 0.2f - delta;
        expect(p.state().speed.y == 0.0f && p.state().var_jump_timer == (remaining < 0.15f ? 0.0f : remaining), "Head bump cancellation must be strict < 0.15");
    }
}

void wall_slide_timer() {
    Body wall{{4.0f, -100.0f}, Hitbox{8.0f, 200.0f, {}}, true};
    PlayerWorld w{{{&wall}, {}}, {&wall}};
    Player p(w, {}, {90.0f, 100.0f});
    p.frame(1.0f / 60.0f, {1});
    expect(p.state().wall_slide_dir == 1 && p.state().speed.y == 85.0f, "Normal wall slide target");
    p.frame(1.0f / 60.0f, {1});
    expect(p.state().wall_slide_timer == 1.2f - 1.0f / 60.0f, "Prior slide decrements timer before Normal");
}

void wall_retention_restores() {
    Body wall{{4.0f, -20.0f}, Hitbox{8.0f, 11.0f, {}}, true};
    PlayerWorld w{{{&wall}, {}}, {&wall}};
    Player p(w, {}, {90.0f, 120.0f});
    p.frame(1.0f / 60.0f, {1});
    expect(p.state().wall_speed_retained == 90.0f && p.state().wall_speed_retention_timer == 0.06f, "Collision records retained speed");
    p.frame(1.0f / 60.0f, {1});
    expect(p.state().speed.x == 90.0f && p.state().wall_speed_retention_timer == 0.0f, "Leaving wall restores retained speed");
}

void wall_retention_cancels() {
    Body wall{{4.0f, -100.0f}, Hitbox{8.0f, 200.0f, {}}, true};
    PlayerWorld w{{{&wall}, {}}, {&wall}};
    Player p(w, {}, {90.0f, 100.0f});
    p.frame(1.0f / 60.0f, {1});
    p.frame(1.0f / 60.0f, {-1});
    p.frame(1.0f / 60.0f, {-1});
    expect(p.state().speed.x < 0.0f && p.state().wall_speed_retention_timer == 0.0f, "Opposing prior speed cancels retention");
}

void eligible_walljump_launches() {
    Body wall{{4.0f, -100.0f}, Hitbox{8.0f, 200.0f, {}}, true};
    PlayerWorld w{{{&wall}, {}}, {&wall}};
    Player p(w);
    p.frame(0.0f, press());
    expect(p.state().speed.x == -130.0f && p.state().speed.y == -105.0f, "Neutral wall jump launch");
    expect(p.state().var_jump_timer == 0.2f && p.jump_button().buffer_counter() == 0.0f, "Wall jump consumes buffer");
}

void airborne_jump_buffers_without_wall() {
    PlayerWorld w;
    Player p(w, {0.0f, -100.0f});
    p.frame(1.0f / 60.0f, press());
    expect(p.jump_button().buffer_counter() == 0.08f && p.state().var_jump_timer == 0.0f, "Noneligible airborne press must buffer, not reject");
}

void unsupported_actions_parameterized() {
    for (int kind : {1, 2}) {
        PlayerWorld w;
        Player p(w);
        PlayerInput input;
        input.dash = kind == 1;
        input.jump.debug_override_pressed = kind == 2;
        invalid([&] { p.frame(0.1f, input); });
        expect(p.jump_button().buffer_counter() == 0.0f && p.state().previous_position.y == 0.0f, "Unsupported action mutated frame before validation");
    }
}

void unsupported_profile() {
    PlayerWorld w;
    invalid([&] { Player p(w, {}, {}, static_cast<PlayerProfile>(1)); });
}

void unsupported_states_parameterized() {
    for (int state : {-1, 1, 2, 3, 25, 26}) {
        PlayerWorld w;
        Player p(w);
        invalid([&] { p.request_state(state); });
        expect(p.state_machine().state() == 0, "Unsupported state changed scheduler");
    }
}

void nonfinite_inputs_parameterized() {
    for (float value : {std::numeric_limits<float>::infinity(), -std::numeric_limits<float>::infinity(), std::numeric_limits<float>::quiet_NaN()}) {
        PlayerWorld w;
        invalid([&] { Player p(w, {value, 0.0f}); });
        invalid([&] { Player p(w, {}, {0.0f, value}); });
        Player p(w);
        invalid([&] { p.frame(value); });
    }
}

void invalid_axes_parameterized() {
    for (PlayerInput input : {PlayerInput{2}, PlayerInput{-2}, PlayerInput{0, 2}, PlayerInput{0, -2}}) {
        PlayerWorld w;
        Player p(w);
        invalid([&] { p.frame(0.1f, input); });
    }
}

void nonfinite_world_validated_before_input() {
    Grounded g;
    Player p(g.world);
    g.floor.position.x = std::numeric_limits<float>::quiet_NaN();
    invalid([&] { p.frame(0.1f, press()); });
    expect(p.jump_button().buffer_counter() == 0.0f, "World invalidity must fail before sampled input update");
}

void bounds_disabled() {
    Grounded g;
    g.world.bounds_left = -6.0f;
    g.world.bounds_right = 6.0f;
    Player p(g.world, {}, {90.0f, 0.0f});
    p.frame(0.1f, {1});
    expect(p.actor().body.position.x == 9.0f, "Fixture bounds must not enforce movement limits");
}

}

int main() {
    const std::pair<const char*, void(*)()> tests[] = {
        {"grounded_jump_consumes_buffer", grounded_jump_consumes_buffer},
        {"initialization_truncates_and_begins_normal", initialization_truncates_and_begins_normal},
        {"run_reverse", run_reverse}, {"jump_overspeed", jump_overspeed},
        {"coyote_expiry_parameterized", coyote_expiry_parameterized},
        {"buffered_landing_uses_next_ground_snapshot", buffered_landing_uses_next_ground_snapshot},
        {"release_clears_landing_buffer", release_clears_landing_buffer},
        {"held_released_apex_parameterized", held_released_apex_parameterized},
        {"fastfall_entry_and_recovery", fastfall_entry_and_recovery}, {"jumpthru_overlap_boost", jumpthru_overlap_boost},
        {"jumpthru_descent_and_unsafe_ground", jumpthru_descent_and_unsafe_ground}, {"solid_ground_has_priority", solid_ground_has_priority},
        {"duck_jump_keeps_duck_colliders", duck_jump_keeps_duck_colliders}, {"blocked_stand_assist_parameterized", blocked_stand_assist_parameterized},
        {"ceiling_correction_priority_parameterized", ceiling_correction_priority_parameterized}, {"headbump_strict_timer_parameterized", headbump_strict_timer_parameterized},
        {"wall_slide_timer", wall_slide_timer}, {"wall_retention_restores", wall_retention_restores}, {"wall_retention_cancels", wall_retention_cancels},
        {"eligible_walljump_launches", eligible_walljump_launches}, {"airborne_jump_buffers_without_wall", airborne_jump_buffers_without_wall},
        {"unsupported_actions_parameterized", unsupported_actions_parameterized}, {"unsupported_profile", unsupported_profile},
        {"unsupported_states_parameterized", unsupported_states_parameterized}, {"nonfinite_inputs_parameterized", nonfinite_inputs_parameterized},
        {"invalid_axes_parameterized", invalid_axes_parameterized}, {"nonfinite_world_validated_before_input", nonfinite_world_validated_before_input},
        {"bounds_disabled", bounds_disabled},
    };
    int failures = 0;
    for (const auto& test : tests) {
        try { test.second(); std::cout << "PASS: " << test.first << '\n'; }
        catch (const std::exception& error) { ++failures; std::cerr << "FAIL: " << test.first << ": " << error.what() << '\n'; }
    }
    return failures ? 1 : 0;
}
