from __future__ import annotations

import json
from unittest import TestCase

from moz.l10n.formats.i18next_json.parse import (
    build_pattern_message,
    build_select_message,
    find_plural_groups,
    i18next_json_parse,
)
from moz.l10n.model import (
    CatchallKey,
    Entry,
    Expression,
    PatternMessage,
    Resource,
    Section,
    SelectMessage,
    VariableRef,
)


def src(data: dict) -> str:
    return json.dumps(data)


class TestBuildPatternMessage(TestCase):
    def test_empty_string(self):
        assert build_pattern_message("") == PatternMessage([""])

    def test_plain_string(self):
        assert build_pattern_message("hello world") == PatternMessage(["hello world"])

    def test_single_variable(self):
        assert build_pattern_message("replace this {{value}}") == PatternMessage(
            ["replace this ", Expression(VariableRef("value"))]
        )

    def test_unescaped_variable(self):
        assert build_pattern_message("replace this {{- value}}") == PatternMessage(
            ["replace this ", Expression(VariableRef("value"))]
        )

    def test_unescaped_no_space(self):
        assert build_pattern_message("{{-value}}") == PatternMessage(
            [Expression(VariableRef("value"))]
        )

    def test_variable_with_complex_formatter(self):
        assert build_pattern_message("{{amount, currency(USD)}}") == PatternMessage(
            [Expression(VariableRef("amount"))]
        )

    def test_multiple_variables(self):
        assert build_pattern_message("{{a}} and {{b}}") == PatternMessage(
            [Expression(VariableRef("a")), " and ", Expression(VariableRef("b"))]
        )

    def test_mixed_unescaped_and_escaped(self):
        assert build_pattern_message("{{- raw}} and {{escaped}}") == PatternMessage(
            [
                Expression(VariableRef("raw")),
                " and ",
                Expression(VariableRef("escaped")),
            ]
        )

    def test_nesting_stays_literal(self):
        assert build_pattern_message("reuse $t(keyDeep.inner)") == PatternMessage(
            ["reuse $t(keyDeep.inner)"]
        )

    def test_empty_braces_literal(self):
        assert build_pattern_message("text {{}} here") == PatternMessage(
            ["text {{}} here"]
        )

    def test_variable_only_no_surrounding_text(self):
        assert build_pattern_message("{{count}}") == PatternMessage(
            [Expression(VariableRef("count"))]
        )


class TestFindPluralGroups(TestCase):
    def test_simple_cardinal(self):
        data = {"item_one": "one item", "item_other": "{{count}} items"}
        groups, plural_keys = find_plural_groups(data)
        assert "item" in groups
        assert groups["item"]["ordinal"] is False
        assert groups["item"]["variants"] == {
            "one": "one item",
            "other": "{{count}} items",
        }
        assert plural_keys == {"item_one", "item_other"}

    def test_all_cldr_suffixes_arabic(self):
        data = {
            "count_zero": "zero",
            "count_one": "one",
            "count_two": "two",
            "count_few": "few",
            "count_many": "many",
            "count_other": "other",
        }
        groups, plural_keys = find_plural_groups(data)
        assert "count" in groups
        assert set(groups["count"]["variants"].keys()) == {
            "zero",
            "one",
            "two",
            "few",
            "many",
            "other",
        }
        assert len(plural_keys) == 6

    def test_ordinal_detection(self):
        data = {
            "place_ordinal_one": "{{count}}st",
            "place_ordinal_two": "{{count}}nd",
            "place_ordinal_few": "{{count}}rd",
            "place_ordinal_other": "{{count}}th",
        }
        groups, _ = find_plural_groups(data)
        assert "place_ordinal" in groups
        assert groups["place_ordinal"]["ordinal"] is True

    def test_orphan_suffix_without_other_not_plural(self):
        data = {"status_one": "one status"}
        groups, plural_keys = find_plural_groups(data)
        assert groups == {}
        assert plural_keys == set()

    def test_context_keys_not_plural(self):
        data = {"keyContext_male": "male", "keyContext_female": "female"}
        groups, plural_keys = find_plural_groups(data)
        assert groups == {}
        assert plural_keys == set()

    def test_optional_zero_variant(self):
        data = {
            "item_zero": "No items",
            "item_one": "{{count}} item",
            "item_other": "{{count}} items",
        }
        groups, plural_keys = find_plural_groups(data)
        assert "item" in groups
        assert "zero" in groups["item"]["variants"]
        assert len(plural_keys) == 3

    def test_key_with_digit_base(self):
        data = {"step1_one": "{{count}} step", "step1_other": "{{count}} steps"}
        groups, _ = find_plural_groups(data)
        assert "step1" in groups


class TestBuildSelectMessage(TestCase):
    def test_cardinal_selector(self):
        variants = {"one": "one item", "other": "{{count}} items"}
        msg = build_select_message(ordinal=False, variants=variants)
        assert isinstance(msg, SelectMessage)
        decl = msg.declarations["count"]
        assert decl.function == "number"
        assert decl.options == {}
        assert msg.selectors == (VariableRef("count"),)

    def test_ordinal_selector_has_option(self):
        variants = {"one": "{{count}}st", "other": "{{count}}th"}
        msg = build_select_message(ordinal=True, variants=variants)
        assert msg.declarations["count"].options == {"select": "ordinal"}

    def test_other_variant_is_catchall(self):
        variants = {"one": "item", "other": "items"}
        msg = build_select_message(ordinal=False, variants=variants)
        assert (CatchallKey("other"),) in msg.variants
        assert ("one",) in msg.variants

    def test_variant_pattern_parsed(self):
        variants = {"one": "{{count}} item", "other": "{{count}} items"}
        msg = build_select_message(ordinal=False, variants=variants)
        one_pattern = msg.variants[("one",)]
        assert Expression(VariableRef("count")) in one_pattern


class TestI18nextJsonParse(TestCase):
    def test_plain_string(self):
        res = i18next_json_parse(src({"key": "value"}))
        assert res == Resource(
            None, [Section((), [Entry(("key",), PatternMessage(["value"]))])]
        )

    def test_empty_object(self):
        res = i18next_json_parse(src({}))
        assert res == Resource(None, [Section((), [])])

    def test_invalid_json_raises(self):
        with self.assertRaises(Exception):
            i18next_json_parse("not json")

    def test_root_not_dict_raises(self):
        with self.assertRaises(ValueError):
            i18next_json_parse('["a", "b"]')

    def test_array_value_skipped(self):
        res = i18next_json_parse(src({"arr": ["a", "b"], "key": "value"}))
        entries = res.sections[0].entries
        assert len(entries) == 1
        assert entries[0].id == ("key",)

    def test_nested_object_skipped(self):
        res = i18next_json_parse(src({"nested": {"inner": "val"}, "key": "value"}))
        entries = res.sections[0].entries
        assert len(entries) == 1
        assert entries[0].id == ("key",)

    def test_plural_group_emitted_as_select_message(self):
        res = i18next_json_parse(
            src(
                {
                    "item_one": "{{count}} item",
                    "item_other": "{{count}} items",
                }
            )
        )
        entries = res.sections[0].entries
        assert len(entries) == 1
        assert entries[0].id == ("item",)
        assert isinstance(entries[0].value, SelectMessage)

    def test_context_keys_are_plain_entries(self):
        res = i18next_json_parse(
            src(
                {
                    "key_male": "male variant",
                    "key_female": "female variant",
                }
            )
        )
        ids = [e.id for e in res.sections[0].entries]
        assert ("key_male",) in ids
        assert ("key_female",) in ids
