#pragma once
#include <cstdio>
#include <stdexcept>
#include <string>

namespace celeste::diagnostic {
template<unsigned Bound,class... Args> std::string bounded_guest_record(const char* error,const char* format,Args... args) {
    char text[Bound];
    const auto length=std::snprintf(text,sizeof(text),format,args...);
    if(length<0 || length>=static_cast<int>(sizeof(text))) throw std::runtime_error(error);
    return std::string(text,length);
}
}
