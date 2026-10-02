"""The example files in examples/ are what the README shows. Keep them in sync with the code."""

import json
from pathlib import Path

import pytest

from plcom2012_service.fhir import enrich_questionnaire_response
from plcom2012_service.mapping import DEFAULT_LINKIDS, extract_inputs, load_linkids
from plcom2012_service.model import calculate
from plcom2012_service.questionnaire import build_questionnaire

EXAMPLES = Path(__file__).resolve().parent.parent / "examples"


def _load(name: str) -> dict:
    return json.loads((EXAMPLES / name).read_text(encoding="utf-8"))


def test_example_questionnaire_matches_the_service():
    expected = build_questionnaire("https://example.org/fhir", DEFAULT_LINKIDS)
    assert _load("questionnaire.json") == expected


def test_example_result_matches_the_service():
    qr = _load("questionnaire-response.json")
    expected = enrich_questionnaire_response(qr, calculate(extract_inputs(qr)))
    assert _load("questionnaire-response-result.json") == expected


def test_example_linkid_map_is_valid():
    assert load_linkids(str(EXAMPLES / "linkid-map.json"))["age"] == "q1-age"


def test_quit_years_is_required_for_former_smokers_in_the_questionnaire():
    items = {i["linkId"]: i for i in _load("questionnaire.json")["item"]}
    assert items["quit-years"]["required"] is True
    assert items["quit-years"]["enableWhen"][0]["question"] == "smoking-status"


@pytest.mark.parametrize("name", ["questionnaire.json", "questionnaire-response-result.json"])
def test_examples_are_valid_json_resources(name):
    assert _load(name)["resourceType"] in {"Questionnaire", "QuestionnaireResponse"}
