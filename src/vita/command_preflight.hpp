#pragma once
#include "decal_commands.hpp"
#include <cstddef>
#include <optional>
#include <variant>

namespace celeste::command_preflight {

struct Page {
    int id=0,width=0,height=0;
};

struct MaterialBinding {
    decal_commands::AtlasFrame original;
    int original_sheet_width=0,original_sheet_height=0;
    int page=0,packed_x=0,packed_y=0,packed_width=0,packed_height=0;
    bool rotated=false;
    std::vector<std::string> equivalent_aliases;
};

struct MaterialTable {
    std::vector<Page> pages;
    std::vector<MaterialBinding> bindings;
};

enum class Coverage { raster, semantic_zero_area_banner };

struct Policy {
    enum class ZeroAreaBanner { reject, accept_semantic_no_raster };
    ZeroAreaBanner zero_area_banner=ZeroAreaBanner::reject;
};

struct CommandInput {
    decal_commands::DecalCommand command;
    decal_commands::DecalGeometry geometry;
    Coverage coverage=Coverage::raster;
};

enum class FailureReason {
    invalid_metadata, ambiguous_material, unsupported_packing, missing_material,
    empty_crop, invalid_crop, nonfinite_input, invalid_geometry, nonfinite_output
};

struct Failure {
    FailureReason reason;
    std::optional<std::size_t> command_index,binding_index;
    std::uint64_t identity=0;
    std::string material,sheet;
    std::array<int,4> crop{};
    std::string detail;
};

struct ReadyCommand {
    decal_commands::DecalCommand command;
    decal_commands::DecalGeometry geometry;
    int page=0;
    Coverage coverage=Coverage::raster;
};

class ReadyFrame;
using Result=std::variant<ReadyFrame,Failure>;

class ReadyFrame final {
public:
    const std::vector<ReadyCommand>& commands() const { return commands_; }
    const std::vector<Page>& pages() const { return pages_; }
    std::size_t required_rgba_bytes() const { return required_rgba_bytes_; }
private:
    ReadyFrame()=default;
    std::vector<ReadyCommand> commands_;
    std::vector<Page> pages_;
    std::size_t required_rgba_bytes_=0;
    friend Result preflight(const MaterialTable&,const std::vector<CommandInput>&,const Policy&);
};

// texture must name the original frame alias, not merely its sheet or packed page.
// Callers must provide geometry projected with the binding's original sheet dimensions.
// This gate proves finite submission readiness, not Source pixel/raster equivalence.
// An empty frame succeeds only after table validation; the byte estimate covers all table pages.
// Semantic zero-area Banner commands retain their actual source NaN XY payload and are
// eligible only through an explicit Policy opt-in; the default remains whole-frame rejection.
Result preflight(const MaterialTable& table,const std::vector<CommandInput>& commands);
Result preflight(const MaterialTable& table,const std::vector<CommandInput>& commands,const Policy& policy);

}
