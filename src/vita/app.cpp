#include "asset_pins.hpp"
#include "assets.hpp"
#include "diagnostic.hpp"
#include "draw.hpp"
#include "guest_io.hpp"
#ifdef CELESTE_ROOM_GUEST_REPLAY
#include "guest_replay.hpp"
#endif
#include <psp2/ctrl.h>
#include <psp2/io/fcntl.h>
#include <psp2/kernel/processmgr.h>
#include <cstdarg>
#include <cstdio>
#include <stdexcept>

namespace {
using namespace celeste::diagnostic;
#ifdef CELESTE_ROOM_GUEST_REPLAY
static_assert(guest_replay_enabled,"Replay build requires matching staging intent");
#else
static_assert(!guest_replay_enabled,"Manual build cannot use replay staging");
#endif
#ifdef CELESTE_ROOM_CAPTURE_AFTER_WALL_JUMP
constexpr bool capture_after_wall_jump = true;
#else
constexpr bool capture_after_wall_jump = false;
#endif
#ifdef CELESTE_ROOM_CAPTURE_AFTER_CLIMB
constexpr bool capture_after_climb = true;
#else
constexpr bool capture_after_climb = false;
#endif
constexpr const char* log_path = "ux0:data/celeste_native_room.log";
void log(const char* format, ...) {
    va_list args;
    va_start(args, format);
    const auto result = std::vfprintf(stderr, format, args);
    va_end(args);
    if (result < 0 || std::fputc('\n', stderr) == EOF || std::fflush(stderr))
        throw std::runtime_error("Guest log write/flush failed");
}
void signal(const char* event, unsigned frame) {
    char text[128];
    const int length = std::snprintf(text,sizeof(text),"%s frame=%u\n",event,frame);
    if (length < 0 || length >= static_cast<int>(sizeof(text))) throw std::runtime_error("Readiness serialization failed");
    write_guest_file("ux0:data/celeste_native_room.ready",std::string_view(text,length),SCE_O_TRUNC);
}
void state(const char* event, unsigned frame, const Session& session) {
    const auto& player = session.player();
    const auto position = player.actor().body.position;
    log("%s frame=%u x=%.0f y=%.0f vx=%.3f vy=%.3f ground=%d dead=%d resets=%u state=%d freeze=%.9f dashes=%d move_x=%d force_x=%d force_timer=%.9f var_timer=%.9f jump_buffer=%.9f jump_kind=%s stamina=%.9f grab=%d",event,frame,
         position.x,position.y,player.state().speed.x,player.state().speed.y,
         player.state().on_ground,player.death().dead,session.resets(),player.state_machine().state(),player.clock().freeze_timer,player.state().dashes,
         player.state().move_x,player.state().force_move_x,player.state().force_move_x_timer,player.state().var_jump_timer,
          player.jump_button().buffer_counter(),jump_kind_name(player.jump_kind()),player.state().stamina,player.grab_held());
}
void run() {
    log("Celeste native room DIAGNOSTIC boot revision=%s fixed_step=1/60 manual_reset=Triangle jump=Cross dash=Square aim=DPad exit=Start", revision);
#ifdef CELESTE_ROOM_GUEST_REPLAY
    log("guest replay fixture=%s fixture_sha256=%s input_source=scripted_guest_controls max_frames=%u physical_controller_verified=false host_input_injected=false",
        guest_replay_id,guest_replay_sha256,guest_replay_frames);
#endif
    Room room(parse_mask(read_asset("app0:assets/native-room/global.mask",4'000'512),mask_checksum),
              parse_spikes(read_asset("app0:assets/native-room/hazards.txt",8192),spike_checksum));
    if (room.grid.columns() != 541 || room.grid.rows() != 440 || room.solids.position.x != -64 ||
        room.solids.position.y != -3272 || room.spikes.size() != 5)
        throw std::runtime_error("Unexpected selected room geometry profile");
    unsigned occupied = 0, visible = 0;
    for (int y=0; y<room.grid.rows(); ++y) for (int x=0; x<room.grid.columns(); ++x) {
        if (!room.grid.at(x,y)) continue;
        ++occupied;
        const auto px = room.solids.position.x+x*8, py=room.solids.position.y+y*8;
        if (px < 320 && px+8 > 0 && py < 180 && py+8 > 0) ++visible;
    }
    if (occupied != 26915 || visible != 363) throw std::runtime_error("Unexpected merged/visible solid counts");
    log("assets ready mask=541x440 origin=-64,-3272 occupied=%u visible=%u spikes=%u",occupied,visible,unsigned(room.spikes.size()));
    const VisualAssets* visual_assets = nullptr;
    const DecalAssets* decal_assets = nullptr;
#ifdef CELESTE_ROOM_TEXTURED
    const auto visuals = parse_visuals(read_asset("app0:assets/native-room/visuals.txt",65'536),visual_checksum);
    visual_assets = &visuals;
#ifdef CELESTE_ROOM_SPIKE_ART
    if (!visuals.spike_art()) throw std::runtime_error("Spike-art intent requires the eight-texture source protocol");
    validate_spike_art(visuals,room.spikes);
    log("render source_static_spikes physical_spikes=5 draw_pieces=19 diagnostic_red_markers=0 depth=-1 FG_occludes_source_parts");
#else
#ifndef CELESTE_ROOM_ANIMATED_PLAYER
    log("render style=textured_partial static_BG_BODY_FG body=idle00_static_no_animation camera=0,0 diagnostic_spike_markers=5 not_faithful_spike_art no_hair_decals_backdrops_animation_audio_menu_fullgame_fidelity submitted_RGBA_bytes=164864 not_physical_GPU_allocation");
#endif
#endif
#ifdef CELESTE_ROOM_DECALS
    const auto decals = parse_decals(read_asset("app0:assets/native-room/decals.txt",65'536),decal_checksum);
    decal_assets = &decals;
    log("render static_decals=22 bg_decals=20 fg_decals=2 animated_omitted=7 source_static_decal_cut render_order=BG_tiles_20BG_player_19spikes_FGtiles_2FG page=64x128 RGBA_bytes=32768");
#endif
#else
    log("render style=debug hitboxes_and_diagnostic_spike_markers camera=0,0");
#endif
    const PlayerAssets* player_assets=nullptr;
#ifdef CELESTE_ROOM_ANIMATED_PLAYER
    const auto player_frames=parse_player_assets(read_asset("app0:assets/native-room/player.txt",65'536),player_checksum);
    player_assets=&player_frames;
#ifdef CELESTE_ROOM_SPIKE_ART
#ifdef CELESTE_ROOM_DECALS
    constexpr const char* decal_scope = "static_decals=22 bg_decals=20 fg_decals=2 animated_omitted=7";
#else
    constexpr const char* decal_scope = "no_death_art_decals";
#endif
    log("render animated_player_partial mode=Madeline bank=player source_bank_sha256=%s diagnostic_rng_seed=0 original_startup_rng_parity=false pages=%u player_RGBA_bytes=%u BG_HAIR_BODY_source_static_spikes_FG physical_spikes=5 draw_pieces=19 diagnostic_red_markers=0 decal_scope=%s backdrops_audio_menu_fullgame_fidelity",
        player_bank_sha256,player_frames.bank.pages,player_frames.bank.pages*128*64*4,decal_scope);
#else
    log("render animated_player_partial mode=Madeline bank=player source_bank_sha256=%s diagnostic_rng_seed=0 original_startup_rng_parity=false pages=%u player_RGBA_bytes=%u BG_HAIR_BODY_diagnostic_markers_FG no_death_art_decals_backdrops_audio_menu_fullgame_fidelity",
        player_bank_sha256,player_frames.bank.pages,player_frames.bank.pages*128*64*4);
#endif
#endif
    initialize_graphics();
    try {
    if (visual_assets) load_textures(*visual_assets);
    if (decal_assets) load_decal_textures(*decal_assets);
    if (player_assets) load_player_textures(*player_assets);
#ifndef CELESTE_ROOM_GUEST_REPLAY
    const int mode = sceCtrlSetSamplingMode(SCE_CTRL_MODE_DIGITAL);
    if (mode < 0) throw std::runtime_error("Controller initialization failed: " + std::to_string(mode));
#endif
    Session session(room.world,{19,144},player_assets ? &player_assets->bank : nullptr,0);
    const auto render=[&](const char* path,unsigned frame) {
        const auto projection=session.projection();
        if(player_assets) {
            PlayerRender animated{*player_assets,*session.presentation(),projection};
            return draw(room,session.player(),path,frame,session.resets(),visual_assets,&animated,decal_assets);
        }
        return draw(room,session.player(),path,frame,session.resets(),visual_assets,nullptr,decal_assets);
    };
    Controller controller;
#ifdef CELESTE_ROOM_GUEST_REPLAY
    GuestReplay replay;
    bool replay_jumped=false,replay_frozen=false,replay_thawed=false,replay_launched=false,replay_dash_done=false,replay_died=false,replay_reset=false;
#endif
    unsigned previous = 0, frame = 0;
    const std::string frame_path = std::string("ux0:data/celeste_native_room-")+revision+".ppm";
    bool captured = !capture_after_wall_jump && !capture_after_climb, wall_near = false, wall_forced = false;
    bool climb_near = false, climbed = false, climb_held = false, climb_released = false, climb_landed = false;
    float climb_entry_y = 0.0f;
    const auto exported = render(captured ? frame_path.c_str() : nullptr,0);
    if (captured) log("%s",exported.c_str());
    log("capture policy=%s",capture_after_climb ? "climb" : capture_after_wall_jump ? "wall_jump" : "spawn");
    state("frame ready",frame,session);
    signal("ready",frame);
    const auto start_time = sceKernelGetProcessTimeWide();
    while (!session.exiting()) {
#ifdef CELESTE_ROOM_GUEST_REPLAY
        const auto controls = replay.next(frame);
        const auto bit=[](bool held,unsigned flag) { return held?flag:0u; };
        const unsigned buttons = bit(controls.left,SCE_CTRL_LEFT)|bit(controls.right,SCE_CTRL_RIGHT)|
            bit(controls.up,SCE_CTRL_UP)|bit(controls.down,SCE_CTRL_DOWN)|bit(controls.cross,SCE_CTRL_CROSS)|
            bit(controls.triangle,SCE_CTRL_TRIANGLE)|bit(controls.start,SCE_CTRL_START)|
            bit(controls.square,SCE_CTRL_SQUARE)|bit(controls.l,SCE_CTRL_LTRIGGER);
        const auto sample = controller.sample(controls);
#else
        SceCtrlData pad{};
        const int result = sceCtrlPeekBufferPositive(0,&pad,1);
        if (result != 1) throw std::runtime_error("Controller sample failed: " + std::to_string(result));
        const auto buttons = pad.buttons;
        const auto down = [&](unsigned flag) { return (buttons & flag) != 0; };
        const auto sample = controller.sample({down(SCE_CTRL_LEFT),down(SCE_CTRL_RIGHT),down(SCE_CTRL_UP),down(SCE_CTRL_DOWN),
                                               down(SCE_CTRL_CROSS),down(SCE_CTRL_TRIANGLE),down(SCE_CTRL_START),down(SCE_CTRL_SQUARE),down(SCE_CTRL_LTRIGGER)});
#endif
        const bool changed = buttons != previous;
        if (changed) log("input frame=%u buttons=%08x x=%d y=%d cross_held=%d cross_pressed=%d reset=%d exit=%d square_held=%d square_pressed=%d grab=%d",frame,
                         unsigned(buttons),sample.player.x,sample.player.y,sample.player.jump.held,sample.player.jump.pressed,sample.reset,sample.exit,
                          sample.player.dash_button.held,sample.player.dash_button.pressed,sample.player.grab);
        const bool dead = session.player().death().dead;
        const int old_state = session.player().state_machine().state();
        const bool frozen = session.player().clock().freeze_timer > 0.0f;
        const unsigned dash_events = session.player().state().dash_events;
        const unsigned jumps = session.player().jump_count();
        session.step(sample);
        if (session.exiting()) break;
        ++frame;
        const auto& player = session.player();
        const bool jumped = !sample.reset && player.jump_count() != jumps;
        const bool wall_jumped = jumped && player.jump_kind() == celeste::JumpKind::wall_jump;
        const auto* presentation=session.presentation();
        const bool animated_climb_ready=!presentation ||
            ((presentation->pose().animation=="climbUp" || presentation->pose().animation=="climbup") &&
             presentation->pose().animation_frame>0 && player.state().speed.y<0 &&
             presentation->pose().hair_nodes[0].x>=0 && presentation->pose().hair_nodes[0].x<320 &&
             presentation->pose().hair_nodes[0].y>=0 && presentation->pose().hair_nodes[0].y<180);
        if (capture_after_climb && !climbed && player.state_machine().state() == 1) climb_entry_y = player.actor().body.position.y;
        const bool capture = !captured && ((capture_after_wall_jump && wall_jumped) ||
            (capture_after_climb && player.state_machine().state() == 1 && !player.state().on_ground &&
              player.state().stamina < 109.0f && player.grab_held() && sample.player.y == -1 && player.actor().body.position.y < climb_entry_y && animated_climb_ready));
        const auto saved = render(capture ? frame_path.c_str() : nullptr,frame);
        if (capture) { captured = true; log("%s",saved.c_str()); }
        if (jumped) state("jump",frame,session);
        const int new_state = player.state_machine().state();
        if (!sample.reset && old_state != new_state)
            log("dash transition frame=%u from=%d to=%d freeze=%.9f dashes=%d",frame,old_state,new_state,player.clock().freeze_timer,player.state().dashes);
        if (!sample.reset && frozen != (player.clock().freeze_timer > 0.0f))
            log("freeze transition frame=%u from=%d to=%d state=%d",frame,frozen,player.clock().freeze_timer > 0.0f,new_state);
        if (!sample.reset && player.state().dash_events > dash_events)
            log("dash launch frame=%u state=%d dir_x=%.6f dir_y=%.6f vx=%.3f vy=%.3f",frame,new_state,
                player.state().dash_dir.x,player.state().dash_dir.y,player.state().speed.x,player.state().speed.y);
        const bool died = !dead && session.player().death().dead;
#ifdef CELESTE_ROOM_GUEST_REPLAY
        replay_jumped = replay_jumped || jumped;
        replay_frozen = replay_frozen || player.clock().freeze_timer>0;
        replay_thawed = replay_thawed || (frozen && player.clock().freeze_timer<=0);
        replay_launched = replay_launched || (!sample.reset && player.state().dash_events>dash_events);
        replay_dash_done = replay_dash_done || (old_state==2 && new_state==0);
        replay_died = replay_died || died;
        replay_reset = replay_reset || (dead && sample.reset && !player.death().dead && session.resets()==2);
#endif
        if (died || sample.reset || changed || frame%120 == 0) state(died ? "death" : sample.reset ? "manual reset" : "frame",frame,session);
        if ((capture_after_wall_jump || capture_after_climb) && !wall_near && !player.state().on_ground && player.actor().body.position.x <= 14 &&
            sample.player.x == -1 && sample.player.jump.held && player.jump_kind() == celeste::JumpKind::jump) {
            wall_near = true;
            signal("wall_near",frame);
        } else if (capture_after_wall_jump && !wall_forced && !wall_jumped && player.jump_kind() == celeste::JumpKind::wall_jump &&
                   player.state().force_move_x_timer > 0 && player.state().move_x == 1 && player.state().speed.x > 0) {
            wall_forced = true;
            state("wall forced",frame,session);
            signal("wall_forced",frame);
        } else if (capture_after_climb && !climb_near && wall_near && !player.state().on_ground && player.state().speed.y >= 0 && !sample.player.jump.held) {
            climb_near = true;
            signal("climb_near",frame);
        } else if (capture_after_climb && !climbed && new_state == 1) {
            climbed = true;
            state("climb entered",frame,session);
            signal("climb_entered",frame);
        } else if (capture_after_climb && capture) {
            state("climb drained",frame,session);
            signal("climb_drained",frame);
        } else if (capture_after_climb && captured && climbed && !climb_held && new_state == 1 && sample.player.y == 0 && player.state().speed.y == 0) {
            climb_held = true;
            state("climb held",frame,session);
            signal("climb_held",frame);
        } else if (capture_after_climb && climbed && !climb_released && !sample.player.grab && new_state == 0) {
            climb_released = true;
            state("climb released",frame,session);
            signal("climb_released",frame);
        } else if (capture_after_climb && climb_released && !climb_landed && player.state().on_ground) {
            climb_landed = true;
            state("climb landed",frame,session);
            signal("climb_landed",frame);
        } else if (died || sample.reset || changed) signal(died ? "dead" : sample.reset ? "reset" : "sampled",frame);
        else if (old_state == 2 && new_state == 0) signal("dash_done",frame);
        previous = buttons;
    }
#ifdef CELESTE_ROOM_GUEST_REPLAY
    if(frame!=guest_replay_frames-1 || !captured || !climbed || !climb_held || !climb_released || !climb_landed ||
       !replay_jumped || !replay_frozen || !replay_thawed || !replay_launched || !replay_dash_done || !replay_died || !replay_reset)
        throw std::runtime_error("Guest replay ended without all observed native checkpoints");
#endif
    const auto elapsed = sceKernelGetProcessTimeWide()-start_time;
    state("clean exit",frame,session);
#ifdef CELESTE_ROOM_GUEST_REPLAY
    log("guest replay completed samples=%u",guest_replay_frames);
#endif
    log("diagnostic measurement frames=%u elapsed_us=%llu observed_fps=%.3f not_a_hardware_estimate",frame,
         static_cast<unsigned long long>(elapsed),elapsed ? frame*1e6/double(elapsed) : 0);
    } catch (const std::exception& error) {
        try { finish_graphics(); }
        catch (const std::exception& cleanup) { throw std::runtime_error(std::string(error.what())+"; graphics teardown also failed: "+cleanup.what()); }
        throw;
    }
    finish_graphics();
}
}
int main() {
    FILE* initial = std::fopen(log_path,"w");
    if (!initial) { sceKernelExitProcess(1); return 1; }
    if (std::fclose(initial) || !std::freopen(log_path,"w",stderr) || std::setvbuf(stderr,nullptr,_IONBF,0)) {
        sceKernelExitProcess(1); return 1;
    }
    int status = 0;
    try { run(); }
    catch (const std::exception& error) {
        status = 1;
        if (std::fprintf(stderr,"FATAL: %s\n",error.what()) < 0 || std::fflush(stderr)) status = 2;
        try {
            const auto failure_path = std::string("ux0:data/celeste_native_room-failure-")+celeste::diagnostic::revision+".txt";
            celeste::diagnostic::write_guest_file(failure_path.c_str(),std::string("FATAL revision=")+celeste::diagnostic::revision+" cause="+error.what()+"\n",SCE_O_EXCL);
            signal("failed",0);
        } catch (const std::exception& diagnostic_error) {
            status = 2;
            std::fprintf(stderr,"Failure receipt also failed: %s; original: %s\n",diagnostic_error.what(),error.what());
        }
    }
    if (std::fclose(stderr)) status = 2;
#ifdef CELESTE_ROOM_GUEST_REPLAY
    if(status==0) {
        try {
            const auto complete_path=std::string("ux0:data/celeste_native_room-complete-")+celeste::diagnostic::revision+".txt";
            celeste::diagnostic::write_guest_file(complete_path.c_str(),std::string("complete revision=")+celeste::diagnostic::revision+
                " input_source=scripted_guest_controls fixture="+celeste::diagnostic::guest_replay_id+" status=0\n",SCE_O_EXCL);
        } catch(const std::exception& error) {
            status=2;
            if(FILE* failure_log=std::fopen(log_path,"a")) {
                std::fprintf(failure_log,"FATAL: completion receipt failed: %s\n",error.what());
                std::fclose(failure_log);
            }
        }
    }
#endif
    sceKernelExitProcess(status);
    return status;
}
