#include "assets.hpp"
#include "diagnostic.hpp"
#include <iostream>
#include <string>

using namespace celeste::diagnostic;
int main(int argc, char** argv) {
    try {
        if (argc != 3 && argc != 4) throw std::invalid_argument("Expected mask and hazards paths, optional --wall-jump");
        const auto mask = read_asset(argv[1],4'000'512), spikes = read_asset(argv[2],8192);
        Room room(parse_mask(mask,checksum(mask)),parse_spikes(spikes,checksum(spikes)));
        Session session(room.world);
        Controller controller;
        if (argc == 4 && std::string(argv[3]) == "--climb") {
            bool climbed = false, drained = false, released = false, landed = false;
            for (unsigned frame = 0; frame < 140; ++frame) {
                Controls controls;
                controls.left = frame < 30;
                controls.cross = frame < 4;
                controls.l = frame >= 12 && frame < 60;
                controls.up = frame >= 30 && frame < 45;
                session.step(controller.sample(controls));
                const auto& player = session.player();
                const auto& s = player.state();
                const auto pos = player.actor().body.position;
                std::cout << frame << " x=" << pos.x << " y=" << pos.y << " vx=" << s.speed.x << " vy=" << s.speed.y
                          << " state=" << player.state_machine().state() << " ground=" << s.on_ground << " stamina=" << s.stamina
                          << " grab=" << controls.l << " up=" << controls.up << '\n';
                climbed = climbed || player.state_machine().state() == 1;
                drained = drained || (player.state_machine().state() == 1 && !s.on_ground && s.stamina < 110.0f);
                released = released || (climbed && !controls.l && player.state_machine().state() == 0);
                landed = landed || (released && s.on_ground);
            }
            if (!climbed || !drained || !released || !landed) throw std::runtime_error("First-room Climb sequence lacks entry/drain/release/landing");
            return 0;
        }
        if (argc == 4) {
            if (std::string(argv[3]) != "--wall-jump") throw std::invalid_argument("Unknown replay mode");
            bool jumped = false;
            for (unsigned frame = 0; frame < 14; ++frame) {
                Controls controls;
                controls.left = true;
                controls.cross = frame < 4 || frame >= 5;
                session.step(controller.sample(controls));
                const auto& player = session.player();
                const auto& s = player.state();
                const auto pos = player.actor().body.position;
                std::cout << frame << " x=" << pos.x << " y=" << pos.y << " vx=" << s.speed.x << " vy=" << s.speed.y
                          << " move=" << s.move_x << " force=" << s.force_move_x << " force_timer=" << s.force_move_x_timer
                          << " var_timer=" << s.var_jump_timer << " buffer=" << player.jump_button().buffer_counter() << '\n';
                jumped = jumped || (s.speed.x == 130.0f && s.speed.y == -105.0f && s.force_move_x == 1 && s.force_move_x_timer == .16f);
            }
            if (!jumped) throw std::runtime_error("First-room sequence did not wall jump");
            return 0;
        }
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
