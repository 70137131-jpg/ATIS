# PROD.md - Automated Tire Detection and Inspection System (ATIS)

## 1. Product Summary

**Product name:** Automated Tire Detection and Inspection System (ATIS)  
**Project title in source document:** Drive IQ Intelligent Car Maintenance  
**Domain:** Road safety, computer vision, deep learning, highway inspection  
**Primary users:** Highway operators, Motorway Police staff, system administrators  
**Purpose:** Detect visually unsafe vehicle tires at highway entry points and alert human operators before those vehicles enter high-speed traffic.

ATIS is a proof-of-concept system that uses cameras, image preprocessing, and a deep learning classification model to inspect vehicle tires. The system classifies tire condition as **Safe**, **Marginal**, or **Unsafe** based on visible wear and damage, then sends alerts to highway operators for manual verification.

The product is designed as a decision-support tool, not a fully autonomous enforcement system.

---

## 2. Problem Statement

Tire-related failures are a major road safety issue in Pakistan, especially for commercial vehicles such as buses and trucks. Manual tire inspections at toll plazas and checkpoints are inconsistent, subjective, and unable to scale for every vehicle. Unsafe tires with worn tread, cracks, bulges, or visible degradation may continue operating until failure, increasing the risk of blowouts, skidding, crashes, road closures, and loss of life.

Existing inspection methods depend heavily on human judgment and periodic certification. ATIS addresses this gap by providing continuous, camera-based screening at highway entry points.

---

## 3. Goals

1. Automatically capture tire images from vehicles passing through highway entry or toll inspection zones.
2. Preprocess captured tire images for AI-based analysis.
3. Classify tire condition using a trained deep learning model.
4. Detect visual tire defects including worn tread, cracks, sidewall bulges, and general degradation.
5. Generate real-time alerts for vehicles with unsafe tire conditions.
6. Provide an operator dashboard for alerts, live inspection status, reports, and historical logs.
7. Store all inspection results with metadata for auditing and future model improvement.
8. Support future integration with ANPR/toll systems for vehicle identification.
9. Demonstrate a cost-effective proof-of-concept suitable for Pakistani highway conditions.

---

## 4. Non-Goals / Out of Scope

The system will **not**:

1. Automatically issue fines or challans.
2. Physically stop vehicles.
3. Replace human inspection or legal enforcement decisions.
4. Measure exact tread depth in millimeters.
5. Detect non-visual tire problems such as internal pressure, temperature, or hidden structural damage.
6. Guarantee accurate detection during extreme weather, low lighting, fog, mud, or camera obstruction.
7. Provide full nationwide deployment in Phase 1.
8. Fully integrate with criminal databases or automated legal penalty systems.
9. Depend on unrelated bot/NLP features mentioned in the appendix of the source template. Those sections appear to be leftover template content and are excluded from this product scope.

---

## 5. Target Users

### 5.1 Highway Operator / Motorway Police

**Role:** Monitors the dashboard, reviews alerts, validates unsafe tire detections, and directs vehicles for secondary inspection.  
**Technical level:** Basic computer literacy.  
**Main needs:** Simple interface, fast alerts, clear visual evidence, reliable status indicators.

### 5.2 System Administrator

**Role:** Manages users, database, cameras, AI model updates, logs, and troubleshooting.  
**Technical level:** Advanced IT/CS knowledge.  
**Main needs:** System configuration, retraining support, error logs, access control, deployment monitoring.

### 5.3 Existing Highway Systems

**Role:** External systems such as ANPR or toll databases that may provide vehicle identification data.  
**Main needs:** API/data exchange for vehicle ID, plate number, timestamp, and location matching.

### 5.4 Project Supervisor / Evaluator

**Role:** Academic reviewer for final year project validation.  
**Main needs:** Clear proof-of-concept, documented requirements, working prototype, design diagrams, and testable outputs.

---

## 6. Core Product Flow

1. Vehicle enters the highway inspection zone.
2. Camera system detects the vehicle and captures tire images.
3. Image preprocessing module improves image quality and extracts tire regions of interest.
4. AI inference module classifies tire condition.
5. If tire is safe, the inspection is logged as safe.
6. If tire is unsafe or uncertain, the system flags the vehicle.
7. The alert management module sends a visual and optional audio alert to the operator dashboard.
8. Operator reviews the captured image, defect type, confidence score, and vehicle data.
9. Operator acknowledges the alert and directs the vehicle for manual verification if required.
10. All inspection data is stored in the database for history, reports, and auditing.


---

## 6.1 Implementation Decision: Flask-Based Web Application

This implementation will use **Flask as the main web framework** for both backend logic and frontend rendering.

The system will be built as a **Flask monolithic web application**, meaning one Flask project will handle:

- user authentication
- dashboard pages
- image upload
- image preprocessing
- AI model inference
- alert generation
- inspection history
- reports
- admin/user management
- database interaction

