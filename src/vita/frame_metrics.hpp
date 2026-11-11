#pragma once
#include <array>
#include <cstdint>
#include <cstdio>
#include <limits>
#include <stdexcept>
#include <string_view>

namespace celeste::diagnostic {

inline constexpr std::array<std::uint64_t,5> metric_bucket_upper_us{16667,20000,33334,50000,100000};
inline constexpr std::array<std::uint64_t,4> metric_threshold_us{20000,33334,50000,100000};
enum MetricFlag : unsigned {
    metric_count_overflow=1,metric_sum_overflow=2,metric_index_overflow=4,
    metric_clock_regression=8,metric_ps_reanchor=16,metric_unanchored=32,metric_capture_excluded=64,metric_summary_excluded=128
};
struct MetricTags {bool capture=false,summary=false;};
enum class MetricCategory : unsigned {loop_interval,step,render_including_swap_capture,log};

struct DurationMetrics {
    std::uint64_t count=0,sum_us=0,max_us=0,max_frame=0,excluded=0,capture_samples=0,summary_samples=0;
    std::array<std::uint64_t,6> buckets{};
    std::array<std::uint64_t,4> over{};
    unsigned flags=0;
    bool invalid=false;

    void exclude(unsigned reason,bool invalid_sample) noexcept {
        flags|=reason;invalid=invalid || invalid_sample;
        if(excluded==std::numeric_limits<std::uint64_t>::max()) {flags|=metric_count_overflow;invalid=true;}
        else ++excluded;
    }
    void record(std::uint64_t us,std::uint64_t frame,MetricTags tags) noexcept {
        constexpr auto limit=std::numeric_limits<std::uint64_t>::max();
        unsigned bucket=0;
        while(bucket<metric_bucket_upper_us.size() && us>metric_bucket_upper_us[bucket]) ++bucket;
        unsigned overflow=0;
        if(count==limit || buckets[bucket]==limit || (tags.capture && capture_samples==limit) || (tags.summary && summary_samples==limit))
            overflow|=metric_count_overflow;
        for(unsigned i=0;i<over.size();++i) if(us>metric_threshold_us[i] && over[i]==limit) overflow|=metric_count_overflow;
        if(us>limit-sum_us) overflow|=metric_sum_overflow;
        if(overflow) {exclude(overflow,true);return;}
        if(count==0 || us>max_us) {max_us=us;max_frame=frame;}
        ++count;sum_us+=us;++buckets[bucket];
        for(unsigned i=0;i<over.size();++i) if(us>metric_threshold_us[i]) ++over[i];
        if(tags.capture) ++capture_samples;
        if(tags.summary) ++summary_samples;
    }
};

struct MetricSummary {
    std::array<char,8192> text{};
    std::size_t size=0;
    template<class... Args> void append(const char* format,Args... args) {
        const auto written=std::snprintf(text.data()+size,text.size()-size,format,args...);
        if(written<0 || static_cast<std::size_t>(written)>=text.size()-size) throw std::runtime_error("Frame metric summary exceeds fixed storage");
        size+=static_cast<std::size_t>(written);
    }
};

struct FrameMetrics {
    std::array<DurationMetrics,4> durations{};
    std::array<DurationMetrics,4> steady_durations{};
    std::uint64_t frames=0,capture_frames=0,summary_frames=0,frame_index=0,anchor_us=0,log_sum_us=0;
    MetricTags tags{},interval_tags{};
    unsigned flags=0;
    bool invalid=false,anchored=false,current_frame_valid=false,current_frame_intercepted=false,log_invalid=false;

