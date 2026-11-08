#include "assets.hpp"
#include "diagnostic.hpp"
#include <iostream>

using namespace celeste::diagnostic;
int main(int argc, char** argv) {
    try {
        if (argc != 3) throw std::invalid_argument("Expected mask and hazards paths");
        const auto mask = read_asset(argv[1],4'000'512), spikes = read_asset(argv[2],8192);
        Room room(parse_mask(mask,checksum(mask)),parse_spikes(spikes,checksum(spikes)));
        Session session(room.world);
        Controller controller;
        for (unsigned frame=0; frame<240; ++frame) {
            Controls controls;
            controls.cross = frame >= 5 && frame < 15;
            controls.right = frame >= 70;
            session.step(controller.sample(controls));
            const auto& player = session.player();
            if (frame%5 == 0 || player.death().dead)
                std::cout << frame << " x=" << player.actor().body.position.x << " y=" << player.actor().body.position.y
                          << " vy=" << player.state().speed.y << " ground=" << player.state().on_ground
                          << " dead=" << player.death().dead << '\n';
            if (player.death().dead) return 0;
        }
        throw std::runtime_error("Bounded replay did not reach actual spike death");
    } catch (const std::exception& error) { std::cerr << error.what() << '\n'; return 1; }
}