The frontend will not be rewritten as a separate React or Vite application. Instead, the UI will be rendered using **Jinja2 HTML templates** inside Flask. This keeps the prototype simpler, easier to demo, and easier to complete for a final year project.

Recommended Flask frontend approach:

```text
Flask routes
    -> Jinja2 templates
        -> Bootstrap 5 styling
        -> Chart.js for reports
        -> small JavaScript/AJAX only where needed
```

This choice is suitable for the current MVP because ATIS needs a working dashboard, upload flow, alerts, and reports more than it needs a complex single-page frontend.


---

## 7. Functional Requirements

### FR-01: User Authentication

**Description:** Allow authorized operators and administrators to log in securely.  
**Inputs:** Username, password.  
**Outputs:** Dashboard access or login error.  
**Workflow:**
1. User enters credentials.
2. System validates credentials against database.
3. System redirects user to the dashboard based on role.

**Acceptance criteria:**
- Passwords must be hashed.
- Invalid login attempts must be rejected.
- Failed login attempts should be logged.
- Role-based access must separate operator and administrator permissions.

---

### FR-02: Capture Tire Image

**Description:** Capture high-resolution tire images as a vehicle passes through the inspection zone.  
**Primary actor:** Camera system.  
**Secondary actor:** Vehicle.  
**Precondition:** Camera is online, calibrated, and positioned correctly.  
**Postcondition:** Tire images are stored or queued for processing.

**Workflow:**
1. Vehicle enters inspection zone.
2. Motion/trigger mechanism detects vehicle presence.
3. Camera captures multiple tire images from configured angles.
4. System attaches timestamp, camera ID, and location metadata.
5. Images are queued for preprocessing.

**Acceptance criteria:**
- Captured image must include visible tire area.
- Images must be saved with unique identifiers.
- Low-quality captures must trigger retry or manual review flag.

---

### FR-03: Preprocess Tire Images

**Description:** Prepare captured images for AI analysis.  
**Primary actor:** Tire Detection System.  
**Input:** Raw tire image.  
**Output:** Processed tire image / ROI ready for classification.

**Workflow:**
1. Retrieve raw tire image from queue.
2. Apply resizing.
3. Apply noise reduction.
4. Adjust contrast and brightness.
5. Extract tire region of interest.
6. Normalize image dimensions for model input.
7. Queue image for classification.

**Acceptance criteria:**
- Preprocessed image must match AI model input shape.
- Unprocessable images must be flagged.
- Preprocessing errors must be logged.

---

### FR-04: Analyze Tire Condition

**Description:** Classify tire condition using a trained deep learning model.  
**Primary actor:** AI inference module.  
**Input:** Preprocessed tire image.  
**Output:** Tire condition, confidence score, defect type.

**Supported classifications:**
- Safe
- Marginal
- Unsafe
- Uncertain / Manual Review

**Supported defect categories:**
- Worn tread
- Sidewall crack
- Sidewall bulge
- Visible surface damage
- Unknown defect

**Workflow:**
1. Load preprocessed image into model.
2. Run model inference.
3. Generate classification result.
4. Calculate confidence score.
5. Detect or assign defect category.
6. Store result in inspection log.

**Acceptance criteria:**
- Inference must complete within the defined latency target.
- Confidence score must be stored with every result.
- Low-confidence predictions must be marked for manual review.

---

### FR-05: Flag Unsafe Vehicle

**Description:** Mark vehicle as unsafe when tire defects are detected.  
**Input:** Unsafe or uncertain classification result.  
**Output:** Flagged vehicle record and alert package.

**Workflow:**
1. System receives unsafe result.
2. System requests or receives vehicle ID from ANPR/toll system if available.
3. System compiles alert data: image, defect type, confidence, timestamp, location, vehicle ID.
4. Vehicle status is updated to `Flagged`.
5. Alert notification process is triggered.

**Acceptance criteria:**
- Vehicle must still be flagged even if ANPR data is unavailable.
- Missing vehicle ID must be stored as `Unknown`.
- Alert package must include enough data for operator review.

---

### FR-06: Send Alert to Operator

**Description:** Notify the operator when an unsafe tire is detected.  
**Primary actor:** Alert management module.  
**Secondary actor:** Highway operator.

**Alert contents:**
- Captured tire image
- Vehicle image, if available
- License plate, if available
- Defect type
- Classification result
- Confidence score
- Timestamp
- Camera/location ID

**Workflow:**
1. System creates alert package.
2. Dashboard receives real-time notification.
3. Alert appears visually on screen.
4. Optional audio alarm plays.
5. Operator reviews and acknowledges alert.
6. System records response time and operator ID.

**Acceptance criteria:**
- Alert must be visible within 1 second after classification.
- Alert must remain pending until acknowledged.
- Acknowledgement must be recorded.
- Unacknowledged alerts should escalate or remain highlighted.

