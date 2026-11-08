#include "assets.hpp"
#include "draw.hpp"
#include <iostream>
#include <stdexcept>

using namespace celeste;
using namespace celeste::diagnostic;

namespace {
void expect(bool condition, const char* message) { if (!condition) throw std::runtime_error(message); }
template<class F> void rejects(F f) {
    try { f(); } catch (const std::invalid_argument&) { return; }
    throw std::runtime_error("Expected invalid visual rejection");
}
std::string fixture() {
    std::string text = "CSRV1\nfd73f8a2311fa5737ded550cbad4b75c85b7686b36432f59185e940fcb65fcfe\nace1892261c03aa766f45aaa38cb2cd60a8823c34eda673f5b2ed8ab31c890ab\n6\n";
    for (int i=0; i<5; ++i) text += "64 128 48 120 0 0 48 120 00000000\n";
    return text + "16 16 13 12 8 20 32 32 00000000\n2\nB 4 0 176 8 112\nF 0 8 0 0 0\n";
}
void parses_layered_commands() {
    const auto text = fixture();
    const auto data = parse_visuals(text,checksum(text));
    expect(data.textures.size() == 6 && data.commands.size() == 2 && data.commands[0].background &&
           data.commands[0].y == 176 && !data.commands[1].background, "Checked BG/FG command ordering and clipped final row");
}
void rejects_visual_corruption() { const auto text = fixture(); rejects([&] { parse_visuals(text,checksum(text)^1); }); }
void rejects_invalid_commands_parameterized() {
    for (const std::string replacement : {"F 6 8 0 0 0", "F 5 8 0 0 0", "F 0 320 0 0 0", "F 0 8 184 0 0",
                                         "F 0 8 0 48 0", "F 0 8 0 -1 0", "B 4 0 176 8 112", "F 0 08 0 0 0"}) {
        auto text = fixture();
        text.replace(text.find("F 0 8 0 0 0"),11,replacement);
        rejects([&] { parse_visuals(text,checksum(text)); });
    }
}
void rejects_wrong_texture_profile() {
    auto text = fixture(); text.replace(text.find("64 128"),6,"32 128");
    rejects([&] { parse_visuals(text,checksum(text)); });
}
void rejects_trailing_visual_data() { auto text = fixture()+"\n"; rejects([&] { parse_visuals(text,checksum(text)); }); }
void validates_exact_texture_bytes() {
    auto info = parse_visuals(fixture(),checksum(fixture())).textures[0];
    std::string pixels(64*128*4,'\0'); info.checksum = checksum(pixels);
    validate_texture_bytes(pixels,info);
}
void rejects_texture_corruption() {
    auto info = parse_visuals(fixture(),checksum(fixture())).textures[0];
    std::string pixels(64*128*4,'\0'); info.checksum = checksum(pixels)^1;
    rejects([&] { validate_texture_bytes(pixels,info); });
}
void right_facing_trim_and_uv() {
    const auto info = parse_visuals(fixture(),checksum(fixture())).textures[5];
    const auto quad = body_quad(info,{19,144},1);
    expect(quad.x == 11 && quad.y == 132 && quad.width == 13 && quad.height == 12 &&
           quad.u0 == 1.0f/16 && quad.u1 == 14.0f/16 && quad.v0 == 1.0f/16 && quad.v1 == 13.0f/16,
           "Right-facing source trim, source origin, pixel-border UV and top-down texture orientation");
}
void left_facing_trim_and_uv() {
    const auto info = parse_visuals(fixture(),checksum(fixture())).textures[5];
    const auto quad = body_quad(info,{25,140},-1);
    expect(quad.x == 20 && quad.y == 128 && quad.u0 == 14.0f/16 && quad.u1 == 1.0f/16,
           "Left-facing geometry mirrors frame about source origin, not a fixed spawn offset");
}
void tile_uv_uses_border_without_resample() {
    const auto data = parse_visuals(fixture(),checksum(fixture()));
    const auto quad = tile_quad(data.textures[4],data.commands[0]);
    expect(quad.y == 176 && quad.height == 8 && quad.u0 == 9.0f/64 && quad.u1 == 17.0f/64 && quad.v0 == 113.0f/128,
           "Source 8x8 tile texels use one extruded border and preserve clipped 23rd row geometry");
}
}

int main() {
    int failed = 0;
    for (auto test : {parses_layered_commands,rejects_visual_corruption,rejects_invalid_commands_parameterized,
                     rejects_wrong_texture_profile,rejects_trailing_visual_data,validates_exact_texture_bytes,
                     rejects_texture_corruption,right_facing_trim_and_uv,left_facing_trim_and_uv,tile_uv_uses_border_without_resample}) {
        try { test(); } catch (const std::exception& error) { std::cerr << error.what() << '\n'; ++failed; }
    }
    std::cout << "visual cases=10 failed=" << failed << '\n';
    return failed ? 1 : 0;
}
