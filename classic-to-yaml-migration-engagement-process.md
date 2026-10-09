# Classic → YAML Pipeline Migration: Team Engagement & Process

> **Page info**
> | | |
> |---|---|
> | **Owner** | DevOps Guild |
> | **Status** | DRAFT – for review |
> | **Scope** | Engaging application teams to migrate ~3,650 Azure DevOps classic build & release pipelines to YAML |
> | **Related** | Classic → YAML Pipeline Migration: What Good Looks Like |
> | **Last updated** | 2026-10-09 |

---

## 1. TL;DR

- The **DevOps Guild is responsible for migrating** classic pipelines to YAML. Teams are consulted, review and approve, but are not expected to do the migration work.
- Teams who can't engage when the Guild schedules them can opt into **self-service** and migrate at their own pace using the same templates, tooling and guidance, by an agreed target date.
- After cut-over, **teams own their YAML pipeline** and their release process; the DevOps Guild owns the central templates.
- Each team's existing controls (approvals, gates, release windows) are **mapped into Azure DevOps Environment checks**, not thrown away.
- Every migration follows the same **8-step process**: Discover → Kick-off → Assess → Migrate → Validate → Cut over → Decommission → Handover.

---

## 2. Engagement models

The default is **Guild-led**. Self-service is an opt-in for teams who can't engage on the Guild's schedule.

| Model | When to use | DevOps Guild does | Team does |
|---|---|---|---|
| **Guild-led** (default) | All teams, in the order set by the migration plan | Inventory, assessment, YAML generation, PR, Environments & service connections, technical validation, cut-over support, decommission | Confirms owners, provides process knowledge (approvers, gates, windows), reviews & approves PR, **validates the app in lower environments**, approves prod cut-over |
| **Self-service** (opt-in) | Team is busy when the Guild schedules them, or prefers to migrate on its own timeline | Provides templates, converter, docs, office hours; reviews the PR against the "good pipeline" checklist; decommissions classic | Migrates at its own pace by an **agreed target date**, following the same process and checklist |

**Self-service rules**

- The team agrees a **target date** with the Guild at kick-off; it's tracked like any other migration.
- Same templates, same checklist, same process. No custom pipelines outside the org template.
- The Guild reviews the PR before cut-over to confirm it meets the "good pipeline" checklist.
- If the target date is missed, the pipeline moves back to the **Guild-led** queue.
- Teams can switch from self-service to Guild-led at any time.

---

## 3. Per-team migration process

```mermaid
flowchart LR
  A[1. Discover] --> B[2. Kick-off]
  B --> C[3. Assess & map]
  C --> D[4. Migrate]
  D --> E[5. Validate]
  E --> F[6. Cut over]
  F --> G[7. Decommission]
  G --> H[8. Handover]
```

> If the Confluence Mermaid macro isn't available, paste the diagram into a draw.io/Gliffy page.

The steps are the same for both models; in **self-service** the team performs steps 3–6 and the Guild reviews.

| # | Step | What happens (Guild-led) | Output | Exit criteria |
|---|---|---|---|---|
| 1 | **Discover** | Guild pulls the team's pipelines from the org-wide inventory scan (created / last modified / build vs release) | Team pipeline list | Owner confirmed for every pipeline |
| 2 | **Kick-off** | Short session: why we're migrating, what "good" looks like, what the Guild needs from the team; team chooses Guild-led or self-service | Agreed model, contacts (and target date if self-service) | Team contact named |
| 3 | **Assess & map** | Guild reviews each pipeline with the team: classify as **retire / consolidate / migrate**; map the team's process into the YAML model (Section 4) | Team migration sheet | All pipelines classified; process mapping signed off by team |
| 4 | **Migrate** | Guild generates YAML (converter + org template), raises the PR in the team repo, creates Environments and WIF service connections | PR per application | PR approved by team |
| 5 | **Validate** | **5a. Guild (technical):** runs the YAML pipeline in non-prod alongside classic; compares artifacts, deployment results, config/variables and timings, then hands over to the team.<br/>**5b. App team (functional):** validates the deployed app in lower environments – smoke/regression tests, key user journeys, config and integrations, approvals and gates behave as expected | Validation notes (Guild + team) | Guild confirms technical parity **and** app team signs off functional validation |
| 6 | **Cut over** | First production deployment through YAML in a window agreed with the team; Guild runs it, team approves | Production deployment record | Healthy production release |
| 7 | **Decommission** | Guild disables classic for the agreed rollback window → exports definition JSON to archive → deletes | Archive entry | Classic pipeline deleted |
| 8 | **Handover** | Team takes ownership of the YAML; short retro captures gaps in templates or process | Feedback logged to DevOps Guild backlog | Team confirms ownership |

---

## 4. Preserving each team's process

Teams' biggest concern is losing their existing controls. Every classic control has an equivalent in YAML:

