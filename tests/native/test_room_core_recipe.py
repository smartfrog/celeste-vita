import copy
import sys
from pathlib import Path
import unittest
import xml.etree.ElementTree as ET

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'scripts'))
from read_player_room_core_sources import presentation_profile
from prepare_player_room_core_oracle import project_text, callback_guards, remove_fixture_class, room_shared_support


def synthetic_room():
    return {'name': 'level', 'attributes': {'name': 'lvl_1', 'windPattern': 'None', 'underwater': False, 'space': False},
        'children': [
            {'name': 'entities', 'attributes': {}, 'children': [
                {'name': name, 'attributes': {'id': index}, 'children': []}
                for index, name in enumerate(['player', 'spikesUp', 'goldenBerry', 'spikesLeft', 'spikesUp', 'spikesUp', 'spikesUp'])]},
            {'name': 'triggers', 'attributes': {}, 'children': []},
            {'name': 'fgdecals', 'attributes': {}, 'children': [{'name': 'decal'}]},
            {'name': 'bgdecals', 'attributes': {}, 'children': [{'name': 'decal'}]},
            {'name': 'objtiles', 'attributes': {'innerText': '7,-1'}, 'children': []}]}


class RoomCoreRecipeTests(unittest.TestCase):
    def test_nested_baseline_sources_are_not_compiled_twice(self):
        project = ET.fromstring(project_text())
        self.assertEqual(project.findtext('PropertyGroup/EnableDefaultCompileItems'), 'false')
        self.assertEqual([entry.attrib['Include'] for entry in project.findall('ItemGroup/Compile')],
            ['Extracted.cs', 'Shared.cs', 'Geometry.cs', 'Services.cs', 'RoomCoreProbe.cs', 'RoomCoreGpu.cs', 'NativeImportGuard.cs', 'NativeImportGuardProbe.cs', 'RoomCoreExecution.cs', 'NativeAbiMetadataAudit.cs', 'PlatformIdentityFixture.cs', 'PlatformIdentityFixtureProbe.cs', 'RoomCoreRoomInput.cs', 'RoomCoreCaller.cs'])

    def test_excluded_callback_guard_throws_only_when_invoked(self):
        original = 'StateMachine.SetCallbacks(3, SwimUpdate);\n\tprivate int SwimUpdate()\n{ return 3; }'
        self.assertEqual(callback_guards(original, ''),
            ['private int SwimUpdate() { throw new DeathOracle.UnsupportedClosure("Excluded state callback: SwimUpdate"); }'])

    def test_selected_callback_is_not_replaced_by_a_guard(self):
        original = 'StateMachine.SetCallbacks(0, NormalUpdate);\n\tprivate int NormalUpdate()\n{ return 0; }'
        self.assertEqual(callback_guards(original, 'private int NormalUpdate() { return 0; }'), [])

    def test_callback_call_is_not_mistaken_for_its_declaration(self):
        original = 'StateMachine.SetCallbacks(3, SwimUpdate);\n\tprivate int SwimUpdate()\n{ return 3; }'
        self.assertEqual(len(callback_guards(original, 'private void Other() { SwimUpdate(); }')), 1)

    def test_old_fixture_body_is_removed_without_removing_other_services(self):
        text = 'before\n    public partial class Player { void Method() { } }\nafter'
        self.assertEqual(remove_fixture_class(text, 'Player'), 'before\n\nafter')

    def test_derived_component_fixture_can_be_replaced_by_original_source(self):
        text = 'before\n    public sealed class VertexLight : Component { public float Alpha; }\nafter'
        self.assertEqual(remove_fixture_class(text, 'VertexLight'), 'before\n\nafter')

    def test_math_struct_fixture_can_be_replaced_by_original_source(self):
        text = 'before\n    public struct Matrix { public float Scale; }\nafter'
        self.assertEqual(remove_fixture_class(text, 'Matrix'), 'before\n\nafter')

    def test_static_tag_fixture_can_be_replaced_by_original_source(self):
        text = 'before\n    public static class Tags { public const int Global = 1; }\nafter'
        self.assertEqual(remove_fixture_class(text, 'Tags'), 'before\n\nafter')

    def test_replaced_fixture_does_not_leave_tracking_attributes_on_the_next_type(self):
        text = 'before\n    [Tracked(false)]\n    public sealed class Lookout { }\n    public class Other { }'
        self.assertEqual(remove_fixture_class(text, 'Lookout'), 'before\n\n    public class Other { }')

    def test_old_presentation_mechanical_services_fail_closed_in_room_probe(self):
        support = Path(__file__).parent / 'oracle/presentation/Shims.cs'
        generated = room_shared_support(support.read_text())
        for name in ('BurstFG', 'Burst'):
            with self.subTest(method=name):
                self.assertRegex(generated, name + r'\([^\n]*?\) => throw new DeathOracle.UnsupportedClosure\(')

    def test_original_static_world_classes_replace_presentation_identity_shells(self):
        support = Path(__file__).parent / 'oracle/presentation/Shims.cs'
        generated = room_shared_support(support.read_text())
        for name in ('Platform', 'Solid', 'JumpThru', 'SurfaceIndex', 'ClimbBlocker'):
            with self.subTest(type=name):
                self.assertNotRegex(generated, r'public (?:static )?class ' + name + r'\b')

    def test_original_tracking_attribute_replaces_both_presentation_aliases(self):
        support = Path(__file__).parent / 'oracle/presentation/Shims.cs'
        generated = room_shared_support(support.read_text())
        self.assertNotRegex(generated, r'class Tracked(?:Attribute)?\b')

    def test_unknown_presentation_support_is_not_silently_accepted(self):
        with self.assertRaisesRegex(ValueError, 'fixture class|legacy presentation boundary'):
            room_shared_support('')

    def test_original_xml_loader_replaces_the_presentation_file_reader(self):
        support = Path(__file__).parent / 'oracle/presentation/Shims.cs'
        self.assertNotIn('public static XmlDocument LoadContentXML(', room_shared_support(support.read_text()))

    def test_changed_texture_boundary_is_not_silently_accepted(self):
        support = Path(__file__).parent / 'oracle/presentation/Shims.cs'
        changed = support.read_text().replace('public sealed class Texture2D', 'public class Texture2D')
        with self.assertRaisesRegex(ValueError, 'metadata texture boundary'):
            room_shared_support(changed)

    def test_profile_preserves_raw_mechanical_order_including_golden(self):
        raw = synthetic_room()
        stripped, changes = presentation_profile(raw)
        self.assertEqual(stripped['children'][0], raw['children'][0])

    def test_profile_does_not_modify_raw_metadata(self):
        raw = synthetic_room()
        before = copy.deepcopy(raw)
        presentation_profile(raw)
        self.assertEqual(raw, before)

    def test_presentation_changes_are_explicit(self):
        stripped, changes = presentation_profile(synthetic_room())
        self.assertEqual([change['layer'] for change in changes], ['fgdecals', 'bgdecals', 'objtiles'])
        self.assertEqual(stripped['children'][-1]['attributes']['innerText'], '')

    def test_unexpected_mechanical_entity_is_rejected(self):
        raw = synthetic_room()
        raw['children'][0]['children'].append({'name': 'refill', 'attributes': {}, 'children': []})
        with self.assertRaisesRegex(ValueError, 'mechanical'):
            presentation_profile(raw)

    def test_nonempty_triggers_are_rejected(self):
        raw = synthetic_room()
        raw['children'][1]['children'].append({'name': 'eventTrigger'})
        with self.assertRaisesRegex(ValueError, 'trigger'):
            presentation_profile(raw)

    def test_nonzero_wind_is_rejected(self):
        raw = synthetic_room()
        raw['attributes']['windPattern'] = 'Right'
        with self.assertRaisesRegex(ValueError, 'environment'):
            presentation_profile(raw)
