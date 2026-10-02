"""Extract the model inputs from a FHIR QuestionnaireResponse.

Items are matched by ``linkId``. The default linkIds can be overridden with a JSON file
(``PLCOM_LINKID_MAP``), so that the service can read an existing questionnaire.
"""

from __future__ import annotations

import json
import math
from collections import defaultdict
from pathlib import Path
from typing import Any

from .model import FieldIssue, InputValidationError, PlcoInput, Race

DEFAULT_LINKIDS: dict[str, str] = {
    "age": "age",
    "race": "race",
    "education": "education",
    "bmi": "bmi",
    "height_cm": "height-cm",
    "weight_kg": "weight-kg",
    "copd": "copd",
    "personal_cancer_history": "personal-cancer-history",
    "family_history_lung_cancer": "family-history-lung-cancer",
    "smoking_status": "smoking-status",
    "cigarettes_per_day": "cigarettes-per-day",
    "smoking_duration_years": "smoking-duration-years",
    "quit_years": "quit-years",
}

# Accepted spellings for race. Values: Race or None (= "not specified", no race term applied).
_CDC_RACE = {  # CDC Race & Ethnicity code system, urn:oid:2.16.840.1.113883.6.238
    "2106-3": Race.WHITE,
    "1002-5": Race.AMERICAN_INDIAN_ALASKA_NATIVE,
    "2054-5": Race.BLACK,
    "2135-2": Race.HISPANIC,
    "2028-9": Race.ASIAN,
    "2076-8": Race.NATIVE_HAWAIIAN_PACIFIC_ISLANDER,
    "2131-1": None,  # "Other Race"
}
_RACE_CODES: dict[str, Race | None] = {
    **{r.value: r for r in Race},
    "american-indian": Race.AMERICAN_INDIAN_ALASKA_NATIVE,
    "alaska-native": Race.AMERICAN_INDIAN_ALASKA_NATIVE,
    "native-hawaiian": Race.NATIVE_HAWAIIAN_PACIFIC_ISLANDER,
    "pacific-islander": Race.NATIVE_HAWAIIAN_PACIFIC_ISLANDER,
    **_CDC_RACE,
    "other": None,
    "unknown": None,
    "unspecified": None,
    "asked-but-unknown": None,
    "unk": None,
}

_YES = {"yes", "y", "true", "1", "la33-6"}  # LA33-6 = LOINC answer "Yes"
_NO = {"no", "n", "false", "0", "la32-8"}  # LA32-8 = LOINC answer "No"


def load_linkids(path: str | None) -> dict[str, str]:
    """Default linkIds, optionally overridden by a JSON object {field: linkId}."""
    linkids = dict(DEFAULT_LINKIDS)
    if path:
        override = json.loads(Path(path).read_text(encoding="utf-8"))
        unknown = set(override) - set(DEFAULT_LINKIDS)
        if unknown:
            raise ValueError(f"Unknown fields in linkId map: {sorted(unknown)}")
        linkids.update(override)
    return linkids