| Classic control | YAML equivalent |
|---|---|
| Pre/post-deployment approvers | **Environment approvals** (same people / groups) |
| Release gates (Azure Monitor, REST API, work item query) | **Environment checks** – Azure Monitor alerts, Invoke REST API, Query Work Items |
| Deployment windows / change freeze | **Business hours** check on the Environment |
| Manual intervention | Environment approval, or `ManualValidation@1` where genuinely needed |
| Variable groups / secrets | Key Vault–linked variable groups, scoped per environment |
| Task groups | Central template steps |
| Scheduled releases | `schedules:` in YAML (**converted to UTC**) |
| Change management (e.g. ServiceNow) | ServiceNow change management check on the Environment |

Anything that genuinely does not fit is logged as a **time-boxed exception** and fed into the template backlog. Templates are **not forked per team**.

---

## 5. Sequencing across teams

1. **Inventory** – scan all orgs/projects, group pipelines by team, confirm owners.
2. **Retire first** – unused or orphaned pipelines are disabled and archived with owner confirmation.
3. **Pilot teams** – Guild migrates 2–3 teams covering the common patterns (.NET web app, Bicep, a complex release) to harden the templates and this process.
4. **Batch the rest** – Guild works through teams ordered by template fit and team availability, easiest first; complex or regulated teams once templates are proven. Self-service teams run in parallel against their target dates.
5. **Lock down** – once most teams are migrated, disable classic pipeline creation and switch the required-template check from audit to blocking.

---

## 6. Communication & support

| Channel | Purpose |
|---|---|
| **Launch announcement** (from engineering leadership) | Why we're doing this, that the Guild will migrate pipelines, what's needed from teams, and the self-service option |
| **Confluence hub** | What good looks like, this process, how-to guides, FAQ, examples |
| **Team contacts** | One named contact per team for scheduling, process knowledge and approvals |
| **Office hours** (recurring) | Live help, especially for self-service teams |
| **Teams/Slack channel** | Async questions, announcements, sharing tips |
| **Recorded walkthrough** | One real migration shown end-to-end, from discovery to decommission (key resource for self-service) |

---

## 7. Tracking

**Work items**

- One **Epic per team**, one **work item per pipeline**.
- States: `Discovered → Assessed → Migrating → Validating → Cut over → Decommissioned`, plus `Retired` and `Exception`.

**Dashboard**

- Pipelines remaining per team, per state and per model (Guild-led / self-service).
- Self-service target dates and overdue items.
- Built from the inventory scan plus work item data.
- Regular progress update to leadership: progress, blockers, open exceptions.

---

## 8. Roles & responsibilities

| Activity | DevOps Guild | Application team (Guild-led) | Application team (self-service) |
|---|---|---|---|
| Templates, tooling, guidance | **Owns** | Consulted | Consulted |
| Inventory & classification | **Leads** | Confirms owners | Confirms owners |
| Process mapping | **Leads** | Provides input, signs off | **Leads**, Guild consulted |
| YAML pull request | **Raises** | Reviews & approves | **Raises**, Guild reviews |
| Environments, approvals, checks | **Sets up** | Provides approvers & gates | **Sets up** using the pattern |
| Technical validation (lower env) | **Executes** | Informed | **Executes**, Guild reviews |
| Functional validation (lower env) | Supports | **Executes & signs off** | **Executes & signs off** |
| Prod cut-over | **Executes** | Approves | **Executes**, Guild supports |
| Decommission classic | **Executes** | Approves | Approves |
| YAML pipeline after handover | Owns templates | **Owns** pipeline | **Owns** pipeline |
| Exceptions | **Approves**, time-boxes | Requests | Requests |

---

## 9. Common pitfalls

| Pitfall | Mitigation |
|---|---|
| Classic and YAML running in parallel too long (double maintenance) | Agree the rollback window up front; disable classic straight after first healthy prod deploy |
| Per-team template forks reintroduce drift | Extend central templates via parameters / backlog instead |
| Release approvals and gates overlooked | Explicit process-mapping step with team sign-off (Step 3) |
| Schedule time-zone change (classic = org local time, YAML = UTC) | Included in the "good pipeline" checklist for every migration |
| Pipelines with no clear owner | Routed to the retire path, not the migrate path |
| Self-service teams stall | Agreed target date; overdue items move back to the Guild-led queue |
| Teams unavailable to approve cut-over | Book cut-over windows at kick-off; named backup approver per team |
| Functional validation becomes a bottleneck | Agree the team's validation slot and test scope at kick-off; Guild provides a short validation checklist |

---

## 10. Next steps

- [ ] Run the org-wide inventory scan and share results with team leads to confirm owners
- [ ] Agree with engineering leadership that the DevOps Guild leads the migration, with self-service as an opt-in
- [ ] Pick 2–3 pilot teams and name a contact in each
- [ ] Publish the Confluence hub (What good looks like + this page + FAQ)
- [ ] Run pilots end-to-end and refine templates and process before scaling
