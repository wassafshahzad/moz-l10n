# i18next JSON v4 Parser — Design Notes

## Scope

Parse-only. No serializer. Input: flat i18next JSON v4 object. Output: `Resource[Message]`.

---

## Key Decisions

### Interpolation regex

```python
INTERP_RE = compile(r"\{\{-?\s*(\w+)[^}]*\}\}")
```

- `-?\s*` — handles both `{{var}}` and `{{- var}}` (unescaped form). The dash is a runtime HTML-escape flag; the variable name is identical in both forms.
- `(\w+)` — captures variable name. Word characters only: no dots, no spaces.
- `[^}]*` — consumes format specifiers (`{{val, number}}`, `{{val, currency(USD)}}`). The variable name is extracted; the formatter is discarded. Formatters are runtime-only and have no representation in the moz.l10n model.

### Dot-notation paths

`{{author.name}}` — `\w+` captures `author`, `[^}]*` consumes `.name`. The path qualifier is lost. `VariableRef` holds a single name with no path concept, so full fidelity is not achievable without extending the model.

### Plural detection sentinel

A plural group requires `{base}_other` to be present. A key ending in `_one` with no `_other` sibling is treated as a plain string entry. This matches the i18next v4 spec which mandates `_other` as the required fallback form.

### Ordinal detection

Ordinal groups use the `_ordinal_` marker between base and CLDR suffix: `place_ordinal_one`, `place_ordinal_other`. Detection checks whether the base (after stripping the CLDR suffix) itself ends in `_ordinal`. The same `{base}_other` sentinel applies, where `base` includes `_ordinal`.

Known limitation: a key whose business name ends in `_ordinal` (e.g. `some_ordinal_one` + `some_ordinal_other`) is falsely detected as an ordinal plural. Resolving this requires explicit configuration or a naming convention ban, neither of which is representable in a plain JSON file.

### Key order preservation

Plural group entries are emitted at the position of the first variant key encountered in the source file. Python 3.7+ guarantees dict insertion order, so source order is fully preserved.

### `format=None`

`Format` is a closed enum. There is no `Format.i18next_json` member and the enum cannot be extended externally. The returned `Resource` uses `format=None`. Any consumer that dispatches on `resource.format` will not recognise i18next output without patching the library.

---

## What Is Skipped

| Feature | Reason |
|---|---|
| Nested objects | Flat JSON assumed. Nested values silently skipped. |
| Array values | No array type in moz.l10n model. `returnObjects`/`joinArrays` are runtime features. |
| Nesting `$t(key)` | Key-reference resolution is runtime-only. Passes through as literal text. |
| Context variants `_male`/`_female` | Suffixes not in CLDR set. No standard MF2 gender function. Application-defined suffix space makes grouping ambiguous. |
| Placeholder formatters | Runtime concern. Variable name extracted; formatter discarded. |
| Custom `pluralSeparator` | Runtime config not representable in JSON. Parser assumes default `_`. |

---

## Running the Tests
```bash
# from repo root
cd python
python -m pytest tests/formats/test_i18next_json.py -v
```

---
