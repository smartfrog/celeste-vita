#pragma once
#include "command_submission.hpp"
#include "gameplay_projection.hpp"

namespace celeste::gameplay_bridge {
std::vector<command_preflight::CommandInput> inputs(const gameplay_commands::Schedule& schedule);
command_preflight::ReadyFrame prepare(unsigned frame,const command_preflight::MaterialTable& table,
                                     const std::vector<command_preflight::CommandInput>& commands);
void submit(unsigned frame,const command_preflight::MaterialTable& table,
    const std::vector<command_preflight::CommandInput>& commands,const std::vector<command_submission::UploadedPage>& pages,
    const command_submission::View& view,const command_submission::Sink& sink);
struct PagePixels { command_preflight::Page page;std::string pixels; };
struct Upload {
    std::function<unsigned()> allocate;
    std::function<void(unsigned,const PagePixels&)> write;
    std::function<void(unsigned)> remove;
};
class PageOwner final {
public:
    PageOwner()=default;
    PageOwner(const PageOwner&)=delete;
    PageOwner& operator=(const PageOwner&)=delete;
    void upload(const std::vector<PagePixels>& pixels,const Upload& driver);
    void dispose(const std::function<void(unsigned)>& remove);
    const std::vector<command_submission::UploadedPage>& pages() const { return pages_; }
private:
    std::vector<command_submission::UploadedPage> pages_;
};
}
