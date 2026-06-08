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
