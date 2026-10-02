import json

import pytest
from conftest import set_answer
from fastapi.testclient import TestClient

from plcom2012_service.config import Settings
from plcom2012_service.main import create_app
from plcom2012_service.mapping import DEFAULT_LINKIDS, extract_inputs
from plcom2012_service.model import calculate

URL = "/fhir/QuestionnaireResponse/$plcom2012"


def _group(resource: dict) -> dict:
    return next(i for i in resource["item"] if i["linkId"] == "plcom2012-result")


def _child(group: dict, link_id: str) -> dict:
    return next(i for i in group["item"] if i["linkId"] == link_id)


def test_returns_enriched_questionnaire_response(client, example_qr):
    r = client.post(URL, json=example_qr)
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("application/fhir+json")
    body = r.json()
    assert body["resourceType"] == "QuestionnaireResponse"

    expected = calculate(extract_inputs(example_qr)).risk_percent
    quantity = _child(_group(body), "plcom2012-risk-percent")["answer"][0]["valueQuantity"]
    assert quantity["value"] == pytest.approx(expected, abs=1e-4)
    assert (quantity["unit"], quantity["code"]) == ("%", "%")


def test_original_items_and_metadata_are_untouched(client, example_qr):
    body = client.post(URL, json=example_qr).json()
    assert body["item"][:-1] == example_qr["item"]
    assert body["subject"] == example_qr["subject"]
    assert body["id"] == example_qr["id"]


def test_resubmitting_replaces_the_result_instead_of_duplicating(client, example_qr):
    once = client.post(URL, json=example_qr).json()
    twice = client.post(URL, json=once).json()
    assert [i["linkId"] for i in twice["item"]].count("plcom2012-result") == 1


def test_race_handling_is_reported(client, example_qr):
    text = _child(_group(client.post(URL, json=example_qr).json()), "plcom2012-race-handling")
    assert "not provided" in text["answer"][0]["valueString"]

    set_answer(example_qr, "race", {"valueCoding": {"code": "asian"}})
    text = _child(_group(client.post(URL, json=example_qr).json()), "plcom2012-race-handling")
    assert text["answer"][0]["valueString"].startswith("Race provided")


def test_warning_is_part_of_the_result(client, example_qr):
    set_answer(example_qr, "age", {"valueInteger": 80})
    group = _group(client.post(URL, json=example_qr).json())
    assert "development cohort" in _child(group, "plcom2012-warning")["answer"][0]["valueString"]


def test_observation_output(client, example_qr):
    r = client.post(URL + "?output=observation", json=example_qr)
    assert r.status_code == 200
    obs = r.json()
    assert obs["resourceType"] == "Observation"
    assert obs["status"] == "final"
    assert obs["subject"] == example_qr["subject"]
    assert obs["derivedFrom"] == [{"reference": "QuestionnaireResponse/example-1"}]
    assert obs["valueQuantity"]["unit"] == "%"
    assert obs["code"]["coding"][0]["code"] == "plcom2012-6y-lung-cancer-risk"

    expected = calculate(extract_inputs(example_qr)).risk_percent
    assert obs["valueQuantity"]["value"] == pytest.approx(expected, abs=1e-4)


def test_observation_without_subject_or_id(client, example_qr):
    del example_qr["subject"], example_qr["id"]
    obs = client.post(URL + "?output=observation", json=example_qr).json()
    assert "subject" not in obs
    assert "derivedFrom" not in obs


def test_unknown_output_is_rejected(client, example_qr):
    r = client.post(URL + "?output=pdf", json=example_qr)
    assert r.status_code == 400
    assert r.json()["resourceType"] == "OperationOutcome"


def test_invalid_json(client):
    r = client.post(URL, content=b"{not json", headers={"content-type": "application/json"})
    assert r.status_code == 400
    assert r.json()["resourceType"] == "OperationOutcome"


def test_wrong_resource_type(client):
    r = client.post(URL, json={"resourceType": "Patient"})
    assert r.status_code == 400


