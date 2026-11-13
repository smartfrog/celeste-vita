#include "guest_file_fixture.hpp"

extern "C" int sceIoGetstat(const char* path,SceIoStat*) {
    using namespace guest_test;
    ++stats;
    if(stat_error && (stat_fail_path.empty() || stat_fail_path==path)) return stat_error;
    return stored.find(path)==stored.end() ? error(2) : 0;
}
extern "C" SceUID sceIoOpen(const char* path,int flags,SceMode) {
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
extern "C" int sceIoClose(SceUID fd) {
    using namespace guest_test;
    ++closes;const auto found=open_files.find(fd);
    if(found==open_files.end()) return error(9);
    stored[found->second.path]={found->second.data};open_files.erase(found);
    return close_error;
}
extern "C" SceSSize sceIoWrite(SceUID fd,const void* buffer,SceSize size) {
    using namespace guest_test;
    const auto found=open_files.find(fd);
    if(found==open_files.end()) return error(9);
    found->second.data.append(static_cast<const char*>(buffer),size);
    return write_error ? static_cast<SceSSize>(size)-write_error : static_cast<SceSSize>(size);
}
