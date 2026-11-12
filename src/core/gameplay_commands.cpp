#include "gameplay_commands.hpp"
#include <algorithm>
#include <map>
#include <set>
#include <stdexcept>
#include <tuple>

namespace celeste::gameplay_commands {
namespace {
using Kind=draw_order::OwnerKind;
using Image=decal_commands::DecalCommand;
constexpr std::size_t absent=std::size_t(-1);
bool persistent(Kind kind) {
    switch(kind) {
    case Kind::background_tiles: case Kind::solid_tiles: case Kind::player:
    case Kind::particle_system_back: case Kind::particle_system_mid: case Kind::particle_system_front:
    case Kind::hud_display: return true;
    case Kind::decal: case Kind::scene_helper: case Kind::wind: case Kind::spikes:
    case Kind::jumpthru_platform: case Kind::strawberry: case Kind::spring: return false;
    }
    throw std::invalid_argument("Unknown gameplay owner kind");
}
class Assembly final {
public:
    Assembly(const draw_order::DrawProjection& projection,const Inputs& inputs):projection(projection),inputs(inputs),
        streams(projection.dispatch.size()),declared(projection.dispatch.size(),false),empty(projection.dispatch.size()) {
        if(!projection.decal_gap_rooms.empty()) throw std::invalid_argument("Unmapped authored gameplay decal rooms");
        std::set<Kind> globals;
        std::set<std::tuple<Kind,std::string,int,bool>> semantic;
        std::vector<std::size_t> membership(projection.live.size(),absent);
        for(std::size_t dispatch=0;dispatch<projection.dispatch.size();++dispatch) {
            const auto index=projection.dispatch[dispatch];
            if(index>=projection.live.size() || membership[index]!=absent)
                throw std::invalid_argument("Invalid or duplicate gameplay dispatch index");
            membership[index]=dispatch;
        }
        for(std::size_t index=0;index<projection.live.size();++index) {
            const auto& owner=projection.live[index];
            const bool global=persistent(owner.kind);
            if(!owner.identity || !owners.emplace(owner.identity,index).second)
                throw std::invalid_argument("Duplicate or zero gameplay owner identity");
            if(global ? (owner.room || owner.authored_id!=-1 || !globals.insert(owner.kind).second) : !owner.room)
                fail(owner.identity,"Invalid persistent/authored gameplay owner binding");
            if(!global && !semantic.emplace(owner.kind,owner.room->name,owner.authored_id,
                                           owner.kind==Kind::decal && owner.sort_depth_band>0).second)
                fail(owner.identity,"Duplicate semantic gameplay owner");
            if(owner.kind==Kind::hud_display) {
                if(owner.visible || !owner.hud_excluded || membership[index]!=absent)
                    fail(owner.identity,"HUD must be explicitly excluded from gameplay capture");
                excluded.push_back({owner.identity,ExclusionReason::hud_outside_gameplay_capture});
            } else if(!owner.visible || owner.hud_excluded || membership[index]==absent) {
                fail(owner.identity,"Gameplay live owner lacks unique dispatch membership");
            }
            if(membership[index]!=absent) dispatches.emplace(owner.identity,membership[index]);
        }
        if(inputs.sheets) for(const auto& sheet:*inputs.sheets) {
            if(sheet.name.empty() || sheet.width<=0 || sheet.height<=0 || !sheets.emplace(sheet.name,&sheet).second)
                throw std::invalid_argument("Invalid or duplicate gameplay sheet dimensions");
        }
    }
    const draw_order::DrawOwner& owner(std::uint64_t identity,Kind kind) const {
        const auto found=owners.find(identity);
        if(found==owners.end()) fail(identity,"Unused producer has no live gameplay owner");
        const auto& result=projection.live[found->second];
        if(result.kind!=kind || !dispatches.count(identity)) fail(identity,"Producer kind/dispatch binding mismatch");
        return result;
    }
    std::size_t declare(std::uint64_t identity,Kind kind) {
        owner(identity,kind);
        const auto dispatch=dispatches.at(identity);
        if(declared[dispatch]) fail(identity,"Duplicate gameplay producer declaration");
        declared[dispatch]=true;
        return dispatch;
    }
    void append(const Image& image,Kind kind,int authored_id,Component component,unsigned piece,
                std::optional<std::size_t>& previous,std::optional<std::size_t> expected_dispatch={}) {
        const auto& binding=owner(image.identity,kind);
        const auto dispatch=dispatches.at(image.identity);
        if((previous && dispatch<*previous) || (expected_dispatch && dispatch!=*expected_dispatch))
            fail(image.identity,"Producer subsequence disagrees with gameplay dispatch");
        previous=dispatch;
        if(image.room!=(binding.room?binding.room->name:"") || authored_id!=binding.authored_id)
            fail(image.identity,"Producer semantic room/entity binding mismatch");
        if(kind==Kind::decal && (image.ordinal!=binding.authored_id || image.background!=(binding.sort_depth_band>0) ||
                               image.texture!=binding.texture || (image.slice>=0)!=binding.banner))
            fail(image.identity,"Producer semantic decal layer/ordinal/component binding mismatch");
        if(empty[dispatch] || piece!=streams[dispatch].size()) fail(image.identity,"Duplicate or out-of-order gameplay component piece");
        const auto sheet=sheets.find(image.sheet);
        if(sheet==sheets.end()) fail(image.identity,"Missing original gameplay sheet dimensions");
        const auto& dimensions=*sheet->second;
        if(image.source_x<0 || image.source_y<0 || image.source_width<0 || image.source_height<0 ||
           image.source_width>dimensions.width || image.source_height>dimensions.height ||
           image.source_x>dimensions.width-image.source_width || image.source_y>dimensions.height-image.source_height)
            fail(image.identity,"Gameplay source rectangle exceeds original sheet");
        streams[dispatch].push_back({image,component,piece,dispatch,dimensions.width,dimensions.height,
            decal_commands::project_geometry(image,dimensions.width,dimensions.height)});
        declared[dispatch]=true;
    }
    void project() {
        std::optional<std::size_t> previous;
        if(inputs.decals) {
            if(!inputs.decals->deferred.empty()) throw std::invalid_argument("Deferred gameplay decal commands are incomplete");
            for(const auto& image:inputs.decals->commands) append(image,Kind::decal,image.ordinal,
                image.slice<0?Component::decal_image:Component::banner,image.slice<0?0:unsigned(image.slice),previous);
        }
        previous.reset();
        if(inputs.spikes) for(const auto& spike:*inputs.spikes) {
            Image image;
            image.identity=spike.identity;image.room=spike.room;image.texture=spike.texture;image.sheet=spike.sheet;
            image.source_x=spike.source_x;image.source_y=spike.source_y;
            image.source_width=spike.source_width;image.source_height=spike.source_height;
            image.position=spike.position;image.origin=spike.origin;image.scale=spike.scale;image.color=spike.color;
            image.rotation=spike.rotation;image.effects=spike.effects;
            if(spike.piece<0) fail(spike.identity,"Negative Spike piece");
            append(image,Kind::spikes,spike.authored_id,Component::image,unsigned(spike.piece),previous);
        }
        previous.reset();
        if(inputs.jumpthrus) for(const auto& command:*inputs.jumpthrus)
            append(command.image,Kind::jumpthru_platform,command.authored_id,Component::image,command.piece,previous,command.dispatch_index);
        previous.reset();
        if(inputs.strawberries) for(const auto& command:*inputs.strawberries)
            append(command,Kind::strawberry,command.authored_id,Component::sprite,0,previous);
        previous.reset();
        if(inputs.springs) for(const auto& command:*inputs.springs) {
            if(command.piece>8) fail(command.image.identity,"Unsupported Spring component piece");
            append(command.image,Kind::spring,command.authored_id,command.piece==8?Component::sprite:Component::direct,
                   command.piece,previous,command.dispatch_index);
        }
        if(inputs.player) player(*inputs.player);
        if(inputs.terrain) terrain(*inputs.terrain);
        for(const auto& producer:inputs.empty) {
            const auto found=owners.find(producer.identity);
            if(found==owners.end()) fail(producer.identity,"Unused empty gameplay producer");
            const auto kind=projection.live[found->second].kind;
            const bool valid=(producer.reason==EmptyReason::scene_helper_has_no_capture_calls && kind==Kind::scene_helper) ||
                (producer.reason==EmptyReason::wind_has_no_capture_calls && kind==Kind::wind) ||
                (producer.reason==EmptyReason::particle_system_has_no_active_images &&
                 (kind==Kind::particle_system_back || kind==Kind::particle_system_front));
            if(!valid) fail(producer.identity,"Empty gameplay producer policy does not cover owner kind");
            const auto dispatch=declare(producer.identity,kind);
            empty[dispatch]=producer.reason;
        }
        for(std::size_t dispatch=0;dispatch<streams.size();++dispatch) {
            const auto& binding=projection.live[projection.dispatch[dispatch]];
            if(!declared[dispatch]) fail(binding.identity,binding.kind==Kind::particle_system_mid?
                "Missing gameplay producer: Particle mid requires committed integration":"Missing gameplay producer");
            if(binding.kind==Kind::spring && streams[dispatch].size()!=9) fail(binding.identity,"Incomplete Spring component stream");
        }
    }
    const draw_order::DrawProjection& projection;
    const Inputs& inputs;
    std::vector<std::vector<Command>> streams;
    std::vector<bool> declared;
    std::vector<std::optional<EmptyReason>> empty;
    std::vector<ExcludedOwner> excluded;
private:
    [[noreturn]] static void fail(std::uint64_t identity,const char* message) {
        throw std::invalid_argument(std::string(message)+"; owner="+std::to_string(identity));
    }
    std::map<std::uint64_t,std::size_t> owners,dispatches;
    std::map<std::string,const terrain::Sheet*> sheets;
    void player(const CachedPlayer& cache) {
        const auto dispatch=declare(cache.identity,Kind::player);
        if(cache.mapping.size()!=cache.bank.frames.size() || (cache.live?cache.draws.size()!=2 && cache.draws.size()!=22:cache.draws.size()!=40))
            fail(cache.identity,"Incomplete cached Player branch/original atlas mapping");
        std::set<std::string> aliases;
        for(std::size_t index=0;index<cache.mapping.size();++index) {
            const auto& frame=cache.bank.frames[index];
            const auto& logical=cache.mapping[index];
            const auto sheet=sheets.find(logical.sheet);
            if(logical.name!=frame.name || !aliases.insert(logical.name).second || logical.width!=frame.width || logical.height!=frame.height ||
               logical.width<0 || logical.height<0 || logical.x<0 || logical.y<0 ||
               logical.width>logical.sheet_width || logical.height>logical.sheet_height ||
               logical.x>logical.sheet_width-logical.width || logical.y>logical.sheet_height-logical.height || sheet==sheets.end() ||
               sheet->second->width!=logical.sheet_width || sheet->second->height!=logical.sheet_height)
                fail(cache.identity,"Cached Player frame lacks original atlas alias/dimensions");
        }
        std::optional<std::size_t> previous;
        for(unsigned piece=0;piece<cache.draws.size();++piece) {
            const auto& draw=cache.draws[piece];
            if(draw.frame>=cache.bank.frames.size()) fail(cache.identity,"Cached Player frame is out of range");
            const auto& frame=cache.bank.frames[draw.frame];
            const auto& logical=cache.mapping[draw.frame];
            Image image;
            image.identity=cache.identity;image.texture=frame.name;image.sheet=logical.sheet;
            image.source_x=logical.x;image.source_y=logical.y;image.source_width=logical.width;image.source_height=logical.height;
            image.position=draw.position;image.origin={draw.origin.x-frame.trim_x,draw.origin.y-frame.trim_y};
            image.scale=draw.scale;image.rotation=draw.rotation;image.color=draw.color;
            const auto component=!cache.live?Component::direct:piece+2<cache.draws.size()?Component::player_hair:
                piece+2==cache.draws.size()?Component::player_sprite:Component::sprite;
            append(image,Kind::player,-1,component,piece,previous,dispatch);
        }
    }
    void terrain(const TerrainInput& input) {
        for(const bool background:{true,false}) {
            const auto identity=background?input.background_identity:input.foreground_identity;
            const auto kind=background?Kind::background_tiles:Kind::solid_tiles;
            declare(identity,kind);
            std::optional<std::size_t> previous;
            unsigned piece=0;
            const auto window=input.catalog.project(background,input.camera,input.viewport,[&](const auto& command) {
                if(command.material>=input.catalog.materials().size()) fail(identity,"Invalid terrain material index");
                const auto& material=input.catalog.materials()[command.material];
                if(material.sheet<0 || std::size_t(material.sheet)>=input.catalog.sheets().size()) fail(identity,"Invalid terrain sheet index");
                const auto& sheet=input.catalog.sheets()[material.sheet];
                const auto dimensions=sheets.find(sheet.name);
                if(dimensions==sheets.end() || dimensions->second->width!=sheet.width || dimensions->second->height!=sheet.height)
                    fail(identity,"Terrain original sheet dimensions mismatch");
                Image image;
                image.identity=identity;image.texture=material.source;image.sheet=sheet.name;
                image.source_x=material.u;image.source_y=material.v;image.source_width=material.width;image.source_height=material.height;
                image.position=command.position;
                append(image,kind,-1,Component::tile_grid,piece++,previous);
            });
            if(window.outside_catalog) fail(identity,"Gameplay terrain window exceeds catalog coverage");
        }
    }
};
}
Schedule assemble(const draw_order::DrawProjection& projection,const Inputs& inputs) {
    Assembly assembly(projection,inputs);
    assembly.project();
    Schedule result;
    result.excluded_=std::move(assembly.excluded);
    for(std::size_t dispatch=0;dispatch<projection.dispatch.size();++dispatch) {
        const auto& owner=projection.live[projection.dispatch[dispatch]];
        const auto begin=result.commands_.size();
        auto& stream=assembly.streams[dispatch];
        result.commands_.insert(result.commands_.end(),std::make_move_iterator(stream.begin()),std::make_move_iterator(stream.end()));
        result.ranges_.push_back({owner.kind,owner.identity,owner.room?owner.room->name:"",owner.authored_id,
            owner.kind==Kind::decal && owner.sort_depth_band>0,begin,result.commands_.size(),assembly.empty[dispatch]});
    }
    return result;
}
}
