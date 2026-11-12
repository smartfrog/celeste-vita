#include "assets.hpp"
#include <iostream>
#include <stdexcept>

using namespace celeste;
using namespace celeste::diagnostic;
namespace {
void require(bool value,const char* message) { if(!value) throw std::runtime_error(message); }
const std::string first="1 0 0 320 180 49 19 144 ";
const std::string second="2 240 -184 320 180 50 264 -24 0\n";
void valid_catalog_preserves_all_object_types() {
    const auto catalog=parse_room_catalog("CROOM1 2\n"+first+"5\n"
        "spike_up 0 64 144 8\nspike_left 1 300 128 16\njump_thru 2 24 80 40\n"
        "spring 3 32 144 0\nstrawberry 4 80 100 0\n"+second);
    require(catalog.first().name=="1" && catalog.first().load_seed==49 && catalog.first().spawn.y==144,
        "First-room fields must survive parsing");
    require(catalog.definitions()[1].bounds.y==-184 && catalog.definitions()[1].bounds.height==180 &&
        catalog.at({264,-24})==&catalog.definitions()[1],"Normalized second room must retain its gap");
    const auto& objects=catalog.first().objects;
    require(objects.size()==5 && objects[0].kind==RoomObjectKind::spike_up && objects[1].kind==RoomObjectKind::spike_left &&
        objects[2].kind==RoomObjectKind::jump_thru && objects[3].kind==RoomObjectKind::spring && objects[4].kind==RoomObjectKind::strawberry &&
        objects[2].id==2 && objects[2].position.y==80 && objects[2].size==40,"All bounded object tokens must retain their fields");
}
void whitespace_and_empty_objects_remain_accepted() {
    const auto catalog=parse_room_catalog(" \tCROOM1\n2\n"+first+"0\n"+second+" \t\n");
    require(catalog.first().objects.empty(),"Legacy formatted-stream whitespace must remain accepted");
}
void maximum_object_count_remains_accepted() {
    std::string text="CROOM1 2\n"+first+"32\n";
    for(int id=0;id<32;++id) text+="strawberry "+std::to_string(id)+" 80 100 0\n";
    require(parse_room_catalog(text+second).first().objects.size()==32,"Inclusive bounded object limit must parse");
}
void invalid_catalogs_reject_parameterized() {
    for(const auto& text:std::vector<std::string>{
        "", "CROOM2 2\n"+first+"0\n"+second, "CROOM1 1\n"+first+"0\n",
        "CROOM1 3\n"+first+"0\n"+second, "CROOM1 2147483648\n",
        "CROOM1 2\n"+first+"-1\n"+second, "CROOM1 2\n"+first+"33\n"+second,
        "CROOM1 2\n"+first+"1\nunknown 0 0 0 8\n"+second,
        "CROOM1 2\n"+first+"1\nspike_up 0 64", "CROOM1 2\n"+first+"0\n",
        "CROOM1 2\n"+first+"0\n"+second+"trailing",
        "CROOM1 2\n1 2147483648 0 320 180 49 19 144 0\n"+second,
        "CROOM1 2\n1 2147483647 0 320 180 49 19 144 0\n"+second,
        "CROOM1 2\n1 0 -2147483648 320 180 49 19 144 0\n"+second,
        "CROOM1 2\n1 0 0 320 184 49 19 144 0\n"+second,
        "CROOM1 2\n1 0 0 320 180 2147483648 19 144 0\n"+second,
        "CROOM1 2\n1 0 0 320 180 49 nan 144 0\n"+second,
        "CROOM1 2\n1 0 0 320 180 49 1e999 144 0\n"+second,
        "CROOM1 2\n1 0 0 320 180 49 320 144 0\n"+second,
        "CROOM1 2\n"+first+"1\nspike_up -1 64 144 8\n"+second,
        "CROOM1 2\n"+first+"1\nspike_up 0 inf 144 8\n"+second,
        "CROOM1 2\n"+first+"1\nspike_up 0 64 1e999 8\n"+second,
        "CROOM1 2\n"+first+"1\nspike_up 0 64 144 2147483648\n"+second,
        "CROOM1 2\n"+first+"1\nspike_up 0 64 144 7\n"+second,
        "CROOM1 2\n"+first+"1\nspike_up 0 64 144 144\n"+second,
        "CROOM1 2\n"+first+"2\nstrawberry 0 64 144 0\nstrawberry 0 80 144 0\n"+second,
        "CROOM1 2\n"+first+"0\n1 240 -184 320 180 50 264 -24 0\n",
        std::string(65'537,' ')}) {
        try { parse_room_catalog(text); }
        catch(const std::invalid_argument&) { continue; }
        throw std::runtime_error("Invalid bounded room catalog must fail loudly");
    }
}
}
int main(int argc,char** argv) {
    try {
        if(argc==2) {
            const auto catalog=parse_room_catalog(read_asset(argv[1],65'536));
            require(catalog.definitions().size()==2,"Pinned catalog must remain bounded");
            std::cout<<"existing catalog parsed rooms=2 objects="<<catalog.definitions()[0].objects.size()+catalog.definitions()[1].objects.size()<<'\n';
            return 0;
        }
        if(argc!=1) throw std::invalid_argument("Expected optional existing room catalog");
        valid_catalog_preserves_all_object_types();
        whitespace_and_empty_objects_remain_accepted();
        maximum_object_count_remains_accepted();
        invalid_catalogs_reject_parameterized();
        std::cout<<"4 bounded room catalog behaviors passed\n";
    } catch(const std::exception& error) { std::cerr<<error.what()<<'\n';return 1; }
}
