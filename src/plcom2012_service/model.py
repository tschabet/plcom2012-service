"""PLCOm2012 risk model (pure calculation, no FHIR, no I/O).

Source of all numbers: Tammemägi MC et al., "Selection criteria for lung-cancer screening",
N Engl J Med 2013;368:728-736, Table 2 (beta coefficients and model constant) and its footnotes
(centering values; smoking intensity enters as ((cigarettes per day / 10) ** -1) - 0.4021541613).

The model is a logistic regression for the probability of a lung cancer diagnosis within 6 years
in ever-smokers. tests/test_paper_table2.py pins the constants to the published table.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from enum import StrEnum


class Race(StrEnum):
    """Race / ethnicity categories of the original model.

    White, American Indian and Alaska Native share the reference category (term 0),
    exactly as in the original model.
    """

    WHITE = "white"
    AMERICAN_INDIAN_ALASKA_NATIVE = "american-indian-alaska-native"
    BLACK = "black"
    HISPANIC = "hispanic"
    ASIAN = "asian"
    NATIVE_HAWAIIAN_PACIFIC_ISLANDER = "native-hawaiian-pacific-islander"


INTERCEPT = -4.532506

COEF_AGE = 0.0778868  # per year, centered at 62
COEF_EDUCATION = -0.0812744  # per level (1-6), centered at 4
COEF_BMI = -0.0274194  # per kg/m2, centered at 27
COEF_COPD = 0.3553063
COEF_PERSONAL_CANCER = 0.4589971
COEF_FAMILY_LUNG_CANCER = 0.587185
COEF_CURRENT_SMOKER = 0.2597431
COEF_INTENSITY = -1.822606  # on (cigarettes_per_day / 10) ** -1, centered at 0.4021541613
COEF_DURATION = 0.0317321  # per year, centered at 27
COEF_QUIT = -0.0308572  # per year, centered at 10

CENTER_AGE = 62
CENTER_EDUCATION = 4
CENTER_BMI = 27
CENTER_INTENSITY = 0.4021541613
CENTER_DURATION = 27
CENTER_QUIT = 10

RACE_TERMS: dict[Race, float] = {
    Race.WHITE: 0.0,
    Race.AMERICAN_INDIAN_ALASKA_NATIVE: 0.0,
    Race.BLACK: 0.3944778,
    Race.HISPANIC: -0.7434744,
    Race.ASIAN: -0.466585,
    Race.NATIVE_HAWAIIAN_PACIFIC_ISLANDER: 1.027152,
}

# Development cohort of the model (PLCO trial): age 55-74. Outside of it we only warn.
DEVELOPMENT_AGE_RANGE = (55, 74)


@dataclass(frozen=True)
class FieldIssue:
    """A problem with one input value. `field` is the model field name."""

    field: str
    message: str
    code: str = "invalid"  # FHIR issue-type: "invalid" or "required"


class InputValidationError(ValueError):
    def __init__(self, issues: list[FieldIssue]):
        self.issues = issues
        super().__init__("; ".join(f"{i.field}: {i.message}" for i in issues))


@dataclass(frozen=True)
class PlcoInput:
    age: float
    education: int
    bmi: float
    copd: bool
    personal_cancer_history: bool
    family_history_lung_cancer: bool
    current_smoker: bool
    cigarettes_per_day: float
    smoking_duration_years: float
    quit_years: float = 0.0
    race: Race | None = None


@dataclass(frozen=True)
class PlcoResult:
    probability: float
    linear_predictor: float
    race_term: float
    race_provided: bool
    warnings: list[str] = field(default_factory=list)

    @property
    def risk_percent(self) -> float:
        return self.probability * 100.0


def validate(x: PlcoInput) -> list[str]:
    """Check the input. Raises InputValidationError for impossible values.

    Returns a list of warnings for values that are calculable but outside
    the range the model was developed for.
    """
    issues: list[FieldIssue] = []
    warnings: list[str] = []

    if not 18 <= x.age <= 110:
        issues.append(FieldIssue("age", "must be between 18 and 110 years"))
    if x.education not in (1, 2, 3, 4, 5, 6):
        issues.append(FieldIssue("education", "must be an integer from 1 to 6"))
    if not 10 <= x.bmi <= 80:
        issues.append(FieldIssue("bmi", "must be between 10 and 80 kg/m2"))
    if not 0 < x.cigarettes_per_day <= 200:
        issues.append(FieldIssue("cigarettes_per_day", "must be greater than 0 and at most 200"))
    if x.smoking_duration_years <= 0:
        issues.append(FieldIssue("smoking_duration_years", "must be greater than 0"))
    if x.quit_years < 0:
        issues.append(FieldIssue("quit_years", "must not be negative"))

    if not issues and x.smoking_duration_years + x.quit_years > x.age + 1:
        issues.append(
            FieldIssue(
                "smoking_duration_years",
                "smoking duration plus years since quitting cannot exceed age",
            )
        )

    if issues:
        raise InputValidationError(issues)

    lo, hi = DEVELOPMENT_AGE_RANGE
    if not lo <= x.age <= hi:
        warnings.append(
            f"Age {x.age:g} is outside {lo}-{hi} years, the age range of the model's "
            "development cohort (PLCO trial). The value is calculated but less reliable."
        )
    if x.current_smoker and x.quit_years:
        warnings.append("quit_years was ignored because the person is a current smoker.")
    return warnings


def calculate(x: PlcoInput) -> PlcoResult:
    """Calculate the 6-year lung cancer probability (0..1)."""
    warnings = validate(x)

    race_term = RACE_TERMS[x.race] if x.race is not None else 0.0
    quit_years = 0.0 if x.current_smoker else x.quit_years

    xb = (
        INTERCEPT
        + COEF_AGE * (x.age - CENTER_AGE)
        + COEF_EDUCATION * (x.education - CENTER_EDUCATION)
        + COEF_BMI * (x.bmi - CENTER_BMI)
        + COEF_COPD * x.copd
        + COEF_PERSONAL_CANCER * x.personal_cancer_history
        + COEF_FAMILY_LUNG_CANCER * x.family_history_lung_cancer
        + COEF_CURRENT_SMOKER * x.current_smoker
        + COEF_INTENSITY * ((x.cigarettes_per_day / 10.0) ** -1 - CENTER_INTENSITY)
        + COEF_DURATION * (x.smoking_duration_years - CENTER_DURATION)
        + COEF_QUIT * (quit_years - CENTER_QUIT)
        + race_term
    )

    return PlcoResult(
        probability=_logistic(xb),
        linear_predictor=xb,
        race_term=race_term,
        race_provided=x.race is not None,
        warnings=warnings,
    )


def _logistic(z: float) -> float:
    if z >= 0:
        return 1.0 / (1.0 + math.exp(-z))
    e = math.exp(z)
    return e / (1.0 + e)
