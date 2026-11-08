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
std::array<GLuint,8> textures{};
unsigned uploaded = 0;
std::array<GLuint,10> player_textures{};
unsigned player_uploaded=0;
constexpr unsigned six_texture_rgba_bytes = 5*64*128*4+16*16*4;
constexpr unsigned spike_rgba_bytes = 2*16*16*4;
unsigned room_rgba_bytes(const VisualAssets& visuals) {
    return six_texture_rgba_bytes + (visuals.spike_art() ? spike_rgba_bytes : 0);
}
void check(const char* stage) {
    const auto error = glGetError();
    if (error != GL_NO_ERROR) throw std::runtime_error(std::string(stage) + ": GL error " + std::to_string(error));
}
void upload_texture(GLuint texture,int width,int height,std::string_view pixels) {
    glBindTexture(GL_TEXTURE_2D,texture);
    glTexParameteri(GL_TEXTURE_2D,GL_TEXTURE_MIN_FILTER,GL_NEAREST);
    glTexParameteri(GL_TEXTURE_2D,GL_TEXTURE_MAG_FILTER,GL_NEAREST);
    glTexParameteri(GL_TEXTURE_2D,GL_TEXTURE_WRAP_S,GL_CLAMP_TO_EDGE);
    glTexParameteri(GL_TEXTURE_2D,GL_TEXTURE_WRAP_T,GL_CLAMP_TO_EDGE);
    glTexImage2D(GL_TEXTURE_2D,0,GL_RGBA,width,height,0,GL_RGBA,GL_UNSIGNED_BYTE,pixels.data());
    check("bounded RGBA texture upload");
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
void textured_vertices(const TexturedQuad& q) {
    glTexCoord2f(q.u0,q.v0); glVertex2f(q.x,q.y);
    glTexCoord2f(q.u1,q.v0); glVertex2f(q.x+q.width,q.y);
    glTexCoord2f(q.u1,q.v1); glVertex2f(q.x+q.width,q.y+q.height);
    glTexCoord2f(q.u0,q.v1); glVertex2f(q.x,q.y+q.height);
}
void textured_quad(const TexturedQuad& q, unsigned texture) {
    glBindTexture(GL_TEXTURE_2D,textures.at(texture));
    glBegin(GL_QUADS);
    textured_vertices(q);
    glEnd();
}
void tile_layer(const VisualAssets& visuals, bool background) {
    int active_texture = -1;
    for (const auto& command : visuals.commands) {
        if (command.background != background) continue;
        if (command.texture != active_texture) {
            if (active_texture != -1) glEnd();
            active_texture = command.texture;
            glBindTexture(GL_TEXTURE_2D,textures.at(active_texture));
            glBegin(GL_QUADS);
        }
        textured_vertices(tile_quad(visuals.textures[command.texture],command));
    }
    if (active_texture != -1) glEnd();
}
void player_layer(PlayerRender& animated) {
    if(player_uploaded!=animated.assets.bank.pages) throw std::logic_error("Incomplete player texture ownership");
    const auto draws=animated.presentation.draw(animated.projection);
    for(const auto& d:draws) {
        const auto& f=animated.assets.bank.frames[d.frame];
        glBindTexture(GL_TEXTURE_2D,player_textures.at(f.page));
        glColor4ub(d.color.r,d.color.g,d.color.b,d.color.a);
        glBegin(GL_QUADS);
        for(const auto& v:player_vertices(f,d)) {glTexCoord2f(v.u,v.v);glVertex2f(v.x,v.y);}
        glEnd();
    }
}
void hazard_markers(const Room& room) {
    glDisable(GL_TEXTURE_2D);
    glColor3f(1,0.2f,0.2f);
    for (const auto& spike : room.spikes) body(spike.body());
}
#ifdef CELESTE_ROOM_SPIKE_ART
void spike_layer(const VisualAssets& visuals) {
    if (!visuals.spike_art()) throw std::logic_error("Source spike art requires the eight-texture protocol");
    glEnable(GL_TEXTURE_2D);
    glColor4f(1,1,1,1);
    for (const auto& piece : visuals.spike_pieces) {
        const auto texture = piece.up ? VisualAssets::up_texture : VisualAssets::left_texture;
        glBindTexture(GL_TEXTURE_2D,textures.at(texture));
        glBegin(GL_QUADS);
        textured_vertices(spike_quad(visuals.textures[texture],piece));
        glEnd();
    }
}
#endif
std::string export_back_buffer(const char* path, const Player& player, unsigned frame, unsigned resets, const VisualAssets* visuals, PlayerRender* animated) {
    glReadBuffer(GL_BACK);
    glFinish();
    check("frame export GPU finish");
    std::vector<std::uint8_t> rgba(960*544*4);
    glReadPixels(0,0,960,544,GL_RGBA,GL_UNSIGNED_BYTE,rgba.data());
    check("frame export glReadPixels GL_BACK RGBA CPU");
    const auto ppm = encode_frame_ppm(960,544,rgba);
    write_guest_file(path,ppm,SCE_O_EXCL);
    const auto position = player.actor().body.position;
    unsigned bg_count = 0, fg_count = 0;
    if (visuals) for (const auto& command : visuals->commands) command.background ? ++bg_count : ++fg_count;
    std::string presentation;
    if(animated) {
        const auto& pose=animated->presentation.pose();
        const auto& texture=animated->assets.bank.frames[pose.frame];
        presentation=" animation="+pose.animation+" body_frame="+std::to_string(pose.animation_frame)+" source_texture="+texture.name+
            " player_page="+std::to_string(texture.page)+" scale="+std::to_string(pose.scale.x)+","+std::to_string(pose.scale.y)+
            " rotation="+std::to_string(pose.rotation)+" hair_simulated=1 hair_count=4 hair_outline=black_16_draws hair_nodes=";
        for(auto node:pose.hair_nodes) presentation+=std::to_string(node.x)+","+std::to_string(node.y)+";";
        const auto c=pose.hair_color;
        presentation+=" hair_color="+std::to_string(c.r)+","+std::to_string(c.g)+","+std::to_string(c.b)+","+std::to_string(c.a)+
            " diagnostic_rng_seed="+std::to_string(animated->presentation.diagnostic_seed())+" rng_calls="+std::to_string(animated->presentation.random_calls())+
            " original_startup_rng_parity=false source_phase=level_after_update_then_render";
    }
    const bool spike_art = visuals && visuals->spike_art();
    const std::string receipt = std::string("frame_saved path=")+path+" width=960 height=544 revision="+revision+
        " stage=after_draw_glFinish_GL_BACK_RGBA_CPU_before_swap frame="+std::to_string(frame)+" x="+std::to_string(position.x)+" y="+std::to_string(position.y)+
        " vx="+std::to_string(player.state().speed.x)+" vy="+std::to_string(player.state().speed.y)+
        " ground="+std::to_string(player.state().on_ground)+" dead="+std::to_string(player.death().dead)+
        " resets="+std::to_string(resets)+" state="+std::to_string(player.state_machine().state())+
        " stamina="+std::to_string(player.state().stamina)+" grab="+std::to_string(player.grab_held())+
        " jump_kind="+jump_kind_name(player.jump_kind())+" capture="+(frame == 0 ? "spawn" : player.state_machine().state() == 1 ? "climb" : "wall_jump")+
        " render_style="+(animated ? "animated_player_partial" : visuals ? "textured_partial" : "debug")+" camera=0,0 bg_draws="+std::to_string(bg_count)+" fg_draws="+std::to_string(fg_count)+
        " body_draws="+(visuals ? "1" : "0")+" diagnostic_spike_markers="+(spike_art ? "0" : "5")+
        (spike_art ? " physical_spikes=5 draw_pieces="+std::to_string(visuals->spike_pieces.size())+" diagnostic_red_markers=0 spike_art=source_static_19" : "")+
        " submitted_rgba_bytes="+std::to_string(visuals ? room_rgba_bytes(*visuals)+player_uploaded*128*64*4 : 0)+
        " alpha="+(visuals ? "premultiplied_ONE_ONE_MINUS_SRC_ALPHA" : "disabled")+" body_pose="+(animated ? "source_animated_with_simulated_hair" : visuals ? "idle00_static_no_animation" : "hitboxes")+
        presentation+" format=P6_RGB_top_down\n";
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
void load_textures(const VisualAssets& visuals) {
    if (uploaded) throw std::logic_error("Room textures already uploaded");
    if (visuals.texture_count < 6 || visuals.texture_count > static_cast<int>(textures.size()))
        throw std::logic_error("Invalid bounded room texture ownership count");
    glGenTextures(visuals.texture_count,textures.data());
    check("texture ownership allocation");
    for (int i=0; i<visuals.texture_count; ++i) {
        const auto pixels = read_asset(("app0:assets/native-room/texture"+std::to_string(i)+".rgba").c_str(),64*128*4);
        const auto& info = visuals.textures[i];
        validate_texture_bytes(pixels,info);
        upload_texture(textures[i],info.width,info.height,pixels);
        ++uploaded;
    }
    glBindTexture(GL_TEXTURE_2D,0);
    check("texture upload completion");
}
void load_player_textures(const PlayerAssets& assets) {
    if(player_uploaded || !assets.bank.pages || assets.bank.pages>player_textures.size()) throw std::logic_error("Invalid player texture ownership");
    glGenTextures(assets.bank.pages,player_textures.data());
    check("player texture ownership allocation");
    for(unsigned i=0;i<assets.bank.pages;++i) {
        const auto pixels=read_asset(("app0:assets/native-room/player"+std::to_string(i)+".rgba").c_str(),128*64*4);
        if(pixels.size()!=128*64*4 || checksum(pixels)!=assets.checksums.at(i)) throw std::invalid_argument("Player page integrity mismatch");
        upload_texture(player_textures[i],128,64,pixels);
        ++player_uploaded;
    }
    glBindTexture(GL_TEXTURE_2D,0);
}
std::string draw(const Room& room, const Player& player, const char* export_path, unsigned frame, unsigned resets, const VisualAssets* visuals, PlayerRender* animated) {
    if(animated && !visuals) throw std::invalid_argument("Animated player requires source-baked room layers");
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
    if (visuals) {
        if (uploaded != static_cast<unsigned>(visuals->texture_count)) throw std::logic_error("Textured room requested without complete texture ownership");
        glEnable(GL_BLEND);
        glBlendFunc(GL_ONE,GL_ONE_MINUS_SRC_ALPHA);
        glEnable(GL_TEXTURE_2D);
        glTexEnvi(GL_TEXTURE_ENV,GL_TEXTURE_ENV_MODE,GL_MODULATE);
        glColor4f(1,1,1,1);
        tile_layer(*visuals,true);
        if(animated) player_layer(*animated);
        else textured_quad(body_quad(visuals->textures[VisualAssets::body_texture],player.actor().body.position,static_cast<int>(player.state().facing)),VisualAssets::body_texture);
#ifdef CELESTE_ROOM_SPIKE_ART
        if (visuals->spike_art()) spike_layer(*visuals);
        else hazard_markers(room);
#else
        hazard_markers(room);
#endif
        glEnable(GL_TEXTURE_2D);
        glColor4f(1,1,1,1);
        tile_layer(*visuals,false);
        glDisable(GL_TEXTURE_2D);
        glDisable(GL_BLEND);
    } else {
    glColor3f(0.3f,0.4f,0.5f);
    for (int y=0; y<room.grid.rows(); ++y) {
        const float py = room.solids.position.y + y*8;
        if (py >= 180 || py+8 <= 0) continue;
        for (int x=0; x<room.grid.columns(); ++x) {
            const float px = room.solids.position.x + x*8;
            if (px < 320 && px+8 > 0 && room.grid.at(x,y)) rectangle(px,py,8,8);
        }
    }
    hazard_markers(room);
    glColor3f(player.death().dead ? 1 : 0.2f, player.death().dead ? 0.1f : 0.9f, 0.4f);
    body(player.actor().body);
    glColor3f(1,0.85f,0.2f);
    const auto hurtbox = player.hurtbox();
    const auto position = player.actor().body.position;
    rectangle(position.x+hurtbox.offset.x,position.y+hurtbox.offset.y,hurtbox.width,hurtbox.height);
    }
    check("room draw");
    const auto exported = export_path ? export_back_buffer(export_path,player,frame,resets,visuals,animated) : std::string{};
    vglSwapBuffers(GL_FALSE);
    check("buffer swap");
    return exported;
}
void finish_graphics() {
    glFinish();
    const auto finish_error = glGetError();
    glDeleteTextures(uploaded,textures.data());
    glDeleteTextures(player_uploaded,player_textures.data());
    textures.fill(0);
    uploaded = 0;
    player_textures.fill(0);
    player_uploaded=0;
    const auto delete_error = glGetError();
    if (finish_error != GL_NO_ERROR || delete_error != GL_NO_ERROR)
        throw std::runtime_error("Graphics finish/texture teardown GL errors "+std::to_string(finish_error)+","+std::to_string(delete_error));
}
}
