# live-meeting-agent Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a Python CLI that listens to system audio, transcribes locally with faster-whisper, and incrementally updates a multi-page `.drawio` file via Claude every 5 minutes or on hotkey.

**Architecture:** Six components - audio capture, transcription thread, rolling transcript, trigger, LLM cycle, XML generator - operate on a JSON state model. Code owns IDs and positions; the LLM owns labels and semantics. Output is a single `.drawio` file with one live page per detected diagram type, per-cycle snapshot pages, and an archived page for soft-deleted entities.

**Tech Stack:** Python 3.11+, anthropic, faster-whisper, sounddevice, numpy, networkx, keyboard, pydantic, pytest, lxml.

**Spec:** `docs/superpowers/specs/2026-04-26-live-meeting-agent-design.md`

---

## File Structure

```
live-meeting-agent/
├── agent.py                 # CLI entry, orchestration loop
├── audio.py                 # WASAPI loopback capture + ring buffer
├── transcription.py         # faster-whisper background thread
├── llm.py                   # Claude API call + prompt loading + caching
├── model.py                 # Pydantic state schema, diff, ID assignment
├── drawio.py                # JSON to mxGraph XML + auto-layout
├── triggers.py              # 5-min timer + global hotkey
├── prompts/
│   ├── system.md            # System prompt for the LLM cycle
│   └── schema.json          # JSON schema for the LLM output
├── meetings/                # output dir, gitignored
├── tests/
│   ├── fixtures/
│   │   ├── transcript_architecture.txt
│   │   ├── transcript_process.txt
│   │   └── golden_state_after_arch.json
│   ├── conftest.py
│   ├── test_model.py
│   ├── test_drawio.py
│   └── test_llm_golden.py
├── requirements.txt
├── pyproject.toml
├── README.md
├── CLAUDE.md                # Index for future Claude sessions
└── .gitignore
```

Dependency direction: `model.py` has no internal deps. `drawio.py` imports `model`. `llm.py` imports `model`. `audio.py` and `transcription.py` are independent. `triggers.py` is independent. `agent.py` imports all.

---

## Phase M1: Batch pipeline

End state: `python agent.py demo --transcript tests/fixtures/transcript_architecture.txt` produces `meetings/demo/meeting.drawio` containing a one-page architecture diagram, validated against a golden snapshot.

### Task 1: Project scaffolding

**Files:**
- Create: `live-meeting-agent/.gitignore`
- Create: `live-meeting-agent/pyproject.toml`
- Create: `live-meeting-agent/requirements.txt`
- Create: `live-meeting-agent/README.md`
- Create: `live-meeting-agent/CLAUDE.md`
- Create empty: `agent.py`, `audio.py`, `transcription.py`, `llm.py`, `model.py`, `drawio.py`, `triggers.py`
- Create: `prompts/`, `tests/`, `tests/fixtures/`, `meetings/` (empty dirs)

- [ ] **Step 1: Initialise git repo**

```bash
cd C:/Repos/dev/playground/live-meeting-agent && git init && git config user.email "vico.strozzi26@gmail.com" && git config user.name "Vico Strozzi"
```

- [ ] **Step 2: Create `.gitignore`**

```gitignore
__pycache__/
*.py[cod]
*$py.class
.venv/
venv/
.env
.pytest_cache/
.mypy_cache/
.ruff_cache/
meetings/
*.egg-info/
dist/
build/
.vscode/
```

- [ ] **Step 3: Create `requirements.txt`**

```
anthropic>=0.40.0
faster-whisper>=1.0.3
sounddevice>=0.4.7
numpy>=1.26
pydantic>=2.7
networkx>=3.3
keyboard>=0.13.5
lxml>=5.2
```

Test deps:

```
pytest>=8.0
pytest-mock>=3.12
```

- [ ] **Step 4: Create `pyproject.toml`**

```toml
[project]
name = "live-meeting-agent"
version = "0.1.0"
requires-python = ">=3.11"

[tool.pytest.ini_options]
testpaths = ["tests"]
```

- [ ] **Step 5: Create `README.md`**

```markdown
# live-meeting-agent

Active scribe that listens to a meeting and incrementally updates a `.drawio` file every 5 minutes (or on hotkey).

## Setup

    python -m venv .venv
    .venv\Scripts\activate
    pip install -r requirements.txt
    set ANTHROPIC_API_KEY=sk-ant-...

## Run (batch mode)

    python agent.py demo --transcript tests/fixtures/transcript_architecture.txt

## Run (live mode)

    python agent.py my-meeting --interval 5m

Open `meetings/<name>/meeting.drawio` in any drawio viewer (VS Code drawio extension, drawio desktop, or app.diagrams.net).

## Hotkey

`Ctrl+Shift+U` forces an immediate diagram update.
```

- [ ] **Step 6: Create `CLAUDE.md` index**

```markdown
# live-meeting-agent

Live diagram generator from meeting audio. Status: under construction.

## Key artefacts
- Spec: `docs/superpowers/specs/2026-04-26-live-meeting-agent-design.md`
- Plan: `docs/superpowers/plans/2026-04-26-live-meeting-agent.md`

## Architecture summary
Audio -> Whisper -> rolling transcript -> Claude -> JSON state -> mxGraph XML -> `meetings/<name>/meeting.drawio`.

State of the world is in `meetings/<name>/state.json`. Code owns IDs and positions; LLM owns labels and semantics.

## Common commands

    pytest                                                           # run unit tests
    python agent.py demo --transcript tests/fixtures/transcript_architecture.txt  # batch run
    python agent.py my-meeting                                       # live run with default 5-min interval
```

- [ ] **Step 7: Create empty Python source files and directories**

```bash
touch agent.py audio.py transcription.py llm.py model.py drawio.py triggers.py
mkdir -p prompts tests/fixtures meetings
touch tests/__init__.py tests/conftest.py
```

- [ ] **Step 8: Create virtual environment and install dependencies**

```bash
python -m venv .venv && .venv/Scripts/pip install -r requirements.txt
```

- [ ] **Step 9: Run `pytest` to verify the test runner works**

```bash
.venv/Scripts/pytest
```

Expected: `no tests ran in 0.0s` (zero tests collected, no errors).

- [ ] **Step 10: Commit**

```bash
git add . && git commit -m "chore: scaffold project structure and dependencies"
```

---

### Task 2: State model schema

**Files:**
- Modify: `model.py`
- Create: `tests/test_model.py`

- [ ] **Step 1: Write failing tests for the state model**

Write to `tests/test_model.py`:

```python
import pytest
from pydantic import ValidationError
from model import Entity, Relation, Page, MeetingState, TranscriptSegment


def test_entity_minimal():
    e = Entity(id="ent_001", label="D365", kind="system")
    assert e.x == 0 and e.y == 0


def test_entity_invalid_kind():
    with pytest.raises(ValidationError):
        Entity(id="ent_001", label="D365", kind="not_a_kind")


def test_relation_uses_from_alias():
    r = Relation.model_validate({"id": "rel_001", "from": "ent_001", "to": "ent_002"})
    assert r.from_ == "ent_001"
    assert r.to == "ent_002"


def test_page_default_lists():
    p = Page(name="architecture", type="architecture", role="live")
    assert p.entities == [] and p.relations == []


def test_meeting_state_round_trip():
    s = MeetingState(
        meeting_id="m1",
        started_at="2026-04-26T14:00:00",
        active_diagram_type="architecture",
    )
    dumped = s.model_dump_json()
    loaded = MeetingState.model_validate_json(dumped)
    assert loaded.meeting_id == "m1"
```

- [ ] **Step 2: Run the test, expect failure**

```bash
.venv/Scripts/pytest tests/test_model.py -v
```

Expected: `ImportError` because `model.py` is empty.

- [ ] **Step 3: Implement the state model**

Write to `model.py`:

