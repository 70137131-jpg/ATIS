"""
models.py - Database Models

This file defines the structure of our database using SQLAlchemy.
We have three main tables:
1. User - for login/authentication
2. Inspection - stores data about each tire inspection (plate, status, etc.)
3. Alert - tracks issues that need attention
4. AuditEvent - immutable workflow/action audit log
"""

import json
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime, timezone
from werkzeug.security import check_password_hash, generate_password_hash

# Initialize the database object
db = SQLAlchemy()


class User(db.Model):
    """
    User Table
    Stores login credentials and roles.

    Passwords are never stored in plain text — only a salted hash is persisted.
    Use ``set_password()`` to assign a password and ``check_password()`` to verify.
    """
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(120), unique=True, nullable=False)
    # Werkzeug hashes can be long (scrypt/pbkdf2); allow generous width.
    password_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(20), nullable=False, default="Operator")
    is_active = db.Column(db.Boolean, nullable=False, default=True)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    def set_password(self, raw_password):
        """Hash and store the given plain-text password."""
        self.password_hash = generate_password_hash(raw_password)

    def check_password(self, raw_password):
        """Return True if the given plain-text password matches the stored hash."""
        if not self.password_hash:
            return False
        return check_password_hash(self.password_hash, raw_password)

    def __repr__(self):
        return f"<User {self.email}>"


class Inspection(db.Model):
    """
    Inspection Table
    The main table storing every vehicle scan event.
    """
    __tablename__ = "inspections"

    id = db.Column(db.Integer, primary_key=True)
    timestamp = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc), index=True)
    plate = db.Column(db.String(20), nullable=True, index=True)          # License plate (can be null if not readable)
    location_id = db.Column(db.Integer, db.ForeignKey("locations.id"), nullable=True, index=True)
    camera_id = db.Column(db.Integer, db.ForeignKey("cameras.id"), nullable=True, index=True)
    location = db.Column(db.String(200), nullable=False)     # e.g. "Main Gate Entrance"
    camera = db.Column(db.String(20), nullable=True)         # Camera ID
    status = db.Column(db.String(10), nullable=False, index=True)        # "safe" or "unsafe"
    confidence = db.Column(db.Integer, nullable=False)       # AI confidence score (0-100)
    predicted_class = db.Column(db.String(80), nullable=True)
    model_path = db.Column(db.String(300), nullable=True)
    model_version = db.Column(db.String(64), nullable=True)
    model_threshold = db.Column(db.Integer, nullable=True)
    low_confidence = db.Column(db.Boolean, nullable=False, default=False)
    inference_ms = db.Column(db.Integer, nullable=True)
    # Legacy/cache field retained for backwards compatibility and old reports.
    # New code also writes structured rows to InspectionDefect.
    defects = db.Column(db.String(300), nullable=True)       # Comma-separated detected defects, e.g. "Crack,Bulge"
    created_by_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    plate_source = db.Column(db.String(30), nullable=True)
    plate_confidence = db.Column(db.Integer, nullable=True)
    plate_raw_text = db.Column(db.String(200), nullable=True)
    review_status = db.Column(db.String(30), nullable=False, default="pending_review", index=True)
    review_notes = db.Column(db.Text, nullable=True)
    reviewer_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    reviewed_at = db.Column(db.DateTime, nullable=True)
    correction_label = db.Column(db.String(80), nullable=True)
    image_path = db.Column(db.String(300), nullable=True)    # Path to uploaded tire image (relative to static/)
    # Image storage metadata. image_data remains the default demo/local backend;
    # object_key supports S3-compatible production storage.
    image_data = db.Column(db.LargeBinary, nullable=True)
    image_mime = db.Column(db.String(50), nullable=True)
    image_storage = db.Column(db.String(20), nullable=False, default="db")
    image_object_key = db.Column(db.String(500), nullable=True)
    image_size = db.Column(db.Integer, nullable=True)
    image_checksum = db.Column(db.String(64), nullable=True, index=True)
    # Crack localizer output: JSON list of {label, confidence, severity, bbox:[x1,y1,x2,y2]}
    # in normalized (0-1) coords, so the detail page can redraw the marker.
    boxes = db.Column(db.Text, nullable=True)

    # Relationship: One inspection can have many alerts
    alerts = db.relationship("Alert", backref="inspection", lazy=True)
    location_ref = db.relationship("Location", foreign_keys=[location_id])
    camera_ref = db.relationship("Camera", foreign_keys=[camera_id])
    created_by = db.relationship("User", foreign_keys=[created_by_id])
    reviewer = db.relationship("User", foreign_keys=[reviewer_id])
    inspection_defects = db.relationship(
        "InspectionDefect",
        back_populates="inspection",
        cascade="all, delete-orphan",
        order_by="InspectionDefect.id",
    )

    @property
    def defect_list(self):
        """
        Helper function to convert the comma-separated defects string
        into a Python list for easy loop usage in templates.
        """
        if self.inspection_defects:
            return [row.defect_type.name for row in self.inspection_defects if row.defect_type]
        if not self.defects:
            return []
        return [d.strip() for d in self.defects.split(",") if d.strip()]

    @property
    def box_list(self):
        """Parse the persisted localization boxes JSON into a list (empty if none)."""
        if not self.boxes:
            return []
        try:
            data = json.loads(self.boxes)
        except (ValueError, TypeError):
            return []
        return data if isinstance(data, list) else []

    def __repr__(self):
        return f"<Inspection {self.id} {self.plate or '—'} {self.status}>"


