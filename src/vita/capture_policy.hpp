#pragma once

#include "session_profile.hpp"
#include <string_view>

namespace celeste::diagnostic {

enum class CapturePolicy { spawn,wall_jump,climb,initial_respawn,dash_trails };

constexpr CapturePolicy select_capture_policy(bool automatic,bool wall_jump,bool climb) {
    if(wall_jump && climb) throw std::invalid_argument("Capture overrides are mutually exclusive");
    if(wall_jump) return CapturePolicy::wall_jump;
    if(climb) return CapturePolicy::climb;
    return automatic ? CapturePolicy::initial_respawn : CapturePolicy::spawn;
}
constexpr const char* capture_policy_name(CapturePolicy policy) {
    switch(policy) {
    case CapturePolicy::spawn:return "spawn";
    case CapturePolicy::wall_jump:return "wall_jump";
    case CapturePolicy::climb:return "climb";
    case CapturePolicy::initial_respawn:return "initial_respawn";
    case CapturePolicy::dash_trails:return "dash_trails";
    }
    throw std::invalid_argument("Unknown native capture policy");
}
#ifdef CELESTE_ROOM_CAPTURE_AFTER_WALL_JUMP
inline constexpr bool capture_after_wall_jump=true;
#else
inline constexpr bool capture_after_wall_jump=false;
#endif
#ifdef CELESTE_ROOM_CAPTURE_AFTER_CLIMB
inline constexpr bool capture_after_climb=true;
#else
inline constexpr bool capture_after_climb=false;
#endif
#ifdef CELESTE_ROOM_DASH_PROBE
static_assert(automatic_session_profile && !capture_after_wall_jump && !capture_after_climb,"Dash probe owns its distinct capture policy");
inline constexpr auto room_capture_policy=CapturePolicy::dash_trails;
#else
inline constexpr auto room_capture_policy=select_capture_policy(automatic_session_profile,capture_after_wall_jump,capture_after_climb);
#endif

inline bool initial_respawn_ready(const FirstRoomSession& life,unsigned frame,unsigned resets,bool reset) {
    const auto& stats=life.stats();
    return frame>0 && !reset && resets==0 && life.player().state_machine().state()==0 && !life.player().death().dead &&
        std::string_view(life.phase())=="live" && life.wipe()==nullptr && stats.loads==1 && stats.reloads==0 &&
        stats.respawn_callbacks==1 && stats.wipe_callbacks==0 && !life.pending_corpse() && !life.committed_corpse();
}
inline bool initial_respawn_ready(const Session& session,unsigned frame,bool reset) {
    return session.lifecycle() && !session.exiting() && initial_respawn_ready(*session.lifecycle(),frame,session.resets(),reset);
}

class InitialRespawnCapture final {
public:
    bool request(const Session& session,unsigned frame,bool reset) {
        if(requested_ || !initial_respawn_ready(session,frame,reset)) return false;
        requested_=true;
        return true;
    }
    void confirm_export(std::string_view closed_receipt) {
        if(!requested_ || exported_ || closed_receipt.empty()) throw std::runtime_error("Initial respawn requires exactly one fresh closed export");
        exported_=true;
    }
    void require_complete() const {
        if(!exported_) throw std::runtime_error("Initial respawn ended without a fresh closed export");
    }
private:
    bool requested_=false,exported_=false;
};

}
