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
