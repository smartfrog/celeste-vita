#pragma once
#include <charconv>
#include <cstdint>
#include <stdexcept>
#include <string>
#include <string_view>

namespace celeste::asset_text {
inline std::string_view take(std::string_view& text,char separator='\n') {
    const auto end=text.find(separator);
    if(end==std::string_view::npos) throw std::invalid_argument("Truncated asset field");
    const auto field=text.substr(0,end);
    text.remove_prefix(end+1);
    return field;
}
inline int integer(std::string_view text) {
    int value=0;
    const auto parsed=std::from_chars(text.data(),text.data()+text.size(),value);
    if(parsed.ec!=std::errc{} || parsed.ptr!=text.data()+text.size() || std::to_string(value)!=text)
        throw std::invalid_argument("Invalid or noncanonical asset integer");
    return value;
}
inline std::uint32_t checksum(std::string_view text) {
    std::uint32_t hash=2166136261u;
    for(unsigned char byte:text) hash=(hash^byte)*16777619u;
    return hash;
}
inline void integrity(std::string_view text,std::size_t limit,std::uint32_t expected) {
    if(text.size()>limit || checksum(text)!=expected)
        throw std::invalid_argument("Asset exceeds bound or fails build-pinned FNV-1a integrity");
}
}
