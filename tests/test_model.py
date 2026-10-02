import json
from dataclasses import replace
from pathlib import Path

import pytest

from plcom2012_service.model import (
    InputValidationError,
    PlcoInput,
    Race,
    calculate,
)

VECTORS = json.loads((Path(__file__).parent / "data/reference_vectors.json").read_text())

BASE = PlcoInput(
    age=62,
    education=4,
    bmi=27,
    copd=False,
    personal_cancer_history=False,
    family_history_lung_cancer=False,
    current_smoker=False,
    cigarettes_per_day=20,
    smoking_duration_years=27,
    quit_years=10,
)


@pytest.mark.parametrize("v", VECTORS, ids=[v["name"] for v in VECTORS])
def test_matches_reference_implementation(v):
    """Golden values generated with the R package resplab/PLCOm2012 (commit 5387abc)."""
    x = PlcoInput(
        age=v["age"],
        race=Race(
            {
                "White": "white",
                "Black": "black",
                "Hispanic": "hispanic",
                "Asian": "asian",
                "American Indian": "american-indian-alaska-native",
                "Alaskan Native": "american-indian-alaska-native",
                "Native Hawaiian": "native-hawaiian-pacific-islander",
                "Pacific Islander": "native-hawaiian-pacific-islander",
            }[v["race"]]
        ),
        education=v["education"],
        bmi=v["bmi"],
        copd=v["copd"],
        personal_cancer_history=v["personal_cancer_history"],
        family_history_lung_cancer=v["family_history_lung_cancer"],
        current_smoker=v["current_smoker"],
        cigarettes_per_day=v["cigarettes_per_day"],
        smoking_duration_years=v["smoking_duration_years"],
        quit_years=v["quit_years"],
    )
    assert calculate(x).probability == pytest.approx(v["probability"], rel=1e-10)


def test_race_not_provided_equals_reference_category():
    without = calculate(BASE)
    white = calculate(replace(BASE, race=Race.WHITE))
    assert without.probability == white.probability
    assert without.race_provided is False
    assert white.race_provided is True


def test_race_changes_risk_in_expected_direction():
    p = {r: calculate(replace(BASE, race=r)).probability for r in Race}
    assert p[Race.BLACK] > p[Race.WHITE] > p[Race.ASIAN] > p[Race.HISPANIC]
    assert p[Race.NATIVE_HAWAIIAN_PACIFIC_ISLANDER] > p[Race.BLACK]


def test_current_smoker_ignores_quit_years():
    current = replace(BASE, current_smoker=True, quit_years=0)
    with_quit = replace(BASE, current_smoker=True, quit_years=5)
    assert calculate(with_quit).probability == calculate(current).probability
    assert any("ignored" in w for w in calculate(with_quit).warnings)


def test_risk_increases_with_age_and_decreases_with_quit_years():
    assert calculate(replace(BASE, age=70)).probability > calculate(BASE).probability
    assert calculate(replace(BASE, quit_years=20)).probability < calculate(BASE).probability


def test_probability_is_a_probability_and_percent_matches():
    r = calculate(BASE)
    assert 0 < r.probability < 1
    assert r.risk_percent == pytest.approx(r.probability * 100)


@pytest.mark.parametrize("age", [50, 80])
def test_age_outside_development_range_warns_but_calculates(age):
    r = calculate(replace(BASE, age=age, smoking_duration_years=20, quit_years=5))
    assert any("development cohort" in w for w in r.warnings)


def test_age_inside_development_range_has_no_warning():
    assert calculate(BASE).warnings == []


@pytest.mark.parametrize(
    ("change", "field"),
    [
        ({"age": 17}, "age"),
        ({"age": 111}, "age"),
        ({"education": 0}, "education"),
        ({"education": 7}, "education"),
        ({"bmi": 5}, "bmi"),
        ({"bmi": 150}, "bmi"),
        ({"cigarettes_per_day": 0}, "cigarettes_per_day"),
        ({"cigarettes_per_day": 500}, "cigarettes_per_day"),
        ({"smoking_duration_years": 0}, "smoking_duration_years"),
        ({"quit_years": -1}, "quit_years"),
        ({"smoking_duration_years": 50, "quit_years": 20}, "smoking_duration_years"),
    ],
)
def test_impossible_values_are_rejected(change, field):
    with pytest.raises(InputValidationError) as exc:
        calculate(replace(BASE, **change))
    assert field in {i.field for i in exc.value.issues}


def test_all_issues_are_reported_together():
    with pytest.raises(InputValidationError) as exc:
        calculate(replace(BASE, age=5, bmi=1, education=9))
    assert {i.field for i in exc.value.issues} == {"age", "bmi", "education"}
