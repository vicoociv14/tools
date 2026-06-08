import json
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


def test_relation_round_trip_uses_alias():
    r = Relation(id="rel_001", from_="ent_001", to="ent_002", label="HTTPS")
    dumped = r.model_dump_json()
    parsed = json.loads(dumped)
    assert "from" in parsed
    assert "from_" not in parsed
    assert parsed["from"] == "ent_001"
    loaded = Relation.model_validate_json(dumped)
    assert loaded.from_ == "ent_001"


def test_meeting_state_with_relations_uses_alias_in_json():
    state = MeetingState(
        meeting_id="m1",
        started_at="2026-04-26T14:00:00",
        active_diagram_type="architecture",
        pages=[
            Page(
                name="architecture", type="architecture", role="live",
                entities=[
                    Entity(id="ent_001", label="A", kind="system"),
                    Entity(id="ent_002", label="B", kind="system"),
                ],
                relations=[Relation(id="rel_001", from_="ent_001", to="ent_002")],
            ),
        ],
    )
    dumped = state.model_dump_json()
    assert '"from":' in dumped
    assert '"from_":' not in dumped


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


def test_assign_ids_chains_across_pages():
    """When called sequentially across multiple pages, IDs do not collide."""
    page_a = Page(
        name="architecture", type="architecture",
        entities=[Entity(id="tmp_001", label="A", kind="system")],
    )
    page_b = Page(
        name="process_flow", type="process_flow",
        entities=[Entity(id="tmp_001", label="B", kind="process")],
    )
    next_ent, next_rel = assign_ids(page_a, next_entity_seq=1, next_relation_seq=1)
    assign_ids(page_b, next_ent, next_rel)
    assert page_a.entities[0].id == "ent_001"
    assert page_b.entities[0].id == "ent_002"
    assert page_a.entities[0].id != page_b.entities[0].id
