#include "guest_io.hpp"
#include <iostream>
#include <map>
#include <stdexcept>
#include <string>
#include <string_view>
#include <vector>

using namespace celeste::diagnostic;

namespace {
struct StoredFile { std::string data; };
struct OpenFile { std::string path; std::string data; };

std::map<std::string,StoredFile> stored;
std::map<SceUID,OpenFile> open_files;
int next_fd = 10;
int stat_error = 0;
int write_error = 0;
int close_error = 0;
unsigned opens = 0, closes = 0;
int last_open_flags = 0;

void reset() {
    stored.clear();
    open_files.clear();
    next_fd = 10;
    stat_error = 0;
    write_error = 0;
    close_error = 0;
    opens = closes = 0;
    last_open_flags = 0;
}

constexpr int error(int code) { return static_cast<int>(0x80010000u | static_cast<unsigned>(code)); }

void expect(bool value, const char* message) { if (!value) throw std::runtime_error(message); }
template<class F> void rejects(F action, const std::string& text) {
    try { action(); }
    catch (const std::exception& error) {
        expect(std::string(error.what()).find(text) != std::string::npos, "Unexpected error text");
        return;
    }
    throw std::runtime_error("Expected rejection");
}

void missing_pair_is_absent() {
    reset();
    expect(!guest_capture_exists("/data/frame.ppm"), "Missing pair must be absent");
    expect(opens == 0, "Availability check must not open outputs");
}

void complete_pair_preserves_without_opening() {
    reset();
    stored["/data/frame.ppm"] = {"old-image"};
    stored["/data/frame.ppm.txt"] = {"old-receipt"};
    expect(guest_capture_exists("/data/frame.ppm"), "Complete pair must be detected");
    expect(opens == 0 && !stored.empty(), "Complete pair must not be opened or replaced");
    expect(stored["/data/frame.ppm"].data == "old-image" && stored["/data/frame.ppm.txt"].data == "old-receipt",
           "Complete pair content must be preserved");
}

void partial_pair_is_present_parameterized() {
    reset();
    stored["/data/frame.ppm"] = {"old-image"};
    expect(guest_capture_exists("/data/frame.ppm"), "Image-only pair must be treated as existing");
    reset();
    stored["/data/frame.ppm.txt"] = {"old-receipt"};
    expect(guest_capture_exists("/data/frame.ppm"), "Receipt-only pair must be treated as existing");
    expect(opens == 0, "Partial pair must not be opened");
}

void fresh_pair_writes_both_closed_outputs() {
    reset();
    const std::string image = "P6\n1 1\n255\nrgb";
    const std::string receipt = "frame_saved path=/data/frame.ppm\n";
    expect(!guest_capture_exists("/data/frame.ppm"), "Fresh pair must be absent");
    write_guest_file("/data/frame.ppm",image,SCE_O_EXCL);
    write_guest_file("/data/frame.ppm.txt",receipt,SCE_O_EXCL);
    expect(opens == 2 && closes == 2, "Fresh image/receipt must each open and close");
    expect((last_open_flags & (SCE_O_WRONLY|SCE_O_CREAT|SCE_O_EXCL)) == (SCE_O_WRONLY|SCE_O_CREAT|SCE_O_EXCL),
           "Fresh output must stay exclusive");
    expect(stored.at("/data/frame.ppm").data == image && stored.at("/data/frame.ppm.txt").data == receipt,
           "Fresh pair content must be complete");
    expect(guest_capture_exists("/data/frame.ppm"), "Fresh pair must become an existing pair");
}

void existing_output_excl_writer_fails_and_preserves() {
    reset();
    stored["/data/frame.ppm"] = {"old-image"};
    rejects([&] { write_guest_file("/data/frame.ppm","new-image",SCE_O_EXCL); },"open failed");
    expect(stored.at("/data/frame.ppm").data == "old-image", "Existing image must not be overwritten");
    expect(closes == 0, "Failed exclusive open must not close a handle");
}

void unexpected_stat_error_is_not_treated_as_missing() {
    reset();
    stat_error = error(13);
    rejects([&] { guest_capture_exists("/data/frame.ppm"); },"stat failed");
    expect(opens == 0, "Unexpected stat error must not fall through to writing");
}

void oversized_output_rejected_before_open() {
    reset();
    const std::string too_large(2*1024*1024+1,'x');
    rejects([&] { write_guest_file("/data/frame.ppm",too_large,SCE_O_EXCL); },"exceeds bounded");
    expect(opens == 0, "Oversized output must be rejected before the filesystem");
}

void partial_write_is_reported_after_close() {
    reset();
    write_error = 1;
    rejects([&] { write_guest_file("/data/frame.ppm","data",SCE_O_EXCL); },"write/close failed");
    expect(closes == 1, "Partial write must still close its handle");
    expect(open_files.empty(), "Failed write must not leak the simulated handle");
}

void close_failure_is_reported() {
    reset();
    close_error = error(5);
    rejects([&] { write_guest_file("/data/frame.ppm","data",SCE_O_EXCL); },"write/close failed");
    expect(closes == 1, "Close failure must be reported");
}
}

extern "C" int sceIoGetstat(const char* path, SceIoStat*) {
    if (stat_error) return stat_error;
    return stored.find(path) == stored.end() ? error(2) : 0;
}

extern "C" SceUID sceIoOpen(const char* path, int flags, SceMode) {
    ++opens;
    last_open_flags = flags;
    const auto found = stored.find(path);
    if ((flags & SCE_O_EXCL) && found != stored.end()) return error(17);
    if (!(flags & SCE_O_CREAT) && found == stored.end()) return error(2);
    const int fd = next_fd++;
    open_files[fd] = {path,(flags & SCE_O_TRUNC) || found == stored.end() ? "" : found->second.data};
    return fd;
}

extern "C" int sceIoClose(SceUID fd) {
    ++closes;
    const auto found = open_files.find(fd);
    if (found == open_files.end()) return error(9);
    stored[found->second.path] = {found->second.data};
    open_files.erase(found);
    return close_error;
}

extern "C" SceSSize sceIoWrite(SceUID fd, const void* buffer, SceSize size) {
    const auto found = open_files.find(fd);
    if (found == open_files.end()) return error(9);
    const auto bytes = static_cast<const char*>(buffer);
    found->second.data.append(bytes,size);
    return write_error ? static_cast<SceSSize>(size)-write_error : static_cast<SceSSize>(size);
}

int main() {
    int failed = 0;
    for (auto test : {missing_pair_is_absent, complete_pair_preserves_without_opening,
         partial_pair_is_present_parameterized, fresh_pair_writes_both_closed_outputs,
         existing_output_excl_writer_fails_and_preserves, unexpected_stat_error_is_not_treated_as_missing,
         oversized_output_rejected_before_open, partial_write_is_reported_after_close,
         close_failure_is_reported}) {
        try { test(); }
        catch (const std::exception& error) { std::cerr << error.what() << '\n'; ++failed; }
    }
    std::cout << "guest io cases=9 failed=" << failed << '\n';
    return failed ? 1 : 0;
}