---

### FR-07: View Inspection Dashboard

**Description:** Provide dashboard for real-time monitoring.  
**Primary actor:** Highway operator.

**Dashboard must display:**
- Live camera/inspection feed
- Total inspections
- Safe count
- Unsafe count
- Pending alerts
- Recent inspections
- System status
- Filtering/search controls

**Acceptance criteria:**
- Dashboard must refresh inspection results in real time or near real time.
- Safe/unsafe statuses must use clear visual coding.
- Operator should be able to access current and recent alerts quickly.

---

### FR-08: View Inspection History / Logs

**Description:** Allow operators and admins to search past inspection records.  
**Inputs:** Date range, license plate, status, defect type, camera/location.  
**Output:** Matching inspection records.

**Workflow:**
1. User opens History section.
2. User applies filters.
3. System retrieves records from database.
4. Records are displayed with image thumbnails and status.

**Acceptance criteria:**
- User must be able to filter by date and status.
- Each record must show timestamp, classification, confidence, and image reference.
- Database read failures must show user-friendly error messages.

---

### FR-09: View Inspection Report

**Description:** Display detailed report for a selected inspection.  
**Primary actor:** Highway operator or administrator.

**Report must include:**
- Inspection ID
- Vehicle ID/license plate, if available
- Vehicle type, if available
- Tire image
- Defect highlight/description
- Classification result
- Confidence score
- Timestamp
- Location/camera ID
- Operator action/status

**Acceptance criteria:**
- Report must be printable or downloadable.
- Corrupted/missing records must display an error and be logged.

---

### FR-10: Store Inspection Log

**Description:** Store all inspection results and metadata.  
**Primary actor:** Tire Detection System.

**Stored data:**
- Inspection ID
- Tire/vehicle reference
- Captured image path or binary reference
- Classification
- Defect type
- Confidence score
- Timestamp
- Location
- Camera ID
- Processing duration
- Alert status, if any

**Acceptance criteria:**
- Every processed image must generate a log entry.
- Failed database writes must retry.
- Persistent database failure must store records locally for later sync.

---

### FR-11: Generate Statistical Reports

**Description:** Generate reports for inspection activity and safety trends.  
**Primary actor:** Highway operator / administrator.

**Reports may include:**
- Total inspections by date range
- Safe vs unsafe counts
- Unsafe percentage
- Defect type distribution
- Camera/location-wise trends
- Daily/weekly/monthly summaries

**Acceptance criteria:**
- Reports must support date range selection.
- Reports must be exportable as PDF or Excel.
- If no data exists, system must show `No data available`.

---

### FR-12: Integrate with ANPR / Toll System

**Description:** Associate tire inspection records with vehicle identification data.  
**Primary actor:** Existing highway monitoring system.  
**Secondary actor:** Tire Detection System.

**Workflow:**
1. Tire Detection System sends timestamp and location to ANPR module.
2. ANPR system returns license plate and vehicle type.
3. System validates returned data.
4. Vehicle ID is linked with tire inspection record.
5. Integration status is logged.

**Acceptance criteria:**
- Tire inspection must continue even if ANPR is unavailable.
- System should retry ANPR lookup later if possible.
- ANPR integration failures must not block tire classification.

---

## 8. Non-Functional Requirements

### 8.1 Performance

- Image capture to alert generation must not exceed **3 seconds**.
- Alert display after unsafe classification must not exceed **1 second**.
- System must process at least **10 vehicles per minute** in controlled deployment conditions.

### 8.2 Reliability

- System should recover automatically after crash or power failure.
- Inspection logs must not be corrupted during restart.
- False positives should be minimized to avoid unnecessary traffic disruption.
- False negatives should be minimized to avoid unsafe vehicles passing undetected.

### 8.3 Availability

- Target uptime during operational hours: **99%**.
- Local fallback storage should be available if database connection fails.

### 8.4 Usability

- Operator UI must be simple and readable.
- Use clear status colors:
  - Green = Safe
  - Yellow/Orange = Marginal or Uncertain
  - Red = Unsafe
- A basic operator should learn core actions within **30 minutes** of training.

### 8.5 Security

- System access must require authentication.
- Passwords must be hashed.
- Inspection logs containing license plates or images must be protected against unauthorized access.
- Admin functions must require elevated permission.

### 8.6 Maintainability

- Code must be modular.
- AI model should be replaceable without rewriting the whole application.
- Error logs must help developers diagnose camera, model, database, and dashboard failures.

### 8.7 Portability

- Core detection logic should run on Windows or Linux with minimal changes.
- Python-based detection should support TensorFlow or PyTorch deployment.

### 8.8 Environmental Constraints

Detection accuracy may decrease due to:
- Heavy rain
- Fog
- Night lighting issues
- Dirty camera lens
- Mud-covered tires
- Fast-moving vehicles
- Poor camera angle

