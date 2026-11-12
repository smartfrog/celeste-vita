#include "lifecycle.hpp"
#include "draw_order.hpp"
#include "source_math.hpp"

#include <algorithm>
#include <cmath>
#include <stdexcept>

namespace celeste {
namespace {
constexpr float pi=3.14159265358979323846f;
}
using source_math::approach;
using source_math::angle_to_vector;

bool AngledWipe::update(float dt) {
    if(!std::isfinite(dt) || dt<0) throw std::invalid_argument("Invalid wipe delta");
    if(!completed) {
        if(percent<1.f) percent=approach(percent,1.f,dt/0.5f);
        else completed=true;
    } else if(!ending) { ending=true; return true; }
    return false;
}

std::array<WipeVertex,36> AngledWipe::vertices() const {
    std::array<WipeVertex,36> result;
    for(int i=0;i<6;++i) {
        const float y=-10.f+float(i)*183.33333f;
        const float delay=(wipe_in ? 1.f-float(i)/6.f : float(i)/6.f)*0.3f;
        float amount=percent>delay ? std::min(1.f,(percent-delay)/0.7f) : 0.f;
        if(wipe_in) amount=1.f-amount;
        const float width=1984.f*amount;
        const std::array<Vec2,6> points{{{-64,y},{-64+width,y},{-64,y+183.33333f},
                                      {-64+width,y},{-64+width+64.f,y+183.33333f},{-64,y+183.33333f}}};
        for(unsigned j=0;j<6;++j) {
            auto p=points[j];
            if(wipe_in) p={1920.f-p.x,1080.f-p.y};
            result[i*6+j].position=p;
        }
    }
    return result;
}

struct FirstRoomSession::Corpse {
    Vec2 position, bounce, from, to;
    int facing;
    float scale=1, rotation=0, effect=0;
    bool has_effect=false, effect_pending=false, tween_pending=false, finished=false;
    PresentationColor initial_color;
    std::unique_ptr<Tween> tween;
    Coroutine routine;
    unsigned stage=0;
};

FirstRoomSession::FirstRoomSession(const PlayerWorld& world,const PlayerFrameBank& bank,bool checkpoint,std::int32_t seed,const RoomCatalog* catalog,
                                 const std::vector<draw_order::AuthoredDecalOwners>* visual_catalog)
    : bank_(bank),diagnostic_seed_(seed),initial_world_(world),catalog_(catalog),visual_catalog_(visual_catalog),world_(world),random_(seed) {
    if(visual_catalog_) {
        if(!catalog_ || visual_catalog_->size()!=catalog_->definitions().size())
            throw std::invalid_argument("Visual initialization requires complete room catalog metadata");
        draw_order::validate_authored_decals(*visual_catalog_);
        for(const auto& room:catalog_->definitions()) visual_owners(room);
    }
    if(world.bounds_left!=0 || world.bounds_right!=320 || world.collision.solids.size()!=1 ||
       !world.collision.solids.front() || !world.collision.solids.front()->grid ||
       world.collision.solids.front()->collider || !world.collision.solids.front()->collidable ||
       !world.collision.jump_thrus.empty() || world.spikes.size()!=5 ||
       world.safe_ground!=world.collision.solids)
        throw std::invalid_argument("Automatic lifecycle requires the bounded static first-room profile");
    retained_solid_position_=world.collision.solids.front()->position;
    retained_grid_=world.collision.solids.front()->grid;
    bank.validate();
    for(const char* id:{"deadup","deaddown","deadside"}) bank.animation(id);
    const auto sweat=std::find_if(bank.frames.begin(),bank.frames.end(),[](const PlayerFrame& frame) {
        return frame.name=="characters/player/sweat/idle00";
    });
    if(sweat==bank.frames.end()) throw std::invalid_argument("First-room lifecycle requires the original transparent sweat idle frame");
    int up_pieces=0,left_pieces=0;
    for(const auto* spike:world.spikes) {
        if(!spike) throw std::invalid_argument("Null first-room spike");
        const auto& box=*spike->body().collider;
        const float size=spike->direction()==SpikeDirection::up ? box.width : box.height;
        if(size>136.f || std::fmod(size,8.f)!=0) throw std::invalid_argument("Unsupported first-room spike size");
        (spike->direction()==SpikeDirection::up ? up_pieces : left_pieces)+=static_cast<int>(size)/8;
        spike_definitions_.push_back(*spike);
    }
    if(up_pieces!=17 || left_pieces!=2) throw std::invalid_argument("First-room profile requires seventeen Up and two Left spike images");
    if(std::count_if(spike_definitions_.begin(),spike_definitions_.end(),[](const StaticSpike& spike) {
        return spike.direction()==SpikeDirection::up;
    })!=4) throw std::invalid_argument("First-room profile requires four Up spikes and one Left spike");
    stats_.hit_checkpoint=checkpoint;
    random_.observer=[this](const char* operation,unsigned calls) {
        random_events_.push_back({random_phase_,operation,calls});
    };
    load();
}

const draw_order::AuthoredDecalOwners* FirstRoomSession::visual_owners(const RoomDefinition& room) const {
    if(!visual_catalog_) return nullptr;
    const auto found=std::find_if(visual_catalog_->begin(),visual_catalog_->end(),[&](const auto& group) { return group.room==&room; });
    if(found==visual_catalog_->end()) throw std::invalid_argument("Visual metadata must bind the exact room instance definition");
    return &*found;
}

void FirstRoomSession::load() {
    world_=initial_world_;
    if(catalog_) {
        const auto& first=catalog_->first();
        if(first.bounds.x!=0 || first.bounds.y!=0 || first.spawn.x!=19 || first.spawn.y!=144)
            throw std::invalid_argument("Room catalog must retain the natural first-room spawn/bounds");
        current_room_=std::make_unique<RoomRuntime>(first,initial_world_.collision,stats_.loads==0,visual_owners(first));
        std::vector<const StaticSpike*> authored_spikes;
        for(const auto& entity:current_room_->entities) if(const auto* spike=std::get_if<StaticSpike>(&entity->object)) authored_spikes.push_back(spike);
        if(authored_spikes.size()!=initial_world_.spikes.size()) throw std::invalid_argument("Catalog first-room hazards differ from the retained world");
        for(std::size_t i=0;i<authored_spikes.size();++i) {
            const auto& actual=*authored_spikes[i];const auto& expected=*initial_world_.spikes[i];
            if(actual.direction()!=expected.direction() || actual.body().position.x!=expected.body().position.x || actual.body().position.y!=expected.body().position.y ||
               actual.body().collider->width!=expected.body().collider->width || actual.body().collider->height!=expected.body().collider->height)
                throw std::invalid_argument("Catalog first-room hazards differ from the retained world");
        }
        stats_.scoped_room_random_calls+=current_room_->scoped_random.calls();
        bind_room_world();
        chaser_history_.clear();
    } else {
        auto reconstructed_spikes=spike_definitions_;
        spikes_=std::move(reconstructed_spikes);
        PresentationRandom room_random(49);
        for(const auto& spike:spikes_) {
            const auto& box=*spike.body().collider;
            const float size=spike.direction()==SpikeDirection::up ? box.width : box.height;
            for(int piece=0;piece<static_cast<int>(size)/8;++piece) room_random.next(1);
        }
        stats_.scoped_room_random_calls+=room_random.calls();
        world_.spikes.clear();
        for(const auto& spike:spikes_) world_.spikes.push_back(&spike);
    }
    auto player=std::make_unique<Player>(world_,Vec2{19,144},Vec2{},PlayerProfile::default_static,&context_);
    auto presentation=std::make_unique<PlayerPresentation>(bank_,player->actor().body.position,diagnostic_seed_,&random_,&time_active_);
    presentation->bind_player_owner(*player);
    player->begin_respawn();
    player_=std::move(player);
    presentation_=std::move(presentation);
    camera_={};
    wipe_=std::make_shared<AngledWipe>(true);
    wipe_pending_=false;
    foreground_owner_=true;
    ++stats_.loads;
    if(catalog_) publish_room_roster();
}

void FirstRoomSession::reload() {
    if(current_room_ && &current_room_->definition!=&catalog_->first()) throw std::runtime_error("Unsupported Room2 reload");
    if(!corpse_ || !corpse_->finished) throw std::logic_error("Reload requires a completed corpse action");
    trails_.clear();
    ++stats_.wipe_callbacks;
    if(!stats_.hit_checkpoint) { stats_.session_time=0; stats_.session_deaths=0; stats_.timer_started=false; }
    dust_.clear();
    dust_index_=0;
    ++stats_.particle_clears;
    corpse_.reset();
    corpse_committed_=false;
    ++stats_.corpse_removes;
    load();
    ++stats_.reloads;
}

PlayerProjection FirstRoomSession::projection() const {
    if(presentation_->player_owner()!=player_.get()) throw std::logic_error("Player/presentation ownership changed");
    auto result=project_player(*player_,world_,input_);
    if(committed_corpse()) { result.position=corpse_->position; result.facing=1; result.tired=false; }
    return result;
}

void FirstRoomSession::queue_corpse() {
    if(corpse_) throw std::logic_error("Duplicate corpse ownership");
    corpse_=std::make_shared<Corpse>();
    auto& corpse=*corpse_;
    corpse.position=player_->actor().body.position;
    corpse.bounce=player_->death().direction;
    corpse.facing=player_->state().facing;
    corpse.initial_color=presentation_->pose().hair_color;
    ++stats_.corpse_adds; ++stats_.session_deaths; ++stats_.room_deaths; ++stats_.save_deaths;
    shake_timer_=std::max(shake_timer_,0.3f);
}

void FirstRoomSession::commit_corpse() {
    corpse_committed_=true;
    ++stats_.corpse_commits;
    auto& c=*corpse_;
    if(c.bounce.x!=0 || c.bounce.y!=0) {
        if(std::abs(c.bounce.x)>std::abs(c.bounce.y)) {
            presentation_->play_animation("deadside");
            c.facing=c.bounce.x>0 ? -1 : 1;
        } else {
            const float angle=static_cast<float>(std::atan2(double(c.bounce.y),double(c.bounce.x)));
            const float target=static_cast<float>(std::atan2(0.0,double(-c.facing)));
            c.bounce=angle_to_vector(source_math::angle_approach(angle,target,0.5f),1);
            presentation_->play_animation(c.bounce.y<0 ? "deadup" : "deaddown");
        }
    }
    c.routine.replace(std::make_shared<Iterator>([this]() -> IteratorStep {
        auto& body=*corpse_;
        if(body.stage==0) {
            ++body.stage;
            if(body.bounce.x!=0 || body.bounce.y!=0) {
                body.scale=1.5f;
                context_.clock.freeze(0.05f);
                return Yield{std::monostate{}};
            }
        }
        if(body.stage==1 && (body.bounce.x!=0 || body.bounce.y!=0)) {
            ++body.stage;
            body.from=body.position;
            body.to={body.from.x+body.bounce.x*24.f,body.from.y+body.bounce.y*24.f};
            body.tween=std::make_unique<Tween>(0.5f,source_math::cube_out);
            body.tween_pending=true;
            body.tween->on_update=[this](const Tween& tween) {
                auto& value=*corpse_;
                value.position={value.from.x+(value.to.x-value.from.x)*tween.eased,value.from.y+(value.to.y-value.from.y)*tween.eased};
                value.scale=1.5f-tween.eased*0.5f;
                value.rotation=static_cast<float>(std::floor(tween.eased*4.f)*6.2831854820251465);
            };
            return Yield{body.tween->duration*0.75f};
        }
        if(body.stage<=2) {
            body.stage=3;
            if(body.tween) body.tween->active=false;
            body.position.y+=-5.f;
            shake_timer_=std::max(shake_timer_,0.3f);
            body.has_effect=true;
            body.effect_pending=true;
            return Yield{0.834f*0.65f};
        }
        end_corpse();
        return std::nullopt;
    }));
}

void FirstRoomSession::end_corpse() {
    if(corpse_->finished) return;
    corpse_->finished=true;
    wipe_=std::make_shared<AngledWipe>(false);
    wipe_pending_=true;
}

void FirstRoomSession::update_corpse() {
    auto& c=*corpse_;
    c.tween_pending=false;
    c.effect_pending=false;
    presentation_->observe(PlayerCosmeticPhase::components,projection(),context_.clock.delta);
    if(c.routine.active) c.routine.update(context_.clock.delta,context_.clock.raw_delta);
    if(c.tween && !c.tween_pending) c.tween->update(context_.clock.delta);
    if(c.has_effect && !c.effect_pending) c.effect=approach(c.effect,1.f,context_.clock.delta/0.834f);
    presentation_->corpse_color(c.initial_color);
}

void FirstRoomSession::dust_burst(Vec2 position,int count) {
    const float direction=-pi/2.f;
    const auto range_vector=angle_to_vector(direction-pi/2.f,4.f);
    const float x=std::abs(range_vector.x),y=std::abs(range_vector.y);
    const auto next=[this]() { return static_cast<float>(random_.next_double()); };
    for(int i=0;i<count;++i) {
        DustParticle particle;
        const float offset_x=-x+next()*(x-(-x));
        const float offset_y=-y+next()*(y-(-y));
        particle.position={position.x+offset_x,position.y+offset_y};
        particle.source=static_cast<int>(random_.next_double()*4.0);
        particle.size=0.7f-0.2f*0.5f+next()*0.2f;
        const float angle=direction-0.5f/2.f+next()*0.5f;
        particle.speed=angle_to_vector(angle,5.f+next()*(15.f-5.f));
        particle.life=0.3f+next()*(0.5f-0.3f);
        particle.rotation=next()*pi*2.f;
        particle.spin=0.f+next()*0.f;
        if(dust_.size()<400) dust_.push_back(particle);
        else dust_[dust_index_]=particle;
        dust_index_=(dust_index_+1)%400;
    }
}

void FirstRoomSession::observe(PlayerCosmeticPhase phase) {
    if(phase==PlayerCosmeticPhase::after_update) return;
    if(phase==PlayerCosmeticPhase::dash_trail) { trails_.add(projection(),presentation_->pose());return; }
    if(phase==PlayerCosmeticPhase::jump) {
        random_phase_="jump-dust";
        dust_burst(player_->actor().body.position,4);
        ++stats_.jumps;
    }
    if(phase==PlayerCosmeticPhase::landing && player_->state().speed.y>=80.f) {
        random_phase_="landing-dust";
        dust_burst(player_->actor().body.position,8);
    }
    if(phase==PlayerCosmeticPhase::respawn_complete) ++stats_.respawn_callbacks;
    random_phase_="presentation";
    presentation_->observe(phase,projection(),context_.clock.delta);
    if(phase==PlayerCosmeticPhase::respawn_complete) {
        const auto& machine=player_->state_machine();
        const auto& tween=*player_->respawn_tween();
        callbacks_.push_back({"respawn-tween",machine.previous_state(),machine.state(),presentation_->pose().scale,
                              player_->state().max_fall,tween.time_left,tween.percent,false,false});
    }
}

void FirstRoomSession::step(float raw_delta_time,PlayerInput input,std::function<void(SessionPhase,const FirstRoomSession&)> observer) {
    if(updating_) throw std::logic_error("Recursive first-room frame");
    const auto& solid=*initial_world_.collision.solids.front();
    if(solid.grid!=retained_grid_ || !solid.collidable || solid.collider ||
       solid.position.x!=retained_solid_position_.x || solid.position.y!=retained_solid_position_.y)
        throw std::invalid_argument("Moving or replaced global collision is outside the first-room lifecycle");
    const float next_time=time_active_+raw_delta_time;
    if(!std::isfinite(raw_delta_time) || raw_delta_time<0 || !std::isfinite(next_time) || next_time/0.04f>=2147483648.f)
        throw std::invalid_argument("First-room time exceeds the source int32 interval domain");
    struct Updating { bool& value; ~Updating() { value=false; } } updating{updating_};
    updating_=true;
    context_.sample(raw_delta_time,input);
    input_=input;
    random_events_.clear();
    callbacks_.clear();
    buffer_before_scene_=context_.jump.buffer_counter();
    pressed_before_scene_=context_.jump.pressed();
    if(observer) observer(SessionPhase::before_frame,*this);
    if(transition_ && (input.dash_button.held || input.dash_button.pressed || context_.clock.freeze_timer>0))
        throw std::runtime_error("Unsupported Dash/freeze crossing during room transition");
    scene_ran_=context_.clock.simulate();
    if(!scene_ran_) { if(observer) observer(SessionPhase::after_frame,*this);return; }
    time_active_+=context_.clock.delta;
    raw_time_active_+=context_.clock.raw_delta;
    if(catalog_) publish_room_roster();
    if(observer) observer(SessionPhase::before_update,*this);
    if(pending_corpse()) commit_corpse();
    if(!transition_) trails_.update(context_.clock.delta);
    foreground_owner_=committed_corpse() || player_->state_machine().state()==14;
    if(!stats_.timer_started && !committed_corpse() && !player_->death().dead && player_->state_machine().state()!=14)
        stats_.timer_started=true;
    if(stats_.timer_started) stats_.session_time+=static_cast<std::int64_t>(double(raw_delta_time)*10000000.0);
    stats_.save_time+=static_cast<std::int64_t>(double(raw_delta_time)*10000000.0);
    random_phase_="level-glitch";
    random_.next_double();
    if(committed_corpse()) update_corpse();
    else if(catalog_) {
        const bool transitioning=bool(transition_);
        if(!transitioning) current_room_->update_banners(context_.clock.delta);
        for(const auto& entry:room_roster_) {
            if(entry.player && (transitioning ? (entry.player->scene_tag()&4)!=0 : entry.player->scene_active())) {
                const auto dashes_before=player_->state().dash_events;
                player_->update_sampled(input_,[this](PlayerCosmeticPhase phase) { observe(phase); });
                stats_.session_dashes+=player_->state().dash_events-dashes_before;
                stats_.save_dashes+=player_->state().dash_events-dashes_before;
                if(player_->death().dead) { queue_corpse();break; }
                enforce_room_bounds();
                while(!chaser_history_.empty() && time_active_-chaser_history_.front().timestamp>4.f) chaser_history_.pop_front();
                chaser_history_.push_back({time_active_,player_->actor().body.position,player_->state().speed,player_->state().facing});
                presentation_->simulate_hair_motion(true);
            } else if(entry.entity && entry.entity->should_update(transitioning)) entry.entity->update(context_.clock.delta);
        }
        if(transitioning) update_room_transition();
    } else {
        const auto dashes_before=player_->state().dash_events;
        player_->update_sampled(input_,[this](PlayerCosmeticPhase phase) { observe(phase); });
        stats_.session_dashes+=player_->state().dash_events-dashes_before;
        stats_.save_dashes+=player_->state().dash_events-dashes_before;
        if(player_->death().dead) queue_corpse();
    }
    const auto current_wipe=wipe_;
    if(current_wipe && !wipe_pending_ && current_wipe->update(raw_delta_time)) {
        wipe_.reset();
        if(!current_wipe->wipe_in) {
            reload();
            callbacks_.push_back({"wipe-reload",0,0,{},0,0,0,current_wipe->completed,current_wipe->ending});
        }
    }
    wipe_pending_=false;
    presentation_->observe(PlayerCosmeticPhase::after_update,projection(),context_.clock.delta);
    if(shake_timer_>0) {
        if(int((raw_time_active_-context_.clock.raw_delta)/0.04f)<int(raw_time_active_/0.04f)) {
            const int magnitude=static_cast<int>(std::ceil(shake_timer_*10.f));
            random_phase_="level-shake-after-hair";
            const int x=-magnitude+random_.next(magnitude*2+1);
            const int y=-magnitude+random_.next(magnitude*2+1);
            shake_={float((x>0)-(x<0)),float((y>0)-(y<0))};
        }
        shake_timer_-=raw_delta_time*1.5f;
    } else shake_={};
    if(observer) observer(SessionPhase::before_eof,*this);
    if(pending_room_) start_room_transition();
    if(observer) observer(SessionPhase::after_eof,*this);
    if(observer) observer(SessionPhase::after_frame,*this);
}

const char* FirstRoomSession::phase() const {
    if(committed_corpse()) return corpse_->has_effect ? "death-effect" : "corpse";
    return player_->state_machine().state()==14 ? "respawn14" : "live";
}
float FirstRoomSession::effect_percent() const { return committed_corpse() && corpse_->has_effect ? corpse_->effect : -1.f; }
float FirstRoomSession::corpse_tween_time() const { return committed_corpse() && corpse_->tween ? corpse_->tween->time_left : -1.f; }

std::vector<PlayerDraw> FirstRoomSession::draw() {
    if(updating_) throw std::logic_error("Cannot render during first-room update");
    const auto p=projection();
    if(committed_corpse()) {
        auto& c=*corpse_;
        if(c.has_effect) return death_effect_draws(bank_,c.position,c.initial_color,c.effect);
        presentation_->corpse_render(c.scale,c.rotation,c.facing);
        return presentation_->draw(p);
    }
    if(player_->state_machine().state()==14) {
        const auto offset=player_->dead_offset();
        return death_effect_draws(bank_,{p.position.x+offset.x,p.position.y-5.5f+offset.y},presentation_->pose().hair_color,player_->intro_ease());
    }
    auto draws=presentation_->draw(p);
    draws.push_back(presentation_->sweat_draw(p));
    return draws;
}

}
