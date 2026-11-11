#include "frame_metrics.hpp"
#include <cstdlib>
#include <iostream>
#include <limits>
#include <new>
#include <stdexcept>
#include <string_view>

using namespace celeste::diagnostic;
namespace {
unsigned allocations=0;
constexpr auto maximum=std::numeric_limits<std::uint64_t>::max();
void expect(bool value,const char* message) { if(!value) throw std::runtime_error(message); }
void buckets_and_strict_thresholds_parameterized() {
    struct Case {std::uint64_t us;unsigned bucket,over;};
    for(const auto item:{Case{0,0,0},Case{16667,0,0},Case{16668,1,0},Case{20000,1,0},Case{20001,2,1},
                        Case{33334,2,1},Case{33335,3,2},Case{50000,3,2},Case{50001,4,3},Case{100000,4,3},Case{100001,5,4}}) {
        DurationMetrics metrics;metrics.record(item.us,7,{});
        expect(metrics.count==1 && metrics.sum_us==item.us && metrics.buckets[item.bucket]==1,"Exact microsecond bucket boundary differs");
        for(unsigned i=0;i<4;++i) expect(metrics.over[i]==(i<item.over ? 1u : 0u),"Threshold counters must be strictly greater");
    }
}
void maximum_keeps_first_frame_on_tie() {
    DurationMetrics metrics;metrics.record(20,3,{});metrics.record(40,4,{});metrics.record(40,5,{});
    expect(metrics.max_us==40 && metrics.max_frame==4 && metrics.sum_us==100,"Maximum must bind the earliest frame on ties");
}
void arithmetic_overflow_excludes_whole_sample_parameterized() {
    for(unsigned field=0;field<4;++field) {
        DurationMetrics metrics;
        if(field==0) metrics.count=maximum;
        if(field==1) metrics.sum_us=maximum;
        if(field==2) metrics.buckets[5]=maximum;
        if(field==3) metrics.over[0]=maximum;
        metrics.record(100001,7,{});
        expect(metrics.invalid && metrics.excluded==1 && metrics.max_us==0,"Overflow must exclude a sample atomically and flag invalid");
        expect(metrics.flags & (field==1 ? metric_sum_overflow : metric_count_overflow),"Overflow reason must remain explicit");
    }
}
void frame_index_overflow_cannot_wrap() {
    FrameMetrics metrics;metrics.frames=maximum;
    expect(!metrics.begin_frame(100,{}),"Frame count overflow must reject frame");
    expect(metrics.frames==maximum && (metrics.flags&metric_index_overflow) && metrics.invalid,"Frame count must not silently wrap");
}
void clock_regression_excludes_and_reanchors() {
    FrameMetrics metrics;metrics.begin_frame(1000,{});metrics.begin_frame(900,{});metrics.begin_frame(920,{});
    const auto& interval=metrics.durations[0];
    expect(interval.count==1 && interval.sum_us==20 && interval.max_frame==1,"Regressing interval must be excluded; subsequent sample must reanchor");
    expect(interval.invalid && interval.excluded==2 && (interval.flags&metric_clock_regression),"Regression must remain invalid/excluded in summary");
}
void ps_intercept_reanchors_without_gap_assumption_parameterized() {
    for(const auto next:{std::uint64_t{1001},maximum}) {
        FrameMetrics metrics;metrics.begin_frame(1000,{});metrics.ps_intercept();metrics.begin_frame(next,{});
        const auto& interval=metrics.durations[0];
        expect(interval.count==0 && interval.excluded==2 && !interval.invalid,"Explicit intercept must exclude gap regardless of length");
        expect(interval.flags&metric_ps_reanchor,"PS reanchor provenance must remain visible");
    }
}
void duration_categories_keep_capture_and_summary_tags() {
    FrameMetrics metrics;metrics.begin_frame(10,{true,true});
    metrics.record(MetricCategory::step,5);metrics.record(MetricCategory::render_including_swap_capture,70);metrics.record(MetricCategory::log,20);
    for(unsigned i=1;i<4;++i) expect(metrics.durations[i].capture_samples==1 && metrics.durations[i].summary_samples==1,"All duration categories must retain instrumentation tags");
    expect(metrics.durations[2].sum_us==70 && metrics.capture_frames==1 && metrics.summary_frames==1,"Render category must not lose capture tags");
}
void summaries_are_bounded_periodic_and_explicit() {
    FrameMetrics metrics;
    for(unsigned i=0;i<300;++i) {metrics.begin_frame(i*17000,{});expect(metrics.summary_due()==(i==299),"Periodic summary must be due exactly every 300 frames");}
    const auto periodic=metrics.summary("periodic","run-0","revision","unbound");
    const auto final=metrics.summary("Start_final","run-0","revision","unbound");
    const std::string_view text(final.text.data(),final.size);
    expect(periodic.size<periodic.text.size() && final.size<final.text.size(),"Summary must remain fixed and bounded");
    for(auto field:{"reason=Start_final","run_id=run-0","revision=revision","clock=unbound","instrumented=1","gpu_time_claim=0","fps_claim=0","render_including_swap_capture","log:"})
        expect(text.find(field)!=std::string_view::npos,"Summary provenance/category missing");
}
void hot_path_has_no_heap_allocations() {
    FrameMetrics metrics;const auto before=allocations;
    for(unsigned i=0;i<1000;++i) {
        metrics.begin_frame(i*17000,{i==36,i%300==0});
        metrics.record(MetricCategory::step,100);metrics.record(MetricCategory::render_including_swap_capture,15000);metrics.record(MetricCategory::log,20);
    }
    expect(allocations==before,"Per-frame metrics must not allocate");
}
void duration_before_first_frame_is_excluded() {
    FrameMetrics metrics;metrics.record(MetricCategory::step,20);
    expect(metrics.durations[1].count==0 && metrics.durations[1].invalid && (metrics.durations[1].flags&metric_unanchored),"Unbound duration must not invent frame zero");
}
void capture_and_summary_are_excluded_from_steady_series() {
    FrameMetrics metrics;metrics.begin_frame(0,{});metrics.mark_capture();metrics.record(MetricCategory::render_including_swap_capture,100);
    metrics.begin_frame(100,{});metrics.mark_summary();metrics.record(MetricCategory::render_including_swap_capture,200);
    metrics.begin_frame(300,{});metrics.record(MetricCategory::render_including_swap_capture,10);
    expect(metrics.durations[2].count==3 && metrics.steady_durations[2].count==1 && metrics.steady_durations[2].sum_us==10,"Steady render must exclude capture/summary while all-series retains measured durations");
    expect(metrics.steady_durations[0].count==0 && metrics.durations[0].capture_samples==1 && metrics.durations[0].summary_samples==1,"Loop intervals must inherit prior frame instrumentation tags");
    expect(metrics.capture_frames==1 && metrics.summary_frames==1,"Late-known instrumentation tags must increment frame counts once");
}
void successful_log_calls_are_summed_without_recursion() {
    FrameMetrics metrics;metrics.begin_frame(0,{});
    metrics.log_success(10,20);metrics.log_success(30,70);metrics.finish_log();
    expect(metrics.durations[3].count==1 && metrics.durations[3].sum_us==50,"Log metric must aggregate successful calls into one sample-frame total");
}
void log_duration_errors_exclude_frame_parameterized() {
    for(unsigned failure=0;failure<2;++failure) {
        FrameMetrics metrics;metrics.begin_frame(0,{});
        if(failure==0) metrics.log_success(2,1);
        else {metrics.log_success(0,maximum);metrics.log_success(0,1);}
        metrics.finish_log();
        expect(metrics.durations[3].invalid && metrics.durations[3].excluded==1 && metrics.durations[3].count==0,"Invalid log sample must be explicitly excluded, never wrapped");
    }
}
void intercepted_frame_categories_are_excluded() {
    FrameMetrics metrics;metrics.begin_frame(100,{},true);metrics.record(MetricCategory::step,50);
    metrics.begin_frame(10000000,{});metrics.record(MetricCategory::step,20);
    expect(metrics.durations[0].count==0 && metrics.durations[1].count==1 && metrics.durations[1].excluded==1,"Explicit interception must exclude affected frame and reanchor without duration inference");
}
void invalid_category_is_rejected_before_regression() {
    FrameMetrics metrics;
    try {metrics.record_span(MetricCategory::loop_interval,2,1);}
    catch(const std::invalid_argument&) {return;}
    throw std::runtime_error("Loop interval must only be recorded by begin_frame, including regressed spans");
}
}
void* operator new(std::size_t size) {++allocations;if(void* value=std::malloc(size ? size : 1)) return value;throw std::bad_alloc();}
void* operator new[](std::size_t size) {return ::operator new(size);}
void operator delete(void* pointer) noexcept {std::free(pointer);}
void operator delete[](void* pointer) noexcept {std::free(pointer);}
void operator delete(void* pointer,std::size_t) noexcept {std::free(pointer);}
void operator delete[](void* pointer,std::size_t) noexcept {std::free(pointer);}
int main() {
    unsigned failed=0;
    for(auto test:{buckets_and_strict_thresholds_parameterized,maximum_keeps_first_frame_on_tie,arithmetic_overflow_excludes_whole_sample_parameterized,
                  frame_index_overflow_cannot_wrap,clock_regression_excludes_and_reanchors,ps_intercept_reanchors_without_gap_assumption_parameterized,
                  duration_categories_keep_capture_and_summary_tags,summaries_are_bounded_periodic_and_explicit,hot_path_has_no_heap_allocations,
                  duration_before_first_frame_is_excluded,capture_and_summary_are_excluded_from_steady_series,successful_log_calls_are_summed_without_recursion,
                  log_duration_errors_exclude_frame_parameterized,intercepted_frame_categories_are_excluded,invalid_category_is_rejected_before_regression}) {
        try {test();} catch(const std::exception& error) {std::cerr<<error.what()<<'\n';++failed;}
    }
    std::cout<<"frame metrics cases=15 failed="<<failed<<'\n';return failed ? 1 : 0;
}
