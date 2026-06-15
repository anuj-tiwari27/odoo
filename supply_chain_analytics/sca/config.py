"""Configuration loading and credential resolution.

Configuration is split in two:

  * non-secret settings live in a YAML file (see ``config.example.yaml``), and
  * secrets (the Acumatica username/password) are read from environment
    variables so they never end up in source control.

Any ``${ENV_VAR}`` token appearing in a string value of the YAML file is
expanded from the environment at load time, which keeps the database URL and
auth out of the file as well.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

_ENV_TOKEN = re.compile(r"\$\{([A-Z0-9_]+)\}")


def _expand_env(value: Any) -> Any:
    """Recursively expand ``${VAR}`` tokens in strings using ``os.environ``."""
    if isinstance(value, str):
        def repl(match: re.Match) -> str:
            name = match.group(1)
            if name not in os.environ:
                raise KeyError(f"Environment variable {name!r} referenced in config is not set")
            return os.environ[name]

        return _ENV_TOKEN.sub(repl, value)
    if isinstance(value, dict):
        return {k: _expand_env(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_expand_env(v) for v in value]
    return value


@dataclass
class AcumaticaConfig:
    base_url: str
    company: str
    username: str
    password: str
    # Generic Inquiry name per logical feed, e.g. {"open_pos": "GI-OpenPOs"}.
    inquiries: dict[str, str] = field(default_factory=dict)
    verify_ssl: bool = True
    timeout_seconds: int = 60

    @property
    def odata_root(self) -> str:
        return f"{self.base_url.rstrip('/')}/odata/{self.company}"


@dataclass
class SeasonalityConfig:
    # Relative weights for week-of-month buckets (1..5). Normalised at use.
    week_of_month_weights: list[float] = field(
        default_factory=lambda: [1.0, 1.0, 1.0, 1.0, 1.0]
    )
    # Optional Mon..Sun ship weights; used by callers that need daily detail.
    day_of_week_weights: list[float] = field(
        default_factory=lambda: [1.0, 1.0, 1.0, 1.0, 1.0, 0.0, 0.0]
    )


@dataclass
class PlanningConfig:
    coverage_horizon_weeks: int = 5
    # Per-item params live in dim_item; these are fallbacks when a field is null.
    default_lead_time_wks: float = 4.0
    default_safety_stock: float = 0.0
    default_assembly_days: float = 0.5
    default_pack_ship_days: float = 0.5


@dataclass
class Config:
    database_url: str
    acumatica: AcumaticaConfig
    seasonality: SeasonalityConfig = field(default_factory=SeasonalityConfig)
    planning: PlanningConfig = field(default_factory=PlanningConfig)
    # Optional per-feed field mappings: feed -> {target_column: source_field}.
    field_maps: dict[str, dict[str, str]] = field(default_factory=dict)

    @classmethod
    def load(cls, path: str | Path) -> "Config":
        raw = yaml.safe_load(Path(path).read_text())
        raw = _expand_env(raw)

        acu = raw.get("acumatica", {})
        acumatica = AcumaticaConfig(
            base_url=acu["base_url"],
            company=acu["company"],
            username=acu.get("username") or os.environ.get("ACUMATICA_USER", ""),
            password=acu.get("password") or os.environ.get("ACUMATICA_PASSWORD", ""),
            inquiries=acu.get("inquiries", {}),
            verify_ssl=acu.get("verify_ssl", True),
            timeout_seconds=acu.get("timeout_seconds", 60),
        )

        seas = raw.get("seasonality", {})
        seasonality = SeasonalityConfig(
            week_of_month_weights=seas.get("week_of_month_weights")
            or SeasonalityConfig().week_of_month_weights,
            day_of_week_weights=seas.get("day_of_week_weights")
            or SeasonalityConfig().day_of_week_weights,
        )

        plan = raw.get("planning", {})
        planning = PlanningConfig(
            coverage_horizon_weeks=plan.get("coverage_horizon_weeks", 5),
            default_lead_time_wks=plan.get("default_lead_time_wks", 4.0),
            default_safety_stock=plan.get("default_safety_stock", 0.0),
            default_assembly_days=plan.get("default_assembly_days", 0.5),
            default_pack_ship_days=plan.get("default_pack_ship_days", 0.5),
        )

        return cls(
            database_url=raw["database_url"],
            acumatica=acumatica,
            seasonality=seasonality,
            planning=planning,
            field_maps=raw.get("field_maps", {}),
        )
