#include "assets.hpp"
#include "diagnostic.hpp"
#include <iostream>
#include <string>

using namespace celeste::diagnostic;
int main(int argc, char** argv) {
    try {
        if (argc != 3 && argc != 4 && argc != 5) throw std::invalid_argument("Expected mask and hazards paths, optional replay mode");
        const auto mask = read_asset(argv[1],4'000'512), spikes = read_asset(argv[2],8192);
        Room room(parse_mask(mask,checksum(mask)),parse_spikes(spikes,checksum(spikes)));
        std::optional<PlayerAssets> assets;
        if(argc==5) {
            if(std::string(argv[3])!="--presentation") throw std::invalid_argument("Unknown presentation replay mode");
            const auto bytes=read_asset(argv[4],65'536);
            assets=parse_player_assets(bytes,checksum(bytes));
        }
        Session session(room.world,{19,144},assets ? &assets->bank : nullptr,0);
        Controller controller;
        if(assets) {
            bool jumped=false,climbed=false,moving_frame=false,released=false,dashed=false,landed=false;
            for(unsigned frame=0;frame<240;++frame) {
                Controls controls;
                controls.left=frame<30;controls.cross=frame<4;controls.l=frame>=12 && frame<60;
                controls.up=(frame>=30 && frame<45) || (frame>=90 && frame<95);controls.square=frame==90;
                session.step(controller.sample(controls));
                const auto& player=session.player();const auto& p=player.state();
                const auto& pose=session.presentation()->pose();
                session.presentation()->draw(session.projection());
                jumped=jumped || player.jump_count()>0;
                climbed=climbed || player.state_machine().state()==1;
                moving_frame=moving_frame || (player.state_machine().state()==1 && p.speed.y<0 && pose.animation=="climbUp" && pose.animation_frame>0);
                released=released || (climbed && !controls.l && player.state_machine().state()==0);
                dashed=dashed || (released && player.state_machine().state()==2);
                landed=landed || (dashed && frame>120 && p.on_ground);
                std::cout<<frame<<" x="<<player.actor().body.position.x<<" y="<<player.actor().body.position.y<<" state="<<player.state_machine().state()
                    <<" vy="<<p.speed.y<<" ground="<<p.on_ground<<" stamina="<<p.stamina<<" grab="<<controls.l
                    <<" animation="<<pose.animation<<" frame="<<pose.animation_frame<<" hair="<<pose.hair_nodes[0].x<<','<<pose.hair_nodes[0].y<<'\n';
            }
            if(!jumped || !climbed || !moving_frame || !released || !dashed || !landed)
                throw std::runtime_error("First-room animated replay lacks Jump/Climb/moving body+hair/release/Dash/landing coverage");
            return 0;
        }
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
