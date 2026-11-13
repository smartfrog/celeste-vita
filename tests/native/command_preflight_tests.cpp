#include "command_preflight.hpp"
#include <algorithm>
#include <cmath>
#include <cstring>
#include <iostream>
#include <limits>
#include <sstream>
#include <stdexcept>
#include <type_traits>

using namespace celeste;
using namespace celeste::command_preflight;
namespace {
void require(bool condition,const char* message) {
    if(!condition) throw std::runtime_error(message);
}

float value(std::int32_t bits) {
    float result;
    std::memcpy(&result,&bits,sizeof(result));
    return result;
}

std::int32_t bits(float value) {
    std::int32_t result;
    std::memcpy(&result,&value,sizeof(result));
    return result;
}

std::string snapshot(const std::vector<CommandInput>& inputs) {
    std::ostringstream out;
    for(const auto& input:inputs) {
        const auto& c=input.command;
        out<<c.identity<<' '<<c.room<<' '<<c.background<<' '<<c.ordinal<<' '<<c.texture<<' '<<c.sheet<<' '
           <<c.source_x<<' '<<c.source_y<<' '<<c.source_width<<' '<<c.source_height<<' '
           <<int(c.color.r)<<' '<<int(c.color.g)<<' '<<int(c.color.b)<<' '<<int(c.color.a)<<' '
           <<c.effects<<' '<<c.slice<<' ';
        for(auto number:{c.position.x,c.position.y,c.origin.x,c.origin.y,c.scale.x,c.scale.y,c.rotation})
            out<<bits(number)<<' ';
        out<<input.geometry.finite<<' ';
        for(const auto& vertex:input.geometry.vertices) for(auto field:vertex) out<<field<<' ';
    }
    return out.str();
}

const ReadyFrame& ready(const Result& result) {
    require(std::holds_alternative<ReadyFrame>(result),"Expected an owned ready frame");
    return std::get<ReadyFrame>(result);
}

const Failure& failure(const Result& result,FailureReason reason) {
    require(std::holds_alternative<Failure>(result),"Expected frame-blocking failure");
    const auto& error=std::get<Failure>(result);
    require(error.reason==reason,"Unexpected failure reason");
    require(!error.detail.empty(),"Failure must explain why the frame is blocked");
    return error;
}

MaterialTable table() {
    MaterialBinding binding;
    binding.original={"synthetic/sheet",16,24,16,12,-3,-5,32,32,"synthetic/frame"};
    binding.original_sheet_width=128;
    binding.original_sheet_height=64;
    binding.page=7;
    binding.packed_x=4;
    binding.packed_y=8;
    binding.packed_width=16;
    binding.packed_height=12;
    return {{{7,64,32}},{binding}};
}

CommandInput input() {
    decal_commands::DecalCommand command;
    command.identity=42;
    command.room="synthetic/room";
    command.texture="synthetic/frame";
    command.sheet="synthetic/sheet";
    command.source_x=20;
    command.source_y=28;
    command.source_width=8;
    command.source_height=4;
    command.position={10,20};
    command.origin={2,3};
    command.scale={-1,1};
    command.color={23,45,67,89};
    return {command,decal_commands::project_geometry(command,128,64)};
}

void valid_trimmed_subrect_is_ready() {
    const auto result=preflight(table(),{input()});
    require(std::holds_alternative<ReadyFrame>(result),"Valid trimmed 8x4 subrect must be ready");
    const auto& frame=std::get<ReadyFrame>(result);
    require(frame.commands().size()==1 && frame.commands()[0].page==7,"Resolved page is required");
    require(frame.required_rgba_bytes()==64*32*4,"RGBA estimate must use actual page dimensions");
}

void source_uv_flips_and_corner_order_are_preserved() {
    auto command=input();
    std::swap(command.geometry.vertices[0][3],command.geometry.vertices[1][3]);
    std::swap(command.geometry.vertices[2][3],command.geometry.vertices[3][3]);
    const auto result=preflight(table(),{command});
    const auto& output=ready(result).commands()[0];
    const std::array<float,4> expected_u{{16.f/64,8.f/64,16.f/64,8.f/64}};
    const std::array<float,4> expected_v{{12.f/32,12.f/32,16.f/32,16.f/32}};
    for(unsigned corner=0;corner<4;++corner) {
        require(output.geometry.vertices[corner][3]==bits(expected_u[corner]),"Packed U must retain flipped corner order");
        require(output.geometry.vertices[corner][4]==bits(expected_v[corner]),"Packed V must use parent crop and actual page height");
    }
}

void signed_zero_xyz_and_descriptor_bits_are_copied() {
    auto command=input();
    command.command.position.x=-0.f;
    for(auto& vertex:command.geometry.vertices) {
        vertex[0]=bits(-0.f);
        vertex[2]=bits(-0.f);
    }
    const auto result=preflight(table(),{command});
    const auto& output=ready(result).commands()[0];
    for(unsigned corner=0;corner<4;++corner) for(unsigned field=0;field<3;++field)
        require(output.geometry.vertices[corner][field]==command.geometry.vertices[corner][field],"XYZ must be copied bit-for-bit without geometry recomputation");
    require(snapshot({{output.command,command.geometry}})==snapshot({command}),"Logical descriptor and color bits must be copied unchanged");
}

void successful_input_is_immutable_and_ready_output_is_owned() {
    auto materials=table();
    std::vector<CommandInput> inputs{input()};
    const auto before=snapshot(inputs);
    const auto result=preflight(materials,inputs);
    require(snapshot(inputs)==before,"Success must not change CPU input bits");
    inputs[0].command.texture="changed";
    inputs[0].geometry.vertices[0][0]=bits(999.f);
    materials.pages[0].width=1;
    require(ready(result).commands()[0].command.texture=="synthetic/frame","Ready output must own material descriptors");
    require(ready(result).pages()[0].width==64,"Ready output must own page metadata");
    require(ready(result).commands()[0].geometry.vertices[0][0]!=bits(999.f),"Ready output must own geometry");
}

void outline_passes_reuse_material_without_reordering() {
    auto first=input(),second=input(),third=input();
    first.command.identity=99;
    second.command.identity=2;
    third.command.identity=77;
    first.command.color={0,0,0,255};
    second.command.color={0,0,0,255};
    first.command.position.x-=1;
    second.command.position.x+=1;
    std::vector<CommandInput> inputs{first,second,third};
    const auto result=preflight(table(),inputs);
    const auto& outputs=ready(result).commands();
    require(outputs.size()==inputs.size(),"Outline passes must not be merged or omitted");
    for(unsigned index=0;index<outputs.size();++index) {
        require(outputs[index].page==7,"Outline passes reuse the same resolved material");
        require(snapshot({{outputs[index].command,inputs[index].geometry}})==snapshot({inputs[index]}),"Command order and all descriptor bits must remain unchanged");
    }
}

void exact_alias_is_required_parameterized() {
    for(const auto& alias:{"","synthetic/other","Synthetic/frame","synthetic/sheet"}) {
        auto command=input();
        command.command.texture=alias;
        const auto result=preflight(table(),{command});
        failure(result,FailureReason::missing_material);
    }
}

void sheet_is_part_of_material_key() {
    auto command=input();
    command.command.sheet="synthetic/other-sheet";
    const auto result=preflight(table(),{command});
    failure(result,FailureReason::missing_material);
}

void explicitly_equivalent_alias_resolves_uniquely() {
    auto materials=table();
    materials.bindings[0].equivalent_aliases={"synthetic/equivalent"};
    auto command=input();
    command.command.texture="synthetic/equivalent";
    const auto result=preflight(materials,{command});
    require(ready(result).commands()[0].page==7,"Explicit equivalent alias must resolve to its declared material");
}

void ambiguous_parent_material_fails_before_frame_walk() {
    auto materials=table();
    auto duplicate=materials.bindings[0];
    duplicate.original.x+=1;
    materials.bindings.push_back(duplicate);
    auto command=input();
    command.command.source_height=0;
    const auto result=preflight(materials,{command});
    const auto& error=failure(result,FailureReason::ambiguous_material);
    require(!error.command_index && error.binding_index==1,"Ambiguous metadata must fail before the empty command is walked");
    require(error.material==duplicate.original.texture && error.sheet==duplicate.original.sheet,"Metadata errors must identify their material");
}

void equivalent_alias_collision_blocks_even_empty_frame() {
    auto materials=table();
    auto duplicate=materials.bindings[0];
    duplicate.original.texture="synthetic/other";
    duplicate.equivalent_aliases={materials.bindings[0].original.texture};
    materials.bindings.push_back(duplicate);
    const auto result=preflight(materials,{});
    failure(result,FailureReason::ambiguous_material);
}

struct MockSubmission {
    unsigned count=0;
    void submit(const ReadyFrame& frame) { count+=frame.commands().size(); }
};

void late_zero_height_blocks_entire_frame_and_preserves_cpu_bits() {
    auto invalid=input();
    invalid.command.identity=123;
    invalid.command.source_height=0;
    invalid.geometry=decal_commands::project_geometry(invalid.command,128,64);
    require(!invalid.geometry.finite,"Fixture must reproduce zero-height Source nonfinite geometry");
    std::vector<CommandInput> inputs{input(),input(),invalid};
    const auto before=snapshot(inputs);
    MockSubmission gpu;
    const auto result=preflight(table(),inputs);
    if(const auto* frame=std::get_if<ReadyFrame>(&result)) gpu.submit(*frame);
    const auto& error=failure(result,FailureReason::empty_crop);
    require(gpu.count==0,"Late invalid command must cause zero GPU submissions, including earlier valid commands");
    require(error.command_index==2 && error.identity==123,"Error must identify command index and owner identity");
    require(error.material==invalid.command.texture && error.sheet==invalid.command.sheet && error.crop==std::array<int,4>{{20,28,8,0}},"Error must identify material and crop");
    require(snapshot(inputs)==before,"Failure must preserve every CPU descriptor and NaN bit");
}

void submission_can_consume_only_complete_ready_frame() {
    static_assert(!std::is_default_constructible_v<ReadyFrame>);
    MockSubmission gpu;
    const auto result=preflight(table(),{input(),input()});
    require(gpu.count==0,"Pure preflight must not submit anything");
    gpu.submit(ready(result));
    require(gpu.count==2,"Submission occurs only after a complete ready frame is obtained");
}

void geometry_nonfinite_bits_are_rejected_parameterized() {
    for(float invalid:{std::numeric_limits<float>::quiet_NaN(),std::numeric_limits<float>::infinity(),-std::numeric_limits<float>::infinity()})
        for(unsigned corner=0;corner<4;++corner) for(unsigned field=0;field<5;++field) {
            auto command=input();
            command.geometry.vertices[corner][field]=bits(invalid);
            command.geometry.finite=true;
            const std::vector<CommandInput> inputs{command};
            const auto before=snapshot(inputs);
            const auto result=preflight(table(),inputs);
            failure(result,FailureReason::nonfinite_input);
            require(snapshot(inputs)==before,"Untrusted finite flag must not allow or sanitize nonfinite bits");
        }
}

void descriptor_nonfinite_fields_are_rejected_parameterized() {
    for(unsigned field=0;field<7;++field) {
        auto command=input();
        auto& c=command.command;
        const std::array<float*,7> fields{{&c.position.x,&c.position.y,&c.origin.x,&c.origin.y,&c.scale.x,&c.scale.y,&c.rotation}};
        *fields[field]=std::numeric_limits<float>::infinity();
        const auto result=preflight(table(),{command});
        failure(result,FailureReason::nonfinite_input);
    }
}

void false_geometry_flag_blocks_frame() {
    auto command=input();
    command.geometry.finite=false;
    const auto result=preflight(table(),{command});
    failure(result,FailureReason::invalid_geometry);
}

void source_uv_outside_descriptor_is_rejected() {
    auto command=input();
    command.geometry.vertices[0][3]=bits(0.f);
    const auto result=preflight(table(),{command});
    failure(result,FailureReason::invalid_geometry);
}

void empty_frame_is_ready_without_materials() {
    const auto result=preflight({},{});
    require(ready(result).commands().empty() && ready(result).pages().empty() && ready(result).required_rgba_bytes()==0,"Empty frame is explicitly ready after metadata validation");
}

void late_missing_material_also_blocks_submission() {
    auto invalid=input();
    invalid.command.texture="synthetic/missing";
    MockSubmission gpu;
    const auto result=preflight(table(),{input(),invalid});
    if(const auto* frame=std::get_if<ReadyFrame>(&result)) gpu.submit(*frame);
    const auto& error=failure(result,FailureReason::missing_material);
    require(gpu.count==0 && error.command_index==1,"Late binding failure must block the entire frame");
}

void late_infinity_blocks_submission_despite_true_finite_flag() {
    auto invalid=input();
    invalid.geometry.vertices[3][2]=bits(std::numeric_limits<float>::infinity());
    invalid.geometry.finite=true;
    MockSubmission gpu;
    const auto result=preflight(table(),{input(),invalid});
    if(const auto* frame=std::get_if<ReadyFrame>(&result)) gpu.submit(*frame);
    const auto& error=failure(result,FailureReason::nonfinite_input);
    require(gpu.count==0 && error.command_index==1,"Late nonfinite bits must block every earlier valid command");
}

void unused_invalid_binding_blocks_otherwise_valid_frame() {
    auto materials=table();
    auto invalid=materials.bindings[0];
    invalid.original.texture="synthetic/unused";
    invalid.page=-1;
    materials.bindings.push_back(invalid);
    const auto result=preflight(materials,{input()});
    const auto& error=failure(result,FailureReason::invalid_metadata);
    require(!error.command_index && error.binding_index==1,"All bindings, including unused ones, must validate before command walking");
}

void command_crop_bounds_are_checked_without_integer_overflow_parameterized() {
    for(const auto crop:{std::array<int,4>{{-1,28,8,4}},{{20,-1,8,4}},{{20,28,-1,4}},
                         {{20,28,8,-1}},{{20,28,100,4}},{{20,28,8,100}},
                         {{std::numeric_limits<int>::max(),28,std::numeric_limits<int>::max(),4}}}) {
        auto command=input();
        command.command.source_x=crop[0];
        command.command.source_y=crop[1];
        command.command.source_width=crop[2];
        command.command.source_height=crop[3];
        const auto result=preflight(table(),{command});
        failure(result,FailureReason::invalid_crop);
    }
}

void zero_extent_always_blocks_parameterized() {
    for(bool width:{false,true}) {
        auto command=input();
        if(width) command.command.source_width=0;
        else command.command.source_height=0;
        const auto result=preflight(table(),{command});
        failure(result,FailureReason::empty_crop);
    }
}

void rotated_and_rescaled_packing_are_explicitly_unsupported_parameterized() {
    for(unsigned kind=0;kind<3;++kind) {
        auto materials=table();
        if(kind==0) materials.bindings[0].rotated=true;
        if(kind==1) materials.bindings[0].packed_width*=2;
        if(kind==2) materials.bindings[0].packed_height*=2;
        const auto result=preflight(materials,{input()});
        failure(result,FailureReason::unsupported_packing);
    }
}

void invalid_metadata_is_rejected_before_commands_parameterized() {
    for(unsigned kind=0;kind<20;++kind) {
        auto materials=table();
        auto& b=materials.bindings[0];
        switch(kind) {
        case 0: materials.pages[0].id=-1; break;
        case 1: materials.pages[0].width=0; break;
        case 2: materials.pages[0].height=-1; break;
        case 3: materials.pages.push_back(materials.pages[0]); break;
        case 4: b.page=99; break;
        case 5: b.original.texture.clear(); break;
        case 6: b.original.sheet.clear(); break;
        case 7: b.original_sheet_width=0; break;
        case 8: b.original_sheet_height=-1; break;
        case 9: b.original.x=std::numeric_limits<int>::max(); break;
        case 10: b.original.y=-1; break;
        case 11: b.original.width=std::numeric_limits<int>::max(); break;
        case 12: b.original.height=0; break;
        case 13: b.original.frame_width=0; break;
        case 14: b.original.frame_height=-1; break;
        case 15: b.original.offset_x=std::numeric_limits<float>::quiet_NaN(); break;
        case 16: b.original.offset_y=std::numeric_limits<float>::infinity(); break;
        case 17: b.packed_x=std::numeric_limits<int>::max(); break;
        case 18: b.packed_y=-1; break;
        case 19: b.equivalent_aliases={""}; break;
        }
        auto invalid=input();
        invalid.command.source_height=0;
        const auto result=preflight(materials,{invalid});
        const auto& error=failure(result,FailureReason::invalid_metadata);
        require(!error.command_index,"Invalid metadata must fail before any command walk");
    }
}

void conflicting_sheet_dimensions_are_rejected() {
    auto materials=table();
    auto second=materials.bindings[0];
    second.original.texture="synthetic/other";
    second.original_sheet_width=256;
    materials.bindings.push_back(second);
    const auto result=preflight(materials,{});
    failure(result,FailureReason::invalid_metadata);
}

void duplicate_identical_bindings_are_not_silently_deduplicated() {
    auto materials=table();
    materials.bindings.push_back(materials.bindings[0]);
    const auto result=preflight(materials,{});
    failure(result,FailureReason::ambiguous_material);
}

void duplicate_alias_within_binding_is_rejected() {
    auto materials=table();
    materials.bindings[0].equivalent_aliases={"synthetic/equivalent","synthetic/equivalent"};
    const auto result=preflight(materials,{});
    failure(result,FailureReason::ambiguous_material);
}

void rgba_byte_estimate_overflow_blocks_frame() {
    const auto maximum=std::numeric_limits<int>::max();
    MaterialTable materials{{{1,maximum,maximum},{2,maximum,maximum}}, {}};
    const auto result=preflight(materials,{});
    failure(result,FailureReason::invalid_metadata);
}

void actual_page_dimensions_have_no_invented_gpu_limit() {
    auto materials=table();
    materials.pages[0].width=8192;
    const auto result=preflight(materials,{input()});
    require(ready(result).required_rgba_bytes()==8192*32*4,"Page estimate is not parser/file size or an invented 4096 GPU cap");
    require(ready(result).commands()[0].geometry.vertices[0][3]==bits(8.f/8192),"Packed UV must use actual large page width");
}

void non_power_of_two_dimensions_map_source_bits_without_clamping() {
    auto materials=table();
    materials.bindings[0].original_sheet_width=137;
    materials.bindings[0].original_sheet_height=79;
    materials.pages[0].width=71;
    materials.pages[0].height=43;
    auto command=input();
    command.geometry=decal_commands::project_geometry(command.command,137,79);
    const auto result=preflight(materials,{command});
    const auto& output=ready(result).commands()[0];
    for(unsigned corner=0;corner<4;++corner) {
        const auto& original=command.geometry.vertices[corner];
        const float expected_u=float((4.0+(double(value(original[3]))*137-16)/16*16)/71);
        const float expected_v=float((8.0+(double(value(original[4]))*79-24)/12*12)/43);
        require(output.geometry.vertices[corner][3]==bits(expected_u) && output.geometry.vertices[corner][4]==bits(expected_v),"UV mapping must use original float bits without clamping or rounding source geometry");
        for(auto field:output.geometry.vertices[corner]) require(std::isfinite(value(field)),"Every output float bit must be finite");
    }
}

const Policy accept_semantic{Policy::ZeroAreaBanner::accept_semantic_no_raster};

CommandInput semantic_input() {
    auto command=input();
    command.command.slice=0;
    command.command.source_y=36;
    command.command.source_height=0;
    command.geometry=decal_commands::project_geometry(command.command,128,64);
    command.coverage=Coverage::semantic_zero_area_banner;
    return command;
}

void require_semantic_bits(const CommandInput& input,const ReadyCommand& output) {
    require(output.coverage==Coverage::semantic_zero_area_banner,"Semantic coverage must survive preflight");
    require(output.command.identity==input.command.identity && output.command.slice==input.command.slice &&
            output.command.source_width==input.command.source_width && output.command.source_height==0,
            "Semantic descriptor and crop metadata must remain unchanged");
    require(snapshot({{output.command,output.geometry}})==snapshot({{input.command,input.geometry,input.coverage}}),
        "Semantic logical descriptor and all geometry payload bits must remain unchanged");
    require(output.geometry.vertices==input.geometry.vertices,"Semantic NaN/UV payload bits and vertex count must remain unchanged");
    for(unsigned corner=0;corner<4;++corner) {
        require(std::isnan(value(output.geometry.vertices[corner][0])) && std::isnan(value(output.geometry.vertices[corner][1])),
            "Semantic XY must retain the real nonfinite pattern");
        for(unsigned field=2;field<5;++field)
            require(std::isfinite(value(output.geometry.vertices[corner][field])),"Semantic ZUV must remain finite");
    }
}

void semantic_zero_area_banner_is_rejected_by_default() {
    const auto command=semantic_input();
    failure(preflight(table(),{command}),FailureReason::empty_crop);
    failure(preflight(table(),{command},Policy{}),FailureReason::empty_crop);
}

void semantic_zero_area_banner_optin_preserves_cpu_bits_and_order() {
    auto first=input(),third=input();
    third.command.identity=77;
    auto middle=semantic_input();
    std::vector<CommandInput> inputs{first,middle,third};
    const auto before=snapshot(inputs);
    const auto result=preflight(table(),inputs,accept_semantic);
    const auto& outputs=ready(result).commands();
    require(outputs.size()==3,"Semantic opt-in must retain every command");
    require(outputs[0].coverage==Coverage::raster && outputs[2].coverage==Coverage::raster,"Finite commands stay raster");
    require(outputs[0].command.identity==first.command.identity && outputs[2].command.identity==third.command.identity,
        "Semantic opt-in must not reorder commands");
    require_semantic_bits(middle,outputs[1]);
    require(snapshot(inputs)==before,"Semantic opt-in must not mutate any input CPU bits");
}

void three_source_empty_strip_patterns_are_semantic_eligible_parameterized() {
    struct Strip { int frame_x,frame_y,frame_width,frame_height,crop_x,crop_y,crop_width; };
    for(const auto strip:{Strip{49,1934,17,20,49,1954,17},Strip{0,138,7,4,0,142,7},Strip{5,94,5,5,5,99,5}}) {
        MaterialTable materials;
        materials.pages={{7,64,32}};
        MaterialBinding binding;
        binding.original={"synthetic/sheet",strip.frame_x,strip.frame_y,strip.frame_width,strip.frame_height,
                          0,0,strip.frame_width,strip.frame_height,"synthetic/zero-area"};
        binding.original_sheet_width=1024;
        binding.original_sheet_height=2048;
        binding.page=7;
        binding.packed_x=4;binding.packed_y=8;
        binding.packed_width=strip.frame_width;binding.packed_height=strip.frame_height;
        materials.bindings.push_back(binding);
        decal_commands::DecalCommand command;
        command.identity=42;command.room="synthetic/room";command.texture="synthetic/zero-area";
        command.sheet="synthetic/sheet";command.source_x=strip.crop_x;command.source_y=strip.crop_y;
        command.source_width=strip.crop_width;command.source_height=0;command.slice=0;
        command.position={10,20};command.origin={2,3};command.scale={1,1};
        CommandInput input{command,decal_commands::project_geometry(command,1024,2048),
            Coverage::semantic_zero_area_banner};
        const auto result=preflight(materials,{input},accept_semantic);
        require_semantic_bits(input,ready(result).commands()[0]);
        require(ready(result).commands()[0].page==7,"Semantic strip must resolve the exact material page");
    }
}

void semantic_zero_area_invalid_claims_and_extreme_crop_bounds_block_frame_parameterized() {
    for(unsigned kind=0;kind<23;++kind) {
        auto command=semantic_input();
        FailureReason expected=FailureReason::invalid_crop;
        switch(kind) {
        case 0: command.command.slice=-1;break;
        case 1: command.command.source_width=0;expected=FailureReason::invalid_crop;break;
        case 2: command.command.source_height=1;break;
        case 3: command.command.source_width=0;command.command.source_height=0;break;
        case 4: command.command.position.x=std::numeric_limits<float>::infinity();expected=FailureReason::nonfinite_input;break;
        case 5: command.command.rotation=std::numeric_limits<float>::quiet_NaN();expected=FailureReason::nonfinite_input;break;
        case 6: command.geometry.vertices[0][2]=bits(std::numeric_limits<float>::infinity());expected=FailureReason::nonfinite_input;break;
        case 7: command.geometry.vertices[1][3]=bits(std::numeric_limits<float>::quiet_NaN());expected=FailureReason::nonfinite_input;break;
        case 8: command.geometry.vertices[2][4]=bits(std::numeric_limits<float>::infinity());expected=FailureReason::nonfinite_input;break;
        case 9: command.geometry.vertices[0][0]=bits(0.f);expected=FailureReason::invalid_geometry;break;
        case 10: command.geometry.vertices[3][1]=bits(std::numeric_limits<float>::infinity());expected=FailureReason::invalid_geometry;break;
        case 11: command.command.source_y=37;break;
        case 12: command.command.source_x=100;break;
        case 13: command.command.texture="synthetic/missing";expected=FailureReason::missing_material;break;
        case 14: command.command.sheet="synthetic/missing-sheet";expected=FailureReason::missing_material;break;
        case 15: command.geometry.vertices[1][0]=bits(0.f);expected=FailureReason::invalid_geometry;break;
        case 16: command.coverage=static_cast<Coverage>(99);expected=FailureReason::invalid_metadata;break;
        case 17: command.command.source_x=std::numeric_limits<int>::max();break;
        case 18: command.command.source_x=std::numeric_limits<int>::min();break;
        case 19: command.command.source_y=std::numeric_limits<int>::max();break;
        case 20: command.command.source_y=std::numeric_limits<int>::min();break;
        case 21: command.command.source_width=std::numeric_limits<int>::max();break;
        case 22: command.command.source_width=-1;break;
        }
        if(kind==1 || kind==2 || kind==3 || kind==11 || kind==12)
            command.geometry=decal_commands::project_geometry(command.command,128,64);
        const std::vector<CommandInput> inputs{command};
        const auto before=snapshot(inputs);
        MockSubmission gpu;
        const auto result=preflight(table(),inputs,accept_semantic);
        if(const auto* frame=std::get_if<ReadyFrame>(&result)) gpu.submit(*frame);
        const auto& error=failure(result,expected);
        require(gpu.count==0 && error.command_index==0,"Invalid semantic claim must block the frame before any submission");
        require(snapshot(inputs)==before,"Invalid semantic claim must not rewrite CPU payload bits");
    }
}

void late_invalid_semantic_blocks_prior_ready_semantic_atomically() {
    auto invalid=semantic_input();
    invalid.command.identity=123;
    invalid.command.source_width=0;
    invalid.geometry=decal_commands::project_geometry(invalid.command,128,64);
    std::vector<CommandInput> inputs{input(),semantic_input(),invalid};
    const auto before=snapshot(inputs);
    MockSubmission gpu;
    const auto result=preflight(table(),inputs,accept_semantic);
    if(const auto* frame=std::get_if<ReadyFrame>(&result)) gpu.submit(*frame);
    const auto& error=failure(result,FailureReason::invalid_crop);
    require(gpu.count==0 && error.command_index==2,"Late invalid semantics must stop every earlier raster and semantic command");
    require(snapshot(inputs)==before,"Atomic semantic failure must preserve every CPU bit");
}

void semantic_true_finite_flag_does_not_override_actual_nan_bits() {
    auto command=semantic_input();
    command.geometry.finite=true;
    const auto result=preflight(table(),{command},accept_semantic);
    require_semantic_bits(command,ready(result).commands()[0]);
}
}

