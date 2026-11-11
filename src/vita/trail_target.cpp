#include "trail_target.hpp"
#include <vitaGL.h>
#include <stdexcept>
#include <string>
#include <algorithm>
#include <cmath>
#include <exception>

namespace celeste::diagnostic {
namespace {
void check(const char* operation) {
    const auto error=glGetError();
    if(error!=GL_NO_ERROR) throw std::runtime_error(std::string(operation)+": GL error "+std::to_string(error));
}
void enabled(GLenum cap,bool value) { if(value) glEnable(cap);else glDisable(cap); }
struct State {
    GLint write=0,read=0,viewport[4]{},scissor[4]{},mode=0,texture=0,src_rgb=0,dst_rgb=0,src_alpha=0,dst_alpha=0,equation_rgb=0,equation_alpha=0;
    GLfloat color[4]{};
    GLfloat clear_color[4]{};
    GLint pack_alignment=-1;
    bool diagnostic=false;
    GLfloat projection[16]{},modelview[16]{};
    bool blend, textured, scissored, depth, cull;
    explicit State(bool extended=false) : diagnostic(extended),blend(glIsEnabled(GL_BLEND)),textured(glIsEnabled(GL_TEXTURE_2D)),scissored(glIsEnabled(GL_SCISSOR_TEST)),
              depth(glIsEnabled(GL_DEPTH_TEST)),cull(glIsEnabled(GL_CULL_FACE)) {
        glGetIntegerv(GL_FRAMEBUFFER_BINDING,&write);glGetIntegerv(GL_READ_FRAMEBUFFER_BINDING,&read);
        glGetIntegerv(GL_VIEWPORT,viewport);glGetIntegerv(GL_SCISSOR_BOX,scissor);
        glGetIntegerv(GL_MATRIX_MODE,&mode);glGetIntegerv(GL_TEXTURE_BINDING_2D,&texture);
        glGetIntegerv(GL_BLEND_SRC_RGB,&src_rgb);glGetIntegerv(GL_BLEND_DST_RGB,&dst_rgb);
        glGetIntegerv(GL_BLEND_SRC_ALPHA,&src_alpha);glGetIntegerv(GL_BLEND_DST_ALPHA,&dst_alpha);
        glGetIntegerv(GL_BLEND_EQUATION_RGB,&equation_rgb);glGetIntegerv(GL_BLEND_EQUATION_ALPHA,&equation_alpha);
        glGetFloatv(GL_CURRENT_COLOR,color);
        glGetFloatv(GL_PROJECTION_MATRIX,projection);glGetFloatv(GL_MODELVIEW_MATRIX,modelview);
        if(diagnostic) {
            glGetFloatv(GL_COLOR_CLEAR_VALUE,clear_color);glGetIntegerv(GL_PACK_ALIGNMENT,&pack_alignment);
        }
        check(diagnostic ? "instrumented trail clear color/pack state query" : "trail state capture");
    }
    void restore() {
        glBindFramebuffer(GL_DRAW_FRAMEBUFFER,GLuint(write));glBindFramebuffer(GL_READ_FRAMEBUFFER,GLuint(read));
        glViewport(viewport[0],viewport[1],viewport[2],viewport[3]);glScissor(scissor[0],scissor[1],scissor[2],scissor[3]);
        glMatrixMode(GL_PROJECTION);glLoadMatrixf(projection);glMatrixMode(GL_MODELVIEW);glLoadMatrixf(modelview);glMatrixMode(GLenum(mode));
        glBindTexture(GL_TEXTURE_2D,GLuint(texture));glColor4f(color[0],color[1],color[2],color[3]);
        if(diagnostic) glClearColor(clear_color[0],clear_color[1],clear_color[2],clear_color[3]);
        glBlendFuncSeparate(GLenum(src_rgb),GLenum(dst_rgb),GLenum(src_alpha),GLenum(dst_alpha));
        glBlendEquationSeparate(GLenum(equation_rgb),GLenum(equation_alpha));
        enabled(GL_BLEND,blend);enabled(GL_TEXTURE_2D,textured);enabled(GL_SCISSOR_TEST,scissored);enabled(GL_DEPTH_TEST,depth);enabled(GL_CULL_FACE,cull);
    }
    void verify() const {
        const auto integer=[](GLenum name) {GLint value=0;glGetIntegerv(name,&value);return value;};
        GLint actual_viewport[4]{},actual_scissor[4]{};GLfloat actual_color[4]{};
        GLfloat actual_projection[16]{},actual_modelview[16]{};
        glGetIntegerv(GL_VIEWPORT,actual_viewport);glGetIntegerv(GL_SCISSOR_BOX,actual_scissor);glGetFloatv(GL_CURRENT_COLOR,actual_color);
        glGetFloatv(GL_PROJECTION_MATRIX,actual_projection);glGetFloatv(GL_MODELVIEW_MATRIX,actual_modelview);
        if(diagnostic) {
            GLfloat actual_clear[4]{};glGetFloatv(GL_COLOR_CLEAR_VALUE,actual_clear);
            if(!std::equal(clear_color,clear_color+4,actual_clear) || integer(GL_PACK_ALIGNMENT)!=pack_alignment)
                throw std::runtime_error("Instrumented trail clear color/pack state restoration failed");
        }
        if(integer(GL_FRAMEBUFFER_BINDING)!=write || integer(GL_READ_FRAMEBUFFER_BINDING)!=read || integer(GL_MATRIX_MODE)!=mode ||
           integer(GL_TEXTURE_BINDING_2D)!=texture || integer(GL_BLEND_SRC_RGB)!=src_rgb || integer(GL_BLEND_DST_RGB)!=dst_rgb ||
           integer(GL_BLEND_SRC_ALPHA)!=src_alpha || integer(GL_BLEND_DST_ALPHA)!=dst_alpha || integer(GL_BLEND_EQUATION_RGB)!=equation_rgb ||
           integer(GL_BLEND_EQUATION_ALPHA)!=equation_alpha || !std::equal(viewport,viewport+4,actual_viewport) ||
           !std::equal(scissor,scissor+4,actual_scissor) || !std::equal(color,color+4,actual_color) ||
           !std::equal(projection,projection+16,actual_projection) || !std::equal(modelview,modelview+16,actual_modelview) || bool(glIsEnabled(GL_BLEND))!=blend ||
           bool(glIsEnabled(GL_TEXTURE_2D))!=textured || bool(glIsEnabled(GL_SCISSOR_TEST))!=scissored || bool(glIsEnabled(GL_DEPTH_TEST))!=depth ||
           bool(glIsEnabled(GL_CULL_FACE))!=cull) throw std::runtime_error("Trail pass failed native GL state restoration");
    }
};
template<class Action> void with_preserved_state(bool diagnostic,const char* context,const Action& action) {
    State state(diagnostic);
    const auto restore=[&] {state.restore();check(context);state.verify();check(context);};
    try {action(state);}
    catch(...) {
        const auto primary=std::current_exception();const auto pending=glGetError();std::string cause,cleanup_failure;
        try {std::rethrow_exception(primary);}
        catch(const std::exception& error) {cause=error.what();}
        catch(...) {cause="Non-standard trail action exception";}
        if(pending!=GL_NO_ERROR) cause+="; GL error before state restoration "+std::to_string(pending);
        try {restore();}
        catch(const std::exception& cleanup) {cleanup_failure=cleanup.what();}
        if(!cleanup_failure.empty()) std::throw_with_nested(std::runtime_error(cause+"; cleanup also failed: "+cleanup_failure));
        if(pending!=GL_NO_ERROR) std::throw_with_nested(std::runtime_error(cause));
        std::rethrow_exception(primary);
    }
    restore();
}
void rectangle(float x,float y,float width,float height) {
    glBegin(GL_QUADS);
    glVertex2f(x,y);glVertex2f(x+width,y);glVertex2f(x+width,y+height);glVertex2f(x,y+height);
    glEnd();
}
}

void TrailTarget::allocate() {
    if(texture_) return;
    glGenTextures(1,&texture_);
    glBindTexture(GL_TEXTURE_2D,texture_);
    glTexParameteri(GL_TEXTURE_2D,GL_TEXTURE_MIN_FILTER,GL_NEAREST);glTexParameteri(GL_TEXTURE_2D,GL_TEXTURE_MAG_FILTER,GL_NEAREST);
    glTexParameteri(GL_TEXTURE_2D,GL_TEXTURE_WRAP_S,GL_CLAMP_TO_EDGE);glTexParameteri(GL_TEXTURE_2D,GL_TEXTURE_WRAP_T,GL_CLAMP_TO_EDGE);
    glTexImage2D(GL_TEXTURE_2D,0,GL_RGBA,512,512,0,GL_RGBA,GL_UNSIGNED_BYTE,nullptr);
    glGenFramebuffers(1,&framebuffer_);
    glBindFramebuffer(GL_FRAMEBUFFER,framebuffer_);
    glFramebufferTexture2D(GL_FRAMEBUFFER,GL_COLOR_ATTACHMENT0,GL_TEXTURE_2D,texture_,0);
    if(glCheckFramebufferStatus(GL_FRAMEBUFFER)!=GL_FRAMEBUFFER_COMPLETE) throw std::runtime_error("Incomplete trail RGBA framebuffer");
    check("trail target allocation");
}

void TrailTarget::capture(PlayerTrails& trails,PlayerPresentation& presentation,const PlayerProjection& player,const PlayerTrails::Capture& draw) {
    bool pending=false;
    for(const auto& slot:trails.slots()) pending=pending || (slot.occupied && !slot.drawn);
    if(!pending) return;
    with_preserved_state(false,"trail capture state restoration",[&](const State&) {
        trails.before_render(presentation,player,[&](unsigned slot,const std::vector<PlayerDraw>& draws) {
            allocate();
            glBindFramebuffer(GL_FRAMEBUFFER,framebuffer_);glViewport(0,0,512,512);
            glMatrixMode(GL_PROJECTION);glLoadIdentity();glOrtho(0,512,512,0,-1,1);
            glMatrixMode(GL_MODELVIEW);glLoadIdentity();
            glDisable(GL_DEPTH_TEST);glDisable(GL_CULL_FACE);
            glEnable(GL_SCISSOR_TEST);glScissor(slot%8*64,512-int(slot/8+1)*64,64,64);
            glEnable(GL_BLEND);glBlendEquation(GL_FUNC_ADD);
            glDisable(GL_TEXTURE_2D);glBlendFunc(GL_ONE,GL_ZERO);glColor4ub(0,0,0,0);
            rectangle(float(slot%8*64),float(slot/8*64),64,64);
            glEnable(GL_TEXTURE_2D);glBlendFunc(GL_ONE,GL_ONE_MINUS_SRC_ALPHA);
            draw(slot,draws);
            glDisable(GL_TEXTURE_2D);glBlendFunc(GL_DST_ALPHA,GL_ZERO);glColor4ub(255,255,255,255);
            rectangle(float(slot%8*64),float(slot/8*64),64,64);
            check("trail tile capture and alpha mask");
        });
    });
    check("trail capture state restoration");
}

void TrailTarget::render(const PlayerTrails& trails) const {
    if(!texture_) return;
    glEnable(GL_TEXTURE_2D);glEnable(GL_BLEND);glBlendEquation(GL_FUNC_ADD);glBlendFunc(GL_ONE,GL_ONE_MINUS_SRC_ALPHA);
    glBindTexture(GL_TEXTURE_2D,texture_);
    for(unsigned index:trails.render_order()) {
        const auto& slot=trails.slots()[index];
        const auto color=PlayerTrails::faded_color(slot);
        const float x=slot.position.x-32,y=slot.position.y-32,u=float(index%8)/8.f,v=1.f-float(index/8)/8.f;
        glColor4ub(color.r,color.g,color.b,color.a);
        glBegin(GL_QUADS);
        glTexCoord2f(u,v);glVertex2f(x,y);glTexCoord2f(u+0.125f,v);glVertex2f(x+64,y);
        glTexCoord2f(u+0.125f,v-0.125f);glVertex2f(x+64,y+64);glTexCoord2f(u,v-0.125f);glVertex2f(x,y+64);
        glEnd();
    }
    glColor4ub(255,255,255,255);
}

std::vector<std::uint8_t> TrailTarget::read_rgba() const {
    if(!framebuffer_) throw std::logic_error("Trail RGBA readback requires a captured tile");
    std::vector<std::uint8_t> pixels(512*512*4);
    with_preserved_state(false,"trail RGBA readback state restoration",[&](const State&) {
        glBindFramebuffer(GL_READ_FRAMEBUFFER,framebuffer_);glFinish();
        glReadPixels(0,0,512,512,GL_RGBA,GL_UNSIGNED_BYTE,pixels.data());
        check("trail FBO attachment RGBA readback");
    });
    check("trail RGBA readback state restoration");
    return pixels;
}

void TrailTarget::dispose() {
    if(framebuffer_) glDeleteFramebuffers(1,&framebuffer_);
    if(texture_) glDeleteTextures(1,&texture_);
    framebuffer_=texture_=0;
    check("trail framebuffer disposal");
}

std::string TrailTarget::prepare_probe(const PlayerTrails& trails,const std::function<void(const std::vector<std::uint8_t>&)>& diagnostic,
                                      const std::function<void()>& before_mask) {
    if(!diagnostic) throw std::invalid_argument("GPU probe requires a diagnostic readback sink");
    if(trails.slots()[63].occupied) throw std::logic_error("GPU probe requires unused diagnostic tile 63");
    const auto before=read_rgba();
    with_preserved_state(false,"trail probe state restoration",[&](const State&) {
        glBindFramebuffer(GL_FRAMEBUFFER,framebuffer_);glViewport(0,0,512,512);
        glMatrixMode(GL_PROJECTION);glLoadIdentity();glOrtho(0,512,512,0,-1,1);
        glMatrixMode(GL_MODELVIEW);glLoadIdentity();glDisable(GL_DEPTH_TEST);glDisable(GL_CULL_FACE);
        glEnable(GL_SCISSOR_TEST);glScissor(448,0,64,64);glDisable(GL_TEXTURE_2D);glEnable(GL_BLEND);glBlendEquation(GL_FUNC_ADD);
        glBlendFunc(GL_ONE,GL_ZERO);glColor4ub(0,0,0,0);rectangle(448,448,64,64);
        glBlendFunc(GL_ONE,GL_ONE_MINUS_SRC_ALPHA);glColor4ub(64,32,16,128);
        rectangle(452,452,16,16);rectangle(460,452,16,16);
        glColor4ub(51,120,0,255);rectangle(484,452,16,8);
        glColor4ub(16,16,16,64);rectangle(484,468,4,4);
        if(before_mask) before_mask();
        glBlendFunc(GL_DST_ALPHA,GL_ZERO);glColor4ub(255,255,255,255);rectangle(448,448,64,64);
        check("diagnostic trail alpha swatches");
    });
    const auto after=read_rgba();
    diagnostic(after);
    for(unsigned slot=0;slot<63;++slot) if(trails.slots()[slot].occupied && trails.slots()[slot].drawn) {
        for(unsigned y=0;y<64;++y) {
            const unsigned offset=((7-slot/8)*64+y)*512*4+slot%8*64*4;
            if(!std::equal(before.begin()+offset,before.begin()+offset+64*4,after.begin()+offset))
                throw std::runtime_error("GPU probe changed a captured ghost tile");
        }
    }
    const auto swatch=[&](const TrailProbeSwatch& point) {
        const auto x=point.x,top=point.top,expected=point.expected;
        const auto offset=((511-top)*512+x)*4;
        for(unsigned channel=0;channel<4;++channel)
            if(std::abs(int(after[offset+channel])-int(expected))>1)
                throw std::runtime_error("GPU trail alpha/orientation swatch failed at "+std::to_string(x)+","+std::to_string(top));
        return std::to_string(after[offset+3]);
    };
    return "trail_probe=diagnostic_rgba_fbo swatch_single="+swatch(trail_probe_swatches[0])+" swatch_inner_union="+swatch(trail_probe_swatches[1])+
        " swatch_opaque="+swatch(trail_probe_swatches[2])+" swatch_orientation="+swatch(trail_probe_swatches[3])+
        " other_captured_tiles_preserved=1 single_ghost_xy=200,16 between_ghost_xy=240,16;248,16 tint_rgba=51,137,191,191 FBO_RGBA=512x512 raw_rows=GL_bottom_up";
}

void TrailTarget::render_probe() const {
    with_preserved_state(false,"trail probe render state restoration",[&](const State&) {
        glEnable(GL_TEXTURE_2D);glEnable(GL_BLEND);glDisable(GL_SCISSOR_TEST);glBlendEquation(GL_FUNC_ADD);glBlendFunc(GL_ONE,GL_ONE_MINUS_SRC_ALPHA);
        glBindTexture(GL_TEXTURE_2D,texture_);glColor4ub(51,137,191,191);
        for(float x:{200.f,240.f,248.f}) {
            glBegin(GL_QUADS);
            glTexCoord2f(0.875f,0.125f);glVertex2f(x,16);glTexCoord2f(1,0.125f);glVertex2f(x+64,16);
            glTexCoord2f(1,0);glVertex2f(x+64,80);glTexCoord2f(0.875f,0);glVertex2f(x,80);glEnd();
        }
        check("diagnostic single and between-ghost swatches");
    });
}

#ifdef CELESTE_ROOM_DASH_PROBE
std::vector<std::uint8_t> TrailTarget::read_probe_pixels(TrailProbeRead phase) const {
    if(!framebuffer_) throw std::logic_error("Instrumented readback requires the existing trail attachment");
    const auto channels=trail_probe_channels(phase);
    std::vector<std::uint8_t> pixels(512*512*channels,trail_probe_sentinel(phase));
    with_preserved_state(true,"instrumented readback state restoration",[&](const State&) {
        glBindFramebuffer(GL_READ_FRAMEBUFFER,framebuffer_);glFinish();
        glReadPixels(0,0,512,512,channels==3 ? GL_RGB : GL_RGBA,GL_UNSIGNED_BYTE,pixels.data());
        check(trail_probe_read_name(phase));
    });
    return pixels;
}

[[noreturn]] void TrailTarget::diagnostic_sweep(const PlayerTrails& trails,const TrailProbeReadback& observe,const std::function<void(const std::string&)>& report) {
    if(!observe || !report) throw std::invalid_argument("Instrumented sweep requires readback and report sinks");
    if(trails.slots()[63].occupied) throw std::logic_error("GPU probe requires unused diagnostic tile 63");
    std::string errors,original_failure;
    const auto emit=[&](const std::string& record) {
        try {report(record);return true;}
        catch(const std::exception& error) {errors+="; diagnostic report failed: "+std::string(error.what());return false;}
    };
    const auto attempt=[&](const char* phase,const auto& action) {
        try {action();}
        catch(const std::exception& error) {
            const auto context=std::string(phase)+": "+error.what();errors+="; "+context;
            emit("diagnostic_error phase="+std::string(phase)+" cause="+error.what());
        }
    };
    const auto read=[&](TrailProbeRead phase,std::vector<std::uint8_t>& pixels) {
        attempt(trail_probe_read_name(phase),[&] {
            pixels=read_probe_pixels(phase);
            observe(phase,pixels);
        });
    };
    emit("sweep_begin additional_reads=5 marker_read_order=RGBA_then_RGB optional_post_RGB_read=0 pack_state_touched=0");
    try {
        prepare_probe(trails,[&](const auto& pixels) {
            attempt("original_post_mask",[&]{observe(TrailProbeRead::original_post_mask,pixels);});
        },[&] {
            std::vector<std::uint8_t> pixels;read(TrailProbeRead::pre_mask,pixels);
        });
    } catch(const std::exception& error) {original_failure=error.what();}
    const bool recorded=emit("original_result="+std::string(original_failure.empty() ? "matched" : "failed")+
        (original_failure.empty() ? "" : " cause="+original_failure));
    if(recorded) {
        std::vector<std::uint8_t> first,second,marker_rgba,marker_rgb;
        read(TrailProbeRead::paired_a,first);read(TrailProbeRead::paired_b,second);
        if(!first.empty() && !second.empty()) {
            const auto pair=trail_probe_pair_counts(first,second);
            emit("sentinel_pair classification="+std::string(pair.classification)+" bytes="+std::to_string(first.size())+
                " retained_pairs="+std::to_string(pair.retained_pairs)+" differing_bytes="+std::to_string(pair.differing));
        } else emit("sentinel_pair classification=unavailable");
        attempt("marker_sweep",[&] {
            with_preserved_state(true,"instrumented marker state restoration",[&](const State& state) {
                attempt("marker_draw",[&] {
                    emit("pack_alignment="+std::to_string(state.pack_alignment)+" pack_state_touched=0");
                    glBindFramebuffer(GL_FRAMEBUFFER,framebuffer_);glViewport(0,0,512,512);
                    glMatrixMode(GL_PROJECTION);glLoadIdentity();glOrtho(0,512,512,0,-1,1);
                    glMatrixMode(GL_MODELVIEW);glLoadIdentity();glDisable(GL_DEPTH_TEST);glDisable(GL_CULL_FACE);
                    glDisable(GL_TEXTURE_2D);glDisable(GL_BLEND);
                    for(unsigned index=0;index<3;++index) {
                        const auto& marker=trail_probe_markers[index];const auto& c=marker.rgba;
                        emit("marker_definition name="+std::string(marker.name)+" rect="+std::to_string(marker.x)+","+std::to_string(marker.top)+","+
                            std::to_string(marker.width)+","+std::to_string(marker.height)+" scissored="+std::to_string(marker.scissored)+
                            " expected_rgba="+std::to_string(c[0])+","+std::to_string(c[1])+","+std::to_string(c[2])+","+std::to_string(c[3]));
                        enabled(GL_SCISSOR_TEST,marker.scissored);
                        if(marker.scissored) glScissor(marker.x,512-marker.top-marker.height,marker.width,marker.height);
                        if(index==0) {glClearColor(c[0]/255.f,c[1]/255.f,c[2]/255.f,c[3]/255.f);glClear(GL_COLOR_BUFFER_BIT);}
                        else {glColor4ub(c[0],c[1],c[2],c[3]);rectangle(float(marker.x),float(marker.top),float(marker.width),float(marker.height));}
                    }
                    check("instrumented marker drawing");
                });
                read(TrailProbeRead::marker_rgba,marker_rgba);
                read(TrailProbeRead::marker_rgb,marker_rgb);
                unsigned checked=0,changed=0,unobservable=0;
                if(!first.empty() && !second.empty() && !marker_rgba.empty()) {
                    for(unsigned slot=0;slot<63;++slot) if(trails.slots()[slot].occupied && trails.slots()[slot].drawn)
                        for(unsigned y=0;y<64;++y) for(unsigned x=0;x<64*4;++x) {
                            const unsigned offset=((7-slot/8)*64+y)*512*4+slot%8*64*4+x;
                            if(first[offset]==second[offset] && marker_rgba[offset]!=trail_probe_sentinel(TrailProbeRead::marker_rgba)) {
                                ++checked;changed+=second[offset]!=marker_rgba[offset];
                            } else ++unobservable;
                        }
                    emit("captured_tiles reference=paired_b checked_bytes="+std::to_string(checked)+" changed_bytes="+std::to_string(changed)+
                        " unobservable_bytes="+std::to_string(unobservable));
                    if(changed) errors+="; instrumented markers changed observable captured ghost bytes";
                } else emit("captured_tiles comparison=unavailable");
            });
        });
    }
    throw std::runtime_error((original_failure.empty() ? std::string("instrumented diagnostic completed; uninstrumented GPU acceptance disabled") :
        original_failure+"; instrumented diagnostic; uninstrumented GPU acceptance disabled")+errors);
}
#endif

}
