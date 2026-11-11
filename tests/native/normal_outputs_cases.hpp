Session ready_session(native_test::LifecycleFixture& fixture) {
    Session session(fixture.world,fixture.frames);
    for(unsigned frame=0;frame<120 && !initial_respawn_ready(session,frame,false);++frame) {
        session.step({});
        session.lifecycle()->draw();
    }
    expect(initial_respawn_ready(session,120,false),"Synthetic fixture must reach live initial respawn");
    return session;
}
void legacy_collision_composes_to_strict_capture_failure() {
    reset();native_test::LifecycleFixture fixture;auto session=ready_session(fixture);
    InitialRespawnCapture capture;
    stored["/data/old.ppm"]={"prior-image"};
    expect(capture.request(session,120,false),"Eligible capture must request export");
    const char* path=guest_capture_exists("/data/old.ppm") ? nullptr : "/data/old.ppm";
    const std::string exported=path ? "closed export" : "";
    rejects([&]{capture.confirm_export(exported);},"fresh closed export");
    expect(stored.at("/data/old.ppm").data=="prior-image" && opens==0,"Strict failure must preserve existing image");
}
void two_launches_preserve_all_prior_outputs() {
    reset();const std::string revision(40,'a');
    stored["ux0:data/celeste_native_room.log"]={"legacy-log"};
    stored["ux0:data/celeste_native_room.ready"]={"legacy-ready"};
    std::string first_run;
    for(unsigned launch=0;launch<2;++launch) {
        std::map<std::string,std::string> prior;
        for(const auto& item:stored) prior[item.first]=item.second.data;
        const auto outputs=claim_normal_outputs(revision,1234);
        expect(launch==0 || outputs.run_id!=first_run,"Repeated clock token must still isolate each launch");
        if(launch==0) first_run=outputs.run_id;
        native_test::LifecycleFixture fixture;auto session=ready_session(fixture);InitialRespawnCapture capture;
        expect(capture.request(session,120,false),"New run must reach eligible capture");
        const auto receipt="frame_saved path="+outputs.frame+" revision="+revision+" capture=initial_respawn "+outputs.capture_identity()+"\n";
        outputs.validate_capture(outputs.frame.c_str(),revision);
        write_guest_file(outputs.frame.c_str(),"fresh-ppm",SCE_O_EXCL);
        write_guest_file(outputs.sidecar.c_str(),receipt,SCE_O_EXCL);
        outputs.confirm_export(receipt,revision);capture.confirm_export(receipt);capture.require_complete();
        write_guest_file(outputs.ready.c_str(),outputs.record("ready","fresh_closed"),SCE_O_EXCL);
        write_guest_file(outputs.failure.c_str(),outputs.record("failure","fresh_closed"),SCE_O_EXCL);
        expect(open_files.empty() && opens==closes,"Every fresh export and claim must close");
        for(const auto& item:prior) expect(stored.at(item.first).data==item.second,"Every prior output byte must survive repeat launch");
    }
}
void normal_orphan_collisions_parameterized() {
    for(unsigned destination=0;destination<5;++destination) {
        reset();const auto occupied=normal_output_paths("revision",77,0);
        const auto paths=occupied.destinations();stored[paths[destination]]={"orphan"};
        const auto fresh=claim_normal_outputs("revision",77);
        expect(fresh.run_id!=occupied.run_id && stored.at(paths[destination]).data=="orphan","Any orphan must occupy the entire candidate");
        expect(opens==1 && closes==1 && stats==10,"All five destinations must be checked for both candidates before the only claim");
    }
}
void normal_namespace_exhaustion() {
    reset();
    for(unsigned i=0;i<normal_output_candidates;++i) stored[normal_output_paths("revision",77,i).sidecar]={"orphan"};
    rejects([&]{claim_normal_outputs("revision",77);},"exhausted");
    expect(opens==0 && stored.size()==normal_output_candidates,"Exhaustion must not open or truncate anything");
}
void normal_stat_failure_parameterized() {
    for(unsigned destination=0;destination<5;++destination) {
        reset();const auto paths=normal_output_paths("revision",77,0).destinations();
        stored[paths[0]]={"occupied"};stat_error=error(13);stat_fail_path=paths[destination];
        rejects([&]{claim_normal_outputs("revision",77);},"stat failed");
        expect(opens==0 && stored.at(paths[0]).data=="occupied","All stat errors, even after an occupied destination, must precede any open");
    }
}
void normal_claim_failures_parameterized() {
    for(unsigned failure=0;failure<4;++failure) {
        reset();const auto candidate=normal_output_paths("revision",77,0);
        stored["unrelated"]={"protected"};
        if(failure==0) race_path=candidate.log;
        if(failure==1) {open_error=error(13);fail_open=1;}
        if(failure==2) write_error=1;
        if(failure==3) close_error=error(5);
        rejects([&]{claim_normal_outputs("revision",77);},failure<2 ? "open failed: "+candidate.log : "write/close failed: "+candidate.log);
        expect(opens==1 && open_files.empty(),"Racing claim and IO failures must be fatal, not try another namespace");
        expect(stored.at("unrelated").data=="protected","Claim errors must preserve unrelated bytes");
        if(failure==0) expect(stored.at(candidate.log).data=="racing-writer-bytes","Exclusive claim must preserve the racing writer's bytes");
        if(failure>=2) expect(stored.count(candidate.log)==1,"Partial claims must remain for recovery");
    }
}
void normal_wrong_binding_parameterized() {
    for(unsigned failure=0;failure<3;++failure) {
        reset();const auto outputs=claim_normal_outputs(std::string(40,'a'),77);
        const auto other=normal_output_paths(std::string(40,'b'),88,0);
        const auto receipt="frame_saved path="+outputs.frame+" revision="+outputs.revision+" capture=initial_respawn "+outputs.capture_identity()+"\n";
        if(failure==0) rejects([&]{outputs.validate_capture(other.frame.c_str(),outputs.revision);},"binding");
        if(failure==1) rejects([&]{outputs.validate_capture(outputs.frame.c_str(),other.revision);},"binding");
        if(failure==2) rejects([&]{outputs.confirm_export("frame_saved path="+other.frame+" revision="+other.revision+" capture=initial_respawn "+other.capture_identity()+"\n",outputs.revision);},"binding");
        expect(!receipt.empty() && opens==1,"Invalid binding must fail before image IO");
    }
}
void normal_invalid_inputs_parameterized() {
    for(const auto& revision:std::vector<std::string>{"","../escape","bad revision","bad\nrevision",std::string(193,'a')}) {
        reset();rejects([&]{claim_normal_outputs(revision,77);},"revision");expect(opens==0,"Invalid revision must fail before IO");
    }
    reset();rejects([&]{normal_output_paths("revision",77,normal_output_candidates);},"candidate");
}
void full_revision_does_not_expand_normal_filenames() {
    reset();const auto outputs=claim_normal_outputs(std::string(192,'a'),77);
    expect(outputs.revision.size()==192 && outputs.log.size()<80 && outputs.record("ready","pending").find(outputs.revision)!=std::string::npos,"Short FAT-safe paths must preserve the full bounded source revision in records");
}
void normal_receipt_binding_corruption_parameterized() {
    const auto outputs=normal_output_paths(std::string(40,'a'),77,0);
    const auto valid="frame_saved path="+outputs.frame+" revision="+outputs.revision+" capture=initial_respawn "+outputs.capture_identity()+"\n";
    for(unsigned corruption=0;corruption<4;++corruption) {
        auto receipt=valid;
        if(corruption==0) receipt+="run_id="+outputs.run_id+"\n";
        if(corruption==1) receipt.erase(receipt.find("run_id="),7+outputs.run_id.size());
        if(corruption==2) receipt.replace(receipt.find("fresh_closed"),12,"pending");
        if(corruption==3) receipt.pop_back();
        rejects([&]{outputs.confirm_export(receipt,outputs.revision);},"binding");
    }
}
