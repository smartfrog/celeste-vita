#pragma once
#include "guest_dash_probe.hpp"
#include "guest_record.hpp"
#include <algorithm>

namespace celeste::diagnostic {

inline std::string dash_probe_receipt_path(std::string_view kind,std::string_view revision) {
    if(kind!="complete" && kind!="failure") throw std::invalid_argument("Unknown Dash probe receipt kind");
    return "ux0:data/celeste_native_room-"+std::string(kind)+"-"+std::string(revision)+"-dash-probe.txt";
}

inline bool probe_record_field(std::string_view record,std::string_view key,std::string_view value) {
    const auto prefix=std::string(key)+"=",token=prefix+std::string(value);
    bool found=false;
    for(auto start=record.find_first_not_of(" \t\r\n");start!=std::string_view::npos;) {
        const auto end=record.find_first_of(" \t\r\n",start);
        const auto word=record.substr(start,end==std::string_view::npos ? record.size()-start : end-start);
        if(word.substr(0,prefix.size())==prefix) {
            if(found || word!=token) return false;
            found=true;
        }
        start=end==std::string_view::npos ? end : record.find_first_not_of(" \t\r\n",end);
    }
    return found;
}

struct ProbeTrailCounts { unsigned trails=0,committed=0,captured=0; };
inline ProbeTrailCounts probe_trail_counts(const Session& session) {
    ProbeTrailCounts counts;
    for(const auto& slot:session.trails().slots()) if(slot.occupied) {
        ++counts.trails;
        counts.committed+=slot.committed;
        counts.captured+=slot.drawn;
    }
    return counts;
}

class GuestDashProbeObserver final {
public:
    GuestDashProbeObserver(const Session& session,std::string_view revision,std::string_view fixture_sha256)
        : session_(&session),life_(session.lifecycle()),revision_(revision),fixture_sha256_(fixture_sha256) {
        if(!life_ || session.resets()!=0 || session.exiting() || session.player().state_machine().state()!=14 ||
           session.player().death().dead || life_->stats().loads!=1 || life_->stats().reloads!=0 || session.trails().count()!=0 || life_->context().clock.frame_counter!=0)
            throw std::invalid_argument("Dash probe requires a fresh production lifecycle Session");
        if(revision.empty() || revision.size()>192 || revision.find_first_of(" \t\r\n")!=std::string_view::npos ||
           fixture_sha256.size()!=64 || !std::all_of(fixture_sha256.begin(),fixture_sha256.end(),[](char c){return (c>='0' && c<='9') || (c>='a' && c<='f');}))
            throw std::invalid_argument("Dash probe requires bounded source revision and fixture hash");
        previous_clock_=life_->context().clock.frame_counter;
    }
    std::string observe(unsigned frame,const Controls& controls,const Sample& sample,const Session& session) {
        if(frame!=samples_ || frame>=guest_dash_probe_frames) throw std::invalid_argument("Dash probe observation out of order");
        require_session(session);
        auto expected_controls=dash_probe_controls(frame);
        expected_controls.start=frame==guest_dash_probe_frames-1;
        const auto expected=expected_controller_.sample(expected_controls);
        if(controls.left!=expected_controls.left || controls.right!=expected_controls.right || controls.up!=expected_controls.up ||
           controls.down!=expected_controls.down || controls.cross!=expected_controls.cross || controls.triangle!=expected_controls.triangle ||
           controls.start!=expected_controls.start || controls.square!=expected_controls.square || controls.l!=expected_controls.l ||
           sample.player.x!=expected.player.x || sample.player.y!=expected.player.y || sample.player.aim_x!=expected.player.aim_x ||
           sample.player.aim_y!=expected.player.aim_y || sample.player.jump.held!=expected.player.jump.held ||
           sample.player.jump.pressed!=expected.player.jump.pressed || sample.player.jump.released!=expected.player.jump.released ||
           sample.player.dash_button.held!=expected.player.dash_button.held || sample.player.dash_button.pressed!=expected.player.dash_button.pressed ||
           sample.player.dash_button.released!=expected.player.dash_button.released || sample.player.grab!=expected.player.grab ||
           sample.player.dash!=expected.player.dash || sample.reset!=expected.reset || sample.exit!=expected.exit)
            throw std::invalid_argument("Dash probe observed input differs from its pinned fixture");
        const auto clock=life_->context().clock.frame_counter;
        if(clock!=previous_clock_+unsigned(!sample.exit) || session.exiting()!=sample.exit)
            throw std::invalid_argument("Dash probe observed an extra or missing Session clock step");
        const auto counts=probe_trail_counts(session);
        if(counts.trails>3 || counts.committed>3 || counts.captured>3) throw std::runtime_error("Dash probe produced more than three trails");
        max_trails_=std::max(max_trails_,counts.trails);max_committed_=std::max(max_committed_,counts.committed);max_captured_=std::max(max_captured_,counts.captured);
        const auto state=session.player().state_machine().state();
        dash_entered_=dash_entered_ || state==2;
        dash_completed_=dash_completed_ || (previous_state_==2 && state==0);
        previous_state_=state;previous_clock_=clock;++samples_;
        return bounded_guest_record<768>("Dash probe sample record exceeds bound",
            "guest_dash_probe fixture=%s frame=%u left=%d right=%d up=%d down=%d cross=%d triangle=%d start=%d square=%d l=%d jump=%d jump_pressed=%d jump_released=%d dash=%d dash_pressed=%d dash_released=%d grab=%d reset=%d exit=%d x=%d y=%d aim_x=%d aim_y=%d state=%d dead=%d clock=%llu dash_events=%u trails=%u committed_trails=%u captured_trails=%u fresh_export=%d native_probe_checks=%d",
            guest_dash_probe_id,frame,int(controls.left),int(controls.right),int(controls.up),int(controls.down),int(controls.cross),int(controls.triangle),
            int(controls.start),int(controls.square),int(controls.l),int(sample.player.jump.held),
            int(sample.player.jump.pressed),int(sample.player.jump.released),int(sample.player.dash_button.held),int(sample.player.dash_button.pressed),
            int(sample.player.dash_button.released),int(sample.player.grab),int(sample.reset),int(sample.exit),sample.player.x,sample.player.y,
            sample.player.aim_x,sample.player.aim_y,state,int(session.player().death().dead),static_cast<unsigned long long>(clock),
            session.player().state().dash_events,counts.trails,counts.committed,counts.captured,int(export_closed_),int(export_closed_));
    }
    void confirm_export(std::string_view receipt,const Session& session) {
        require_session(session);
        const auto counts=probe_trail_counts(session);
        const auto path="ux0:data/celeste_native_room-"+revision_+"-dash-probe.ppm";
        if(export_closed_ || samples_==0 || samples_>=guest_dash_probe_frames || counts.trails!=3 || counts.committed!=3 || counts.captured!=3 ||
           !probe_record_field(receipt,"path",path) || !probe_record_field(receipt,"revision",revision_) ||
           !probe_record_field(receipt,"probe_fixture",guest_dash_probe_id) || !probe_record_field(receipt,"probe_fixture_sha256",fixture_sha256_) ||
           !probe_record_field(receipt,"frame",std::to_string(samples_)) || !probe_record_field(receipt,"capture","dash_trails") ||
            !probe_record_field(receipt,"stage","after_draw_glFinish_GL_BACK_RGBA_CPU_before_swap") ||
            !probe_record_field(receipt,"trail_probe","diagnostic_rgba_fbo") || !probe_record_field(receipt,"other_captured_tiles_preserved","1") ||
            !probe_record_field(receipt,"native_probe_checks","1"))
            throw std::runtime_error("Dash probe requires three captured trails and one fresh closed native probe export");
        export_closed_=true;
    }
    bool complete(const Session& session) const {
        return &session==session_ && session.lifecycle()==life_ && samples_==guest_dash_probe_frames && session.exiting() &&
            session.resets()==0 && !session.player().death().dead && session.player().state_machine().state()==0 &&
            life_->stats().loads==1 && life_->stats().reloads==0 && life_->stats().room_deaths==0 && life_->stats().save_deaths==0 &&
            life_->stats().respawn_callbacks==1 && session.player().state().dash_events==1 &&
            max_trails_==3 && max_committed_==3 && max_captured_==3 && dash_entered_ && dash_completed_ && export_closed_ &&
            life_->context().clock.frame_counter==previous_clock_;
    }
    std::string completion_fields(const Session& session) const {
        if(!complete(session)) throw std::runtime_error("Dash probe did not complete 360 observed samples and native probe export");
        return bounded_guest_record<768>("Dash probe completion record exceeds bound",
            "revision=%s fixture=%s fixture_sha256=%s samples=%u exit_frame=%u clock=%llu dash_events=%u max_trails=%u max_committed=%u max_captured=%u fresh_export=1 native_probe_checks=1 full_completion=1",
            revision_.c_str(),guest_dash_probe_id,fixture_sha256_.c_str(),samples_,guest_dash_probe_frames-1,
            static_cast<unsigned long long>(life_->context().clock.frame_counter),session.player().state().dash_events,max_trails_,max_committed_,max_captured_);
    }
private:
    const Session* session_;
    const FirstRoomSession* life_;
    std::string revision_,fixture_sha256_;
    Controller expected_controller_;
    unsigned samples_=0,max_trails_=0,max_committed_=0,max_captured_=0;
    std::uint64_t previous_clock_=0;
    int previous_state_=14;
    bool dash_entered_=false,dash_completed_=false,export_closed_=false;
    void require_session(const Session& session) const {
        if(&session!=session_ || session.lifecycle()!=life_ || session.resets()!=0 || session.player().death().dead ||
           life_->stats().reloads!=0 || life_->stats().loads!=1 || life_->stats().room_deaths!=0 || life_->stats().save_deaths!=0)
            throw std::invalid_argument("Dash probe lost its unchanged live Session");
    }
};

class GuestDashProbeCompletion final {
public:
    void record_run(const GuestDashProbeObserver& observer,const Session& session) {
        if(phase_!=Phase::empty) throw std::runtime_error("Duplicate Dash probe completion");
        fields_=observer.completion_fields(session);phase_=Phase::run_verified;
    }
    void graphics_finished() {
        if(phase_!=Phase::run_verified) throw std::runtime_error("Dash probe graphics completion out of order");
        phase_=Phase::graphics_finished;
    }
    std::string log_record() const {
        if(phase_!=Phase::graphics_finished) throw std::runtime_error("Dash probe completion requires successful graphics teardown");
        return "guest_dash_probe_complete "+fields_+" graphics_teardown=1";
    }
    void logged() {
        if(phase_!=Phase::graphics_finished) throw std::runtime_error("Dash probe summary completion out of order");
        phase_=Phase::completion_logged;
    }
    void log_closed() {
        if(phase_!=Phase::completion_logged) throw std::runtime_error("Dash probe log completion out of order");
        phase_=Phase::log_closed;
    }
    std::string closed_receipt() const {
        if(phase_!=Phase::log_closed) throw std::runtime_error("Dash probe receipt requires a successfully closed log");
        const auto receipt="complete "+fields_+" input_source=scripted_guest_controls capture=dash_trails graphics_teardown=1 log_closed=1 status=0\n";
        if(receipt.size()>1024) throw std::runtime_error("Dash probe closed receipt exceeds bound");
        return receipt;
    }
private:
    enum class Phase {empty,run_verified,graphics_finished,completion_logged,log_closed};
    Phase phase_=Phase::empty;
    std::string fields_;
};

}
