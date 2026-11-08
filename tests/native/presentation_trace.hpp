#pragma once
#include "presentation.hpp"
#include "player.hpp"
#include "fixture_io.hpp"
#include "draw.hpp"

namespace native_test {
inline const celeste::PlayerFrameBank* presentation_bank=nullptr;
inline const char* phase_name(celeste::PlayerCosmeticPhase phase) {
    using P=celeste::PlayerCosmeticPhase;
    switch(phase) {
    case P::scene_tick:return "scene_tick"; case P::ground:return "ground"; case P::duck_turn:return "duck_turn";
    case P::components:return "components"; case P::jump:return "jump"; case P::duck:return "duck";
    case P::stand:return "stand"; case P::fast_fall:return "fast_fall"; case P::landing:return "landing";
    case P::select:return "select"; case P::hair_color:return "hair_color"; case P::after_update:return "after_update";
    }
    throw std::invalid_argument("Unknown cosmetic phase");
}
class PresentationTrace {
public:
    PresentationTrace(const celeste::PlayerFrameBank& bank, celeste::Vec2 spawn) : bank_(bank), view_(bank,spawn,0) { }
    void observe(const std::string& name, int tick, celeste::PlayerCosmeticPhase phase, const celeste::PlayerProjection& p, float dt) {
        projection(name,tick,phase_name(phase),p,dt);
        view_.observe(phase,p,dt);
        state(name,tick,phase_name(phase));
    }
    void render(const std::string& name, int tick, const celeste::PlayerProjection& p, float dt) {
        projection(name,tick,"render",p,dt);
        auto draws=view_.draw(p);
        state(name,tick,"render");
        unsigned i=0;
        for(const auto& d:draws) {
            const auto& f=bank_.frames[d.frame];
            std::cout<<"D\t"<<name<<'\t'<<tick<<'\t'<<i<<'\t'<<f.name<<'\t'
                <<bits(d.position.x)<<'\t'<<bits(d.position.y)<<'\t'<<bits(d.origin.x-f.trim_x)<<'\t'<<bits(d.origin.y-f.trim_y)<<'\t'
                <<bits(d.scale.x)<<'\t'<<bits(d.scale.y)<<'\t'<<bits(d.rotation)<<'\t'
                <<unsigned(d.color.r)<<'\t'<<unsigned(d.color.g)<<'\t'<<unsigned(d.color.b)<<'\t'<<unsigned(d.color.a)<<"\t0\n";
            std::cout<<"V\t"<<name<<'\t'<<tick<<'\t'<<i++;
            for(const auto& v:celeste::diagnostic::player_vertices(f,d)) std::cout<<'\t'<<bits(v.x)<<'\t'<<bits(v.y);
            std::cout<<'\n';
        }
    }
private:
    const celeste::PlayerFrameBank& bank_;
    celeste::PlayerPresentation view_;
    void projection(const std::string& name, int tick, const char* phase, const celeste::PlayerProjection& p, float dt) {
        const auto at=[&](float x,float y){return celeste::Vec2{p.position.x+x,p.position.y+y};};
        std::cout<<"P\t"<<name<<'\t'<<tick<<'\t'<<phase<<'\t'<<bits(dt)<<'\t'<<bits(p.position.x)<<'\t'<<bits(p.position.y)<<'\t'
            <<bits(p.speed.x)<<'\t'<<bits(p.speed.y)<<'\t'<<p.facing<<'\t'<<p.state<<'\t'<<p.move_x<<'\t'<<p.raw_x<<'\t'<<p.raw_y<<'\t'
            <<p.climb_move<<'\t'<<p.wall_slide<<'\t'<<p.dash_attacking<<'\t'<<p.dashes<<'\t'<<p.on_ground<<'\t'<<p.ducking<<'\t'<<p.tired<<'\t'
            <<bits(p.dash_direction.x)<<'\t'<<bits(p.dash_direction.y)<<'\t'
            <<p.solid_body(at(float(p.facing),6))<<p.solid_body(at(float(p.move_x),0))<<'\t'
            <<p.solid_point(at(float(p.facing),2))<<p.solid_point(at(float(p.facing*4),2))
            <<p.solid_point(at(float(-p.facing),2))<<p.solid_point(at(float(-p.facing*4),2))<<'\t'
            <<p.jump_thru_body(at(float(p.facing*4),2))<<p.jump_thru_body(at(float(-p.facing*4),2))<<'\n';
    }
    void state(const std::string& name,int tick,const char* phase) {
        const auto& s=view_.pose();
        std::cout<<"R\t"<<name<<'\t'<<tick<<'\t'<<phase<<'\t'<<s.animation<<'\t'<<s.last_animation<<'\t'<<s.animation_frame<<'\t'
            <<bank_.frames[s.frame].name<<'\t'<<bits(s.timer)<<'\t'<<bits(s.rate)<<'\t'<<bits(s.scale.x)<<'\t'<<bits(s.scale.y)<<'\t'
            <<bits(s.rotation)<<'\t'<<bits(s.wave)<<'\t'<<bits(s.idle_timer)<<'\t'<<bits(s.highest_air_y)<<'\t'<<s.flash<<'\t'<<s.fast_jump<<'\t'
            <<bits(s.hair_flash_timer)<<'\t'<<s.last_dashes<<'\t'<<s.hair_facing<<'\t'
            <<unsigned(s.hair_color.r)<<'\t'<<unsigned(s.hair_color.g)<<'\t'<<unsigned(s.hair_color.b)<<'\t'<<unsigned(s.hair_color.a);
        for(auto n:s.hair_nodes) std::cout<<'\t'<<bits(n.x)<<'\t'<<bits(n.y);
        std::cout<<'\t'<<s.frame_callbacks<<'\t'<<s.change_callbacks<<'\t'<<s.last_callbacks<<'\t'<<s.callback_hash<<'\t'<<view_.random_calls()<<'\t'<<bits(view_.scene_time())<<'\t'<<s.animating<<'\n';
    }
};
}
