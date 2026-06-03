"""Interactive OpenCV calibration for fixed live tire scan zones."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import cv2


DEFAULT_OUTPUT = Path("config/live_zones.json")


class ZoneCalibrator:
    def __init__(self):
        self.zones = []
        self.drag_start = None
        self.drag_current = None

    def handle_mouse(self, event, x, y, _flags, _param):
        if event == cv2.EVENT_LBUTTONDOWN:
            self.drag_start = (x, y)
            self.drag_current = (x, y)
        elif event == cv2.EVENT_MOUSEMOVE and self.drag_start:
            self.drag_current = (x, y)
        elif event == cv2.EVENT_LBUTTONUP and self.drag_start:
            x1, y1 = self.drag_start
            x2, y2 = x, y
            left, right = sorted((x1, x2))
            top, bottom = sorted((y1, y2))
            if right - left >= 20 and bottom - top >= 20:
                self.zones.append({
                    "name": f"zone_{len(self.zones) + 1}",
                    "rect": (left, top, right, bottom),
                })
            self.drag_start = None
            self.drag_current = None

    def draw(self, frame):
        output = frame.copy()
        for zone in self.zones:
            left, top, right, bottom = zone["rect"]
            cv2.rectangle(output, (left, top), (right, bottom), (37, 107, 79), 2)
            cv2.putText(
                output,
                zone["name"],
                (left, max(20, top - 8)),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.6,
                (244, 197, 66),
                2,
            )

        if self.drag_start and self.drag_current:
            x1, y1 = self.drag_start
            x2, y2 = self.drag_current
            cv2.rectangle(output, (x1, y1), (x2, y2), (245, 158, 11), 2)

        instructions = "Drag tire zones | s=save | c=clear | q=quit"
        cv2.putText(output, instructions, (18, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)
        return output

    def to_config(self, width, height):
        zones = []
        for zone in self.zones:
            left, top, right, bottom = zone["rect"]
            zones.append({
                "name": zone["name"],
                "x": round(left / width, 6),
                "y": round(top / height, 6),
                "w": round((right - left) / width, 6),
                "h": round((bottom - top) / height, 6),
            })
        return {
            "version": 1,
            "source_width": width,
            "source_height": height,
            "zones": zones,
        }


def parse_args():
    parser = argparse.ArgumentParser(description="Draw and save live tire scan zones.")
    parser.add_argument("--camera", type=int, default=0, help="OpenCV camera index.")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT, help="Output JSON path.")
    parser.add_argument("--width", type=int, default=1280, help="Requested camera width.")
    parser.add_argument("--height", type=int, default=720, help="Requested camera height.")
    return parser.parse_args()


def main():
    args = parse_args()
    cap = cv2.VideoCapture(args.camera)
    if not cap.isOpened():
        raise SystemExit(f"Could not open camera index {args.camera}")

    cap.set(cv2.CAP_PROP_FRAME_WIDTH, args.width)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, args.height)

    calibrator = ZoneCalibrator()
    window_name = "ATIS Zone Calibration"
    cv2.namedWindow(window_name)
    cv2.setMouseCallback(window_name, calibrator.handle_mouse)

    saved = False
    try:
        while True:
            ok, frame = cap.read()
            if not ok:
                raise SystemExit("Camera frame read failed.")

            cv2.imshow(window_name, calibrator.draw(frame))
            key = cv2.waitKey(1) & 0xFF
            if key == ord("q"):
                break
            if key == ord("c"):
                calibrator.zones.clear()
            if key == ord("s"):
                if not calibrator.zones:
                    print("Draw at least one zone before saving.")
                    continue
                height, width = frame.shape[:2]
                args.output.parent.mkdir(parents=True, exist_ok=True)
                args.output.write_text(
                    json.dumps(calibrator.to_config(width, height), indent=2),
                    encoding="utf-8",
                )
                print(f"Saved {len(calibrator.zones)} zone(s) to {args.output}")
                saved = True
                break
    finally:
        cap.release()
        cv2.destroyAllWindows()

    if not saved:
        print("Calibration closed without saving.")


if __name__ == "__main__":
    main()
