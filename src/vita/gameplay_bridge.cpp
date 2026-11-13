#include "gameplay_bridge.hpp"
#include <limits>
#include <set>
#include <stdexcept>

namespace celeste::gameplay_bridge {
namespace {
const char* reason(command_preflight::FailureReason value) {
    using R=command_preflight::FailureReason;
    switch(value) {
    case R::invalid_metadata:return "invalid_metadata";
    case R::ambiguous_material:return "ambiguous_material";
    case R::unsupported_packing:return "unsupported_packing";
    case R::missing_material:return "missing_material";
    case R::empty_crop:return "empty_crop";
    case R::invalid_crop:return "invalid_crop";
    case R::nonfinite_input:return "nonfinite_input";
    case R::invalid_geometry:return "invalid_geometry";
    case R::nonfinite_output:return "nonfinite_output";
    }
    throw std::invalid_argument("Unknown preflight failure reason");
}
}
std::vector<command_preflight::CommandInput> inputs(const gameplay_commands::Schedule& schedule) {
    std::vector<command_preflight::CommandInput> result;
    result.reserve(schedule.commands().size());
    for(const auto& command:schedule.commands()) result.push_back({command.image,command.geometry});
    return result;
}
command_preflight::ReadyFrame prepare(unsigned frame,const command_preflight::MaterialTable& table,
                                     const std::vector<command_preflight::CommandInput>& commands) {
    auto result=command_preflight::preflight(table,commands);
    if(const auto* failure=std::get_if<command_preflight::Failure>(&result)) {
        const auto& crop=failure->crop;
        throw std::runtime_error("Gameplay preflight frame="+std::to_string(frame)+" owner="+std::to_string(failure->identity)+
            " material="+failure->material+" sheet="+failure->sheet+" crop="+std::to_string(crop[0])+","+
            std::to_string(crop[1])+","+std::to_string(crop[2])+","+std::to_string(crop[3])+" reason="+reason(failure->reason)+
            " command="+(failure->command_index?std::to_string(*failure->command_index):"none")+" cause="+failure->detail);
    }
    return std::get<command_preflight::ReadyFrame>(std::move(result));
}
void submit(unsigned frame,const command_preflight::MaterialTable& table,
    const std::vector<command_preflight::CommandInput>& commands,const std::vector<command_submission::UploadedPage>& pages,
    const command_submission::View& view,const command_submission::Sink& sink) {
    command_submission::submit(prepare(frame,table,commands),pages,view,sink);
}
void PageOwner::dispose(const std::function<void(unsigned)>& remove) {
    if(!remove) throw std::invalid_argument("Page cleanup callback is missing");
    auto owned=std::move(pages_);
    pages_.clear();
    std::string failures;
    for(const auto& page:owned) {
        try { remove(page.texture); }
        catch(const std::exception& error) { failures+=" page="+std::to_string(page.id)+": "+error.what(); }
    }
    if(!failures.empty()) throw std::runtime_error("Page cleanup failed:"+failures);
}
void PageOwner::upload(const std::vector<PagePixels>& pixels,const Upload& driver) {
    if(!pages_.empty()) throw std::logic_error("Gameplay pages already owned");
    if(!driver.allocate || !driver.write || !driver.remove) throw std::invalid_argument("Incomplete page upload callbacks");
    std::set<int> ids;
    for(const auto& value:pixels) {
        const auto& page=value.page;
        const auto maximum=std::numeric_limits<std::size_t>::max();
        if(page.id<0 || page.width<=0 || page.height<=0 || !ids.insert(page.id).second ||
           std::size_t(page.width)>maximum/std::size_t(page.height)/4 ||
           value.pixels.size()!=std::size_t(page.width)*std::size_t(page.height)*4)
            throw std::invalid_argument("Invalid gameplay RGBA page id/dimensions/bytes: "+std::to_string(page.id));
    }
    pages_.reserve(pixels.size());
    std::set<unsigned> handles;
    try {
        for(const auto& value:pixels) {
            const auto texture=driver.allocate();
            if(!texture) throw std::runtime_error("Gameplay page allocation returned zero: "+std::to_string(value.page.id));
            if(!handles.insert(texture).second) throw std::runtime_error("Gameplay page allocation returned duplicate handle: "+std::to_string(value.page.id));
            pages_.push_back({value.page.id,value.page.width,value.page.height,texture});
            driver.write(texture,value);
        }
    } catch(const std::exception& error) {
        const std::string cause=error.what();
        try { dispose(driver.remove); }
        catch(const std::exception& cleanup) { throw std::runtime_error(cause+"; rollback also failed: "+cleanup.what()); }
        throw;
    }
}
}
