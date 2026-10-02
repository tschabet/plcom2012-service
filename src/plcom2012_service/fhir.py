"""Build the FHIR resources the service returns."""

from __future__ import annotations

import copy
from datetime import UTC, datetime
from typing import Any

from . import __version__
from .model import FieldIssue, PlcoResult

FHIR_JSON = "application/fhir+json"

RESULT_GROUP = "plcom2012-result"
RESULT_RISK = "plcom2012-risk-percent"
RESULT_RACE = "plcom2012-race-handling"
RESULT_MODEL = "plcom2012-model"
RESULT_WARNING = "plcom2012-warning"

OBSERVATION_CODE = "plcom2012-6y-lung-cancer-risk"
MODEL_TEXT = "PLCOm2012 (Tammemägi et al., N Engl J Med 2013;368:728-736)"


def _quantity(percent: float) -> dict[str, Any]:
    return {
        "value": round(percent, 4),
        "unit": "%",
        "system": "http://unitsofmeasure.org",
        "code": "%",
    }


def _race_text(result: PlcoResult) -> str:
    if result.race_provided:
        return "Race provided: race term of the model applied."
    return (
        "Race not provided: no race term applied (identical to the reference category "
        "White / American Indian / Alaska Native)."
    )


def enrich_questionnaire_response(qr: dict[str, Any], result: PlcoResult) -> dict[str, Any]:
    """Return a copy of the QuestionnaireResponse with the result group appended.

    An existing result group (e.g. from an earlier call) is replaced, not duplicated.
    """
    out = copy.deepcopy(qr)
    items = [i for i in out.get("item", []) if i.get("linkId") != RESULT_GROUP]

    children: list[dict[str, Any]] = [
        {
            "linkId": RESULT_RISK,
            "text": "6-year lung cancer risk",
            "answer": [{"valueQuantity": _quantity(result.risk_percent)}],
        },
        {
            "linkId": RESULT_RACE,
            "text": "Handling of race",
            "answer": [{"valueString": _race_text(result)}],
        },
        {
            "linkId": RESULT_MODEL,
            "text": "Model",
            "answer": [{"valueString": f"{MODEL_TEXT}; plcom2012-service {__version__}"}],
        },
    ]
    if result.warnings:
        children.append(
            {
                "linkId": RESULT_WARNING,
                "text": "Warnings",
                "answer": [{"valueString": w} for w in result.warnings],
            }
        )

    items.append({"linkId": RESULT_GROUP, "text": "PLCOm2012 result", "item": children})
    out["item"] = items
    return out


def build_observation(
    qr: dict[str, Any], result: PlcoResult, canonical_base: str
) -> dict[str, Any]:
    obs: dict[str, Any] = {
        "resourceType": "Observation",
        "status": "final",
        "category": [
            {
                "coding": [
                    {
                        "system": "http://terminology.hl7.org/CodeSystem/observation-category",
                        "code": "survey",
                        "display": "Survey",
                    }
                ]
            }
        ],
        "code": {
            "coding": [
                {
                    "system": f"{canonical_base}/CodeSystem/plcom2012",
                    "code": OBSERVATION_CODE,
                    "display": "PLCOm2012 6-year lung cancer risk",
                }
            ],
            "text": "PLCOm2012 6-year lung cancer risk",
        },
        "effectiveDateTime": datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z"),
        "valueQuantity": _quantity(result.risk_percent),
        "method": {"text": MODEL_TEXT},
        "note": [{"text": _race_text(result)}, *({"text": w} for w in result.warnings)],
    }
    if "subject" in qr:
        obs["subject"] = copy.deepcopy(qr["subject"])
    if "encounter" in qr:
        obs["encounter"] = copy.deepcopy(qr["encounter"])
    if qr.get("id"):
        obs["derivedFrom"] = [{"reference": f"QuestionnaireResponse/{qr['id']}"}]
    return obs


def operation_outcome(
    issues: list[dict[str, Any]],
) -> dict[str, Any]:
    return {"resourceType": "OperationOutcome", "issue": issues}


def simple_outcome(code: str, text: str, severity: str = "error") -> dict[str, Any]:
    return operation_outcome([{"severity": severity, "code": code, "details": {"text": text}}])


def outcome_from_field_issues(issues: list[FieldIssue], linkids: dict[str, str]) -> dict[str, Any]:
    fhir_issues = []
    for i in issues:
        link_id = linkids.get(i.field)
        text = i.message
        if link_id and not text.startswith("item '"):
            text = f"item '{link_id}': {text}"
        entry: dict[str, Any] = {
            "severity": "error",
            "code": i.code,
            "details": {"text": text},
        }
        if link_id:
            entry["expression"] = [f"QuestionnaireResponse.repeat(item).where(linkId='{link_id}')"]
        fhir_issues.append(entry)
    return operation_outcome(fhir_issues)