---

## 9. Technical Stack

### 9.1 Final Implementation Stack

The selected implementation stack is:

```text
Web Framework:
Flask

Frontend Rendering:
Jinja2 templates

UI Styling:
Bootstrap 5
Custom CSS where needed

Database:
SQLite for local prototype
PostgreSQL optional for final deployment

ORM:
Flask-SQLAlchemy / SQLAlchemy

Authentication:
Flask-Login
Werkzeug password hashing

Image Upload:
Flask file upload handling

Image Processing:
OpenCV
NumPy
Pillow

AI / Deep Learning:
TensorFlow/Keras CNN model
Mock classifier fallback for development

Charts / Reports:
Chart.js
HTML reports first
PDF export later using WeasyPrint or ReportLab

Development Tools:
VS Code
Jupyter Notebook
Git / GitHub
Draw.io for diagrams
```

### 9.2 Programming Languages

- Python
- HTML
- CSS
- JavaScript

JavaScript will be used only for dashboard interactivity, alerts refresh, form helpers, and charts. The main frontend will be server-rendered by Flask/Jinja2, not React.

### 9.3 AI / Deep Learning

- TensorFlow/Keras is recommended for the first implementation.
- PyTorch can be used later if the trained model is built in PyTorch.
- The app must support a mock classifier fallback so the system works even before the real model is trained.

### 9.4 Image Processing

- OpenCV for image loading, resizing, noise reduction, contrast adjustment, and ROI preprocessing.
- NumPy for array operations.
- Pillow for image format handling and preview/export support.

### 9.5 Backend / Frontend Framework

Selected framework:

- **Flask**

Flask will provide:

- HTTP routing
- template rendering
- form handling
- file uploads
- authentication
- dashboard pages
- inspection workflows
- report pages
- database access through SQLAlchemy

FastAPI is not required for the current Flask-based implementation. React/Vite is also not required.

### 9.6 Database

Recommended implementation path:

- **SQLite** for local development and FYP demo.
- **PostgreSQL** only if the project needs a more production-style deployment.

SQLite is enough for the MVP because the prototype mainly needs login, image upload, predictions, alerts, history, and reports. PostgreSQL can be added later without changing the core product logic.

### 9.7 Hardware

- High-resolution IP camera or uploaded tire images for demo.
- GPU-enabled server or workstation if available.
- CPU inference is acceptable for prototype testing with small models.
- Minimum RAM: 16 GB recommended for smoother model loading and image processing.
- SSD storage for faster image buffering and inspection logs.
## 10. System Architecture

### 10.1 Selected Architecture: Flask Monolith

ATIS will be implemented as a **Flask monolithic web application** with modular internal services.

This means the system will have one main Flask application containing separate modules for:

1. Authentication
2. Dashboard
3. Image upload
4. Image preprocessing
5. AI inference
6. Alerts
7. Inspection history
8. Reports
9. Admin/user management
10. Optional ANPR integration

This architecture is simpler than a separated frontend/backend architecture and is better suited for the current academic prototype.

### 10.2 High-Level Components

1. **Vehicle**  
   Passes through inspection zone.

2. **Camera System / Uploaded Image Source**  
   Captures tire images or receives manually uploaded tire images during prototype demo.

3. **Flask Web Application**  
   Main application layer that handles routes, templates, authentication, user actions, and workflow control.

4. **Jinja2 Template Layer**  
   Renders dashboard, alerts, history, reports, login, and inspection pages.

5. **Image Preprocessing Service**  
   Resizes, enhances, filters, and crops tire regions before classification.

6. **AI Classification Service**  
   Uses CNN/deep learning model or mock classifier fallback to classify tire condition.

7. **Decision & Alert Service**  
   Evaluates classification results and creates alerts for unsafe or uncertain tires.

8. **Database Layer**  
   Stores users, vehicles, tire records, inspections, predictions, alerts, and report data using SQLAlchemy.

9. **Operator Interface**  
   Browser-based Flask/Jinja dashboard used by highway operators.

10. **Existing Highway Monitoring Systems**  
   Optional ANPR/toll systems that may provide vehicle identification data.

### 10.3 Component Dependencies

```text
Camera / Uploaded Image
    -> Flask Inspection Route
        -> Image Preprocessing Service
            -> AI Classification Service
                -> Decision & Alert Service
                    -> Database
                    -> Flask/Jinja Operator Dashboard
                        -> Alert Acknowledgement
                            -> Database Update

Optional ANPR / Toll System
    -> ANPR Integration Service
        -> Inspection Record Linking
```

### 10.4 Flask Request Flow

```text
User opens browser page
    -> Flask route receives request
        -> Route calls service layer
            -> Service reads/writes database
            -> Service may call OpenCV or AI model
        -> Flask renders Jinja2 template
            -> Browser displays result
```

### 10.5 Real-Time Alert Strategy

