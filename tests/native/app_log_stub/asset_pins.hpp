#pragma once
#include <cstdint>
namespace celeste::diagnostic {
inline constexpr bool guest_replay_enabled=false;
inline constexpr const char* guest_automatic=nullptr;
inline constexpr const char* revision="test-revision";
inline constexpr const char* player_bank_sha256="synthetic-test-bank";
inline constexpr std::uint32_t mask_checksum=0,spike_checksum=0,visual_checksum=0,player_checksum=0,decal_checksum=0;
}
