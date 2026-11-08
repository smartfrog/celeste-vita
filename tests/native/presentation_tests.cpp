#include "presentation.hpp"
#include "draw.hpp"
#include "diagnostic.hpp"
#include <cmath>
#include <iostream>
#include <stdexcept>

using namespace celeste;

namespace {
void require(bool condition, const char* message) {
    if (!condition) throw std::runtime_error(message);
}
PlayerFrameBank bank() {
    PlayerFrameBank b;
    b.pages = 1;
    for (int i=0; i<3; ++i) b.frames.push_back({"synthetic"+std::to_string(i),0,1,1,10,10,0,0,32,32,{float(i),-2},i,true});
    for (const char* id : {"idle","idleA","idleB","idleC","runSlow","runFast","runStumble","flip","skid","jumpSlow","jumpFast","fallSlow","fallFast","duck","edge","edgeBack","push","lookUp","climbUp","climbLookBackStart","climbLookBack","dangling","wallslide","dash"})
        b.animations.push_back({id,0.1f,id,{0,1,2}});
    b.bangs = {0,1,2}; b.hair=0;
    return b;
}
PlayerProjection grounded() {
    PlayerProjection p;
    p.position = {20,160}; p.on_ground = true;
    p.solid_point = [](Vec2 p) {return p.y>=160;};
    p.solid_body = [](Vec2 p) {return p.y>160;};
    p.jump_thru_body = [](Vec2) {return false;};
    return p;
}
void animation_advances_before_selection() {
    auto b=bank(); auto p=grounded(); PlayerPresentation v(b,p.position);
    v.observe(PlayerCosmeticPhase::components,p,0.1f);
    require(v.pose().animation_frame==1,"Source timer must advance before selection");
}
void large_delta_advances_only_once() {
    auto b=bank(); auto p=grounded(); PlayerPresentation v(b,p.position);
    v.observe(PlayerCosmeticPhase::components,p,1.0f);
    require(v.pose().animation_frame==1,"Sprite.Update must not drain a large timer in a loop");
}
void hair_simulates_all_four_nodes() {
    auto b=bank(); auto p=grounded(); PlayerPresentation v(b,p.position);
    v.observe(PlayerCosmeticPhase::components,p,1.f/60);
    v.observe(PlayerCosmeticPhase::after_update,p,1.f/60);
    require(v.pose().hair_nodes[0].y==149,"Hair root uses frame offset and scaled body anchor");
    for (unsigned i=1;i<4;++i) {
        auto a=v.pose().hair_nodes[i-1],n=v.pose().hair_nodes[i];
        require(std::hypot(n.x-a.x,n.y-a.y)<3.00001f,"Hair spring must constrain each segment");
    }
}
void hair_draws_outline_then_reverse_fill_then_body() {
    auto b=bank(); auto p=grounded(); PlayerPresentation v(b,p.position);
    v.observe(PlayerCosmeticPhase::after_update,p,1.f/60);
    auto draws=v.draw(p);
    require(draws.size()==21,"Four outlined hair nodes plus body must all draw");
    require(draws.front().color.r==0 && draws[16].color.r==172,"Hair outlines must precede colored fill");
    require(draws.back().origin.x==16 && draws.back().origin.y==32,"Body must draw last with source origin");
}
void depleted_color_truncates_each_lerp_channel() {
    auto b=bank(); auto p=grounded(); PlayerPresentation v(b,p.position);
    p.dashes=0;
    v.observe(PlayerCosmeticPhase::hair_color,p,1.f/60);
    auto c=v.pose().hair_color;
    require(c.r==161 && c.g==63 && c.b==70,"FNA Color.Lerp must truncate byte channels, not round");
}
void one_choice_goto_does_not_consume_random() {
    auto b=bank(); auto p=grounded(); PlayerPresentation v(b,p.position);
    for(int i=0;i<4;++i)v.observe(PlayerCosmeticPhase::components,p,0.1f);
    require(v.random_calls()==0,"Original Chooser one-choice fast path must retain its zero RNG consumption");
}
void signed_squash_preserves_trim_and_fractional_root() {
    PlayerFrame frame{"synthetic",0,1,1,12,10,6,20,32,32,{},0,true};
    PlayerDraw draw{0,{20.75f,100.25f},{16,32},{-0.6f,1.4f},0,{}};
    auto vertices=celeste::diagnostic::player_vertices(frame,draw);
    require(std::abs(vertices[0].x-26.75f)<0.00001f && std::abs(vertices[0].y-83.45f)<0.00001f,
            "Signed body squash must transform the trim-adjusted source origin without flooring geometry");
    require(vertices[1].x<vertices[0].x,"Negative scale must preserve source winding and UV orientation");
}
void session_skips_positive_freeze_including_zero_crossing() {
    auto b=bank();
    Body floor{{-100,0},Hitbox{200,8,{}},true};
    PlayerWorld world;world.collision.solids={&floor};
    celeste::diagnostic::Session session(world,{},&b);
    celeste::diagnostic::Sample dash;dash.player.dash_button={true,true,false};dash.player.aim_x=1;
    session.step(dash);
    const float wave=session.presentation()->pose().wave;
    require(session.player().clock().freeze_timer>0,"Fixture must enter a real Dash freeze");
    while(session.player().clock().freeze_timer>0) {
        session.step({});
        require(session.presentation()->pose().wave==wave,"Frozen and zero-crossing ticks must not advance hair simulation");
    }
    session.step({});
    require(session.presentation()->pose().wave>wave,"Presentation must resume on the next simulation tick");
}
}
int main() {
    try {
        animation_advances_before_selection(); large_delta_advances_only_once(); hair_simulates_all_four_nodes();
        hair_draws_outline_then_reverse_fill_then_body(); depleted_color_truncates_each_lerp_channel();
        one_choice_goto_does_not_consume_random();
        signed_squash_preserves_trim_and_fractional_root();
        session_skips_positive_freeze_including_zero_crossing();
        std::cout<<"8 presentation behaviors passed\n";
    } catch(const std::exception& e) { std::cerr<<e.what()<<'\n'; return 1; }
}
