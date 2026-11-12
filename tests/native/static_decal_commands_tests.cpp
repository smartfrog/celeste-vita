#include "assets.hpp"
#include "decal_commands.hpp"
#include <algorithm>
#include <cmath>
#include <iostream>
#include <limits>
#include <memory>
#include <stdexcept>
#include <string>
#include <utility>
#include <vector>

using namespace celeste;
using namespace celeste::decal_commands;
using namespace celeste::diagnostic;
namespace {
constexpr const char* input_sha = "fd73f8a2311fa5737ded550cbad4b75c85b7686b36432f59185e940fcb65fcfe";
constexpr const char* map_sha = "ace1892261c03aa766f45aaa38cb2cd60a8823c34eda673f5b2ed8ab31c890ab";
constexpr const char* decal_source_sha = "81d04a56cb9b5cb981f3c7823388bed6082db2d5755d364c15c35bbcaf8b7746";
constexpr const char* atlas_sha = "b75f913d315bd641c35a4990d9041b238c0d9ef3f8b1247ec557de8a9defc1cc";
constexpr const char* authored_sha = "1eb4bcb699363754df20ddf9b6f7b21738401cddf53e961755127f3ba5fda350";
constexpr std::uint64_t identity_namespace = 0x6000'0000'0000'0000ull;

void require(bool condition,const char* message) { if(!condition) throw std::runtime_error(message); }

std::string replace_once(std::string text,const std::string& old,const std::string& value) {
    const auto at=text.find(old);
    require(at!=std::string::npos,"Mutation target stands absent");
    text.replace(at,old.size(),value);
    return text;
}

struct OwnerSpec {
    bool background;
    int ordinal;
    std::string texture;
    int x,y,scale_x,scale_y;
    bool banner;
    unsigned family;
};
struct RoomSpec {
    std::string name;
    RoomBounds bounds;
    int raw_height;
    std::vector<OwnerSpec> owners;
    int background,foreground;
};
struct Dataset {
    std::unique_ptr<RoomCatalog> rooms;
    std::vector<draw_order::AuthoredDecalOwners> authored;
    std::string cdo1;
    std::string catalog;
};

std::vector<RoomSpec> authored_specs() {
    std::vector<RoomSpec> rooms;
    int static_index=0,banner_index=0;
    const auto add=[&](RoomSpec& room,bool background,int ordinal,bool banner) {
        OwnerSpec owner{background,ordinal,{},0,0,1,1,banner,0};
        owner.family=unsigned(static_index%23);
        owner.texture=banner ? "synthetic/banner"+std::to_string(banner_index++)+".png"
                             : "synthetic/static"+std::to_string(owner.family)+".png";
        if(!banner) ++static_index;
        owner.x=10+ordinal*3+(background?0:40);
        owner.y=20+ordinal*2+(background?0:80);
        owner.scale_x=static_index%7==0?-1:1;
        owner.scale_y=static_index%11==0?-1:1;
        room.owners.push_back(std::move(owner));
    };
    RoomSpec first{"1",{0,0,320,180},184,{},25,4};
    for(int ordinal=0;ordinal<20;++ordinal) add(first,true,ordinal,false);
    for(int ordinal=20;ordinal<25;++ordinal) add(first,true,ordinal,true);
    for(int ordinal=0;ordinal<2;++ordinal) add(first,false,ordinal,false);
    for(int ordinal=2;ordinal<4;++ordinal) add(first,false,ordinal,true);
    RoomSpec second{"2",{240,-184,320,180},184,{},18,5};
    for(int ordinal=0;ordinal<8;++ordinal) add(second,true,ordinal,false);
    for(int ordinal=8;ordinal<10;++ordinal) add(second,true,ordinal,true);
    add(second,true,10,false);
    for(int ordinal=11;ordinal<13;++ordinal) add(second,true,ordinal,true);
    for(int ordinal=13;ordinal<18;++ordinal) add(second,true,ordinal,false);
    for(int ordinal=0;ordinal<5;++ordinal) add(second,false,ordinal,false);
    rooms.push_back(std::move(first));
    rooms.push_back(std::move(second));
    return rooms;
}

std::string cdo1_text(const std::vector<RoomSpec>& rooms) {
    std::string text=std::string("CDO1\n")+input_sha+"\n"+map_sha+"\n"+decal_source_sha+"\n6000000000000000\n2\n";
    for(const auto& room:rooms) {
        text+="R "+room.name+' '+std::to_string(room.bounds.x)+' '+std::to_string(room.bounds.y)+' '+
              std::to_string(room.bounds.width)+' '+std::to_string(room.bounds.height)+' '+
              std::to_string(room.raw_height)+' '+std::to_string(room.background)+' '+
              std::to_string(room.foreground)+'\n';
        for(const auto& owner:room.owners)
            text+=std::string(owner.background?"B ":"F ")+std::to_string(owner.ordinal)+' '+owner.texture+' '+
                  std::to_string(owner.x)+' '+std::to_string(owner.y)+' '+std::to_string(owner.scale_x)+' '+
                  std::to_string(owner.scale_y)+' '+std::to_string(owner.banner?1:0)+'\n';
    }
    return text;
}

std::string family_row(unsigned index) {
    const int x=8+int(index)*5,y=16+int(index)*7,width=1+int(index)%9,height=1+int(index*3)%11;
    const int offset_x=-7+int(index)%13,offset_y=-9+int(index)%17;
    const int frame_width=16+int(index)%4*8,frame_height=16+int(index*2)%5*8;
    return "Gameplay0 "+std::to_string(x)+' '+std::to_string(y)+' '+std::to_string(width)+' '+
           std::to_string(height)+' '+std::to_string(offset_x)+' '+std::to_string(offset_y)+' '+
           std::to_string(frame_width)+' '+std::to_string(frame_height)+
           " synthetic/static"+std::to_string(index)+".png\n";
}

std::string catalog_text(const std::vector<RoomSpec>& rooms) {
    std::string text=std::string("CDSC1\n")+input_sha+"\n"+map_sha+"\n"+decal_source_sha+"\n"+
                     atlas_sha+"\n"+authored_sha+"\n23\n";
    for(unsigned index=0;index<23;++index) text+=family_row(index);
    int owners=0,deferred=0;
    for(const auto& room:rooms) for(const auto& owner:room.owners) {
        if(owner.banner) ++deferred; else ++owners;
    }
    text+=std::to_string(owners)+"\n";
    for(const auto& room:rooms) for(const auto& owner:room.owners) if(!owner.banner)
        text+="O "+room.name+' '+(owner.background?"B ":"F ")+std::to_string(owner.ordinal)+' '+
              std::to_string(owner.family)+'\n';
    text+=std::to_string(deferred)+"\n";
    for(const auto& room:rooms) for(const auto& owner:room.owners) if(owner.banner)
        text+="D "+room.name+' '+(owner.background?"B ":"F ")+std::to_string(owner.ordinal)+' '+owner.texture+'\n';
    return text;
}

Dataset dataset() {
    const auto rooms=authored_specs();
    const auto cdo1=cdo1_text(rooms);
    auto catalog=std::make_unique<RoomCatalog>(std::vector<RoomDefinition>{
        {"1",{0,0,320,180},49,{19,144},{}},
        {"2",{240,-184,320,180},50,{264,-24},{}}});
    auto authored=parse_authored_decals(cdo1,checksum(cdo1),*catalog);
    auto descriptor=catalog_text(rooms);
    return {std::move(catalog),std::move(authored),cdo1,descriptor};
}

const draw_order::DrawOwner& owner(const Dataset& data,const std::string& room,bool background,int ordinal) {
    for(const auto& group:data.authored) {
        if(group.room->name!=room) continue;
        for(const auto& value:group.owners)
            if(value.sort_depth_band>0==background && value.authored_id==ordinal) return value;
    }
    throw std::runtime_error("Synthetic authored owner is missing");
}

const StaticDecalOwner& descriptor(const StaticDecalCatalog& parsed,std::uint64_t identity) {
    for(const auto& value:parsed.owners) if(value.identity==identity) return value;
    throw std::runtime_error("Synthetic descriptor is missing");
}

draw_order::DrawProjection projection_of(std::vector<const draw_order::DrawOwner*> owners) {
    draw_order::DrawProjection drawn;
    for(const auto* value:owners) {
        drawn.dispatch.push_back(drawn.live.size());
        drawn.live.push_back(*value);
    }
    return drawn;
}

void static_command_uses_atlas_frame_and_center_offset() {
    auto data=dataset();
    const auto parsed=parse_static_decal_catalog(data.catalog,checksum(data.catalog),data.authored);
    const auto& authored=owner(data,"1",true,0);
    const auto drawn=projection_of({&authored});
    const auto result=project(drawn,parsed);
    require(result.commands.size()==1 && result.deferred.empty(),"One static command is required");
    const auto& command=result.commands.front();
    const auto& frame=parsed.families[descriptor(parsed,authored.identity).family];
    require(command.identity==authored.identity && command.room=="1" && command.background &&
            command.ordinal==0,"Static command identity/room/layer changed");
    require(command.texture==authored.texture && command.sheet=="Gameplay0","Static texture/sheet changed");
    require(command.source_x==frame.x && command.source_y==frame.y && command.source_width==frame.width &&
            command.source_height==frame.height,"Atlas source rectangle changed");
    require(command.position.x==authored.position.x && command.position.y==authored.position.y,
            "World position changed");
    require(command.origin.x==frame.frame_width/2.f+frame.offset_x &&
            command.origin.y==frame.frame_height/2.f+frame.offset_y,
            "Center-minus-draw-offset origin changed");
    require(command.scale.x==authored.scale.x && command.scale.y==authored.scale.y,"Signed scale changed");
    require(command.color.r==255 && command.color.g==255 && command.color.b==255 && command.color.a==255,
            "Static decal modulation is not white");
    require(command.rotation==0 && command.effects=="None","Static decal rotation/effects changed");
}

void source_rectangle_is_preserved_and_not_trimmed() {
    auto data=dataset();
    const auto parsed=parse_static_decal_catalog(data.catalog,checksum(data.catalog),data.authored);
    const auto& authored=owner(data,"1",false,0);
    const auto result=project(projection_of({&authored}),parsed);
    const auto& frame=parsed.families[descriptor(parsed,authored.identity).family];
    require(frame.width!=frame.frame_width || frame.height!=frame.frame_height,
            "Fixture must retain a crop/frame size difference");
    require(result.commands.front().source_width==frame.width && result.commands.front().source_height==frame.height,
            "Source crop must pass through unchanged");
    require(result.commands.front().origin.x!=frame.width/2.f,
            "Origin must use the frame size, not the trimmed crop size");
}

void negative_scale_preserves_signed_axes_and_origin() {
    auto data=dataset();
    const auto parsed=parse_static_decal_catalog(data.catalog,checksum(data.catalog),data.authored);
    const draw_order::DrawOwner* selected=nullptr;
    for(const auto& group:data.authored) for(const auto& value:group.owners) {
        if(!value.banner && (value.scale.x<0 || value.scale.y<0)) { selected=&value; break; }
        if(selected) break;
    }
    require(selected!=nullptr,"Fixture must include a mirrored static decal");
    const auto result=project(projection_of({selected}),parsed);
    const auto& command=result.commands.front();
    const auto& frame=parsed.families[descriptor(parsed,selected->identity).family];
    require(command.scale.x==selected->scale.x && command.scale.y==selected->scale.y,
            "Negative scale must preserve both signed axes");
    require(command.source_x==frame.x && command.source_y==frame.y,
            "Negative scale must not reverse or normalize the source rectangle");
    require(command.origin.x==frame.frame_width/2.f+frame.offset_x &&
            command.origin.y==frame.frame_height/2.f+frame.offset_y,
            "Negative scale must not move the center origin");
}

void command_order_follows_visible_dispatch() {
    auto data=dataset();
    const auto parsed=parse_static_decal_catalog(data.catalog,checksum(data.catalog),data.authored);
    const auto& first=owner(data,"1",true,3);
    const auto& second=owner(data,"2",false,2);
    const auto& third=owner(data,"2",true,0);
    const auto result=project(projection_of({&third,&first,&second}),parsed);
    require(result.commands.size()==3,"Three dispatched statics must emit three commands");
    require(result.commands[0].identity==third.identity && result.commands[1].identity==first.identity &&
            result.commands[2].identity==second.identity,"Static command order must follow native dispatch");
}

void banner_owner_is_deferred_with_identity_and_key() {
    auto data=dataset();
    const auto parsed=parse_static_decal_catalog(data.catalog,checksum(data.catalog),data.authored);
    const auto& authored=owner(data,"1",true,20);
    require(authored.banner,"Fixture must select a Banner owner");
    const auto result=project(projection_of({&authored}),parsed);
    require(result.commands.empty(),"Banner owners must never produce static commands");
    require(result.deferred.size()==1,"Banner owner must be reported as deferred");
    const auto& deferred=result.deferred.front();
    require(deferred.identity==authored.identity && deferred.room=="1" && deferred.background &&
            deferred.ordinal==20 && deferred.texture==authored.texture,
            "Deferred Banner identity/key changed");
}

void mixed_static_and_banner_keep_dispatch_order() {
    auto data=dataset();
    const auto parsed=parse_static_decal_catalog(data.catalog,checksum(data.catalog),data.authored);
    const auto& first=owner(data,"1",true,1);
    const auto& banner=owner(data,"2",true,8);
    const auto& last=owner(data,"2",false,4);
    const auto result=project(projection_of({&first,&banner,&last}),parsed);
    require(result.commands.size()==2 && result.deferred.size()==1,"Mixed dispatch split changed");
    require(result.commands[0].identity==first.identity && result.commands[1].identity==last.identity,
            "Static commands must skip deferred Banner owners without reordering");
    require(result.deferred[0].identity==banner.identity,"Deferred owner must retain dispatch position data");
}

void undispatched_owner_is_not_emitted() {
    auto data=dataset();
    const auto parsed=parse_static_decal_catalog(data.catalog,checksum(data.catalog),data.authored);
    const auto& authored=owner(data,"1",true,0);
    draw_order::DrawProjection drawn;
    drawn.live.push_back(authored);
    const auto result=project(drawn,parsed);
    require(result.commands.empty() && result.deferred.empty(),"Undispatched owners must not emit commands");
}

void missing_static_descriptor_rejects() {
    auto data=dataset();
    auto parsed=parse_static_decal_catalog(data.catalog,checksum(data.catalog),data.authored);
    const auto& authored=owner(data,"1",true,0);
    parsed.owners.erase(std::remove_if(parsed.owners.begin(),parsed.owners.end(),
        [&](const StaticDecalOwner& value) { return value.identity==authored.identity; }),parsed.owners.end());
    try { project(projection_of({&authored}),parsed); }
    catch(const std::invalid_argument&) { return; }
    throw std::runtime_error("A missing static descriptor must reject");
}

void unknown_deferred_descriptor_rejects() {
    auto data=dataset();
    auto parsed=parse_static_decal_catalog(data.catalog,checksum(data.catalog),data.authored);
    const auto& authored=owner(data,"1",true,20);
    parsed.deferred.clear();
    try { project(projection_of({&authored}),parsed); }
    catch(const std::invalid_argument&) { return; }
    throw std::runtime_error("An unknown Banner descriptor must reject");
}

void duplicate_catalog_identity_rejects() {
    auto data=dataset();
    auto parsed=parse_static_decal_catalog(data.catalog,checksum(data.catalog),data.authored);
    parsed.owners.push_back(parsed.owners.front());
    try { project(projection_of({}),parsed); }
    catch(const std::invalid_argument&) { return; }
    throw std::runtime_error("Duplicate static descriptor identity must reject");
}

void duplicate_deferred_identity_rejects() {
    auto data=dataset();
    auto parsed=parse_static_decal_catalog(data.catalog,checksum(data.catalog),data.authored);
    parsed.deferred.push_back(parsed.deferred.front());
    try { project(projection_of({}),parsed); }
    catch(const std::invalid_argument&) { return; }
    throw std::runtime_error("Duplicate deferred identity must reject");
}

void descriptor_room_mismatch_rejects() {
    auto data=dataset();
    auto parsed=parse_static_decal_catalog(data.catalog,checksum(data.catalog),data.authored);
    const auto& authored=owner(data,"1",true,0);
    for(auto& value:parsed.owners) if(value.identity==authored.identity) value.room="2";
    try { project(projection_of({&authored}),parsed); }
    catch(const std::invalid_argument&) { return; }
    throw std::runtime_error("A foreign descriptor room must reject");
}

void descriptor_layer_mismatch_rejects() {
    auto data=dataset();
    auto parsed=parse_static_decal_catalog(data.catalog,checksum(data.catalog),data.authored);
    const auto& authored=owner(data,"1",true,0);
    for(auto& value:parsed.owners) if(value.identity==authored.identity) value.background=false;
    try { project(projection_of({&authored}),parsed); }
    catch(const std::invalid_argument&) { return; }
    throw std::runtime_error("A descriptor layer mismatch must reject");
}

void descriptor_ordinal_mismatch_rejects() {
    auto data=dataset();
    auto parsed=parse_static_decal_catalog(data.catalog,checksum(data.catalog),data.authored);
    const auto& authored=owner(data,"1",true,0);
    for(auto& value:parsed.owners) if(value.identity==authored.identity) value.ordinal=9;
    try { project(projection_of({&authored}),parsed); }
    catch(const std::invalid_argument&) { return; }
    throw std::runtime_error("A descriptor ordinal mismatch must reject");
}

void descriptor_texture_mismatch_rejects() {
    auto data=dataset();
    auto parsed=parse_static_decal_catalog(data.catalog,checksum(data.catalog),data.authored);
    const auto& authored=owner(data,"1",true,0);
    for(auto& value:parsed.owners) if(value.identity==authored.identity) value.texture="synthetic/other.png";
    try { project(projection_of({&authored}),parsed); }
    catch(const std::invalid_argument&) { return; }
    throw std::runtime_error("A descriptor texture mismatch must reject");
}

void invalid_scale_rejects_parameterized() {
    auto data=dataset();
    const auto parsed=parse_static_decal_catalog(data.catalog,checksum(data.catalog),data.authored);
    for(const float value:{0.f,2.f,-2.f,0.5f}) {
        auto selected=owner(data,"1",true,0);
        selected.scale={value,1};
        try { project(projection_of({&selected}),parsed); }
        catch(const std::invalid_argument&) { continue; }
        throw std::runtime_error("A non-signed static scale must reject");
    }
}

void nonfinite_geometry_rejects_parameterized() {
    auto data=dataset();
    const auto parsed=parse_static_decal_catalog(data.catalog,checksum(data.catalog),data.authored);
    for(const float value:{std::numeric_limits<float>::quiet_NaN(),std::numeric_limits<float>::infinity()}) {
        auto position=owner(data,"1",true,0);
        position.position={value,0};
        try { project(projection_of({&position}),parsed); }
        catch(const std::invalid_argument&) { continue; }
        throw std::runtime_error("A nonfinite static position must reject");
    }
}

void nonfinite_scale_rejects_parameterized() {
    auto data=dataset();
    const auto parsed=parse_static_decal_catalog(data.catalog,checksum(data.catalog),data.authored);
    for(const float value:{std::numeric_limits<float>::quiet_NaN(),std::numeric_limits<float>::infinity()}) {
        auto scale=owner(data,"1",true,0);
        scale.scale={1,value};
        try { project(projection_of({&scale}),parsed); }
        catch(const std::invalid_argument&) { continue; }
        throw std::runtime_error("A nonfinite static scale must reject");
    }
}

void bad_family_index_rejects() {
    auto data=dataset();
    auto parsed=parse_static_decal_catalog(data.catalog,checksum(data.catalog),data.authored);
    const auto& authored=owner(data,"1",true,0);
    for(auto& value:parsed.owners) if(value.identity==authored.identity) value.family=parsed.families.size();
    try { project(projection_of({&authored}),parsed); }
    catch(const std::invalid_argument&) { return; }
    throw std::runtime_error("An out-of-range family index must reject");
}

std::uint64_t expected_identity(std::string_view room,bool background,int ordinal) {
    return identity_namespace|(std::uint64_t(room=="2"?2:1)<<32)|
        (std::uint64_t(background?1:2)<<24)|std::uint64_t(ordinal+1);
}
void require_owner_identity(const StaticDecalOwner& value,const draw_order::DrawOwner& authored) {
    require(value.identity==authored.identity && value.identity==expected_identity(value.room,value.background,value.ordinal),
            "Catalog identity is not the verified authored identity");
}
void parser_accepts_pinned_metadata_counts() {
    auto data=dataset();
    const auto parsed=parse_static_decal_catalog(data.catalog,checksum(data.catalog),data.authored);
    require(parsed.families.size()==23 && parsed.owners.size()==41 && parsed.deferred.size()==11,
            "Authored static/deferred/family counts changed");
    for(const auto& value:parsed.owners) {
        const auto& authored=owner(data,value.room,value.background,value.ordinal);
        require_owner_identity(value,authored);
        require(value.texture==authored.texture,"Catalog family texture is not bound to its owner key");
    }
}

void parser_rejects_incorrect_identity_42() {
    auto data=dataset();
    const auto parsed=parse_static_decal_catalog(data.catalog,checksum(data.catalog),data.authored);
    auto value=parsed.owners.front();
    value.identity=42;
    auto authored=owner(data,value.room,value.background,value.ordinal);
    authored.identity=42;
    try { require_owner_identity(value,authored); }
    catch(const std::runtime_error&) { return; }
    throw std::runtime_error("Incorrect identity 42 passed the actual identity assertion");
}

void parser_rejects_bad_versions_and_pins_parameterized() {
    auto data=dataset();
    const std::vector<std::pair<std::string,std::string>> mutations{
        {"CDSC1","CDSC2"},{"CDSC1","CDO1"},
        {std::string(atlas_sha),std::string("b75f913d315bd641c35a4990d9041b238c0d9ef3f8b1247ec557de8a9defc1cd")},
        {std::string(authored_sha),std::string("1eb4bcb699363754df20ddf9b6f7b21738401cddf53e961755127f3ba5fda351")},
        {std::string(decal_source_sha),std::string("81d04a56cb9b5cb981f3c7823388bed6082db2d5755d364c15c35bbcaf8b7747")},
        {"\n23\n","\n22\n"},{"\n23\n","\n24\n"},
        {"\n41\n","\n40\n"},{"\n11\n","\n10\n"},
        {"O 1 B 0 0","O 1 X 0 0"},{"O 1 B 0 0","O 3 B 0 0"},
        {"O 1 B 0 0","O 1 B 0 23"},{"O 1 B 0 0","O 1 B 0 0\nO 1 B 0 0"},
        {"D 1 B 20 synthetic/banner0.png","D 1 B 20 synthetic/banner1.png"},
        {"D 1 B 20 synthetic/banner0.png","D 1 X 20 synthetic/banner0.png"},
        {"Gameplay0 8 16","Gameplay0 4096 16"},
        {"Gameplay0 8 16 1 1 -7 -9","Gameplay0 8 16 1 1 4097 -9"},
        {"Gameplay0 8 16 1 1 -7 -9 16 16","Gameplay0 8 16 1 1 -7 -9 0 16"}
    };
    for(const auto& mutation:mutations) {
        auto text=replace_once(data.catalog,mutation.first,mutation.second);
        try { parse_static_decal_catalog(text,checksum(text),data.authored); }
        catch(const std::invalid_argument&) { continue; }
        throw std::runtime_error("Malformed descriptor catalog was accepted: "+mutation.second);
    }
}

void parser_rejects_duplicate_family_texture() {
    auto data=dataset();
    auto text=replace_once(data.catalog,family_row(1),family_row(0));
    try { parse_static_decal_catalog(text,checksum(text),data.authored); }
    catch(const std::invalid_argument&) { return; }
    throw std::runtime_error("A duplicate atlas family texture was accepted");
}

void parser_rejects_truncation() {
    auto data=dataset();
    auto truncated=data.catalog;
    truncated.erase(truncated.find_last_of('\n'));
    try { parse_static_decal_catalog(truncated,checksum(truncated),data.authored); }
    catch(const std::invalid_argument&) { return; }
    throw std::runtime_error("A truncated descriptor catalog was accepted");
}

void parser_rejects_trailing_data() {
    auto data=dataset();
    auto trailing=data.catalog+"extra\n";
    try { parse_static_decal_catalog(trailing,checksum(trailing),data.authored); }
    catch(const std::invalid_argument&) { return; }
    throw std::runtime_error("Trailing descriptor data was accepted");
}

void parser_rejects_wrong_integrity() {
    auto data=dataset();
    try { parse_static_decal_catalog(data.catalog,checksum(data.catalog)^1,data.authored); }
    catch(const std::invalid_argument&) { return; }
    throw std::runtime_error("Wrong descriptor integrity was accepted");
}

void legacy_authored_parser_still_accepts_the_bound_metadata() {
    auto data=dataset();
    require(data.authored.size()==2 && data.authored[0].owners.size()==29 && data.authored[1].owners.size()==23,
            "Legacy authored parser counts changed");
    int banners=0,statics=0;
    for(const auto& group:data.authored) for(const auto& value:group.owners) {
        if(value.banner) ++banners; else ++statics;
    }
    require(statics==41 && banners==11,"Legacy authored static/Banner split changed");
}

void parser_rejects_missing_static_coverage() {
    auto data=dataset();
    auto parsed=parse_static_decal_catalog(data.catalog,checksum(data.catalog),data.authored);
    require(!parsed.owners.empty(),"Descriptor fixture must not be empty");
    auto text=data.catalog;
    const std::string line="O 1 B 0 0\n";
    const auto at=text.find(line);
    require(at!=std::string::npos,"First descriptor owner row is missing");
    text.erase(at,line.size());
    const std::string count="\n41\n";
    const auto count_at=text.find(count);
    text.replace(count_at,count.size(),"\n40\n");
    try { parse_static_decal_catalog(text,checksum(text),data.authored); }
    catch(const std::invalid_argument&) { return; }
    throw std::runtime_error("Missing static owner coverage was accepted");
}

void parser_rejects_missing_deferred_coverage() {
    auto data=dataset();
    auto text=data.catalog;
    const std::string line="D 1 B 20 synthetic/banner0.png\n";
    const auto at=text.find(line);
    require(at!=std::string::npos,"First deferred owner row is missing");
    text.erase(at,line.size());
    const std::string count="\n11\n";
    const auto count_at=text.find(count);
    text.replace(count_at,count.size(),"\n10\n");
    try { parse_static_decal_catalog(text,checksum(text),data.authored); }
    catch(const std::invalid_argument&) { return; }
    throw std::runtime_error("Missing Banner owner coverage was accepted");
}
}

