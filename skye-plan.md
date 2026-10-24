# Skye – Drone Flight Education Agent: Implementation Plan

## Top-Level Overview

Build an MVP FastAPI backend for **Skye**, a drone-flight education agent for new US drone users.
One FastAPI app (`app/main.py`) exposes **two focused endpoints** serving two distinct use cases:

| Endpoint | Use case | Primary tool path |
|---|---|---|
| `GET /check?lat=&lon=` | User drops a pin on a map → automatic flight-restriction check | AirHub sim + facility map + NSUFR + TFR providers |
| `GET /rules?query=` | User types a plain-English rules question | ChromaDB `search_rules` only, no location tools |

Both endpoints share a single OpenAI `gpt-4o` agent loop (function-calling, max 6 rounds) in `composer.py`. The loop receives a pre-built context that steers it toward the correct tool set for each use case. No router module; the agent decides which tools to call within its lane and forms its own plain-language explanation from the results. Everything external falls back to local fixtures or the offline simulator when keys or networks are unavailable.

**Key constraints**
- Never say "approved", "legal to fly", "safe", or "clear".
- A hard-coded disclaimer footer is appended in Python after the model's answer.
- `mock_data: true` whenever any simulated / fixture / dummy-corpus result was used.
- `USE_SIM=true` by default; real keys are optional.
- Existing `airhub_sim.py` and `test_airhub_sim.py` must be copied unchanged.

---

## Sub-Task 1 — Repo Skeleton & Configuration

**Intent:** Create every directory, the `.env.example`, `Makefile`, and `config.py` so all later
sub-tasks have a stable import path and environment to work against.

**Expected Outcomes**
- Directory tree matches the spec exactly.
- `config.py` exposes typed settings (pydantic `BaseSettings`): `OPENAI_API_KEY`,
  `OPENAI_MODEL=gpt-4o`, `USE_SIM=true`, `AIRHUB_API_KEY`, `AIRHUB_CLIENT_ID`,
  `AIRHUB_CLIENT_SECRET`, and the real FAA property constants (`PROP_CEILING="CEILING"`, etc.).
- `.env.example` documents every env var.
- `Makefile` has `run`, `test`, `seed` targets.
- `README.md` skeleton lists env vars, simulated vs real, known gaps, and the no-persistence notice.

**Todo List**
1. Create directory tree: `app/`, `app/providers/`, `app/tools/`, `app/rules/`, `scripts/`,
   `fixtures/`, `data/uasfm/`, `tests/`.
2. Write `app/config.py` with `Settings` (pydantic BaseSettings), FAA property name constants,
   and a module-level `settings = Settings()`.
3. Write `.env.example`.
4. Write `Makefile` with `run` (`uvicorn app.main:app --reload`), `test` (`pytest`), `seed`
   (`python -m app.rules.chroma_dummy`).
5. Write `README.md` skeleton.

**Relevant Context**
- FAA property names from spec: `CEILING`, `UNIT`, `APT1_FAAID`, `APT1_ICAO`, `APT1_NAME`,
  `APT1_LAANC`, `AIRSPACE_1`, `ARPT_COUNT`, `APT1_Enabled`, `MAP_EFF`, `LAST_EDIT`,
  `LATITUDE`, `LONGITUDE`, `GLOBALID`, `OBJECTID`, `REGION`.

**Status:** [ ] pending

---

## Sub-Task 2 — Copy Existing Files + Provider Base

**Intent:** Place the two provided files where the import graph expects them, and define the shared
Pydantic result models that all providers return.

**Expected Outcomes**
- `app/providers/airhub_sim.py` is a byte-for-byte copy of `airhub_sim.py`; imports still work.
- `tests/test_airhub_sim.py` is copied from `test_airhub_sim.py`; `pytest tests/test_airhub_sim.py`
  passes with a `conftest.py` that adds `app/providers` to `sys.path` so the copy can import itself.
- `app/providers/base.py` defines:
  - `ProviderStatus = Literal["ok", "failed", "stale"]`
  - `BaseResult(BaseModel)` with `checked_at: datetime`, `status: ProviderStatus`,
    `simulated: bool = False`, `fixture: bool = False`.
  - Concrete result models: `AirspaceResult`, `FacilityCeilingResult`, `AdvisoryResult`,
    `NSUFRResult`, `TFRResult`, `PlaceResult`.

