#include "command_preflight.hpp"
#include <cmath>
#include <cstring>
#include <limits>
#include <unordered_map>

namespace celeste::command_preflight {
namespace {
using decal_commands::DecalCommand;

float value(std::int32_t bits) {
    float result;
    static_assert(sizeof(result)==sizeof(bits));
    std::memcpy(&result,&bits,sizeof(result));
    return result;
}

std::int32_t bits(float value) {
    std::int32_t result;
    std::memcpy(&result,&value,sizeof(result));
    return result;
}

bool contained(int x,int y,int width,int height,int left,int top,int outer_width,int outer_height) {
    return x>=left && y>=top && width>0 && height>0 &&
        std::int64_t(x)+width<=std::int64_t(left)+outer_width &&
        std::int64_t(y)+height<=std::int64_t(top)+outer_height;
}

bool contained_zero_height(int x,int y,int width,int left,int top,int outer_width,int outer_height) {
    return x>=left && y>=top && width>0 &&
        std::int64_t(x)+width<=std::int64_t(left)+outer_width &&
        std::int64_t(y)<=std::int64_t(top)+outer_height;
}

using AliasMap=std::unordered_map<std::string,std::unordered_map<std::string,std::size_t>>;

struct ResolvedMaterial {
    const MaterialBinding* binding=nullptr;
    FailureReason reason=FailureReason::missing_material;
    const char* detail="";
};

ResolvedMaterial resolve_material(const MaterialTable& table,const AliasMap& aliases,
                                  const std::string& sheet_name,const std::string& texture) {
    if(texture.empty()) return {nullptr,FailureReason::missing_material,"Missing exact frame alias and original sheet key"};
    const auto sheet=aliases.find(sheet_name);
    if(sheet==aliases.end()) return {nullptr,FailureReason::missing_material,"Missing exact frame alias and original sheet key"};
    const auto alias=sheet->second.find(texture);
    if(alias==sheet->second.end()) return {nullptr,FailureReason::missing_material,"Missing exact or explicitly equivalent frame alias"};
    return {&table.bindings[alias->second],FailureReason::missing_material,""};
}

Failure command_failure(FailureReason reason,std::size_t index,const DecalCommand& command,const char* detail) {
    return {reason,index,{},command.identity,command.texture,command.sheet,
        {command.source_x,command.source_y,command.source_width,command.source_height},detail};
}

Failure binding_failure(FailureReason reason,std::size_t index,const MaterialBinding& binding,const char* detail) {
    const auto& frame=binding.original;
    return {reason,{},index,0,frame.texture,frame.sheet,{frame.x,frame.y,frame.width,frame.height},detail};
}

bool finite(const DecalCommand& command) {
    for(const auto number:{command.position.x,command.position.y,command.origin.x,command.origin.y,
                          command.scale.x,command.scale.y,command.rotation})
        if(!std::isfinite(number)) return false;
    return true;
}
}

Result preflight(const MaterialTable& table,const std::vector<CommandInput>& commands) {
    return preflight(table,commands,Policy{});
}

Result preflight(const MaterialTable& table,const std::vector<CommandInput>& commands,const Policy& policy) {
    ReadyFrame ready;
    std::unordered_map<int,const Page*> pages;
    for(const auto& page:table.pages) {
        const auto invalid=[&](const char* detail) {
            return Failure{FailureReason::invalid_metadata,{},{},0,{},{},{},
                "Page "+std::to_string(page.id)+": "+detail};
        };
        if(page.id<0 || page.width<=0 || page.height<=0) return invalid("invalid ID or dimensions");
        if(!pages.emplace(page.id,&page).second) return invalid("duplicate ID");
        const auto width=std::size_t(page.width),height=std::size_t(page.height);
        const auto maximum=std::numeric_limits<std::size_t>::max();
        if(width>maximum/height || width*height>maximum/4) return invalid("RGBA byte size overflow");
        const auto bytes=width*height*4;
        if(ready.required_rgba_bytes_>maximum-bytes) return invalid("total RGBA byte size overflow");
        ready.required_rgba_bytes_+=bytes;
    }

    AliasMap aliases;
    std::unordered_map<std::string,std::pair<int,int>> sheet_dimensions;
    for(std::size_t index=0;index<table.bindings.size();++index) {
        const auto& binding=table.bindings[index];
        const auto& frame=binding.original;
        const auto fail=[&](FailureReason reason,const char* detail) {
            return binding_failure(reason,index,binding,detail);
        };
        if(frame.texture.empty() || frame.sheet.empty() ||
           binding.original_sheet_width<=0 || binding.original_sheet_height<=0 ||
           frame.frame_width<=0 || frame.frame_height<=0 ||
           !std::isfinite(frame.offset_x) || !std::isfinite(frame.offset_y) ||
           !contained(frame.x,frame.y,frame.width,frame.height,0,0,
                      binding.original_sheet_width,binding.original_sheet_height))
            return fail(FailureReason::invalid_metadata,"Invalid original frame/sheet metadata");
        const auto dimensions=std::make_pair(binding.original_sheet_width,binding.original_sheet_height);
        const auto inserted=sheet_dimensions.emplace(frame.sheet,dimensions);
        if(!inserted.second && inserted.first->second!=dimensions)
            return fail(FailureReason::invalid_metadata,"Incoherent original sheet dimensions");
        const auto page=pages.find(binding.page);
        if(page==pages.end()) return fail(FailureReason::invalid_metadata,"Unknown packed page ID");
        if(binding.rotated || binding.packed_width!=frame.width || binding.packed_height!=frame.height)
            return fail(FailureReason::unsupported_packing,"Only one-to-one unrotated packing is supported");
        if(!contained(binding.packed_x,binding.packed_y,binding.packed_width,binding.packed_height,
                      0,0,page->second->width,page->second->height))
            return fail(FailureReason::invalid_metadata,"Packed crop outside actual page dimensions");
        auto& sheet_aliases=aliases[frame.sheet];
        if(!sheet_aliases.emplace(frame.texture,index).second)
            return fail(FailureReason::ambiguous_material,"Duplicate/ambiguous original material key");
        for(const auto& alias:binding.equivalent_aliases) {
            if(alias.empty()) return fail(FailureReason::invalid_metadata,"Empty equivalent alias");
            if(!sheet_aliases.emplace(alias,index).second)
                return fail(FailureReason::ambiguous_material,"Duplicate/ambiguous equivalent alias");
        }
    }

    ready.commands_.reserve(commands.size());
    for(std::size_t index=0;index<commands.size();++index) {
        const auto& input=commands[index];
        const auto& command=input.command;
        const auto fail=[&](FailureReason reason,const char* detail) {
            return command_failure(reason,index,command,detail);
        };
        const auto raster_command=[&]() -> std::optional<Failure> {
            if(command.source_width==0 || command.source_height==0)
                return fail(FailureReason::empty_crop,"EMPTY_CROP blocks frame; Source EMPTY_RASTER is unknown");
            if(!finite(command)) return fail(FailureReason::nonfinite_input,"Nonfinite logical command field");
            const auto resolved=resolve_material(table,aliases,command.sheet,command.texture);
            if(!resolved.binding) return fail(resolved.reason,resolved.detail);
            const auto& binding=*resolved.binding;
            const auto& original=binding.original;
            if(!contained(command.source_x,command.source_y,command.source_width,command.source_height,
                          original.x,original.y,original.width,original.height))
                return fail(FailureReason::invalid_crop,"Command crop is not contained in its original parent frame");
            for(const auto& vertex:input.geometry.vertices)
                for(const auto field:vertex)
                    if(!std::isfinite(value(field)))
                        return fail(FailureReason::nonfinite_input,"Nonfinite source geometry bits");
            if(!input.geometry.finite) return fail(FailureReason::invalid_geometry,"Source geometry marked nonfinite");

            const auto& page=*pages.at(binding.page);
            ReadyCommand output{command,input.geometry,binding.page};
            for(auto& vertex:output.geometry.vertices) {
                for(unsigned axis=0;axis<2;++axis) {
                    const auto uv=value(vertex[3+axis]);
                    const int sheet_size=axis==0?binding.original_sheet_width:binding.original_sheet_height;
                    const int source=axis==0?command.source_x:command.source_y;
                    const int extent=axis==0?command.source_width:command.source_height;
                    const float low=float(source)/float(sheet_size);
                    const float high=low+float(extent)/float(sheet_size);
                    if(uv<low || uv>high)
                        return fail(FailureReason::invalid_geometry,"Source UV outside command crop");
                    const int parent=axis==0?original.x:original.y;
                    const int parent_size=axis==0?original.width:original.height;
                    const int packed=axis==0?binding.packed_x:binding.packed_y;
                    const int packed_size=axis==0?binding.packed_width:binding.packed_height;
                    const int page_size=axis==0?page.width:page.height;
                    const double local=(double(uv)*sheet_size-parent)/parent_size;
                    const float mapped=float((packed+local*packed_size)/page_size);
                    if(!std::isfinite(mapped)) return fail(FailureReason::nonfinite_output,"Nonfinite packed UV");
                    vertex[3+axis]=bits(mapped);
                }
            }
            ready.commands_.push_back(std::move(output));
            return std::nullopt;
        };

        if(policy.zero_area_banner==Policy::ZeroAreaBanner::reject) {
            if(const auto error=raster_command()) return *error;
            continue;
        }
        switch(input.coverage) {
        case Coverage::raster:
            if(const auto error=raster_command()) return *error;
            break;
        case Coverage::semantic_zero_area_banner: {
            if(command.slice<0 || command.source_width<=0 || command.source_height!=0)
                return fail(FailureReason::invalid_crop,
                    "Semantic zero-area Banner requires a banner slice, positive width and zero height");
            if(!finite(command)) return fail(FailureReason::nonfinite_input,"Nonfinite logical command field");
            const auto resolved=resolve_material(table,aliases,command.sheet,command.texture);
            if(!resolved.binding) return fail(resolved.reason,resolved.detail);
            const auto& binding=*resolved.binding;
            const auto& original=binding.original;
            if(!contained_zero_height(command.source_x,command.source_y,command.source_width,
                                      original.x,original.y,original.width,original.height))
                return fail(FailureReason::invalid_crop,"Command crop is not contained in its original parent frame");
            bool xy_is_nan=true,zuv_is_finite=true;
            for(const auto& vertex:input.geometry.vertices) {
                if(!std::isnan(value(vertex[0])) || !std::isnan(value(vertex[1]))) xy_is_nan=false;
                for(unsigned field=2;field<5;++field)
                    if(!std::isfinite(value(vertex[field]))) zuv_is_finite=false;
            }
            if(!xy_is_nan)
                return fail(FailureReason::invalid_geometry,
                    "Semantic zero-area Banner requires all source XY words to be NaN");
            if(!zuv_is_finite)
                return fail(FailureReason::nonfinite_input,"Nonfinite semantic ZUV bits");
            ready.commands_.push_back({command,input.geometry,binding.page,
                Coverage::semantic_zero_area_banner});
            break;
        }
        default:
            return fail(FailureReason::invalid_metadata,"Unknown command coverage");
        }
    }
    ready.pages_=table.pages;
    return ready;
}
}