def _collect_answers(qr: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    answers: dict[str, list[dict[str, Any]]] = defaultdict(list)

    def walk(items: Any) -> None:
        for item in items or []:
            if not isinstance(item, dict):
                continue
            link_id = item.get("linkId")
            item_answers = [a for a in (item.get("answer") or []) if isinstance(a, dict)]
            if link_id:
                answers[link_id].extend(item_answers)
            walk(item.get("item"))
            for answer in item_answers:
                walk(answer.get("item"))

    walk(qr.get("item"))
    return answers


class _Reader:
    def __init__(self, answers: dict[str, list[dict[str, Any]]], linkids: dict[str, str]):
        self.answers = answers
        self.linkids = linkids
        self.issues: list[FieldIssue] = []

    def _issue(self, field: str, message: str, code: str = "invalid") -> None:
        self.issues.append(FieldIssue(field, f"item '{self.linkids[field]}': {message}", code))

    def _answer(self, field: str, required: bool) -> dict[str, Any] | None:
        found = self.answers.get(self.linkids[field], [])
        if not found:
            if required:
                self._issue(field, "required answer is missing", "required")
            return None
        if len(found) > 1:
            self._issue(field, "exactly one answer expected, got several")
            return None
        return found[0]

    def number(self, field: str, required: bool = True) -> float | None:
        ans = self._answer(field, required)
        if ans is None:
            return None
        value: Any = ans.get("valueDecimal", ans.get("valueInteger"))
        if value is None and isinstance(ans.get("valueQuantity"), dict):
            value = ans["valueQuantity"].get("value")
        if (
            isinstance(value, bool)
            or not isinstance(value, int | float)
            or not math.isfinite(value)
        ):
            self._issue(field, "expected a number (valueDecimal, valueInteger or valueQuantity)")
            return None
        return float(value)

    def integer(self, field: str, required: bool = True) -> int | None:
        ans = self._answer(field, required)
        if ans is None:
            return None
        value: Any = ans.get("valueInteger", ans.get("valueDecimal"))
        if value is None and isinstance(ans.get("valueCoding"), dict):
            value = ans["valueCoding"].get("code")
        try:
            number = float(value)
        except (TypeError, ValueError):
            number = float("nan")
        if isinstance(value, bool) or not math.isfinite(number) or number != int(number):
            self._issue(
                field, "expected an integer (valueInteger or valueCoding with numeric code)"
            )
            return None
        return int(number)

    def boolean(self, field: str) -> bool | None:
        ans = self._answer(field, required=True)
        if ans is None:
            return None
        if isinstance(ans.get("valueBoolean"), bool):
            return ans["valueBoolean"]
        code = _code_of(ans)
        if code in _YES:
            return True
        if code in _NO:
            return False
        self._issue(field, "expected valueBoolean (or a yes/no coding)")
        return None

    def code(self, field: str, required: bool) -> str | None:
        ans = self._answer(field, required)
        if ans is None:
            return None
        code = _code_of(ans)
        if code is None:
            self._issue(field, "expected valueCoding or valueString")
        return code


def _code_of(answer: dict[str, Any]) -> str | None:
    coding = answer.get("valueCoding")
    if isinstance(coding, dict) and isinstance(coding.get("code"), str):
        return coding["code"].strip().lower()
    if isinstance(answer.get("valueString"), str):
        return answer["valueString"].strip().lower()
    return None


def extract_inputs(qr: dict[str, Any], linkids: dict[str, str] | None = None) -> PlcoInput:
    """Build the model input from a QuestionnaireResponse or raise InputValidationError."""
    linkids = linkids or DEFAULT_LINKIDS
    r = _Reader(_collect_answers(qr), linkids)

    age = r.number("age")
    education = r.integer("education")
    copd = r.boolean("copd")
    cancer = r.boolean("personal_cancer_history")
    family = r.boolean("family_history_lung_cancer")
    cpd = r.number("cigarettes_per_day")
    duration = r.number("smoking_duration_years")

    bmi = _read_bmi(r)
    current_smoker = _read_smoking_status(r)
    quit_years = r.number("quit_years", required=current_smoker is False)
    race = _read_race(r)

    if r.issues:
        raise InputValidationError(r.issues)

    assert None not in (age, education, copd, cancer, family, cpd, duration, bmi, current_smoker)
    return PlcoInput(
        age=age,
        education=education,
        bmi=bmi,
        copd=copd,
        personal_cancer_history=cancer,
        family_history_lung_cancer=family,
        current_smoker=current_smoker,
        cigarettes_per_day=cpd,
        smoking_duration_years=duration,
        quit_years=quit_years or 0.0,
        race=race,
    )


def _read_bmi(r: _Reader) -> float | None:
    """BMI directly, or computed from height (cm) and weight (kg)."""
    if r.answers.get(r.linkids["bmi"]):
        return r.number("bmi")
    if not (r.answers.get(r.linkids["height_cm"]) and r.answers.get(r.linkids["weight_kg"])):
        r._issue(
            "bmi",
            f"missing: provide '{r.linkids['bmi']}' or both "
            f"'{r.linkids['height_cm']}' and '{r.linkids['weight_kg']}'",
            "required",
        )
        return None
    height = r.number("height_cm")
    weight = r.number("weight_kg")
    if height is None or weight is None:
        return None
    if height <= 0:
        r._issue("height_cm", "must be greater than 0")
        return None
    return weight / (height / 100.0) ** 2


def _read_smoking_status(r: _Reader) -> bool | None:
    code = r.code("smoking_status", required=True)
    if code is None:
        return None
    if code == "current":
        return True
    if code == "former":
        return False
    if code == "never":
        r._issue(
            "smoking_status",
            "PLCOm2012 is only defined for current and former smokers, not for never smokers",
        )
    else:
        r._issue("smoking_status", "expected 'current' or 'former'")
    return None


def _read_race(r: _Reader) -> Race | None:
    code = r.code("race", required=False)
    if code is None:
        return None
    if code not in _RACE_CODES:
        r._issue("race", f"unknown race code '{code}'. Omit the item if race is not available")
        return None
    return _RACE_CODES[code]
