#include "presentation.hpp"
#include "source_math.hpp"
#include <algorithm>
#include <cmath>
#include <cstring>
#include <limits>
#include <stdexcept>

namespace celeste {
namespace {
bool same_id(std::string_view a, std::string_view b) {
    if (a.size()!=b.size()) return false;
    for (std::size_t i=0;i<a.size();++i) {
        const auto lower=[](char c){return c>='A' && c<='Z' ? c+('a'-'A') : c;};
        if (lower(a[i])!=lower(b[i])) return false;
    }
    return true;
}
bool starts(std::string_view text, std::string_view prefix) { return text.substr(0,prefix.size())==prefix; }
std::int32_t subtract(std::int32_t a, std::int32_t b) {
    auto bits=static_cast<std::uint32_t>(a)-static_cast<std::uint32_t>(b);
    std::int32_t result;
    std::memcpy(&result,&bits,sizeof result);
    return result;
}
float length(Vec2 v) { return static_cast<float>(std::sqrt(static_cast<double>(v.x*v.x+v.y*v.y))); }
Vec2 normalized(Vec2 v) {
    if (v.x==0 && v.y==0) return {};
    const float factor=1.f/length(v);
    return {v.x*factor,v.y*factor};
}
Vec2 approach(Vec2 value, Vec2 target, float amount) {
    if (amount==0 || (value.x==target.x && value.y==target.y)) return value;
    Vec2 difference{target.x-value.x,target.y-value.y};
    if (length(difference)<amount) return target;
    auto unit=normalized(difference);
    return {value.x+unit.x*amount,value.y+unit.y*amount};
}
void finite(Vec2 p) {
    if (!std::isfinite(p.x) || !std::isfinite(p.y)) throw std::invalid_argument("Nonfinite presentation vector");
}
}

PresentationRandom::PresentationRandom(std::int32_t seed) : initial_seed_(seed) {
    auto value=subtract(161803398,seed==std::numeric_limits<std::int32_t>::min() ? std::numeric_limits<std::int32_t>::max() : std::abs(seed));
    values_[55]=value;
    std::int32_t next=1;
    for (int i=1;i<55;++i) {
        int at=21*i%55;
        values_[at]=next;
        next=subtract(value,next);
        if (next<0) next+=std::numeric_limits<std::int32_t>::max();
        value=values_[at];
    }
    for (int pass=1;pass<5;++pass) for (int i=1;i<56;++i) {
        values_[i]=subtract(values_[i],values_[1+(i+30)%55]);
        if (values_[i]<0) values_[i]+=std::numeric_limits<std::int32_t>::max();
    }
}
double PresentationRandom::sample() {
    if (++index_>=56) index_=1;
    if (++partner_>=56) partner_=1;
    auto value=subtract(values_[index_],values_[partner_]);
    if (value==std::numeric_limits<std::int32_t>::max()) --value;
    if (value<0) value+=std::numeric_limits<std::int32_t>::max();
    values_[index_]=value;
    ++calls_;
    return static_cast<double>(value)*4.656612875245797E-10;
}
double PresentationRandom::next_double() {
    const double value=sample();
    if(observer) observer("NextDouble",calls_);
    return value;
}
int PresentationRandom::next(int maximum) {
    if(maximum<=0) throw std::invalid_argument("Invalid random upper bound");
    const int value=static_cast<int>(sample()*maximum);
    if(observer) observer("Next",calls_);
    return value;
}
std::array<std::int32_t,58> PresentationRandom::state_words() const {
    std::array<std::int32_t,58> result{};
    result[0]=index_;result[1]=partner_;
    std::copy(values_.begin(),values_.end(),result.begin()+2);
    return result;
}

const PlayerAnimation& PlayerFrameBank::animation(std::string_view id) const {
    for (const auto& animation:animations) if (same_id(animation.id,id)) return animation;
    throw std::invalid_argument("Missing bounded player animation: "+std::string(id));
}
void PlayerFrameBank::validate() const {
    if (!pages || pages>10 || frames.empty() || frames.size()>256 || (animations.size()!=24 && animations.size()!=27))
        throw std::invalid_argument("Invalid bounded player frame bank size");
    for (const auto& f:frames) {
        if (f.name.empty() || f.page>=pages || f.u<1 || f.v<1 || f.width<1 || f.height<1 ||
            f.u+f.width>=128 || f.v+f.height>=64 || f.frame_width<1 || f.frame_height<1 || f.hair_frame<0 || f.hair_frame>2)
            throw std::invalid_argument("Invalid bounded player texture metadata");
        finite(f.hair_offset);
    }
    for (std::size_t i=0;i<animations.size();++i) {
        const auto& a=animations[i];
        if (a.id.empty() || !std::isfinite(a.delay) || a.delay<0 || a.frames.empty() || a.frames.size()>32)
            throw std::invalid_argument("Invalid bounded player animation");
        for (std::size_t j=0;j<i;++j) if (same_id(a.id,animations[j].id)) throw std::invalid_argument("Duplicate player animation");
        for (auto f:a.frames) if (f>=frames.size()) throw std::invalid_argument("Player animation frame outside bank");
        if (!a.next.empty()) animation(a.next);
    }
    for (const char* id:{"idle","idleA","idleB","idleC","runSlow","runFast","runStumble","flip","skid","jumpSlow","jumpFast","fallSlow","fallFast","duck","edge","edgeBack","push","lookUp","climbUp","climbLookBackStart","climbLookBack","dangling","wallslide","dash"}) animation(id);
    if(animations.size()==27) for(const char* id:{"deadup","deaddown","deadside"}) animation(id);
    for (auto f:bangs) if (f>=frames.size()) throw std::invalid_argument("Bangs outside player bank");
    if (hair>=frames.size()) throw std::invalid_argument("Hair outside player bank");
}

PlayerPresentation::PlayerPresentation(const PlayerFrameBank& bank, Vec2 spawn, std::int32_t diagnostic_seed,
                                     PresentationRandom* random, const float* level_time)
    : bank_(bank), diagnostic_seed_(diagnostic_seed), owned_random_(diagnostic_seed),
      random_(random ? *random : owned_random_), level_time_(level_time) {
    bank.validate();
    reset(spawn);
}
void PlayerPresentation::reset(Vec2 spawn) {
    finite(spawn);
    pose_={};
    simulate_hair_motion_=true;
    const auto& idle=bank_.animation("idle");
    pose_.animation=pose_.last_animation="idle";
    pose_.frame=idle.frames.front();
    pose_.animating=idle.delay>0;
    for(auto& node:pose_.hair_nodes) node={spawn.x-200,spawn.y+200};
}
void PlayerPresentation::bind_player_owner(const Player& player) {
    if(player_owner_ && player_owner_!=&player) throw std::logic_error("Player presentation owner cannot be replaced");
    player_owner_=&player;
}
void PlayerPresentation::callback(std::string_view kind, std::string_view animation) {
    const auto add=[this](std::string_view text){for(unsigned char c:text){pose_.callback_hash^=c;pose_.callback_hash*=16777619u;}};
    add(kind); add(":"); add(animation); add(";");
}
void PlayerPresentation::set_frame(unsigned frame) {
    if (pose_.frame==frame) return;
    pose_.frame=frame;
    ++pose_.frame_callbacks;
    callback("frame",pose_.animation+"/"+std::to_string(pose_.animation_frame));
}
void PlayerPresentation::play(std::string_view id) {
    if (pose_.animation==id) return;
    const auto& animation=bank_.animation(id);
    ++pose_.change_callbacks;
    callback("change",pose_.last_animation+">"+std::string(id));
    pose_.animation=pose_.last_animation=id;
    pose_.animating=animation.delay>0;
    pose_.timer=0;
    pose_.animation_frame=0;
    set_frame(animation.frames.front());
}
void PlayerPresentation::update_animation(float dt) {
    if (!pose_.animating) return;
    const auto& animation=bank_.animation(pose_.animation);
    pose_.timer+=dt*pose_.rate;
    if (!(std::abs(pose_.timer)>=animation.delay)) return;
    ++pose_.animation_frame;
    pose_.timer-=animation.delay;
    if (pose_.animation_frame>=animation.frames.size()) {
        const auto old=pose_.animation;
        ++pose_.last_callbacks;
        callback("last",old+"/"+std::to_string(pose_.animation_frame));
        if(old=="idle" && pose_.idle_timer>3.f && static_cast<float>(random_.next_double())<0.2f) {
            const double chosen=random_.next_double()*9.0;
            play(chosen<5.0 ? "idleA" : chosen<8.0 ? "idleB" : "idleC");
        }
        if(old!=pose_.animation) return;
        if(!animation.next.empty()) {
            pose_.animation=animation.next;
            ++pose_.change_callbacks;
            callback("change",pose_.last_animation+">"+pose_.animation);
            pose_.last_animation=pose_.animation;
            pose_.animation_frame=0;
            set_frame(bank_.animation(pose_.animation).frames.front());
        } else {
            pose_.animation_frame=animation.frames.size()-1;
            pose_.animating=false;
            pose_.animation.clear();
            pose_.timer=0;
        }
    } else set_frame(animation.frames[pose_.animation_frame]);
}
void PlayerPresentation::select(const PlayerProjection& p) {
    const auto at=[&](float x,float y){return Vec2{p.position.x+x,p.position.y+y};};
    if (p.dash_attacking) {
        if(p.on_ground && p.dash_direction.y==0 && !p.ducking && p.speed.x!=0 && p.move_x==-((p.speed.x>0)-(p.speed.x<0))) play("skid");
        else play(p.ducking ? "duck" : "dash");
    } else if(p.state==1) {
        if(p.climb_move<0) play("climbUp");
        else if(p.climb_move>0) play("wallslide");
        else if(!p.solid_body(at(float(p.facing),6))) play("dangling");
        else if(p.raw_x==-p.facing) {if(pose_.animation!="climbLookBack") play("climbLookBackStart");}
        else play("wallslide");
    } else if(p.ducking && p.state==0) play("duck");
    else if(p.on_ground) {
        pose_.fast_jump=false;
        if(p.move_x!=0 && p.solid_body(at(float(p.move_x),0))) play("push");
        else if(std::abs(p.speed.x)<=25 && p.move_x==0) {
            if(!p.solid_point(at(float(p.facing),2)) && !p.solid_point(at(float(p.facing*4),2)) && !p.jump_thru_body(at(float(p.facing*4),2))) play("edge");
            else if(!p.solid_point(at(float(-p.facing),2)) && !p.solid_point(at(float(-p.facing*4),2)) && !p.jump_thru_body(at(float(-p.facing*4),2))) play("edgeBack");
            else if(p.raw_y==-1) {if(pose_.last_animation!="lookUp") play("lookUp");}
            else if(pose_.animation.find("idle")==std::string::npos) play("idle");
        } else if(((p.speed.x>0)-(p.speed.x<0))==-p.move_x && p.move_x!=0) {
            if(std::abs(p.speed.x)>90) play("skid");
            else if(pose_.animation!="skid") play("flip");
        } else if(pose_.last_animation!="flip" && !starts(pose_.last_animation,"run")) play(std::abs(p.speed.x)<45 ? "runSlow" : "runFast");
    } else if(p.wall_slide!=0) play("wallslide");
    else if(p.speed.y<0) {
        if(pose_.fast_jump || std::abs(p.speed.x)>90) {pose_.fast_jump=true;play("jumpFast");}
        else play("jumpSlow");
    } else if(pose_.fast_jump || p.speed.y>=160) {
        pose_.fast_jump=true;
        if(pose_.last_animation!="fallFast") play("fallFast");
    } else play("fallSlow");
}
void PlayerPresentation::observe(PlayerCosmeticPhase phase, const PlayerProjection& p, float dt) {
    if (!std::isfinite(dt) || dt<0 || (p.facing!=1 && p.facing!=-1) || p.state<0 || (p.state>2 && p.state!=14) || p.dashes<0 || p.dashes>1)
        throw std::invalid_argument("Presentation is limited to default-inventory Normal, Climb and Dash");
    finite(p.position); finite(p.speed); finite(p.dash_direction);
    switch(phase) {
    case PlayerCosmeticPhase::scene_tick:
        if(!level_time_) scene_time_+=dt;
        pose_.idle_timer+=dt;
        if(p.speed.x!=0 || p.speed.y!=0) pose_.idle_timer=0;
        break;
    case PlayerCosmeticPhase::ground:
        pose_.highest_air_y=p.on_ground ? p.position.y : std::min(p.position.y,pose_.highest_air_y);
        if(int((scene_time()-dt)/0.05f)<int(scene_time()/0.05f)) pose_.flash=!pose_.flash;
        break;
    case PlayerCosmeticPhase::duck_turn: case PlayerCosmeticPhase::stand: pose_.scale={0.8f,1.2f}; break;
    case PlayerCosmeticPhase::duck: pose_.scale={1.4f,0.6f}; break;
    case PlayerCosmeticPhase::jump: pose_.scale={0.6f,1.4f}; break;
    case PlayerCosmeticPhase::climb_hop: pose_.fast_jump=false; break;
    case PlayerCosmeticPhase::components:
        pose_.wave+=dt*4.f;
        update_animation(dt);
        break;
    case PlayerCosmeticPhase::fast_fall:
        if(p.speed.y>=200) {
            float amount=std::min(1.f,(p.speed.y-200.f)/40.f);
            pose_.scale={1.f+(0.5f-1.f)*amount,1.f+(1.5f-1.f)*amount};
        }
        break;
    case PlayerCosmeticPhase::landing: {
        float amount=std::min(p.speed.y/240.f,1.f);
        pose_.scale={1.f+(1.6f-1.f)*amount,1.f+(0.4f-1.f)*amount};
        if(pose_.highest_air_y<p.position.y-50.f && p.speed.y>=160 && std::abs(p.speed.x)>=90) play("runStumble");
        break;
    }
    case PlayerCosmeticPhase::select:
        if(!p.solid_body || !p.solid_point || !p.jump_thru_body) throw std::invalid_argument("Player presentation requires exact point and full-body probes");
        pose_.scale.x=source_math::approach(pose_.scale.x,1,1.75f*dt);
        pose_.scale.y=source_math::approach(pose_.scale.y,1,1.75f*dt);
        if(p.state!=14) select(p);
        pose_.rate=1;
        break;
    case PlayerCosmeticPhase::hair_color:
        if(p.dashes==0) {
            float amount=std::clamp(6.f*dt,0.f,1.f);
            auto lerp=[amount](int a,int b){return static_cast<std::uint8_t>(int(float(a)+float(b-a)*amount));};
            auto& c=pose_.hair_color;
            c={lerp(c.r,68),lerp(c.g,183),lerp(c.b,255),lerp(c.a,255)};
        } else if(pose_.last_dashes!=p.dashes) {pose_.hair_color={};pose_.hair_flash_timer=0.12f;}
        else if(!(pose_.hair_flash_timer>0)) pose_.hair_color={172,50,50,255};
        else {pose_.hair_color={};pose_.hair_flash_timer-=dt;}
        pose_.hair_facing=p.facing;
        pose_.last_dashes=p.dashes;
        break;
    case PlayerCosmeticPhase::after_update: {
        const auto& f=bank_.frames[pose_.frame];
        auto& nodes=pose_.hair_nodes;
        nodes[0]={p.position.x+f.hair_offset.x*float(pose_.hair_facing),p.position.y+(-9.f*pose_.scale.y)+f.hair_offset.y};
        Vec2 target{nodes[0].x+float(-pose_.hair_facing)*0.5f*2.f,nodes[0].y+2.f};
        Vec2 previous=nodes[0];
        for(unsigned i=1;i<4;++i) {
            float step=(1.f-float(i)/4.f*0.5f)*64.f;
            if(simulate_hair_motion_) nodes[i]=approach(nodes[i],target,step*dt);
            Vec2 difference{nodes[i].x-previous.x,nodes[i].y-previous.y};
            if(length(difference)>3.f) {
                auto unit=normalized(difference);
                nodes[i]={previous.x+unit.x*3.f,previous.y+unit.y*3.f};
            }
            target={nodes[i].x+float(-pose_.hair_facing)*0.5f,nodes[i].y+2.f};
            previous=nodes[i];
        }
        break;
    }
    case PlayerCosmeticPhase::respawn_complete: pose_.scale={1.5f,0.5f}; break;
    case PlayerCosmeticPhase::dash_trail: break;
    }
}
void PlayerPresentation::corpse_render(float scale, float rotation, int facing) {
    if((facing!=1 && facing!=-1) || !std::isfinite(scale) || !std::isfinite(rotation))
        throw std::invalid_argument("Invalid corpse pose");
    pose_.scale={float(facing)*scale,scale};
    pose_.rotation=rotation;
    pose_.hair_facing=facing;
}
void PlayerPresentation::corpse_color(PresentationColor initial) {
    pose_.hair_color=pose_.animation_frame==0 ? PresentationColor{} : initial;
}
std::vector<PlayerDraw> PlayerPresentation::hair_draws() {
    const auto& f=bank_.frames[pose_.frame];
    std::vector<PlayerDraw> draws;
    if(f.has_hair) {
        pose_.hair_nodes[0]={std::floor(pose_.hair_nodes[0].x),std::floor(pose_.hair_nodes[0].y)};
        const auto scale=[&](unsigned i) {
            float n=0.25f+(1.f-float(i)/4.f)*0.75f;
            return Vec2{(i==0 ? float(pose_.hair_facing) : n)*std::abs(pose_.scale.x),n};
        };
        const auto frame=[&](unsigned i){return i==0 ? bank_.bangs[f.hair_frame] : bank_.hair;};
        for(unsigned i=0;i<4;++i) for(auto offset:{Vec2{-1,0},Vec2{1,0},Vec2{0,-1},Vec2{0,1}})
            draws.push_back({frame(i),{pose_.hair_nodes[i].x+offset.x,pose_.hair_nodes[i].y+offset.y},{5,5},scale(i),0,{0,0,0,255}});
        for(int i=3;i>=0;--i) draws.push_back({frame(i),pose_.hair_nodes[i],{5,5},scale(i),0,pose_.hair_color});
    }
    return draws;
}
std::vector<PlayerDraw> PlayerPresentation::draw(const PlayerProjection& p) {
    auto draws=hair_draws();
    const Vec2 position{std::floor(p.position.x),std::floor(p.position.y)};
    pose_.sprite_color=p.tired && pose_.flash ? PresentationColor{255,0,0,255} : PresentationColor{};
    draws.push_back({pose_.frame,position,{16,32},
                     {pose_.scale.x*float(p.facing),pose_.scale.y},pose_.rotation,pose_.sprite_color});
    return draws;
}

std::vector<PlayerDraw> PlayerPresentation::trail_capture(const PlayerProjection& p,Vec2 offset,Vec2 body_scale) {
    for(auto& node:pose_.hair_nodes) { node.x+=offset.x;node.y+=offset.y; }
    struct RestoreHair {
        std::array<Vec2,4>& nodes;
        Vec2 offset;
        ~RestoreHair() { for(auto& node:nodes) { node.x-=offset.x;node.y-=offset.y; } }
    } restore{pose_.hair_nodes,offset};
    auto draws=hair_draws();
    draws.push_back({pose_.frame,{std::floor(p.position.x+offset.x),std::floor(p.position.y+offset.y)},{16,32},body_scale,pose_.rotation,pose_.sprite_color});
    return draws;
}

std::vector<PlayerDraw> death_effect_draws(const PlayerFrameBank& bank, Vec2 position, PresentationColor color, float ease) {
    finite(position);
    if(!std::isfinite(ease) || ease<0 || ease>1) throw std::invalid_argument("Invalid death effect percent");
    const auto fill=std::fmod(std::floor(ease*10.f),2.0)==0 ? color : PresentationColor{};
    const float scale=ease<0.5f ? 0.5f+ease : source_math::cube_out(1.f-(ease-0.5f)*2.f);
    const auto& frame=bank.frames.at(bank.hair);
    const Vec2 origin{frame.frame_width*0.5f,frame.frame_height*0.5f};
    std::vector<PlayerDraw> draws;
    const auto at=[&](int i) {
        const float angle=(float(i)/8.f+ease*0.25f)*6.2831855f;
        const auto vector=source_math::angle_to_vector(angle,source_math::cube_out(ease)*24.f);
        return Vec2{position.x+vector.x,position.y+vector.y};
    };
    for(int i=0;i<8;++i) {
        const auto p=at(i);
        for(auto offset:{Vec2{-1,0},Vec2{1,0},Vec2{0,-1},Vec2{0,1}})
            draws.push_back({bank.hair,{p.x+offset.x,p.y+offset.y},origin,{scale,scale},0,{0,0,0,255}});
    }
    for(int i=0;i<8;++i) draws.push_back({bank.hair,at(i),origin,{scale,scale},0,fill});
    return draws;
}
}
