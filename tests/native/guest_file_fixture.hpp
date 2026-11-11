#pragma once
#include "guest_io.hpp"
#include <map>

namespace guest_test {
struct StoredFile {std::string data;};
struct OpenFile {std::string path,data;};
inline std::map<std::string,StoredFile> stored;
inline std::map<SceUID,OpenFile> open_files;
inline int next_fd=10,stat_error=0,write_error=0,close_error=0,open_error=0;
inline std::string stat_fail_path,race_path;
inline unsigned fail_open=0,opens=0,closes=0,stats=0;
inline int last_open_flags=0;
inline constexpr int error(int code) {return static_cast<int>(0x80010000u | static_cast<unsigned>(code));}
inline void reset() {
    stored.clear();open_files.clear();next_fd=10;
    stat_error=write_error=close_error=open_error=0;
    stat_fail_path.clear();race_path.clear();fail_open=opens=closes=stats=0;last_open_flags=0;
}
}
extern "C" inline int sceIoGetstat(const char* path,SceIoStat*) {
    using namespace guest_test;
    ++stats;
    if(stat_error && (stat_fail_path.empty() || stat_fail_path==path)) return stat_error;
    return stored.find(path)==stored.end() ? error(2) : 0;
}
extern "C" inline SceUID sceIoOpen(const char* path,int flags,SceMode) {
    using namespace guest_test;
    ++opens;last_open_flags=flags;
    if(race_path==path) stored[path]={"racing-writer-bytes"};
    if(open_error && opens==fail_open) return open_error;
    const auto found=stored.find(path);
    if((flags&SCE_O_EXCL) && found!=stored.end()) return error(17);
    if(!(flags&SCE_O_CREAT) && found==stored.end()) return error(2);
    const int fd=next_fd++;
    open_files[fd]={path,(flags&SCE_O_TRUNC) || found==stored.end() ? "" : found->second.data};
    return fd;
}
extern "C" inline int sceIoClose(SceUID fd) {
    using namespace guest_test;
    ++closes;const auto found=open_files.find(fd);
    if(found==open_files.end()) return error(9);
    stored[found->second.path]={found->second.data};open_files.erase(found);
    return close_error;
}
extern "C" inline SceSSize sceIoWrite(SceUID fd,const void* buffer,SceSize size) {
    using namespace guest_test;
    const auto found=open_files.find(fd);
    if(found==open_files.end()) return error(9);
    found->second.data.append(static_cast<const char*>(buffer),size);
    return write_error ? static_cast<SceSSize>(size)-write_error : static_cast<SceSSize>(size);
}