**Todo List**
1. Copy `airhub_sim.py` → `app/providers/airhub_sim.py` (unchanged).
2. Copy `test_airhub_sim.py` → `tests/test_airhub_sim.py`.
3. Add `tests/conftest.py` that inserts `app/providers` into `sys.path` so
   `from airhub_sim import ...` resolves in the copied test.
4. Write `app/providers/base.py` with `ProviderStatus`, `BaseResult`, and all concrete models.

**Relevant Context**
- `test_airhub_sim.py` imports directly: `from airhub_sim import AirHubClient, AirHubError, ...`
  The conftest path-hack is the minimal fix that keeps the file unchanged.
- Every tool response must carry `checked_at` and `status`; the `BaseResult` fields enforce this.

**Status:** [ ] pending

---

## Sub-Task 3 — Provider Implementations

**Intent:** Implement all five provider modules. Each is independently loadable; failing providers
return `status="failed"` instead of raising exceptions that would crash the agent loop.

**Expected Outcomes**
- `airspace.py` — wraps sim client; `get_airspace(lat, lon)` and `get_advisories(lat, lon, radius_km)`
  catch `AirHubError` and return `status="failed"`.
- `faa_facility_map.py` — loads a GeoJSON at startup, builds a shapely `STRtree`; `get_facility_ceiling(lat, lon)`.
  Falls back to `fixtures/uasfm_sample.geojson` with `status="stale"` if `data/uasfm/*.geojson` is absent.
- `nsufr.py` — reads `fixtures/nsufr_hit.json`; optional live FAA ArcGIS query behind `USE_LIVE_NSUFR` flag.
- `tfr.py` — reads `fixtures/tfr_active.json`; in-process cache (60-min TTL); live FAA XML fetch optional.
- `mock_osm.py` — reads `data/mock_osm.geojson`; `find_places(area, tags, radius_km)`.

**Todo List**
1. Write `app/providers/airspace.py` using `make_sim_client()` from the copied simulator.
2. Write `fixtures/uasfm_sample.geojson` with the two SJC cells from the spec.
3. Write `app/providers/faa_facility_map.py`.
4. Write `fixtures/nsufr_hit.json`, `fixtures/tfr_active.json`, `fixtures/provider_down.json`.
5. Write `app/providers/nsufr.py`.
6. Write `app/providers/tfr.py` (in-process dict cache, `checked_at` timestamp, 60-min TTL).
7. Write `data/mock_osm.geojson` (10 hand-entered US places with OSM-style tags).
8. Write `app/providers/mock_osm.py`.

**Relevant Context**
- `faa_facility_map.py`: STRtree is built over cell bounding boxes (each cell is a small rectangle).
  Point-in-polygon via `shapely.geometry.Point.within(cell_polygon)`. Result fields: `in_grid`,
  `ceiling_ft`, `airport_name`, `airport_icao`, `airspace_class`, `laanc_enabled`, `enabled_types`,
  `map_effective`, `fetched_at`, `source_url`.
- Cell 1 bounds: lon −121.88335→−121.87502, lat 37.29167→37.30001, ceiling 300.
- Cell 2 bounds: lon −121.94168→−121.93335, lat 37.39167→37.40001, ceiling 400.
- Both cells: APT1_FAAID=SJC, APT1_ICAO=KSJC, APT1_LAANC=1, AIRSPACE_1=C.

**Status:** [ ] pending

---

## Sub-Task 4 — Chroma Rules Store

**Intent:** Build a local, offline, tag-filterable rules corpus that the agent can query. Wrap it
behind a `RulesStore` interface so a real corpus can replace it later without touching the tool.

**Expected Outcomes**
- `app/rules/seed_rules.json` contains exactly the 10 paraphrased rule chunks from the spec, each
  with `rule_id`, `text`, `tags`, `applies_to`, `citation`, `source_url`, `retrieved_date`,
  `dummy: true`.
- `app/rules/chroma_dummy.py` defines `RulesStore` (protocol/ABC) and `DummyRulesStore` that:
  - Builds (or loads) a persistent Chroma collection `faa_rules_dummy` at `./.chroma`.
  - Exposes `query(query_text, tags=[], k=4) -> list[dict]`.
  - Applies a metadata `$contains` / `$in` filter on `tags` when tags are provided.
  - Never embeds coordinates in queries.
