#include "draw.hpp"
#include "diagnostic.hpp"
#include "frame.hpp"
#include "guest_io.hpp"
#include "asset_pins.hpp"
#include <vitaGL.h>
#include <stdexcept>
#include <string>

namespace celeste::diagnostic {
namespace {
void check(const char* stage) {
    const auto error = glGetError();
    if (error != GL_NO_ERROR) throw std::runtime_error(std::string(stage) + ": GL error " + std::to_string(error));
}
void rectangle(float x, float y, float width, float height) {
    glBegin(GL_QUADS);
    glVertex2f(x,y); glVertex2f(x+width,y); glVertex2f(x+width,y+height); glVertex2f(x,y+height);
    glEnd();
}
void body(const Body& shape) {
    const auto& box = shape.collider.value();
    rectangle(shape.position.x+box.offset.x, shape.position.y+box.offset.y, box.width, box.height);
}
std::string export_back_buffer(const char* path, const Player& player) {
    glReadBuffer(GL_BACK);
    glFinish();
    check("frame export GPU finish");
    std::vector<std::uint8_t> rgb(960*544*3);
    glReadPixels(0,0,960,544,GL_RGB,GL_UNSIGNED_BYTE,rgb.data());
    check("frame export glReadPixels GL_BACK RGB transfer");
    const auto ppm = encode_frame_ppm(960,544,rgb);
    write_guest_file(path,ppm,SCE_O_EXCL);
    const auto position = player.actor().body.position;
    const std::string receipt = std::string("frame_saved path=")+path+" width=960 height=544 revision="+revision+
        " stage=after_draw_glFinish_GL_BACK_RGB_transfer_before_swap frame=0 x="+std::to_string(position.x)+" y="+std::to_string(position.y)+
        " vx="+std::to_string(player.state().speed.x)+" vy="+std::to_string(player.state().speed.y)+
        " ground="+std::to_string(player.state().on_ground)+" dead="+std::to_string(player.death().dead)+
        " resets=0 format=P6_RGB_top_down\n";
    write_guest_file((std::string(path)+".txt").c_str(),receipt,SCE_O_EXCL);
    return receipt;
}
}
void initialize_graphics() {
    const auto fallback = vglInitExtended(1024*1024, 960, 544, 64*1024*1024, SCE_GXM_MULTISAMPLE_NONE);
    if (fallback || !glGetString(GL_VERSION) || !vglMemTotal(VGL_MEM_RAM) || !vglMemTotal(VGL_MEM_VRAM))
        throw std::runtime_error("vitaGL initialization missing requested resolution/context/memory pools");
    GLint viewport[4]{};
    glGetIntegerv(GL_VIEWPORT, viewport);
    if (viewport[2] != 960 || viewport[3] != 544) throw std::runtime_error("Unexpected initialized viewport");
    vglWaitVblankStart(GL_TRUE);
    glDisable(GL_TEXTURE_2D);
    glDisable(GL_DEPTH_TEST);
    glDisable(GL_BLEND);
    check("graphics initialization");
}
std::string draw(const Room& room, const Player& player, const char* export_path) {
    glViewport(0,0,960,544);
    glClearColor(0,0,0,1);
    glClear(GL_COLOR_BUFFER_BIT);
    const auto viewport = letterbox(960,544);
    glViewport(viewport.x,viewport.y,viewport.width,viewport.height);
    glMatrixMode(GL_PROJECTION);
    glLoadIdentity();
    glOrtho(0,320,180,0,-1,1);
    glMatrixMode(GL_MODELVIEW);
    glLoadIdentity();
    glColor3f(0.035f,0.045f,0.07f);
    rectangle(0,0,320,180);
    glColor3f(0.3f,0.4f,0.5f);
    for (int y=0; y<room.grid.rows(); ++y) {
        const float py = room.solids.position.y + y*8;
        if (py >= 180 || py+8 <= 0) continue;
        for (int x=0; x<room.grid.columns(); ++x) {
            const float px = room.solids.position.x + x*8;
            if (px < 320 && px+8 > 0 && room.grid.at(x,y)) rectangle(px,py,8,8);
        }
    }
    glColor3f(1,0.2f,0.2f);
    for (const auto& spike : room.spikes) body(spike.body());
    glColor3f(player.death().dead ? 1 : 0.2f, player.death().dead ? 0.1f : 0.9f, 0.4f);
    body(player.actor().body);
    glColor3f(1,0.85f,0.2f);
    const auto hurtbox = player.hurtbox();
    const auto position = player.actor().body.position;
    rectangle(position.x+hurtbox.offset.x,position.y+hurtbox.offset.y,hurtbox.width,hurtbox.height);
    check("room draw");
    const auto exported = export_path ? export_back_buffer(export_path,player) : std::string{};
    vglSwapBuffers(GL_FALSE);
    check("buffer swap");
    return exported;
}
void finish_graphics() {
    glFinish();
    check("graphics finish");
}
}
