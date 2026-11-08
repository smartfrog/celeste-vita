#include "frame.hpp"
#include <iostream>
#include <stdexcept>
#include <utility>

using namespace celeste::diagnostic;

namespace {
void expect(bool condition, const char* message) { if (!condition) throw std::runtime_error(message); }
template<class F> void rejects(F f) {
    try { f(); } catch (const std::invalid_argument&) { return; }
    throw std::runtime_error("Expected invalid frame rejection");
}
void flips_rows_and_preserves_rgb_channels() {
    const std::vector<std::uint8_t> pixels{0,0,255,255,255,255,255,0,0,0,255,0};
    const auto ppm = encode_frame_ppm(2,2,pixels);
    const std::string expected = std::string("P6\n2 2\n255\n") + std::string("\xff\0\0\0\xff\0\0\0\xff\xff\xff\xff",12);
    expect(ppm == expected,"OpenGL bottom-up packed RGB must become top-down P6 RGB without row padding");
}
void rejects_invalid_dimensions_parameterized() {
    for (const auto size : {std::pair<int,int>{0,1},{1,0},{961,1},{1,545},{-1,1}})
        rejects([&] { encode_frame_ppm(size.first,size.second,{}); });
}
void rejects_truncated_rgb() { rejects([] { encode_frame_ppm(1,1,{1,2}); }); }
void full_frame_has_exact_payload_length() {
    const auto ppm = encode_frame_ppm(960,544,std::vector<std::uint8_t>(960*544*3));
    expect(ppm.size() == std::string("P6\n960 544\n255\n").size()+960*544*3,"Full framebuffer payload length");
}
}

int main() {
    int failed = 0;
    for (auto test : {flips_rows_and_preserves_rgb_channels,rejects_invalid_dimensions_parameterized,
                      rejects_truncated_rgb,full_frame_has_exact_payload_length}) {
        try { test(); } catch (const std::exception& error) { std::cerr << error.what() << '\n'; ++failed; }
    }
    std::cout << "frame export cases=4 failed=" << failed << '\n';
    return failed ? 1 : 0;
}
