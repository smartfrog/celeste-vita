#include "diagnostic.hpp"
#include "directional_input.hpp"
#include "player.hpp"

#include <cmath>
#include <cstdint>
#include <cstring>
#include <iostream>
#include <limits>
#include <stdexcept>
#include <string>
#include <utility>

using namespace celeste;
using namespace celeste::diagnostic;

namespace {

void expect(bool condition, const char* message) {
    if (!condition) throw std::runtime_error(message);
}

std::uint32_t bits(float value) {
    std::uint32_t result;
    std::memcpy(&result, &value, sizeof(result));
    return result;
}

template<typename Action>
void expect_invalid(Action action) {
    try { action(); }
    catch (const std::invalid_argument&) { return; }
    throw std::runtime_error("Expected invalid_argument");
}

DirectionalInput resolve(DirectionalResolver& resolver, bool left, bool right, bool up, bool down,
                         float x, float y) {
    return resolver.update({left, right, up, down}, {x, y});
}

void neutral_initial_state_is_explicit() {
    DirectionalResolver resolver;
    const auto input = resolver.update({}, {});
    expect(input.move_x == 0 && input.move_y == 0 && input.aim_x == 0 && input.aim_y == 0,
           "Fresh resolver must start neutral");
}

void normalize_neutral_noise_and_scaling() {
    auto stick = normalize_vita_stick({128, 128, true});
    expect(bits(stick.x) == bits(0.0f) && bits(stick.y) == bits(0.0f), "128 must be neutral");
    stick = normalize_vita_stick({127, 129, true});
    expect(bits(stick.x) == bits(-1.0f / 128.0f) && bits(stick.y) == bits(1.0f / 127.0f),
           "Piecewise -1/128 and 1/127 scaling");
    stick = normalize_vita_stick({64, 191, true});
    expect(bits(stick.x) == bits(-0.5f) && bits(stick.y) == bits(63.0f / 127.0f),
           "Intermediate piecewise scaling");
}

void normalize_extremes_and_polarity() {
    auto stick = normalize_vita_stick({0, 0, true});
    expect(stick.x == -1.0f && stick.y == -1.0f, "Raw zero must be left/up, never neutral");
    stick = normalize_vita_stick({255, 255, true});
    expect(stick.x == 1.0f && stick.y == 1.0f, "Raw maximum must be right/down");
    stick = normalize_vita_stick({255, 0, true});
    expect(stick.x == 1.0f && stick.y == -1.0f, "Axis polarity is independent");
    stick = normalize_vita_stick({0, 255, true});
    expect(stick.x == -1.0f && stick.y == 1.0f, "Axis polarity is independent");
}

void invalid_or_zero_initialized_reading_stays_neutral() {
    auto stick = normalize_vita_stick({0, 0, false});
    expect(stick.x == 0.0f && stick.y == 0.0f, "Invalid zero bytes must not become full up-left");
    stick = normalize_vita_stick({255, 255, false});
    expect(stick.x == 0.0f && stick.y == 0.0f, "Invalid maximum bytes must stay neutral");
    stick = normalize_vita_stick(StickReading{});
    expect(stick.x == 0.0f && stick.y == 0.0f, "Default reading must be explicit neutral");
    expect_invalid([] { normalize_vita_stick({256, 128, true}); });
    expect_invalid([] { normalize_vita_stick({128, 256, true}); });
}

void move_axis_deadzones_are_inclusive_normalized_floats() {
    DirectionalResolver resolver;
    expect(resolve(resolver, false, false, false, false, 0.3f, 0.0f).move_x == 1, "MoveX 0.3 inclusive");
    resolver = DirectionalResolver{};
    expect(resolve(resolver, false, false, false, false, std::nextafter(0.3f, 0.0f), 0.0f).move_x == 0,
           "MoveX below 0.3");
    resolver = DirectionalResolver{};
    expect(resolve(resolver, false, false, false, false, 0.0f, 0.7f).move_y == 1, "MoveY 0.7 inclusive down");
    resolver = DirectionalResolver{};
    expect(resolve(resolver, false, false, false, false, 0.0f, std::nextafter(0.7f, 0.0f)).move_y == 0,
           "MoveY below 0.7");
    resolver = DirectionalResolver{};
    expect(resolve(resolver, false, false, false, false, 0.0f, -0.7f).move_y == -1, "MoveY 0.7 inclusive up");
}

void move_overlap_take_newer_invert_hold_and_release() {
    DirectionalResolver resolver;
    expect(resolve(resolver, false, true, false, false, 0.0f, 0.0f).move_x == 1, "Right only");
    expect(resolve(resolver, true, true, false, false, 0.0f, 0.0f).move_x == -1, "First overlap inverts");
    expect(resolve(resolver, true, true, false, false, 0.0f, 0.0f).move_x == -1, "Overlap holds");
    expect(resolve(resolver, false, true, false, false, 0.0f, 0.0f).move_x == 1, "Release restores");
    expect(resolve(resolver, true, false, false, false, 0.0f, 0.0f).move_x == -1, "Left only");
}

void move_overlap_from_zero_stays_zero_until_release() {
    DirectionalResolver resolver;
    expect(resolve(resolver, true, true, false, false, 0.0f, 0.0f).move_x == 0, "First zero overlap");
    expect(resolve(resolver, true, true, false, false, 0.0f, 0.0f).move_x == 0, "Zero overlap holds");
    expect(resolve(resolver, false, true, false, false, 0.0f, 0.0f).move_x == 1, "Release leaves right");
}

void weak_same_direction_stick_shadows_dpad_only_for_its_binding() {
    DirectionalResolver resolver;
    const auto input = resolve(resolver, false, false, true, false, 0.0f, -0.1f);
    expect(input.move_y == -1, "MoveY binding must fall through weak stick to DPad");
    expect(input.aim_x == 0 && input.aim_y == 0, "Aim binding must use weak stick before DPad and radial-zero it");
}

void aim_radial_deadzone_is_strict_at_quarter() {
    DirectionalResolver resolver;
    expect(resolve(resolver, false, false, false, false, 0.0f, -0.25f).aim_y == -1, "Radial 0.25 inclusive");
    resolver = DirectionalResolver{};
    const auto inside = resolve(resolver, false, false, false, false, 0.0f, std::nextafter(-0.25f, 0.0f));
    expect(inside.aim_x == 0 && inside.aim_y == 0, "Radial below 0.25 is neutral");
    resolver = DirectionalResolver{};
    expect(resolve(resolver, false, false, false, false, 0.0f, -0.250001f).aim_y == -1, "Radial above 0.25");
}

void half_up_keeps_move_neutral_but_aim_up() {
    DirectionalResolver resolver;
    const auto input = resolve(resolver, false, false, false, false, 0.0f, -0.5f);
    expect(input.move_y == 0, "MoveY 0.5 must stay below the 0.7 deadzone");
    expect(input.aim_x == 0 && input.aim_y == -1, "AimY must remain independently up");
}

void fifth_up_is_neutral_on_both_channels() {
    DirectionalResolver resolver;
    const auto input = resolve(resolver, false, false, false, false, 0.0f, -0.2f);
    expect(input.move_y == 0 && input.aim_x == 0 && input.aim_y == 0, "Y 0.2 must be neutral without DPad");
}

void aim_overlap_uses_magnitudes_then_take_newer() {
    DirectionalResolver resolver;
    expect(resolve(resolver, true, false, false, false, 0.5f, 0.0f).aim_x == -1, "DPad left magnitude 1 wins");
    resolver = DirectionalResolver{};
    expect(resolve(resolver, false, true, false, false, -0.5f, 0.0f).aim_x == 1, "DPad right magnitude 1 wins");
    resolver = DirectionalResolver{};
    expect(resolve(resolver, false, false, false, false, 1.0f, 0.0f).aim_x == 1, "Prior right");
    expect(resolve(resolver, true, false, false, false, 1.0f, 0.0f).aim_x == -1, "Equal overlap takes newer left");
    expect(resolve(resolver, true, false, false, false, 1.0f, 0.0f).aim_x == -1, "Equal overlap holds newer");
    expect(resolve(resolver, false, false, false, false, 1.0f, 0.0f).aim_x == 1, "Release restores right");
}

void aim_equal_overlap_from_zero_stays_zero() {
    DirectionalResolver resolver;
    const auto input = resolve(resolver, true, true, false, false, 0.0f, 0.0f);
    expect(input.aim_x == 0 && input.aim_y == 0, "Equal opposite DPad from zero must stay neutral");
    expect(resolve(resolver, false, true, false, false, 0.0f, 0.0f).aim_x == 1, "Release leaves right");
}

void aim_diagonals_and_cardinals_are_eight_way() {
    const std::pair<StickVector, std::pair<int, int>> cases[] = {
        {{1.0f, 0.0f}, {1, 0}}, {{1.0f, 1.0f}, {1, 1}}, {{0.0f, 1.0f}, {0, 1}},
        {{-1.0f, 1.0f}, {-1, 1}}, {{-1.0f, 0.0f}, {-1, 0}}, {{-1.0f, -1.0f}, {-1, -1}},
        {{0.0f, -1.0f}, {0, -1}}, {{1.0f, -1.0f}, {1, -1}}};
    for (const auto& item : cases) {
        const auto aim = snap_aim_direction(item.first);
        expect(aim.x == item.second.first && aim.y == item.second.second, "Eight-way aim direction");
    }
    const auto zero = snap_aim_direction({0.0f, 0.0f});
    expect(zero.x == 0 && zero.y == 0, "Zero aim stays for Player facing resolution");
}

void aim_snap_uses_strict_225_and_175_degree_boundaries() {
    constexpr float pi = 3.14159265358979323846f;
    const float positive = pi / 8.0f;
    const float negative = pi / 8.0f - 0.08726646f;
    const auto vector = [](float angle) { return StickVector{std::cos(angle), std::sin(angle)}; };
    const auto inside_positive = snap_aim_direction(vector(positive - 0.001f));
    expect(inside_positive.x == 1 && inside_positive.y == 0, "Positive inside 22.5 is cardinal");
    const auto exact_positive = snap_aim_direction(vector(positive));
    expect(exact_positive.x == 1 && exact_positive.y == 1, "Positive exact 22.5 is outside the strict threshold");
    const auto outside = snap_aim_direction(vector(positive + 0.001f));
    expect(outside.x == 1 && outside.y == 1, "Positive outside 22.5 is diagonal");
    const auto inside_negative = snap_aim_direction(vector(-negative + 0.001f));
    expect(inside_negative.x == 1 && inside_negative.y == 0, "Negative inside 17.5 is cardinal");
    const auto exact_negative = snap_aim_direction(vector(-negative));
    expect(exact_negative.x == 1 && exact_negative.y == -1, "Negative exact 17.5 is outside the strict threshold");
    const auto negative_outside = snap_aim_direction(vector(-negative - 0.001f));
    expect(negative_outside.x == 1 && negative_outside.y == -1, "Negative outside 17.5 is diagonal");
}

Sample analog_sample(Controller& controller, Controls buttons, StickReading stick) {
    return controller.sample_analog({buttons, stick});
}

void analog_edges_match_legacy_for_ordinary_buttons() {
    Controller legacy;
    Controller analog;
    const Controls sequence[] = {
        {false, false, false, false, true}, {false, false, false, false, true}, {},
        {false, false, false, false, false, false, false, true}, {}, {false, false, true}, {},
        {false, false, false, false, false, true}, {false, false, false, false, false, false, true}};
    for (const auto& controls : sequence) {
        const auto expected = legacy.sample(controls);
        const auto actual = analog_sample(analog, controls, {128, 128, true});
        expect(actual.player.x == expected.player.x && actual.player.y == expected.player.y &&
               actual.player.aim_x == expected.player.aim_x && actual.player.aim_y == expected.player.aim_y &&
               actual.player.jump.held == expected.player.jump.held &&
               actual.player.jump.pressed == expected.player.jump.pressed &&
               actual.player.jump.released == expected.player.jump.released &&
               actual.player.dash_button.held == expected.player.dash_button.held &&
               actual.player.dash_button.pressed == expected.player.dash_button.pressed &&
               actual.player.dash_button.released == expected.player.dash_button.released &&
               actual.player.grab == expected.player.grab && actual.reset == expected.reset && actual.exit == expected.exit,
               "Ordinary analog button edges must match legacy");
    }
}

void opposite_dpad_take_newer_is_the_explicit_profile_difference() {
    Controller legacy;
    Controller analog;
    const Controls right{false, true};
    const Controls both{true, true};
    expect(legacy.sample(right).player.x == 1 && analog_sample(analog, right, {128, 128, true}).player.x == 1,
           "Ordinary right");
    expect(legacy.sample(both).player.x == 0, "Legacy opposite DPad stays neutral");
    expect(analog_sample(analog, both, {128, 128, true}).player.x == -1,
           "Analog profile source TakeNewer inverts the conflicting axis");
}

void invalid_sample_keeps_neutral_axes_and_buttons() {
    Controller controller;
    const auto input = analog_sample(controller, {}, {0, 0, false});
    expect(input.player.x == 0 && input.player.y == 0 && input.player.aim_x == 0 && input.player.aim_y == 0,
           "Unavailable reading must be neutral, not raw zero full up-left");
    expect(!input.player.grab && !input.player.jump.held && !input.player.dash_button.held,
           "Unavailable reading must not synthesize buttons");
}

void l_and_stick_drive_actual_climb_axes() {
    Body wall{{4.0f, -100.0f}, Hitbox{8.0f, 200.0f, {}}, true};
    PlayerWorld world;
    world.collision.solids = {&wall};
    Player player(world, {}, {0.0f, 50.0f});
    Controller controller;
    Controls held;
    held.l = true;
    const auto down = analog_sample(controller, held, {128, 255, true});
    expect(down.player.grab && down.player.y == 1, "L and stick down feed Grab and MoveY");
    player.frame(1.0f / 60.0f, down.player);
    expect(player.state_machine().state() == 1 && player.grab_held(), "Analog Grab plus down enters Climb");
    const auto up = analog_sample(controller, held, {128, 0, true});
    expect(up.player.grab && up.player.y == -1, "L and stick up feed Grab and MoveY");
    bool moved_up = false;
    for (int frame = 0; frame < 10 && !moved_up; ++frame) {
        player.frame(1.0f / 60.0f, up.player);
        moved_up = player.state_machine().state() == 1 && player.grab_held() && player.state().speed.y < 0.0f;
    }
    expect(moved_up, "Analog up moves the real Climb state upward");
}

void raw_extremes_drive_the_controller_seam() {
    Controller controller;
    auto input = analog_sample(controller, {}, {255, 128, true});
    expect(input.player.x == 1 && input.player.aim_x == 1, "Raw full right reaches move and aim");
    input = analog_sample(controller, {}, {0, 128, true});
    expect(input.player.x == -1 && input.player.aim_x == -1, "Raw full left reaches move and aim");
    input = analog_sample(controller, {}, {128, 0, true});
    expect(input.player.y == -1 && input.player.aim_y == -1, "Raw full up reaches move and aim");
    input = analog_sample(controller, {}, {128, 255, true});
    expect(input.player.y == 1 && input.player.aim_y == 1, "Raw full down reaches move and aim");
    input = analog_sample(controller, {}, {127, 128, true});
    expect(input.player.x == 0 && input.player.aim_x == 0 && input.player.aim_y == 0, "Raw 127 noise stays neutral");
    input = analog_sample(controller, {}, {128, 129, true});
    expect(input.player.y == 0 && input.player.aim_y == 0, "Raw 129 noise stays neutral");
}

}

