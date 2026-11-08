import hashlib
import json
import sys
import tempfile
from pathlib import Path
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
from prepare_player_death_oracle import validate_profile, validate_coverage, required_callbacks, validate_provenance, CALLBACKS
from prepare_player_presentation_oracle import source_block
import check_native_oracle


class DeathSourceGateTests(unittest.TestCase):
    def test_malformed_source_range_is_rejected(self):
        data = b"line\n"
        with self.assertRaisesRegex(ValueError, "range"):
            source_block(data, [(0, 1)], hashlib.sha256(data).hexdigest())

    def test_changed_source_hash_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "identity"):
            source_block(b"line\n", [(1, 1)], "0" * 64)

    def test_generated_extraction_cannot_omit_a_required_original_block(self):
        with tempfile.TemporaryDirectory(prefix="death-extraction-") as temporary:
            root = Path(temporary)
            data = b"required original block\n"
            generated = b"different generated body\n"
            (root / "source.cs").write_bytes(data)
            (root / "Extracted.cs").write_bytes(generated)
            (root / "source-manifest.json").write_text(json.dumps({
                "extracted_sha256": hashlib.sha256(generated).hexdigest(),
                "extractions": [{"file": "source.cs", "source_path": "source.cs", "source_sha256": hashlib.sha256(data).hexdigest(),
                    "lines_inclusive": [[1, 1]], "blocks_sha256": [hashlib.sha256(data).hexdigest()]}]}))
            with patch.object(check_native_oracle, "ROOT", root), self.assertRaisesRegex(ValueError, "Unchanged source block"):
                check_native_oracle.verify_extraction(root)

    def test_partial_traces_cannot_claim_lifecycle_closure(self):
        with self.assertRaisesRegex(ValueError, "eight"):
            validate_coverage({"traces": []})

    def test_missing_reload_callback_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "Reload"):
            required_callbacks({"DeathRoutine", "End", "IntroRespawnBegin", "IntroRespawnEnd"})

    def test_unsupported_state_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "state"):
            validate_profile({"inventory": 1, "backpack": True, "mode": "Madeline", "states": [0, 1, 2, 15]})

    def test_default_static_profile_is_accepted(self):
        validate_profile({"inventory": 1, "backpack": True, "mode": "Madeline", "states": [0, 1, 2, 14]})

    def test_boolean_inventory_is_not_an_integer_profile(self):
        with self.assertRaisesRegex(ValueError, "inventory"):
            validate_profile({"inventory": True, "backpack": True, "mode": "Madeline", "states": [0, 1, 2, 14]})

    def test_missing_source_is_not_accepted_from_a_receipt(self):
        with self.assertRaisesRegex(ValueError, "provenance"):
            validate_provenance({"sources": []}, {"synthetic.cs": "0" * 64})

    def test_recorded_callbacks_do_not_prove_coherent_execution(self):
        with self.assertRaisesRegex(ValueError, "Coherent"):
            validate_coverage({"traces": [{"id": name, "events": ["nonempty"], "status": "source-executed"} for name in
                ("up", "left", "ordering", "corpse", "boundaries", "freeze-input", "reload", "cycles")], "callbacks": list(CALLBACKS)})

    def test_empty_events_cannot_count_as_coverage(self):
        with self.assertRaisesRegex(ValueError, "events"):
            validate_coverage({"traces": [{"id": name, "events": []} for name in
                ("up", "left", "ordering", "corpse", "boundaries", "freeze-input", "reload", "cycles")]})