```python
from typing import Literal
from pydantic import BaseModel, Field, ConfigDict

EntityKind = Literal["system", "role", "store", "actor", "process", "decision", "event"]
DiagramType = Literal["architecture", "process_flow", "mindmap", "sequence", "entity_model"]
PageRole = Literal["live", "snapshot", "archived"]


class Entity(BaseModel):
    id: str
    label: str
    kind: EntityKind
    x: int = 0
    y: int = 0


class Relation(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    id: str
    from_: str = Field(alias="from")
    to: str
    label: str = ""


class Page(BaseModel):
    name: str
    type: DiagramType
    role: PageRole = "live"
    entities: list[Entity] = []
    relations: list[Relation] = []


class TranscriptSegment(BaseModel):
    t: str
    text: str


class MeetingState(BaseModel):
    meeting_id: str
    started_at: str
    active_diagram_type: DiagramType
    pages: list[Page] = []
    transcript: list[TranscriptSegment] = []
```

- [ ] **Step 4: Run the test, expect pass**

```bash
.venv/Scripts/pytest tests/test_model.py -v
```

Expected: 5 passed.

- [ ] **Step 5: Commit**

```bash
git add model.py tests/test_model.py && git commit -m "feat(model): add Pydantic state schema with entity, relation, page, meeting state"
```

---

### Task 3: ID assignment and diff

**Files:**
- Modify: `model.py`
- Modify: `tests/test_model.py`

- [ ] **Step 1: Write failing tests for ID assignment**

Append to `tests/test_model.py`:

```python
from model import assign_ids, diff_pages


def test_assign_ids_replaces_tmp_ids():
    page = Page(
        name="architecture", type="architecture",
        entities=[
            Entity(id="ent_001", label="D365", kind="system"),
            Entity(id="tmp_001", label="MT Proxy", kind="system"),
            Entity(id="tmp_002", label="Translator", kind="system"),
        ],
        relations=[
            Relation(id="rel_001", from_="ent_001", to="tmp_001"),
            Relation(id="tmp_rel_001", from_="tmp_001", to="tmp_002"),
        ],
    )
    next_id = assign_ids(page, next_entity_seq=2, next_relation_seq=2)
    assert next_id == (4, 3)
    labels_to_ids = {e.label: e.id for e in page.entities}
    assert labels_to_ids["MT Proxy"].startswith("ent_")
    assert labels_to_ids["Translator"].startswith("ent_")
    assert page.relations[1].from_ == labels_to_ids["MT Proxy"]
    assert page.relations[1].to == labels_to_ids["Translator"]


def test_diff_pages_added_changed_removed():
    before = Page(
        name="architecture", type="architecture",
        entities=[
            Entity(id="ent_001", label="D365", kind="system"),
            Entity(id="ent_002", label="Translator", kind="system"),
        ],
    )
    after = Page(
        name="architecture", type="architecture",
        entities=[
            Entity(id="ent_001", label="D365", kind="system"),
            Entity(id="ent_002", label="MT Service", kind="system"),
            Entity(id="ent_003", label="MT Proxy", kind="system"),
        ],
    )
    d = diff_pages(before, after)
    assert d.added == ["MT Proxy"]
    assert d.changed == [("Translator", "MT Service")]
    assert d.removed == []
```

- [ ] **Step 2: Run the tests, expect failure**

```bash
.venv/Scripts/pytest tests/test_model.py -v
```

Expected: `ImportError: cannot import name 'assign_ids' from 'model'`.

- [ ] **Step 3: Implement `assign_ids` and `diff_pages`**

Append to `model.py`:

```python
from dataclasses import dataclass


def assign_ids(page: Page, next_entity_seq: int, next_relation_seq: int) -> tuple[int, int]:
    """Replace tmp_* ids with stable ent_NNN/rel_NNN ids. Returns the next sequence numbers."""
    tmp_to_real: dict[str, str] = {}
    for e in page.entities:
        if e.id.startswith("tmp_"):
            real_id = f"ent_{next_entity_seq:03d}"
            next_entity_seq += 1
            tmp_to_real[e.id] = real_id
            e.id = real_id
    for r in page.relations:
        if r.from_ in tmp_to_real:
            r.from_ = tmp_to_real[r.from_]
        if r.to in tmp_to_real:
            r.to = tmp_to_real[r.to]
        if r.id.startswith("tmp_"):
            r.id = f"rel_{next_relation_seq:03d}"
            next_relation_seq += 1
    return (next_entity_seq, next_relation_seq)


@dataclass
class PageDiff:
    added: list[str]
    changed: list[tuple[str, str]]
    removed: list[str]


def diff_pages(before: Page, after: Page) -> PageDiff:
    before_by_id = {e.id: e for e in before.entities}
    after_by_id = {e.id: e for e in after.entities}
    added = [after_by_id[i].label for i in after_by_id.keys() - before_by_id.keys()]
    removed = [before_by_id[i].label for i in before_by_id.keys() - after_by_id.keys()]
    changed = [
        (before_by_id[i].label, after_by_id[i].label)
        for i in before_by_id.keys() & after_by_id.keys()
        if before_by_id[i].label != after_by_id[i].label
    ]
    return PageDiff(added=added, changed=changed, removed=removed)
```

- [ ] **Step 4: Run the tests, expect pass**

```bash
.venv/Scripts/pytest tests/test_model.py -v
```

Expected: 7 passed.

- [ ] **Step 5: Commit**

```bash
git add model.py tests/test_model.py && git commit -m "feat(model): add tmp-id assignment and page diff"
```

---

### Task 4: Prompt and JSON schema files

**Files:**
- Create: `prompts/system.md`
- Create: `prompts/schema.json`

- [ ] **Step 1: Create the system prompt**

Write to `prompts/system.md`:

```markdown
You are a meeting scribe agent. You watch a transcript of a live conversation and maintain a JSON state model that represents what is being discussed visually.

## Your job per cycle

You receive:
1. The current state model (entities, relations, current diagram type, recent transcript).
2. New transcript segments since the last cycle.

You return an updated state model. Your output MUST conform to the JSON schema you were given.

## Diagram type detection

Choose `active_diagram_type` from: `architecture`, `process_flow`, `mindmap`, `sequence`, `entity_model`.

Stay with the current type unless the conversation has clearly shifted to a different mode. Examples:
- "let's design the integration" -> architecture
- "what happens when the customer clicks submit" -> process_flow
- "let's brainstorm everything related to onboarding" -> mindmap
- "user calls the API, then the API calls..." -> sequence
- "we need a Customer table with..." -> entity_model

## Entity rules

- For entities that already exist in the state, keep their `id` (they look like `ent_NNN`).
- For new entities, assign temporary IDs like `tmp_001`, `tmp_002`, etc. Code will replace these with stable IDs.
- Do not reassign an existing entity's `id`. Do not change `x` or `y` (you do not own positions).
- The `kind` field must be one of: `system`, `role`, `store`, `actor`, `process`, `decision`, `event`.

## Relation rules

- A relation has `from`, `to`, and optional `label`. `from`/`to` must reference an entity `id` that exists in the same page.
- Use temporary `id`s like `tmp_rel_001` for new relations.

## Multi-page model

The state has a list of pages. The page whose `type` matches `active_diagram_type` and whose `role` is `live` is where new content goes. Do not modify pages with `role: snapshot` or `role: archived`. If you decide an entity is no longer relevant, omit it from the live page; code will move it to the archived page.

## What you do NOT do

- Do not invent transcript content. Only extract from what is provided.
- Do not modify positions, IDs, snapshot pages, or the archived page.
- Do not return prose. Only valid JSON conforming to the schema.
```

- [ ] **Step 2: Create the JSON schema**

Write to `prompts/schema.json`:

