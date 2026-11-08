#include "asset_pins.hpp"
#include "assets.hpp"
#include "diagnostic.hpp"
#include "draw.hpp"
#include <psp2/ctrl.h>
#include <psp2/io/fcntl.h>
#include <psp2/kernel/processmgr.h>
#include <cstdarg>
#include <cstdio>
#include <stdexcept>

namespace {
using namespace celeste::diagnostic;
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
    const auto fd = sceIoOpen("ux0:data/celeste_native_room.ready", SCE_O_WRONLY|SCE_O_CREAT|SCE_O_TRUNC, 0666);
    if (fd < 0) throw std::runtime_error("Readiness open failed: " + std::to_string(fd));
    const auto written = sceIoWrite(fd,text,length);
    const auto closed = sceIoClose(fd);
    if (written != length || closed < 0) throw std::runtime_error("Readiness write/close failed");
}
void state(const char* event, unsigned frame, const Session& session) {
    const auto& player = session.player();
    const auto position = player.actor().body.position;
    log("%s frame=%u x=%.0f y=%.0f vx=%.3f vy=%.3f ground=%d dead=%d resets=%u",event,frame,
        position.x,position.y,player.state().speed.x,player.state().speed.y,
        player.state().on_ground,player.death().dead,session.resets());
}
void run() {
    log("Celeste native room DIAGNOSTIC boot revision=%s fixed_step=1/60 manual_reset=Triangle", revision);
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
    draw(room,session.player());
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
                                              down(SCE_CTRL_CROSS),down(SCE_CTRL_TRIANGLE),down(SCE_CTRL_START)});
        const bool changed = buttons != previous;
        if (changed) log("input frame=%u buttons=%08x x=%d y=%d cross_held=%d cross_pressed=%d reset=%d exit=%d",frame,
                         unsigned(buttons),sample.player.x,sample.player.y,sample.player.jump.held,sample.player.jump.pressed,sample.reset,sample.exit);
        const bool dead = session.player().death().dead;
        session.step(sample);
        if (session.exiting()) break;
        ++frame;
        draw(room,session.player());
        const bool died = !dead && session.player().death().dead;
        if (died || sample.reset || changed || frame%120 == 0) state(died ? "death" : sample.reset ? "manual reset" : "frame",frame,session);
        if (died || sample.reset || changed) signal(died ? "dead" : sample.reset ? "reset" : "sampled",frame);
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
    }
    if (std::fclose(stderr)) status = 2;
    sceKernelExitProcess(status);
    return status;
}
