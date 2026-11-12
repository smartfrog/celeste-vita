#include "command_submission.hpp"
#include <cmath>
#include <stdexcept>
#include <unordered_map>

namespace celeste::command_submission {
void submit(const command_preflight::ReadyFrame& frame,const std::vector<UploadedPage>& pages,
            const View& view,const Sink& sink) {
    if(!sink.begin || !sink.quad || !sink.end)
        throw std::invalid_argument("ReadyFrame submission requires begin/quad/end callbacks");
    if(view.width<=0 || view.height<=0 || view.width>960 || view.height>544)
        throw std::invalid_argument("ReadyFrame viewport outside bounded 960x544 display");
    const Projection projection{diagnostic::letterbox(view.width,view.height),
        view.camera.x,view.camera.x+320.f,view.camera.y,view.camera.y+180.f};
    // Finite endpoints alone do not exclude collapsed or rounded logical extents.
    if(!std::isfinite(projection.left) || !std::isfinite(projection.right) ||
       !std::isfinite(projection.top) || !std::isfinite(projection.bottom) ||
       projection.right-projection.left!=320.f || projection.bottom-projection.top!=180.f)
        throw std::invalid_argument("ReadyFrame camera cannot represent a finite 320x180 projection");

    std::unordered_map<int,const UploadedPage*> uploaded;
    for(const auto& page:pages) {
        if(page.id<0 || page.width<=0 || page.height<=0 || !page.texture)
            throw std::invalid_argument("Invalid uploaded page metadata: "+std::to_string(page.id));
        if(!uploaded.emplace(page.id,&page).second)
            throw std::invalid_argument("Duplicate uploaded page ID: "+std::to_string(page.id));
    }
    if(uploaded.size()!=frame.pages().size())
        throw std::invalid_argument("Uploaded page set differs from ReadyFrame table pages");
    for(const auto& page:frame.pages()) {
        const auto found=uploaded.find(page.id);
        if(found==uploaded.end())
            throw std::invalid_argument("Missing uploaded page ID: "+std::to_string(page.id));
        if(found->second->width!=page.width || found->second->height!=page.height)
            throw std::invalid_argument("Uploaded page dimensions differ: "+std::to_string(page.id));
    }
    if(frame.commands().empty()) return;
    sink.begin(projection);
    for(const auto& command:frame.commands()) sink.quad(uploaded.at(command.page)->texture,command);
    sink.end();
}
}
