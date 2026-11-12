#include "material_table.hpp"
#include "asset_text.hpp"
#include <iostream>
#include <limits>
#include <stdexcept>

using namespace celeste;
namespace {
void require(bool condition,const char* message) {
    if(!condition) throw std::runtime_error(message);
}
command_preflight::MaterialTable fixture() {
    command_preflight::MaterialBinding b;
    b.original={"Synthetic",10,20,4,5,-2,-3,12,16,"synthetic/frame"};
    b.original_sheet_width=64;b.original_sheet_height=64;
    b.page=7;b.packed_x=1;b.packed_y=2;b.packed_width=4;b.packed_height=5;
    b.equivalent_aliases={"synthetic/alias"};
    return {{{7,32,32}},{b}};
}
void roundtrip_is_owned_and_deterministic() {
    const auto text=material_table::serialize(fixture());
    const auto table=material_table::parse(text,asset_text::checksum(text));
    require(material_table::serialize(table)==text,"Roundtrip must be canonical");
    require(table.bindings[0].original.x==10 && table.bindings[0].original.offset_y==-3,
            "Keep original crop and trim rather than packed geometry");
    require(table.bindings[0].equivalent_aliases[0]=="synthetic/alias","Keep explicit aliases");
}
void malformed_text_is_rejected_parameterized() {
    const auto text=material_table::serialize(fixture());
    for(const auto& bad:{std::string{},std::string("CSMT2\n0\n0\n"),text+"extra\n",
                         std::string("CSMT1\n65\n"),std::string("CSMT1\n-1\n"),
                         std::string("CSMT1\n01\n"),std::string("CSMT1\n2147483648\n"),
                         text.substr(0,text.size()-1),std::string(2*1024*1024+1,'x')}) {
        bool rejected=false;
        try { material_table::parse(bad,asset_text::checksum(bad)); }
        catch(const std::invalid_argument& error) {
            rejected=std::string(error.what()).find("Material table")!=std::string::npos;
        }
        require(rejected,"Malformed text must fail with context");
    }
}
void integrity_is_checked_before_parse() {
    const auto text=material_table::serialize(fixture());
    bool rejected=false;
    try { material_table::parse(text,asset_text::checksum(text)^1); }
    catch(const std::invalid_argument&) { rejected=true; }
    require(rejected,"Caller pin must be checked");
}
void unused_metadata_is_rejected_parameterized() {
    for(unsigned kind=0;kind<13;++kind) {
        auto table=fixture();
        auto& b=table.bindings[0];
        switch(kind) {
        case 0: table.pages.push_back(table.pages[0]);break;
        case 1: b.page=99;break;
        case 2: b.packed_x=31;break;
        case 3: b.packed_width=3;break;
        case 4: b.rotated=true;break;
        case 5: b.equivalent_aliases.push_back(b.equivalent_aliases[0]);break;
        case 6: b.equivalent_aliases={b.original.texture};break;
        case 7: b.original.width=std::numeric_limits<int>::max();break;
        case 8: b.original.offset_x=.5f;break;
        case 9: b.original.texture="synthetic/../bad";break;
        case 10: b.original.sheet="invalid sheet";break;
        case 11: table.bindings.push_back(b);break;
        case 12: table.pages[0].width=0;break;
        }
        bool rejected=false;
        try { material_table::serialize(table); }
        catch(const std::invalid_argument&) { rejected=true; }
        require(rejected,"Unused invalid metadata must fail before any frame");
    }
}
void parser_rejects_invalid_packed_metadata() {
    auto text=material_table::serialize(fixture());
    const auto position=text.find("64 64 7 1 2 4 5 0 1");
    require(position!=std::string::npos,"Synthetic row must exist");
    text.replace(position,19,"64 64 99 1 2 4 5 0 1");
    bool rejected=false;
    try { material_table::parse(text,asset_text::checksum(text)); }
    catch(const std::invalid_argument&) { rejected=true; }
    require(rejected,"Parser must validate metadata, not only its syntax");
}
void page_dimensions_are_not_a_gpu_capacity_claim() {
    auto table=fixture();table.pages[0].width=8192;
    const auto text=material_table::serialize(table);
    const auto loaded=material_table::parse(text,asset_text::checksum(text));
    const auto result=command_preflight::preflight(loaded,{});
    require(std::get<command_preflight::ReadyFrame>(result).required_rgba_bytes()==8192*32*4,
            "Only actual submitted RGBA estimate is available");
}
void untrusted_unused_rows_are_rejected_parameterized() {
    const std::string header="CSMT1\n1\n7 32 32\n1\n";
    const std::string frame="Synthetic 10 20 4 5 -2 -3 12 16 synthetic/frame\n";
    for(const auto& bad:{
        std::string("CSMT1\n2\n7 32 32\n7 32 32\n0\n"),
        std::string("CSMT1\n2\n7 2147483647 2147483647\n8 2147483647 2147483647\n0\n"),
        header+"64 64 99 1 2 4 5 0 0\n"+frame,
        header+"64 64 7 31 2 4 5 0 0\n"+frame,
        header+"64 64 7 1 2 4 5 1 0\n"+frame,
        header+"64 64 7 1 2 4 5 0 2\n"+frame+"synthetic/alias\nsynthetic/alias\n",
        header+"64 64 7 1 2 4 5 0 1\n"+frame+"synthetic/frame\n",
        header+"64 64 7 1 2 4 5 0 0\nSynthetic 4095 20 4 5 -2 -3 12 16 synthetic/frame\n",
        header+"64 64 7 1 2 4 5 0 0\nSynthetic 10 20 4 5 0.5 -3 12 16 synthetic/frame\n"}) {
        bool rejected=false;
        try { material_table::parse(bad,asset_text::checksum(bad)); }
        catch(const std::invalid_argument&) { rejected=true; }
        require(rejected,"Untrusted unused rows must be validated, including arithmetic bounds");
    }
}
}
int main() {
    try {
        roundtrip_is_owned_and_deterministic();malformed_text_is_rejected_parameterized();
        integrity_is_checked_before_parse();unused_metadata_is_rejected_parameterized();
        parser_rejects_invalid_packed_metadata();page_dimensions_are_not_a_gpu_capacity_claim();
        untrusted_unused_rows_are_rejected_parameterized();
        std::cout<<"7 material table scenarios passed (including parameterized cases)\n";
    } catch(const std::exception& error) { std::cerr<<error.what()<<'\n';return 1; }
}
