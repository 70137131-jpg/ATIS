"""
seed.py — Create tables and populate dummy data for ATIS.
Run once:  python seed.py

Demo defect labels are sample dashboard data. The current web inference path
only classifies normal vs cracked; do not treat bulge/flat-spot seed rows as
current model capability.
"""
import sys, os
sys.path.insert(0, os.path.dirname(__file__))

from datetime import datetime, timedelta
from app import DEMO_USER_CREDENTIALS, app
from models import db, User, Inspection, Alert


def seed():
    with app.app_context():
        # Drop and recreate all tables for a clean reset
        db.drop_all()
        db.create_all()
        print("✓ Tables dropped and recreated.")

        # ── Users (passwords stored hashed via set_password) ──
        users = []
        for email, password, role in DEMO_USER_CREDENTIALS:
            user = User(email=email, role=role)
            user.set_password(password)
            users.append(user)
        db.session.add_all(users)

        # ── Inspections ────────────────────────────────────
        # Base time: Feb 13, 2026 ~14:48
        base = datetime(2026, 2, 13, 14, 48, 33)

        inspections_data = [
            # === Recent dashboard rows ===
            {"offset": 0,   "plate": "BXP-8735", "location": "Highway I-95 South - Mile 58",       "camera": "CAM-002", "status": "safe",   "confidence": 79,  "defects": None},
            {"offset": 1,   "plate": "BGL-8880", "location": "Interstate 80 - Weigh Station",      "camera": "CAM-005", "status": "safe",   "confidence": 86,  "defects": None},
            {"offset": 4,   "plate": "DPJ-2877", "location": "Route 66 East - Checkpoint A",       "camera": "CAM-003", "status": "unsafe", "confidence": 91,  "defects": "Crack,Bulge,Flat Spot"},
            {"offset": 14,  "plate": "MLL-2498", "location": "Highway 101 - Toll Plaza",           "camera": "CAM-006", "status": "safe",   "confidence": 84,  "defects": None},
            {"offset": 24,  "plate": "7DT-3323", "location": "Highway I-95 South - Mile 58",       "camera": "CAM-007", "status": "safe",   "confidence": 94,  "defects": None},
            {"offset": 27,  "plate": "WNZ-8747", "location": "Interstate 80 - Weigh Station",      "camera": "CAM-005", "status": "safe",   "confidence": 93,  "defects": None},
            {"offset": 29,  "plate": None,        "location": "Highway I-95 South - Mile 58",       "camera": "CAM-002", "status": "safe",   "confidence": 91,  "defects": None},

            # === History rows ===
            {"offset": 1,   "plate": "JAD-J993", "location": "Highway I-95 South - Mile 58",       "camera": "CAM-001", "status": "safe",   "confidence": 94,  "defects": None},
            {"offset": 17,  "plate": "X7X-4114", "location": "Route 66 East - Checkpoint A",       "camera": "CAM-003", "status": "unsafe", "confidence": 81,  "defects": "Crack,Bulge"},
            {"offset": 23,  "plate": "KXB-0007", "location": "Highway 101 - Toll Plaza",           "camera": "CAM-006", "status": "safe",   "confidence": 81,  "defects": None},
            {"offset": 26,  "plate": None,        "location": "Highway I-95 North - Checkpoint B",  "camera": "CAM-004", "status": "unsafe", "confidence": 88,  "defects": "Crack,Flat Spot"},
            {"offset": 28,  "plate": "THB-1995", "location": "Interstate 80 - Weigh Station",      "camera": "CAM-005", "status": "unsafe", "confidence": 86,  "defects": "Crack"},
            {"offset": 39,  "plate": "KDX-6325", "location": "Interstate 80 - Weigh Station",      "camera": "CAM-005", "status": "unsafe", "confidence": 81,  "defects": None},
            {"offset": 42,  "plate": "WTU-6244", "location": "Highway I-95 North - Checkpoint B",  "camera": "CAM-004", "status": "safe",   "confidence": 92,  "defects": None},

            # === Additional recent inspections ===
            {"offset": 5,   "plate": "RNK-4421", "location": "Route 66 West - Checkpoint C",       "camera": "CAM-008", "status": "safe",   "confidence": 88,  "defects": None},
            {"offset": 8,   "plate": "PMZ-9034", "location": "Highway 101 - Toll Plaza",           "camera": "CAM-006", "status": "safe",   "confidence": 95,  "defects": None},
            {"offset": 11,  "plate": "GTR-1567", "location": "Highway I-95 North - Checkpoint B",  "camera": "CAM-004", "status": "unsafe", "confidence": 78,  "defects": "Flat Spot"},
            {"offset": 19,  "plate": "YWQ-3380", "location": "Interstate 80 - Weigh Station",      "camera": "CAM-005", "status": "safe",   "confidence": 90,  "defects": None},
            {"offset": 33,  "plate": "FBN-7712", "location": "Route 66 East - Checkpoint A",       "camera": "CAM-003", "status": "unsafe", "confidence": 85,  "defects": "Bulge,Crack"},
            {"offset": 45,  "plate": "HVD-6053", "location": "Highway I-95 South - Mile 58",       "camera": "CAM-002", "status": "safe",   "confidence": 97,  "defects": None},
            {"offset": 55,  "plate": None,        "location": "Route 66 West - Checkpoint C",       "camera": "CAM-008", "status": "unsafe", "confidence": 76,  "defects": "Flat Spot"},
            {"offset": 63,  "plate": "CVX-2910", "location": "Highway 101 - Toll Plaza",           "camera": "CAM-006", "status": "safe",   "confidence": 89,  "defects": None},
            {"offset": 78,  "plate": "NLB-4488", "location": "Interstate 80 - Weigh Station",      "camera": "CAM-005", "status": "safe",   "confidence": 92,  "defects": None},
            {"offset": 90,  "plate": "AKW-5519", "location": "Highway I-95 North - Checkpoint B",  "camera": "CAM-004", "status": "unsafe", "confidence": 82,  "defects": "Bulge"},
            {"offset": 105, "plate": "ZJT-8830", "location": "Route 66 East - Checkpoint A",       "camera": "CAM-003", "status": "safe",   "confidence": 91,  "defects": None},
            {"offset": 120, "plate": "QMP-1176", "location": "Highway I-95 South - Mile 58",       "camera": "CAM-002", "status": "safe",   "confidence": 87,  "defects": None},

            # === Alert-linked inspections ===
            {"offset": 146, "plate": None,        "location": "Highway I-95 North - Checkpoint B",  "camera": "CAM-004", "status": "unsafe", "confidence": 87,  "defects": "Crack,Bulge,Flat Spot"},
            {"offset": 238, "plate": "VDM-5786", "location": "Highway I-95 North - Checkpoint B",  "camera": "CAM-004", "status": "unsafe", "confidence": 85,  "defects": "Bulge,Crack"},
            {"offset": 244, "plate": "hST-1181", "location": "Highway I-95 North - Checkpoint B",  "camera": "CAM-004", "status": "unsafe", "confidence": 82,  "defects": "Bulge"},
            {"offset": 388, "plate": "MRM-2628", "location": "Route 66 West - Checkpoint C",       "camera": "CAM-008", "status": "unsafe", "confidence": 90,  "defects": "Flat Spot,Bulge"},
            {"offset": 441, "plate": "XPV-8558", "location": "Highway 101 - Toll Plaza",           "camera": "CAM-006", "status": "unsafe", "confidence": 88,  "defects": "Bulge,Crack"},
            {"offset": 531, "plate": "LEC-7918", "location": "Highway 101 - Toll Plaza",           "camera": "CAM-006", "status": "unsafe", "confidence": 79,  "defects": "Crack"},
            {"offset": 618, "plate": None,        "location": "Route 66 West - Checkpoint C",       "camera": "CAM-008", "status": "unsafe", "confidence": 84,  "defects": "Crack,Bulge,Flat Spot"},
            {"offset": 780, "plate": "FXJ-0917", "location": "Route 66 East - Checkpoint A",       "camera": "CAM-003", "status": "unsafe", "confidence": 86,  "defects": "Bulge,Crack"},
            {"offset": 891, "plate": None,        "location": "Route 66 East - Checkpoint A",       "camera": "CAM-003", "status": "unsafe", "confidence": 83,  "defects": "Bulge"},

            # === More alert-linked inspections (acknowledged / resolved) ===
            {"offset": 950,  "plate": "WBX-3341", "location": "Highway I-95 South - Mile 58",      "camera": "CAM-002", "status": "unsafe", "confidence": 80,  "defects": "Flat Spot"},
            {"offset": 1020, "plate": "TKN-6629", "location": "Interstate 80 - Weigh Station",     "camera": "CAM-005", "status": "unsafe", "confidence": 77,  "defects": "Crack"},
            {"offset": 1100, "plate": "RGP-4450", "location": "Route 66 West - Checkpoint C",      "camera": "CAM-008", "status": "unsafe", "confidence": 83,  "defects": "Bulge"},
            {"offset": 1200, "plate": None,        "location": "Highway 101 - Toll Plaza",          "camera": "CAM-006", "status": "unsafe", "confidence": 75,  "defects": "Crack,Bulge"},
            {"offset": 1350, "plate": "JNR-8817", "location": "Highway I-95 North - Checkpoint B", "camera": "CAM-004", "status": "unsafe", "confidence": 89,  "defects": "Flat Spot,Bulge"},
            {"offset": 1500, "plate": "DLS-2205", "location": "Route 66 East - Checkpoint A",      "camera": "CAM-003", "status": "unsafe", "confidence": 81,  "defects": "Bulge,Crack"},
            {"offset": 1620, "plate": "BYX-9903", "location": "Highway I-95 South - Mile 58",      "camera": "CAM-002", "status": "unsafe", "confidence": 74,  "defects": "Flat Spot"},
            {"offset": 1800, "plate": "KMH-7741", "location": "Interstate 80 - Weigh Station",     "camera": "CAM-005", "status": "unsafe", "confidence": 78,  "defects": "Crack,Bulge"},
            {"offset": 2000, "plate": "SNP-5508", "location": "Route 66 West - Checkpoint C",      "camera": "CAM-008", "status": "unsafe", "confidence": 85,  "defects": "Flat Spot,Bulge,Crack"},
        ]

        inspections = []
        for d in inspections_data:
            insp = Inspection(
                timestamp=base - timedelta(minutes=d["offset"]),
                plate=d["plate"],
                location=d["location"],
                camera=d["camera"],
                status=d["status"],
                confidence=d["confidence"],
                defects=d["defects"],
            )
            inspections.append(insp)
            db.session.add(insp)

        db.session.flush()  # assign IDs

        # ── Alerts (all four statuses: pending, acknowledged, resolved, escalated) ──
        alert_data = [
            # (inspection index, alert status, response note)
            # — Pending —
            (26, "pending",      None),                          # offset 146
            (27, "pending",      None),                          # VDM-5786
            (28, "pending",      None),                          # hST-1181
            (30, "pending",      None),                          # XPV-8558
            (31, "pending",      None),                          # LEC-7918

            # — Escalated —
            (29, "escalated",    None),                          # MRM-2628
            (32, "escalated",    None),                          # offset 618
            (33, "escalated",    None),                          # FXJ-0917
            (34, "escalated",    None),                          # offset 891

            # — Acknowledged —
            (35, "acknowledged", "Driver notified"),              # WBX-3341
            (36, "acknowledged", "Inspection team dispatched"),   # TKN-6629
            (37, "acknowledged", "Under review"),                 # RGP-4450
            (38, "acknowledged", "Fleet manager contacted"),      # Unknown plate

            # — Resolved —
            (39, "resolved",     "Tire replaced — cleared"),      # JNR-8817
            (40, "resolved",     "False positive confirmed"),     # DLS-2205
            (41, "resolved",     "Vehicle recalled to depot"),    # BYX-9903
            (42, "resolved",     "Tire pressure corrected"),      # KMH-7741
            (43, "resolved",     "All tires replaced on-site"),   # SNP-5508
        ]

        for idx, status, response in alert_data:
            alert = Alert(
                inspection_id=inspections[idx].id,
                status=status,
                response=response,
                created_at=inspections[idx].timestamp,
            )
            db.session.add(alert)

        db.session.commit()
        print(f"✓ Seeded {len(inspections)} inspections, {len(alert_data)} alerts, {len(users)} users.")


if __name__ == "__main__":
    seed()
