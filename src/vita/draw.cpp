#include "draw.hpp"
#include "diagnostic.hpp"
#include "frame.hpp"
#include "guest_io.hpp"
#include "asset_pins.hpp"
#include "capture_policy.hpp"
#include "normal_outputs.hpp"
#include "trail_target.hpp"
#ifdef CELESTE_ROOM_DASH_PROBE
#include "guest_dash_probe_diagnostic.hpp"
#endif
#include <vitaGL.h>
#include <cmath>
#include <cstring>
#include <stdexcept>
#include <string>

namespace celeste::diagnostic {
namespace {
std::array<GLuint,8> textures{};
unsigned uploaded = 0;
std::array<GLuint,10> player_textures{};
unsigned player_uploaded=0;
TrailTarget trail_target;
std::string trail_probe_receipt;
#ifdef CELESTE_ROOM_DECALS
GLuint decal_texture=0;
bool decal_uploaded=false;
constexpr unsigned decal_rgba_bytes=64*128*4;
#endif
constexpr unsigned six_texture_rgba_bytes = 5*64*128*4+16*16*4;
constexpr unsigned spike_rgba_bytes = 2*16*16*4;
unsigned room_rgba_bytes(const VisualAssets& visuals, const DecalAssets* decals) {
    unsigned total = six_texture_rgba_bytes + (visuals.spike_art() ? spike_rgba_bytes : 0);
#ifdef CELESTE_ROOM_DECALS
    if (decals) total += decal_rgba_bytes;
#else
    (void)decals;
#endif
    return total;
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
void player_draws(PlayerRender& animated,const std::vector<PlayerDraw>& draws) {
    for(const auto& d:draws) {
        const auto& f=animated.assets.bank.frames[d.frame];
        glBindTexture(GL_TEXTURE_2D,player_textures.at(f.page));
        glColor4ub(d.color.r,d.color.g,d.color.b,d.color.a);
        glBegin(GL_QUADS);
        for(const auto& v:player_vertices(f,d)) {glTexCoord2f(v.u,v.v);glVertex2f(v.x,v.y);}
        glEnd();
    }
}
void player_layer(PlayerRender& animated) {
    if(player_uploaded!=animated.assets.bank.pages) throw std::logic_error("Incomplete player texture ownership");
    player_draws(animated,animated.lifecycle ? animated.lifecycle->draw() : animated.presentation.draw(animated.projection));
}
bool foreground_player(const PlayerRender* animated) {
    return animated && animated->lifecycle && animated->lifecycle->foreground_owner();
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
#ifdef CELESTE_ROOM_DECALS
void decal_layer(const DecalAssets& decals, bool background) {
    if (!decal_uploaded) throw std::logic_error("Static decal layer requested without the bounded decal page");
    glBindTexture(GL_TEXTURE_2D,decal_texture);
    glColor4f(1,1,1,1);
    glBegin(GL_QUADS);
    for (const auto& instance : decals.instances) {
        if (instance.background != background) continue;
        for (const auto& vertex : decal_vertices(decals.textures.at(instance.texture),instance)) {
            glTexCoord2f(vertex.u,vertex.v);
            glVertex2f(vertex.x,vertex.y);
        }
    }
    glEnd();
}
#endif
std::string export_back_buffer(const char* path, const Player& player, unsigned frame, unsigned resets, const VisualAssets* visuals, PlayerRender* animated, const DecalAssets* decals,const NormalOutputPaths* normal_outputs) {
    if(normal_outputs) normal_outputs->validate_capture(path,revision);
    const auto* lifecycle=animated ? animated->lifecycle : nullptr;
    if(room_capture_policy==CapturePolicy::initial_respawn && (!lifecycle || !initial_respawn_ready(*lifecycle,frame,resets,false)))
        throw std::runtime_error("Initial respawn export requires the live initial Normal Player without a wipe");
    glReadBuffer(GL_BACK);
    glFinish();
    check("frame export GPU finish");
    std::vector<std::uint8_t> rgba(960*544*4);
    glReadPixels(0,0,960,544,GL_RGBA,GL_UNSIGNED_BYTE,rgba.data());
    check("frame export glReadPixels GL_BACK RGBA CPU");
    const auto ppm = encode_frame_ppm(960,544,rgba);
    write_guest_file(path,ppm,SCE_O_EXCL);
#ifdef CELESTE_ROOM_DASH_PROBE
    const auto trail_rgba=trail_target.read_rgba();
    write_guest_file((std::string(path)+".trail.rgba").c_str(),
        std::string_view(reinterpret_cast<const char*>(trail_rgba.data()),trail_rgba.size()),SCE_O_EXCL);
    const auto probe_identity=std::string(" probe_fixture=")+guest_dash_probe+" probe_fixture_sha256="+guest_dash_probe_sha256+" native_probe_checks=1";
#else
    const std::string probe_identity;
#endif
    const auto position = lifecycle ? lifecycle->projection().position : player.actor().body.position;
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
        const auto* trails=animated->trails ? animated->trails : lifecycle ? &lifecycle->trails() : nullptr;
        if(trails) {
            presentation+=" trail_depth=1 trail_target_logical_RGBA_bytes="+std::to_string(trail_target.texture() ? 512*512*4 : 0)+" trail_snapshots=";
            for(auto slot:trails->render_order()) {
                const auto& snapshot=trails->slots()[slot];const auto tint=PlayerTrails::faded_color(snapshot);
                presentation+=std::to_string(slot)+","+std::to_string(snapshot.percent)+","+std::to_string(snapshot.position.x)+","+std::to_string(snapshot.position.y)+","+
                    std::to_string(tint.r)+","+std::to_string(tint.g)+","+std::to_string(tint.b)+","+std::to_string(tint.a)+";";
            }
        }
    }
    const bool spike_art = visuals && visuals->spike_art();
    const bool decal_art = decals != nullptr;
    const std::string lifecycle_phase=lifecycle ? lifecycle->phase() : "legacy_manual";
    const bool body_visible=!lifecycle || lifecycle_phase=="live" || lifecycle_phase=="corpse";
    std::string lifecycle_receipt;
    if(lifecycle) {
        const auto& stats=lifecycle->stats();
        lifecycle_receipt=" lifecycle=source_first_room phase="+lifecycle_phase+" automatic_reloads="+std::to_string(stats.reloads)+
            " loads="+std::to_string(stats.loads)+" respawn_callbacks="+std::to_string(stats.respawn_callbacks)+
            " wipe_callbacks="+std::to_string(stats.wipe_callbacks)+" pending_corpses="+std::to_string(lifecycle->pending_corpse())+
            " committed_corpses="+std::to_string(lifecycle->committed_corpse())+" wipe_active="+std::to_string(lifecycle->wipe()!=nullptr)+" legacy_manual_replay=false";
    }
    const std::string receipt = std::string("frame_saved path=")+path+" width=960 height=544 revision="+revision+
        " stage=after_draw_glFinish_GL_BACK_RGBA_CPU_before_swap frame="+std::to_string(frame)+" x="+std::to_string(position.x)+" y="+std::to_string(position.y)+
        " vx="+std::to_string(player.state().speed.x)+" vy="+std::to_string(player.state().speed.y)+
        " ground="+std::to_string(player.state().on_ground)+" dead="+std::to_string(player.death().dead)+
        " resets="+std::to_string(resets)+" state="+std::to_string(player.state_machine().state())+
        " stamina="+std::to_string(player.state().stamina)+" grab="+std::to_string(player.grab_held())+
        " jump_kind="+jump_kind_name(player.jump_kind())+" capture="+capture_policy_name(room_capture_policy)+
        " render_style="+(animated ? "animated_player_partial" : visuals ? "textured_partial" : "debug")+" camera=0,0 bg_draws="+std::to_string(bg_count)+" fg_draws="+std::to_string(fg_count)+
        " body_draws="+(visuals && body_visible ? "1" : "0")+" diagnostic_spike_markers="+(spike_art ? "0" : "5")+
        (spike_art ? " physical_spikes=5 draw_pieces="+std::to_string(visuals->spike_pieces.size())+" diagnostic_red_markers=0 spike_art=source_static_19" : "")+
        (decal_art ? " static_decals=22 bg_decals=20 fg_decals=2 animated_omitted=7 decal_art=source_static_decal_cut decal_page_bytes=32768" : "")+
        " submitted_rgba_bytes="+std::to_string(visuals ? room_rgba_bytes(*visuals,decals)+player_uploaded*128*64*4 : 0)+
        " alpha="+(visuals ? "premultiplied_ONE_ONE_MINUS_SRC_ALPHA" : "disabled")+" body_pose="+(animated ? "source_animated_with_simulated_hair" : visuals ? "idle00_static_no_animation" : "hitboxes")+
        presentation+lifecycle_receipt+" "+trail_probe_receipt+probe_identity+
        (normal_outputs ? " "+normal_outputs->capture_identity() : "")+" format=P6_RGB_top_down\n";
    write_guest_file((std::string(path)+".txt").c_str(),receipt,SCE_O_EXCL);
    return receipt;
}
}
void submit_ready_frame(const command_preflight::ReadyFrame& frame,
                        const std::vector<command_submission::UploadedPage>& pages,
                        const command_submission::View& view) {
    command_submission::submit(frame,pages,view,{
        [](const command_submission::Projection& projection) {
            check("ReadyFrame caller GL state");
            const auto* version=glGetString(GL_VERSION);
            check("ReadyFrame context query");
            if(!version) throw std::runtime_error("ReadyFrame requires a current vitaGL context");
            const auto& viewport=projection.viewport;
            glViewport(viewport.x,viewport.y,viewport.width,viewport.height);
            glMatrixMode(GL_PROJECTION);
            glLoadIdentity();
            glOrtho(projection.left,projection.right,projection.bottom,projection.top,-1,1);
            glMatrixMode(GL_MODELVIEW);
            glLoadIdentity();
            glDisable(GL_CULL_FACE);
            glDisable(GL_DEPTH_TEST);
            glEnable(GL_BLEND);
            glBlendEquation(GL_FUNC_ADD);
            glBlendFunc(GL_ONE,GL_ONE_MINUS_SRC_ALPHA);
            glActiveTexture(GL_TEXTURE1);
            glDisable(GL_TEXTURE_1D);
            glDisable(GL_TEXTURE_2D);
            glActiveTexture(GL_TEXTURE0);
            glDisable(GL_TEXTURE_1D);
            glBindSampler(0,0);
            glMatrixMode(GL_TEXTURE);
            glLoadIdentity();
            glMatrixMode(GL_MODELVIEW);
            check("ReadyFrame texture unit state");
            glEnable(GL_TEXTURE_2D);
            glTexEnvi(GL_TEXTURE_ENV,GL_TEXTURE_ENV_MODE,GL_MODULATE);
            check("ReadyFrame projection and draw state");
        },
        [](unsigned texture,const command_preflight::ReadyCommand& command) {
            glBindTexture(GL_TEXTURE_2D,texture);
            glTexParameteri(GL_TEXTURE_2D,GL_TEXTURE_MIN_FILTER,GL_NEAREST);
            glTexParameteri(GL_TEXTURE_2D,GL_TEXTURE_MAG_FILTER,GL_NEAREST);
            glTexParameteri(GL_TEXTURE_2D,GL_TEXTURE_WRAP_S,GL_CLAMP_TO_EDGE);
            glTexParameteri(GL_TEXTURE_2D,GL_TEXTURE_WRAP_T,GL_CLAMP_TO_EDGE);
            const auto& color=command.command.color;
            glColor4ub(color.r,color.g,color.b,color.a);
            check("ReadyFrame texture and color state");
            glBegin(GL_TRIANGLE_STRIP);
            for(const auto& words:command.geometry.vertices) {
                float vertex[5];
                static_assert(sizeof(vertex)==sizeof(words));
                std::memcpy(vertex,words.data(),sizeof(vertex));
                glTexCoord2f(vertex[3],vertex[4]);
                glVertex3f(vertex[0],vertex[1],vertex[2]);
            }
            glEnd();
            check("ReadyFrame quad");
        },
        [] {check("ReadyFrame submission completion");}
    });
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
void load_decal_textures(const DecalAssets& decals) {
#ifdef CELESTE_ROOM_DECALS
    if (decal_uploaded || decals.texture_count != 15 || decals.page_checksum == 0)
        throw std::logic_error("Invalid static decal texture ownership");
    const auto pixels = read_asset("app0:assets/native-room/decal0.rgba",64*128*4);
    if (pixels.size() != decal_rgba_bytes || checksum(pixels) != decals.page_checksum)
        throw std::invalid_argument("Static decal page integrity mismatch");
    glGenTextures(1,&decal_texture);
    check("decal texture ownership allocation");
    upload_texture(decal_texture,DecalAssets::page_width,DecalAssets::page_height,pixels);
    decal_uploaded=true;
    glBindTexture(GL_TEXTURE_2D,0);
#else
    (void)decals;
    throw std::logic_error("Static decals require the CELESTE_ROOM_DECALS build intent");
#endif
}
std::string draw(const Room& room, const Player& player, const char* export_path, unsigned frame, unsigned resets, const VisualAssets* visuals, PlayerRender* animated, const DecalAssets* decals,const NormalOutputPaths* normal_outputs) {
    if(normal_outputs && !normal_initial_respawn_profile) throw std::invalid_argument("Per-run outputs require the normal initial-respawn profile");
    if(export_path && normal_initial_respawn_profile && !normal_outputs) throw std::invalid_argument("Normal export requires claimed per-run output binding");
    if(animated && !visuals) throw std::invalid_argument("Animated player requires source-baked room layers");
    auto* trails=animated ? (animated->trails ? animated->trails : animated->lifecycle ? &animated->lifecycle->trails() : nullptr) : nullptr;
    if(trails) trail_target.capture(*trails,animated->presentation,animated->projection,
        [&](unsigned,const std::vector<PlayerDraw>& draws) { player_draws(*animated,draws); });
#ifdef CELESTE_ROOM_DASH_PROBE
    if(export_path) trail_target.diagnostic_sweep(*trails,[&](auto phase,const auto& pixels) {
        write_dash_probe_sweep_read(phase,pixels,revision,frame,stderr);
    },[&](const auto& event) {write_dash_probe_sweep_event(event,revision,frame,stderr);});
#endif
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
    if(animated && animated->lifecycle) {
        const auto camera=animated->lifecycle->camera(),shake=animated->lifecycle->shake();
        glTranslatef(-std::floor(camera.x+shake.x),-std::floor(camera.y+shake.y),0);
    }
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
#ifdef CELESTE_ROOM_DECALS
        if (decals) decal_layer(*decals,true);
#endif
        if(trails) trail_target.render(*trails);
        if(animated && !foreground_player(animated)) player_layer(*animated);
        else if(!animated) textured_quad(body_quad(visuals->textures[VisualAssets::body_texture],player.actor().body.position,static_cast<int>(player.state().facing)),VisualAssets::body_texture);
#ifdef CELESTE_ROOM_SPIKE_ART
        if (visuals->spike_art()) spike_layer(*visuals);
        else hazard_markers(room);
#else
        hazard_markers(room);
#endif
        glEnable(GL_TEXTURE_2D);
        glColor4f(1,1,1,1);
        tile_layer(*visuals,false);
#ifdef CELESTE_ROOM_DECALS
        if (decals) decal_layer(*decals,false);
#endif
        if(foreground_player(animated)) player_layer(*animated);
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
#ifdef CELESTE_ROOM_DASH_PROBE
    if(export_path) trail_target.render_probe();
#endif
    if(animated && animated->lifecycle && animated->lifecycle->wipe()) {
        glLoadIdentity();
        glDisable(GL_TEXTURE_2D);
        glDisable(GL_BLEND);
        glBegin(GL_TRIANGLES);
        for(const auto& vertex:animated->lifecycle->wipe()->vertices()) {
            glColor4ub(vertex.color.r,vertex.color.g,vertex.color.b,vertex.color.a);
            glVertex2f(vertex.position.x/6.f,vertex.position.y/6.f);
        }
        glEnd();
    }
    check("room draw");
    const auto exported = export_path ? export_back_buffer(export_path,player,frame,resets,visuals,animated,decals,normal_outputs) : std::string{};
    vglSwapBuffers(GL_FALSE);
    check("buffer swap");
    return exported;
}
void finish_graphics() {
    glFinish();
    const auto finish_error = glGetError();
    trail_target.dispose();
    glDeleteTextures(uploaded,textures.data());
    glDeleteTextures(player_uploaded,player_textures.data());
#ifdef CELESTE_ROOM_DECALS
    if (decal_uploaded) glDeleteTextures(1,&decal_texture);
#endif
    textures.fill(0);
    uploaded = 0;
    player_textures.fill(0);
    player_uploaded=0;
#ifdef CELESTE_ROOM_DECALS
    decal_texture=0;
    decal_uploaded=false;
#endif
    const auto delete_error = glGetError();
    if (finish_error != GL_NO_ERROR || delete_error != GL_NO_ERROR)
        throw std::runtime_error("Graphics finish/texture teardown GL errors "+std::to_string(finish_error)+","+std::to_string(delete_error));
}
}