```json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "type": "object",
  "required": ["meeting_id", "started_at", "active_diagram_type", "pages"],
  "properties": {
    "meeting_id": {"type": "string"},
    "started_at": {"type": "string"},
    "active_diagram_type": {
      "type": "string",
      "enum": ["architecture", "process_flow", "mindmap", "sequence", "entity_model"]
    },
    "pages": {
      "type": "array",
      "items": {
        "type": "object",
        "required": ["name", "type", "role", "entities", "relations"],
        "properties": {
          "name": {"type": "string"},
          "type": {"type": "string", "enum": ["architecture", "process_flow", "mindmap", "sequence", "entity_model"]},
          "role": {"type": "string", "enum": ["live", "snapshot", "archived"]},
          "entities": {
            "type": "array",
            "items": {
              "type": "object",
              "required": ["id", "label", "kind"],
              "properties": {
                "id": {"type": "string"},
                "label": {"type": "string"},
                "kind": {"type": "string", "enum": ["system", "role", "store", "actor", "process", "decision", "event"]},
                "x": {"type": "integer"},
                "y": {"type": "integer"}
              }
            }
          },
          "relations": {
            "type": "array",
            "items": {
              "type": "object",
              "required": ["id", "from", "to"],
              "properties": {
                "id": {"type": "string"},
                "from": {"type": "string"},
                "to": {"type": "string"},
                "label": {"type": "string"}
              }
            }
          }
        }
      }
    }
  }
}
```

- [ ] **Step 3: Commit**

```bash
git add prompts/ && git commit -m "feat(prompts): add system prompt and JSON schema for the LLM cycle"
```

---

### Task 5: LLM cycle (Claude integration)

**Files:**
- Modify: `llm.py`
- Create: `tests/fixtures/transcript_architecture.txt`
- Create: `tests/test_llm_golden.py`

- [ ] **Step 1: Create the transcript fixture**

Write to `tests/fixtures/transcript_architecture.txt`:

```
14:02:00 So we want to design the new translation service. Customer-facing requests come into D365.
14:02:30 D365 sends them to the MT Proxy via HTTPS, then the proxy hands them off to the Translator service.
14:03:00 The translator returns the response back through the proxy to D365. We need a cache somewhere.
14:03:30 Let's put a Redis store between the proxy and the translator for caching translations.
14:04:00 D365 also writes audit logs to a SQL audit store.
```

- [ ] **Step 2: Write the LLM cycle module**

Write to `llm.py`:

```python
import json
import os
from pathlib import Path
from anthropic import Anthropic
from model import MeetingState

PROMPT_DIR = Path(__file__).parent / "prompts"
DEFAULT_MODEL = "claude-sonnet-4-6"


def _load_prompt() -> str:
    return (PROMPT_DIR / "system.md").read_text(encoding="utf-8")


def _load_schema() -> dict:
    return json.loads((PROMPT_DIR / "schema.json").read_text(encoding="utf-8"))


def run_cycle(
    state: MeetingState,
    new_segments_text: str,
    model: str = DEFAULT_MODEL,
    client: Anthropic | None = None,
) -> MeetingState:
    """Run one LLM cycle. Returns an updated MeetingState (with tmp_ ids for new entities)."""
    client = client or Anthropic()
    system_prompt = _load_prompt()
    schema = _load_schema()
    user_message = (
        "Current state:\n"
        f"```json\n{state.model_dump_json(indent=2, by_alias=True)}\n```\n\n"
        "New transcript segments since last cycle:\n"
        f"```\n{new_segments_text}\n```\n\n"
        "Return the updated state model as JSON. Output ONLY the JSON, no prose, no markdown fences."
    )
    response = client.messages.create(
        model=model,
        max_tokens=8000,
        system=[
            {
                "type": "text",
                "text": system_prompt + "\n\n## JSON schema\n\n" + json.dumps(schema),
                "cache_control": {"type": "ephemeral"},
            }
        ],
        messages=[{"role": "user", "content": user_message}],
    )
    raw = response.content[0].text.strip()
    if raw.startswith("```"):
        raw = raw.split("```", 2)[1]
        if raw.startswith("json"):
            raw = raw[4:]
        raw = raw.strip()
    return MeetingState.model_validate_json(raw)
```

- [ ] **Step 3: Write the golden integration test**

Write to `tests/test_llm_golden.py`:

```python
import os
import pytest
from pathlib import Path
from llm import run_cycle
from model import MeetingState

pytestmark = pytest.mark.skipif(
    not os.environ.get("ANTHROPIC_API_KEY"),
    reason="requires ANTHROPIC_API_KEY",
)

FIXTURES = Path(__file__).parent / "fixtures"


def test_cycle_extracts_architecture_entities():
    transcript = (FIXTURES / "transcript_architecture.txt").read_text(encoding="utf-8")
    initial = MeetingState(
        meeting_id="test",
        started_at="2026-04-26T14:00:00",
        active_diagram_type="architecture",
        pages=[],
    )
    updated = run_cycle(initial, transcript)
    assert updated.active_diagram_type == "architecture"
    assert len(updated.pages) >= 1
    live = next(p for p in updated.pages if p.role == "live")
    labels = {e.label.lower() for e in live.entities}
    expected_keywords = {"d365", "mt proxy", "translator"}
    matched = sum(1 for kw in expected_keywords if any(kw in l for l in labels))
    assert matched >= 2, f"expected at least 2 of {expected_keywords} in {labels}"
```

- [ ] **Step 4: Run the test (requires API key)**

```bash
set ANTHROPIC_API_KEY=sk-ant-... && .venv/Scripts/pytest tests/test_llm_golden.py -v
```

Expected: PASS. If your key is missing the test is skipped.

- [ ] **Step 5: Commit**

```bash
git add llm.py tests/test_llm_golden.py tests/fixtures/transcript_architecture.txt && git commit -m "feat(llm): add Claude cycle with prompt caching and golden test"
```

---

### Task 6: drawio XML basics (single page, no layout)

**Files:**
- Modify: `drawio.py`
- Create: `tests/test_drawio.py`

- [ ] **Step 1: Write failing tests for the XML generator**

Write to `tests/test_drawio.py`:

```python
from lxml import etree
from model import Entity, Relation, Page, MeetingState
from drawio import to_drawio_xml, STYLE_FOR_KIND


def _parse(xml: str):
    return etree.fromstring(xml.encode("utf-8"))


def test_to_drawio_xml_root_is_mxfile():
    state = MeetingState(
        meeting_id="m", started_at="2026-04-26T14:00:00",
        active_diagram_type="architecture",
        pages=[Page(name="architecture", type="architecture", role="live")],
    )
    xml = to_drawio_xml(state)
    root = _parse(xml)
    assert root.tag == "mxfile"
    diagrams = root.findall("diagram")
    assert len(diagrams) == 1
    assert diagrams[0].get("name") == "architecture"


def test_entity_uses_correct_style():
    state = MeetingState(
        meeting_id="m", started_at="2026-04-26T14:00:00",
        active_diagram_type="architecture",
        pages=[Page(
            name="architecture", type="architecture", role="live",
            entities=[Entity(id="ent_001", label="D365", kind="system", x=120, y=80)],
        )],
    )
    xml = to_drawio_xml(state)
    root = _parse(xml)
    cell = root.xpath("//mxCell[@value='D365']")[0]
    assert cell.get("style") == STYLE_FOR_KIND["system"]
    geom = cell.find("mxGeometry")
    assert geom.get("x") == "120" and geom.get("y") == "80"


