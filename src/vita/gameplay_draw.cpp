#include "gameplay_draw.hpp"
#include "asset_pins.hpp"
#include "capture_policy.hpp"
#include "draw.hpp"
#include "frame.hpp"
#include "guest_io.hpp"
#include "normal_outputs.hpp"
#include <vitaGL.h>
#include <stdexcept>
#include <string>

namespace celeste::diagnostic {
void dispose_gameplay_pages(gameplay_bridge::PageOwner& owner) {
    owner.dispose([](unsigned texture) {
        glDeleteTextures(1,&texture);
        require_graphics_ok("gameplay owned page cleanup");
    });
}
void upload_gameplay_pages(gameplay_bridge::PageOwner& owner,const std::vector<gameplay_bridge::PagePixels>& pixels) {
    owner.upload(pixels,{
        [] {
            GLuint texture=0;
            glGenTextures(1,&texture);
            if(!texture) {
                require_graphics_ok("gameplay page allocation returned zero");
                throw std::runtime_error("gameplay page allocation returned zero without GL error");
            }
            return texture;
        },
        [](unsigned texture,const gameplay_bridge::PagePixels& page) {
            require_graphics_ok("gameplay owned page allocation");
            upload_bounded_rgba(texture,page.page.width,page.page.height,page.pixels);
            glBindTexture(GL_TEXTURE_2D,0);
            require_graphics_ok("gameplay owned page upload completion");
        },
        [](unsigned texture) {
            glDeleteTextures(1,&texture);
            require_graphics_ok("gameplay owned page rollback");
        }
    });
}
std::string draw_gameplay(const command_preflight::ReadyFrame& frame,
    const std::vector<command_submission::UploadedPage>& pages,const command_submission::View& view,
    const char* export_path,unsigned frame_number,const NormalOutputPaths* normal_outputs) {
    if(export_path && normal_initial_respawn_profile && !normal_outputs)
        throw std::invalid_argument("Normal gameplay export requires claimed per-run output binding");
    if(export_path && normal_outputs) normal_outputs->validate_capture(export_path,revision);
    command_submission::submit(frame,pages,view,{[](const auto&) {},[](auto,const auto&) {},[] {}});
    glViewport(0,0,view.width,view.height);
    glClearColor(0,0,0,1);
    glClear(GL_COLOR_BUFFER_BIT);
    require_graphics_ok("gameplay clear");
    submit_ready_frame(frame,pages,view);
    std::string receipt;
    if(export_path) {
        glReadBuffer(GL_BACK);
        glFinish();
        require_graphics_ok("gameplay export GPU finish");
        std::vector<std::uint8_t> rgba(std::size_t(view.width)*std::size_t(view.height)*4);
        glReadPixels(0,0,view.width,view.height,GL_RGBA,GL_UNSIGNED_BYTE,rgba.data());
        require_graphics_ok("gameplay export read pixels");
        write_guest_file(export_path,encode_frame_ppm(view.width,view.height,rgba),SCE_O_EXCL);
        receipt="frame_saved path="+std::string(export_path)+" revision="+revision+" capture="+capture_policy_name(room_capture_policy)+
            " render_style=bounded_gameplay_production frame="+
            std::to_string(frame_number)+" camera="+std::to_string(view.camera.x)+","+std::to_string(view.camera.y)+
            " commands="+std::to_string(frame.commands().size())+" finite_preflight=1 pixel_parity_claim=0 required_RGBA_bytes="+
            std::to_string(frame.required_rgba_bytes())+" physical_GPU_allocation_verified=0"+
            (normal_outputs ? " "+normal_outputs->capture_identity() : "")+"\n";
        write_guest_file((std::string(export_path)+".txt").c_str(),receipt,SCE_O_EXCL);
    }
    vglSwapBuffers(GL_FALSE);
    require_graphics_ok("gameplay buffer swap");
    return receipt;
}
}