int main() {
    int passed=0;
    const std::vector<std::pair<const char*,void(*)()>> tests{
        {"static_command_uses_atlas_frame_and_center_offset",static_command_uses_atlas_frame_and_center_offset},
        {"source_rectangle_is_preserved_and_not_trimmed",source_rectangle_is_preserved_and_not_trimmed},
        {"negative_scale_preserves_signed_axes_and_origin",negative_scale_preserves_signed_axes_and_origin},
        {"command_order_follows_visible_dispatch",command_order_follows_visible_dispatch},
        {"banner_owner_is_deferred_with_identity_and_key",banner_owner_is_deferred_with_identity_and_key},
        {"mixed_static_and_banner_keep_dispatch_order",mixed_static_and_banner_keep_dispatch_order},
        {"undispatched_owner_is_not_emitted",undispatched_owner_is_not_emitted},
        {"missing_static_descriptor_rejects",missing_static_descriptor_rejects},
        {"unknown_deferred_descriptor_rejects",unknown_deferred_descriptor_rejects},
        {"duplicate_catalog_identity_rejects",duplicate_catalog_identity_rejects},
        {"duplicate_deferred_identity_rejects",duplicate_deferred_identity_rejects},
        {"descriptor_room_mismatch_rejects",descriptor_room_mismatch_rejects},
        {"descriptor_layer_mismatch_rejects",descriptor_layer_mismatch_rejects},
        {"descriptor_ordinal_mismatch_rejects",descriptor_ordinal_mismatch_rejects},
        {"descriptor_texture_mismatch_rejects",descriptor_texture_mismatch_rejects},
        {"invalid_scale_rejects_parameterized",invalid_scale_rejects_parameterized},
        {"nonfinite_geometry_rejects_parameterized",nonfinite_geometry_rejects_parameterized},
        {"nonfinite_scale_rejects_parameterized",nonfinite_scale_rejects_parameterized},
        {"bad_family_index_rejects",bad_family_index_rejects},
        {"parser_accepts_pinned_metadata_counts",parser_accepts_pinned_metadata_counts},
        {"parser_rejects_incorrect_identity_42",parser_rejects_incorrect_identity_42},
        {"parser_rejects_bad_versions_and_pins_parameterized",parser_rejects_bad_versions_and_pins_parameterized},
        {"parser_rejects_duplicate_family_texture",parser_rejects_duplicate_family_texture},
        {"parser_rejects_truncation",parser_rejects_truncation},
        {"parser_rejects_trailing_data",parser_rejects_trailing_data},
        {"parser_rejects_wrong_integrity",parser_rejects_wrong_integrity},
        {"legacy_authored_parser_still_accepts_the_bound_metadata",legacy_authored_parser_still_accepts_the_bound_metadata},
        {"parser_rejects_missing_static_coverage",parser_rejects_missing_static_coverage},
        {"parser_rejects_missing_deferred_coverage",parser_rejects_missing_deferred_coverage}
    };
    for(const auto& [name,test]:tests) {
        try { test(); ++passed; }
        catch(const std::exception& error) { std::cerr<<name<<": "<<error.what()<<'\n'; return 1; }
    }
    std::cout<<passed<<" static decal command behaviors passed\n";
    return 0;
}
