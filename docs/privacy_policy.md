# ATIS Privacy Notice (template)

> **Status: template.** This is a starting draft for the NHA's legal/data-
> protection function to review and adopt. Bracketed `[…]` values must be filled
> in before publication. It reflects what the ATIS software actually does; do not
> publish claims the deployment does not implement.

## Who processes your data

The Automated Tyre Inspection System (ATIS) is operated by
**[National Highway Authority / operating entity]** ("we"), the data controller.
Contact the data protection point of contact at **[email / postal address]**.

## What we collect

When a vehicle passes an ATIS-equipped checkpoint, or an operator uploads an
image, we may process:

- an **image of the tyre / vehicle**, which can include the **licence plate** and
  surroundings;
- the **licence plate number**, read automatically or entered by an operator;
- **inspection results** (safe/unsafe verdict, model confidence, defects,
  location, camera, timestamp);
- for system users, an **account email and role**, and technical **audit logs**
  including **IP address** and browser user-agent.

## Why we process it (purpose and lawful basis)

- To assess tyre roadworthiness and highway safety at checkpoints —
  **[lawful basis: public task / legal obligation — confirm with legal]**.
- To secure and audit the system (access logs) —
  **[lawful basis: legitimate interest / legal obligation]**.

Automated verdicts are **[decision-support only and reviewed by an operator /
…]** — state clearly whether any enforcement decision is made solely by the
system. ATIS supports human review of flagged inspections.

## How long we keep it

Inspection records and images are retained for **[ATIS_RETENTION_DAYS →
period]**; security audit logs for **[ATIS_AUDIT_RETENTION_DAYS → period]**.
After that they are automatically deleted. (See `docs/data_governance.md`.)

## Who we share it with

**[List processors: hosting provider, object-storage provider, error-tracking
(Sentry) if enabled, and any authority the data is shared with.]** We do not sell
personal data.

## Your rights

Subject to applicable law **[cite the relevant statute, e.g. Pakistan's Personal
Data Protection framework]**, you may request **access** to, or **erasure** of,
the data we hold about a vehicle you are responsible for. We can produce a full
record for a plate and erase it on request (see `docs/data_governance.md`).
Contact **[email]**. You may also complain to **[supervisory authority]**.

## Security

Access requires authentication and is role-restricted; passwords are stored
hashed; transport is encrypted **[confirm HTTPS/TLS termination]**; access is
audited. Images can be stored in encrypted object storage.

## Changes

We will update this notice as the system changes. Last reviewed: **[date]**.
