#include "assets.hpp"
#include "diagnostic.hpp"
#include <iostream>
#include <stdexcept>

using namespace celeste;
using namespace celeste::diagnostic;

namespace {
void expect(bool value, const char* message) { if (!value) throw std::runtime_error(message); }
template<class F> void rejects(F f) {
    try { f(); } catch (const std::invalid_argument&) { return; }
    throw std::runtime_error("Expected invalid_argument");
}
const std::string hashes = "fd73f8a2311fa5737ded550cbad4b75c85b7686b36432f59185e940fcb65fcfe\nace1892261c03aa766f45aaa38cb2cd60a8823c34eda673f5b2ed8ab31c890ab\n";
const std::string mask = "CSTM1\n" + hashes + "-8 -16 2 2\n1010\n";
const std::string spikes = "CSH1\n" + hashes + "2\nup 0 8 16\nleft 24 0 8\n";
void checksum_known_vector() { expect(checksum("hello") == 0x4f9f2cabu, "FNV-1a vector"); }
void mask_geometry() {
    const auto data = parse_mask(mask, checksum(mask));
    expect(data.x == -8 && data.y == -16 && data.columns == 2 && data.rows == 2 &&
           data.cells == std::vector<std::uint8_t>{1,0,1,0}, "Row-major mask geometry");
}
void mask_invalid_parameterized() {
    for (const std::string& bad : {std::string{}, "CSTM2\n" + mask.substr(6),
         "CSTM1\n" + std::string(64, '0') + "\n" + mask.substr(71),
         "CSTM1\n" + hashes + "0 0 0 2\n\n", "CSTM1\n" + hashes + "0 0 2147483647 2\n10\n",
         "CSTM1\n" + hashes + "2147483640 0 2 2\n1010\n", "CSTM1\n" + hashes + "-8 -16 2 2\n101\n",
         "CSTM1\n" + hashes + "-8 -16 2 2\n1020\n", mask + "\n", mask.substr(0, mask.size()-1),
         "CSTM1\n" + hashes + "-08 -16 2 2\n1010\n"}) {
        rejects([&] { parse_mask(bad, checksum(bad)); });
    }
}
void mask_corruption() { rejects([&] { parse_mask(mask, checksum(mask) ^ 1); }); }
void spike_geometry() {
    const auto data = parse_spikes(spikes, checksum(spikes));
    expect(data.size() == 2 && data[0].body().collider->height == 3 &&
           data[0].body().collider->width == 16 && data[1].body().collider->offset.x == -3 &&
           data[1].direction() == SpikeDirection::left, "Actual spike constructors");
}
void spike_invalid_parameterized() {
    for (const std::string& bad : {std::string{}, "CSH2\n" + spikes.substr(5),
         "CSH1\n" + hashes + "1\nright 0 0 8\n", "CSH1\n" + hashes + "1\nup 0 0 0\n",
         "CSH1\n" + hashes + "2\nup 0 0 8\n", spikes + "left 0 0 8\n",
         "CSH1\n" + hashes + "65\n", "CSH1\n" + hashes + "1\nup 2147483647 0 8\n"}) {
        rejects([&] { parse_spikes(bad, checksum(bad)); });
    }
}
void spike_corruption() { rejects([&] { parse_spikes(spikes, checksum(spikes) ^ 1); }); }
void missing_asset_fails_before_world() {
    try { read_asset("nonexistent-native-diagnostic-asset",32); }
    catch (const std::runtime_error& e) {
        expect(std::string(e.what()).find("Cannot open asset") != std::string::npos, "Preserve asset error context");
        return;
    }
    throw std::runtime_error("Missing asset accepted");
}
void button_edges() {
    Controller controller;
    expect(controller.sample({false,false,false,false,true}).player.jump.pressed, "Cross press");
    const auto held = controller.sample({false,false,false,false,true});
    expect(held.player.jump.held && !held.player.jump.pressed, "Cross hold");
    expect(!controller.sample({}).player.jump.held, "Cross release");
    expect(controller.sample({false,false,false,false,true}).player.jump.pressed, "Cross repress");
}
void opposing_axes_neutral() {
    Controller controller;
    const auto input = controller.sample({true,true,true,true}).player;
    expect(input.x == 0 && input.y == 0, "Opposing directions neutral");
}
void reset_edge() {
    Controller controller;
    const Controls reset{false,false,false,false,false,true};
    expect(controller.sample(reset).reset && !controller.sample(reset).reset, "Reset only rising edge");
}
void viewport_parameterized() {
    for (const auto size : {Viewport{0,2,960,540}, Viewport{0,90,320,180}}) {
        const auto v = letterbox(size.width, size.y*2+size.height);
        expect(v.x == size.x && v.y == size.y && v.width == size.width && v.height == size.height, "Integer letterbox");
    }
}
void invalid_viewport_parameterized() {
    for (const auto size : {Viewport{0,0,0,544}, Viewport{0,0,960,-1}, Viewport{0,0,1,1}})
        rejects([&] { letterbox(size.width, size.height); });
}
void reset_fresh_after_death() {
    StaticSpike spike({23,133}, 16, SpikeDirection::left);
    PlayerWorld world;
    world.spikes = {&spike};
    Session session(world);
    session.step({});
    expect(session.player().death().dead, "Actual accepted spike death");
    session.step({});
    session.step({{},true,false});
    expect(!session.player().death().dead && session.resets() == 1 &&
           session.player().actor().body.position.x == 19 && session.player().state().speed.x == 0 &&
           session.player().state().max_fall == 160 && session.player().actor().body.collidable,
           "Reset constructs fresh Player without a simulation step");
}
void exit_wins_over_reset() {
    PlayerWorld world;
    Session session(world);
    session.step({{},true,true});
    expect(session.exiting() && session.resets() == 0 && session.player().actor().body.position.y == 144, "Exit wins");
}
void diagnostic_clock_fixed() {
    PlayerWorld world;
    Session session(world);
    Player reference(world, {19,144});
    for (int i=0; i<10; ++i) { session.step({}); reference.frame(1.0f/60.0f); }
    expect(session.player().actor().body.position.y == reference.actor().body.position.y &&
           session.player().state().speed.y == reference.state().speed.y, "One sampled step is exactly 1/60 core frame");
}
}

int main() {
    int failed = 0;
    for (auto test : {checksum_known_vector, mask_geometry, mask_invalid_parameterized, mask_corruption,
         spike_geometry, spike_invalid_parameterized, spike_corruption, button_edges, opposing_axes_neutral,
         reset_edge, viewport_parameterized, invalid_viewport_parameterized, reset_fresh_after_death,
         exit_wins_over_reset, diagnostic_clock_fixed, missing_asset_fails_before_world}) {
        try { test(); } catch (const std::exception& e) { std::cerr << e.what() << '\n'; ++failed; }
    }
    std::cout << "diagnostic cases=16 failed=" << failed << '\n';
    return failed ? 1 : 0;
}