def test_relation_creates_edge():
    state = MeetingState(
        meeting_id="m", started_at="2026-04-26T14:00:00",
        active_diagram_type="architecture",
        pages=[Page(
            name="architecture", type="architecture", role="live",
            entities=[
                Entity(id="ent_001", label="D365", kind="system"),
                Entity(id="ent_002", label="MT Proxy", kind="system"),
            ],
            relations=[Relation(id="rel_001", from_="ent_001", to="ent_002", label="HTTPS")],
        )],
    )
    xml = to_drawio_xml(state)
    root = _parse(xml)
    edge = root.xpath("//mxCell[@edge='1']")[0]
    assert edge.get("source") == "ent_001"
    assert edge.get("target") == "ent_002"
    assert edge.get("value") == "HTTPS"
```

- [ ] **Step 2: Run the test, expect failure**

```bash
.venv/Scripts/pytest tests/test_drawio.py -v
```

Expected: `ImportError: cannot import name 'to_drawio_xml' from 'drawio'`.

- [ ] **Step 3: Implement the XML generator**

Write to `drawio.py`:

```python
from lxml import etree
from model import MeetingState, Page, Entity, Relation

STYLE_FOR_KIND = {
    "system": "rounded=0;whiteSpace=wrap;html=1;fillColor=#dae8fc;strokeColor=#6c8ebf;",
    "role": "ellipse;whiteSpace=wrap;html=1;fillColor=#d5e8d4;strokeColor=#82b366;",
    "store": "shape=cylinder3;whiteSpace=wrap;html=1;boundedLbl=1;backgroundOutline=1;size=15;fillColor=#fff2cc;strokeColor=#d6b656;",
    "actor": "shape=umlActor;verticalLabelPosition=bottom;html=1;outlineConnect=0;",
    "process": "rhombus;whiteSpace=wrap;html=1;fillColor=#f8cecc;strokeColor=#b85450;",
    "decision": "rhombus;whiteSpace=wrap;html=1;",
    "event": "ellipse;whiteSpace=wrap;html=1;fillColor=#e1d5e7;strokeColor=#9673a6;",
}
EDGE_STYLE = "endArrow=classic;html=1;rounded=0;"
ENTITY_WIDTH = 160
ENTITY_HEIGHT = 60


def _build_page(page: Page) -> etree._Element:
    diagram = etree.Element("diagram", name=page.name)
    graph = etree.SubElement(diagram, "mxGraphModel", grid="1", page="1")
    root = etree.SubElement(graph, "root")
    etree.SubElement(root, "mxCell", id="0")
    etree.SubElement(root, "mxCell", id="1", parent="0")
    for e in page.entities:
        cell = etree.SubElement(
            root, "mxCell",
            id=e.id, value=e.label, style=STYLE_FOR_KIND[e.kind],
            vertex="1", parent="1",
        )
        etree.SubElement(
            cell, "mxGeometry",
            x=str(e.x), y=str(e.y),
            width=str(ENTITY_WIDTH), height=str(ENTITY_HEIGHT),
        ).set("as", "geometry")
    for r in page.relations:
        edge = etree.SubElement(
            root, "mxCell",
            id=r.id, value=r.label, style=EDGE_STYLE,
            edge="1", parent="1", source=r.from_, target=r.to,
        )
        etree.SubElement(edge, "mxGeometry", relative="1").set("as", "geometry")
    return diagram


def to_drawio_xml(state: MeetingState) -> str:
    mxfile = etree.Element("mxfile", host="live-meeting-agent")
    for page in state.pages:
        mxfile.append(_build_page(page))
    return etree.tostring(mxfile, pretty_print=True, xml_declaration=False).decode("utf-8")
```

- [ ] **Step 4: Run the test, expect pass**

```bash
.venv/Scripts/pytest tests/test_drawio.py -v
```

Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add drawio.py tests/test_drawio.py && git commit -m "feat(drawio): add mxGraph XML generation for entities and relations"
```

---

### Task 7: Auto-layout for new entities

**Files:**
- Modify: `drawio.py`
- Modify: `tests/test_drawio.py`

- [ ] **Step 1: Append a failing test for auto-layout**

Append to `tests/test_drawio.py`:

```python
from drawio import layout_new_entities


def test_layout_new_entities_assigns_positions():
    page = Page(
        name="architecture", type="architecture", role="live",
        entities=[
            Entity(id="ent_001", label="D365", kind="system", x=100, y=100),
            Entity(id="ent_002", label="MT Proxy", kind="system"),
            Entity(id="ent_003", label="Translator", kind="system"),
        ],
        relations=[
            Relation(id="rel_001", from_="ent_001", to="ent_002"),
            Relation(id="rel_002", from_="ent_002", to="ent_003"),
        ],
    )
    layout_new_entities(page)
    by_id = {e.id: e for e in page.entities}
    assert by_id["ent_001"].x == 100 and by_id["ent_001"].y == 100  # preserved
    assert by_id["ent_002"].x != 0 or by_id["ent_002"].y != 0  # placed
    assert by_id["ent_003"].x != 0 or by_id["ent_003"].y != 0  # placed


def test_layout_new_entities_deterministic_with_seed():
    def make_page():
        return Page(
            name="architecture", type="architecture", role="live",
            entities=[
                Entity(id="ent_001", label="A", kind="system"),
                Entity(id="ent_002", label="B", kind="system"),
            ],
            relations=[Relation(id="rel_001", from_="ent_001", to="ent_002")],
        )
    p1 = make_page()
    p2 = make_page()
    layout_new_entities(p1, seed=42)
    layout_new_entities(p2, seed=42)
    assert p1.entities[0].x == p2.entities[0].x
    assert p1.entities[0].y == p2.entities[0].y
```

- [ ] **Step 2: Run the test, expect failure**

```bash
.venv/Scripts/pytest tests/test_drawio.py -v
```

Expected: `ImportError: cannot import name 'layout_new_entities' from 'drawio'`.

- [ ] **Step 3: Implement auto-layout**

Append to `drawio.py`:

```python
import networkx as nx

CANVAS_W = 1200
CANVAS_H = 800
MARGIN = 80


def layout_new_entities(page: Page, seed: int = 0) -> None:
    """Assigns x, y to entities whose position is (0, 0). Existing positions are preserved.
    Uses spring layout for the new entities only, with existing entities as fixed anchors."""
    g = nx.Graph()
    for e in page.entities:
        g.add_node(e.id)
    for r in page.relations:
        if r.from_ in g and r.to in g:
            g.add_edge(r.from_, r.to)
    fixed = {e.id: (e.x, e.y) for e in page.entities if (e.x, e.y) != (0, 0)}
    new_ids = [e.id for e in page.entities if (e.x, e.y) == (0, 0)]
    if not new_ids:
        return
    if fixed:
        pos = nx.spring_layout(g, pos=fixed, fixed=list(fixed.keys()), seed=seed, scale=400)
    else:
        pos = nx.spring_layout(g, seed=seed, scale=400)
    by_id = {e.id: e for e in page.entities}
    for nid in new_ids:
        nx_x, nx_y = pos[nid]
        by_id[nid].x = int(CANVAS_W / 2 + nx_x)
        by_id[nid].y = int(CANVAS_H / 2 + nx_y)
```

- [ ] **Step 4: Run the test, expect pass**

```bash
.venv/Scripts/pytest tests/test_drawio.py -v
```

Expected: 5 passed.

- [ ] **Step 5: Commit**

```bash
git add drawio.py tests/test_drawio.py && git commit -m "feat(drawio): add spring-layout auto-positioning for new entities"
```

---

### Task 8: Snapshot pages and archived page

**Files:**
- Modify: `drawio.py`
- Modify: `tests/test_drawio.py`

- [ ] **Step 1: Append failing tests for snapshots and archive**

Append to `tests/test_drawio.py`:

