# plcom2012-service

A small FHIR REST service that calculates the **PLCOm2012 6-year lung cancer risk**
(Tammemägi et al., *N Engl J Med* 2013;368:728-736) from a FHIR `QuestionnaireResponse`.

You POST the filled-in questionnaire and get the same `QuestionnaireResponse` back, extended by the
risk in percent. If you prefer a separate resource, `?output=observation` returns an `Observation`.

> **Not a certified medical device.** This is research / demonstration software. Using a risk
> calculation to support screening decisions in clinical practice can make the software a medical
> device under the EU MDR (and comparable regulations elsewhere). Do not send real patient data to a
> public test instance.

## API

| Method | Path | Purpose |
|---|---|---|
| `POST` | `/fhir/QuestionnaireResponse/$plcom2012` | Calculate the risk |
| `GET` | `/fhir/Questionnaire/plcom2012` | Reference Questionnaire (input + result items) |
| `GET` | `/health` | Liveness |
| `GET` | `/docs` | OpenAPI UI |

```bash
curl -X POST 'http://localhost:8000/fhir/QuestionnaireResponse/$plcom2012' \
  -H 'Content-Type: application/fhir+json' \
  -d @examples/questionnaire-response.json
```

**Why a `QuestionnaireResponse` and not a `Questionnaire`?** In FHIR a `Questionnaire` is the empty
form, the answers live in a `QuestionnaireResponse`. That is what the service takes and returns.

### Output 1 (default): `QuestionnaireResponse` + result group

The request is returned unchanged, with one group item appended (an existing `plcom2012-result`
group is replaced, so re-submitting is safe):

```json
{
  "linkId": "plcom2012-result",
  "item": [
    { "linkId": "plcom2012-risk-percent",
      "answer": [{ "valueQuantity": { "value": 3.7994, "unit": "%",
                                      "system": "http://unitsofmeasure.org", "code": "%" } }] },
    { "linkId": "plcom2012-race-handling", "answer": [{ "valueString": "Race not provided: ..." }] },
    { "linkId": "plcom2012-model", "answer": [{ "valueString": "PLCOm2012 (...); plcom2012-service 0.1.0" }] },
    { "linkId": "plcom2012-warning", "answer": [{ "valueString": "..." }] }
  ]
}
```

`plcom2012-warning` is only present if there is something to warn about.

> **Validity caveat.** A `QuestionnaireResponse` should only contain items that exist in its
> `Questionnaire`. The reference questionnaire served at `/fhir/Questionnaire/plcom2012` contains the
> result items (read-only). If you use your own questionnaire, add the result items to it, otherwise
> strict validators will complain about the appended group. If you cannot change the questionnaire,
> use the Observation output.

### Output 2: `?output=observation`

An `Observation` (`status: final`, category `survey`) with `valueQuantity` in `%`, `subject` and
`encounter` copied from the request, and `derivedFrom` pointing to the `QuestionnaireResponse` if it
has an `id`. The code is `plcom2012-6y-lung-cancer-risk` in
`{PLCOM_CANONICAL_BASE}/CodeSystem/plcom2012`. There is no registered LOINC code behind it that this
project knows of, so a local code system is used. Replace it if you have a better one.

### Input items

Items are matched by `linkId` and may be nested in groups.

| linkId | Answer type | Required |
|---|---|---|
| `age` | number (years) | yes |
| `race` | `valueCoding.code` / `valueString`, see below | **no** |
| `education` | integer 1-6 (`valueInteger` or `valueCoding.code`) | yes |
| `bmi` | number | yes, or `height-cm` + `weight-kg` |
| `height-cm`, `weight-kg` | number | alternative to `bmi` |
| `copd` | boolean | yes |
| `personal-cancer-history` | boolean | yes |
| `family-history-lung-cancer` | boolean | yes |
| `smoking-status` | code `current` or `former` | yes |
| `cigarettes-per-day` | number > 0 | yes |
| `smoking-duration-years` | number > 0 | yes |
| `quit-years` | number >= 0 | yes for `former`, ignored for `current` |

Numbers may be `valueDecimal`, `valueInteger` or `valueQuantity`. Booleans may also be a coding with
code `yes`/`no` or the LOINC answers `LA33-6`/`LA32-8`.

Education levels (as in the model): 1 less than high school, 2 high-school graduate, 3 some training
after high school, 4 some college, 5 college graduate, 6 postgraduate. **Mapping a national
education system (e.g. Austrian) to these six levels is up to the caller** and affects the result.

### Race is optional

Accepted codes: `white`, `black`, `hispanic`, `asian`, `american-indian-alaska-native`,
`native-hawaiian-pacific-islander` (plus `american-indian`, `alaska-native`, `native-hawaiian`,
`pacific-islander`) and the CDC codes `2106-3`, `2054-5`, `2135-2`, `2028-9`, `1002-5`, `2076-8`.
`other`, `unknown`, `unspecified` and `2131-1` count as "not provided".

If race is not provided, **no race term is applied**. That is mathematically the same as the
reference category of the original model (White, American Indian, Alaska Native). It is *not* the
separately fitted "noRace" model, which this service does not include. The response states which
case applied (`plcom2012-race-handling`). An unrecognised race value is an error, it is never silently
ignored.

### Errors

Errors are `OperationOutcome` resources: `400` (not JSON / not a `QuestionnaireResponse` / bad
`output`), `401` (API key), `413` (body too large), `422` (missing or implausible values, one issue per
problem with the `linkId` in `expression`). Never smokers get a `422`: the model is only defined for
current and former smokers.

Implausible values are rejected (e.g. age outside 18-110, BMI outside 10-80, more than 200
cigarettes per day, smoking years plus quit years above age). An age outside 55-74, the age range of
the PLCO development cohort, is calculated but returns a warning.

## Run

```bash
pip install -e ".[dev]"
uvicorn plcom2012_service.main:app --reload     # http://localhost:8000/docs
pytest
```

```bash
docker compose up --build
```

### Configuration (environment variables)

| Variable | Default | Meaning |
|---|---|---|
| `PLCOM_API_KEY` | unset | If set, `POST` requires header `X-API-Key` |
| `PLCOM_CANONICAL_BASE` | `https://example.org/fhir` | Base of canonical URLs. **Set your own.** |
| `PLCOM_LINKID_MAP` | unset | Path to a JSON file `{"age": "my-age-linkid", ...}` to read an existing questionnaire |
| `PLCOM_MAX_BODY_BYTES` | `262144` | Request size limit |

See [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md) for container deployment and the smoke test.

The service does not log request bodies. For a public instance put rate limiting and TLS in front of
it (reverse proxy) and set `PLCOM_API_KEY` or use your SSO.

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

## License

[PolyForm Noncommercial License 1.0.0](LICENSE): free to use, copy, modify and redistribute for any
**noncommercial** purpose, including personal use, research, and use by charitable, educational,
public research, public health and government organizations. Commercial use needs a separate
license from the copyright holder.

Note that this is a *source-available* license, not an OSI-approved open source license.
