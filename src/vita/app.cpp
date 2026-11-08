#include "asset_pins.hpp"
#include "assets.hpp"
#include "diagnostic.hpp"
#include "draw.hpp"
#include "guest_io.hpp"
#include <psp2/ctrl.h>
#include <psp2/io/fcntl.h>
#include <psp2/kernel/processmgr.h>
#include <cstdarg>
#include <cstdio>
#include <stdexcept>

namespace {
using namespace celeste::diagnostic;
#ifdef CELESTE_ROOM_CAPTURE_AFTER_WALL_JUMP
constexpr bool capture_after_wall_jump = true;
#else
constexpr bool capture_after_wall_jump = false;
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
    log("%s frame=%u x=%.0f y=%.0f vx=%.3f vy=%.3f ground=%d dead=%d resets=%u state=%d freeze=%.9f dashes=%d move_x=%d force_x=%d force_timer=%.9f var_timer=%.9f jump_buffer=%.9f jump_kind=%s",event,frame,
         position.x,position.y,player.state().speed.x,player.state().speed.y,
         player.state().on_ground,player.death().dead,session.resets(),player.state_machine().state(),player.clock().freeze_timer,player.state().dashes,
         player.state().move_x,player.state().force_move_x,player.state().force_move_x_timer,player.state().var_jump_timer,
         player.jump_button().buffer_counter(),jump_kind_name(player.jump_kind()));
}
void run() {
    log("Celeste native room DIAGNOSTIC boot revision=%s fixed_step=1/60 manual_reset=Triangle jump=Cross dash=Square aim=DPad exit=Start", revision);
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
    initialize_graphics();
    const int mode = sceCtrlSetSamplingMode(SCE_CTRL_MODE_DIGITAL);
    if (mode < 0) throw std::runtime_error("Controller initialization failed: " + std::to_string(mode));
    Session session(room.world);
    Controller controller;
    unsigned previous = 0, frame = 0;
    const std::string frame_path = std::string("ux0:data/celeste_native_room-")+revision+".ppm";
    bool captured = !capture_after_wall_jump, wall_near = false, wall_forced = false;
    const auto exported = draw(room,session.player(),captured ? frame_path.c_str() : nullptr);
    if (captured) log("%s",exported.c_str());
    log("capture policy=%s",capture_after_wall_jump ? "wall_jump" : "spawn");
    state("frame ready",frame,session);
    signal("ready",frame);
    const auto start_time = sceKernelGetProcessTimeWide();
    while (!session.exiting()) {
        SceCtrlData pad{};
        const int result = sceCtrlPeekBufferPositive(0,&pad,1);
        if (result != 1) throw std::runtime_error("Controller sample failed: " + std::to_string(result));
        const auto buttons = pad.buttons;
        const auto down = [&](unsigned flag) { return (buttons & flag) != 0; };
        const auto sample = controller.sample({down(SCE_CTRL_LEFT),down(SCE_CTRL_RIGHT),down(SCE_CTRL_UP),down(SCE_CTRL_DOWN),
                                              down(SCE_CTRL_CROSS),down(SCE_CTRL_TRIANGLE),down(SCE_CTRL_START),down(SCE_CTRL_SQUARE)});
        const bool changed = buttons != previous;
        if (changed) log("input frame=%u buttons=%08x x=%d y=%d cross_held=%d cross_pressed=%d reset=%d exit=%d square_held=%d square_pressed=%d",frame,
                         unsigned(buttons),sample.player.x,sample.player.y,sample.player.jump.held,sample.player.jump.pressed,sample.reset,sample.exit,
                         sample.player.dash_button.held,sample.player.dash_button.pressed);
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
        const bool capture = capture_after_wall_jump && !captured && wall_jumped;
        const auto saved = draw(room,player,capture ? frame_path.c_str() : nullptr,frame,session.resets());
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
        if (died || sample.reset || changed || frame%120 == 0) state(died ? "death" : sample.reset ? "manual reset" : "frame",frame,session);
        if (capture_after_wall_jump && !wall_near && !player.state().on_ground && player.actor().body.position.x <= 14 &&
            sample.player.x == -1 && sample.player.jump.held && player.jump_kind() == celeste::JumpKind::jump) {
            wall_near = true;
            signal("wall_near",frame);
        } else if (capture_after_wall_jump && !wall_forced && !wall_jumped && player.jump_kind() == celeste::JumpKind::wall_jump &&
                   player.state().force_move_x_timer > 0 && player.state().move_x == 1 && player.state().speed.x > 0) {
            wall_forced = true;
            state("wall forced",frame,session);
            signal("wall_forced",frame);
        } else if (died || sample.reset || changed) signal(died ? "dead" : sample.reset ? "reset" : "sampled",frame);
        else if (old_state == 2 && new_state == 0) signal("dash_done",frame);
        previous = buttons;
    }
    finish_graphics();
    const auto elapsed = sceKernelGetProcessTimeWide()-start_time;
    state("clean exit",frame,session);
    log("diagnostic measurement frames=%u elapsed_us=%llu observed_fps=%.3f not_a_hardware_estimate",frame,
        static_cast<unsigned long long>(elapsed),elapsed ? frame*1e6/double(elapsed) : 0);
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
    sceKernelExitProcess(status);
    return status;
}