For the MVP, alerts should use simple polling instead of WebSockets.

Recommended approach:

```text
Dashboard page
    -> JavaScript fetches /alerts/partial or /api/alerts/pending every 5 seconds
    -> New unsafe alerts appear on dashboard
    -> Operator acknowledges alert
    -> Flask updates alert status in database
```

WebSockets can be added later, but polling is enough for the prototype and simpler to implement reliably.
## 11. Data Flow

### Level 0 Context Flow

```text
Vehicle
  -> Tire Images
  -> ATIS
  -> Alerts
  -> Highway Operator / Motorway Police

Existing Highway Systems
  -> Vehicle Identification Data
  -> ATIS

ATIS
  -> Inspection Logs
  -> Database
```

### Level 1 Detailed Flow

```text
1. Capture Tire Images
2. Preprocess Images
3. Classify Tire Condition
4. Flag Unsafe Vehicles
5. Notify Operators
6. Store Inspection Logs
7. Generate Reports
```

---

## 12. Database Design

### 12.1 Vehicle Table

| Field | Type | Constraint | Description |
|---|---|---|---|
| vehicle_id | INT | Primary Key | Unique vehicle identifier |
| vehicle_type | VARCHAR(50) | Required | Bus, Truck, Car, etc. |
| license_plate | VARCHAR(20) | Required, Unique | Vehicle plate number |
| owner_name | VARCHAR(100) | Required | Vehicle owner name |

### 12.2 Tire Table

| Field | Type | Constraint | Description |
|---|---|---|---|
| tire_id | INT | Primary Key | Unique tire identifier |
| vehicle_id | INT | Foreign Key | Reference to Vehicle |
| position | VARCHAR(20) | Required | Tire position such as FL, FR, RL, RR |
| installation_date | DATE | Required | Tire installation date |
| mileage | FLOAT | Required | Total mileage on tire |
| last_inspection_date | DATE | Nullable | Last inspection date |

### 12.3 Inspection Table

| Field | Type | Constraint | Description |
|---|---|---|---|
| inspection_id | INT | Primary Key | Unique inspection identifier |
| tire_id | INT | Foreign Key | Reference to Tire |
| inspection_date | DATETIME | Required | Inspection date/time |
| tire_condition | VARCHAR(20) | Required | Safe, Marginal, Unsafe, Uncertain |
| defect_type | VARCHAR(50) | Nullable | Type of defect detected |
| confidence_level | FLOAT | Required | AI confidence percentage |

### 12.4 Alert Table

| Field | Type | Constraint | Description |
|---|---|---|---|
| alert_id | INT | Primary Key | Unique alert identifier |
| inspection_id | INT | Foreign Key | Reference to Inspection |
| operator_id | INT | Foreign Key | Reference to Operator |
| alert_date | DATETIME | Required | Alert generation timestamp |
| status | VARCHAR(20) | Required | Pending, Acknowledged, Resolved |

### 12.5 Operator Table

| Field | Type | Constraint | Description |
|---|---|---|---|
| operator_id | INT | Primary Key | Unique operator identifier |
| name | VARCHAR(100) | Required | Operator name |
| role | VARCHAR(50) | Required | Highway Operator, Motorway Police, Admin |

### 12.6 Recommended Additional Fields

For implementation, add these fields to make the database more practical and traceable:

#### Inspection
- `image_path`
- `camera_id`
- `location_id`
- `processing_duration_ms`
- `model_version`
- `created_at`
- `updated_at`

#### Alert
- `acknowledged_at`
- `resolved_at`
- `resolution_notes`

#### Operator
- `username`
- `password_hash`
- `is_active`
- `last_login_at`

---

## 13. UI Screens

All UI screens will be implemented as **Flask/Jinja2 templates**. Styling should use **Bootstrap 5** with small custom CSS where needed.

### 13.1 Sign In

**Route:** `/login`  
**Template:** `auth/login.html`

Purpose: Authenticate operators and administrators.

Required elements:
- Username field
- Password field
- Login button
- Error message area
- Redirect to dashboard after successful login

### 13.2 Main Layout / Base Template

**Template:** `base.html`

Purpose: Provide shared page structure.

Required elements:
- Sidebar navigation
- Header/top bar
- Logged-in user display
- Logout button
- Flash message area
- Content block for child templates

Menu items:
- Dashboard
- Upload Inspection
- Alerts
- History
- Reports
- Users/Admin, if role allows

### 13.3 Dashboard

**Route:** `/dashboard`  
**Template:** `dashboard/index.html`

Purpose: Real-time or near-real-time monitoring.

Required elements:
- Recent inspections
- Current pending alerts
- Safe/unsafe/marginal counters
- System health indicator
- Latest uploaded/captured tire image
- Alert refresh using simple JavaScript polling

### 13.4 Upload / Capture Inspection