int main() {
    try {
        const std::array tests{
            valid_trimmed_subrect_is_ready,
            source_uv_flips_and_corner_order_are_preserved,
            signed_zero_xyz_and_descriptor_bits_are_copied,
            successful_input_is_immutable_and_ready_output_is_owned,
            outline_passes_reuse_material_without_reordering,
            exact_alias_is_required_parameterized,
            sheet_is_part_of_material_key,
            explicitly_equivalent_alias_resolves_uniquely,
            ambiguous_parent_material_fails_before_frame_walk,
            equivalent_alias_collision_blocks_even_empty_frame,
            late_zero_height_blocks_entire_frame_and_preserves_cpu_bits,
            submission_can_consume_only_complete_ready_frame,
            geometry_nonfinite_bits_are_rejected_parameterized,
            descriptor_nonfinite_fields_are_rejected_parameterized,
            false_geometry_flag_blocks_frame,
            source_uv_outside_descriptor_is_rejected,
            empty_frame_is_ready_without_materials,
            late_missing_material_also_blocks_submission,
            late_infinity_blocks_submission_despite_true_finite_flag,
            unused_invalid_binding_blocks_otherwise_valid_frame,
            command_crop_bounds_are_checked_without_integer_overflow_parameterized,
            zero_extent_always_blocks_parameterized,
            rotated_and_rescaled_packing_are_explicitly_unsupported_parameterized,
            invalid_metadata_is_rejected_before_commands_parameterized,
            conflicting_sheet_dimensions_are_rejected,
            duplicate_identical_bindings_are_not_silently_deduplicated,
            duplicate_alias_within_binding_is_rejected,
            rgba_byte_estimate_overflow_blocks_frame,
            actual_page_dimensions_have_no_invented_gpu_limit,
            non_power_of_two_dimensions_map_source_bits_without_clamping,
            semantic_zero_area_banner_is_rejected_by_default,
            semantic_zero_area_banner_optin_preserves_cpu_bits_and_order,
            three_source_empty_strip_patterns_are_semantic_eligible_parameterized,
            semantic_zero_area_invalid_claims_and_extreme_crop_bounds_block_frame_parameterized,
            late_invalid_semantic_blocks_prior_ready_semantic_atomically,
            semantic_true_finite_flag_does_not_override_actual_nan_bits
        };
        for(auto test:tests) test();
        std::cout<<tests.size()<<" command preflight scenarios passed (including parameterized cases)\n";
        return 0;
    } catch(const std::exception& error) {
        std::cerr<<error.what()<<'\n';
        return 1;
    }
}
