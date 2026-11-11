#include "assets.hpp"
#include "diagnostic.hpp"
#include "draw.hpp"
#include "lifecycle.hpp"
#include <fstream>
#include <iomanip>
#include <iostream>
#include <limits>

using namespace celeste;
using namespace celeste::diagnostic;

namespace {
void vec(Vec2 value) { std::cout<<'['<<value.x<<','<<value.y<<']'; }
void color(PresentationColor value) { std::cout<<'['<<int(value.r)<<','<<int(value.g)<<','<<int(value.b)<<','<<int(value.a)<<']'; }
void optional(float value) { if(value<0) std::cout<<"null"; else std::cout<<value; }
void record(int tick,FirstRoomSession& session,const PlayerFrameBank& bank) {
    const auto draws=session.draw();
    const auto p=session.projection();
    const auto& pose=session.presentation().pose();
    const auto& stats=session.stats();
    const auto& context=session.context();
    const auto* tween=session.committed_corpse() ? nullptr : session.player().respawn_tween();
    std::cout<<"{\"tick\":"<<tick<<",\"phase\":\""<<session.phase()<<"\",\"position\":";vec(p.position);
    std::cout<<",\"speed\":";vec(session.player().state().speed);
    std::cout<<",\"state\":"<<session.player().state_machine().state()<<",\"dead\":"<<session.player().death().dead
        <<",\"frameCounter\":"<<context.clock.frame_counter<<",\"freeze\":"<<context.clock.freeze_timer
        <<",\"sceneRan\":"<<session.scene_ran()<<",\"timeActive\":"<<session.time_active()
        <<",\"rawTimeActive\":"<<session.raw_time_active()
        <<",\"bufferBeforeScene\":"<<session.buffer_before_scene()<<",\"bufferAfterScene\":"<<context.jump.buffer_counter()
        <<",\"jumpPressedBeforeScene\":"<<session.pressed_before_scene()<<",\"moveX\":"<<p.raw_x
        <<",\"jumpCheck\":"<<context.jump.check()<<",\"jumpReleased\":"<<context.jump.released()
        <<",\"rngCalls\":"<<session.random().calls()<<",\"animation\":\""<<pose.animation<<"\",\"animationFrame\":"<<pose.animation_frame
        <<",\"animationTimer\":"<<pose.timer<<",\"wave\":"<<pose.wave<<",\"spriteScale\":";vec(pose.scale);
    std::cout<<",\"spriteRotation\":"<<pose.rotation<<",\"hasHair\":"<<bank.frames[pose.frame].has_hair
        <<",\"hairFacing\":"<<pose.hair_facing<<",\"hairColor\":";color(pose.hair_color);
    std::cout<<",\"hairNodes\":[";
    for(unsigned i=0;i<4;++i) { if(i)std::cout<<',';vec(pose.hair_nodes[i]); }
    std::cout<<"],\"introEase\":";
    if(session.committed_corpse()) std::cout<<"null"; else std::cout<<session.player().intro_ease();
    std::cout<<",\"deadOffset\":";
    if(session.committed_corpse()) std::cout<<"null"; else vec(session.player().dead_offset());
    std::cout<<",\"effectPercent\":";optional(session.effect_percent());
    std::cout<<",\"tweenTime\":";optional(tween ? tween->time_left : session.corpse_tween_time());
    std::cout<<",\"pendingCorpses\":"<<int(session.pending_corpse())<<",\"committedCorpses\":"<<int(session.committed_corpse())
        <<",\"jumps\":"<<stats.jumps<<",\"sessionDeaths\":"<<stats.session_deaths<<",\"roomDeaths\":"<<stats.room_deaths
        <<",\"saveDeaths\":"<<stats.save_deaths<<",\"sessionTime\":"<<stats.session_time<<",\"reloads\":"<<stats.reloads
        <<",\"loads\":"<<stats.loads<<",\"respawnCallbacks\":"<<stats.respawn_callbacks<<",\"wipeCallbacks\":"<<stats.wipe_callbacks
        <<",\"rawHazards\":"<<session.world().spikes.size()
        <<",\"scopedRoomRandomCalls\":"<<stats.scoped_room_random_calls
        <<",\"corpseAdds\":"<<stats.corpse_adds<<",\"corpseCommits\":"<<stats.corpse_commits<<",\"corpseRemoves\":"<<stats.corpse_removes
        <<",\"randomEvents\":[";
    bool first=true;
    for(const auto& event:session.random_events()) {
        if(!first)std::cout<<','; first=false;
        std::cout<<"{\"phase\":\""<<event.phase<<"\",\"operation\":\""<<event.operation<<"\",\"calls\":"<<event.calls<<'}';
    }
    std::cout<<"],\"callbacks\":[";first=true;
    for(const auto& callback:session.callbacks()) {
        if(!first)std::cout<<',';first=false;
        std::cout<<"{\"callback\":\""<<callback.name<<"\",\"invocations\":1";
        if(callback.name=="respawn-tween") {
            std::cout<<",\"stateBefore\":"<<callback.state_before<<",\"stateAfter\":"<<callback.state_after<<",\"scaleAfter\":";vec(callback.scale);
            std::cout<<",\"maxFall\":"<<callback.max_fall<<",\"timeLeft\":"<<callback.time_left<<",\"percent\":"<<callback.percent;
        } else std::cout<<",\"Completed\":"<<callback.completed<<",\"ending\":"<<callback.ending;
        std::cout<<'}';
    }
    std::cout<<"],\"draws\":[";first=true;
    for(const auto& draw:draws) {
        if(!first)std::cout<<','; first=false;
        const auto& frame=bank.frames[draw.frame];
        std::cout<<"{\"texture\":\""<<frame.name<<"\",\"position\":";vec(draw.position);
        std::cout<<",\"origin\":";vec(draw.origin);
        std::cout<<",\"scale\":";vec(draw.scale);
        std::cout<<",\"Rotation\":"<<draw.rotation<<",\"color\":";color(draw.color);
        std::cout<<",\"vertices\":[";
        unsigned index=0;
        for(const auto& vertex:player_vertices(frame,draw)) {
            if(index++)std::cout<<',';
            std::cout<<"{\"position\":["<<vertex.x<<','<<vertex.y<<",0],\"uv\":["<<vertex.u<<','<<vertex.v<<"]}";
        }
        std::cout<<"]}";
    }
    std::cout<<"],\"wipe\":";
    if(const auto* wipe=session.wipe()) {
        std::cout<<"{\"WipeIn\":"<<wipe->wipe_in<<",\"Percent\":"<<wipe->percent<<",\"Completed\":"<<wipe->completed<<",\"ending\":"<<wipe->ending<<",\"vertices\":[";
        first=true;
        for(const auto& vertex:wipe->vertices()) {
            if(!first)std::cout<<',';first=false;
            std::cout<<"{\"position\":["<<vertex.position.x<<','<<vertex.position.y<<",0],\"color\":";color(vertex.color);std::cout<<'}';
        }
        std::cout<<"]}";
    } else std::cout<<"null";
    std::cout<<"}\n";
}
}