class Location(db.Model):
    """Operational checkpoint/location catalog."""
    __tablename__ = "locations"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), nullable=False)
    normalized_name = db.Column(db.String(200), nullable=False, unique=True, index=True)
    zone = db.Column(db.String(80), nullable=True, index=True)
    is_active = db.Column(db.Boolean, nullable=False, default=True, index=True)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    cameras = db.relationship("Camera", back_populates="location", order_by="Camera.name")

    def __repr__(self):
        return f"<Location {self.name}>"


class Camera(db.Model):
    """Operational camera catalog linked to a location."""
    __tablename__ = "cameras"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(20), nullable=False)
    normalized_name = db.Column(db.String(20), nullable=False, index=True)
    location_id = db.Column(db.Integer, db.ForeignKey("locations.id"), nullable=True, index=True)
    zone = db.Column(db.String(80), nullable=True, index=True)
    is_active = db.Column(db.Boolean, nullable=False, default=True, index=True)
    assigned_user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True, index=True)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    location = db.relationship("Location", back_populates="cameras")
    assigned_user = db.relationship("User", foreign_keys=[assigned_user_id])

    __table_args__ = (
        db.UniqueConstraint("normalized_name", "location_id", name="uq_cameras_name_location"),
    )

    def __repr__(self):
        return f"<Camera {self.name}>"


class DefectType(db.Model):
    """Canonical defect taxonomy used by reports, filters, and review feedback."""
    __tablename__ = "defect_types"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(80), nullable=False)
    normalized_name = db.Column(db.String(80), nullable=False, unique=True, index=True)
    description = db.Column(db.String(255), nullable=True)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    inspection_defects = db.relationship("InspectionDefect", back_populates="defect_type")

    def __repr__(self):
        return f"<DefectType {self.name}>"


class InspectionDefect(db.Model):
    """Structured defect occurrence attached to a single inspection."""
    __tablename__ = "inspection_defects"

    id = db.Column(db.Integer, primary_key=True)
    inspection_id = db.Column(db.Integer, db.ForeignKey("inspections.id"), nullable=False, index=True)
    defect_type_id = db.Column(db.Integer, db.ForeignKey("defect_types.id"), nullable=False, index=True)
    severity = db.Column(db.String(20), nullable=True)
    confidence = db.Column(db.Integer, nullable=True)
    bbox = db.Column(db.Text, nullable=True)
    model_source = db.Column(db.String(300), nullable=True)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    inspection = db.relationship("Inspection", back_populates="inspection_defects")
    defect_type = db.relationship("DefectType", back_populates="inspection_defects")

    @property
    def bbox_list(self):
        """Parse normalized bbox JSON into a list, or return None."""
        if not self.bbox:
            return None
        try:
            data = json.loads(self.bbox)
        except (TypeError, ValueError):
            return None
        return data if isinstance(data, list) else None

    def __repr__(self):
        name = self.defect_type.name if self.defect_type else self.defect_type_id
        return f"<InspectionDefect {self.inspection_id} {name}>"


