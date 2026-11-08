#include "assets.hpp"
#include "draw.hpp"
#include <iostream>
#include <stdexcept>
#include <utility>

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
std::string spike_fixture() {
    std::string text = "CSRV2\nfd73f8a2311fa5737ded550cbad4b75c85b7686b36432f59185e940fcb65fcfe\nace1892261c03aa766f45aaa38cb2cd60a8823c34eda673f5b2ed8ab31c890ab\n8\n";
    for (int i=0; i<5; ++i) text += "64 128 48 120 0 0 48 120 00000000\n";
    text += "16 16 13 12 8 20 32 32 00000000\n16 16 7 6 1 1 7 6 00000000\n16 16 6 7 1 1 6 7 00000000\n";
    text += "2\nB 4 0 176 8 112\nF 0 8 0 0 0\n2\ndefault_up 1\ndefault_left 1\n2\n";
    return text + "up 40 163 7 6 1 1\nleft 267 81 6 7 1 1\n";
}
void parses_layered_commands() {
    const auto text = fixture();
    const auto data = parse_visuals(text,checksum(text));
    expect(data.texture_count == 6 && data.commands.size() == 2 && data.commands[0].background &&
           data.commands[0].y == 176 && !data.commands[1].background, "Checked BG/FG command ordering and clipped final row");
}
void parses_source_spike_protocol() {
    const auto text = spike_fixture();
    const auto data = parse_visuals(text,checksum(text));
    expect(data.texture_count == 8 && data.spike_art() && data.spike_pieces.size() == 2 &&
           data.spike_pieces[0].up && data.spike_pieces[0].x == 40 && data.spike_pieces[0].y == 163 &&
           !data.spike_pieces[1].up && data.spike_pieces[1].x == 267 && data.spike_pieces[1].y == 81 &&
           VisualAssets::body_texture == 5 && VisualAssets::up_texture == 6 && VisualAssets::left_texture == 7,
           "Source spike image protocol and non-aliased texture slots");
}
void spike_geometry_uses_extruded_border() {
    const auto data = parse_visuals(spike_fixture(),checksum(spike_fixture()));
    const auto up = spike_quad(data.textures[VisualAssets::up_texture],data.spike_pieces[0]);
    const auto left = spike_quad(data.textures[VisualAssets::left_texture],data.spike_pieces[1]);
    expect(up.x == 40 && up.y == 163 && up.width == 7 && up.height == 6 &&
           up.u0 == 1.0f/16 && up.u1 == 8.0f/16 && up.v0 == 1.0f/16 && up.v1 == 7.0f/16 &&
           left.x == 267 && left.y == 81 && left.width == 6 && left.height == 7 &&
           left.u0 == 1.0f/16 && left.u1 == 7.0f/16 && left.v0 == 1.0f/16 && left.v1 == 8.0f/16,
           "Source spike quad and one-pixel extruded UV border");
}
void validates_spike_art_against_hazards() {
    const auto data = parse_visuals(spike_fixture(),checksum(spike_fixture()));
    const std::vector<StaticSpike> spikes{StaticSpike({40,168},8,SpikeDirection::up),
                                           StaticSpike({272,80},8,SpikeDirection::left)};
    validate_spike_art(data,spikes);
    const std::vector<StaticSpike> wrong{StaticSpike({48,168},8,SpikeDirection::up),
                                         StaticSpike({272,80},8,SpikeDirection::left)};
    rejects([&] { validate_spike_art(data,wrong); });
    rejects([&] { validate_spike_art(parse_visuals(fixture(),checksum(fixture())),spikes); });
}
void rejects_invalid_spike_protocol_parameterized() {
    for (const std::string replacement : {"1\ndefault_up 1", "3\ndefault_up 1", "2\ndefault_up 2",
                                          "2\ndefault_up 1\ndefault_left 1\n1\nup 40 163 6 6 1 1",
                                          "2\ndefault_up 1\ndefault_left 1\n1\nright 40 163 7 6 1 1",
                                          "2\ndefault_up 1\ndefault_left 1\n1\nup 40 163 7 6 0 1",
                                          "2\ndefault_up 1\ndefault_left 1\n1\nup 2000000 163 7 6 1 1",
                                          "2\ndefault_up 1\ndefault_left 1\n1\nup 40 163 7 6 1 1\nextra"}) {
        auto text = spike_fixture();
        const auto start = text.find("2\ndefault_up");
        text.replace(start,text.size()-start,replacement+"\n");
        rejects([&] { parse_visuals(text,checksum(text)); });
    }
    auto text = spike_fixture();
    text.replace(text.find("16 16 7 6"),9,"16 16 8 6");
    rejects([&] { parse_visuals(text,checksum(text)); });
}
void rejects_trailing_source_spike_data() {
    auto text = spike_fixture()+"\n";
    rejects([&] { parse_visuals(text,checksum(text)); });
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
    for (auto [name,test] : {std::pair{"parses_layered_commands",parses_layered_commands},
                     std::pair{"parses_source_spike_protocol",parses_source_spike_protocol},
                     std::pair{"spike_geometry_uses_extruded_border",spike_geometry_uses_extruded_border},
                     std::pair{"validates_spike_art_against_hazards",validates_spike_art_against_hazards},
                     std::pair{"rejects_invalid_spike_protocol_parameterized",rejects_invalid_spike_protocol_parameterized},
                     std::pair{"rejects_trailing_source_spike_data",rejects_trailing_source_spike_data},
                     std::pair{"rejects_visual_corruption",rejects_visual_corruption},
                     std::pair{"rejects_invalid_commands_parameterized",rejects_invalid_commands_parameterized},
                     std::pair{"rejects_wrong_texture_profile",rejects_wrong_texture_profile},
                     std::pair{"rejects_trailing_visual_data",rejects_trailing_visual_data},
                     std::pair{"validates_exact_texture_bytes",validates_exact_texture_bytes},
                     std::pair{"rejects_texture_corruption",rejects_texture_corruption},
                     std::pair{"right_facing_trim_and_uv",right_facing_trim_and_uv},
                     std::pair{"left_facing_trim_and_uv",left_facing_trim_and_uv},
                     std::pair{"tile_uv_uses_border_without_resample",tile_uv_uses_border_without_resample}}) {
        try { test(); } catch (const std::exception& error) { std::cerr << name << ": " << error.what() << '\n'; ++failed; }
    }
    std::cout << "visual cases=15 failed=" << failed << '\n';
    return failed ? 1 : 0;
}
