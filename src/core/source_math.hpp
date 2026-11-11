#pragma once

#include "movement.hpp"
#include <algorithm>
#include <cmath>

namespace celeste::source_math {

inline float approach(float value,float target,float amount) {
    return value>target ? std::max(value-amount,target) : std::min(value+amount,target);
}
inline float cube_out(float value) {
    const float inverse=1.f-value;
    return 1.f-inverse*inverse*inverse;
}
inline Vec2 angle_to_vector(float angle,float length) {
    return {static_cast<float>(std::cos(double(angle)))*length,static_cast<float>(std::sin(double(angle)))*length};
}
inline float angle_approach(float value,float target,float step) {
    constexpr float pi=3.14159265358979323846f;
    float difference=target-value;
    while(difference>pi) difference-=pi*2.f;
    while(difference<=-pi) difference+=pi*2.f;
    return std::abs(difference)<step ? target : value+std::clamp(difference,-step,step);
}

}
