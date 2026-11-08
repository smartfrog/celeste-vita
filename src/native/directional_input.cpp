#include "directional_input.hpp"

#include <algorithm>
#include <cmath>
#include <stdexcept>

namespace celeste {

namespace {

constexpr float pi = 3.14159265358979323846f;
constexpr float move_x_threshold = 0.3f;
constexpr float move_y_threshold = 0.7f;
constexpr float aim_radial_threshold = 0.25f;
constexpr float negative_aim_threshold = 0.08726646f;

float normalize_axis(unsigned value) {
    if (value > 255) throw std::invalid_argument("Vita stick byte exceeds 255");
    const int delta = static_cast<int>(value) - 128;
    return delta < 0 ? static_cast<float>(delta) / 128.0f : static_cast<float>(delta) / 127.0f;
}

float binding_value(bool digital, float analog, float threshold) {
    if (analog > 0.0f && analog >= threshold) return analog;
    return digital ? 1.0f : 0.0f;
}

int integer_axis(float positive, float negative, int previous, bool& turned) {
    const bool has_positive = positive > 0.0f;
    const bool has_negative = negative > 0.0f;
    if (has_positive && has_negative) {
        if (!turned) {
            previous = -previous;
            turned = true;
        }
        return previous;
    }
    if (has_positive) {
        turned = false;
        return 1;
    }
    if (has_negative) {
        turned = false;
        return -1;
    }
    turned = false;
    return 0;
}

float joystick_axis(float positive, float negative, float previous, bool& turned) {
    if (positive > negative) negative = 0.0f;
    else if (negative > positive) positive = 0.0f;
    if (positive != 0.0f && negative != 0.0f) {
        if (!turned) {
            if (previous > 0.0f) previous = -negative;
            else if (previous < 0.0f) previous = positive;
            turned = true;
        } else if (previous > 0.0f) {
            previous = positive;
        } else if (previous < 0.0f) {
            previous = -negative;
        }
        return previous;
    }
    if (positive != 0.0f) {
        turned = false;
        return positive;
    }
    if (negative != 0.0f) {
        turned = false;
        return -negative;
    }
    turned = false;
    return 0.0f;
}

float angle_diff(float radians_a, float radians_b) {
    float result = radians_b - radians_a;
    while (result > pi) result -= 2.0f * pi;
    while (result <= -pi) result += 2.0f * pi;
    return result;
}

float abs_angle_diff(float radians_a, float radians_b) {
    return std::fabs(angle_diff(radians_a, radians_b));
}

int sign(float value) {
    return (value > 0.0f) - (value < 0.0f);
}

}

StickVector normalize_vita_stick(const StickReading& reading) {
    if (!reading.valid) return {};
    return {normalize_axis(reading.lx), normalize_axis(reading.ly)};
}

AimDirection snap_aim_direction(const StickVector& aim) {
    if (aim.x == 0.0f && aim.y == 0.0f) return {};
    const float angle = std::atan2(aim.y, aim.x);
    const float threshold = pi / 8.0f - (angle < 0.0f ? negative_aim_threshold : 0.0f);
    if (abs_angle_diff(angle, 0.0f) < threshold) return {1, 0};
    if (abs_angle_diff(angle, pi) < threshold) return {-1, 0};
    if (abs_angle_diff(angle, -pi / 2.0f) < threshold) return {0, -1};
    if (abs_angle_diff(angle, pi / 2.0f) < threshold) return {0, 1};
    return {sign(aim.x), sign(aim.y)};
}

DirectionalInput DirectionalResolver::update(const DirectionalButtons& buttons, const StickVector& stick) {
    if (!std::isfinite(stick.x) || !std::isfinite(stick.y))
        throw std::invalid_argument("Nonfinite directional stick");

    const float right = std::max(0.0f, stick.x);
    const float left = std::max(0.0f, -stick.x);
    const float down = std::max(0.0f, stick.y);
    const float up = std::max(0.0f, -stick.y);

    move_x_ = integer_axis(binding_value(buttons.right, right, move_x_threshold),
                           binding_value(buttons.left, left, move_x_threshold),
                           move_x_, move_x_turned_);
    move_y_ = integer_axis(binding_value(buttons.down, down, move_y_threshold),
                           binding_value(buttons.up, up, move_y_threshold),
                           move_y_, move_y_turned_);

    aim_x_ = joystick_axis(binding_value(buttons.right, right, 0.0f),
                           binding_value(buttons.left, left, 0.0f),
                           aim_x_, aim_x_turned_);
    aim_y_ = joystick_axis(binding_value(buttons.down, down, 0.0f),
                           binding_value(buttons.up, up, 0.0f),
                           aim_y_, aim_y_turned_);
    if (std::sqrt(aim_x_ * aim_x_ + aim_y_ * aim_y_) < aim_radial_threshold) {
        aim_x_ = 0.0f;
        aim_y_ = 0.0f;
    }

    const auto aim = snap_aim_direction({aim_x_, aim_y_});
    return {move_x_, move_y_, aim.x, aim.y};
}

}