- `app/tools/chroma_tool.py` wraps `DummyRulesStore` into an OpenAI function-callable tool
  (`search_rules(query, tags, k)`).

**Todo List**
1. Write `app/rules/seed_rules.json` with the 10 rule chunks.
2. Write `app/rules/chroma_dummy.py` with `RulesStore` protocol and `DummyRulesStore`.
3. Write `app/tools/chroma_tool.py` with `search_rules` function and its JSON schema for the
   OpenAI `tools` list.
4. Verify that `make seed` (`python -m app.rules.chroma_dummy`) exits cleanly and that
   `.chroma/` is created. Add `.chroma/` to `.gitignore`.

**Relevant Context**
- Chroma metadata filtering: `{"tags": {"$contains": tag}}` for single-tag filter.
  For multi-tag: query once per tag and union the results (Chroma's `$contains` is per-field).
- `dummy: true` in metadata triggers `mock_data=true` in the response.
- Rule IDs: `controlled-airspace-auth`, `facility-map-ceiling`, `altitude-400`,
  `authorization-not-override`, `prohibited-restricted`, `nsufr-99-7`, `weather-minimums`,
  `yield-to-aircraft`, `part-108-pending`, `section-2209-pending`.

**Status:** [ ] pending

---

## Sub-Task 5 — Agent Loop (composer.py) & Repetition Control

**Intent:** Implement the agent's reasoning loop and the in-process repetition/session store.
`composer.py` exposes two entry points — `check_location` and `ask_rules` — that pre-configure
the agent's context and allowed tools before entering the shared gpt-4o loop.

**Expected Outcomes**
- `app/repetition.py`: plain-dict store keyed by `session_id`; tracks `concepts_explained` (set),
  last 3 answer summaries, last fact-bundle hash, flight-check count; 5–15 min fact TTL;
  exposes `get_context(session_id)` and `record_answer(session_id, facts, answer_summary)`.
- `app/composer.py` exposes **two public functions** sharing one internal loop:
  - `check_location(lat, lon, session_id, flight_time) -> CheckResponse`
    - Allowed tools: `get_airspace`, `get_facility_ceiling`, `get_advisories`, `get_nsufr`, `get_tfrs`, `find_places`, `search_rules`.
    - System prompt context: "The user has provided coordinates. Automatically call the location tools first, then search_rules with the tags you discover. Do NOT wait for more user input."
    - Response structure: airspace class, ceiling, active restrictions, pre-flight checklist, suggestion for nearby alternatives.
  - `ask_rules(query, session_id) -> RulesResponse`
    - Allowed tools: `search_rules` only.
    - System prompt context: "The user is asking a rules question. Use search_rules only. Do not call location tools."
    - Response structure: rule explanation with citations, applies_to note, disclaimer.
  - Both functions append the hard-coded disclaimer footer and return a typed response object.
- The forbidden words (`approved`, `legal to fly`, `safe`, `clear`) are listed in the system prompt,
  not enforced by regex in Python.

**Todo List**
1. Write `app/repetition.py`.
2. Write `app/composer.py`:
   a. Shared system prompt (Skye persona + agent judgement rules).
   b. Internal `_run_loop(messages, tools_allowed, session_id) -> LoopResult` — the gpt-4o tool-calling loop (max 6 rounds), collecting `tools_called[]`, `sources_failed[]`, `data_freshness{}`, `mock_data`.
   c. `check_location(lat, lon, session_id, flight_time) -> CheckResponse` — builds location-check context, calls `_run_loop` with location + rules tools.
   d. `ask_rules(query, session_id) -> RulesResponse` — builds rules-question context, calls `_run_loop` with `search_rules` only.
   e. Both functions append hard-coded footer to the model's final answer.

**Relevant Context**
- Tool dispatch registry (full set, restricted per entry point):
  - Location tools: `get_airspace`, `get_facility_ceiling`, `get_advisories`, `get_nsufr`, `get_tfrs`, `find_places`.
  - Rules tool: `search_rules`.
  - `/check` uses all; `/rules` uses only `search_rules`.
- `mock_data` flag: set `True` if any tool result has `simulated=True`, `fixture=True`,
  or any Chroma chunk has `dummy=True`.
- Footer content: per-tool `checked_at` timestamps, "State and local rules are not fully covered.",
  "Simulated or demo data was used." (when `mock_data`), "Verify in an FAA-approved app (e.g.
  B4UFLY) before flying."

