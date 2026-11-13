#pragma once
#include "command_preflight.hpp"
#include "command_submission.hpp"
#include "gameplay_bridge.hpp"

namespace celeste::diagnostic {
struct NormalOutputPaths;
void upload_gameplay_pages(gameplay_bridge::PageOwner& owner,const std::vector<gameplay_bridge::PagePixels>& pixels);
void dispose_gameplay_pages(gameplay_bridge::PageOwner& owner);
// Preflight and page validation already happened; this is the actual opt-in draw/export.
std::string draw_gameplay(const command_preflight::ReadyFrame& frame,
    const std::vector<command_submission::UploadedPage>& pages,const command_submission::View& view,
    const char* export_path,unsigned frame_number,const NormalOutputPaths* normal_outputs=nullptr);
}
