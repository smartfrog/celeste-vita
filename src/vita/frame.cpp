#include "frame.hpp"
#include <stdexcept>

namespace celeste::diagnostic {
std::string encode_frame_ppm(int width, int height, const std::vector<std::uint8_t>& bottom_up_rgba) {
    if (width <= 0 || height <= 0 || width > 960 || height > 544)
        throw std::invalid_argument("Frame dimensions exceed bounded 960x544 export");
    if (bottom_up_rgba.size() != static_cast<std::size_t>(width)*height*4)
        throw std::invalid_argument("Wrong RGBA frame length");
    std::string ppm = "P6\n" + std::to_string(width) + " " + std::to_string(height) + "\n255\n";
    ppm.reserve(ppm.size()+static_cast<std::size_t>(width)*height*3);
    for (int y=height-1; y>=0; --y) {
        for (int x=0; x<width; ++x) {
            const auto offset = (static_cast<std::size_t>(y)*width+x)*4;
            ppm.append(reinterpret_cast<const char*>(bottom_up_rgba.data()+offset),3);
        }
    }
    return ppm;
}
}
