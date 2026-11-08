#include "input.hpp"

#include <cstdint>
#include <cstring>
#include <iostream>
#include <cmath>
#include <limits>
#include <stdexcept>
#include <string>
#include <utility>

using namespace celeste;

namespace {

void expect(bool condition, const std::string& message) {
    if (!condition) throw std::runtime_error(message);
}

std::uint32_t bits(float value) {
    std::uint32_t result;
    std::memcpy(&result, &value, sizeof(result));
    return result;
}

void press_hold_release() {
    VirtualButton button(0.08f);
    button.sample = {true, true};
    button.update(0.01f);
    expect(button.check() && button.pressed(), "Fresh press missing");
    expect(bits(button.buffer_counter()) == bits(0.08f), "Fresh press did not set buffer");
    button.sample = {true};
    button.update(0.01f);
    expect(button.pressed() && bits(button.buffer_counter()) == bits(0.08f - 0.01f), "Held buffer lost");
    button.sample = {false, false, true};
    button.update(0.01f);
    expect(!button.check() && !button.pressed() && button.released(), "Release queries");
    expect(bits(button.buffer_counter()) == 0 && bits(button.repeat_counter()) == 0, "Release did not clear counters");
}

void buffer_profiles_parameterized() {
    for (float time : {0.0f, 0.08f, -0.08f, -0.0f}) {
        VirtualButton button(time);
        button.sample = {true, true};
        button.update(0.1f);
        expect(button.pressed() && bits(button.buffer_counter()) == bits(time), "Raw press/buffer profile");
        button.sample.pressed = false;
        button.update(0.0f);
        expect(button.pressed() == (time > 0.0f), "Nonpositive buffer should not press");
    }
}

void buffer_boundary_parameterized() {
    for (float delta : {0.04f, 0.08f, std::nextafter(0.08f, 1.0f)}) {
        VirtualButton button(0.08f);
        button.sample = {true, true};
        button.update(1.0f);
        button.sample.pressed = false;
        button.update(delta);
        const float remaining = 0.08f - delta;
        expect(bits(button.buffer_counter()) == bits(remaining), "Buffer countdown was clamped or reordered");
        expect(button.pressed() == (remaining > 0.0f), "Buffer boundary query");
    }
}

void consume_buffer_retains_raw_press() {
    VirtualButton button(0.08f);
    button.sample = {true, true};
    button.update(0.01f);
    button.consume_buffer();
    expect(button.pressed() && !button.consumed() && bits(button.buffer_counter()) == 0, "ConsumeBuffer consumed raw press");
    button.sample.pressed = false;
    expect(!button.pressed() && button.check(), "ConsumeBuffer did not clear buffer only");
}

void consume_press_resets_on_next_update() {
    VirtualButton button(0.08f);
    button.sample = {true, true, true};
    button.update(0.01f);
    button.consume_press();
    expect(button.consumed() && !button.pressed() && button.check() && button.released(), "ConsumePress gated wrong queries");
    button.consume_buffer();
    expect(button.consumed() && !button.pressed(), "ConsumeBuffer cleared consumed flag");
    button.update(0.0f);
    expect(!button.consumed() && button.pressed(), "Next Update did not reset consumed first");
}

void query_gates_parameterized() {
    for (bool disabled : {false, true}) for (bool consumed : {false, true})
    for (bool debug : {false, true}) for (bool raw : {false, true}) {
        VirtualButton button;
        button.sample = {true, raw, true, disabled, debug};
        if (consumed) button.consume_press();
        const bool expected = debug || (!disabled && !consumed && raw);
        expect(button.pressed() == expected && button.pressed() == expected, "Pressed precedence or unstable query");
        expect(button.check() == !disabled && button.released() == !disabled, "Disabled check/release gate");
    }
}

void disabled_update_still_counts_down() {
    VirtualButton button(0.08f);
    button.set_repeat(0.1f, 0.2f);
    button.sample = {true, true};
    button.update(1.0f);
    button.sample = {true, false, true, true};
    button.update(0.04f);
    expect(!button.consumed() && bits(button.buffer_counter()) == bits(0.08f - 0.04f), "Disabled skipped buffer update");
    expect(bits(button.repeat_counter()) == bits(0.1f - 0.04f), "Disabled skipped repeat update");
    expect(!button.check() && !button.pressed() && !button.released(), "Disabled query leaked");
    button.sample.disabled = false;
    expect(button.pressed(), "Disabled destroyed remaining buffer");
}

void repeat_first_multi_and_overshoot() {
    VirtualButton button;
    button.set_repeat(0.1f, 0.25f);
    button.sample = {true};
    button.update(9.0f);
    expect(button.can_repeat() && !button.repeating() && bits(button.repeat_counter()) == bits(0.1f), "First update did not only prime repeat");
    button.update(0.05f);
    expect(!button.repeating() && bits(button.repeat_counter()) == bits(0.1f - 0.05f), "First delay countdown");
    button.update(0.05f);
    expect(button.repeating() && button.pressed() && bits(button.repeat_counter()) == bits(0.25f), "Exact zero repeat boundary");
    button.update(10.0f);
    expect(button.repeating() && bits(button.repeat_counter()) == bits(0.25f), "Overshoot caught up or retained excess time");
    button.update(0.0f);
    expect(!button.repeating() && !button.pressed(), "Repeat persisted on non-firing tick");
}

void consume_buffer_retains_repeat() {
    VirtualButton button;
    button.set_repeat(0.1f);
    button.sample.held = true;
    button.update(0.0f);
    button.update(0.1f);
    button.consume_buffer();
    expect(button.repeating() && button.pressed(), "ConsumeBuffer cleared repeat");
    button.consume_press();
    expect(button.repeating() && !button.pressed(), "ConsumePress cleared repeat or failed its gate");
}

void zero_multi_primes_first_again() {
    VirtualButton button;
    button.set_repeat(0.1f, 0.0f);
    button.sample.held = true;
    button.update(0.0f);
    button.update(0.1f);
    expect(button.repeating() && bits(button.repeat_counter()) == 0, "Zero multi did not fire");
    button.update(9.0f);
    expect(!button.repeating() && bits(button.repeat_counter()) == bits(0.1f), "Zero counter must reprime first and return");
}

void negative_multi_remains_source_configuration() {
    VirtualButton button;
    button.set_repeat(0.1f, -0.2f);
    button.sample.held = true;
    button.update(0.0f);
    button.update(0.1f);
    button.update(0.0f);
    expect(button.repeating() && bits(button.repeat_counter()) == bits(-0.2f), "Negative multi clamped/reset");
}

void disabling_repeat_preserves_counters_parameterized() {
    for (float first : {0.0f, -0.1f, -0.0f}) {
        VirtualButton button(0.08f);
        button.set_repeat(0.1f, 0.2f);
        button.sample = {true, true};
        button.update(0.0f);
        button.sample.pressed = false;
        button.update(0.1f);
        expect(button.repeating(), "Repeat setup");
        const auto buffer = bits(button.buffer_counter());
        button.set_repeat(first, -0.4f);
        expect(!button.can_repeat() && !button.repeating(), "Nonpositive first delay did not disable");
        expect(bits(button.repeat_counter()) == bits(0.2f) && bits(button.buffer_counter()) == buffer, "SetRepeat reset counters");
        button.update(0.01f);
        expect(bits(button.repeat_counter()) == bits(0.2f), "Disabled repeat counter advanced");
        button.set_repeat(0.9f, 0.3f);
        button.update(0.05f);
        expect(bits(button.repeat_counter()) == bits(0.2f - 0.05f), "Reenable reset to first delay");
    }
}

void enabled_set_repeat_retains_repeating_and_consumption() {
    VirtualButton button;
    button.set_repeat(0.1f);
    button.sample.held = true;
    button.update(0.0f);
    button.update(0.1f);
    button.consume_press();
    button.set_repeat(0.5f, 0.6f);
    expect(button.repeating() && button.consumed() && bits(button.repeat_counter()) == bits(0.1f), "Enabled SetRepeat reset live state");
}

void release_clears_repeat_while_disabled() {
    VirtualButton button(0.08f);
    button.set_repeat(0.1f);
    button.sample = {true, true};
    button.update(0.0f);
    button.update(0.1f);
    button.sample = {false, false, true, true};
    button.update(0.0f);
    expect(!button.repeating() && bits(button.repeat_counter()) == 0 && bits(button.buffer_counter()) == 0, "Release did not clear disabled repeat");
}

void pressed_without_held_still_primes() {
    VirtualButton button(0.08f);
    button.set_repeat(0.1f);
    button.sample.pressed = true;
    button.update(1.0f);
    expect(!button.check() && button.pressed() && bits(button.repeat_counter()) == bits(0.1f), "Raw press lost precedence over held");
}

void zero_delta_and_omitted_scene_update() {
    VirtualButton button(0.08f);
    button.sample = {true, true};
    button.update(0.0f);
    button.sample.pressed = false;
    button.consume_press();
    button.update(0.0f);
    expect(!button.consumed() && bits(button.buffer_counter()) == 0, "Zero delta did not reset consumed");
    button.sample.pressed = true;
    button.update(0.0f);
    button.sample.pressed = false;
    button.update(0.04f);
    expect(button.pressed() && bits(button.buffer_counter()) == bits(0.08f - 0.04f), "Input needed a scene update");
}

void negative_delta_is_not_clamped() {
    VirtualButton button;
    button.sample.held = true;
    button.update(-0.25f);
    expect(button.pressed() && bits(button.buffer_counter()) == bits(0.25f), "Finite negative delta changed");
}

template<typename Action>
void expect_invalid(Action action) {
    try { action(); }
    catch (const std::invalid_argument&) { return; }
    throw std::runtime_error("Expected invalid_argument");
}

void nonfinite_inputs_rejected_parameterized() {
    for (float value : {std::numeric_limits<float>::infinity(), -std::numeric_limits<float>::infinity(), std::numeric_limits<float>::quiet_NaN()}) {
        expect_invalid([&] { VirtualButton button(value); });
        VirtualButton button;
        expect_invalid([&] { button.set_repeat(value, 0.0f); });
        expect_invalid([&] { button.set_repeat(0.1f, value); });
        expect_invalid([&] { button.update(value); });
        button.buffer_time = value;
        expect_invalid([&] { button.update(0.0f); });
    }
}

void counter_overflow_rejected() {
    VirtualButton button(std::numeric_limits<float>::max());
    button.sample = {true, true};
    button.update(0.0f);
    button.sample.pressed = false;
    expect_invalid([&] { button.update(-std::numeric_limits<float>::max()); });
}

void repeat_counter_overflow_rejected() {
    VirtualButton button;
    button.set_repeat(std::numeric_limits<float>::max());
    button.sample.held = true;
    button.update(0.0f);
    expect_invalid([&] { button.update(-std::numeric_limits<float>::max()); });
}

}

