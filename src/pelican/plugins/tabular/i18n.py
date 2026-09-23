"""Shared component localization for tabular and its consumers.

Catalogs contain text, not HTML. Translation matching never crosses scripts;
bare ``zh`` retains the historical Traditional Chinese convention.
"""

from __future__ import annotations

import html
import json
import re
import string
import unicodedata
from collections.abc import Mapping
from copy import deepcopy
from functools import lru_cache
from pathlib import Path
from typing import Any, TypeAlias

from babel import Locale, UnknownLocaleError
from langcodes import Language, standardize_tag
from langcodes.tag_parser import LanguageTagError

LocalizedText: TypeAlias = str | Mapping[str, str]
Message: TypeAlias = str | dict[str, Any]
_CATEGORIES = {"zero", "one", "two", "few", "many", "other"}


def normalize_locale(value: str, path: str = "lang") -> str:
    """Canonicalize a BCP 47 tag; accept underscores at the settings boundary."""
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{path}: expected a non-empty language tag")
    try:
        return standardize_tag(value.replace("_", "-"))
    except (LanguageTagError, ValueError) as exc:
        raise ValueError(f"{path}: invalid language tag {value!r}") from exc


def component_locale(*values: str | None) -> str:
    """Resolve explicit component, content, build, then English language."""
    return normalize_locale(next((v for v in values if v is not None), "en"))


@lru_cache(maxsize=128)
def _language(tag: str) -> Language:
    return Language.get("zh-Hant" if tag == "zh" else tag).maximize()


def match_locale(locale: str, available: Mapping[str, Any]) -> str | None:
    """Exact match, compatible parent, then a resource of the same script.

    Return an original mapping key. Unknown languages simply have no match.
    """
    tag = normalize_locale(locale)
    keys = {normalize_locale(k): k for k in available}
    if tag in keys:
        return keys[tag]
    wanted = _language(tag)
    compatible = [
        k
        for k in keys
        if _language(k).language == wanted.language
        and _language(k).script == wanted.script
    ]
    if not compatible:
        return None
    compatible.sort(
        key=lambda k: (
            0 if tag.startswith(k + "-") else 1,
            0 if Language.get(k).territory is None else 1,
            len(k),
            k,
        )
    )
    return keys[compatible[0]]


def resolve_text(
    value: LocalizedText,
    locale: str,
    *,
    fallback: str = "",
    source_lang: str = "und",
    path: str = "text",
    english_fallback: bool = True,
) -> tuple[str, str]:
    """Resolve display text and retain its actual language on fallback."""
    if isinstance(value, str):
        return value, source_lang
    if not isinstance(value, Mapping):
        raise ValueError(f"{path}: expected text or a language-to-text mapping")
    for key, text in value.items():
        normalize_locale(key, f"{path}.{key}")
        if not isinstance(text, str):
            raise ValueError(f"{path}.{key}: expected text")
    matched = match_locale(locale, value)
    if matched is None and english_fallback:
        matched = match_locale("en", value)
    if matched is None:
        return fallback, source_lang
    return value[matched], normalize_locale(matched)


def localized_text(
    value: LocalizedText, locale: str, *, fallback: str = "", path: str = "text"
) -> str:
    return resolve_text(value, locale, fallback=fallback, path=path)[0]


def direction(locale: str) -> str:
    return (
        "rtl"
        if _language(normalize_locale(locale)).script
        in {
            "Arab",
            "Hebr",
            "Thaa",
            "Nkoo",
            "Adlm",
            "Rohg",
            "Syrc",
            "Samr",
            "Mand",
        }
        else "ltr"
    )


def normalize_search(value: str) -> str:
    """NFKC and Unicode lowercase, matching JS; no transliteration/casefold."""
    return unicodedata.normalize("NFKC", value).lower()