    bool begin_frame(std::uint64_t now_us,MetricTags frame_tags,bool intercepted=false) noexcept {
        constexpr auto limit=std::numeric_limits<std::uint64_t>::max();
        current_frame_valid=false;
        if(frames==limit || (frame_tags.capture && capture_frames==limit) || (frame_tags.summary && summary_frames==limit)) {
            flags|=frames==limit ? metric_index_overflow : metric_count_overflow;invalid=true;return false;
        }
        frame_index=frames++;tags=frame_tags;current_frame_valid=true;
        log_sum_us=0;log_invalid=false;
        current_frame_intercepted=intercepted;
        if(intercepted) ps_intercept();
        if(tags.capture) ++capture_frames;
        if(tags.summary) ++summary_frames;
        if(!anchored) exclude(0,metric_unanchored,false);
        else if(now_us<anchor_us) exclude(0,metric_clock_regression,true);
        else record_sample(0,now_us-anchor_us,frame_index-1,interval_tags);
        anchor_us=now_us;interval_tags=tags;anchored=!intercepted;
        return true;
    }
    void ps_intercept() noexcept {
        anchored=false;current_frame_intercepted=true;
        durations[0].flags|=metric_ps_reanchor;steady_durations[0].flags|=metric_ps_reanchor;
    }
    void mark_capture() noexcept {
        if(!tags.capture) {
            if(capture_frames==std::numeric_limits<std::uint64_t>::max()) {flags|=metric_count_overflow;invalid=true;}
            else ++capture_frames;
        }
        tags.capture=true;interval_tags.capture=true;
    }
    void mark_summary() noexcept {
        if(!tags.summary) {
            if(summary_frames==std::numeric_limits<std::uint64_t>::max()) {flags|=metric_count_overflow;invalid=true;}
            else ++summary_frames;
        }
        tags.summary=true;interval_tags.summary=true;
    }
    void exclude(unsigned index,unsigned reason,bool invalid_sample) noexcept {
        durations[index].exclude(reason,invalid_sample);steady_durations[index].exclude(reason,invalid_sample);
    }
    void record_sample(unsigned index,std::uint64_t us,std::uint64_t frame,MetricTags sample_tags) noexcept {
        durations[index].record(us,frame,sample_tags);
        const auto excluded=(sample_tags.capture ? metric_capture_excluded : 0u)|(sample_tags.summary ? metric_summary_excluded : 0u);
        if(excluded) steady_durations[index].exclude(excluded,false);
        else steady_durations[index].record(us,frame,{});
    }
    static unsigned duration_index(MetricCategory category) {
        const auto index=static_cast<unsigned>(category);
        if(index==0 || index>=4) throw std::invalid_argument("Use begin_frame for loop interval; unknown duration category");
        return index;
    }
    void record(MetricCategory category,std::uint64_t duration_us) {
        const auto index=duration_index(category);
        if(!current_frame_valid) {exclude(index,metric_unanchored,true);return;}
        if(current_frame_intercepted) {exclude(index,metric_ps_reanchor,false);return;}
        record_sample(index,duration_us,frame_index,tags);
    }
    void record_span(MetricCategory category,std::uint64_t begin_us,std::uint64_t end_us) {
        const auto index=duration_index(category);
        if(end_us<begin_us) {exclude(index,metric_clock_regression,true);return;}
        record(category,end_us-begin_us);
    }
    void log_success(std::uint64_t begin_us,std::uint64_t end_us) noexcept {
        if(log_invalid) return;
        const auto reason=end_us<begin_us ? metric_clock_regression : end_us-begin_us>std::numeric_limits<std::uint64_t>::max()-log_sum_us ? metric_sum_overflow : 0u;
        if(reason) {exclude(3,reason,true);log_invalid=true;return;}
        log_sum_us+=end_us-begin_us;
    }
    void finish_log() {if(!log_invalid) record(MetricCategory::log,log_sum_us);}
    bool summary_due() const noexcept {return current_frame_valid && frames%300==0;}

    MetricSummary summary(std::string_view reason,std::string_view run_id,std::string_view revision,std::string_view clock) const {
        for(const auto token:{reason,run_id,revision,clock})
            if(token.empty() || token.size()>192 || token.find_first_not_of("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789._-")!=std::string_view::npos)
                throw std::invalid_argument("Invalid bounded frame metric provenance token");
        MetricSummary output;
        const auto u=[](std::uint64_t value){return static_cast<unsigned long long>(value);};
        auto all_flags=flags;
        bool any_invalid=invalid;
        for(const auto& duration:durations) {all_flags|=duration.flags;any_invalid=any_invalid || duration.invalid;}
        output.append("frame_metrics reason=%.*s run_id=%.*s revision=%.*s clock=%.*s instrumented=1 gpu_time_claim=0 fps_claim=0 loop_interval_covers=prior_sample_frame summary_excludes_own_log=1 frames=%llu capture_frames=%llu summary_frames=%llu flags=%u invalid=%u buckets_us_le=16667,20000,33334,50000,100000,inf strict_over_us=20000,33334,50000,100000",
            int(reason.size()),reason.data(),int(run_id.size()),run_id.data(),int(revision.size()),revision.data(),int(clock.size()),clock.data(),
            u(frames),u(capture_frames),u(summary_frames),all_flags,unsigned(any_invalid));
        constexpr std::array<const char*,4> names{"loop_interval","step","render_including_swap_capture","log"};
        for(unsigned series=0;series<2;++series) for(unsigned i=0;i<durations.size();++i) {
            const auto& d=series==0 ? durations[i] : steady_durations[i];
            output.append(" %s_%s:count=%llu,sum_us=%llu,max_us=%llu,max_frame=%llu,excluded=%llu,capture=%llu,summary=%llu,flags=%u,invalid=%u,buckets=%llu,%llu,%llu,%llu,%llu,%llu,over=%llu,%llu,%llu,%llu",
                series==0 ? "all" : "steady",names[i],u(d.count),u(d.sum_us),u(d.max_us),u(d.max_frame),u(d.excluded),u(d.capture_samples),u(d.summary_samples),d.flags,unsigned(d.invalid),
                u(d.buckets[0]),u(d.buckets[1]),u(d.buckets[2]),u(d.buckets[3]),u(d.buckets[4]),u(d.buckets[5]),u(d.over[0]),u(d.over[1]),u(d.over[2]),u(d.over[3]));
        }
        output.append("%s","\n");return output;
    }
};

}
