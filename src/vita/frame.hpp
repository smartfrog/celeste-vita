#pragma once

#include <cstdint>
#include <string>
#include <vector>

namespace celeste::diagnostic {
std::string encode_frame_ppm(int width, int height, const std::vector<std::uint8_t>& bottom_up_rgb);
}