def _placeholders(template: str, path: str) -> set[str]:
    found: set[str] = set()
    try:
        for _, field, spec, conversion in string.Formatter().parse(template):
            if field is not None:
                if (
                    not re.fullmatch(r"[A-Za-z_][A-Za-z_0-9]*", field)
                    or spec
                    or conversion
                ):
                    raise ValueError("use simple {name} placeholders")
                found.add(field)
    except ValueError as exc:
        raise ValueError(f"{path}: invalid message template: {exc}") from exc
    return found


def validate_message(value: Any, required: set[str], path: str) -> None:
    if isinstance(value, str):
        found = _placeholders(value, path)
        if value and found != required:
            raise ValueError(f"{path}: expected placeholders {sorted(required)}")
        return
    if not isinstance(value, dict) or set(value) - {"plural", "forms", "locale"}:
        raise ValueError(f"{path}: expected text or a plural message")
    if value.get("plural") not in required:
        raise ValueError(f"{path}.plural: expected a count placeholder")
    forms = value.get("forms")
    if not isinstance(forms, dict) or "other" not in forms or set(forms) - _CATEGORIES:
        raise ValueError(f"{path}.forms: expected CLDR categories including other")
    for category, template in forms.items():
        if not isinstance(template, str):
            raise ValueError(f"{path}.forms.{category}: expected text")
        validate_message(template, required, f"{path}.forms.{category}")
    if "locale" in value:
        normalize_locale(value["locale"], f"{path}.locale")


def message_fields(value: Message) -> set[str]:
    template = value if isinstance(value, str) else value["forms"]["other"]
    return _placeholders(template, "message")


def other_template(message: Message) -> str:
    """Expose a catalog's default form to legacy template-only callers."""
    return message if isinstance(message, str) else str(message["forms"]["other"])


@lru_cache(maxsize=128)
def _babel_locale(locale: str) -> Locale:
    lang = Language.get(locale)
    # Extensions/private use do not change cardinal rules.
    for tag in (lang.simplify_script().to_tag(), lang.language, "en"):
        try:
            return Locale.parse(tag or "en", sep="-")
        except (UnknownLocaleError, ValueError):
            continue
    return Locale("en")


def format_message(message: Message, locale: str = "en", **values: Any) -> str:
    if isinstance(message, dict):
        category = _babel_locale(message.get("locale", locale)).plural_form(
            values[message["plural"]]
        )
        template = str(message["forms"].get(category, message["forms"]["other"]))
    else:
        template = message
    return template.format_map(values)


class Catalog:
    """Validated package catalog; resolve a fresh message set per component."""

    def __init__(self, path: Path) -> None:
        self.data: dict[str, dict[str, Message]] = json.loads(path.read_text("utf-8"))
        self.defaults = self.data["en"]
        for locale, messages in self.data.items():
            normalize_locale(locale, str(path))
            if messages.keys() != self.defaults.keys():
                raise ValueError(f"{path}.{locale}: catalog keys differ from en")
            for key, value in messages.items():
                validate_message(
                    value, message_fields(self.defaults[key]), f"{path}.{locale}.{key}"
                )

    def resolve(
        self,
        locale: str,
        overrides: Mapping[str, Any] | None = None,
        *,
        path: str = "messages",
    ) -> dict[str, Message]:
        key = match_locale(locale, self.data) or "en"
        result = deepcopy(self.data[key])
        for value in result.values():
            if isinstance(value, dict):
                value["locale"] = key
        if overrides is not None and not isinstance(overrides, Mapping):
            raise ValueError(f"{path}: expected a mapping")
        for name, value in (overrides or {}).items():
            if name not in self.defaults:
                raise ValueError(f"{path}.{name}: unknown message")
            if isinstance(value, Mapping) and "forms" not in value:
                value, actual = resolve_text(value, locale, path=f"{path}.{name}")
                if actual == "und":
                    continue
            validate_message(
                value, message_fields(self.defaults[name]), f"{path}.{name}"
            )
            resolved = deepcopy(value)
            if isinstance(resolved, dict) and "locale" in resolved:
                resolved["locale"] = normalize_locale(
                    resolved["locale"], f"{path}.{name}.locale"
                )
            result[name] = resolved
        return result