int main(int argc,char** argv) {
    try {
        if(argc!=6) throw std::invalid_argument("Expected mask, hazards, player metadata, input fixture, checkpoint flag");
        const auto mask=read_asset(argv[1],4'000'512),hazards=read_asset(argv[2],8192),player=read_asset(argv[3],65'536);
        Room room(parse_mask(mask,checksum(mask)),parse_spikes(hazards,checksum(hazards)));
        const auto assets=parse_player_assets(player,checksum(player));
        const std::string checkpoint=argv[5];
        if(checkpoint!="0" && checkpoint!="1") throw std::invalid_argument("Invalid checkpoint flag");
        FirstRoomSession session(room.world,assets.bank,checkpoint=="1");
        Controller controller;
        std::ifstream inputs(argv[4]);
        if(!inputs) throw std::runtime_error("Cannot read lifecycle input fixture");
        std::cout<<std::setprecision(std::numeric_limits<float>::max_digits10)<<std::boolalpha;
        record(-1,session,assets.bank);
        int tick=0,x=0,jump=0,expected=0;
        while(inputs>>tick>>x>>jump) {
            if(tick!=expected++ || x<-1 || x>1 || (jump!=0 && jump!=1)) throw std::invalid_argument("Invalid lifecycle input order/value");
            Controls controls;controls.left=x<0;controls.right=x>0;controls.cross=jump;
            session.step(1.f/60,controller.sample(controls).player);
            record(tick,session,assets.bank);
        }
        if(!inputs.eof() || expected!=364) throw std::invalid_argument("Incomplete bounded lifecycle fixture");
    } catch(const std::exception& error) { std::cerr<<error.what()<<'\n';return 1; }
}
