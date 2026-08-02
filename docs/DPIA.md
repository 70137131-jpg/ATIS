# ATIS Data Protection Impact Assessment (DPIA)

> **Status: working draft** for the NHA's data-protection function to complete
> and sign. A DPIA is appropriate because ATIS involves systematic monitoring of
> a public space, automated processing that informs decisions about vehicles, and
> images that can identify people. Fill the `[…]` fields and record sign-off.

## 1. Description of the processing

- **What:** ATIS captures/receives tyre-and-vehicle images at highway
  checkpoints, reads the licence plate (automatically or by operator entry),
  runs a YOLOv11 classifier that labels each tyre `safe` or `unsafe`, stores the
  inspection, and raises alerts for unsafe tyres. Operators review flagged cases.
- **Data:** licence plates, tyre/vehicle images, inspection metadata, operator
  accounts, and audit logs (IP, user-agent). See `docs/data_governance.md §1`.
- **Scale / scope:** **[expected vehicles/day, number of checkpoints, retention
  period]**.
- **Data subjects:** vehicle keepers/drivers passing checkpoints; system
  operators.

## 2. Necessity and proportionality

- **Purpose:** highway safety — detecting unroadworthy tyres.
- **Lawful basis:** **[public task / legal obligation — confirm with legal]**.
- **Necessity:** the plate links a verdict to a vehicle for follow-up; the image
  is the evidence and the model input. Assess whether the plate must be stored in
  clear or could be hashed/truncated for records that are not acted on.
- **Data minimisation:** retention windows age data out (`ATIS_RETENTION_DAYS`);
  images can be stored only as long as needed; consider not persisting images for
  `safe` verdicts if the workflow allows.

## 3. Risks and mitigations

| Risk | Likelihood / impact | Mitigation (implemented) | Residual action |
|------|---------------------|--------------------------|-----------------|
| **False negative** — cracked tyre passed as safe | Med / **High (safety)** | Asymmetric fail-safe threshold; low-confidence `normal` sent to review; live missed-defect monitoring (`atis-model-monitor`) | **Field-validate before enforcing verdicts** (`docs/model_governance.md`) |
| Indefinite retention of plates/images | High / Med | Configurable retention + scheduled purge | Controller must set the windows |
| Unauthorised access to images/plates | Med / High | Auth + RBAC, hashed passwords, audited access, non-root container | Add security headers, session revocation (roadmap) |
| Re-identification from images (bystanders) | Med / Med | Access controls; retention limits | Consider cropping to the tyre ROI |
| Data loss | Med / High | Backup + rehearsed restore scripts | Schedule + rehearse (checklist) |
| Function creep (ANPR used for tracking) | Med / High | Purpose limited to tyre safety; audit log | Governance/policy control by controller |
| Model bias across vehicle types/conditions | Med / Med | Documented limitations; review workflow | Field validation across conditions |

## 4. Individuals' rights

Access and erasure are supported per-plate (`atis-export-plate` /
`atis-erase-plate`). Transparency is provided via `docs/privacy_policy.md`.
**[Describe how subjects are informed at the checkpoint — signage, notice.]**

## 5. Consultation and sign-off

- Data Protection Officer / advisor: **[name, date]**
- System owner (NHA): **[name, date]**
- Engineering lead: **[name, date]**
- Review date: **[recur, e.g. annually or on major change]**

## 6. Outcome

**[Approved / Approved with conditions / Not approved.]** Conditions:
**[e.g. "verdicts remain advisory until field validation is signed off"].**