**Route:** `/inspections/upload`  
**Template:** `inspections/upload.html`

Purpose: Upload or capture a tire image and run analysis.

Required elements:
- Image upload field
- Optional license plate field
- Optional vehicle type field
- Image preview
- Analyze button
- Result card after analysis

### 13.5 Alerts

**Route:** `/alerts`  
**Template:** `alerts/index.html`

Purpose: Review and acknowledge unsafe tire alerts.

Required elements:
- Alert list
- Pending alerts first
- Alert priority/status
- Tire image
- Defect type
- Confidence score
- Acknowledge button
- Resolve button

### 13.6 History

**Route:** `/inspections`  
**Template:** `inspections/history.html`

Purpose: Search and view past inspections.

Required filters:
- Date range
- Vehicle plate
- Status
- Defect type
- Location/camera

### 13.7 Inspection Detail / Report

**Route:** `/inspections/<inspection_id>`  
**Template:** `inspections/detail.html`

Purpose: Detailed single-inspection view.

Required elements:
- Inspection metadata
- Vehicle data
- Original tire image
- Preprocessed image, if available
- Classification result
- Defect details
- Confidence score
- Operator action history
- Print/download button placeholder

### 13.8 Reports

**Route:** `/reports`  
**Template:** `reports/index.html`

Purpose: Generate statistical summaries.

Required elements:
- Date range selector
- Safe vs unsafe chart
- Defect distribution chart
- Daily inspection trend chart
- Export PDF placeholder
- Export Excel placeholder

### 13.9 User Management

**Route:** `/admin/users`  
**Template:** `admin/users.html`

Purpose: Manage operator/admin accounts.

Required elements:
- User list
- Create user button
- Edit/deactivate user actions
- Role selection
- Admin-only access control
## 14. User Stories

### Operator Stories

1. As a highway operator, I want to see unsafe tire alerts immediately so that I can stop risky vehicles for manual inspection.
2. As a highway operator, I want to view captured tire images so that I can verify whether the alert is reasonable.
3. As a highway operator, I want to acknowledge alerts so that the system records my response.
4. As a highway operator, I want to search inspection history so that I can review previous vehicle records.
5. As a highway operator, I want to generate reports so that safety trends can be reviewed.

### Admin Stories

1. As an admin, I want to manage operator accounts so that only authorized users access the system.
2. As an admin, I want to monitor camera and model status so that operational problems are detected early.
3. As an admin, I want to update or retrain the AI model so that accuracy improves over time.
4. As an admin, I want to export logs so that audit and evaluation can be performed.

### System Stories

1. As the system, I must classify tire images within 3 seconds so that traffic flow is not delayed.
2. As the system, I must store every inspection result so that records remain auditable.
3. As the system, I must continue inspection even if ANPR data is temporarily unavailable.
4. As the system, I must flag low-confidence results for manual review instead of treating uncertain predictions as final decisions.

---

## 15. Acceptance Criteria Summary

| Area | Criteria |
|---|---|
| Authentication | Only valid users can access dashboard |
| Image Capture | Tire images captured with timestamp and camera metadata |
| Preprocessing | ROI extraction and image normalization completed successfully |
| AI Classification | Tire condition and confidence score generated |
| Alerting | Unsafe tire alert appears within 1 second after classification |
| Logging | Every inspection result saved to database |
| Dashboard | Operator can view live status and recent inspections |
| History | Operator can search/filter past records |
| Reports | System can generate date-based statistical report |
| ANPR | Inspection works even when ANPR is unavailable |
| Performance | End-to-end detection to alert target is under 3 seconds |
| Security | Password authentication and protected inspection logs |

---

## 16. Error Handling

### 16.1 Camera Failure

- Show camera offline status.
- Log failure with timestamp.
- Notify administrator.
- Continue processing from other active cameras if available.

### 16.2 Poor Image Quality

- Retry image capture if possible.
- Mark image as `Unprocessable` if quality remains poor.
- Request manual review.

### 16.3 Low Model Confidence

- Mark result as `Uncertain`.
- Send alert for manual review if safety risk is possible.
- Store confidence score and image for future model improvement.

### 16.4 Database Failure

- Retry write operation.
- Temporarily store record locally.
- Sync once database connection is restored.

### 16.5 ANPR Failure

- Continue tire inspection.
- Store vehicle ID as `Unknown`.
- Retry matching later using timestamp/location.

---

## 17. AI Model Requirements

### 17.1 Model Type

- CNN-based image classification model.
- Framework: TensorFlow/Keras or PyTorch.

### 17.2 Input

- Preprocessed tire ROI image.
- Standardized resolution depending on chosen model architecture.

### 17.3 Output

- Class label: Safe, Marginal, Unsafe, Uncertain.
- Confidence score.
- Optional defect category.

### 17.4 Training Dataset