**Status:** [ ] pending

---

## Sub-Task 6 — FastAPI App (main.py)

**Intent:** Wire the two composer entry points into two dedicated FastAPI endpoints plus a health check.

**Expected Outcomes**
- `GET /health` returns `{"status":"ok","persist_user_data":false,"mock_data":<bool>}`.
- `GET /check?lat=<float>&lon=<float>` (required) `&session_id=<str>` (optional) `&flight_time=<ISO>` (optional)
  - Calls `composer.check_location(lat, lon, session_id, flight_time)`.
  - Returns `CheckResponse`: `answer_markdown`, `citations[]`, `tools_called[{name,args,status,checked_at}]`, `sources_failed[]`, `data_freshness{provider: iso_ts}`, `nearby_alternatives[]`, `mock_data: bool`.
- `GET /rules?query=<str>` (required) `&session_id=<str>` (optional)
  - Calls `composer.ask_rules(query, session_id)`.
  - Returns `RulesResponse`: `answer_markdown`, `citations[]`, `tools_called[{name,args,status,checked_at}]`, `mock_data: bool`.
- FastAPI `/docs` page documents all three endpoints.

**Todo List**
1. Write `app/schema.py` with `CheckResponse`, `RulesResponse`, and shared sub-models
   (`ToolCall`, `Citation`).
2. Write `app/main.py` with `FastAPI()` app, lifespan startup (load facility map, seed Chroma if
   needed), and the three route handlers (`/health`, `/check`, `/rules`).
3. Wire `/check` → `composer.check_location(...)` and `/rules` → `composer.ask_rules(...)`.

**Relevant Context**
- Startup: call `faa_facility_map.load()` and `chroma_dummy.ensure_seeded()` so first requests
  are not slow.
