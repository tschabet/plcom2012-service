# plcom2012-service

[![CI](https://github.com/tschabet/plcom2012-service/actions/workflows/ci.yml/badge.svg)](https://github.com/tschabet/plcom2012-service/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

A small REST service that calculates the **PLCOm2012 6-year lung cancer risk** (Tammemägi et al.,
*N Engl J Med* 2013;368:728-736) for current and former smokers. It speaks **FHIR R4**: you send a
filled-in `QuestionnaireResponse`, you get the same `QuestionnaireResponse` back with the risk in
percent added. If you prefer a separate resource, you can get an `Observation` instead.

> **Not a certified medical device.** Research and demonstration software, provided as is (see
> [LICENSE](LICENSE)). Using a risk calculation to support screening decisions in clinical practice
> can make software a medical device under the EU MDR and comparable regulations. Do not send real
> patient data to a public test instance. FHIR output has not yet been checked with the official
> HL7 validator.

## How it fits together

```
 Questionnaire        the empty form (GET /fhir/Questionnaire/plcom2012)
      │  filled in by patient or clinician in your portal / EHR
      ▼
 QuestionnaireResponse ──POST /fhir/QuestionnaireResponse/$plcom2012──►  plcom2012-service
      ▲                                                                        │
      └──────────── same QuestionnaireResponse + result group (risk in %) ◄────┘
                    or, with ?output=observation, an Observation
```

The service is stateless: it stores nothing and calls nothing else.

## Quick start

You need either Docker, or Python 3.11 or newer.

**Option A: Docker**

```bash
git clone https://github.com/tschabet/plcom2012-service.git
cd plcom2012-service
docker build -t plcom2012-service .
docker run -d --name plcom2012 -p 8000:8000 plcom2012-service
```

If port 8000 is already in use on your machine, use e.g. `-p 8010:8000` and replace 8000 by 8010 below.

**Option B: Python**

```bash
git clone https://github.com/tschabet/plcom2012-service.git
cd plcom2012-service
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
uvicorn plcom2012_service.main:app
```

**Check that it runs**

```bash
curl http://localhost:8000/health
```

Expected: `{"status":"ok","version":"0.1.0"}`

**First calculation** with the example in `examples/`:

```bash
curl -s -X POST 'http://localhost:8000/fhir/QuestionnaireResponse/$plcom2012' \
  -H 'Content-Type: application/fhir+json' \
  -d @examples/questionnaire-response.json
```

Use single quotes around the URL, otherwise your shell tries to expand `$plcom2012`. The response is
the example `QuestionnaireResponse` plus a result group with `3.7994 %`. Interactive API docs are at
http://localhost:8000/docs.

## Test instance

A running instance is available at <https://plcom2012.lab.schabetsberger.info> (interactive API docs at `/docs`). It is a lab deployment for testing: rate limited, no availability guarantee, and it may change or disappear without notice.

**Use synthetic data only. Never send real patient data.** The instance runs with `PLCOM_CANONICAL_BASE=https://plcom2012.lab.schabetsberger.info/fhir`.

```
curl https://plcom2012.lab.schabetsberger.info/health
```

## The Questionnaire (the form)

`GET /fhir/Questionnaire/plcom2012` returns the reference Questionnaire, the same file as
[`examples/questionnaire.json`](examples/questionnaire.json). It defines the items the service reads
(matched by `linkId`) and the read-only result items it writes.

| linkId | Type | Required | Meaning |
|---|---|---|---|
| `age` | integer | yes | Age in years |
| `race` | choice | **no** | See [Race is optional](#race-is-optional) |
| `education` | choice, 1-6 | yes | Education level, see below |
| `bmi` | decimal | yes, or `height-cm` + `weight-kg` | Body mass index in kg/m² |
| `height-cm`, `weight-kg` | decimal | alternative to `bmi` | BMI is computed from them |
| `copd` | boolean | yes | COPD |
| `personal-cancer-history` | boolean | yes | Personal history of cancer |
| `family-history-lung-cancer` | boolean | yes | Family history of lung cancer |
| `smoking-status` | choice | yes | `current` or `former` |
| `cigarettes-per-day` | decimal, > 0 | yes | Average cigarettes per day |
| `smoking-duration-years` | decimal, > 0 | yes | Years of smoking |
| `quit-years` | decimal, >= 0 | yes if `former` | Years since quitting (enabled only for former smokers) |
| `plcom2012-result` | group, read-only | | **Output**, written by the service |

Education levels as in the original model: 1 less than high-school graduate, 2 high-school
graduate, 3 some training after high school, 4 some college, 5 college graduate, 6 postgraduate or
professional degree. Mapping a national education system to these six levels is up to the caller and
affects the result.

The model is only defined for **ever-smokers**. Never smokers get a `422`.

Excerpt of the Questionnaire (one optional item, one conditional item):

```json
{
  "linkId": "race",
  "text": "Race / ethnicity (optional)",
  "type": "choice",
  "required": false,
  "answerOption": [
    {
      "valueCoding": {
        "system": "https://example.org/fhir/CodeSystem/plcom2012-race",
        "code": "white",
        "display": "White"
      }
    },
    {
      "valueCoding": {
        "system": "https://example.org/fhir/CodeSystem/plcom2012-race",
        "code": "black",
        "display": "Black or African American"
      }
    },
    ...
  ]
}

{
  "linkId": "quit-years",
  "text": "Years since quitting",
  "type": "decimal",
  "required": true,
  "enableWhen": [
    {
      "question": "smoking-status",
      "operator": "=",
      "answerCoding": {
        "system": "https://example.org/fhir/CodeSystem/plcom2012-smoking-status",
        "code": "former"
      }
    }
  ]
}
```

### Using your own questionnaire

You have two options:

1. **Use ours.** Load `examples/questionnaire.json` into your form tool or FHIR server and render it.
   The linkIds then match without any configuration.
2. **Keep yours.** Tell the service which of your linkIds means what, with a JSON file (only the
   fields that differ) and the environment variable `PLCOM_LINKID_MAP`:

   ```json
   {
     "age": "q1-age",
     "copd": "q7-copd",
     "smoking_status": "q9-smoking-status"
   }
   ```

   Run with `PLCOM_LINKID_MAP=/path/to/map.json`. The keys are the fields from the table above (with
   `-` written as `_`: `height_cm`, `smoking_status`, ...). Unknown keys are rejected at startup.

   Because a `QuestionnaireResponse` should only contain items that exist in its `Questionnaire`,
   add the `plcom2012-result` group from `examples/questionnaire.json` to your own Questionnaire.
   If you cannot change it, use `?output=observation`.

## The interface

| Method | Path | Purpose |
|---|---|---|
| `POST` | `/fhir/QuestionnaireResponse/$plcom2012` | Calculate the risk |
| `GET` | `/fhir/Questionnaire/plcom2012` | Reference Questionnaire |
| `GET` | `/health` | Liveness check |
| `GET` | `/docs` | Interactive OpenAPI UI |

### `POST /fhir/QuestionnaireResponse/$plcom2012`

**Request**

- Body: a FHIR `QuestionnaireResponse` as JSON. Content type `application/fhir+json` or `application/json`.
- Query parameter `output` (optional): `questionnaireresponse` (default) or `observation`.
- Header `X-API-Key`: only if the server was started with `PLCOM_API_KEY`.
- Body size limit: 256 KB by default.

Minimal request body (this is [`examples/questionnaire-response.json`](examples/questionnaire-response.json)):

```json
{
  "resourceType": "QuestionnaireResponse",
  "id": "example-1",
  "questionnaire": "https://example.org/fhir/Questionnaire/plcom2012",
  "status": "completed",
  "subject": { "reference": "Patient/example" },
  "authored": "2026-10-01T09:00:00Z",
  "item": [
    { "linkId": "age", "answer": [{ "valueInteger": 66 }] },
    { "linkId": "education", "answer": [{ "valueCoding": { "code": "4" } }] },
    { "linkId": "bmi", "answer": [{ "valueDecimal": 26.5 }] },
    { "linkId": "copd", "answer": [{ "valueBoolean": false }] },
    { "linkId": "personal-cancer-history", "answer": [{ "valueBoolean": false }] },
    { "linkId": "family-history-lung-cancer", "answer": [{ "valueBoolean": true }] },
    { "linkId": "smoking-status", "answer": [{ "valueCoding": { "code": "former" } }] },
    { "linkId": "cigarettes-per-day", "answer": [{ "valueDecimal": 20 }] },
    { "linkId": "smoking-duration-years", "answer": [{ "valueDecimal": 40 }] },
    { "linkId": "quit-years", "answer": [{ "valueDecimal": 5 }] }
  ]
}
```

Answers may be given as follows:

| Kind | Accepted |
|---|---|
| numbers | `valueDecimal`, `valueInteger` or `valueQuantity` |
| booleans | `valueBoolean`, or a coding with code `yes`/`no`, or LOINC `LA33-6` / `LA32-8` |
| `education` | `valueInteger` 1-6, or `valueCoding.code` `"1"` to `"6"` |
| `smoking-status`, `race` | `valueCoding.code` or `valueString` |

Items may be nested in groups. Each item must have at most one answer.

**Response 1 (default): the `QuestionnaireResponse` plus a result group**

Everything you sent is returned unchanged. One item is appended (a `plcom2012-result` group already
present in the request is replaced, so sending a result back again is safe). Full file:
[`examples/questionnaire-response-result.json`](examples/questionnaire-response-result.json).

```json
{
  "linkId": "plcom2012-result",
  "text": "PLCOm2012 result",
  "item": [
    {
      "linkId": "plcom2012-risk-percent",
      "text": "6-year lung cancer risk",
      "answer": [
        {
          "valueQuantity": {
            "value": 3.7994,
            "unit": "%",
            "system": "http://unitsofmeasure.org",
            "code": "%"
          }
        }
      ]
    },
    {
      "linkId": "plcom2012-race-handling",
      "text": "Handling of race",
      "answer": [
        {
          "valueString": "Race not provided: no race term applied (identical to the reference category White / American Indian / Alaska Native)."
        }
      ]
    },
    {
      "linkId": "plcom2012-model",
      "text": "Model",
      "answer": [
        {
          "valueString": "PLCOm2012 (Tammemägi et al., N Engl J Med 2013;368:728-736); plcom2012-service 0.1.0"
        }
      ]
    }
  ]
}
```

The risk is `valueQuantity` in `%` (UCUM). A `plcom2012-warning` item with one answer per warning is
added if there is something to warn about, e.g. an age outside 55-74, the age range of the
development cohort.

**Response 2: `?output=observation`**

```json
{
  "resourceType": "Observation",
  "status": "final",
  "category": [
    {
      "coding": [
        {
          "system": "http://terminology.hl7.org/CodeSystem/observation-category",
          "code": "survey",
          "display": "Survey"
        }
      ]
    }
  ],
  "code": {
    "coding": [
      {
        "system": "https://example.org/fhir/CodeSystem/plcom2012",
        "code": "plcom2012-6y-lung-cancer-risk",
        "display": "PLCOm2012 6-year lung cancer risk"
      }
    ],
    "text": "PLCOm2012 6-year lung cancer risk"
  },
  "effectiveDateTime": "2026-10-02T14:25:57Z",
  "valueQuantity": {
    "value": 3.7994,
    "unit": "%",
    "system": "http://unitsofmeasure.org",
    "code": "%"
  },
  "method": {
    "text": "PLCOm2012 (Tammemägi et al., N Engl J Med 2013;368:728-736)"
  },
  "note": [
    {
      "text": "Race not provided: no race term applied (identical to the reference category White / American Indian / Alaska Native)."
    }
  ],
  "subject": {
    "reference": "Patient/example"
  },
  "derivedFrom": [
    {
      "reference": "QuestionnaireResponse/example-1"
    }
  ]
}
```

`subject` and `encounter` are copied from the request, `derivedFrom` points to the
`QuestionnaireResponse` if it has an `id`. There is no registered LOINC code for this score that
this project knows of, so the code is local: `{PLCOM_CANONICAL_BASE}/CodeSystem/plcom2012`. Set
`PLCOM_CANONICAL_BASE` to your own namespace, the default is `https://example.org/fhir`.

**Errors** are returned as `OperationOutcome`, with the failing item in `expression`:

| Status | Cause |
|---|---|
| `400` | Body is not valid JSON, not a `QuestionnaireResponse`, or `output` is unknown |
| `401` | `X-API-Key` missing or wrong (only if an API key is configured) |
| `413` | Body too large |
| `422` | Required item missing, wrong answer type, never smoker, or implausible value |

```json
{
  "resourceType": "OperationOutcome",
  "issue": [
    {
      "severity": "error",
      "code": "required",
      "details": {
        "text": "item 'education': required answer is missing"
      },
      "expression": [
        "QuestionnaireResponse.repeat(item).where(linkId='education')"
      ]
    },
    {
      "severity": "error",
      "code": "required",
      "details": {
        "text": "item 'copd': required answer is missing"
      },
      "expression": [
        "QuestionnaireResponse.repeat(item).where(linkId='copd')"
      ]
    }
  ]
}
```

Implausible values are rejected, e.g. age outside 18-110, BMI outside 10-80, more than 200 cigarettes
per day, or smoking years plus quit years above age. All problems are reported in one response.

## Race is optional

Accepted codes: `white`, `black`, `hispanic`, `asian`, `american-indian-alaska-native`,
`native-hawaiian-pacific-islander` (plus `american-indian`, `alaska-native`, `native-hawaiian`,
`pacific-islander`) and the CDC codes `2106-3`, `2054-5`, `2135-2`, `2028-9`, `1002-5`, `2076-8`.
`other`, `unknown`, `unspecified` and `2131-1` count as "not provided".

If race is not provided, **no race term is applied**. That is mathematically the same as the
reference category of the original model (White, American Indian, Alaska Native). It is *not* the
separately fitted "noRace" model, which this service does not include. The response states which case
applied (`plcom2012-race-handling`). An unrecognised race value is an error, it is never silently
ignored.

## Configuration

Environment variables:

| Variable | Default | Meaning |
|---|---|---|
| `PLCOM_API_KEY` | unset | If set, `POST` requires header `X-API-Key` |
| `PLCOM_CANONICAL_BASE` | `https://example.org/fhir` | Base of canonical URLs. **Set your own.** |
| `PLCOM_LINKID_MAP` | unset | JSON file to map your own linkIds, see above |
| `PLCOM_MAX_BODY_BYTES` | `262144` | Request size limit |

The service does not log request bodies. For a public instance put TLS and rate limiting in front of
it and set `PLCOM_API_KEY` or use your SSO. See [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md) for
container deployment and an acceptance test (`scripts/smoke_test.sh`).

## Development

```bash
pip install -e ".[dev]"
pytest -q
ruff check . && ruff format --check .
```

CI runs this on Python 3.11, 3.12 and 3.13. The examples in `examples/` are checked against the code
by the tests, so they cannot go stale.

## Source of the numbers and how they are verified

All coefficients, centering values and the model constant come from **Table 2 and its footnotes of
the original publication**: Tammemägi MC, Katki HA, Hocking WG, et al. *Selection criteria for
lung-cancer screening.* N Engl J Med 2013;368:728-736 (PLCOm2012).

- `tests/test_paper_table2.py` pins every constant to the printed beta coefficient and checks that
  `exp(beta)` reproduces the printed odds ratio (3 decimals).
- As an independent cross-check of the *implementation* (not as a source), `tests/data/reference_vectors.json`
  holds 12 profiles (all race categories, current and former smokers, edge ages) with probabilities
  computed by a separate implementation, the R package
  [resplab/PLCOm2012](https://github.com/resplab/PLCOm2012) (see `tests/data/generate_reference_vectors.R`).
  The tests require agreement to a relative 1e-10. No code from that package is used here.

If you use this service in your work, please cite the original model publication above.

## License

[MIT](LICENSE). Copyright (c) 2026 Thomas Schabetsberger.