def component_attrs(locale: str, words: Mapping[str, Any]) -> str:
    payload = html.escape(
        json.dumps({"locale": locale, "words": words}, ensure_ascii=False), quote=True
    )
    return (
        f' lang="{html.escape(locale, quote=True)}" dir="{direction(locale)}"'
        f' data-i18n="{payload}"'
    )


def project_record(
    record: dict[str, Any],
    locale: str,
    config: Mapping[str, Any] | None,
    *,
    path: str = "translations",
) -> dict[str, Any]:
    """Explicit display projection; never alter the caller's source/cache.

    Only allowlisted scalar text fields may be translated. ``aliases`` maps
    language → displayed field → existing source field (e.g. title_native).
    Translation payload is removed from the public projection, so it cannot
    accidentally become an auto-detected column or search index.
    """
    result = deepcopy(record)
    if config is None:
        return result
    if not isinstance(config, Mapping):
        raise ValueError(f"{path}: expected a mapping")
    if not config:
        return result
    fields = config.get("fields", [])
    if not isinstance(fields, list) or any(not isinstance(f, str) for f in fields):
        raise ValueError(f"{path}.fields: expected field names")
    forbidden = {
        "id",
        "lat",
        "lon",
        "osm_id",
        "osm_type",
        "slug",
        "tags",
        "urls",
        "images",
    }
    if any(f in forbidden or f.startswith("_") for f in fields):
        raise ValueError(
            f"{path}.fields: IDs, coordinates and structural fields "
            "cannot be translated"
        )
    source_lang = normalize_locale(
        config.get("source_lang", "und"), f"{path}.source_lang"
    )
    translation_field = config.get("field", "translations")
    if not isinstance(translation_field, str) or translation_field in fields:
        raise ValueError(f"{path}.field: expected a separate translation field")
    translations = result.pop(translation_field, {})
    aliases = config.get("aliases", {})
    if not isinstance(translations, Mapping) or not isinstance(aliases, Mapping):
        raise ValueError(f"{path}: translations and aliases must be mappings")
    candidates: dict[str, dict[str, str]] = {}
    for source, is_alias in ((aliases, True), (translations, False)):
        for tag, entries in source.items():
            tag = normalize_locale(tag, path)
            if not isinstance(entries, Mapping) or set(entries) - set(fields):
                raise ValueError(
                    f"{path}.{tag}: only allowlisted fields may be translated"
                )
            for field, value in entries.items():
                if is_alias:
                    if not isinstance(value, str):
                        raise ValueError(
                            f"{path}.aliases.{tag}.{field}: expected a field name"
                        )
                    value = record.get(value)
                    if value is None or value == "":
                        continue
                if not isinstance(value, str):
                    raise ValueError(f"{path}.{tag}.{field}: expected text")
                candidates.setdefault(field, {})[tag] = value
    languages = {}
    originals = {}
    for field in fields:
        field_candidates = candidates.get(field, {})
        # Keep absent optional fields out of auto-detected table columns.
        if field not in record and match_locale(locale, field_candidates) is None:
            continue
        original = record.get(field)
        if original is not None and not isinstance(original, str):
            raise ValueError(f"{path}.{field}: only scalar text can be translated")
        originals[field] = original
        result[field], languages[field] = resolve_text(
            field_candidates,
            locale,
            fallback=original or "",
            source_lang=source_lang,
            english_fallback=False,
            path=f"{path}.{field}",
        )
    result["_i18n_langs"] = languages
    result["_i18n_source"] = originals
    return result


def value_lang(record: Mapping[str, Any], field: str) -> str:
    """An HTML attribute for an explicitly localized data cell."""
    language = record.get("_i18n_langs", {}).get(field)
    if not language and "." in field:
        head, _, rest = field.partition(".")
        child = record.get(head)
        if isinstance(child, Mapping):
            return value_lang(child, rest)
    return f' lang="{html.escape(language, quote=True)}"' if language else ""


CATALOG = Catalog(Path(__file__).with_name("messages.json"))
