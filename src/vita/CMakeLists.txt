set(CELESTE_VITAGL_LIBRARY "" CACHE FILEPATH "Existing no-splash vitaGL archive")
set(CELESTE_ROOM_STAGING "" CACHE PATH "Verified private staging from stage_native_room.py")
if(NOT EXISTS "${CELESTE_VITAGL_LIBRARY}" OR NOT EXISTS "${CELESTE_ROOM_STAGING}/asset_pins.hpp")
    message(FATAL_ERROR "Supply the existing no-splash archive and verified private room staging")
endif()
include("$ENV{VITASDK}/share/vita.cmake" REQUIRED)
add_executable(celeste_native_room app.cpp draw.cpp)
option(CELESTE_ROOM_CAPTURE_AFTER_WALL_JUMP "Export once after an actual input-driven WallJump instead of spawn" OFF)
if(CELESTE_ROOM_CAPTURE_AFTER_WALL_JUMP)
    target_compile_definitions(celeste_native_room PRIVATE CELESTE_ROOM_CAPTURE_AFTER_WALL_JUMP)
endif()
target_include_directories(celeste_native_room PRIVATE "${CELESTE_ROOM_STAGING}")
target_compile_options(celeste_native_room PRIVATE -Wall -Wextra -Wpedantic -Werror)
target_link_options(celeste_native_room PRIVATE -Wl,-q -Wl,-z,nocopyreloc)
target_link_libraries(celeste_native_room PRIVATE celeste_room_diagnostic
    "${CELESTE_VITAGL_LIBRARY}" vitashark SceShaccCgExt SceShaccCg_stub_weak taihen_stub_weak
    SceCtrl_stub_weak SceDisplay_stub_weak SceGxm_stub_weak SceAppMgr_stub_weak SceSysmodule_stub_weak
    SceProcessmgr_stub_weak SceKernelDmacMgr_stub_weak SceCommonDialog_stub_weak mathneon m stdc++)
vita_create_self(eboot.bin celeste_native_room)
vita_create_vpk(celeste_native_room.vpk CELR00001 eboot.bin VERSION 00.01 NAME "Celeste Native Room Diagnostic"
    FILE "${CELESTE_ROOM_STAGING}/assets/native-room/global.mask" assets/native-room/global.mask
    FILE "${CELESTE_ROOM_STAGING}/assets/native-room/hazards.txt" assets/native-room/hazards.txt
    FILE "${CELESTE_ROOM_STAGING}/assets/native-room/provenance.json" assets/native-room/provenance.json)