Dataset should include:
- New/safe tires
- Worn tires
- Cracked tires
- Bulged tires
- Tires with sidewall damage
- Retreaded/used commercial vehicle tires
- Tires under varying lighting and road conditions

### 17.5 Evaluation Metrics

- Accuracy
- Precision
- Recall
- F1 score
- Confusion matrix
- False positive rate
- False negative rate

### 17.6 Safety Preference

False negatives are more dangerous than false positives. The model threshold should prioritize catching unsafe tires, while keeping operator workload reasonable.

---

## 18. Deployment Requirements

### 18.1 Nodes

1. Vehicle inspection lane
2. Camera node
3. AI processing server
4. Database server
5. Operator workstation
6. ANPR/toll integration service

### 18.2 Deployment Considerations

- Camera angle must be calibrated for lane width.
- Camera lens must be kept clean.
- Server should have GPU acceleration for real-time processing.
- Power backup is required for operational continuity.
- Local network should support stable camera-to-server streaming.

---

## 19. Suggested Repository Structure

The implementation should use a Flask application structure with clear separation between routes, models, services, templates, and static files.

```text
atis-flask/
├── app/
│   ├── __init__.py
│   ├── config.py
│   ├── extensions.py
│   │
│   ├── models/
│   │   ├── __init__.py
│   │   ├── user.py
│   │   ├── vehicle.py
│   │   ├── tire.py
│   │   ├── inspection.py
│   │   ├── prediction.py
│   │   └── alert.py
│   │
│   ├── routes/
│   │   ├── __init__.py
│   │   ├── auth_routes.py
│   │   ├── dashboard_routes.py
│   │   ├── inspection_routes.py
│   │   ├── alert_routes.py
│   │   ├── report_routes.py
│   │   ├── admin_routes.py
│   │   └── api_routes.py
│   │
│   ├── services/
│   │   ├── __init__.py
│   │   ├── preprocessing_service.py
│   │   ├── classifier_service.py
│   │   ├── mock_classifier.py
│   │   ├── alert_service.py
│   │   ├── report_service.py
│   │   └── anpr_service.py
│   │
│   ├── templates/
│   │   ├── base.html
│   │   ├── auth/
│   │   │   └── login.html
│   │   ├── dashboard/
│   │   │   └── index.html
│   │   ├── inspections/
│   │   │   ├── upload.html
│   │   │   ├── history.html
│   │   │   └── detail.html
│   │   ├── alerts/
│   │   │   └── index.html
│   │   ├── reports/
│   │   │   └── index.html
│   │   └── admin/
│   │       └── users.html
│   │
│   ├── static/
│   │   ├── css/
│   │   │   └── main.css
│   │   ├── js/
│   │   │   ├── dashboard.js
│   │   │   ├── alerts.js
│   │   │   └── charts.js
│   │   └── uploads/
│   │       ├── original/
│   │       └── processed/
│   │
│   └── utils/
│       ├── file_utils.py
│       ├── security.py
│       └── validators.py
│
├── ai_model/
│   ├── models/
│   │   └── tire_model.h5
│   ├── notebooks/
│   └── training/
│
├── migrations/
├── tests/
├── docs/
│   ├── diagrams/
│   └── user_manual.md
├── instance/
│   └── atis.sqlite
├── scripts/
│   ├── create_admin.py
│   └── seed_data.py
├── requirements.txt
├── run.py
├── README.md
└── PROD.md
```

### 19.1 Important Structure Rules

- Keep Flask routes thin.
- Put business logic in `services/`.
- Put database schema in `models/`.
- Put reusable helpers in `utils/`.
- Put AI code in `services/` and `ai_model/`, not inside templates.
- Store uploaded images under `app/static/uploads/` for simple prototype access.
- Use `instance/` for local SQLite database and private runtime files.
## 20. Flask Route Suggestions

Since the project will use Flask with Jinja templates, most user-facing functionality should be normal web routes, not a separate REST API.

### 20.1 Authentication Routes

```http
GET  /login
POST /login
GET  /logout
GET  /profile
```

### 20.2 Dashboard Routes

```http
GET /dashboard
GET /dashboard/summary
```

`/dashboard/summary` may return partial JSON for dashboard counters if JavaScript refresh is used.

### 20.3 Inspection Routes

```http
GET  /inspections
GET  /inspections/upload
POST /inspections/upload
POST /inspections/<inspection_id>/analyze
GET  /inspections/<inspection_id>
GET  /inspections/<inspection_id>/print
```

### 20.4 Alert Routes

```http
GET  /alerts
POST /alerts/<alert_id>/acknowledge
POST /alerts/<alert_id>/resolve
GET  /alerts/pending
```

`/alerts/pending` may return JSON for polling pending alerts on the dashboard.

### 20.5 Report Routes

```http
GET  /reports
POST /reports/generate
GET  /reports/export/pdf
GET  /reports/export/excel
```

### 20.6 Admin/User Routes

