#include "gameplay_bridge.hpp"
#include <iostream>
#include <stdexcept>

using namespace celeste;
namespace {
void require(bool condition,const char* message) { if(!condition) throw std::runtime_error(message); }
const command_preflight::Policy accept_semantic{
    command_preflight::Policy::ZeroAreaBanner::accept_semantic_no_raster};

decal_commands::DecalCommand zero_height_strip(std::uint64_t identity,int ordinal,
                                               const char* texture,int slice) {
    decal_commands::DecalCommand command;
    command.identity=identity;command.room="fixture";command.background=true;
    command.ordinal=ordinal;command.texture=texture;command.sheet="Fixture";
    command.source_x=2;command.source_y=2;command.source_width=8;command.source_height=0;
    command.position={32,16};command.origin={4,4};command.scale={1,1};command.slice=slice;
    return command;
}
struct BannerSchedule {
    RoomDefinition room{"fixture",{0,0,64,64},49,{0,0},{}};
    draw_order::DrawOwner banner_owner{draw_order::OwnerKind::decal,2,1,&room,9000,1,true,false,true,"banner",{32,16}};
    draw_order::DrawOwner image_owner{draw_order::OwnerKind::decal,1,0,&room,9000,0,true,false,false,"image",{16,16}};
    draw_order::DrawProjection projection;
    decal_commands::DecalProjection decals;
    std::vector<terrain::Sheet> sheets{{"Fixture",64,64}};
    gameplay_commands::Inputs inputs;
    command_preflight::MaterialTable materials;
    explicit BannerSchedule(bool include_image) {
        projection.live.push_back(banner_owner);
        projection.dispatch.push_back(0);
        decals.commands.push_back(zero_height_strip(2,1,"banner",0));
        if(include_image) {
            projection.live.push_back(image_owner);
            projection.dispatch.push_back(1);
            decals.commands.push_back(zero_height_strip(1,0,"image",-1));
        }
        inputs.decals=&decals;inputs.sheets=&sheets;
        materials.pages={{7,64,64}};
        for(const auto& command:decals.commands) {
            command_preflight::MaterialBinding binding;
            binding.original={"Fixture",0,0,16,16,0,0,16,16,command.texture};
            binding.original_sheet_width=64;binding.original_sheet_height=64;
            binding.page=7;binding.packed_x=0;binding.packed_y=0;
            binding.packed_width=16;binding.packed_height=16;
            materials.bindings.push_back(binding);
        }
    }
    gameplay_commands::Schedule assemble() const { return gameplay_commands::assemble(projection,inputs); }
};
void bridge_derives_semantic_coverage_from_assembled_banner_only() {
    BannerSchedule fixture(true);
    const auto schedule=fixture.assemble();
    require(schedule.commands().size()==2 &&
            schedule.commands()[0].component==gameplay_commands::Component::banner &&
            schedule.commands()[1].component==gameplay_commands::Component::decal_image,
        "Actual assembly must retain Banner and DecalImage components before bridge derivation");
    const auto input=gameplay_bridge::inputs(schedule);
    require(input.size()==2,"Every assembled command must reach preflight");
    require(input[0].coverage==command_preflight::Coverage::semantic_zero_area_banner,
        "Only the assembled Banner zero-height strip may be derived as semantic coverage");
    require(input[1].coverage==command_preflight::Coverage::raster,
        "A non-Banner zero-height command must remain raster even with the same NaN geometry");
    for(std::size_t index=0;index<input.size();++index)
        require(input[index].geometry.vertices==schedule.commands()[index].geometry.vertices,
            "Bridge derivation must retain original geometry words bit-for-bit");
    unsigned callbacks=0;
    try {
        gameplay_bridge::submit(9,fixture.materials,input,{{7,64,64,11}},{{},960,544},
            {[&](const auto&) { ++callbacks; },[&](auto,const auto&) { ++callbacks; },[&] { ++callbacks; },
             [&](const auto&) { ++callbacks; }},accept_semantic);
    } catch(const std::runtime_error& error) {
        const std::string text=error.what();
        require(callbacks==0 && text.find("empty_crop")!=std::string::npos &&
                text.find("command=1")!=std::string::npos,
            "Non-Banner zero-area input must still reject the entire frame before callbacks");
        return;
    }
    throw std::runtime_error("Non-Banner zero-area input must not be accepted as semantic");
}
void optin_assembled_banner_passes_and_default_rejects() {
    BannerSchedule fixture(false);
    const auto schedule=fixture.assemble();
    const auto input=gameplay_bridge::inputs(schedule);
    require(input.size()==1 && input[0].coverage==command_preflight::Coverage::semantic_zero_area_banner,
        "Actual assembled Banner zero-area strip must derive semantic coverage");
    try {
        gameplay_bridge::prepare(7,fixture.materials,input);
    } catch(const std::runtime_error& error) {
        require(std::string(error.what()).find("empty_crop")!=std::string::npos,
            "Default policy must still reject the assembled semantic strip");
        const auto ready=gameplay_bridge::prepare(7,fixture.materials,input,accept_semantic);
        require(ready.commands().size()==1 &&
                ready.commands()[0].coverage==command_preflight::Coverage::semantic_zero_area_banner,
            "Explicit host opt-in must preserve the assembled semantic command");
        require(ready.commands()[0].geometry.vertices==schedule.commands()[0].geometry.vertices &&
                ready.commands()[0].command.identity==2 && ready.commands()[0].command.slice==0,
            "Opt-in must preserve the exact assembled NaN payload and banner metadata");
        unsigned begins=0,quads=0,ends=0,acks=0;
        command_submission::Sink sink{
            [&](const auto&) { ++begins; },[&](auto,const auto&) { ++quads; },[&] { ++ends; },
            [&](const auto& command) { ++acks;require(command.command.identity==2,"Ack must identify the Banner owner"); }};
        gameplay_bridge::submit(7,fixture.materials,input,{{7,64,64,11}},{{},960,544},sink,accept_semantic);
        require(begins==0 && quads==0 && ends==0 && acks==1,
            "A bridge opt-in semantic frame must emit one ordered ack and no raster GL batch");
        return;
    }
    throw std::runtime_error("Default policy accepted an assembled zero-area Banner strip");
}
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
            {[&](const auto&) { ++callbacks; },[&](auto,const auto&) { ++callbacks; },[&] { ++callbacks; },
             [&](const auto&) { ++callbacks; }});
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
        bridge_derives_semantic_coverage_from_assembled_banner_only();
        optin_assembled_banner_passes_and_default_rejects();
        std::cout<<"6 production bridge behaviors passed\n";
    } catch(const std::exception& error) { std::cerr<<error.what()<<'\n';return 1; }
}
