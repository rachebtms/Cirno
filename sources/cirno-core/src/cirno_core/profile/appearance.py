"""Paired day/night palettes and the owner's presentation preferences."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel


class Palette(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    background: str = Field(pattern=r"^#[0-9a-fA-F]{6}$")
    surface: str = Field(pattern=r"^#[0-9a-fA-F]{6}$")
    panel: str = Field(pattern=r"^#[0-9a-fA-F]{6}$")
    text: str = Field(pattern=r"^#[0-9a-fA-F]{6}$")
    muted: str = Field(pattern=r"^#[0-9a-fA-F]{6}$")
    accent: str = Field(pattern=r"^#[0-9a-fA-F]{6}$")
    border: str = Field(pattern=r"^#[0-9a-fA-F]{6}$")


class Theme(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    id: str = Field(pattern=r"^[a-z][a-z0-9-]{0,63}$")
    name: str = Field(min_length=1, max_length=80)
    light: Palette
    dark: Palette


def theme(identifier: str, name: str, light: list[str], dark: list[str]) -> Theme:
    fields = tuple(Palette.model_fields)
    return Theme(
        id=identifier,
        name=name,
        light=Palette(**dict(zip(fields, light, strict=True))),
        dark=Palette(**dict(zip(fields, dark, strict=True))),
    )


BUILTIN_THEMES = (
    theme(
        "cirno-snow",
        "Cirno Snow",
        ["#f7fbff", "#edf5fc", "#ffffff", "#183247", "#526c80", "#087fa3", "#d0e2ef"],
        ["#0e1b29", "#152738", "#1b3043", "#eaf6ff", "#a2bdd0", "#7bd5f1", "#304b60"],
    ),
    theme(
        "ocean",
        "Ocean",
        ["#f3fbfc", "#e7f3f4", "#ffffff", "#1a3942", "#4f6c75", "#08777e", "#c7dfe2"],
        ["#13242e", "#1a303b", "#213c46", "#e8f6f4", "#a7c9c8", "#79d5cf", "#36545e"],
    ),
    theme(
        "forest",
        "Forest",
        ["#f7faf6", "#edf3e9", "#ffffff", "#273b2c", "#5c705e", "#3e744a", "#d4e0d0"],
        ["#18231b", "#213026", "#2a3b2e", "#edf5e9", "#b1c4ac", "#9ad1a2", "#415344"],
    ),
    theme(
        "graphite",
        "Graphite",
        ["#fafafa", "#f0f0f1", "#ffffff", "#27292d", "#62656b", "#4f6384", "#dadce0"],
        ["#202124", "#292b2f", "#33363b", "#f1f2f4", "#b0b4bc", "#b0c5e9", "#484c53"],
    ),
)


class Preferences(BaseModel):
    model_config = ConfigDict(extra="forbid", alias_generator=to_camel)

    theme_id: str = "cirno-snow"
    theme_mode: Literal["system", "light", "dark"] = "system"
    custom_themes: list[Theme] = Field(default_factory=list)
    language: str = "en"
    launcher_order: list[str] = Field(default_factory=list)
    activity_mode: Literal["auto", "expanded"] = "auto"
    reasoning_detail_mode: Literal["brief", "detailed"] = "brief"
    tool_detail_mode: Literal["brief", "detailed"] = "brief"
    reading_text_size: Literal["small", "standard", "large", "custom"] = "standard"
    custom_reading_text_size: int = Field(default=16, ge=14, le=28)
    code_wrap: bool = True
    brand_logos: bool = True
    browser_notifications: bool = False
    notification_sound: bool = False
    muted_notification_categories: list[Literal["operations", "conversations", "system"]] = Field(
        default_factory=list
    )
    file_edit_display_mode: Literal["summary", "diff", "collapsed_diff"] = "summary"
