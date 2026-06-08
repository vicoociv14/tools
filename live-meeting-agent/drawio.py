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