```python
from drawio import add_snapshot, archive_missing_entities


def test_add_snapshot_clones_live_page():
    state = MeetingState(
        meeting_id="m", started_at="2026-04-26T14:00:00",
        active_diagram_type="architecture",
        pages=[Page(
            name="architecture", type="architecture", role="live",
            entities=[Entity(id="ent_001", label="D365", kind="system", x=10, y=10)],
        )],
    )
    add_snapshot(state, timestamp_label="14:05")
    assert len(state.pages) == 2
    snap = state.pages[1]
    assert snap.role == "snapshot"
    assert snap.name == "architecture - 14:05"
    assert snap.entities[0].label == "D365"
    state.pages[0].entities[0].label = "D365 (renamed)"
    assert snap.entities[0].label == "D365"  # snapshot is a deep copy


def test_archive_missing_entities_moves_them():
    before = Page(
        name="architecture", type="architecture", role="live",
        entities=[
            Entity(id="ent_001", label="D365", kind="system"),
            Entity(id="ent_002", label="Old System", kind="system"),
        ],
    )
    after = Page(
        name="architecture", type="architecture", role="live",
        entities=[Entity(id="ent_001", label="D365", kind="system")],
    )
    state = MeetingState(
        meeting_id="m", started_at="2026-04-26T14:00:00",
        active_diagram_type="architecture",
        pages=[after],
    )
    archive_missing_entities(state, before, after)
    archived = next(p for p in state.pages if p.role == "archived")
    assert any(e.label == "Old System" for e in archived.entities)
```

- [ ] **Step 2: Run the test, expect failure**

```bash
.venv/Scripts/pytest tests/test_drawio.py -v
```

Expected: `ImportError`.

- [ ] **Step 3: Implement snapshot and archive helpers**

Append to `drawio.py`:

```python
import copy


def add_snapshot(state: MeetingState, timestamp_label: str) -> None:
    """Append a frozen snapshot of the current live page for the active diagram type."""
    live = next(
        (p for p in state.pages if p.role == "live" and p.type == state.active_diagram_type),
        None,
    )
    if live is None:
        return
    snap = copy.deepcopy(live)
    snap.role = "snapshot"
    snap.name = f"{live.type} - {timestamp_label}"
    state.pages.append(snap)


def archive_missing_entities(state: MeetingState, before: Page, after: Page) -> None:
    """Move entities present in `before` but missing in `after` to the archived page."""
    after_ids = {e.id for e in after.entities}
    missing = [e for e in before.entities if e.id not in after_ids]
    if not missing:
        return
    archived = next((p for p in state.pages if p.role == "archived"), None)
    if archived is None:
        archived = Page(name="archived", type=state.active_diagram_type, role="archived")
        state.pages.append(archived)
    archived.entities.extend(copy.deepcopy(missing))
```

- [ ] **Step 4: Run the test, expect pass**

```bash
.venv/Scripts/pytest tests/test_drawio.py -v
```

Expected: 7 passed.

- [ ] **Step 5: Commit**

```bash
git add drawio.py tests/test_drawio.py && git commit -m "feat(drawio): add per-cycle snapshot pages and archived page"
```

---

### Task 9: CLI agent in batch mode

**Files:**
- Modify: `agent.py`
- Create: `tests/test_agent_batch.py`

- [ ] **Step 1: Write a smoke test for the CLI in batch mode**

Write to `tests/test_agent_batch.py`:

```python
import os
import subprocess
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.skipif(
    not os.environ.get("ANTHROPIC_API_KEY"),
    reason="requires ANTHROPIC_API_KEY",
)


def test_batch_run_produces_drawio_and_state(tmp_path, monkeypatch):
    monkeypatch.chdir(Path(__file__).resolve().parent.parent)
    output_root = tmp_path / "meetings"
    cmd = [
        sys.executable, "agent.py", "smoketest",
        "--transcript", "tests/fixtures/transcript_architecture.txt",
        "--output-dir", str(output_root),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
    assert result.returncode == 0, result.stderr
    out = output_root / "smoketest"
    assert (out / "meeting.drawio").exists()
    assert (out / "state.json").exists()
    drawio = (out / "meeting.drawio").read_text(encoding="utf-8")
    assert "<mxfile" in drawio
```

- [ ] **Step 2: Run the test, expect failure**

```bash
.venv/Scripts/pytest tests/test_agent_batch.py -v
```

Expected: `agent.py` produces no output, returncode != 0.

- [ ] **Step 3: Implement the CLI in batch mode**

Write to `agent.py`:

```python
import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

from model import MeetingState, Page, assign_ids, diff_pages
from llm import run_cycle
from drawio import to_drawio_xml, layout_new_entities, add_snapshot, archive_missing_entities


def _load_or_init_state(state_path: Path, meeting_id: str) -> MeetingState:
    if state_path.exists():
        return MeetingState.model_validate_json(state_path.read_text(encoding="utf-8"))
    return MeetingState(
        meeting_id=meeting_id,
        started_at=datetime.now().isoformat(timespec="seconds"),
        active_diagram_type="architecture",
        pages=[],
    )


def _next_seqs(state: MeetingState) -> tuple[int, int]:
    ent = max(
        (int(e.id.split("_")[1]) for p in state.pages for e in p.entities if e.id.startswith("ent_")),
        default=0,
    )
    rel = max(
        (int(r.id.split("_")[1]) for p in state.pages for r in p.relations if r.id.startswith("rel_")),
        default=0,
    )
    return ent + 1, rel + 1


def run_one_cycle(state: MeetingState, transcript_text: str, timestamp_label: str | None = None) -> MeetingState:
    before_live = next(
        (p for p in state.pages if p.role == "live" and p.type == state.active_diagram_type),
        Page(name="empty", type=state.active_diagram_type, role="live"),
    )
    updated = run_cycle(state, transcript_text)
    next_ent, next_rel = _next_seqs(updated)
    for p in updated.pages:
        if p.role == "live":
            assign_ids(p, next_ent, next_rel)
            layout_new_entities(p)
    after_live = next(
        (p for p in updated.pages if p.role == "live" and p.type == updated.active_diagram_type),
        None,
    )
    if after_live is not None:
        archive_missing_entities(updated, before_live, after_live)
        d = diff_pages(before_live, after_live)
        print(f"+ {d.added}  ~ {d.changed}  - {d.removed}")
    if timestamp_label:
        add_snapshot(updated, timestamp_label)
    return updated


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="agent")
    parser.add_argument("name", help="meeting name (used as folder name)")
    parser.add_argument("--transcript", type=Path, help="batch mode: read this transcript file and exit")
    parser.add_argument("--output-dir", type=Path, default=Path("meetings"))
    args = parser.parse_args(argv)

    out = args.output_dir / args.name
    out.mkdir(parents=True, exist_ok=True)
    state_path = out / "state.json"
    drawio_path = out / "meeting.drawio"

    state = _load_or_init_state(state_path, args.name)

    if args.transcript:
        text = args.transcript.read_text(encoding="utf-8")
        state = run_one_cycle(state, text, timestamp_label=datetime.now().strftime("%H:%M"))
        state_path.write_text(state.model_dump_json(indent=2, by_alias=True), encoding="utf-8")
        drawio_path.write_text(to_drawio_xml(state), encoding="utf-8")
        return 0

    print("Live mode not yet implemented (requires Phase M2).", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Run the test, expect pass**

```bash
.venv/Scripts/pytest tests/test_agent_batch.py -v
```

Expected: PASS.

- [ ] **Step 5: Manual verification**

```bash
.venv/Scripts/python agent.py demo --transcript tests/fixtures/transcript_architecture.txt
```

Open `meetings/demo/meeting.drawio` in VS Code with the drawio extension. Verify entities (D365, MT Proxy, Translator, etc.) appear with edges.

- [ ] **Step 6: Commit**

```bash
git add agent.py tests/test_agent_batch.py && git commit -m "feat(agent): batch-mode CLI with end-to-end transcript-to-drawio flow"
```

**End of Phase M1.** Tag the commit:

```bash
git tag M1
```

---

## Phase M2: Live audio

End state: `python agent.py live-demo` starts a process that captures system audio, transcribes it in the background, and updates the diagram on Enter (manual trigger).

### Task 10: Audio capture (WASAPI loopback ring buffer)

**Files:**
- Modify: `audio.py`
- Create: `tests/test_audio.py`

- [ ] **Step 1: Write a unit test for the ring buffer**

Write to `tests/test_audio.py`:

```python
import numpy as np
from audio import RingBuffer