def test_sending_a_questionnaire_gets_a_helpful_hint(client):
    r = client.post(URL, json={"resourceType": "Questionnaire"})
    assert r.status_code == 400
    assert "filled-in QuestionnaireResponse" in r.json()["issue"][0]["details"]["text"]


def test_missing_items_return_422_with_expressions(client, example_qr):
    set_answer(example_qr, "age", None)
    set_answer(example_qr, "copd", None)
    r = client.post(URL, json=example_qr)
    assert r.status_code == 422
    issues = r.json()["issue"]
    assert {i["code"] for i in issues} == {"required"}
    assert {i["expression"][0] for i in issues} == {
        "QuestionnaireResponse.repeat(item).where(linkId='age')",
        "QuestionnaireResponse.repeat(item).where(linkId='copd')",
    }


def test_implausible_value_returns_422_naming_the_item(client, example_qr):
    set_answer(example_qr, "bmi", {"valueDecimal": 270})
    r = client.post(URL, json=example_qr)
    assert r.status_code == 422
    assert "item 'bmi'" in r.json()["issue"][0]["details"]["text"]


def test_never_smoker_gets_422(client, example_qr):
    set_answer(example_qr, "smoking-status", {"valueCoding": {"code": "never"}})
    r = client.post(URL, json=example_qr)
    assert r.status_code == 422
    assert "never smokers" in r.json()["issue"][0]["details"]["text"]


def test_body_size_limit(example_qr):
    small = TestClient(create_app(Settings(max_body_bytes=100)))
    assert small.post(URL, json=example_qr).status_code == 413


def test_api_key_is_enforced_when_configured(example_qr):
    secured = TestClient(create_app(Settings(api_key="s3cret")))
    assert secured.post(URL, json=example_qr).status_code == 401
    assert secured.post(URL, json=example_qr, headers={"X-API-Key": "wrong"}).status_code == 401
    assert secured.post(URL, json=example_qr, headers={"X-API-Key": "s3cret"}).status_code == 200
    assert secured.get("/health").status_code == 200  # health stays open


def test_health_and_index(client):
    assert client.get("/health").json()["status"] == "ok"
    assert "patient data" in client.get("/").json()["warning"]


def test_reference_questionnaire_covers_every_linkid_the_service_reads(client):
    q = client.get("/fhir/Questionnaire/plcom2012").json()
    assert q["resourceType"] == "Questionnaire"

    def ids(items):
        for i in items:
            yield i["linkId"]
            yield from ids(i.get("item", []))

    present = set(ids(q["item"]))
    assert set(DEFAULT_LINKIDS.values()) <= present
    assert {"plcom2012-result", "plcom2012-risk-percent"} <= present


def test_enriched_response_only_adds_linkids_known_to_the_questionnaire(client, example_qr):
    q = client.get("/fhir/Questionnaire/plcom2012").json()

    def ids(items):
        for i in items:
            yield i["linkId"]
            yield from ids(i.get("item", []))

    allowed = set(ids(q["item"]))
    body = client.post(URL, json=example_qr).json()
    set_answer(example_qr, "age", {"valueInteger": 80})  # also exercise the warning item
    body_with_warning = client.post(URL, json=example_qr).json()
    for b in (body, body_with_warning):
        assert set(ids(b["item"])) <= allowed


def test_canonical_base_is_configurable(example_qr):
    c = TestClient(create_app(Settings(canonical_base="https://fhir.example.com/plcom")))
    obs = c.post(URL + "?output=observation", json=example_qr).json()
    assert (
        obs["code"]["coding"][0]["system"] == "https://fhir.example.com/plcom/CodeSystem/plcom2012"
    )
    assert (
        c.get("/fhir/Questionnaire/plcom2012")
        .json()["url"]
        .startswith("https://fhir.example.com/plcom/")
    )


def test_example_file_roundtrips_as_json(client, example_qr):
    assert json.loads(json.dumps(client.post(URL, json=example_qr).json()))