class Alert(db.Model):
    """
    Alert Table
    Created when an inspection is 'unsafe'. Tracks the workflow status.
    """
    __tablename__ = "alerts"

    id = db.Column(db.Integer, primary_key=True)
    
    # Link to the Inspection table
    inspection_id = db.Column(db.Integer, db.ForeignKey("inspections.id"), nullable=False, index=True)
    
    # Status of the alert workflow: pending -> acknowledged -> resolved
    status = db.Column(db.String(20), nullable=False, default="pending", index=True)
    
    # Optional notes added by the operator
    response = db.Column(db.String(200), nullable=True)
    priority = db.Column(db.String(20), nullable=False, default="medium", index=True)
    severity = db.Column(db.String(20), nullable=False, default="major", index=True)
    assigned_user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True, index=True)
    assigned_team = db.Column(db.String(80), nullable=True)
    sla_due_at = db.Column(db.DateTime, nullable=True, index=True)
    escalation_status = db.Column(db.String(30), nullable=False, default="none", index=True)
    resolution_category = db.Column(db.String(50), nullable=True)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), index=True)
    acknowledged_by_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    acknowledged_at = db.Column(db.DateTime, nullable=True)
    resolved_by_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    resolved_at = db.Column(db.DateTime, nullable=True)

    acknowledged_by = db.relationship("User", foreign_keys=[acknowledged_by_id])
    resolved_by = db.relationship("User", foreign_keys=[resolved_by_id])
    assigned_user = db.relationship("User", foreign_keys=[assigned_user_id])
    comments = db.relationship(
        "AlertComment",
        back_populates="alert",
        cascade="all, delete-orphan",
        order_by="AlertComment.created_at.desc()",
    )

    def __repr__(self):
        return f"<Alert {self.id} {self.status}>"


class AlertComment(db.Model):
    """Comments and workflow history entries attached to an alert."""
    __tablename__ = "alert_comments"

    id = db.Column(db.Integer, primary_key=True)
    alert_id = db.Column(db.Integer, db.ForeignKey("alerts.id"), nullable=False, index=True)
    author_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True, index=True)
    comment_type = db.Column(db.String(20), nullable=False, default="comment", index=True)
    body = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc), index=True)

    alert = db.relationship("Alert", back_populates="comments")
    author = db.relationship("User", foreign_keys=[author_id])

    def __repr__(self):
        return f"<AlertComment {self.alert_id} {self.comment_type}>"


class SavedFilter(db.Model):
    """Named per-user saved filters for repeat operational views."""
    __tablename__ = "saved_filters"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    page = db.Column(db.String(50), nullable=False, default="history", index=True)
    name = db.Column(db.String(80), nullable=False)
    params = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))

    user = db.relationship("User", foreign_keys=[user_id])

    __table_args__ = (
        db.UniqueConstraint("user_id", "page", "name", name="uq_saved_filters_user_page_name"),
    )

    @property
    def params_dict(self):
        if not self.params:
            return {}
        try:
            data = json.loads(self.params)
        except (TypeError, ValueError):
            return {}
        return data if isinstance(data, dict) else {}

    def __repr__(self):
        return f"<SavedFilter {self.user_id} {self.page} {self.name}>"


class AuditEvent(db.Model):
    """Append-only audit trail for user and workflow actions."""
    __tablename__ = "audit_events"

    id = db.Column(db.Integer, primary_key=True)
    created_at = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc), index=True)
    actor_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True, index=True)
    actor_email = db.Column(db.String(120), nullable=True)
    action = db.Column(db.String(80), nullable=False, index=True)
    entity_type = db.Column(db.String(50), nullable=True, index=True)
    entity_id = db.Column(db.Integer, nullable=True, index=True)
    ip_address = db.Column(db.String(45), nullable=True)
    user_agent = db.Column(db.String(255), nullable=True)
    details = db.Column(db.Text, nullable=True)

    actor = db.relationship("User", foreign_keys=[actor_id])

    @property
    def details_dict(self):
        """Parse JSON audit details into a dict."""
        if not self.details:
            return {}
        try:
            data = json.loads(self.details)
        except (TypeError, ValueError):
            return {}
        return data if isinstance(data, dict) else {}

    def __repr__(self):
        return f"<AuditEvent {self.id} {self.action}>"
