"""Pure Python/OpenCV live tire inspection runner."""

from __future__ import annotations

import argparse
import json
import re
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

import cv2

from atis_inference import classify_tyre_frame


DEFAULT_ZONES_PATH = Path("config/live_zones.json")


@dataclass
class Zone:
    name: str
    x: float
    y: float
    w: float
    h: float


@dataclass
class ZoneState:
    previous_gray: Any | None = None
    last_prediction: dict[str, Any] | None = None
    last_motion_score: float = 0.0
    unsafe_streak: int = 0
    last_log_at: float = 0.0
    last_error: str | None = None
    last_analyzed_at: float = 0.0
    last_logged_id: int | None = None


@dataclass
class RuntimeState:
    zones: list[Zone]
    zone_states: dict[str, ZoneState] = field(default_factory=dict)
    paused: bool = False

    def __post_init__(self):
        for zone in self.zones:
            self.zone_states[zone.name] = ZoneState()


def parse_args():
    parser = argparse.ArgumentParser(description="Run live ATIS tire inspection from a camera.")
    parser.add_argument("--camera", type=int, default=0, help="OpenCV camera index.")
    parser.add_argument("--zones", type=Path, default=DEFAULT_ZONES_PATH, help="Calibrated zone JSON path.")
    parser.add_argument("--width", type=int, default=1280, help="Requested camera width.")
    parser.add_argument("--height", type=int, default=720, help="Requested camera height.")
    parser.add_argument("--analyze-interval", type=float, default=0.5, help="Seconds between model passes.")
    parser.add_argument("--motion-threshold", type=float, default=8.0, help="Mean frame-diff required before analysis.")
    parser.add_argument("--unsafe-streak", type=int, default=3, help="Unsafe predictions required before logging.")
    parser.add_argument("--cooldown", type=float, default=20.0, help="Seconds between logs per zone.")
    parser.add_argument("--location", default="Live Camera Feed", help="Location stored for DB inspection rows.")
    parser.add_argument("--camera-label", default="LIVE-CAM", help="Camera label stored for DB inspection rows.")
    parser.add_argument("--no-db-log", action="store_true", help="Display results without writing inspections/alerts.")
    return parser.parse_args()


