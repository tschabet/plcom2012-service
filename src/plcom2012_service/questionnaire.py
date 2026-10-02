"""Reference Questionnaire matching the linkIds the service reads.

It documents the expected input and contains the result items (read-only), so that a
QuestionnaireResponse enriched by this service is valid against it.
"""

from __future__ import annotations

from typing import Any

from .fhir import (
    RESULT_GROUP,
    RESULT_MODEL,
    RESULT_RACE,
    RESULT_RISK,
    RESULT_WARNING,
)

EDUCATION_LEVELS = [
    ("1", "Less than high-school graduate"),
    ("2", "High-school graduate"),
    ("3", "Some training after high school"),
    ("4", "Some college"),
    ("5", "College graduate"),
    ("6", "Postgraduate or professional degree"),
]
RACE_OPTIONS = [
    ("white", "White"),
    ("black", "Black or African American"),
    ("hispanic", "Hispanic or Latino"),
    ("asian", "Asian"),
    ("american-indian-alaska-native", "American Indian or Alaska Native"),
    ("native-hawaiian-pacific-islander", "Native Hawaiian or other Pacific Islander"),
]


def _choice(system: str, options: list[tuple[str, str]]) -> list[dict[str, Any]]:
    return [
        {"valueCoding": {"system": system, "code": code, "display": display}}
        for code, display in options
    ]


def build_questionnaire(canonical_base: str, linkids: dict[str, str]) -> dict[str, Any]:
    cs = f"{canonical_base}/CodeSystem"
    L = linkids  # noqa: N806

    def item(field: str, text: str, type_: str, **extra: Any) -> dict[str, Any]:
        return {"linkId": L[field], "text": text, "type": type_, **extra}

    return {
        "resourceType": "Questionnaire",
        "id": "plcom2012",
        "url": f"{canonical_base}/Questionnaire/plcom2012",
        "version": "0.1.0",
        "name": "PLCOm2012Input",
        "title": "PLCOm2012 6-year lung cancer risk: input",
        "status": "draft",
        "subjectType": ["Patient"],
        "description": (
            "Input of the PLCOm2012 model for current and former smokers. "
            "Result items are filled by plcom2012-service."
        ),
        "item": [
            item("age", "Age (years)", "integer", required=True),
            item(
                "race",
                "Race / ethnicity (optional)",
                "choice",
                required=False,
                answerOption=_choice(f"{cs}/plcom2012-race", RACE_OPTIONS),
            ),
            item(
                "education",
                "Highest education (level 1-6)",
                "choice",
                required=True,
                answerOption=_choice(f"{cs}/plcom2012-education", EDUCATION_LEVELS),
            ),
            item("bmi", "Body mass index (kg/m2)", "decimal", required=False),
            item("height_cm", "Height (cm), alternative to BMI", "decimal", required=False),
            item("weight_kg", "Weight (kg), alternative to BMI", "decimal", required=False),
            item("copd", "Chronic obstructive pulmonary disease (COPD)", "boolean", required=True),
            item(
                "personal_cancer_history",
                "Personal history of cancer",
                "boolean",
                required=True,
            ),
            item(
                "family_history_lung_cancer",
                "Family history of lung cancer",
                "boolean",
                required=True,
            ),
            item(
                "smoking_status",
                "Smoking status",
                "choice",
                required=True,
                answerOption=_choice(
                    f"{cs}/plcom2012-smoking-status",
                    [("current", "Current smoker"), ("former", "Former smoker")],
                ),
            ),
            item("cigarettes_per_day", "Cigarettes per day", "decimal", required=True),
            item("smoking_duration_years", "Years of smoking", "decimal", required=True),
            item(
                "quit_years",
                "Years since quitting",
                "decimal",
                required=True,  # only applies while enabled, i.e. for former smokers
                enableWhen=[
                    {
                        "question": L["smoking_status"],
                        "operator": "=",
                        "answerCoding": {
                            "system": f"{cs}/plcom2012-smoking-status",
                            "code": "former",
                        },
                    }
                ],
            ),
            {
                "linkId": RESULT_GROUP,
                "text": "PLCOm2012 result",
                "type": "group",
                "readOnly": True,
                "item": [
                    {
                        "linkId": RESULT_RISK,
                        "text": "6-year lung cancer risk",
                        "type": "quantity",
                        "readOnly": True,
                    },
                    {
                        "linkId": RESULT_RACE,
                        "text": "Handling of race",
                        "type": "string",
                        "readOnly": True,
                    },
                    {"linkId": RESULT_MODEL, "text": "Model", "type": "string", "readOnly": True},
                    {
                        "linkId": RESULT_WARNING,
                        "text": "Warnings",
                        "type": "string",
                        "readOnly": True,
                        "repeats": True,
                    },
                ],
            },
        ],
    }