```http
GET  /admin/users
GET  /admin/users/create
POST /admin/users/create
GET  /admin/users/<user_id>/edit
POST /admin/users/<user_id>/edit
POST /admin/users/<user_id>/deactivate
```

### 20.7 Optional JSON Routes

These routes can be used for AJAX updates without turning the whole app into a separate API project:

```http
GET /api/alerts/pending
GET /api/reports/summary
GET /api/reports/defects
GET /api/reports/daily-trends
GET /api/system/status
```

### 20.8 Optional ANPR Integration Routes

```http
POST /integrations/anpr/match
GET  /integrations/anpr/status
```

ANPR integration remains optional for the MVP. The tire inspection flow must still work when ANPR is unavailable.
## 21. Testing Plan

### 21.1 Unit Tests

- Authentication validation
- Image preprocessing functions
- Model inference wrapper
- Database CRUD operations
- Alert creation logic
- Report generation functions

### 21.2 Integration Tests

- Camera capture to preprocessing
- Preprocessing to AI inference
- AI result to alert generation
- Alert to dashboard display
- Inspection logging to report generation
- ANPR lookup fallback

### 21.3 System Tests

- Process sample vehicle images end to end.
- Generate safe and unsafe results.
- Confirm alert timing.
- Confirm database entries.
- Confirm dashboard updates.

### 21.4 User Acceptance Tests

- Operator logs in successfully.
- Operator views live dashboard.
- Operator receives unsafe tire alert.
- Operator acknowledges alert.
- Operator views history.
- Operator generates report.

---

## 22. Risks and Mitigations

| Risk | Impact | Mitigation |
|---|---|---|
| Poor lighting | Lower model accuracy | Add controlled lighting or IR camera in future |
| Dirty tire/camera lens | Poor image quality | Add maintenance routine and image quality checks |
| Weak dataset | Poor classification | Collect local tire images and retrain model |
| High false positives | Traffic disruption | Tune threshold and add marginal/manual review class |
| High false negatives | Unsafe vehicles pass | Prioritize recall for unsafe class |
| ANPR unavailable | Missing vehicle ID | Continue inspection and store vehicle as Unknown |
| Database downtime | Lost logs | Local fallback queue with sync |
| Hardware underpowered | Slow inference | Use GPU-enabled server |

---

## 23. Future Enhancements

1. Infrared/night-vision tire inspection.
2. Full ANPR integration.
3. Automated challan workflow after human verification.
4. Mobile app for field officers.
5. Cloud dashboard for multiple highway checkpoints.
6. Real-time model retraining pipeline.
7. Sidewall text reading for tire age and specifications.
8. Integration with national vehicle fitness databases.
9. Multi-camera inspection for full tire coverage.
10. Thermal imaging for overheating tire detection.

---

## 24. Open Questions

1. Final project name must be confirmed: `Drive IQ Intelligent Car Maintenance` or `Automated Tire Detection and Inspection System`.
2. Final database for demo should be confirmed: SQLite is recommended, PostgreSQL is optional.
3. Final deep learning framework should be confirmed: TensorFlow/Keras is recommended for this Flask implementation.
4. Target camera specifications are not finalized.
5. Required model accuracy threshold is not specified.
6. Whether classification should be binary (`Safe/Unsafe`) or three-class (`Safe/Marginal/Unsafe`) must be finalized.
7. ANPR integration is described but not fully specified and should remain optional for MVP.
8. Appendix bot/NLP sections conflict with the tire detection system and should be removed from final documentation.
9. Whether the demo will use live camera capture or manual image upload must be confirmed. Manual upload is recommended first because it is more reliable during presentation.

---

## 25. MVP Definition

The minimum viable prototype should include:

1. Flask login page using Flask-Login.
2. Flask/Jinja dashboard page.
3. Tire image upload page.
4. Image preprocessing pipeline using OpenCV.
5. Mock classifier fallback.
6. TensorFlow/Keras model loader when model file is available.
7. AI inference for tire safety classification.
8. Unsafe or uncertain tire alert generation.
9. Inspection log database using SQLite.
10. Inspection history page with filters.
11. Inspection detail/report page.
12. Basic reports page with Chart.js.
13. Default admin user script.
14. Demo dataset and test images.
15. README with local run instructions.

A successful MVP proves that ATIS can classify tire images, alert operators, and store inspection logs through a working Flask web application.

### 25.1 Recommended MVP Build Order

```text
1. Create Flask app factory and project structure
2. Add config, database, and extensions
3. Create SQLAlchemy models
4. Add authentication
5. Add base template and dashboard layout
6. Add image upload flow
7. Add preprocessing service
8. Add mock classifier
9. Add analysis workflow
10. Add alert creation and acknowledgement
11. Add inspection history and detail pages
12. Add reports page
13. Add real model loader
14. Add seed data and admin script
15. Test full flow from login to report
```
