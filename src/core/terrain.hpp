#pragma once
#include "movement.hpp"
#include <array>
#include <functional>
#include <string>
#include <string_view>

namespace celeste::terrain {
struct Sheet { std::string name; int width=0,height=0; };
struct Material {
    std::string source;
    int sheet=0,u=0,v=0,width=8,height=8;
};
struct Command { unsigned material=0; Vec2 position{}; };
struct Window {
    int left=0,top=0,right=0,bottom=0;
    bool outside_catalog=false;
};
class Catalog final {
public:
    const std::vector<Sheet>& sheets() const { return sheets_; }
    const std::vector<Material>& materials() const { return materials_; }
    const std::array<std::string,4>& provenance() const { return provenance_; }
    Window window(Vec2 camera,Vec2 viewport={320,180}) const;
    Window project(bool background,Vec2 camera,Vec2 viewport,const std::function<void(const Command&)>& emit) const;
private:
    Catalog()=default;
    friend Catalog parse(std::string_view,std::uint32_t);
    int x_=0,y_=0,columns_=0,rows_=0;
    std::array<std::string,4> provenance_;
    std::vector<Sheet> sheets_;
    std::vector<Material> materials_;
    std::array<std::vector<unsigned>,2> cells_;
};
inline constexpr std::size_t catalog_byte_limit=32'000'000;
Catalog parse(std::string_view text,std::uint32_t expected_checksum);
}
