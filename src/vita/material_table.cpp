#include "material_table.hpp"
#include "atlas_frame_text.hpp"
#include <array>
#include <cmath>
#include <locale>
#include <sstream>

namespace celeste::material_table {
namespace {
int count(std::string_view text,int maximum) {
    const auto value=asset_text::integer(text);
    if(value<0 || value>maximum) throw std::invalid_argument("Count outside schema bound");
    return value;
}
template<std::size_t N> std::array<int,N> numbers(std::string_view row) {
    std::array<int,N> result{};
    for(std::size_t i=0;i<N;++i)
        result[i]=asset_text::integer(i+1==N?row:asset_text::take(row,' '));
    return result;
}
void validate(const command_preflight::MaterialTable& table) {
    if(table.pages.size()>64 || table.bindings.size()>4096)
        throw std::invalid_argument("Count outside schema bound");
    std::size_t aliases=0;
    for(const auto& binding:table.bindings) {
        atlas_frame_text::validate(binding.original);
        if(binding.original.offset_x!=std::trunc(binding.original.offset_x) ||
           binding.original.offset_y!=std::trunc(binding.original.offset_y))
            throw std::invalid_argument("Noninteger atlas offset");
        if(binding.original_sheet_width>4096 || binding.original_sheet_height>4096 ||
           binding.equivalent_aliases.size()>64)
            throw std::invalid_argument("Sheet or alias count outside schema bound");
        aliases+=binding.equivalent_aliases.size();
        if(aliases>4096) throw std::invalid_argument("Total aliases outside schema bound");
        for(const auto& alias:binding.equivalent_aliases)
            if(!atlas_frame_text::identity(alias)) throw std::invalid_argument("Invalid equivalent alias");
    }
    const auto result=command_preflight::preflight(table,{});
    if(const auto* error=std::get_if<command_preflight::Failure>(&result))
        throw std::invalid_argument((error->binding_index?"Binding "+std::to_string(*error->binding_index)+": ":"")+error->detail);
}
}

command_preflight::MaterialTable parse(std::string_view text,std::uint32_t expected_checksum) {
    std::string context="header";
    try {
        asset_text::integrity(text,maximum_text_bytes,expected_checksum);
        if(asset_text::take(text)!="CSMT1") throw std::invalid_argument("Unsupported version");
        command_preflight::MaterialTable table;
        const auto pages=count(asset_text::take(text),64);
        for(int i=0;i<pages;++i) {
            context="page "+std::to_string(i);
            const auto row=numbers<3>(asset_text::take(text));
            table.pages.push_back({row[0],row[1],row[2]});
        }
        context="binding count";
        const auto bindings=count(asset_text::take(text),4096);
        std::size_t aliases=0;
        for(int i=0;i<bindings;++i) {
            context="binding "+std::to_string(i);
            const auto row=numbers<9>(asset_text::take(text));
            if(row[7]!=0 || row[8]<0 || row[8]>64)
                throw std::invalid_argument("Unsupported rotation or alias count");
            aliases+=std::size_t(row[8]);
            if(aliases>4096) throw std::invalid_argument("Total aliases outside schema bound");
            command_preflight::MaterialBinding binding;
            binding.original_sheet_width=row[0];binding.original_sheet_height=row[1];
            binding.page=row[2];binding.packed_x=row[3];binding.packed_y=row[4];
            binding.packed_width=row[5];binding.packed_height=row[6];
            binding.original=atlas_frame_text::parse(asset_text::take(text));
            for(int j=0;j<row[8];++j) binding.equivalent_aliases.emplace_back(asset_text::take(text));
            table.bindings.push_back(std::move(binding));
        }
        if(!text.empty()) throw std::invalid_argument("Trailing data");
        context="metadata";
        validate(table);
        return table;
    } catch(const std::invalid_argument& error) {
        throw std::invalid_argument("Material table "+context+": "+error.what());
    }
}

std::string serialize(const command_preflight::MaterialTable& table) {
    try {
        validate(table);
        std::ostringstream out;
        out.imbue(std::locale::classic());
        out<<"CSMT1\n"<<table.pages.size()<<'\n';
        for(const auto& page:table.pages) out<<page.id<<' '<<page.width<<' '<<page.height<<'\n';
        out<<table.bindings.size()<<'\n';
        for(const auto& b:table.bindings) {
            out<<b.original_sheet_width<<' '<<b.original_sheet_height<<' '<<b.page<<' '
               <<b.packed_x<<' '<<b.packed_y<<' '<<b.packed_width<<' '<<b.packed_height
               <<" 0 "<<b.equivalent_aliases.size()<<'\n';
            const auto& f=b.original;
            out<<f.sheet<<' '<<f.x<<' '<<f.y<<' '<<f.width<<' '<<f.height<<' '
               <<int(f.offset_x)<<' '<<int(f.offset_y)<<' '<<f.frame_width<<' '<<f.frame_height<<' '<<f.texture<<'\n';
            for(const auto& alias:b.equivalent_aliases) out<<alias<<'\n';
        }
        const auto text=out.str();
        if(text.size()>maximum_text_bytes) throw std::invalid_argument("Text exceeds schema bound");
        return text;
    } catch(const std::invalid_argument& error) {
        throw std::invalid_argument(std::string("Material table serialization: ")+error.what());
    }
}
}
