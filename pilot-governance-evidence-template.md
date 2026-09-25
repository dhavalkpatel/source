# Pilot Governance Evidence

Keep this document short. Link to immutable Azure DevOps pipeline runs and
artifacts; do not copy logs, screenshots, credentials, or secret values here.

## Scope

| Item | Value |
|---|---|
| Application / team | |
| Classic pipeline name and ID | |
| Migrated YAML pipeline | |
| Application Taskfile path and targets | |
| Shared library version and commit | |
| Pilot run URL | |
| Owner / review date | |

## Control Evidence

| Control | Result | Evidence link |
|---|---|---|
| Secrets are external; no secrets committed | Pass / Fail / N/A | |
| Least-privilege identity and approved service connection | Pass / Fail / N/A | |
| Build, tests, and required scans pass | Pass / Fail / N/A | |
| Failing test or scan blocks downstream packaging/deployment | Pass / Fail / N/A | |
| Artifact name, version, and checksum are recorded | Pass / Fail / N/A | |
| IaC validation / what-if passes, if applicable | Pass / Fail / N/A | |
| Non-production deployment, approval, and smoke test pass, if applicable | Pass / Fail / N/A | |
| Rollback is documented or tested, if applicable | Pass / Fail / N/A | |
| Run, deployment history, and platform telemetry are available | Pass / Fail / N/A | |

## Classic Mapping and Exceptions

| Classic task or phase | New Taskfile target / ADO concern | Outcome | Evidence or exception ID |
|---|---|---|---|
| | | Reused / Shared capability / App-specific / Manual gate / Out of scope | |

## Decision

- [ ] All mandatory controls pass.
- [ ] Exceptions are approved, time-bound, and have an owner.
- [ ] The Classic pipeline remains available for rollback until acceptance.

| Role | Name | Approval / date |
|---|---|---|
| Application owner | | |
| DevOps Guild / template owner | | |
| Platform governance | | |