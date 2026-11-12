#pragma once
#include "command_preflight.hpp"
#include <cstdint>
#include <string_view>

namespace celeste::material_table {
constexpr std::size_t maximum_text_bytes=2*1024*1024;
// CSMT1 stores metadata only. The caller pins integrity and owns page IO/lifetime.
command_preflight::MaterialTable parse(std::string_view text,std::uint32_t expected_checksum);
std::string serialize(const command_preflight::MaterialTable& table);
}
