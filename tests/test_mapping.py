import json

import pytest
from conftest import set_answer

from plcom2012_service.mapping import DEFAULT_LINKIDS, extract_inputs, load_linkids
from plcom2012_service.model import InputValidationError, Race


def test_example_is_mapped(example_qr):
    x = extract_inputs(example_qr)
    assert (x.age, x.education, x.bmi) == (66, 4, 26.5)
    assert x.family_history_lung_cancer is True
    assert x.current_smoker is False
    assert (x.cigarettes_per_day, x.smoking_duration_years, x.quit_years) == (20, 40, 5)
    assert x.race is None


def test_nested_items_are_found(example_qr):
    example_qr["item"] = [
        {"linkId": "group", "item": [{"linkId": "outer", "item": example_qr["item"]}]}
    ]
    assert extract_inputs(example_qr).age == 66


def test_bmi_is_computed_from_height_and_weight(example_qr):
    set_answer(example_qr, "bmi", None)
    set_answer(example_qr, "height-cm", {"valueDecimal": 180})
    set_answer(example_qr, "weight-kg", {"valueDecimal": 81})
    assert extract_inputs(example_qr).bmi == pytest.approx(25.0)


def test_bmi_missing_is_reported_once(example_qr):
    set_answer(example_qr, "bmi", None)
    with pytest.raises(InputValidationError) as exc:
        extract_inputs(example_qr)
    assert [(i.field, i.code) for i in exc.value.issues] == [("bmi", "required")]


@pytest.mark.parametrize(
    ("answer", "expected"),
    [
        ({"valueCoding": {"code": "black"}}, Race.BLACK),
        ({"valueString": " Asian "}, Race.ASIAN),
        (
            {"valueCoding": {"system": "urn:oid:2.16.840.1.113883.6.238", "code": "2054-5"}},
            Race.BLACK,
        ),
        ({"valueCoding": {"code": "2106-3"}}, Race.WHITE),
        ({"valueCoding": {"code": "pacific-islander"}}, Race.NATIVE_HAWAIIAN_PACIFIC_ISLANDER),
        ({"valueCoding": {"code": "other"}}, None),
        ({"valueCoding": {"code": "2131-1"}}, None),
    ],
)
def test_race_variants(example_qr, answer, expected):
    set_answer(example_qr, "race", answer)
    assert extract_inputs(example_qr).race == expected


def test_unknown_race_is_an_error_not_silently_ignored(example_qr):
    set_answer(example_qr, "race", {"valueString": "martian"})
    with pytest.raises(InputValidationError) as exc:
        extract_inputs(example_qr)
    assert exc.value.issues[0].field == "race"


@pytest.mark.parametrize(
    "answer",
    [{"valueBoolean": True}, {"valueCoding": {"code": "LA33-6"}}, {"valueCoding": {"code": "yes"}}],
)
def test_boolean_variants_true(example_qr, answer):
    set_answer(example_qr, "copd", answer)
    assert extract_inputs(example_qr).copd is True


def test_boolean_no_coding(example_qr):
    set_answer(example_qr, "copd", {"valueCoding": {"code": "LA32-8"}})
    assert extract_inputs(example_qr).copd is False


def test_boolean_garbage_is_rejected(example_qr):
    set_answer(example_qr, "copd", {"valueString": "maybe"})
    with pytest.raises(InputValidationError):
        extract_inputs(example_qr)


def test_current_smoker_needs_no_quit_years(example_qr):
    set_answer(example_qr, "smoking-status", {"valueCoding": {"code": "current"}})
    set_answer(example_qr, "quit-years", None)
    x = extract_inputs(example_qr)
    assert x.current_smoker is True
    assert x.quit_years == 0


def test_former_smoker_needs_quit_years(example_qr):
    set_answer(example_qr, "quit-years", None)
    with pytest.raises(InputValidationError) as exc:
        extract_inputs(example_qr)
    assert [(i.field, i.code) for i in exc.value.issues] == [("quit_years", "required")]


def test_never_smoker_gets_a_clear_message(example_qr):
    set_answer(example_qr, "smoking-status", {"valueCoding": {"code": "never"}})
    with pytest.raises(InputValidationError) as exc:
        extract_inputs(example_qr)
    assert "never smokers" in exc.value.issues[0].message


def test_all_missing_items_are_reported_at_once():
    with pytest.raises(InputValidationError) as exc:
        extract_inputs({"resourceType": "QuestionnaireResponse", "item": []})
    fields = {i.field for i in exc.value.issues}
    assert {"age", "education", "copd", "smoking_status", "cigarettes_per_day", "bmi"} <= fields
    assert "race" not in fields


def test_several_answers_for_one_item_are_rejected(example_qr):
    example_qr["item"][0]["answer"].append({"valueInteger": 70})
    with pytest.raises(InputValidationError):
        extract_inputs(example_qr)


@pytest.mark.parametrize(
    "bad", [{"valueBoolean": True}, {"valueString": "66"}, {"valueDecimal": float("inf")}]
)
def test_age_must_be_a_number(example_qr, bad):
    set_answer(example_qr, "age", bad)
    with pytest.raises(InputValidationError):
        extract_inputs(example_qr)


def test_quantity_is_accepted_for_numbers(example_qr):
    set_answer(example_qr, "age", {"valueQuantity": {"value": 66, "unit": "a"}})
    assert extract_inputs(example_qr).age == 66


def test_custom_linkids(example_qr, tmp_path):
    f = tmp_path / "map.json"
    f.write_text(json.dumps({"age": "q1-age", "copd": "q7"}))
    linkids = load_linkids(str(f))
    example_qr["item"][0]["linkId"] = "q1-age"
    set_answer(example_qr, "copd", None)
    set_answer(example_qr, "q7", {"valueBoolean": True})
    x = extract_inputs(example_qr, linkids)
    assert x.age == 66
    assert x.copd is True


def test_linkid_map_rejects_unknown_fields(tmp_path):
    f = tmp_path / "map.json"
    f.write_text(json.dumps({"agee": "x"}))
    with pytest.raises(ValueError):
        load_linkids(str(f))


def test_default_linkids_are_unique():
    assert len(set(DEFAULT_LINKIDS.values())) == len(DEFAULT_LINKIDS)
