import copy
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from plcom2012_service.config import Settings
from plcom2012_service.main import create_app

ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture
def example_qr() -> dict:
    """A fresh copy of the example QuestionnaireResponse (race omitted)."""
    return copy.deepcopy(json.loads((ROOT / "examples/questionnaire-response.json").read_text()))


@pytest.fixture
def client() -> TestClient:
    return TestClient(create_app(Settings()))


def set_answer(qr: dict, link_id: str, answer: dict | None) -> dict:
    """Replace (or with None: remove) the answer of one item."""
    qr["item"] = [i for i in qr["item"] if i["linkId"] != link_id]
    if answer is not None:
        qr["item"].append({"linkId": link_id, "answer": [answer]})
    return qr
