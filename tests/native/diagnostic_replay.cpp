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
        bool dashed = false, freeze_crossed = false, dash_exited = false;
        for (unsigned frame=0; frame<360; ++frame) {
            Controls controls;
            controls.cross = frame >= 5 && frame < 15;
            controls.up = frame >= 70 && frame < 75;
            controls.square = frame == 70;
            controls.right = frame >= 150;
            session.step(controller.sample(controls));
            const auto& player = session.player();
            dashed = dashed || player.state_machine().state() == 2;
            freeze_crossed = freeze_crossed || (dashed && player.clock().freeze_timer == 0.0f);
            dash_exited = dash_exited || (dashed && player.state_machine().state() == 0);
            if (frame%5 == 0 || player.death().dead)
                std::cout << frame << " x=" << player.actor().body.position.x << " y=" << player.actor().body.position.y
                          << " vy=" << player.state().speed.y << " ground=" << player.state().on_ground
                          << " dead=" << player.death().dead << '\n';
            if (player.death().dead) {
                if (!dashed || !freeze_crossed || !dash_exited) throw std::runtime_error("Missing Dash/freeze/Normal transitions before death");
                return 0;
            }
        }
        throw std::runtime_error("Bounded replay did not reach actual spike death");
    } catch (const std::exception& error) { std::cerr << error.what() << '\n'; return 1; }
}