int main() {
    const std::pair<const char*, void(*)()> tests[] = {
        {"press_hold_release", press_hold_release},
        {"buffer_profiles_parameterized", buffer_profiles_parameterized},
        {"buffer_boundary_parameterized", buffer_boundary_parameterized},
        {"consume_buffer_retains_raw_press", consume_buffer_retains_raw_press},
        {"consume_press_resets_on_next_update", consume_press_resets_on_next_update},
        {"query_gates_parameterized", query_gates_parameterized},
        {"disabled_update_still_counts_down", disabled_update_still_counts_down},
        {"repeat_first_multi_and_overshoot", repeat_first_multi_and_overshoot},
        {"consume_buffer_retains_repeat", consume_buffer_retains_repeat},
        {"zero_multi_primes_first_again", zero_multi_primes_first_again},
        {"negative_multi_remains_source_configuration", negative_multi_remains_source_configuration},
        {"disabling_repeat_preserves_counters_parameterized", disabling_repeat_preserves_counters_parameterized},
        {"enabled_set_repeat_retains_repeating_and_consumption", enabled_set_repeat_retains_repeating_and_consumption},
        {"release_clears_repeat_while_disabled", release_clears_repeat_while_disabled},
        {"pressed_without_held_still_primes", pressed_without_held_still_primes},
        {"zero_delta_and_omitted_scene_update", zero_delta_and_omitted_scene_update},
        {"negative_delta_is_not_clamped", negative_delta_is_not_clamped},
        {"nonfinite_inputs_rejected_parameterized", nonfinite_inputs_rejected_parameterized},
        {"counter_overflow_rejected", counter_overflow_rejected},
        {"repeat_counter_overflow_rejected", repeat_counter_overflow_rejected},
    };
    int failures = 0;
    for (const auto& test : tests) {
        try { test.second(); std::cout << "PASS: " << test.first << '\n'; }
        catch (const std::exception& error) { ++failures; std::cerr << "FAIL: " << test.first << ": " << error.what() << '\n'; }
    }
    return failures == 0 ? 0 : 1;
}
