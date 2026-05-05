from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class ActiveRegion:
    value: str


def _normalize(region: str, allowed_regions: tuple[str, ...]) -> str:
    region = (region or "").strip().lower()
    if region not in allowed_regions:
        raise ValueError(f"region must be one of {allowed_regions}, got {region!r}")
    return region


def read_active_region(path: str, default_region: str, allowed_regions: tuple[str, ...]) -> ActiveRegion:
    try:
        with open(path, "r", encoding="utf-8") as f:
            return ActiveRegion(_normalize(f.read(), allowed_regions))
    except FileNotFoundError:
        region = _normalize(default_region, allowed_regions)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(region)
        return ActiveRegion(region)


def write_active_region(path: str, region: str, allowed_regions: tuple[str, ...]) -> ActiveRegion:
    region = _normalize(region, allowed_regions)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(region)
    return ActiveRegion(region)

