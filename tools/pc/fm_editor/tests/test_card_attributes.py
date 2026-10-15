"""A mod's card attributes use the declarations attributes.c would accept.

The editor reads one manifest, so a custom id/name must be declared by that
manifest. The runtime additionally receives declarations from earlier active
mods; resolving that combined mod order is outside this standalone editor.

    python -m unittest discover -s tools/pc/fm_editor/tests -t tools/pc
"""
import unittest

from fm_editor import manifest, monster_effects, validate
from fm_editor.model import Project
from fm_editor.tests.test_data import fixture

BASE = 1   # "Blue Dragon" in the synthetic fixture, a monster


def project() -> Project:
    return Project(fixture().game())


class CardAttributeTest(unittest.TestCase):
    def test_retail_name_needs_no_declaration(self):
        p = project()
        before = p.cards[BASE].attribute
        messages = manifest.apply(p, {"id": "m", "cards": [{"replace": BASE, "attribute": "Light"}]})
        self.assertEqual(p.cards[BASE].attribute, 0)
        self.assertNotEqual(before, 0)
        self.assertFalse(messages)

    def test_undeclared_numeric_id_is_left_out(self):
        p = project()
        before = p.cards[BASE].attribute
        messages = manifest.apply(p, {"id": "m", "cards": [{"replace": BASE, "attribute": 8}]})
        self.assertEqual(p.cards[BASE].attribute, before)
        self.assertTrue(any("attribute" in msg for msg in messages), messages)

    def test_validator_rejects_undeclared_and_reserved_ids(self):
        p = project()
        for attribute in (8, 15):
            p.cards[BASE].attribute = attribute
            self.assertTrue(any("attribute" in issue.message for issue in validate.validate_card(p, BASE)))

    def test_undeclared_digit_string_is_left_out(self):
        p = project()
        before = p.cards[BASE].attribute
        messages = manifest.apply(p, {"id": "m", "cards": [{"replace": BASE, "attribute": "8"}]})
        self.assertEqual(p.cards[BASE].attribute, before)
        self.assertTrue(messages)

    def test_id_declared_for_a_different_id_is_left_out(self):
        p = project()
        before = p.cards[BASE].attribute
        manifest_json = {"id": "m", "attributes": {"attributes": [{"id": 9, "name": "Void"}]},
                         "cards": [{"replace": BASE, "attribute": 8}]}
        messages = manifest.apply(p, manifest_json)
        self.assertEqual(p.cards[BASE].attribute, before)
        self.assertTrue(messages)

    def test_declared_numeric_id_applies(self):
        p = project()
        manifest_json = {"id": "m", "attributes": {"attributes": [{"id": 8, "name": "Metal"}]},
                         "cards": [{"replace": BASE, "attribute": 8}]}
        messages = manifest.apply(p, manifest_json)
        self.assertEqual(p.cards[BASE].attribute, 8)
        self.assertFalse(messages)

    def test_declared_name_applies(self):
        p = project()
        manifest_json = {"id": "m", "attributes": {"attributes": [{"id": 8, "name": "Metal"}]},
                         "cards": [{"replace": BASE, "attribute": "Metal"}]}
        messages = manifest.apply(p, manifest_json)
        self.assertEqual(p.cards[BASE].attribute, 8)
        self.assertFalse(messages)

    def test_reserved_ids_never_apply_even_if_declared(self):
        p = project()
        before = p.cards[BASE].attribute
        manifest_json = {"id": "m", "attributes": {"attributes": [{"id": 6, "name": "Spell"}]},
                         "cards": [{"replace": BASE, "attribute": "Spell"}]}
        messages = manifest.apply(p, manifest_json)
        self.assertEqual(p.cards[BASE].attribute, before)
        self.assertTrue(messages)

    def test_runtime_rejected_declaration_cannot_apply(self):
        p = project()
        before = p.cards[BASE].attribute
        messages = manifest.apply(p, {"id": "m", "attributes": {"attributes": [{"id": 8, "name": "Light"}]},
                                      "cards": [{"replace": BASE, "attribute": 8}]})
        self.assertEqual(p.cards[BASE].attribute, before)
        self.assertTrue(messages)

    def test_numeric_and_boolean_declarations_are_rejected(self):
        p = project()
        before = p.cards[BASE].attribute
        messages = manifest.apply(p, {"id": "m", "attributes": {"attributes": [
            {"id": 8, "name": "8-"}, {"id": True, "name": "Boolean"}]},
            "cards": [{"replace": BASE, "attribute": 8}]})
        self.assertEqual(p.cards[BASE].attribute, before)
        self.assertTrue(messages)

    def test_runtime_name_normalization_and_retail_aliases(self):
        p = project()
        section = {"attributes": [
            {"id": 0, "name": "Radiant"}, {"id": 8, "name": "Metal"},
            {"id": 9, "name": "r-a-d-i-a-n-t"}]}
        messages = manifest.apply(p, {"id": "m", "attributes": section,
                                      "cards": [{"replace": BASE, "attribute": "m-e-t-a-l"}]})
        self.assertEqual(p.cards[BASE].attribute, 8)
        self.assertEqual(manifest._attribute_choice(9, section), -1)
        self.assertFalse(messages)

    def test_utf8_names_do_not_use_python_unicode_casefolding(self):
        p = project()
        messages = manifest.apply(p, {"id": "m", "attributes": {"attributes": [
            {"id": 8, "name": "É"}, {"id": 9, "name": "é"}]},
            "cards": [{"replace": BASE, "attribute": "é"}]})
        self.assertEqual(p.cards[BASE].attribute, 9)
        self.assertFalse(messages)

    def test_custom_attribute_applies_to_card_and_monster_effects(self):
        p = project()
        messages = manifest.apply(p, {"id": "m", "attributes": {"attributes": [{"id": 20, "name": "Metal"}]},
                                      "cards": [{"replace": BASE, "attribute": 20, "monster_effects": [{
                                          "when": "summon", "do": "boost", "attack": 500, "attribute": "Metal",
                                          "for_each": {"attribute": 20}}]}]})
        self.assertFalse(messages)
        self.assertEqual(p.cards[BASE].attribute, 20)
        resolve_attribute = lambda value: manifest._attribute_choice(value, p.other.get("attributes"))
        effect = p.card_extra[BASE]["monster_effects"][0]
        self.assertEqual(monster_effects.normalize(effect, p.resolve, resolve_attribute), {
            "when": "summon", "do": "boost", "target": "self", "attack": 500, "attribute": 20,
            "for_each": {"whose": "all", "attribute": 20}})
        self.assertFalse(validate.errors(validate.validate_card(p, BASE)))

    def test_standalone_effect_normalization_rejects_undeclared_custom_attribute(self):
        effect = {"when": "summon", "do": "boost", "attack": 500, "attribute": 20}
        self.assertIsNone(monster_effects.normalize(effect))


if __name__ == "__main__":
    unittest.main()