def test_ring_buffer_basic_write_read():
    buf = RingBuffer(capacity_seconds=2, sample_rate=16000)
    chunk = np.ones(8000, dtype=np.float32)
    buf.write(chunk)
    out = buf.read_since(0.0)
    assert len(out) == 8000


def test_ring_buffer_overwrites_oldest():
    buf = RingBuffer(capacity_seconds=1, sample_rate=16000)
    buf.write(np.ones(20000, dtype=np.float32))  # 1.25s of audio in 1s buffer
    out = buf.read_since(0.0)
    assert len(out) == 16000  # capped at capacity
```

- [ ] **Step 2: Run the test, expect failure**

```bash
.venv/Scripts/pytest tests/test_audio.py -v
```

Expected: `ImportError`.

- [ ] **Step 3: Implement the ring buffer and capture loop**

Write to `audio.py`:

```python
import threading
import time
import numpy as np
import sounddevice as sd

SAMPLE_RATE = 16000


class RingBuffer:
    def __init__(self, capacity_seconds: float, sample_rate: int = SAMPLE_RATE):
        self.sample_rate = sample_rate
        self.capacity = int(capacity_seconds * sample_rate)
        self.buffer = np.zeros(self.capacity, dtype=np.float32)
        self.write_pos = 0
        self.total_written = 0
        self.lock = threading.Lock()

    def write(self, chunk: np.ndarray) -> None:
        with self.lock:
            n = len(chunk)
            if n >= self.capacity:
                self.buffer[:] = chunk[-self.capacity:]
                self.write_pos = 0
                self.total_written += n
                return
            end = self.write_pos + n
            if end <= self.capacity:
                self.buffer[self.write_pos:end] = chunk
            else:
                first = self.capacity - self.write_pos
                self.buffer[self.write_pos:] = chunk[:first]
                self.buffer[:n - first] = chunk[first:]
            self.write_pos = (self.write_pos + n) % self.capacity
            self.total_written += n

    def read_since(self, seconds_ago: float) -> np.ndarray:
        with self.lock:
            samples = min(int(seconds_ago * self.sample_rate) if seconds_ago else self.capacity, self.total_written, self.capacity)
            if samples == 0:
                return np.zeros(0, dtype=np.float32)
            start = (self.write_pos - samples) % self.capacity
            if start + samples <= self.capacity:
                return self.buffer[start:start + samples].copy()
            return np.concatenate([self.buffer[start:], self.buffer[:samples - (self.capacity - start)]])


def find_loopback_device() -> int | None:
    """Return the device index of a WASAPI loopback for the default output."""
    hostapis = sd.query_hostapis()
    wasapi_idx = next((i for i, h in enumerate(hostapis) if h["name"] == "Windows WASAPI"), None)
    if wasapi_idx is None:
        return None
    devices = sd.query_devices()
    for i, d in enumerate(devices):
        if d["hostapi"] == wasapi_idx and d["max_input_channels"] > 0 and "loopback" in d["name"].lower():
            return i
    default_out = sd.query_hostapis(wasapi_idx)["default_output_device"]
    return default_out


class CaptureThread(threading.Thread):
    def __init__(self, ring: RingBuffer):
        super().__init__(daemon=True)
        self.ring = ring
        self.stop_flag = threading.Event()

    def run(self):
        while not self.stop_flag.is_set():
            try:
                device = find_loopback_device()
                with sd.InputStream(
                    device=device,
                    samplerate=self.ring.sample_rate,
                    channels=1,
                    dtype="float32",
                    extra_settings=sd.WasapiSettings(loopback=True),
                    callback=self._callback,
                ):
                    while not self.stop_flag.is_set():
                        time.sleep(0.1)
            except Exception as exc:  # pragma: no cover - hardware errors
                print(f"audio: capture error {exc!r}, retrying in 5s")
                time.sleep(5)

    def _callback(self, indata, frames, t, status):  # pragma: no cover - sounddevice callback
        if status:
            print(f"audio: status {status}")
        self.ring.write(indata[:, 0].copy())

    def stop(self):
        self.stop_flag.set()
```

- [ ] **Step 4: Run the unit tests, expect pass**

```bash
.venv/Scripts/pytest tests/test_audio.py -v
```

Expected: 2 passed.

- [ ] **Step 5: Manual smoke test**

Create `scripts/audio_smoke.py`:

```python
import time
from audio import RingBuffer, CaptureThread

ring = RingBuffer(capacity_seconds=10)
cap = CaptureThread(ring)
cap.start()
print("capturing for 5 seconds, play some audio...")
time.sleep(5)
cap.stop()
samples = ring.read_since(5)
print(f"captured {len(samples)} samples, max amplitude {abs(samples).max():.3f}")
```

```bash
mkdir -p scripts && .venv/Scripts/python scripts/audio_smoke.py
```

Expected output: `captured 80000 samples, max amplitude 0.X` (non-zero if audio was playing).

- [ ] **Step 6: Commit**

```bash
git add audio.py tests/test_audio.py scripts/audio_smoke.py && git commit -m "feat(audio): WASAPI loopback ring buffer with restart-on-failure"
```

---

### Task 11: Transcription thread (faster-whisper)

**Files:**
- Modify: `transcription.py`
- Create: `tests/test_transcription.py`

- [ ] **Step 1: Write a test that transcribes a known WAV**

Download or generate a 5-second WAV that says "this is a test of the transcription system" and place it at `tests/fixtures/test_speech.wav`. (For automated CI, generate with text-to-speech; for manual dev, record once with the Windows Voice Recorder.)

Write to `tests/test_transcription.py`:

```python
from pathlib import Path
import pytest
import numpy as np
from transcription import transcribe_array

WAV = Path(__file__).parent / "fixtures" / "test_speech.wav"
pytestmark = pytest.mark.skipif(not WAV.exists(), reason="missing fixture WAV")


def test_transcribe_array_returns_text():
    import wave
    with wave.open(str(WAV)) as f:
        frames = f.readframes(f.getnframes())
        audio = np.frombuffer(frames, dtype=np.int16).astype(np.float32) / 32768.0
        sr = f.getframerate()
    text = transcribe_array(audio, sr)
    assert "test" in text.lower() or "transcription" in text.lower()
```

- [ ] **Step 2: Run the test, expect failure**

```bash
.venv/Scripts/pytest tests/test_transcription.py -v
```

Expected: `ImportError`.

- [ ] **Step 3: Implement the transcription module**

Write to `transcription.py`:

```python
import threading
import time
import numpy as np
from faster_whisper import WhisperModel
from audio import RingBuffer
from model import TranscriptSegment

DEFAULT_MODEL_SIZE = "medium.en"
CHUNK_SECONDS = 30


_model_cache: WhisperModel | None = None


def _model() -> WhisperModel:
    global _model_cache
    if _model_cache is None:
        _model_cache = WhisperModel(DEFAULT_MODEL_SIZE, device="auto", compute_type="auto")
    return _model_cache


def transcribe_array(audio: np.ndarray, sample_rate: int) -> str:
    if sample_rate != 16000:
        from scipy import signal
        audio = signal.resample_poly(audio, 16000, sample_rate).astype(np.float32)
    segments, _ = _model().transcribe(audio, language="en", vad_filter=True)
    return " ".join(s.text.strip() for s in segments).strip()


