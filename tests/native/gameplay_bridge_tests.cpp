#include "gameplay_bridge.hpp"
#include <iostream>
#include <stdexcept>

using namespace celeste;
namespace {
void require(bool condition,const char* message) { if(!condition) throw std::runtime_error(message); }
void late_invalid_command_blocks_every_sink_callback() {
    command_preflight::MaterialTable table;
    table.pages={{7,16,16}};
    table.bindings={{{"fixture-sheet",0,0,8,8,0,0,8,8,"fixture-image"},16,16,7,0,0,8,8,false,{}}};
    decal_commands::DecalCommand image;
    image.identity=42;image.texture="fixture-image";image.sheet="fixture-sheet";
    image.source_width=8;image.source_height=8;
    std::vector<command_preflight::CommandInput> commands{{image,decal_commands::project_geometry(image,16,16)}};
    image.identity=99;image.source_height=0;
    commands.push_back({image,decal_commands::project_geometry(image,16,16)});
    unsigned callbacks=0;
    try {
        gameplay_bridge::submit(123,table,commands,{{7,16,16,11}},{{3.25f,-4.5f},960,544},
            {[&](const auto&) { ++callbacks; },[&](auto,const auto&) { ++callbacks; },[&] { ++callbacks; }});
    } catch(const std::runtime_error& error) {
        const std::string text=error.what();
        require(callbacks==0,"Late invalid input must prevent ALL sink callbacks");
        for(const auto* field:{"frame=123","owner=99","fixture-image","crop=0,0,8,0","empty_crop"})
            require(text.find(field)!=std::string::npos,"Failure must preserve frame/owner/material/crop/reason");
        return;
    }
    throw std::runtime_error("Empty crop must block the frame");
}
void upload_failure_rolls_back_every_allocated_page() {
    std::vector<gameplay_bridge::PagePixels> pixels{{{8,1,1},"aaaa"},{{2,1,1},"bbbb"}};
    unsigned next=100,uploads=0;std::vector<unsigned> deleted;
    gameplay_bridge::PageOwner owner;
    try {
        owner.upload(pixels,{[&] { return ++next; },[&](auto,const auto&) {
            if(++uploads==2) throw std::runtime_error("fixture driver failure");
        },[&](unsigned handle) { deleted.push_back(handle); }});
    } catch(const std::runtime_error& error) {
        require(std::string(error.what()).find("fixture driver failure")!=std::string::npos,"Driver cause must propagate");
        require(deleted==std::vector<unsigned>{101,102},"Rollback must include allocated but not uploaded pages");
        require(owner.pages().empty(),"Rollback must relinquish every handle");
        owner.dispose([&](unsigned handle) { deleted.push_back(handle); });
        require(deleted.size()==2,"Repeated cleanup must not double-delete");return;
    }
    throw std::runtime_error("Driver failure must propagate");
}
void malformed_page_catalog_has_no_upload_side_effects() {
    gameplay_bridge::PageOwner owner;unsigned calls=0;
    try {
        owner.upload({{{2,1,1},"aaaa"},{{2,1,1},"bbbb"}},
            {[&] { ++calls;return 1u; },[&](auto,const auto&) { ++calls; },[&](auto) { ++calls; }});
    } catch(const std::invalid_argument&) { require(calls==0,"Validate complete page set before GL");return; }
    throw std::runtime_error("Duplicate page IDs must reject");
}
void duplicate_driver_handles_never_double_free() {
    gameplay_bridge::PageOwner owner;std::vector<unsigned> removed;
    try {
        owner.upload({{{2,1,1},"aaaa"},{{3,1,1},"bbbb"}},
            {[] { return 9u; },[](auto,const auto&) {},[&](auto texture) { removed.push_back(texture); }});
    } catch(const std::runtime_error& error) {
        require(std::string(error.what()).find("duplicate")!=std::string::npos,"Duplicate allocation error must be explicit");
        require(removed==std::vector<unsigned>{9},"Duplicate driver handles must not lead to double deletion");return;
    }
    owner.dispose([&](auto texture) { removed.push_back(texture); });
    throw std::runtime_error("Duplicate driver handles must reject");
}
}
int main() {
    try {
        late_invalid_command_blocks_every_sink_callback();
        upload_failure_rolls_back_every_allocated_page();
        malformed_page_catalog_has_no_upload_side_effects();
        duplicate_driver_handles_never_double_free();
        std::cout<<"4 production bridge behaviors passed\n";
    } catch(const std::exception& error) { std::cerr<<error.what()<<'\n';return 1; }
}
