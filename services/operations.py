"""Operational location/camera catalog helpers."""

from __future__ import annotations

import re

from models import Camera, Location, db


def normalize_operational_name(raw: str | None) -> str:
    return re.sub(r"\s+", " ", (raw or "").strip()).lower()


def get_or_create_location(name: str, *, zone: str | None = None) -> Location:
    display_name = re.sub(r"\s+", " ", (name or "").strip()) or "Unknown Location"
    normalized_name = normalize_operational_name(display_name)
    location = Location.query.filter_by(normalized_name=normalized_name).first()
    if location is not None:
        if zone and not location.zone:
            location.zone = zone[:80]
        return location

    location = Location(
        name=display_name[:200],
        normalized_name=normalized_name[:200],
        zone=zone[:80] if zone else None,
        is_active=True,
    )
    db.session.add(location)
    db.session.flush()
    return location


def get_or_create_camera(name: str | None, *, location: Location | None = None, zone: str | None = None) -> Camera | None:
    if not name:
        return None
    display_name = re.sub(r"\s+", " ", name.strip().upper())[:20]
    if not display_name:
        return None
    normalized_name = normalize_operational_name(display_name)[:20]
    camera = Camera.query.filter_by(
        normalized_name=normalized_name,
        location_id=location.id if location else None,
    ).first()
    if camera is not None:
        if zone and not camera.zone:
            camera.zone = zone[:80]
        return camera

    camera = Camera(
        name=display_name,
        normalized_name=normalized_name,
        location_id=location.id if location else None,
        zone=zone[:80] if zone else (location.zone if location else None),
        is_active=True,
    )
    db.session.add(camera)
    db.session.flush()
    return camera


def resolve_operational_context(location_name: str, camera_name: str | None = None, *, zone: str | None = None):
    """Return `(Location, Camera|None)` for inspection metadata."""
    location = get_or_create_location(location_name, zone=zone)
    camera = get_or_create_camera(camera_name, location=location, zone=zone)
    return location, camera
