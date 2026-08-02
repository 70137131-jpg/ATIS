# ATIS Data Governance

This document is the operational contract for the personal data ATIS holds: what
it is, how long it is kept, how it is backed up, and how a data-subject access or
erasure request is answered. The tooling described here is implemented — it is
not aspirational.

## 1. Personal-data inventory

| Data | Where | Personal data? | Notes |
|------|-------|----------------|-------|
| Licence plate | `inspections.plate`, `inspections.plate_raw_text` | **Yes** | Identifies a vehicle/keeper. |
| Tyre / vehicle image | `inspections.image_data` (DB) or S3 object | **Yes** | May capture plate, surroundings, people. |
| Request IP address | `audit_events.ip_address` | **Yes** | Identifies the operator's network. |
| User agent | `audit_events.user_agent` | Indirect | Device fingerprinting risk. |
| Operator account | `users.email` | **Yes** | Staff identity. |
| Inspection metadata | status, confidence, location, camera, timestamps | Contextual | Personal only in combination with the plate/image. |

Related rows that reference an inspection (`inspection_defects`, `alerts`,
`alert_comments`) are removed with it, so erasing an inspection leaves no
orphaned personal data.

## 2. Retention policy

Retention is **configuration, not code** — set the windows per the legal basis
agreed with the NHA. It is **off by default (0 = keep forever)** because
silently deleting highway-safety records is itself a risk; a deployment must
consciously choose a window.

| Variable | Controls | Suggested starting point |
|----------|----------|--------------------------|
| `ATIS_RETENTION_DAYS` | Inspections (plates + images) | Set to the agreed evidentiary period. |
| `ATIS_AUDIT_RETENTION_DAYS` | Audit events (IP addresses) | Often longer than inspections for security forensics. |

Apply the policy with the purge command (dry run by default):

```bash
# Preview what would be removed
flask --app app atis-purge-expired

# Actually delete
flask --app app atis-purge-expired --apply
```

Schedule it from cron (or a platform scheduled job), e.g. nightly:

```cron
30 2 * * * cd /app && flask --app app atis-purge-expired --apply >> /var/log/atis-purge.log 2>&1
```

The purge deletes each expired inspection's S3 image object (DB-stored bytes go
with the row) plus its alerts/comments/defects, then audit events past their own
window. See `services/retention.py`.

## 3. Data-subject requests

**Access** — export every record held for a plate:

```bash
flask --app app atis-export-plate --plate ABC-1234 > abc-1234.json
```

**Erasure** — remove every inspection/image/alert for a plate (dry run first):

```bash
flask --app app atis-erase-plate --plate ABC-1234            # preview
flask --app app atis-erase-plate --plate ABC-1234 --apply    # commit
```

Both are case-insensitive on the plate. Erasure is irreversible once `--apply`
is passed — take a backup first (section 4).

## 4. Backups and restore

Backups are only real once a restore has been rehearsed. Two scripts implement
both halves for SQLite and PostgreSQL, driven by the same `DATABASE_URL` the app
uses.

```bash
# Back up (writes a timestamped, compressed dump to ./backups by default)
./scripts/backup_db.sh /var/backups/atis

# Restore — refuses to run without an explicit confirmation env var
ATIS_RESTORE_CONFIRM=yes ./scripts/restore_db.sh \
    /var/backups/atis/atis-pg-20260802T023000Z.dump \
    postgresql://user:pass@staging:5432/atis_scratch
```

**Required before go-live (DEPLOY.md checklist):**
1. Schedule `backup_db.sh` (hourly or daily per RPO).
2. **Rehearse a restore into a scratch database at least once** and confirm the
   app boots and the row counts match. Record the date rehearsed.
3. Store backups off the app host (object storage / managed-DB snapshots).

## 5. Responsibilities

| Role | Responsibility |
|------|----------------|
| Data controller (NHA) | Sets retention periods and lawful basis; owns subject requests. |
| Deployer/operator | Configures the env vars, schedules purge + backup, rehearses restore. |
| Engineering | Maintains the tooling and the personal-data inventory above. |

See also `docs/privacy_policy.md` (subject-facing notice) and `docs/DPIA.md`
(risk assessment).
