#pragma once
#include <cstdio>
#include <stdexcept>
#include <string>

namespace celeste::diagnostic {
inline FILE* open_app_log(const char* path) {
    if(!path || !*path) throw std::invalid_argument("Normal app log requires its claimed path");
    auto* stream=std::fopen(path,"a");
    if(!stream) throw std::runtime_error(std::string("Normal app log open failed: ")+path);
    if(std::setvbuf(stream,nullptr,_IOFBF,4096)) {
        const auto closed=std::fclose(stream);
        throw std::runtime_error(std::string("Normal app log buffer setup failed: ")+path+(closed ? "; cleanup close failed" : ""));
    }
    return stream;
}
inline void finish_app_log_line(FILE* stream,const char* path,int formatted) {
    if(!stream) throw std::runtime_error(std::string("Normal app log is not open: ")+path);
    if(formatted<0) throw std::runtime_error(std::string("Normal app log format failed: ")+path);
    if(std::fputc('\n',stream)==EOF) throw std::runtime_error(std::string("Normal app log newline failed: ")+path);
    if(std::fflush(stream)) throw std::runtime_error(std::string("Normal app log flush failed: ")+path);
}
inline void close_app_log(FILE*& stream,const char* path) {
    if(!stream) return;
    auto* owned=stream;stream=nullptr;
    if(std::fclose(owned)) throw std::runtime_error(std::string("Normal app log close failed: ")+path);
}
}
