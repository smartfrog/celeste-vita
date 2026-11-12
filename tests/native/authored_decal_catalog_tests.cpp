#include "assets.hpp"
#include <iostream>
#include <stdexcept>

using namespace celeste;
using namespace celeste::diagnostic;
namespace {
void require(bool condition,const char* message) { if(!condition) throw std::runtime_error(message); }
const std::string header="CDO1\nfd73f8a2311fa5737ded550cbad4b75c85b7686b36432f59185e940fcb65fcfe\n"
    "ace1892261c03aa766f45aaa38cb2cd60a8823c34eda673f5b2ed8ab31c890ab\n"
    "81d04a56cb9b5cb981f3c7823388bed6082db2d5755d364c15c35bbcaf8b7746\n6000000000000000\n2\n";
std::string metadata() {
    return header+"R 1 0 0 320 180 184 1 1\nB 0 test\\static.png 10 20 1 -1 0\nF 0 test/banner.png 30 40 -1 1 1\n"
        "R 2 240 -184 320 180 184 1 0\nB 0 test/static.png 250 -170 1 1 0\n";
}
RoomCatalog rooms() { return RoomCatalog({{"1",{0,0,320,180},49,{19,144},{}},
    {"2",{240,-184,320,180},50,{264,-24},{}}}); }
std::string replaced(std::string text,const std::string& old,const std::string& value) {
    const auto at=text.find(old);
    require(at!=std::string::npos,"Mutation target absent");
    text.replace(at,old.size(),value);return text;
}
void rejects(const std::string& text) {
    try { parse_authored_decals(text,checksum(text),rooms()); }
    catch(const std::invalid_argument&) { return; }
    throw std::runtime_error("Malformed authored metadata accepted");
}
void preserves_authored_metadata() {
    const auto catalog=rooms();const auto text=metadata();
    const auto result=parse_authored_decals(text,checksum(text),catalog);
    require(result.size()==2 && result[0].owners.size()==2 && result[1].owners.size()==1,"Owner counts changed");
    const auto& owner=result[0].owners[0];
    require(owner.texture=="test\\static.png" && owner.position.x==10 && owner.position.y==20 && owner.scale.y==-1,
        "Original texture/transform was not retained");
    require(result[0].owners[1].banner && result[1].owners[0].room==&catalog.definitions()[1],"Banner or room binding changed");
    require(owner.identity!=result[0].owners[1].identity && owner.identity!=result[1].owners[0].identity,
        "Room/layer identity namespaces alias");
}
void rejects_wrong_integrity() {
    const auto text=metadata();
    try { parse_authored_decals(text,checksum(text)^1,rooms()); }
    catch(const std::invalid_argument&) { return; }
    throw std::runtime_error("Wrong metadata integrity accepted");
}
}
int main() {
    try {
        preserves_authored_metadata();
        rejects_wrong_integrity();
        const std::vector<std::pair<std::string,std::string>> mutations{
            {"CDO1","CDO2"},{"6000000000000000","5000000000000000"},
            {"81d04a56","01d04a56"},{"\n2\n","\n1\n"},
            {"R 2 240","R 1 240"},{"R 2 240","R 3 240"},
            {"320 180 184 1 0","320 184 184 1 0"},
            {"B 0 test/static.png","X 0 test/static.png"},
            {"B 0 test/static.png","B 1 test/static.png"},
            {"F 0 test/banner.png","B 0 test/banner.png"},
            {"184 1 1","184 2 1"},{"184 1 1","184 -1 1"},
            {"250 -170","1000001 -170"},{"1 -1 0","1 0 0"},
            {"-1 1 1","-1 1 2"},{"test/banner.png","../escape.png"},
            {"B 0 test/static.png 250 -170 1 1 0\n",""}};
        for(const auto& mutation:mutations) rejects(replaced(metadata(),mutation.first,mutation.second));
        rejects(metadata()+"extra\n");
        std::cout<<"20 authored decal catalog behaviors passed\n";
        return 0;
    } catch(const std::exception& error) { std::cerr<<error.what()<<'\n';return 1; }
}
