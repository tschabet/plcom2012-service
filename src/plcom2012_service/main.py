"""FastAPI application: FHIR operation $plcom2012 on QuestionnaireResponse."""

from __future__ import annotations

import json
import logging
import secrets
from typing import Any

from fastapi import Depends, FastAPI, Header, Request
from fastapi.responses import JSONResponse

from . import __version__
from .config import Settings
from .fhir import (
    FHIR_JSON,
    build_observation,
    enrich_questionnaire_response,
    outcome_from_field_issues,
    simple_outcome,
)
from .mapping import extract_inputs, load_linkids
from .model import InputValidationError, calculate
from .questionnaire import build_questionnaire

log = logging.getLogger("plcom2012")

OUTPUTS = ("questionnaireresponse", "observation")

DESCRIPTION = """
Calculates the **PLCOm2012 6-year lung cancer risk**.

`POST /fhir/QuestionnaireResponse/$plcom2012` takes a filled-in FHIR *QuestionnaireResponse*
and returns it extended by the risk (default), or an *Observation* (`?output=observation`).

**Do not send real patient data to a public test instance.**
Research / demonstration software, not a certified medical device.
"""


class FhirError(Exception):
    def __init__(self, status: int, outcome: dict[str, Any]):
        self.status = status
        self.outcome = outcome


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings.from_env()
    linkids = load_linkids(settings.linkid_map_path)

    app = FastAPI(title="PLCOm2012 FHIR service", version=__version__, description=DESCRIPTION)

    @app.exception_handler(FhirError)
    async def _fhir_error(_: Request, exc: FhirError) -> JSONResponse:
        return JSONResponse(exc.outcome, status_code=exc.status, media_type=FHIR_JSON)

    def require_api_key(x_api_key: str | None = Header(default=None)) -> None:
        if settings.api_key and not (
            x_api_key and secrets.compare_digest(x_api_key, settings.api_key)
        ):
            raise FhirError(401, simple_outcome("login", "Missing or invalid X-API-Key header"))

    @app.get("/", include_in_schema=False)
    async def index() -> dict[str, str]:
        return {
            "service": "plcom2012-service",
            "version": __version__,
            "docs": "/docs",
            "operation": "POST /fhir/QuestionnaireResponse/$plcom2012",
            "warning": "Do not send real patient data to a public test instance.",
        }

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok", "version": __version__}

    @app.get("/fhir/Questionnaire/plcom2012", response_class=JSONResponse)
    async def reference_questionnaire() -> JSONResponse:
        return JSONResponse(
            build_questionnaire(settings.canonical_base, linkids), media_type=FHIR_JSON
        )

    @app.post(
        "/fhir/QuestionnaireResponse/$plcom2012",
        dependencies=[Depends(require_api_key)],
        summary="Calculate the PLCOm2012 6-year lung cancer risk",
        openapi_extra={
            "requestBody": {
                "required": True,
                "content": {
                    "application/fhir+json": {"schema": {"type": "object"}},
                    "application/json": {"schema": {"type": "object"}},
                },
            }
        },
    )
    async def plcom2012_operation(
        request: Request, output: str = "questionnaireresponse"
    ) -> JSONResponse:
        if output not in OUTPUTS:
            raise FhirError(
                400, simple_outcome("invalid", f"output must be one of: {', '.join(OUTPUTS)}")
            )

        declared = request.headers.get("content-length")
        if declared and declared.isdigit() and int(declared) > settings.max_body_bytes:
            raise FhirError(413, simple_outcome("too-costly", "Request body too large"))
        body = await request.body()
        if len(body) > settings.max_body_bytes:
            raise FhirError(413, simple_outcome("too-costly", "Request body too large"))

        try:
            qr = json.loads(body)
        except ValueError as exc:
            raise FhirError(400, simple_outcome("structure", "Body is not valid JSON")) from exc
        if not isinstance(qr, dict) or qr.get("resourceType") != "QuestionnaireResponse":
            hint = ""
            if isinstance(qr, dict) and qr.get("resourceType") == "Questionnaire":
                hint = (
                    " (a Questionnaire is the empty form; send the filled-in QuestionnaireResponse)"
                )
            raise FhirError(
                400, simple_outcome("structure", f"Expected a QuestionnaireResponse resource{hint}")
            )

        try:
            result = calculate(extract_inputs(qr, linkids))
        except InputValidationError as exc:
            raise FhirError(422, outcome_from_field_issues(exc.issues, linkids)) from exc

        log.info("calculated output=%s warnings=%d", output, len(result.warnings))
        if output == "observation":
            payload = build_observation(qr, result, settings.canonical_base)
        else:
            payload = enrich_questionnaire_response(qr, result)
        return JSONResponse(payload, media_type=FHIR_JSON)

    return app


app = create_app()
