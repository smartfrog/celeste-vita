#include "input.hpp"

#include <cmath>
#include <stdexcept>

namespace celeste {

VirtualButton::VirtualButton(float time) : buffer_time(time) {
    if (!std::isfinite(time)) throw std::invalid_argument("Nonfinite buffer time");
}

bool VirtualButton::check() const { return !sample.disabled && sample.held; }

bool VirtualButton::pressed() const {
    if (sample.debug_override_pressed) return true;
    if (sample.disabled || consumed_) return false;
    return buffer_counter_ > 0.0f || repeating_ || sample.pressed;
}

bool VirtualButton::released() const { return !sample.disabled && sample.released; }

void VirtualButton::update(float scaled_delta_time) {
    if (!std::isfinite(scaled_delta_time) || !std::isfinite(buffer_time))
        throw std::invalid_argument("Nonfinite input time");
    consumed_ = false;
    const float remaining_buffer = buffer_counter_ - scaled_delta_time;
    if (!std::isfinite(remaining_buffer)) throw std::invalid_argument("Buffer timer overflow");
    buffer_counter_ = remaining_buffer;
    if (sample.pressed) buffer_counter_ = buffer_time;
    if (!sample.pressed && !sample.held) {
        repeating_ = false;
        repeat_counter_ = 0.0f;
        buffer_counter_ = 0.0f;
    } else {
        if (!can_repeat_) return;
        repeating_ = false;
        if (repeat_counter_ == 0.0f) {
            repeat_counter_ = first_repeat_time_;
            return;
        }
        const float remaining_repeat = repeat_counter_ - scaled_delta_time;
        if (!std::isfinite(remaining_repeat)) throw std::invalid_argument("Repeat timer overflow");
        repeat_counter_ = remaining_repeat;
        if (repeat_counter_ <= 0.0f) {
            repeating_ = true;
            repeat_counter_ = multi_repeat_time_;
        }
    }
}

void VirtualButton::set_repeat(float time) { set_repeat(time, time); }

void VirtualButton::set_repeat(float first, float multi) {
    if (!std::isfinite(first) || !std::isfinite(multi)) throw std::invalid_argument("Nonfinite repeat time");
    first_repeat_time_ = first;
    multi_repeat_time_ = multi;
    can_repeat_ = first_repeat_time_ > 0.0f;
    if (!can_repeat_) repeating_ = false;
}

void VirtualButton::consume_buffer() { buffer_counter_ = 0.0f; }

void VirtualButton::consume_press() {
    buffer_counter_ = 0.0f;
    consumed_ = true;
}

}
