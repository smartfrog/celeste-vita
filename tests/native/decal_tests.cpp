#include "assets.hpp"
#include "draw.hpp"
#include <iostream>
#include <stdexcept>
#include <string>
#include <utility>

using namespace celeste;
using namespace celeste::diagnostic;

namespace {
constexpr const char* input_sha = "fd73f8a2311fa5737ded550cbad4b75c85b7686b36432f59185e940fcb65fcfe";
constexpr const char* map_sha = "ace1892261c03aa766f45aaa38cb2cd60a8823c34eda673f5b2ed8ab31c890ab";

void expect(bool condition, const char* message) { if (!condition) throw std::runtime_error(message); }
template<class F> void rejects(F f) {
    try { f(); } catch (const std::invalid_argument&) { return; }
    throw std::runtime_error("Expected invalid decal rejection");
}

std::string texture_row(const std::string& name) { return name + " 1 1 8 8 0 0 16 16\n"; }

std::string decal_fixture() {
    std::string text = std::string("CSD1\n")+input_sha+"\n"+map_sha+"\n1\n64 128 00000001\n15\n";
    for (int i=0; i<15; ++i) text += texture_row("decals/generic/t" + std::to_string(i));
    text += "22\n";
    for (int i=0; i<20; ++i) {
        const bool flip = i == 8 || i == 10 || i == 13;
        text += "B " + std::to_string(i) + " " + std::to_string(i) + " " + std::to_string(i) + " " +
                (flip ? "-1" : "1") + " 1 " + std::to_string(i % 15) + "\n";
    }
    text += "F 0 48 32 1 1 0\nF 1 272 48 1 1 1\n";
    text += "7\nB 20 1-forsakencity/ragsB\nB 21 1-forsakencity/rags\nB 22 1-forsakencity/ragsB\n"
            "B 23 1-forsakencity/rags\nB 24 1-forsakencity/ragsB\n"
            "F 2 generic/grass_a\nF 3 generic/grass_d\n";
    return text;
}

void rejects_maximum_integer_crop_coordinates_parameterized() {
    for (const std::string values : {"2147483647 1 8 8", "1 2147483647 8 8", "1 1 2147483647 8",
                                     "1 1 8 2147483647", "2147483640 1 20 8", "1 2147483640 8 20",
                                     "-2147483648 1 8 8", "1 -2147483648 8 8", "1 1 -2147483648 8",
                                     "1 1 8 -2147483648", "0 1 8 8", "1 0 8 8", "1 1 0 8", "1 1 8 0",
                                     "1 1 -1 8", "1 1 8 -1", "1 1 63 8", "1 1 8 127"}) {
        auto text = decal_fixture();
        const std::string original = "decals/generic/t0 1 1 8 8";
        const auto offset = text.find(original);
        if (offset == std::string::npos) throw std::runtime_error("Missing first decal texture row");
        text.replace(offset, original.size(), "decals/generic/t0 " + values);
        rejects([&] { parse_decals(text,checksum(text)); });
    }
}
void accepts_legitimate_one_pixel_padding_boundary() {
    auto text = decal_fixture();
    const std::string original = "decals/generic/t0 1 1 8 8";
    text.replace(text.find(original), original.size(), "decals/generic/t0 1 1 62 126");
    const auto data = parse_decals(text,checksum(text));
    expect(data.texture_count == 15 && data.textures[0].u == 1 && data.textures[0].v == 1 &&
           data.textures[0].width == 62 && data.textures[0].height == 126,
           "Legitimate one-pixel interior padding boundary");
}

void parses_twenty_two_static_and_seven_explicit_banners() {
    const auto text = decal_fixture();
    const auto data = parse_decals(text,checksum(text));
    expect(data.texture_count == 15 && data.instances.size() == 22 && data.omitted.size() == 7,
           "Decal protocol count split");
    expect(data.instances[0].background && data.instances[19].background && !data.instances[20].background &&
           !data.instances[21].background, "Decal layer order");
    expect(data.omitted[0].name == "1-forsakencity/ragsB" && data.omitted[6].name == "generic/grass_d",
           "Explicit Banner omission list");
    expect(data.instances[8].scale_x == -1 && data.instances[8].scale_y == 1 &&
           data.instances[0].scale_x == 1 && data.instances[0].scale_y == 1, "Signed scale preservation");
}

void decal_geometry_uses_center_minus_draw_offset() {
    DecalTexture texture{ "decals/generic/hanginggrass_a",3,4,12,8,3,0,16,16 };
    DecalInstance instance{ false,0,0,48,32,1,1 };
    const auto vertices = decal_vertices(texture,instance);
    expect(vertices[0].x == 43 && vertices[0].y == 24 && vertices[1].x == 55 && vertices[1].y == 24 &&
           vertices[2].x == 55 && vertices[2].y == 32 && vertices[3].x == 43 && vertices[3].y == 32,
           "Decal center anchor and frame/draw-offset geometry");
    expect(vertices[0].u == 3.0f/64 && vertices[0].v == 4.0f/128 && vertices[1].u == 15.0f/64 &&
           vertices[2].v == 12.0f/128, "Decal crop UV rectangle with extruded page border");
}

void decal_geometry_preserves_both_negative_scale_axes() {
    DecalTexture texture{ "decals/1-forsakencity/collumn_small_broken",20,60,6,11,5,5,16,16 };
    DecalInstance vertical{ true,0,0,256,104,1,-1 };
    const auto down = decal_vertices(texture,vertical);
    expect(down[0].x == 253 && down[0].y == 107 && down[1].x == 259 && down[3].y == 96,
           "Vertical signed scale mirrors about Center-DrawOffset without a position heuristic");
    DecalTexture snow{ "decals/generic/snow_d",1,75,10,10,2,5,16,16 };
    DecalInstance horizontal{ true,8,11,82,128,-1,1 };
    const auto mirrored = decal_vertices(snow,horizontal);
    expect(mirrored[0].x == 88 && mirrored[1].x == 78 && mirrored[0].y == 125 && mirrored[3].y == 135,
           "Horizontal signed scale preserves the source UV order while flipping destination geometry");
    expect(mirrored[0].u < mirrored[1].u && mirrored[0].v < mirrored[3].v,
           "Negative scale must not reverse or abs the source UVs");
}

void rejects_malformed_decal_protocol_parameterized() {
    const auto base = decal_fixture();
    for (const std::string replacement : {"63 128 00000001", "64 127 00000001", "64 128 00000000",
                                          "64 128 00000001\n14", "64 128 00000001\n16"}) {
        auto text = base;
        text.replace(text.find("64 128 00000001"),15,replacement);
        rejects([&] { parse_decals(text,checksum(text)); });
    }
    {
        auto text = base;
        text.replace(text.find("decals/generic/t1 1 1 8 8"),std::string("decals/generic/t1 1 1 8 8").size(),
                     "decals/generic/t0 1 1 8 8");
        rejects([&] { parse_decals(text,checksum(text)); });
    }
    {
        auto text = base;
        text.replace(text.find("decals/generic/t0 1 1 8 8"),std::string("decals/generic/t0 1 1 8 8").size(),
                     "decals/generic/t0 60 1 8 8");
        rejects([&] { parse_decals(text,checksum(text)); });
    }
    {
        auto text = base;
        text.replace(text.find("B 19 19 19 1 1 4"),std::string("B 19 19 19 1 1 4").size(),
                     "B 0 19 19 1 1 4");
        rejects([&] { parse_decals(text,checksum(text)); });
    }
    {
        auto text = base;
        text.replace(text.find("B 19 19 19 1 1 4"),std::string("B 19 19 19 1 1 4").size(),
                     "B 19 19 19 0 1 4");
        rejects([&] { parse_decals(text,checksum(text)); });
    }
    {
        auto text = base;
        text.replace(text.find("F 0 48 32 1 1 0"),std::string("F 0 48 32 1 1 0").size(),
                     "B 0 48 32 1 1 0");
        rejects([&] { parse_decals(text,checksum(text)); });
    }
    {
        auto text = base;
        text.replace(text.find("B 20 1-forsakencity/ragsB"),std::string("B 20 1-forsakencity/ragsB").size(),
                     "B 20 1-forsakencity/rags");
        rejects([&] { parse_decals(text,checksum(text)); });
    }
    {
        auto text = base + "\n";
        rejects([&] { parse_decals(text,checksum(text)); });
    }
    {
        const auto text = base;
        rejects([&] { parse_decals(text,checksum(text)^1); });
    }
}
}

int main() {
    int failed = 0;
    for (auto [name,test] : {std::pair{"parses_twenty_two_static_and_seven_explicit_banners",parses_twenty_two_static_and_seven_explicit_banners},
                     std::pair{"rejects_maximum_integer_crop_coordinates_parameterized",rejects_maximum_integer_crop_coordinates_parameterized},
                     std::pair{"accepts_legitimate_one_pixel_padding_boundary",accepts_legitimate_one_pixel_padding_boundary},
                     std::pair{"decal_geometry_uses_center_minus_draw_offset",decal_geometry_uses_center_minus_draw_offset},
                     std::pair{"decal_geometry_preserves_both_negative_scale_axes",decal_geometry_preserves_both_negative_scale_axes},
                     std::pair{"rejects_malformed_decal_protocol_parameterized",rejects_malformed_decal_protocol_parameterized}}) {
        try { test(); } catch (const std::exception& error) { std::cerr << name << ": " << error.what() << '\n'; ++failed; }
    }
    std::cout << "decal cases=6 failed=" << failed << '\n';
    return failed ? 1 : 0;
}
