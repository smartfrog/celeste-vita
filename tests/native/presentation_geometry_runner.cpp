#include "assets.hpp"
#include "presentation_trace.hpp"

using namespace celeste;
using namespace celeste::diagnostic;
using namespace native_test;

int main(int argc,char** argv) {
    try {
        if(argc!=2) throw std::invalid_argument("Expected private player bank path");
        const auto bytes=read_asset(argv[1],65'536);
        const auto assets=parse_player_assets(bytes,checksum(bytes));
        const auto& bank=assets.bank;
        const std::array<unsigned,3> frames{bank.animation("idle").frames.front(),bank.bangs[0],bank.hair};
        unsigned index=0;
        for(int facing:{-1,1}) for(float rotation:{0.f,0.37f}) for(unsigned role=0;role<frames.size();++role) {
            const auto scale=role==0 ? Vec2{float(facing)*0.6f,1.4f} : role==1 ? Vec2{float(facing)*0.6f,1} : Vec2{0.375f,0.625f};
            const PlayerDraw draw{frames[role],{20.75f,-5.125f},role==0 ? Vec2{16,32} : Vec2{5,5},scale,rotation,
                                  role==0 ? PresentationColor{} : PresentationColor{172,50,50,255}};
            print_player_draw("geometry",1,index++,bank,draw);
        }
        return 0;
    } catch(const std::exception& error) {std::cerr<<error.what()<<'\n';return 1;}
}