class TranscriptionThread(threading.Thread):
    def __init__(self, ring: RingBuffer, sink: list[TranscriptSegment]):
        super().__init__(daemon=True)
        self.ring = ring
        self.sink = sink
        self.sink_lock = threading.Lock()
        self.stop_flag = threading.Event()

    def run(self):
        while not self.stop_flag.is_set():
            time.sleep(CHUNK_SECONDS)
            audio = self.ring.read_since(CHUNK_SECONDS)
            if len(audio) < self.ring.sample_rate:  # less than 1 second
                continue
            try:
                text = transcribe_array(audio, self.ring.sample_rate)
            except Exception as exc:  # pragma: no cover
                print(f"transcription: error {exc!r}")
                continue
            if text:
                t = time.strftime("%H:%M:%S")
                with self.sink_lock:
                    self.sink.append(TranscriptSegment(t=t, text=text))

    def drain(self) -> list[TranscriptSegment]:
        with self.sink_lock:
            out = list(self.sink)
            self.sink.clear()
            return out

    def stop(self):
        self.stop_flag.set()
```

Note: `scipy` is needed for resampling. Add it to `requirements.txt`:

```
scipy>=1.13
```

Then `pip install scipy`.

- [ ] **Step 4: Run the test (only if you have a fixture WAV)**

```bash
.venv/Scripts/pytest tests/test_transcription.py -v
```

Expected: PASS, or skipped if no fixture.

- [ ] **Step 5: Commit**

```bash
git add transcription.py tests/test_transcription.py requirements.txt && git commit -m "feat(transcription): faster-whisper background thread with chunked decoding"
```

---

### Task 12: Live mode in `agent.py` (manual trigger)

**Files:**
- Modify: `agent.py`

- [ ] **Step 1: Replace the live-mode stub in `agent.py`**

Modify the `main` function in `agent.py`. Replace the section starting with `if args.transcript:` and the live-mode error block. New version:

```python
def _live_mode(args, state: MeetingState, state_path: Path, drawio_path: Path) -> int:
    from audio import RingBuffer, CaptureThread
    from transcription import TranscriptionThread

    ring = RingBuffer(capacity_seconds=600)
    transcript_sink: list = []
    cap = CaptureThread(ring)
    transcribe = TranscriptionThread(ring, transcript_sink)
    cap.start()
    transcribe.start()
    print("live mode running. Press Enter for force-update, Ctrl+C to stop.")
    try:
        while True:
            input()
            new_segments = transcribe.drain()
            state.transcript.extend(new_segments)
            new_text = "\n".join(f"{s.t} {s.text}" for s in new_segments)
            if not new_text:
                print("(no new transcript yet, skipping cycle)")
                continue
            state = run_one_cycle(state, new_text, timestamp_label=datetime.now().strftime("%H:%M"))
            state_path.write_text(state.model_dump_json(indent=2, by_alias=True), encoding="utf-8")
            drawio_path.write_text(to_drawio_xml(state), encoding="utf-8")
    except KeyboardInterrupt:
        print("\nstopping...")
    finally:
        cap.stop()
        transcribe.stop()
    return 0
```

In `main`, replace the `print("Live mode not yet implemented...")` block with:

```python
    return _live_mode(args, state, state_path, drawio_path)
```

- [ ] **Step 2: Manual end-to-end test**

```bash
.venv/Scripts/python agent.py live-demo
```

Speak into the meeting (or play a YouTube video about a software architecture). Wait 30+ seconds. Press Enter. Verify the diagram appears in `meetings/live-demo/meeting.drawio`. Press Ctrl+C to stop.

- [ ] **Step 3: Commit**

```bash
git add agent.py && git commit -m "feat(agent): wire live audio + manual Enter trigger into the cycle loop"
```

**End of Phase M2.** Tag:

```bash
git tag M2
```

---

## Phase M3: Active participant

End state: `python agent.py live-demo --interval 5m` runs autonomously; `Ctrl+Shift+U` forces an immediate update.

### Task 13: Timer trigger

**Files:**
- Modify: `triggers.py`
- Create: `tests/test_triggers.py`

- [ ] **Step 1: Write a test for the timer**

Write to `tests/test_triggers.py`:

```python
import time
from triggers import IntervalTimer


def test_interval_timer_fires_repeatedly():
    fires: list[float] = []
    timer = IntervalTimer(interval_seconds=0.2, callback=lambda: fires.append(time.time()))
    timer.start()
    time.sleep(0.7)
    timer.stop()
    assert len(fires) >= 3
```

- [ ] **Step 2: Run the test, expect failure**

```bash
.venv/Scripts/pytest tests/test_triggers.py -v
```

Expected: `ImportError`.

- [ ] **Step 3: Implement the timer**

Write to `triggers.py`:

```python
import threading
import time
from typing import Callable


class IntervalTimer:
    def __init__(self, interval_seconds: float, callback: Callable[[], None]):
        self.interval = interval_seconds
        self.callback = callback
        self.stop_flag = threading.Event()
        self.thread: threading.Thread | None = None

    def start(self) -> None:
        def loop():
            while not self.stop_flag.wait(self.interval):
                try:
                    self.callback()
                except Exception as exc:  # pragma: no cover
                    print(f"timer: callback error {exc!r}")
        self.thread = threading.Thread(target=loop, daemon=True)
        self.thread.start()

    def stop(self) -> None:
        self.stop_flag.set()
```

- [ ] **Step 4: Run the test, expect pass**

```bash
.venv/Scripts/pytest tests/test_triggers.py -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add triggers.py tests/test_triggers.py && git commit -m "feat(triggers): interval timer that runs a callback on a background thread"
```

---

### Task 14: Global hotkey + interval flag in agent

**Files:**
- Modify: `triggers.py`
- Modify: `agent.py`

- [ ] **Step 1: Add hotkey helper to `triggers.py`**

Append to `triggers.py`:

```python
def register_hotkey(hotkey: str, callback: Callable[[], None]) -> Callable[[], None]:
    """Register a global hotkey. Returns an unregister function."""
    import keyboard
    keyboard.add_hotkey(hotkey, callback)
    return lambda: keyboard.remove_hotkey(hotkey)
```

(No unit test - hotkey registration depends on a real OS event loop. Manual verification only.)

- [ ] **Step 2: Add `--interval` and `--hotkey` arguments**

In `agent.py`, modify `main` to accept new arguments. Replace the parser block with:

```python
    parser = argparse.ArgumentParser(prog="agent")
    parser.add_argument("name", help="meeting name (used as folder name)")
    parser.add_argument("--transcript", type=Path, help="batch mode: read this transcript file and exit")
    parser.add_argument("--output-dir", type=Path, default=Path("meetings"))
    parser.add_argument("--interval", default="5m", help="auto-update interval (e.g. 5m, 30s, off)")
    parser.add_argument("--hotkey", default="ctrl+shift+u", help="global hotkey for force-update")
    args = parser.parse_args(argv)
```

- [ ] **Step 3: Wire the timer and hotkey into `_live_mode`**

Replace the body of `_live_mode` with:

```python
def _live_mode(args, state: MeetingState, state_path: Path, drawio_path: Path) -> int:
    from audio import RingBuffer, CaptureThread
    from transcription import TranscriptionThread
    from triggers import IntervalTimer, register_hotkey

    ring = RingBuffer(capacity_seconds=600)
    transcript_sink: list = []
    cap = CaptureThread(ring)
    transcribe = TranscriptionThread(ring, transcript_sink)
    cap.start()
    transcribe.start()

    fire_event = threading.Event()

    def trigger():
        fire_event.set()

    interval_seconds = _parse_interval(args.interval)
    timer = IntervalTimer(interval_seconds, trigger) if interval_seconds else None
    if timer:
        timer.start()
    unregister_hotkey = register_hotkey(args.hotkey, trigger)
    print(f"live mode: interval={args.interval}, hotkey={args.hotkey}, Ctrl+C to stop.")

    try:
        while True:
            fire_event.wait()
            fire_event.clear()
            new_segments = transcribe.drain()
            state.transcript.extend(new_segments)
            new_text = "\n".join(f"{s.t} {s.text}" for s in new_segments)
            if not new_text:
                print("(no new transcript yet, skipping cycle)")
                continue
            state = run_one_cycle(state, new_text, timestamp_label=datetime.now().strftime("%H:%M"))
            state_path.write_text(state.model_dump_json(indent=2, by_alias=True), encoding="utf-8")
            drawio_path.write_text(to_drawio_xml(state), encoding="utf-8")
    except KeyboardInterrupt:
        print("\nstopping...")
    finally:
        cap.stop()
        transcribe.stop()
        if timer:
            timer.stop()
        unregister_hotkey()
    return 0


