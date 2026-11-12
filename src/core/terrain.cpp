#include "terrain.hpp"
#include "asset_text.hpp"
#include <algorithm>
#include <cmath>
#include <map>
#include <set>
#include <utility>

namespace celeste::terrain {
namespace {
using asset_text::take;
using asset_text::integer;
bool identity(std::string_view name) {
    return !name.empty() && name.size()<=192 && name.front()!='/' &&
        name.find_first_not_of("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_/-")==std::string_view::npos;
}
int bounded(std::string_view text,int low,int high) {
    const int value=integer(text);
    if(value<low || value>high) throw std::invalid_argument("Terrain field out of range");
    return value;
}
}
Catalog parse(std::string_view text,std::uint32_t expected_checksum) {
    asset_text::integrity(text,catalog_byte_limit,expected_checksum);
    if(take(text)!="CSTV1") throw std::invalid_argument("Wrong terrain catalog version");
    Catalog result;
    for(auto& pin:result.provenance_) {
        const auto value=take(text);
        if(value.size()!=64 || value.find_first_not_of("0123456789abcdef")!=std::string_view::npos)
            throw std::invalid_argument("Invalid terrain provenance pin");
        pin=value;
    }
    auto row=take(text);
    result.x_=bounded(take(row,' '),-1'000'000,1'000'000);
    result.y_=bounded(take(row,' '),-1'000'000,1'000'000);
    result.columns_=bounded(take(row,' '),1,4096);
    result.rows_=bounded(take(row,' '),1,4096);
    if(integer(take(row,' '))!=8 || integer(row)!=1)
        throw std::invalid_argument("Terrain requires tile size 8 and visual extension 1");
    const auto area=std::size_t(result.columns_)*result.rows_;
    if(area>4'000'000) throw std::invalid_argument("Terrain grid exceeds cell bound");
    const int sheets=bounded(take(text),1,16);
    std::set<std::string> sheet_names;
    for(int i=0;i<sheets;++i) {
        row=take(text);
        Sheet sheet;
        sheet.name=take(row,' ');
        sheet.width=bounded(take(row,' '),8,16384);sheet.height=bounded(row,8,16384);
        if(!identity(sheet.name) || !sheet_names.insert(sheet.name).second)
            throw std::invalid_argument("Invalid or duplicate terrain sheet");
        result.sheets_.push_back(std::move(sheet));
    }
    const int materials=bounded(take(text),1,65536);
    std::set<std::string> descriptors;
    std::map<std::string,int> source_sheets;
    for(int i=0;i<materials;++i) {
        row=take(text);
        if(!descriptors.insert(std::string(row)).second) throw std::invalid_argument("Duplicate terrain material");
        Material material;
        material.source=take(row,' ');
        material.sheet=bounded(take(row,' '),0,sheets-1);
        const auto& sheet=result.sheets_[material.sheet];
        material.u=bounded(take(row,' '),0,sheet.width-8);
        material.v=bounded(take(row,' '),0,sheet.height-8);
        if(!identity(material.source)) throw std::invalid_argument("Invalid terrain source identity");
        const auto previous=source_sheets.emplace(material.source,material.sheet);
        if(!previous.second && previous.first->second!=material.sheet)
            throw std::invalid_argument("Terrain source spans inconsistent sheets");
        for(const int expected:{8,8,0,0,8,8,255,255,255,255})
            if(integer(take(row,' '))!=expected) throw std::invalid_argument("Unsupported terrain geometry/color");
        if(integer(row)!=1) throw std::invalid_argument("Terrain alpha must be one");
        result.materials_.push_back(std::move(material));
    }
    if(integer(take(text))!=2) throw std::invalid_argument("Expected two terrain layers");
    std::vector<bool> used(materials);
    for(int layer=0;layer<2;++layer) {
        row=take(text);
        if(take(row,' ')!=(layer==0?"B":"F") || integer(take(row,' '))!=(layer==0?10000:-10000))
            throw std::invalid_argument("Invalid terrain layer/depth/order");
        const int count=bounded(row,0,int(area));
        auto& cells=result.cells_[layer];cells.resize(area);
        std::pair<int,int> previous{-1,-1};
        for(int i=0;i<count;++i) {
            row=take(text);
            const int x=bounded(take(row,' '),0,result.columns_-1),y=bounded(take(row,' '),0,result.rows_-1);
            const int material=bounded(row,0,materials-1);
            const auto cell=std::make_pair(x,y);
            if(cell<=previous) throw std::invalid_argument("Duplicate or unordered terrain cell");
            previous=cell;
            cells[std::size_t(x)*result.rows_+y]=unsigned(material+1);
            used[material]=true;
        }
    }
    if(!text.empty()) throw std::invalid_argument("Trailing terrain catalog data");
    if(std::find(used.begin(),used.end(),false)!=used.end()) throw std::invalid_argument("Unused terrain material");
    return result;
}
Window Catalog::window(Vec2 camera,Vec2 viewport) const {
    if(!std::isfinite(camera.x) || !std::isfinite(camera.y) || !std::isfinite(viewport.x) || !std::isfinite(viewport.y) ||
        viewport.x<=0 || viewport.y<=0) throw std::invalid_argument("Terrain camera and positive viewport must be finite");
    const float left=std::floor(camera.x),top=std::floor(camera.y);
    const float right=left+viewport.x,bottom=top+viewport.y;
    if(!std::isfinite(right) || !std::isfinite(bottom)) throw std::invalid_argument("Terrain camera edge overflow");
    const auto clamp=[](double value,int maximum) { return int(std::clamp(value,0.0,double(maximum))); };
    return {clamp(std::floor((left-x_)/8.f)-1,columns_),clamp(std::floor((top-y_)/8.f)-1,rows_),
        clamp(std::ceil((right-x_)/8.f)+1,columns_),clamp(std::ceil((bottom-y_)/8.f)+1,rows_),
        left<x_ || top<y_ || right>x_+columns_*8 || bottom>y_+rows_*8};
}
Window Catalog::project(bool background,Vec2 camera,Vec2 viewport,const std::function<void(const Command&)>& emit) const {
    if(!emit) throw std::invalid_argument("Terrain projection requires a command consumer");
    const auto clipped=window(camera,viewport);
    const auto& cells=cells_[background?0:1];
    for(int x=clipped.left;x<clipped.right;++x) for(int y=clipped.top;y<clipped.bottom;++y) {
        const auto material=cells[std::size_t(x)*rows_+y];
        if(material) emit({material-1,{float(x_+x*8),float(y_+y*8)}});
    }
    return clipped;
}
}
