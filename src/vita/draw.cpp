#include "draw.hpp"
#include "diagnostic.hpp"
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
void draw(const Room& room, const Player& player) {
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
    vglSwapBuffers(GL_FALSE);
    check("buffer swap");
}
void finish_graphics() {
    glFinish();
    check("graphics finish");
}
}