int main() {
    const std::pair<const char*, void(*)()> tests[] = {
        {"neutral_initial_state_is_explicit", neutral_initial_state_is_explicit},
        {"normalize_neutral_noise_and_scaling", normalize_neutral_noise_and_scaling},
        {"normalize_extremes_and_polarity", normalize_extremes_and_polarity},
        {"invalid_or_zero_initialized_reading_stays_neutral", invalid_or_zero_initialized_reading_stays_neutral},
        {"move_axis_deadzones_are_inclusive_normalized_floats", move_axis_deadzones_are_inclusive_normalized_floats},
        {"move_overlap_take_newer_invert_hold_and_release", move_overlap_take_newer_invert_hold_and_release},
        {"move_overlap_from_zero_stays_zero_until_release", move_overlap_from_zero_stays_zero_until_release},
        {"weak_same_direction_stick_shadows_dpad_only_for_its_binding", weak_same_direction_stick_shadows_dpad_only_for_its_binding},
        {"aim_radial_deadzone_is_strict_at_quarter", aim_radial_deadzone_is_strict_at_quarter},
        {"half_up_keeps_move_neutral_but_aim_up", half_up_keeps_move_neutral_but_aim_up},
        {"fifth_up_is_neutral_on_both_channels", fifth_up_is_neutral_on_both_channels},
        {"aim_overlap_uses_magnitudes_then_take_newer", aim_overlap_uses_magnitudes_then_take_newer},
        {"aim_equal_overlap_from_zero_stays_zero", aim_equal_overlap_from_zero_stays_zero},
        {"aim_diagonals_and_cardinals_are_eight_way", aim_diagonals_and_cardinals_are_eight_way},
        {"aim_snap_uses_strict_225_and_175_degree_boundaries", aim_snap_uses_strict_225_and_175_degree_boundaries},
        {"analog_edges_match_legacy_for_ordinary_buttons", analog_edges_match_legacy_for_ordinary_buttons},
        {"opposite_dpad_take_newer_is_the_explicit_profile_difference", opposite_dpad_take_newer_is_the_explicit_profile_difference},
        {"invalid_sample_keeps_neutral_axes_and_buttons", invalid_sample_keeps_neutral_axes_and_buttons},
        {"raw_extremes_drive_the_controller_seam", raw_extremes_drive_the_controller_seam},
        {"l_and_stick_drive_actual_climb_axes", l_and_stick_drive_actual_climb_axes},
    };
    int failures = 0;
    for (const auto& test : tests) {
        try { test.second(); std::cout << "PASS: " << test.first << '\n'; }
        catch (const std::exception& error) { ++failures; std::cerr << "FAIL: " << test.first << ": " << error.what() << '\n'; }
    }
    return failures == 0 ? 0 : 1;
}
