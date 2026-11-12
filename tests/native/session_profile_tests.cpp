#include "session_profile.hpp"
#include "session_catalog_fixture.hpp"
#include <iostream>
#include <stdexcept>

using namespace celeste::diagnostic;
namespace {
void require(bool value,const char* message) { if(!value) throw std::runtime_error(message); }
template<class F> void rejects(F operation) {
    try { operation(); } catch(const std::invalid_argument&) { return; }
    throw std::runtime_error("Unsupported profile configuration must reject explicitly");
}
void default_call_preserves_selected_profile() {
    native_test::SessionCatalogFixture fixture;
    auto session=make_session(fixture.physical.world,&fixture.physical.frames);
    require(bool(session.lifecycle())==automatic_session_profile,"Default callers must retain the configured profile");
    if(session.lifecycle()) require(!session.lifecycle()->room_definition(),"Default app calls must not implicitly activate Room2");
}
void automatic_profile_forwards_borrowed_configuration() {
    native_test::SessionCatalogFixture fixture;
    auto session=make_session(fixture.physical.world,&fixture.physical.frames,&fixture.catalog,&fixture.owners);
    require(session.lifecycle() && session.lifecycle()->room_definition()==&fixture.catalog.first(),"Automatic profile must forward the exact catalog");
    require(native_test::catalog_room(*session.lifecycle(),fixture.catalog.first()).banners().size()==1,"Automatic profile must initialize provided visual owners");
    session.step({{},true,false});
    require(native_test::catalog_room(*session.lifecycle(),fixture.catalog.first()).banners().size()==1,"Automatic profile reset must retain metadata");
}
void legacy_arguments_reject_parameterized() {
    for(unsigned scenario=0;scenario<3;++scenario) {
        native_test::SessionCatalogFixture fixture;
        rejects([&] { make_session(fixture.physical.world,&fixture.physical.frames,
            scenario==1?nullptr:&fixture.catalog,scenario==0?nullptr:&fixture.owners); });
    }
}
void null_bank_behavior_remains_profile_specific() {
    native_test::SessionCatalogFixture fixture;
    if constexpr(automatic_session_profile) rejects([&] { make_session(fixture.physical.world,nullptr); });
    else { auto session=make_session(fixture.physical.world,nullptr);require(!session.presentation(),"Legacy null bank must stay supported"); }
}
}
int main() {
    try {
        default_call_preserves_selected_profile();
        null_bank_behavior_remains_profile_specific();
        if constexpr(automatic_session_profile) automatic_profile_forwards_borrowed_configuration();
        else legacy_arguments_reject_parameterized();
        std::cout<<"3 session profile behaviors passed automatic="<<automatic_session_profile<<'\n';
    } catch(const std::exception& error) { std::cerr<<error.what()<<'\n';return 1; }
}
