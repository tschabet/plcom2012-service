"""Pin the model constants to Table 2 of Tammemägi et al., N Engl J Med 2013;368:728-736.

The paper prints a beta coefficient and an odds ratio (rounded to 3 decimals) per variable.
The betas must match exactly, and exp(beta) must reproduce the printed odds ratio, which guards
against transcription errors in either direction.
"""

import math

import pytest

from plcom2012_service import model as m

# (name, constant in model.py, beta as printed, odds ratio as printed)
TABLE_2 = [
    ("age per year", m.COEF_AGE, 0.0778868, 1.081),
    ("black", m.RACE_TERMS[m.Race.BLACK], 0.3944778, 1.484),
    ("hispanic", m.RACE_TERMS[m.Race.HISPANIC], -0.7434744, 0.475),
    ("asian", m.RACE_TERMS[m.Race.ASIAN], -0.466585, 0.627),
    (
        "native hawaiian / pacific islander",
        m.RACE_TERMS[m.Race.NATIVE_HAWAIIAN_PACIFIC_ISLANDER],
        1.027152,
        2.793,
    ),
    ("education per level", m.COEF_EDUCATION, -0.0812744, 0.922),
    ("bmi per unit", m.COEF_BMI, -0.0274194, 0.973),
    ("copd", m.COEF_COPD, 0.3553063, 1.427),
    ("personal history of cancer", m.COEF_PERSONAL_CANCER, 0.4589971, 1.582),
    ("family history of lung cancer", m.COEF_FAMILY_LUNG_CANCER, 0.587185, 1.799),
    ("current vs former smoker", m.COEF_CURRENT_SMOKER, 0.2597431, 1.297),
    ("smoking duration per year", m.COEF_DURATION, 0.0317321, 1.032),
    ("smoking quit time per year", m.COEF_QUIT, -0.0308572, 0.970),
]


@pytest.mark.parametrize(
    ("name", "coef", "beta", "odds_ratio"), TABLE_2, ids=[t[0] for t in TABLE_2]
)
def test_coefficient_matches_published_table(name, coef, beta, odds_ratio):
    assert coef == beta
    assert round(math.exp(beta), 3) == pytest.approx(odds_ratio, abs=1e-9)


def test_smoking_intensity_coefficient_and_model_constant():
    # Table 2 prints no odds ratio for smoking intensity (non-linear term) and for the constant.
    assert m.COEF_INTENSITY == -1.822606
    assert m.INTERCEPT == -4.532506


def test_centering_values_from_table_footnotes():
    assert m.CENTER_AGE == 62
    assert m.CENTER_EDUCATION == 4
    assert m.CENTER_BMI == 27
    assert m.CENTER_DURATION == 27
    assert m.CENTER_QUIT == 10
    assert m.CENTER_INTENSITY == 0.4021541613


def test_white_and_american_indian_alaska_native_are_both_reference_groups():
    assert m.RACE_TERMS[m.Race.WHITE] == 0.0
    assert m.RACE_TERMS[m.Race.AMERICAN_INDIAN_ALASKA_NATIVE] == 0.0


def test_reference_profile_from_the_paper_figure():
    """Figure 1 profile: 62 y, white, some college, BMI 27, no COPD/cancer/family history,
    former smoker, 27 years smoked, quit 10 years ago. With intensity 10/0.4021541613 cigarettes
    per day the intensity term is 0, so the linear predictor equals the model constant."""
    x = m.PlcoInput(
        age=62,
        education=4,
        bmi=27,
        copd=False,
        personal_cancer_history=False,
        family_history_lung_cancer=False,
        current_smoker=False,
        cigarettes_per_day=10 / m.CENTER_INTENSITY,
        smoking_duration_years=27,
        quit_years=10,
        race=m.Race.WHITE,
    )
    assert m.calculate(x).linear_predictor == pytest.approx(m.INTERCEPT, abs=1e-12)
