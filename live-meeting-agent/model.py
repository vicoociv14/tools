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
    model_config = ConfigDict(populate_by_name=True, serialize_by_alias=True)
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