def load_zones(path: Path) -> list[Zone]:
    if not path.exists():
        raise SystemExit(
            f"Zone config not found: {path}\n"
            "Run: python3 calibrate_live_zones.py --camera 0"
        )

    data = json.loads(path.read_text(encoding="utf-8"))
    zones = []
    for index, raw_zone in enumerate(data.get("zones", []), start=1):
        try:
            zone = Zone(
                name=str(raw_zone.get("name") or f"zone_{index}"),
                x=float(raw_zone["x"]),
                y=float(raw_zone["y"]),
                w=float(raw_zone["w"]),
                h=float(raw_zone["h"]),
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise SystemExit(f"Invalid zone #{index} in {path}: {raw_zone}") from exc
        if zone.w <= 0 or zone.h <= 0:
            raise SystemExit(f"Invalid non-positive zone size in {path}: {raw_zone}")
        zones.append(zone)

    if not zones:
        raise SystemExit(f"No zones found in {path}")
    return zones


def zone_rect(zone: Zone, frame_width: int, frame_height: int):
    left = int(max(0, min(frame_width - 1, round(zone.x * frame_width))))
    top = int(max(0, min(frame_height - 1, round(zone.y * frame_height))))
    right = int(max(left + 1, min(frame_width, round((zone.x + zone.w) * frame_width))))
    bottom = int(max(top + 1, min(frame_height, round((zone.y + zone.h) * frame_height))))
    return left, top, right, bottom


def crop_zone(frame, zone: Zone):
    height, width = frame.shape[:2]
    left, top, right, bottom = zone_rect(zone, width, height)
    return frame[top:bottom, left:right], (left, top, right, bottom)


def motion_score(crop, state: ZoneState) -> float:
    gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
    gray = cv2.resize(gray, (96, 96), interpolation=cv2.INTER_AREA)
    if state.previous_gray is None:
        state.previous_gray = gray
        return 0.0

    diff = cv2.absdiff(gray, state.previous_gray)
    state.previous_gray = gray
    return float(diff.mean())


def safe_filename(value: str) -> str:
    value = re.sub(r"[^A-Za-z0-9_.-]+", "_", value.strip())
    return value.strip("_") or "zone"


class InspectionLogger:
    def __init__(self, enabled: bool):
        self.enabled = enabled
        self.available = False
        self.error: str | None = None
        if not enabled:
            return

        try:
            from app import UPLOAD_FOLDER, app
            from models import Alert, Inspection, db
        except Exception as exc:
            self.error = f"Database logging unavailable: {exc}"
            print(self.error)
            return

        self.app = app
        self.db = db
        self.Alert = Alert
        self.Inspection = Inspection
        self.upload_folder = Path(UPLOAD_FOLDER)
        self.upload_folder.mkdir(parents=True, exist_ok=True)
        self.available = True

    def log_unsafe(self, *, frame, crop, rect, zone: Zone, prediction: dict[str, Any], location: str, camera_label: str):
        if not self.enabled:
            return None
        if not self.available:
            print(self.error or "Database logging unavailable.")
            return None

        timestamp = datetime.utcnow()
        stamp = timestamp.strftime("%Y%m%d_%H%M%S_%f")
        zone_name = safe_filename(zone.name)
        frame_name = f"live_{zone_name}_{stamp}_frame.jpg"
        crop_name = f"live_{zone_name}_{stamp}_crop.jpg"
        frame_path = self.upload_folder / frame_name
        crop_path = self.upload_folder / crop_name

        annotated = frame.copy()
        left, top, right, bottom = rect
        cv2.rectangle(annotated, (left, top), (right, bottom), (68, 68, 239), 3)
        cv2.putText(
            annotated,
            f"{zone.name}: {prediction['predicted_class']} {prediction['confidence']}%",
            (left + 6, max(24, top - 10)),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.75,
            (68, 68, 239),
            2,
        )

        cv2.imwrite(str(frame_path), annotated)
        cv2.imwrite(str(crop_path), crop)

        defects = prediction.get("defects") or []
        try:
            with self.app.app_context():
                inspection = self.Inspection(
                    timestamp=timestamp,
                    plate=None,
                    location=location,
                    camera=camera_label,
                    status=prediction["status"],
                    confidence=int(prediction["confidence"]),
                    defects=",".join(defects) if defects else None,
                    image_path=f"uploads/{frame_name}",
                )
                self.db.session.add(inspection)
                self.db.session.flush()
                self.db.session.add(self.Alert(
                    inspection_id=inspection.id,
                    status="pending",
                    created_at=timestamp,
                ))
                self.db.session.commit()
                print(f"Logged unsafe live inspection #{inspection.id} for {zone.name}")
                return inspection.id
        except Exception as exc:
            try:
                self.db.session.rollback()
            except Exception:
                pass
            print(f"Live inspection DB log failed: {exc}")
            return None


def color_for_status(status: str | None):
    if status == "safe":
        return (22, 132, 95)
    if status == "unsafe":
        return (68, 68, 239)
    return (128, 128, 128)


def draw_zone_overlay(frame, zone: Zone, rect, state: ZoneState, motion_threshold: float):
    left, top, right, bottom = rect
    prediction = state.last_prediction
    status = prediction.get("status") if prediction else None
    color = color_for_status(status)

    if state.last_motion_score < motion_threshold:
        label = f"{zone.name}: waiting"
        color = (128, 128, 128)
    elif prediction:
        label = f"{zone.name}: {prediction['predicted_class']} {prediction['confidence']}%"
    else:
        label = f"{zone.name}: scanning"
        color = (0, 165, 255)

    cv2.rectangle(frame, (left, top), (right, bottom), color, 2)
    cv2.rectangle(frame, (left, max(0, top - 28)), (right, top), color, -1)
    cv2.putText(frame, label, (left + 6, max(18, top - 8)), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (255, 255, 255), 2)

    if prediction and prediction.get("defects"):
        defect_text = ", ".join(prediction["defects"])
        cv2.putText(frame, defect_text, (left + 6, min(bottom + 22, frame.shape[0] - 8)), cv2.FONT_HERSHEY_SIMPLEX, 0.55, color, 2)


def maybe_analyze_zone(crop, rect, state: ZoneState, args, logger: InspectionLogger, frame_for_log, zone: Zone, now: float):
    score = motion_score(crop, state)
    state.last_motion_score = score

    if score < args.motion_threshold:
        state.unsafe_streak = 0
        return

    if now - state.last_analyzed_at < args.analyze_interval:
        return

    state.last_analyzed_at = now
    try:
        prediction = classify_tyre_frame(crop)
        state.last_prediction = prediction
        state.last_error = None
    except Exception as exc:
        state.last_error = str(exc)
        print(f"Model inference failed for {zone.name}: {exc}")
        return

    if prediction["status"] == "unsafe":
        state.unsafe_streak += 1
        if state.unsafe_streak >= args.unsafe_streak and now - state.last_log_at >= args.cooldown:
            inspection_id = logger.log_unsafe(
                frame=frame_for_log,
                crop=crop,
                rect=rect,
                zone=zone,
                prediction=prediction,
                location=args.location,
                camera_label=args.camera_label,
            )
            state.last_log_at = now
            state.last_logged_id = inspection_id
            state.unsafe_streak = 0
    else:
        state.unsafe_streak = 0


def draw_header(frame, args, state: RuntimeState):
    status = "PAUSED" if state.paused else "LIVE"
    text = (
        f"ATIS {status} | q=quit p=pause r=reset | "
        f"unsafe streak={args.unsafe_streak} cooldown={int(args.cooldown)}s"
    )
    cv2.rectangle(frame, (0, 0), (frame.shape[1], 42), (16, 41, 31), -1)
    cv2.putText(frame, text, (16, 28), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (244, 197, 66), 2)


def reset_states(state: RuntimeState):
    for zone_state in state.zone_states.values():
        zone_state.last_prediction = None
        zone_state.unsafe_streak = 0
        zone_state.last_error = None
        zone_state.last_logged_id = None


def main():
    args = parse_args()
    zones = load_zones(args.zones)
    runtime = RuntimeState(zones)
    logger = InspectionLogger(enabled=not args.no_db_log)

    cap = cv2.VideoCapture(args.camera)
    if not cap.isOpened():
        raise SystemExit(f"Could not open camera index {args.camera}")

    cap.set(cv2.CAP_PROP_FRAME_WIDTH, args.width)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, args.height)

    window_name = "ATIS Live Tire Inspection"
    print(f"Loaded {len(zones)} live zone(s) from {args.zones}")
    print("Press q to quit, p to pause/resume, r to reset counters.")

    try:
        while True:
            ok, frame = cap.read()
            if not ok:
                print("Camera frame read failed.")
                break

            display = frame.copy()
            now = time.monotonic()

            if not runtime.paused:
                for zone in zones:
                    crop, rect = crop_zone(frame, zone)
                    maybe_analyze_zone(
                        crop,
                        rect,
                        runtime.zone_states[zone.name],
                        args,
                        logger,
                        frame.copy(),
                        zone,
                        now,
                    )
                    draw_zone_overlay(display, zone, rect, runtime.zone_states[zone.name], args.motion_threshold)
            else:
                for zone in zones:
                    _crop, rect = crop_zone(frame, zone)
                    draw_zone_overlay(display, zone, rect, runtime.zone_states[zone.name], args.motion_threshold)

            draw_header(display, args, runtime)
            cv2.imshow(window_name, display)

            key = cv2.waitKey(1) & 0xFF
            if key == ord("q"):
                break
            if key == ord("p"):
                runtime.paused = not runtime.paused
            if key == ord("r"):
                reset_states(runtime)
    finally:
        cap.release()
        cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
