"""
models.py - Database Models

This file defines the structure of our database using SQLAlchemy.
We have three main tables:
1. User - for login/authentication
2. Inspection - stores data about each tire inspection (plate, status, etc.)
3. Alert - tracks issues that need attention
"""

from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
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
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

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
    timestamp = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    plate = db.Column(db.String(20), nullable=True)          # License plate (can be null if not readable)
    location = db.Column(db.String(200), nullable=False)     # e.g. "Main Gate Entrance"
    camera = db.Column(db.String(20), nullable=True)         # Camera ID
    status = db.Column(db.String(10), nullable=False)        # "safe" or "unsafe"
    confidence = db.Column(db.Integer, nullable=False)       # AI confidence score (0-100)
    defects = db.Column(db.String(300), nullable=True)       # String list of defects, e.g. "Tread,Sidewall"
    image_path = db.Column(db.String(300), nullable=True)    # Path to uploaded tire image (relative to static/)

    # Relationship: One inspection can have many alerts
    alerts = db.relationship("Alert", backref="inspection", lazy=True)

    @property
    def defect_list(self):
        """
        Helper function to convert the comma-separated defects string 
        into a Python list for easy loop usage in templates.
        """
        if not self.defects:
            return []
        # Split string by comma and remove whitespace
        return [d.strip() for d in self.defects.split(",") if d.strip()]

    def __repr__(self):
        return f"<Inspection {self.id} {self.plate or '—'} {self.status}>"


class Alert(db.Model):
    """
    Alert Table
    Created when an inspection is 'unsafe'. Tracks the workflow status.
    """
    __tablename__ = "alerts"

    id = db.Column(db.Integer, primary_key=True)
    
    # Link to the Inspection table
    inspection_id = db.Column(db.Integer, db.ForeignKey("inspections.id"), nullable=False)
    
    # Status of the alert workflow: pending -> acknowledged -> resolved
    status = db.Column(db.String(20), nullable=False, default="pending")
    
    # Optional notes added by the operator
    response = db.Column(db.String(200), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def __repr__(self):
        return f"<Alert {self.id} {self.status}>"