def _parse_interval(value: str) -> float | None:
    if value.lower() == "off":
        return None
    if value.endswith("m"):
        return float(value[:-1]) * 60
    if value.endswith("s"):
        return float(value[:-1])
    return float(value)
```

Add `import threading` at the top of `agent.py`.

- [ ] **Step 4: Manual end-to-end test**

```bash
.venv/Scripts/python agent.py live-demo --interval 60s
```

Play architecture-discussion audio. Wait 60s. Diagram should auto-update. Press Ctrl+Shift+U during minute 2 to force an extra update. Press Ctrl+C to stop.

- [ ] **Step 5: Commit**

```bash
git add agent.py triggers.py && git commit -m "feat(agent): autonomous timer + global hotkey for force-update"
```

---

### Task 15: Final polish

**Files:**
- Modify: `README.md`
- Modify: `CLAUDE.md`
- Create: `tests/fixtures/transcript_process.txt`

- [ ] **Step 1: Add a process-flow fixture**

Write to `tests/fixtures/transcript_process.txt`:

```
14:10:00 Let's walk through the customer onboarding flow.
14:10:30 Customer fills the registration form. Then the system validates the email.
14:11:00 If valid, we create the account in D365. Otherwise we send a "please retry" email.
14:11:30 After account creation, we send the welcome email and create the audit log entry.
```

- [ ] **Step 2: Add an end-of-task script that runs both fixtures**

Create `scripts/sanity.py`:

```python
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
PYTHON = ROOT / ".venv" / "Scripts" / "python.exe"

for name, transcript in [
    ("sanity-arch", "tests/fixtures/transcript_architecture.txt"),
    ("sanity-process", "tests/fixtures/transcript_process.txt"),
]:
    print(f"\n=== {name} ===")
    subprocess.run([str(PYTHON), "agent.py", name, "--transcript", transcript], cwd=ROOT, check=True)
    print(f"-> meetings/{name}/meeting.drawio")
```

```bash
.venv/Scripts/python scripts/sanity.py
```

Open both `meetings/sanity-arch/meeting.drawio` and `meetings/sanity-process/meeting.drawio`. Verify the first is an architecture diagram (rectangles, edges) and the second is a process flow (rhombus shapes for decisions).

- [ ] **Step 3: Update README with full usage**

Replace `README.md` with:

```markdown
# live-meeting-agent

Active scribe that listens to a meeting and incrementally updates a `.drawio` file every 5 minutes (or on hotkey).

## Setup

    python -m venv .venv
    .venv\Scripts\activate
    pip install -r requirements.txt
    set ANTHROPIC_API_KEY=sk-ant-...

The first run downloads the `medium.en` Whisper model (~1.5 GB) into the user cache.

## Run

Live mode (default 5-min interval, hotkey `Ctrl+Shift+U`):

    python agent.py my-meeting

Live mode with custom interval:

    python agent.py my-meeting --interval 90s

Batch mode (one-shot from a transcript file):

    python agent.py demo --transcript tests/fixtures/transcript_architecture.txt

Open `meetings/<name>/meeting.drawio` in any drawio viewer (VS Code drawio extension, drawio desktop, or app.diagrams.net) and screen-share that window in Teams.

## Output structure

    meetings/<name>/
    +- meeting.drawio    # multi-page: live page per type, snapshots, archived
    +- state.json        # current JSON model (resume from where you left off)

## Tests

    pytest                                  # unit tests
    pytest tests/test_llm_golden.py         # LLM golden tests (needs ANTHROPIC_API_KEY)

## Architecture

See `docs/superpowers/specs/2026-04-26-live-meeting-agent-design.md`.
```

- [ ] **Step 4: Update CLAUDE.md**

Replace `CLAUDE.md` with:

```markdown
# live-meeting-agent

Live diagram generator from meeting audio. v1 complete (M1+M2+M3).

## Key artefacts
- Spec: `docs/superpowers/specs/2026-04-26-live-meeting-agent-design.md`
- Plan: `docs/superpowers/plans/2026-04-26-live-meeting-agent.md`

## Architecture summary
Audio (sounddevice WASAPI loopback) -> Whisper (faster-whisper, local) -> rolling transcript -> Claude (Sonnet 4.6, prompt cached) -> JSON state -> mxGraph XML -> `meetings/<name>/meeting.drawio`.

State of the world is in `meetings/<name>/state.json`. Code owns IDs (ent_NNN, rel_NNN) and positions; LLM owns labels and semantics. New entities use tmp_NNN; code converts to stable IDs after every cycle.

Pages in the .drawio file:
- `live` pages: one per detected diagram type. Updated every cycle.
- `snapshot` pages: frozen copy of the live page at each cycle (timeline flipbook).
- `archived` page: soft-deleted entities go here.

## Common commands

    pytest                                                                            # unit tests
    pytest tests/test_llm_golden.py                                                   # golden tests (needs API key)
    python agent.py demo --transcript tests/fixtures/transcript_architecture.txt      # batch run
    python agent.py my-meeting                                                        # live run, default 5-min interval
    python scripts/sanity.py                                                          # run both fixture transcripts end-to-end

## Known gotchas
- Bluetooth headsets: WASAPI loopback captures system *output*, so it does NOT trip the Hands-Free profile (mic input is not opened). The agent and Teams can coexist.
- `keyboard` global hotkeys may need admin on some Windows configurations. If `Ctrl+Shift+U` does nothing, try `python agent.py ... --hotkey ctrl+alt+u`.
- First run downloads ~1.5 GB Whisper model. Subsequent runs are fast.
```

- [ ] **Step 5: Run the full test suite**

```bash
.venv/Scripts/pytest -v
```

Expected: all tests pass (or skip if no API key / no fixture WAV).

- [ ] **Step 6: Final commit**

```bash
git add . && git commit -m "docs: full README and CLAUDE.md for v1"
git tag v1
```

**End of Phase M3. v1 done.**

---

## Self-review checklist

After implementation, verify against the spec:

- [ ] Six components from the spec exist as separate files (`audio.py`, `transcription.py`, `model.py` (transcript+state), `triggers.py`, `llm.py`, `drawio.py`).
- [ ] State model has the ownership split: LLM owns label/kind/type/relations; code owns id/x/y. Tests cover that `assign_ids` only rewrites `tmp_*` IDs and never modifies positions.
- [ ] Auto-detect: the LLM call returns `active_diagram_type`, and a new live page is created when the type changes (verify by running the architecture fixture, then manually driving a process-flow follow-up cycle).
- [ ] Multi-page: live + snapshot + archived all coexist in one `.drawio` file. Open in drawio viewer and confirm tabs.
- [ ] Soft delete: when an entity disappears between cycles, it lands on the archived page rather than being lost.
- [ ] Failure modes: invalid LLM JSON triggers a retry-then-skip (currently propagates - if it crashes the agent in practice, add a try/except around `run_cycle` in `_live_mode` as a follow-up).
- [ ] CLI defaults match the spec: 5-minute interval, `Ctrl+Shift+U`, output to `meetings/<name>/`.
