"""Data contracts: the EpisodeBrief (input) and the storyboard the writer produces."""

from typing import Literal

from pydantic import BaseModel, Field


class Lyrics(BaseModel):
    en: str | None = None
    hi: str | None = None


class EpisodeBrief(BaseModel):
    """What the user's other AI fills in. Only show/topic/learning_goal are required."""

    show: str = Field(description="Show id from library/shows (e.g. pip-and-paro, octo-family)")
    topic: str = Field(description="What the episode is about, e.g. 'colours of fruits'")
    learning_goal: str = Field(description="What a child should learn, e.g. 'name 5 colours'")
    age_band: Literal["2-3", "3-5", "5-7"] = "2-3"
    languages: list[Literal["en", "hi"]] = ["en", "hi"]
    duration_sec: int = Field(75, ge=40, le=150)
    cast: list[str] = Field(default_factory=list, description="Cast ids to feature; empty = writer chooses from the show")
    scenes: list[str] = Field(default_factory=list, description="Scene ids to use; empty = writer chooses")
    mood: str = Field("happy, bouncy", description="Song mood words")
    bpm: int | None = Field(None, ge=60, le=140, description="Optional fixed tempo; otherwise the writer picks")
    song_style: str | None = Field(None, description="Optional extra music/voice style for this episode")
    key: str | None = Field(None, description="Optional musical key, e.g. 'C Major'")
    voice_pitch_hz: float | None = Field(None, description="Target median vocal pitch (child ≈ 350–450 Hz) used to rank takes")
    repetition: Literal["low", "medium", "high"] = "high"
    lyrics: Lyrics | None = Field(None, description="Optional ready-made lyrics with [Verse]/[Chorus] tags")
    must_include: list[str] = Field(default_factory=list)
    avoid: list[str] = Field(default_factory=list)
    autopilot: bool = False
    slug: str | None = None


SectionKind = Literal["intro", "verse", "chorus", "bridge", "outro", "interlude"]
Shot = Literal["wide", "medium", "close"]


class PropRef(BaseModel):
    id: str
    label: str = ""  # e.g. "1", "Red"


class CastAction(BaseModel):
    who: str
    action: str


class Line(BaseModel):
    singers: list[str]
    en: str
    hi: str
    shot: Shot = "wide"
    focus: str = ""
    actions: list[CastAction] = []
    props: list[PropRef] = []


class Section(BaseModel):
    kind: SectionKind
    scene: str
    lines: list[Line]


class PropDef(BaseModel):
    id: str
    description: str


class Bilingual(BaseModel):
    en: str
    hi: str


class Storyboard(BaseModel):
    title: Bilingual
    description: Bilingual
    bpm: int = Field(100, ge=80, le=135)
    sections: list[Section]
    props: list[PropDef] = []

    def lines(self) -> list[Line]:
        return [ln for s in self.sections for ln in s.lines]
