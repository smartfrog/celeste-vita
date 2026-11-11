#include "assets.hpp"
#include "diagnostic.hpp"
#include "draw.hpp"
#include "guest_dash_probe.hpp"
#include <iomanip>
#include <iostream>
#include <limits>

using namespace celeste;
using namespace celeste::diagnostic;
namespace {
void vec(Vec2 p){std::cout<<'['<<p.x<<','<<p.y<<']';}
void record_draw(const PlayerDraw& d,const PlayerFrameBank& bank) {
    const auto& f=bank.frames.at(d.frame);
    std::cout<<"{\"texture\":\""<<f.name<<"\",\"position\":";vec(d.position);
    std::cout<<",\"origin\":";vec(d.origin);std::cout<<",\"scale\":";vec(d.scale);
    const auto c=d.color;
    std::cout<<",\"rotation\":"<<d.rotation<<",\"color\":["<<int(c.r)<<','<<int(c.g)<<','<<int(c.b)<<','<<int(c.a)<<"],\"vertices\":[";
    bool first=true;for(const auto& v:player_vertices(f,d)){if(!first)std::cout<<',';first=false;std::cout<<"["<<v.x<<','<<v.y<<"]";}
    std::cout<<"]}";
}
}
int main(int argc,char** argv) {
    try {
        if(argc!=5) throw std::invalid_argument("Expected mask, hazards, player metadata and scenario");
        const auto mask=read_asset(argv[1],4'000'512),hazards=read_asset(argv[2],8192),metadata=read_asset(argv[3],65'536);
        Room room(parse_mask(mask,checksum(mask)),parse_spikes(hazards,checksum(hazards)));
        const auto assets=parse_player_assets(metadata,checksum(metadata));FirstRoomSession session(room.world,assets.bank);Controller controller;
        const std::string scenario=argv[4];
        std::cout<<std::setprecision(std::numeric_limits<float>::max_digits10)<<std::boolalpha;
        for(unsigned tick=0;tick<guest_dash_probe_frames;++tick) {
            const auto input=controller.sample(dash_probe_controls(tick,scenario));
            session.step(1.f/60,input.player);
            auto& trails=session.trails();
            if(tick==39 && scenario=="capacity") trails.add(session.projection(),session.presentation().pose());
            if(tick==40 && (scenario=="capacity" || scenario=="fractional")) {
                auto projection=session.projection();
                if(scenario=="fractional") projection.position={19.25f,144.75f};
                for(unsigned i=0;i<(scenario=="capacity" ? 65u : 1u);++i) trails.add(projection,session.presentation().pose());
            }
            std::cout<<"{\"tick\":"<<tick<<",\"slots\":[";
            bool first=true;for(unsigned i=0;i<64;++i) {
                const auto& s=trails.slots()[i];if(!s.occupied)continue;
                if(!first)std::cout<<',';first=false;
                std::cout<<"{\"Index\":"<<i<<",\"Percent\":"<<s.percent<<",\"Drawn\":"<<s.drawn<<",\"committed\":"<<s.committed<<",\"position\":";
                vec(s.position);std::cout<<",\"scale\":";vec(s.scale);std::cout<<'}';
            }
            std::cout<<"],\"captures\":[";first=true;
            const auto calls=session.random().calls();
            trails.before_render(session.presentation(),session.projection(),[&](unsigned slot,const auto& draws){
                if(!first)std::cout<<',';first=false;std::cout<<"{\"slot\":"<<slot<<",\"draws\":[";
                bool first_draw=true;for(const auto& draw:draws){if(!first_draw)std::cout<<',';first_draw=false;record_draw(draw,assets.bank);}std::cout<<"]}";
            });
            std::cout<<"],\"ghosts\":[";first=true;
            for(auto slot:trails.render_order()) {
                if(!first)std::cout<<',';first=false;const auto c=PlayerTrails::faded_color(trails.slots()[slot]);
                std::cout<<"{\"slot\":"<<slot<<",\"color\":["<<int(c.r)<<','<<int(c.g)<<','<<int(c.b)<<','<<int(c.a)<<"]}";
            }
            std::cout<<"],\"liveDraws\":[";first=true;
            for(const auto& draw:session.draw()) {if(!first)std::cout<<',';first=false;record_draw(draw,assets.bank);}
            if(calls!=session.random().calls()) throw std::runtime_error("Trail capture/draw consumed RNG");
            std::cout<<"],\"sceneRan\":"<<session.scene_ran()<<",\"state\":"<<session.player().state_machine().state()<<",\"dead\":"<<session.player().death().dead<<",\"reloads\":"<<session.stats().reloads<<"}\n";
        }
    } catch(const std::exception& e){std::cerr<<e.what()<<'\n';return 1;}
}
