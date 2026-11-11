#include "asset_pins.hpp"
#include "assets.hpp"
#include "diagnostic.hpp"
#include "draw.hpp"
#include "guest_io.hpp"
#include "session_profile.hpp"
#include "capture_policy.hpp"
#include "normal_outputs.hpp"
#include "platform_diagnostics.hpp"
#ifdef CELESTE_ROOM_DASH_PROBE
#include "guest_dash_probe_observer.hpp"
#endif
#ifdef CELESTE_ROOM_GUEST_REPLAY
#include "guest_replay.hpp"
#endif
#ifdef CELESTE_ROOM_GUEST_AUTOMATIC
#include "guest_automatic_observer.hpp"
#endif
#include <psp2/ctrl.h>
#include <psp2/io/fcntl.h>
#include <psp2/kernel/processmgr.h>
#include <cstdarg>
#include <cstdio>
#include <stdexcept>

namespace {
using namespace celeste::diagnostic;
#if defined(CELESTE_ROOM_DASH_PROBE) != defined(CELESTE_STAGED_DASH_PROBE)
#error "Dash probe mode requires matching staging; production cannot use probe staging"
#endif
#ifdef CELESTE_ROOM_DASH_PROBE
static_assert(std::string_view(guest_dash_probe)==guest_dash_probe_id && guest_dash_probe_samples==guest_dash_probe_frames &&
              guest_dash_probe_exit_frame==guest_dash_probe_frames-1,"Dash probe staging fixture differs from its source header");
GuestDashProbeCompletion dash_completion;
std::string dash_failure_record(const char* cause) {
    return bounded_guest_record<2048>("Dash probe failure receipt exceeds bound",
        "FATAL revision=%s fixture=%s fixture_sha256=%s capture=dash_trails cause=%s\n",
        revision,guest_dash_probe_id,guest_dash_probe_sha256,cause);
}
#endif
#ifdef CELESTE_ROOM_GUEST_REPLAY
static_assert(guest_replay_enabled,"Replay build requires matching staging intent");
#else
static_assert(!guest_replay_enabled,"Manual build cannot use replay staging");
#endif
#ifdef CELESTE_ROOM_GUEST_AUTOMATIC
static_assert(guest_automatic!=nullptr,"Automatic guest build requires matching staging intent");
#else
static_assert(guest_automatic==nullptr,"Production or legacy build cannot use automatic guest staging");
#endif
const char* log_path = "ux0:data/celeste_native_room.log";
NormalOutputPaths normal_outputs;
bool normal_ready_written=false,normal_capture_closed=false;
FrameMetrics frame_metrics;
bool measuring_frame=false;
void log(const char* format, ...) {
    const bool measured=normal_initial_respawn_profile && measuring_frame;
    const auto begin=measured ? process_now_us() : 0;
    va_list args;
    va_start(args, format);
    const auto result = std::vfprintf(stderr, format, args);
    va_end(args);
    if (result < 0 || std::fputc('\n', stderr) == EOF || std::fflush(stderr))
        throw std::runtime_error("Guest log write/flush failed");
    if(measured) frame_metrics.log_success(begin,process_now_us());
}
void metrics_summary(const char* reason) {
    const auto summary=frame_metrics.summary(reason,normal_outputs.run_id,revision,process_clock_provenance);
    log("%.*s",int(summary.size-1),summary.text.data());
}
void finish_metrics_frame(std::uint64_t step_begin,std::uint64_t step_end,bool rendered,std::uint64_t render_begin,std::uint64_t render_end,bool exiting) {
    const bool periodic=frame_metrics.summary_due();
    if(periodic || exiting) frame_metrics.mark_summary();
    frame_metrics.record_span(MetricCategory::step,step_begin,step_end);
    if(rendered) frame_metrics.record_span(MetricCategory::render_including_swap_capture,render_begin,render_end);
    if(periodic) metrics_summary("periodic");
    frame_metrics.finish_log();
    measuring_frame=false;
}
void signal(const char* event, unsigned frame) {
    if constexpr(normal_initial_respawn_profile) {
        const auto text=normal_outputs.record(event,normal_capture_closed ? "fresh_closed" : "pending")+"frame="+std::to_string(frame)+"\n";
        write_guest_file(normal_outputs.ready.c_str(),text,normal_ready_written ? SCE_O_TRUNC : SCE_O_EXCL);
        normal_ready_written=true;
        return;
    }
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
    if constexpr(normal_initial_respawn_profile) {
        const auto calibration=calibrate_platform_clock();
        const auto record=calibration_record(normal_outputs,calibration);
        log("%.*s",int(record.size),record.text.data());
        log("normal diagnostics run_id=%s revision=%s instrumented=1 metric_frame_index=sample_frame loop_interval_covers=prior_sample_frame render_includes=swap_and_capture log_duration=sum_successful_in_loop_calls steady_excludes=capture_summary_intercept intercept_signal=SCE_CTRL_INTERCEPTED_from_existing_sample detection_completeness_verified=0 startup_teardown_and_final_summary_log_excluded=1 suspend_validated=0 hardware_perf_proof=0",normal_outputs.run_id.c_str(),revision);
    }
#if !defined(CELESTE_ROOM_GUEST_REPLAY) && !defined(CELESTE_ROOM_GUEST_AUTOMATIC) && !defined(CELESTE_ROOM_DASH_PROBE)
    log("input profile=standard_analog center=128 range=0..255 fixture_assumption=true hardware_calibrated=false move=LeftStick/DPad aim=LeftStick/DPad");
#endif
#ifdef CELESTE_ROOM_GUEST_AUTOMATIC
    log("guest automatic fixture=%s fixture_sha256=%s input_source=scripted_guest_controls samples=%u exit_frame=%u physical_controller_verified=false host_input_injected=false",
        guest_automatic,guest_automatic_sha256,guest_automatic_samples,guest_automatic_exit_frame);
#endif
#ifdef CELESTE_ROOM_GUEST_REPLAY
    log("guest replay fixture=%s fixture_sha256=%s input_source=scripted_guest_controls max_frames=%u physical_controller_verified=false host_input_injected=false",
        guest_replay_id,guest_replay_sha256,guest_replay_frames);
#endif
#ifdef CELESTE_ROOM_DASH_PROBE
    log("guest dash probe fixture=%s fixture_sha256=%s input_source=scripted_guest_controls samples=%u exit_frame=%u physical_controller_verified=false host_input_injected=false capture_policy=dash_trails instrumented=1 uninstrumented_proof=0 diagnostic_sweep=1 acceptance_disabled=1",
        guest_dash_probe,guest_dash_probe_sha256,guest_dash_probe_samples,guest_dash_probe_exit_frame);
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
#ifdef CELESTE_ROOM_GUEST_AUTOMATIC
    std::string automatic_completion;
#endif
    try {
    if (visual_assets) load_textures(*visual_assets);
    if (decal_assets) load_decal_textures(*decal_assets);
    if (player_assets) load_player_textures(*player_assets);
#if !defined(CELESTE_ROOM_GUEST_REPLAY) && !defined(CELESTE_ROOM_GUEST_AUTOMATIC) && !defined(CELESTE_ROOM_DASH_PROBE)
    const int mode = sceCtrlSetSamplingMode(SCE_CTRL_MODE_ANALOG);
    if (mode < 0) throw std::runtime_error("Controller initialization failed: " + std::to_string(mode));
#endif
    auto session=make_session(room.world,player_assets ? &player_assets->bank : nullptr);
    if constexpr(automatic_session_profile)
        log("lifecycle source_first_room automatic_corpse_wipe_reload_respawn14 seed=0 original_startup_rng_parity=false Triangle=manual_diagnostic_restart");
    else log("lifecycle legacy_manual_diagnostic Triangle=fresh_Normal_player automatic_reload=false");
    const auto render=[&](const char* path,unsigned frame) {
        const auto* outputs=normal_initial_respawn_profile ? &normal_outputs : nullptr;
        const auto projection=session.projection();
        if(player_assets) {
            PlayerRender animated{*player_assets,*session.presentation(),projection,session.lifecycle(),&session.trails()};
            return draw(room,session.player(),path,frame,session.resets(),visual_assets,&animated,decal_assets,outputs);
        }
        return draw(room,session.player(),path,frame,session.resets(),visual_assets,nullptr,decal_assets,outputs);
    };
    Controller controller;
#ifdef CELESTE_ROOM_GUEST_REPLAY
    GuestReplay replay;
    bool replay_jumped=false,replay_frozen=false,replay_thawed=false,replay_launched=false,replay_dash_done=false,replay_died=false,replay_reset=false;
#elif defined(CELESTE_ROOM_GUEST_AUTOMATIC)
    GuestAutomaticReplay replay;
    GuestAutomaticObserver automatic_observer(session);
#elif defined(CELESTE_ROOM_DASH_PROBE)
    GuestDashProbeObserver dash_observer(session,revision,guest_dash_probe_sha256);
#else
    unsigned previous_lx = 0, previous_ly = 0;
#endif
    unsigned previous = 0, frame = 0;
    const std::string frame_path = normal_initial_respawn_profile ? normal_outputs.frame : std::string("ux0:data/celeste_native_room-")+revision+
#ifdef CELESTE_ROOM_DASH_PROBE
        "-dash-probe.ppm";
#else
        ".ppm";
#endif
    bool capture_resolved = false, capture_observed = room_capture_policy==CapturePolicy::spawn;
    InitialRespawnCapture initial_capture;
#ifdef CELESTE_ROOM_GUEST_AUTOMATIC
    bool fresh_exported=false;
#endif
    bool wall_near = false, wall_forced = false;
    bool climb_near = false, climbed = false, climb_held = false, climb_released = false, climb_landed = false;
#ifndef CELESTE_ROOM_DASH_PROBE
    float climb_entry_y = 0.0f;
#endif
    const auto capture_path = [&]() -> const char* {
        capture_resolved = true;
        if (guest_capture_exists(frame_path.c_str())) {
            if constexpr(normal_initial_respawn_profile) throw std::runtime_error("Normal run capture destination occupied after claim: "+frame_path);
            log("capture_skipped_existing path=%s prior_capture_preserved=ppm_and_receipt current_run_capture=false",frame_path.c_str());
            return nullptr;
        }
        return frame_path.c_str();
    };
    const auto exported = render(capture_observed ? capture_path() : nullptr,0);
    if (!exported.empty()) log("%s",exported.c_str());
#ifdef CELESTE_ROOM_GUEST_AUTOMATIC
    fresh_exported=!exported.empty();
#endif
    log("capture policy=%s",capture_policy_name(room_capture_policy));
    state("frame ready",frame,session);
    signal("ready",frame);
    const auto start_time = sceKernelGetProcessTimeWide();
    while (!session.exiting()) {
#if defined(CELESTE_ROOM_GUEST_REPLAY) || defined(CELESTE_ROOM_GUEST_AUTOMATIC) || defined(CELESTE_ROOM_DASH_PROBE)
#ifdef CELESTE_ROOM_DASH_PROBE
        auto controls=dash_probe_controls(frame);
        controls.start=frame==guest_dash_probe_frames-1;
#else
        const auto controls = replay.next(frame);
#endif
        const auto bit=[](bool held,unsigned flag) { return held?flag:0u; };
        const unsigned buttons = bit(controls.left,SCE_CTRL_LEFT)|bit(controls.right,SCE_CTRL_RIGHT)|
            bit(controls.up,SCE_CTRL_UP)|bit(controls.down,SCE_CTRL_DOWN)|bit(controls.cross,SCE_CTRL_CROSS)|
            bit(controls.triangle,SCE_CTRL_TRIANGLE)|bit(controls.start,SCE_CTRL_START)|
            bit(controls.square,SCE_CTRL_SQUARE)|bit(controls.l,SCE_CTRL_LTRIGGER);
        const auto sample = controller.sample(controls);
#else
        unsigned lx = 0, ly = 0;
        SceCtrlData pad{};
        const int result = sceCtrlPeekBufferPositive(0,&pad,1);
        if (result != 1) throw std::runtime_error("Controller sample failed: " + std::to_string(result));
        const auto buttons = pad.buttons;
        const auto down = [&](unsigned flag) { return (buttons & flag) != 0; };
        const Controls held_buttons{down(SCE_CTRL_LEFT),down(SCE_CTRL_RIGHT),down(SCE_CTRL_UP),down(SCE_CTRL_DOWN),
                                    down(SCE_CTRL_CROSS),down(SCE_CTRL_TRIANGLE),down(SCE_CTRL_START),down(SCE_CTRL_SQUARE),down(SCE_CTRL_LTRIGGER)};
        lx = pad.lx;
        ly = pad.ly;
        const auto sample = controller.sample_analog({held_buttons, {lx, ly, true}});
#endif
        if constexpr(normal_initial_respawn_profile) {
            frame_metrics.begin_frame(process_now_us(),{},(buttons&SCE_CTRL_INTERCEPTED)!=0);
            measuring_frame=true;
        }
        const bool changed = buttons != previous;
        if (changed) log("input frame=%u buttons=%08x x=%d y=%d cross_held=%d cross_pressed=%d reset=%d exit=%d square_held=%d square_pressed=%d grab=%d",frame,
                         unsigned(buttons),sample.player.x,sample.player.y,sample.player.jump.held,sample.player.jump.pressed,sample.reset,sample.exit,
                          sample.player.dash_button.held,sample.player.dash_button.pressed,sample.player.grab);
#if !defined(CELESTE_ROOM_GUEST_REPLAY) && !defined(CELESTE_ROOM_GUEST_AUTOMATIC) && !defined(CELESTE_ROOM_DASH_PROBE)
        const bool analog_changed = lx != previous_lx || ly != previous_ly;
        if (changed || analog_changed || frame % 120 == 0)
            log("input analog frame=%u buttons=%08x valid=1 lx=%u ly=%u move_x=%d move_y=%d aim_x=%d aim_y=%d",frame,
                unsigned(buttons),lx,ly,sample.player.x,sample.player.y,sample.player.aim_x,sample.player.aim_y);
        previous_lx = lx;
        previous_ly = ly;
#endif
        const bool dead = session.player().death().dead;
        const int old_state = session.player().state_machine().state();
        const bool frozen = session.player().clock().freeze_timer > 0.0f;
        const unsigned dash_events = session.player().state().dash_events;
        const unsigned jumps = session.jump_count();
        const unsigned reloads = session.lifecycle() ? session.lifecycle()->stats().reloads : 0;
        const auto step_begin=normal_initial_respawn_profile ? process_now_us() : 0;
        session.step(sample);
        const auto step_end=normal_initial_respawn_profile ? process_now_us() : 0;
#ifdef CELESTE_ROOM_GUEST_AUTOMATIC
        log("%s",automatic_observer.observe(frame,sample,session).c_str());
#endif
#ifdef CELESTE_ROOM_DASH_PROBE
        log("%s",dash_observer.observe(frame,controls,sample,session).c_str());
#endif
        if (session.exiting()) {
            if constexpr(normal_initial_respawn_profile) finish_metrics_frame(step_begin,step_end,false,0,0,true);
            break;
        }
        ++frame;
        const auto& player = session.player();
        const bool jumped = !sample.reset && session.jump_count() > jumps;
        const bool wall_jumped = jumped && player.jump_kind() == celeste::JumpKind::wall_jump;
#ifndef CELESTE_ROOM_DASH_PROBE
        const auto* presentation=session.presentation();
        const bool animated_climb_ready=!presentation ||
            ((presentation->pose().animation=="climbUp" || presentation->pose().animation=="climbup") &&
             presentation->pose().animation_frame>0 && player.state().speed.y<0 &&
             presentation->pose().hair_nodes[0].x>=0 && presentation->pose().hair_nodes[0].x<320 &&
              presentation->pose().hair_nodes[0].y>=0 && presentation->pose().hair_nodes[0].y<180);
#endif
#ifndef CELESTE_ROOM_DASH_PROBE
        if (capture_after_climb && !climbed && player.state_machine().state() == 1) climb_entry_y = player.actor().body.position.y;
#endif
        const bool capture_event = !capture_resolved && (
#ifdef CELESTE_ROOM_DASH_PROBE
            session.trails().count()==3 && session.trails().render_order().size()==3);
#else
            (room_capture_policy==CapturePolicy::initial_respawn && initial_capture.request(session,frame,sample.reset)) ||
            (capture_after_wall_jump && wall_jumped) ||
            (capture_after_climb && player.state_machine().state() == 1 && !player.state().on_ground &&
               player.state().stamina < 109.0f && player.grab_held() && sample.player.y == -1 && player.actor().body.position.y < climb_entry_y && animated_climb_ready));
#endif
        if (capture_event) capture_observed = true;
        if constexpr(normal_initial_respawn_profile) if(capture_event) frame_metrics.mark_capture();
        const auto render_begin=normal_initial_respawn_profile ? process_now_us() : 0;
        const auto exported = render(capture_event ? capture_path() : nullptr,frame);
        const auto render_end=normal_initial_respawn_profile ? process_now_us() : 0;
        if constexpr(normal_initial_respawn_profile) if(capture_event) {
            normal_outputs.confirm_export(exported,revision);
            normal_capture_closed=true;
        }
#ifdef CELESTE_ROOM_DASH_PROBE
        if(capture_event) dash_observer.confirm_export(exported,session);
#endif
        if(capture_event && room_capture_policy==CapturePolicy::initial_respawn) initial_capture.confirm_export(exported);
#ifdef CELESTE_ROOM_GUEST_AUTOMATIC
        fresh_exported=fresh_exported || !exported.empty();
#endif
        if (!exported.empty()) log("%s",exported.c_str());
        if (jumped) state("jump",frame,session);
        if(session.lifecycle() && session.lifecycle()->stats().reloads>reloads) {
            const auto& stats=session.lifecycle()->stats();
            log("automatic reload frame=%u reloads=%u state=%d session_deaths=%u room_deaths=%u save_deaths=%u source_profile=first_room Triangle=false",
                frame,stats.reloads,player.state_machine().state(),stats.session_deaths,stats.room_deaths,stats.save_deaths);
        }
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
        } else if (capture_after_climb && capture_event) {
            state("climb drained",frame,session);
            signal("climb_drained",frame);
        } else if (capture_after_climb && capture_observed && climbed && !climb_held && new_state == 1 && sample.player.y == 0 && player.state().speed.y == 0) {
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
        if constexpr(normal_initial_respawn_profile) finish_metrics_frame(step_begin,step_end,true,render_begin,render_end,false);
    }
#ifdef CELESTE_ROOM_GUEST_REPLAY
    if(frame!=guest_replay_frames-1 || !capture_observed || !climbed || !climb_held || !climb_released || !climb_landed ||
       !replay_jumped || !replay_frozen || !replay_thawed || !replay_launched || !replay_dash_done || !replay_died || !replay_reset)
        throw std::runtime_error("Guest replay ended without all observed native checkpoints");
#endif
    if(room_capture_policy==CapturePolicy::initial_respawn) initial_capture.require_complete();
#ifdef CELESTE_ROOM_DASH_PROBE
    dash_completion.record_run(dash_observer,session);
#endif
#ifdef CELESTE_ROOM_GUEST_AUTOMATIC
    if(!fresh_exported) throw std::runtime_error("Guest automatic ended without a fresh closed native frame export");
    automatic_completion=automatic_observer.completion_record(session);
    if(!automatic_observer.complete(session)) {
        log("%s",automatic_completion.c_str());
        throw std::runtime_error("Guest automatic ended without observed initial respawn, two automatic cycles and three actual Jumps");
    }
#endif
    const auto elapsed = sceKernelGetProcessTimeWide()-start_time;
    state("clean exit",frame,session);
#ifdef CELESTE_ROOM_GUEST_REPLAY
    log("guest replay completed samples=%u",guest_replay_frames);
#endif
    if constexpr(normal_initial_respawn_profile) metrics_summary("Start_final");
    else log("diagnostic measurement frames=%u elapsed_us=%llu observed_fps=%.3f not_a_hardware_estimate",frame,
         static_cast<unsigned long long>(elapsed),elapsed ? frame*1e6/double(elapsed) : 0);
    } catch (const std::exception& error) {
        try { finish_graphics(); }
        catch (const std::exception& cleanup) { throw std::runtime_error(std::string(error.what())+"; graphics teardown also failed: "+cleanup.what()); }
        throw;
    }
    finish_graphics();
#ifdef CELESTE_ROOM_DASH_PROBE
    dash_completion.graphics_finished();
    log("%s",dash_completion.log_record().c_str());
    dash_completion.logged();
#endif
#ifdef CELESTE_ROOM_GUEST_AUTOMATIC
    log("%s",automatic_completion.c_str());
#endif
}
}
int main() {
    if constexpr(normal_initial_respawn_profile) {
        try {
            normal_outputs=claim_normal_outputs(revision,sceKernelGetProcessTimeWide());
            log_path=normal_outputs.log.c_str();
        } catch(const std::exception& error) {
            std::fprintf(stderr,"Normal output startup failed: %s\n",error.what());
            sceKernelExitProcess(1);return 1;
        }
    }
    if constexpr(!normal_initial_respawn_profile) {
    FILE* initial = std::fopen(log_path,"w");
    if (!initial) { sceKernelExitProcess(1); return 1; }
    if (std::fclose(initial) || !std::freopen(log_path,"w",stderr) || std::setvbuf(stderr,nullptr,_IONBF,0)) {
        sceKernelExitProcess(1); return 1;
    }
    } else if(!std::freopen(log_path,"a",stderr) || std::setvbuf(stderr,nullptr,_IONBF,0)) {
        sceKernelExitProcess(1);return 1;
    }
    int status = 0;
    try { run(); }
    catch (const std::exception& error) {
        status = 1;
        if (std::fprintf(stderr,"FATAL: %s\n",error.what()) < 0 || std::fflush(stderr)) status = 2;
        try {
            const auto failure_path =
#ifdef CELESTE_ROOM_DASH_PROBE
                dash_probe_receipt_path("failure",revision);
#else
                normal_initial_respawn_profile ? normal_outputs.failure : std::string("ux0:data/celeste_native_room-failure-")+celeste::diagnostic::revision+".txt";
#endif
            if (celeste::diagnostic::guest_file_exists(failure_path.c_str())) {
                if (std::fprintf(stderr,"Failure receipt preserved: %s; original: %s\n",failure_path.c_str(),error.what()) < 0 || std::fflush(stderr))
                    status = 2;
            } else {
                celeste::diagnostic::write_guest_file(failure_path.c_str(),
#ifdef CELESTE_ROOM_DASH_PROBE
                    dash_failure_record(error.what()),
#else
                    normal_initial_respawn_profile ? normal_outputs.record("FATAL",normal_capture_closed ? "fresh_closed" : "failed")+"cause="+error.what()+"\n" :
                    std::string("FATAL revision=")+celeste::diagnostic::revision+" cause="+error.what()+"\n",
#endif
                    SCE_O_EXCL);
            }
            signal("failed",0);
        } catch (const std::exception& diagnostic_error) {
            status = 2;
            std::fprintf(stderr,"Failure receipt also failed: %s; original: %s\n",diagnostic_error.what(),error.what());
        }
    }
    if (std::fclose(stderr)) status = 2;
#if defined(CELESTE_ROOM_GUEST_REPLAY) || defined(CELESTE_ROOM_GUEST_AUTOMATIC) || defined(CELESTE_ROOM_DASH_PROBE)
    if(status==0) {
        try {
            const auto complete_path=
#ifdef CELESTE_ROOM_DASH_PROBE
                dash_probe_receipt_path("complete",revision);
            dash_completion.log_closed();
            celeste::diagnostic::write_guest_file(complete_path.c_str(),dash_completion.closed_receipt(),SCE_O_EXCL);
#else
                std::string("ux0:data/celeste_native_room-complete-")+celeste::diagnostic::revision+".txt";
#ifdef CELESTE_ROOM_GUEST_AUTOMATIC
            const auto* fixture=celeste::diagnostic::guest_automatic_id;
#else
            const auto* fixture=celeste::diagnostic::guest_replay_id;
#endif
            celeste::diagnostic::write_guest_file(complete_path.c_str(),std::string("complete revision=")+celeste::diagnostic::revision+
                " input_source=scripted_guest_controls fixture="+fixture+" status=0\n",SCE_O_EXCL);
#endif
        } catch(const std::exception& error) {
            status=2;
#ifdef CELESTE_ROOM_DASH_PROBE
            std::string failure_cause=error.what();
            try {
                const auto failure_path=dash_probe_receipt_path("failure",revision);
                if(!guest_file_exists(failure_path.c_str())) write_guest_file(failure_path.c_str(),dash_failure_record(error.what()),SCE_O_EXCL);
            } catch(const std::exception& receipt_error) {
                failure_cause+="; failure receipt also failed: "+std::string(receipt_error.what());
            }
#endif
            if(FILE* failure_log=std::fopen(log_path,"a")) {
                std::fprintf(failure_log,"FATAL: completion receipt failed: %s\n",
#ifdef CELESTE_ROOM_DASH_PROBE
                    failure_cause.c_str());
#else
                    error.what());
#endif
                std::fclose(failure_log);
            }
        }
    }
#endif
    sceKernelExitProcess(status);
    return status;
}
