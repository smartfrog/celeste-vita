#include "assets.hpp"
#include "diagnostic.hpp"
#include "draw_order.hpp"
#include "player_draw_trace.hpp"
#include <fstream>
#include <iomanip>
#include <iostream>
#include <limits>
#include <type_traits>
#include <set>
#include <algorithm>

using namespace celeste;
using namespace celeste::diagnostic;
namespace {
void vec(Vec2 value) { std::cout<<'['<<value.x<<','<<value.y<<']'; }
void bounds(const RoomBounds& value) { std::cout<<'['<<value.x<<','<<value.y<<','<<value.width<<','<<value.height<<']'; }
const char* phase_name(SessionPhase phase) {
    switch(phase) {
    case SessionPhase::before_frame:return "before-frame";
    case SessionPhase::before_update:return "before-update";
    case SessionPhase::before_eof:return "before-eof";
    case SessionPhase::after_eof:return "after-eof";
    case SessionPhase::after_frame:return "after-frame";
    }
    throw std::invalid_argument("Unknown session phase");
}
const char* kind(const RoomEntity& entity) {
    return std::visit([](const auto& object) -> const char* {
        using T=std::decay_t<decltype(object)>;
        if constexpr(std::is_same_v<T,RoomSceneHelper>) return "scene_helper";
        if constexpr(std::is_same_v<T,RoomWind>) return "wind";
        if constexpr(std::is_same_v<T,StaticSpike>) return "spike";
        if constexpr(std::is_same_v<T,RoomJumpThru>) return "jump_thru";
        if constexpr(std::is_same_v<T,RoomSpring>) return "spring";
        return "strawberry";
    },entity.object);
}
RoomCatalog read_catalog(const char* path) {
    std::ifstream stream(path);std::string magic;int count=0;
    if(!(stream>>magic>>count) || magic!="CROOM1" || count!=2) throw std::invalid_argument("Invalid bounded room catalog header");
    std::vector<RoomDefinition> rooms;
    for(int index=0;index<count;++index) {
        RoomDefinition room;int objects=0;
        if(!(stream>>room.name>>room.bounds.x>>room.bounds.y>>room.bounds.width>>room.bounds.height>>room.load_seed>>room.spawn.x>>room.spawn.y>>objects) || objects<0 || objects>32)
            throw std::invalid_argument("Invalid bounded room record");
        for(int object=0;object<objects;++object) {
            std::string name;RoomObjectDefinition value;
            if(!(stream>>name>>value.id>>value.position.x>>value.position.y>>value.size)) throw std::invalid_argument("Incomplete room object");
            if(name=="spike_up") value.kind=RoomObjectKind::spike_up;
            else if(name=="spike_left") value.kind=RoomObjectKind::spike_left;
            else if(name=="jump_thru") value.kind=RoomObjectKind::jump_thru;
            else if(name=="spring") value.kind=RoomObjectKind::spring;
            else if(name=="strawberry") value.kind=RoomObjectKind::strawberry;
            else throw std::invalid_argument("Unsupported room object: "+name);
            room.objects.push_back(value);
        }
        rooms.push_back(std::move(room));
    }
    std::string extra;if(stream>>extra) throw std::invalid_argument("Trailing room catalog data");
    if(!stream.eof()) throw std::runtime_error("Failed reading room catalog");
    return RoomCatalog(std::move(rooms));
}
void entity(const RoomRosterEntry& entry,const PlayerWorld& world) {
    if(entry.player) {
        std::cout<<"{\"kind\":\"player\",\"id\":"<<entry.player->object_identity()<<",\"tag\":"<<entry.player->scene_tag()<<",\"active\":"<<entry.player->scene_active()
            <<",\"collidable\":"<<entry.player->actor().body.collidable<<",\"position\":";
        vec(entry.player->actor().body.position);std::cout<<'}';return;
    }
    const auto& value=*entry.entity;
    std::cout<<"{\"kind\":\""<<kind(value)<<"\",\"id\":"<<value.object_identity<<",\"room\":\""<<entry.room->definition.name
        <<"\",\"authoredId\":"<<value.authored_id<<",\"tag\":"<<value.tag()<<",\"active\":"<<value.active<<",\"position\":";
    vec(value.position());
    const auto* body=value.body();
    std::cout<<",\"collidable\":"<<(!body || body->collidable)<<",\"box\":";
    if(body && body->collider) {
        const auto& box=*body->collider;
        std::cout<<'['<<box.width<<','<<box.height<<','<<box.offset.x<<','<<box.offset.y<<']';
    } else std::cout<<"null";
    if(std::holds_alternative<RoomJumpThru>(value.object)) std::cout<<",\"safe\":"<<(std::find(world.safe_ground.begin(),world.safe_ground.end(),body)!=world.safe_ground.end());
    if(std::holds_alternative<StaticSpike>(value.object) || std::holds_alternative<RoomJumpThru>(value.object)) std::cout<<",\"images\":"<<value.image_cells.size();
    if(const auto* berry=std::get_if<RoomStrawberry>(&value.object))
        std::cout<<",\"wobble\":"<<berry->wobble<<",\"spriteFrame\":"<<berry->sprite_frame<<",\"spriteTimer\":"<<berry->sprite_timer;
    if(const auto* spring=std::get_if<RoomSpring>(&value.object))
        std::cout<<",\"wiggler\":"<<spring->wiggler<<",\"attached\":\""<<spring->attached<<'"';
    std::cout<<'}';
}
void record(int tick,SessionPhase phase,const FirstRoomSession& session) {
    const auto& player=session.player();const auto& state=player.state();const auto& pose=session.presentation().pose();
    for(const auto& entry:session.room_roster()) if(entry.player && entry.player!=&player) throw std::logic_error("Native roster Player ownership changed before publication");
    std::cout<<"{\"event\":\"phase\",\"tick\":"<<tick<<",\"phase\":\""<<phase_name(phase)<<"\",\"state\":{\"level\":"<<session.object_identity()
        <<",\"player\":"<<player.object_identity()<<",\"presentation\":"<<session.presentation().object_identity()
        <<",\"spriteStorage\":\""<<&pose.animation<<"\",\"hairStorage\":\""<<&pose.hair_nodes
        <<"\",\"worldStorage\":\""<<&session.world()<<"\",\"collisionStorage\":\""<<&session.world().collision
        <<"\",\"solidStorage\":\""<<session.world().collision.solids.front()<<"\",\"gridStorage\":\""<<session.world().collision.solids.front()->grid<<"\",\"solidOrigin\":";
    vec(session.world().collision.solids.front()->position);
    const auto owner=session.presentation().player_owner();
    std::cout<<",\"sameTrackedPlayer\":"<<(std::count_if(session.room_roster().begin(),session.room_roster().end(),[&](const auto& entry) { return entry.player==&player; })==1)
        <<",\"sameSpriteOwner\":"<<(owner==&player)<<",\"sameHairOwner\":"<<(owner==&player);
    std::cout<<",\"room\":\""<<session.room_definition()->name<<"\",\"bounds\":";bounds(session.room_definition()->bounds);
    std::cout<<",\"collisionBounds\":["<<session.world().bounds_left<<','<<session.world().bounds_right<<']';
    std::cout<<",\"previousBounds\":";if(session.previous_bounds()) bounds(*session.previous_bounds());else std::cout<<"null";
    std::cout<<",\"position\":";vec(player.actor().body.position);
    const auto& body=player.actor().body;const auto& box=*body.collider;
    const Vec2 center{body.position.x+box.offset.x+box.width/2.f,body.position.y+box.offset.y+box.height/2.f};
    std::cout<<",\"center\":";vec(center);std::cout<<",\"upProbe\":";vec({center.x,center.y-12.f});
    std::cout<<",\"speed\":";vec(state.speed);
    std::cout<<",\"remainder\":";vec(player.actor().position_remainder());
    std::cout<<",\"state\":"<<player.state_machine().state()<<",\"previousState\":"<<player.state_machine().previous_state()<<",\"Locked\":"<<player.state_machine().locked
        <<",\"Dead\":"<<player.death().dead<<",\"Dashes\":"<<state.dashes<<",\"Stamina\":"<<state.stamina<<",\"AutoJump\":"<<state.auto_jump
        <<",\"AutoJumpTimer\":"<<state.auto_jump_timer<<",\"varJumpTimer\":"<<state.var_jump_timer<<",\"jumpGraceTimer\":"<<state.jump_grace_timer
        <<",\"wallSlideTimer\":"<<state.wall_slide_timer<<",\"forceMoveXTimer\":"<<state.force_move_x_timer<<",\"onGround\":"<<state.on_ground<<",\"groundQuery\":"<<player.ground_query()
        <<",\"animation\":\""<<pose.animation<<"\",\"animationFrame\":"<<pose.animation_frame<<",\"spriteScale\":";vec(pose.scale);
    std::cout<<",\"hairNodes\":[";for(unsigned i=0;i<pose.hair_nodes.size();++i) { if(i)std::cout<<',';vec(pose.hair_nodes[i]); }
    std::cout<<"],\"camera\":";vec(session.camera());
    std::cout<<",\"respawn\":";vec(session.respawn_point());
    std::cout<<",\"pendingEOF\":"<<session.pending_end_of_frame()<<",\"Transitioning\":"<<bool(session.transition())<<",\"ownsOutgoingRoom\":"<<session.owns_outgoing_room()<<",\"NextTransitionDuration\":"<<session.next_transition_duration()
        <<",\"chaserCount\":"<<session.chaser_history().size()<<",\"TimeActive\":"<<session.time_active()<<",\"RawTimeActive\":"<<session.raw_time_active()
        <<",\"FrameCounter\":"<<session.context().clock.frame_counter<<",\"FreezeTimer\":"<<session.context().clock.freeze_timer
        <<",\"TimeRate\":"<<session.context().clock.time_rate<<",\"TimeRateB\":"<<session.context().clock.time_rate_b
        <<",\"sessionTime\":"<<session.stats().session_time<<",\"saveTime\":"<<session.stats().save_time
        <<",\"roomDeaths\":"<<session.stats().room_deaths<<",\"sessionDeaths\":"<<session.stats().session_deaths<<",\"saveDeaths\":"<<session.stats().save_deaths
        <<",\"saveJumps\":"<<session.stats().jumps<<",\"sessionDashes\":"<<session.stats().session_dashes<<",\"saveDashes\":"<<session.stats().save_dashes
        <<",\"rng\":{\"id\":"<<session.random().object_identity()<<",\"calls\":"<<session.random().calls()<<",\"words\":[";
    bool first=true;for(auto word:session.random().state_words()) { if(!first)std::cout<<',';first=false;std::cout<<word; }
    std::cout<<"]},\"entities\":[";first=true;
    for(const auto& entry:session.room_roster()) { if(!first)std::cout<<',';first=false;entity(entry,session.world()); }
    std::cout<<"],\"pending\":[";first=true;for(const auto* pending:session.pending_room_entities()) { if(!first)std::cout<<',';first=false;std::cout<<pending->object_identity; }
    std::cout<<"],\"colliderOrder\":[";first=true;
    for(const auto& collider:session.world().ordered_colliders) {
        const RoomEntity* owner=nullptr;
        for(const auto& entry:session.room_roster()) if(entry.entity) {
            if(const auto* spike=std::get_if<StaticSpike>(&entry.entity->object)) if(spike==collider.spike) owner=entry.entity;
            if(const auto* spring=std::get_if<RoomSpring>(&entry.entity->object)) if(&spring->body==collider.unsupported_body) owner=entry.entity;
            if(const auto* berry=std::get_if<RoomStrawberry>(&entry.entity->object)) if(&berry->body==collider.unsupported_body) owner=entry.entity;
        }
        if(!owner) throw std::logic_error("Published collider has no live room owner");
        if(!first) std::cout<<',';
        first=false;
        std::cout<<owner->object_identity;
    }
    std::cout<<"],\"transition\":";
    if(const auto* transition=session.transition()) {
        std::cout<<"{\"id\":"<<transition->object_identity<<",\"loaded\":"<<transition->loaded<<",\"active\":"<<transition->routine.active
            <<",\"finished\":"<<transition->routine.finished()<<",\"wait\":"<<transition->routine.wait_timer()<<",\"cameraAt\":"<<transition->camera_at<<",\"cameraFrom\":";vec(transition->camera_from);
        std::cout<<",\"cameraTo\":";vec(transition->camera_to);std::cout<<",\"playerTo\":";vec(transition->player_to);
        std::cout<<",\"outgoing\":[";first=true;for(const auto* value:transition->outgoing) { if(!first)std::cout<<',';first=false;std::cout<<value->object_identity; }
        std::cout<<"]}";
    } else std::cout<<"null";
    std::cout<<"}}\n";
}
void expect_guard(const char* member,const std::function<void()>& operation) {
    try { operation(); }
    catch(const std::runtime_error& error) {
        if(std::string(error.what()).find(member)==std::string::npos) throw;
        std::cout<<"{\"event\":\"native-guard\",\"member\":\""<<member<<"\",\"rejected\":true}\n";
        return;
    }
    throw std::runtime_error(std::string("Unsupported guard bypass: ")+member);
}
const char* draw_kind_name(draw_order::OwnerKind kind) {
    using namespace draw_order;
    switch(kind) {
    case OwnerKind::background_tiles: return "BackgroundTiles";
    case OwnerKind::decal: return "Decal";
    case OwnerKind::particle_system_back: case OwnerKind::particle_system_mid: case OwnerKind::particle_system_front:
        return "ParticleSystem";
    case OwnerKind::scene_helper: return "Entity";
    case OwnerKind::wind: return "WindController";
    case OwnerKind::hud_display: return "TotalStrawberriesDisplay";
    case OwnerKind::player: return "Player";
    case OwnerKind::spikes: return "Spikes";
    case OwnerKind::jumpthru_platform: return "JumpthruPlatform";
    case OwnerKind::strawberry: return "Strawberry";
    case OwnerKind::spring: return "Spring";
    case OwnerKind::solid_tiles: return "SolidTiles";
    }
    throw std::invalid_argument("Unknown draw owner kind");
}
std::uint64_t decal_identity(bool background,bool banner,int source_index) {
    return (std::uint64_t(background?1:2)<<32) | (std::uint64_t(banner?1:0)<<31) | std::uint64_t(source_index);
}
std::vector<draw_order::AuthoredDecalOwners> authored_first_room_decals(const DecalAssets& decals,const RoomDefinition& room) {
    draw_order::AuthoredDecalOwners authored{&room,{}};
    for(const auto& instance:decals.instances)
        authored.owners.push_back({draw_order::OwnerKind::decal,decal_identity(instance.background,false,instance.source_index),
            instance.source_index,&room,instance.depth(),unsigned(instance.source_index),true,false,false});
    for(const auto& omitted:decals.omitted)
        authored.owners.push_back({draw_order::OwnerKind::decal,decal_identity(omitted.background,true,omitted.source_index),
            omitted.source_index,&room,omitted.background?9000:-10500,unsigned(omitted.source_index),true,false,true});
    return {authored};
}
void draw_owners(int tick,const FirstRoomSession& session,const RoomDefinition& initial_room,
                 const std::vector<draw_order::AuthoredDecalOwners>& authored) {
    const auto projection=draw_order::project(draw_order::snapshot(session,&initial_room),authored);
    std::cout<<"{\"event\":\"draw-owner-roster\",\"tick\":"<<tick<<",\"live\":[";
    bool first=true;
    for(const auto& owner:projection.live) {
        if(!first) std::cout<<',';
        first=false;
        std::cout<<"{\"kind\":\""<<draw_kind_name(owner.kind)<<"\",\"identity\":"<<owner.identity
            <<",\"authoredId\":"<<owner.authored_id<<",\"room\":\""<<(owner.room?owner.room->name:"")<<"\""
            <<",\"sortDepthBand\":"<<owner.sort_depth_band<<",\"sequence\":"<<owner.sequence
            <<",\"visible\":"<<owner.visible<<",\"hudExcluded\":"<<owner.hud_excluded
            <<",\"banner\":"<<owner.banner<<'}';
    }
    std::cout<<"],\"decalGapRooms\":[";
    first=true;
    for(const auto* room:projection.decal_gap_rooms) {
        if(!first) std::cout<<',';
        first=false;
        std::cout<<'"'<<room->name<<'"';
    }
    std::cout<<"]}\n";
    std::cout<<"{\"event\":\"draw-owner-dispatch\",\"tick\":"<<tick<<",\"order\":[";
    first=true;
    for(const auto index:projection.dispatch) {
        if(!first) std::cout<<',';
        first=false;
        std::cout<<projection.live[index].identity;
    }
    std::cout<<"]}\n";
}
}
int main(int argc,char** argv) {
    try {
        const bool player_commands=argc>=3 && std::string(argv[argc-2])=="--player-commands";
        const int legacy_argc=argc-(player_commands?2:0);
        if(legacy_argc!=7 && legacy_argc!=8) throw std::invalid_argument("Expected mask, first-room hazards, metadata, room catalog, legal controls, seed"
            " and optional authored first-room decal metadata, then optional --player-commands logical-mapping");
        const auto mask=read_asset(argv[1],4'000'512),hazards=read_asset(argv[2],8192),metadata=read_asset(argv[3],65536);
        Room room(parse_mask(mask,checksum(mask)),parse_spikes(hazards,checksum(hazards)));
        const auto assets=parse_player_assets(metadata,checksum(metadata));const auto catalog=read_catalog(argv[4]);
        std::vector<draw_order::AuthoredDecalOwners> authored;
        if(legacy_argc==8) {
            const auto decal_text=read_asset(argv[7],65536);
            authored=authored_first_room_decals(parse_decals(decal_text,checksum(decal_text)),catalog.first());
        }
        std::vector<native_test::LogicalPlayerFrame> player_mapping;
        if(player_commands) {
            std::ifstream mapping(argv[argc-1]);
            player_mapping=native_test::read_player_draw_mapping(mapping,assets.bank);
        }
        const std::string seed_text=argv[6];std::size_t used=0;const int seed=std::stoi(seed_text,&used);
        if(used!=seed_text.size()) throw std::invalid_argument("Invalid seed");
        FirstRoomSession session(room.world,assets.bank,false,seed,&catalog);
        Controller controller;std::ifstream controls(argv[5]);if(!controls) throw std::runtime_error("Cannot read legal controls");
        std::cout<<std::setprecision(std::numeric_limits<float>::max_digits10)<<std::boolalpha;
        std::set<const RoomRuntime*> observed_rooms;
        std::vector<Controls> route_controls;
        int tick=0,x=0,y=0,jump=0,dash=0,grab=0,expected=0;
        while(controls>>tick>>x>>y>>jump>>dash>>grab) {
            if(tick!=expected++ || expected>3600 || x<-1 || x>1 || y<-1 || y>1 || jump<0 || jump>1 || dash<0 || dash>1 || grab<0 || grab>1)
                throw std::invalid_argument("Invalid legal controls");
            Controls raw;raw.left=x<0;raw.right=x>0;raw.up=y<0;raw.down=y>0;raw.cross=jump;raw.square=dash;raw.l=grab;
            route_controls.push_back(raw);
            const auto input=controller.sample(raw).player;
            session.step(1.f/60,input,[&](SessionPhase phase,const FirstRoomSession& observed) {
                for(const auto& entry:observed.room_roster()) if(entry.room && observed_rooms.insert(entry.room).second) {
                    std::cout<<"{\"event\":\"room-scope\",\"tick\":"<<(phase==SessionPhase::before_frame && tick==0 ? -1 : tick)
                        <<",\"room\":\""<<entry.room->definition.name<<"\",\"seed\":"<<entry.room->scoped_random.initial_seed()<<",\"calls\":"<<entry.room->scoped_random.calls()<<"}\n";
                    if(tick==0) for(const auto& event:entry.room->random_events)
                        std::cout<<"{\"event\":\"rng\",\"tick\":-1,\"phase\":\"bootstrap\",\"operation\":\""<<event.first<<"\",\"room\":\""<<entry.room->definition.name<<"\",\"calls\":"<<event.second<<"}\n";
                }
                if(phase==SessionPhase::before_eof) for(const auto& event:observed.random_events())
                    std::cout<<"{\"event\":\"rng\",\"tick\":"<<tick<<",\"phase\":\"before-update\",\"operation\":\""<<event.operation
                        <<"\",\"room\":\""<<event.room<<"\",\"calls\":"<<event.calls<<"}\n";
                if(phase==SessionPhase::before_frame)
                    std::cout<<"{\"event\":\"input\",\"tick\":"<<tick<<",\"moveX\":"<<input.x<<",\"moveY\":"<<input.y
                        <<",\"aim\":["<<input.aim_x<<','<<input.aim_y<<']'
                        <<",\"jumpCheck\":"<<observed.context().jump.check()<<",\"jumpPressed\":"<<observed.context().jump.pressed()
                        <<",\"jumpReleased\":"<<observed.context().jump.released()<<",\"jumpBuffer\":"<<observed.context().jump.buffer_counter()
                        <<",\"dashCheck\":"<<observed.context().dash.check()<<",\"dashPressed\":"<<observed.context().dash.pressed()
                        <<",\"dashBuffer\":"<<observed.context().dash.buffer_counter()<<",\"climb\":"<<input.grab
                        <<",\"buttons\":{\"Left\":"<<raw.left<<",\"Right\":"<<raw.right<<",\"Up\":"<<raw.up<<",\"Down\":"<<raw.down<<",\"C\":"<<raw.cross<<",\"X\":"<<raw.square<<",\"Z\":"<<raw.l<<"}}\n";
                record(tick,phase,observed);
                if(phase==SessionPhase::after_frame) draw_owners(tick,observed,catalog.first(),authored);
            });
            if(player_commands) {
                const std::string phase=session.phase();
                if(phase!="live" && phase!="respawn14") throw std::runtime_error("Unsupported Player command trace phase: "+phase);
                const auto cached=session.draw();
                native_test::write_player_draw(std::cout,tick,session.player().object_identity(),phase=="live",assets.bank,player_mapping,cached);
            }
        }
        if(!controls.eof() || !expected) throw std::invalid_argument("Incomplete controls");
        for(const auto& entry:session.room_roster()) if(entry.entity) {
            if(const auto* spring=std::get_if<RoomSpring>(&entry.entity->object)) expect_guard("Spring.OnCollide",[&] { Player probe(session.world(),spring->body.position);probe.frame(0); });
            if(const auto* berry=std::get_if<RoomStrawberry>(&entry.entity->object)) expect_guard("Strawberry.OnPlayer",[&] { Player probe(session.world(),berry->body.position);probe.frame(0); });
        }
        expect_guard("Room2 death/reload",[&] { Player probe(session.world(),session.respawn_point());probe.die({}); });
        const auto replay_until=[&](Session& replay,Controller& replay_controller,bool incoming) {
            for(const auto& raw:route_controls) {
                replay.step(replay_controller.sample(raw));
                if(incoming ? replay.lifecycle()->room_definition()!=&catalog.first() : replay.lifecycle()->transition()!=nullptr) return;
            }
            throw std::runtime_error("Negative API fixture did not reach a natural transition");
        };
        expect_guard("Room2 diagnostic reload",[&] {
            Session replay(room.world,assets.bank,false,seed,&catalog);Controller replay_controller;
            replay_until(replay,replay_controller,true);
            Controls reset;reset.triangle=true;replay.step(replay_controller.sample(reset));
        });
        expect_guard("Dash/freeze crossing",[&] {
            Session replay(room.world,assets.bank,false,seed,&catalog);Controller replay_controller;
            replay_until(replay,replay_controller,false);
            Controls dash_input;dash_input.square=true;replay.step(replay_controller.sample(dash_input));
        });
        std::cout<<"{\"event\":\"native-ended\",\"frames\":"<<expected<<",\"reloads\":"<<session.stats().reloads<<",\"loads\":"<<session.stats().loads<<"}\n";
        return 0;
    } catch(const std::exception& error) { std::cerr<<error.what()<<'\n';return 1; }
}