- `/check` validates that `lat` is in [-90, 90] and `lon` is in [-180, 180]; return HTTP 422 on
  invalid coordinates (FastAPI's built-in validation is sufficient).
- Error handling: provider failures are captured inside the response objects, not raised as HTTP
  errors. Unhandled exceptions → 500 `{"detail": ...}`.

**Status:** [ ] pending

---

## Sub-Task 7 — Fetch Script & Data Files

**Intent:** Provide the one-time FAA UAS Facility Map download script and all fixture files.

**Expected Outcomes**
- `scripts/fetch_facility_map.py`: downloads the FAA UAS Facility Map GeoJSON to
  `data/uasfm/facility_map.geojson`, writes `data/uasfm/meta.json` with `fetched_at`, and
  prints the property names of the first record.
- All fixture files are valid JSON: `uasfm_sample.geojson`, `nsufr_hit.json`,
  `tfr_active.json`, `provider_down.json`.

**Todo List**
1. Write `scripts/fetch_facility_map.py`.
2. Verify `fixtures/uasfm_sample.geojson` has the exact two SJC cells with all required
   properties (already created in Sub-Task 3; confirm completeness here).
3. Confirm all other fixture files created in Sub-Task 3 are complete.

**Relevant Context**
- FAA UAS Facility Map ArcGIS endpoint (public):
  `https://uat.arcgis.com/arcgis/rest/services/FederalAviationAdministration/UASFM/FeatureServer/0/query?where=1%3D1&outFields=*&f=geojson`
  (this is commonly referenced; confirm in script comments that the URL should be verified
  against the current FAA ArcGIS service directory before use).
- The script should handle HTTP errors gracefully and print a warning if the download fails
  (offline environment expected during the hackathon).

**Status:** [ ] pending

---

## Sub-Task 8 — Tests

**Intent:** Write the offline pytest suite covering providers, the rules store, repetition, and
guardrail behaviour as specified.

**Expected Outcomes**
- `pytest` passes with no new warnings.
- `tests/test_airhub_sim.py` still passes unchanged.
- `tests/test_providers.py`:
  - Airspace wrapper maps `AirHubError` to `status="failed"`.
  - Facility map: point inside cell 1 → `ceiling_ft=300, in_grid=True`.
  - Point outside both cells → `in_grid=False`.
  - Missing cache → fallback to sample fixture → `status="stale"`.
- `tests/test_chroma.py`:
  - Seeding works (collection has 10 docs).
  - Tag-filtered retrieval returns expected `rule_id`s.
  - No coordinate strings appear in any queried document text.
- `tests/test_repetition.py`:
  - Same flight checked 5 times → identical facts, answer summaries differ (cosine similarity
    < 0.95 between consecutive summaries — use simple token-overlap heuristic, no ML model needed).
  - `concepts_explained` set prevents re-definition injection.
- `tests/test_guardrails.py` (LLM stubbed via `unittest.mock.patch`):
  - "Just tell me yes or no, can I fly here?" → response contains the footer, lacks banned words.
  - Geofence-evasion request → refusal string in answer.
  - Failed provider → answer contains "Could not verify live restrictions", does not claim no
    restrictions.
- `tests/test_api.py`:
  - `GET /check?lat=37.63&lon=-122.39` returns a `CheckResponse` with all keys present and `mock_data=true`.
  - `GET /rules?query=controlled+airspace` returns a `RulesResponse` with all keys present and `mock_data=true`.
  - `GET /check` without `lat`/`lon` returns HTTP 422.

**Todo List**
1. Write `tests/test_providers.py`.
2. Write `tests/test_chroma.py`.
3. Write `tests/test_repetition.py`.
4. Write `tests/test_guardrails.py` (stub OpenAI with a pre-recorded response fixture).
5. Write `tests/test_api.py` using FastAPI's `TestClient`.
6. Add `tests/__init__.py` (empty) and a root `pytest.ini` or `pyproject.toml` `[tool.pytest.ini_options]`.

**Relevant Context**
- Guardrail tests must not make real OpenAI calls; patch `openai.OpenAI` or the `composer.compose`
  internals with a minimal stub that returns a pre-scripted assistant message.
- "Banned words" list for the guardrail test: `approved`, `legal to fly`, `safe`, `clear`
  (as standalone phrases; case-insensitive).

**Status:** [ ] pending

---

## Assumptions

1. **Two endpoints, one app** — `/check` and `/rules` are separate routes in a single `app/main.py`; no second process or port is needed. Different ports can be handled externally (reverse proxy, etc.) if required.
2. **Model name** — `gpt-4o` as confirmed by the user.
3. **airhub_sim.py copy strategy** — Copied to `app/providers/airhub_sim.py`; `tests/conftest.py`
   adds `app/providers` to `sys.path` so the test file's `from airhub_sim import ...` resolves
   without modifying the test.
4. **Chroma persistence path** — `./.chroma` relative to the project root (where `make seed` runs).
5. **Facility map fallback** — `fixtures/uasfm_sample.geojson` is the hardcoded fallback path;
   `faa_facility_map.py` checks `data/uasfm/` for any `.geojson` file first.
6. **TFR / NSUFR live sources** — Both are fixture-backed by default; live fetches are behind
   feature flags (`USE_LIVE_TFR`, `USE_LIVE_NSUFR`) and are not required for the hackathon MVP.
7. **No session persistence** — `repetition.py` uses a plain module-level dict; data is lost on
   restart. Documented in README and `/health`.
8. **Repetition similarity check** — Uses a simple Jaccard / token-overlap heuristic (no sentence
   transformer) to keep the test suite fully offline.
9. **FAA ArcGIS URL** — The fetch script uses a publicly documented URL; it is commented as
   "verify before use" since it may change without notice.
10. **`mock_data` flag** — Set `True` whenever `simulated=True`, `fixture=True`, or
    `dummy=True` appears in any tool result; the agent loop accumulates this flag across all calls.
11. **Forbidden-word enforcement** — Listed in the system prompt only; no Python-level regex guard
    (consistent with the "single LLM agent" design principle).
12. **`scripts/fetch_facility_map.py`** — Not a FastAPI route; it is a standalone script run
    manually or as part of a CI step before deployment.
13. **No `__init__.py` files needed** in `app/` subdirectories for Python 3.11 namespace packages,
    but they will be added for clarity and tool compatibility.
