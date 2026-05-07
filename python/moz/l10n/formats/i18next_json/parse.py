from __future__ import annotations

from json import loads
from re import compile
from typing import TypedDict

from ...model import (
    CatchallKey,
    Entry,
    Expression,
    Message,
    PatternMessage,
    Resource,
    Section,
    SelectMessage,
    VariableRef,
)

INTERP_RE = compile(r"\{\{-?\s*(\w+)[^}]*\}\}")
PLURAL_SUFFIXES = {"zero", "one", "two", "few", "many", "other"}


class PluralGroup(TypedDict):
    ordinal: bool
    variants: dict[str, str]


def build_pattern_message(value: str) -> PatternMessage:
    """Parse an i18next string value into a PatternMessage.

    Handles ``{{var}}`` and ``{{- var}}`` interpolation. Format specifiers
    (``{{val, number}}``) are runtime-only; the variable name is extracted
    and the formatter discarded. Nesting calls (``$t(key)``) and dot-notation
    paths (``{{author.name}}``) are left as literal text.
    """
    pattern = []
    pos = 0

    for m in INTERP_RE.finditer(value):
        pattern.append(value[pos : m.start()])
        pattern.append(Expression(VariableRef(m.group(1))))
        pos = m.end()

    pattern.append(value[pos:])
    result = [p for p in pattern if p or not isinstance(p, str)]
    return PatternMessage(result or [""])


def build_select_message(ordinal: bool, variants: dict[str, str]) -> SelectMessage:
    """Build a SelectMessage from a set of plural variant strings.

    The selector is always ``count`` with ``:number``, matching the i18next
    spec. The ``other`` suffix maps to CatchallKey as the required MF2
    fallback variant. Pass ``ordinal=True`` to add ``{"select": "ordinal"}``
    for ordinal plural rules.
    """
    options = {"select": "ordinal"} if ordinal else {}

    msg = SelectMessage(
        declarations={
            "count": Expression(VariableRef("count"), "number", options=options)
        },
        selectors=(VariableRef("count"),),
        variants={},
    )

    for suffix, value in variants.items():
        key = (CatchallKey(suffix),) if suffix == "other" else (suffix,)
        msg.variants[key] = build_pattern_message(value).pattern

    return msg


def find_plural_groups(
    items: dict[str, object],
) -> tuple[dict[str, PluralGroup], set[str]]:
    """Scan a flat i18next JSON object and identify cardinal and ordinal plural groups.

    A group requires ``{base}_other`` to be present; lone suffix keys with no
    ``_other`` sibling are treated as plain entries. Ordinal groups are detected
    when the base ends in ``_ordinal`` (e.g. ``place_ordinal_one``).
    Context keys (``_male``, ``_female``) are not grouped — their suffixes are
    outside the CLDR set and have no standard MF2 selector function.
    """
    groups: dict[str, PluralGroup] = {}
    plural: set[str] = set()

    for key, value in items.items():
        parts = key.rsplit("_", 1)
        if len(parts) < 2 or parts[1] not in PLURAL_SUFFIXES:
            continue

        base, suffix = parts
        ord_parts = base.rsplit("_", 1)

        if f"{base}_other" not in items:
            continue

        ordinal = len(ord_parts) == 2 and ord_parts[1] == "ordinal"

        plural.add(key)

        if base not in groups:
            groups[base] = {"ordinal": ordinal, "variants": {}}
        groups[base]["variants"][suffix] = value  # type: ignore[assignment]

    return groups, plural


def i18next_json_parse(source: str | bytes) -> Resource[Message]:
    """Parse an i18next JSON v4 file into a moz.l10n Resource.

    Plain strings become PatternMessage, plural groups become SelectMessage.
    Array values, nested objects, nesting calls (``$t``), and context variants
    are skipped silently. Returns ``format=None`` because ``Format`` is a
    closed enum with no i18next_json member.
    """
    data = loads(source)
    if not isinstance(data, dict):
        raise ValueError(f"Unexpected root value: {data}")

    plural_groups, plural_keys = find_plural_groups(data)
    entries: list[Entry[Message]] = []
    emitted: set[str] = set()

    for key, value in data.items():
        if key in plural_keys:
            base = key.rsplit("_", 1)[0]
            if base not in emitted:
                info = plural_groups[base]
                entries.append(
                    Entry(
                        (base,), build_select_message(info["ordinal"], info["variants"])
                    )
                )
                emitted.add(base)
        elif isinstance(value, str):
            entries.append(Entry((key,), build_pattern_message(value)))

    return Resource(None, sections=[Section((), entries)])
