#pragma once

#include <psp2/io/fcntl.h>
#include <psp2/io/stat.h>
#include <sys/errno.h>
#include <stdexcept>
#include <string>
#include <string_view>

namespace celeste::diagnostic {
inline bool guest_file_exists(const char* path) {
    SceIoStat status{};
    const auto result = sceIoGetstat(path,&status);
    if (result >= 0) return true;
    if ((result & 0xffff) == ENOENT) return false;
    throw std::runtime_error(std::string("Guest output stat failed: ")+path+" code="+std::to_string(result));
}
inline bool guest_capture_exists(const char* path) {
    const auto receipt = std::string(path)+".txt";
    const bool image = guest_file_exists(path);
    const bool saved = guest_file_exists(receipt.c_str());
    return image || saved;
}
inline void write_guest_file(const char* path, std::string_view data, int creation_flags) {
    if (data.size() > 2*1024*1024) throw std::invalid_argument("Guest output exceeds bounded diagnostic IO size");
    const auto file = sceIoOpen(path,SCE_O_WRONLY|SCE_O_CREAT|creation_flags,0666);
    if (file < 0) throw std::runtime_error(std::string("Guest output open failed: ")+path+" code="+std::to_string(file));
    const auto written = sceIoWrite(file,data.data(),static_cast<SceSize>(data.size()));
    const auto closed = sceIoClose(file);
    if (written != static_cast<SceSSize>(data.size()) || closed < 0)
        throw std::runtime_error(std::string("Guest output write/close failed: ")+path+" write="+std::to_string(written)+" close="+std::to_string(closed));
}
}
