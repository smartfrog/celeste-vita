#include "material_table.hpp"
#include "asset_text.hpp"
#include <iostream>
#include <iterator>
#include <stdexcept>
#include <string>

int main() {
    try {
        std::string text{std::istreambuf_iterator<char>(std::cin),std::istreambuf_iterator<char>()};
        const auto table=celeste::material_table::parse(text,celeste::asset_text::checksum(text));
        std::cout<<"CSMT1 pages="<<table.pages.size()<<" bindings="<<table.bindings.size()<<'\n';
        return 0;
    } catch(const std::exception& error) {
        std::cerr<<error.what()<<'\n';
        return 1;
    }
}
