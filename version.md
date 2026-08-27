Enterprise Taskfile Versioning & Platform Telemetry
Version: 2.0 Owner: DevOps Guild (library and release process) / Platform Engineering (observability infrastructure and ADO governance settings)

Overview
This document defines the enterprise strategy for:
* Versioning the shared Taskfile Platform Library
* Consuming platform capabilities with zero app-team versioning burden
* Platform telemetry reporting
* Version compliance dashboard
* Governance and upgrade process
The goal is a governed, observable, and scalable CI/CD platform where application teams consume standardised capabilities by referencing a channel tag — no manual pinning, no vendoring, no version awareness required from app teams.

Why Version the Platform Library?
Without versioning:
* Applications copy Taskfiles and scripts
* Bug fixes require updating hundreds of repositories
* Security fixes cannot be enforced consistently
* Platform capabilities drift over time
Instead, applications consume a released Platform Library similar to how GitHub Actions are consumed:
# GitHub Actions reference
- uses: actions/checkout@v4

# Equivalent: Platform Library channel reference
ref: refs/tags/stable

Applications depend on a channel that always resolves to a validated release. The resolved version is self-reported by the library on every pipeline run via telemetry.

Ownership
Asset	Owner	Notes
platform-taskfile-library repo	DevOps Guild	Taskfile logic, templates, CHANGELOG, VERSION file
Channel tag promotion (stable, v1-stable)	DevOps Guild	Controlled via promotion pipeline, not manual git push
ADO Required Templates setting	Platform Engineering / ADO Admin	One-time project-level configuration
Log Analytics workspace and Workbook	Platform Engineering	Observability infrastructure
Application pipeline file	Application Team	Written once at onboarding, not touched for routine releases
Application-specific variables	Application Team	APP_NAME, RESOURCE_GROUP, environment targets
Versioning Strategy
Semantic Versioning applies to the library repo.
Version	Meaning	Example
Major	Breaking changes — task renamed, parameter removed	v2.0.0
Minor	Backward-compatible capability added	v1.5.0
Patch	Bug fix or security update	v1.4.1
Immutable version tags are created on every release and never moved:
v1.0.0  v1.1.0  v1.2.0  v1.2.1  v2.0.0


Consumption Model: Channel Tags
Rather than requiring app teams to pin a version number, the DevOps Guild maintains channel tags — mutable git tags that always point to the latest validated release within a channel.
Channel Tag	Points To	Consumer
stable	Latest validated release	Most application teams
v1-stable	Latest within v1.x	Teams not yet migrated to v2
lts	Long-term support releases only	Regulated or change-controlled workloads
How ADO Resolves a Channel Tag
When an application pipeline runs, ADO resolves refs/tags/stable to the commit SHA it currently points to — at pipeline queue time, not at YAML authoring time. Moving the stable tag is all that is required to deliver a new release to all downstream consumers. No app repo is touched.
Application Pipeline (Written Once at Onboarding)
# app-repo/azure-pipeline.yml — complete file; app team never edits this for routine releases
resources:
  repositories:
    - repository: platform
      type: git
      name: DevOpsGuild/platform-taskfile-library
      ref: refs/tags/stable        # subscribes to the stable channel

extends:
  template: templates/azure-pipelines-thin.yml@platform
  parameters:
    environment: Production

Application Taskfile (Optional App-Specific Extension)
Application teams that need to add steps beyond the platform defaults compose from the platform namespace. Telemetry is already wired into task ci and task cd inside the library — app teams must not duplicate it.
version: '3'

includes:
  platform:
    taskfile: .platform/taskfile.yml   # resolved from the channel tag at run time

vars:
  APP_NAME: claims-api
  RESOURCE_GROUP: claims-rg-prod

tasks:
  ci:
    cmds:
      - task: platform:ci             # build + test + sast + telemetry all included
  cd:
    cmds:
      - task: platform:cd             # infra + deploy + telemetry all included


Versioning Strategy Comparison: Channel Tags vs Separate VERSION Repository
Two approaches exist for communicating the current platform version to consumers. The right choice depends on what problem is being solved.
Approach A — Channel Tags (Recommended)
The channel tag in the library repo IS the version reference. refs/tags/stable resolves to the validated commit; the VERSION file inside that commit is the self-reported version number.
platform-taskfile-library/
  VERSION        ← "1.4.0" — self-identification of the library at this commit
  CHANGELOG.md
  Taskfile.yml
  ...

git tag stable  → points to the v1.4.0 commit

How it works end to end:
App pipeline references refs/tags/stable
        ↓
ADO resolves stable → SHA of v1.4.0 commit
        ↓
Library checked out at v1.4.0
        ↓
task ci runs; telemetry:report reads VERSION → "1.4.0"
        ↓
{ "platformVersion": "1.4.0" } emitted to Log Analytics

Property	Behaviour
App team version awareness	None required
Extra infrastructure	None
Version discovery for consumers	None needed — channel handles it
Rollback	Move stable tag back — takes seconds, no app repo changes
Audit trail	Git tag history; immutable version tags preserve full history
ADO/GitHub native	Yes — resources.repositories.ref resolves tags natively
Network dependency at run time	None beyond normal repo checkout
Approach B — Separate VERSION Repository
A dedicated repository (e.g., platform-version-registry) contains a file such as channels/stable.txt holding 1.4.0. App pipelines query this registry at startup to determine the current version, then compare against their locally pinned version.
platform-version-registry/
  channels/
    stable.txt      ← "1.4.0"
    v1-stable.txt   ← "1.4.0"
    lts.txt         ← "1.2.1"

How it works end to end:
App pipeline starts
        ↓
Checkout platform-version-registry
        ↓
Read channels/stable.txt → "1.4.0"
        ↓
Compare against locally vendored .platform/VERSION → "1.3.0"
        ↓
Version mismatch — warn or fail
        ↓
App team must manually update their vendored .platform/ to 1.4.0

Property	Behaviour
App team version awareness	Still required for upgrades — must re-vendor
Extra infrastructure	Additional repository, access policies, maintenance
Version discovery for consumers	Explicit — app team queries registry
Rollback	Update registry file + re-deploy consumers manually
Audit trail	Two repos to correlate (library + registry)
ADO/GitHub native	No — requires an extra checkout or API call step
Network dependency at run time	Yes — registry checkout must succeed
Decision
Criteria	Channel Tags	Separate VERSION Repo
App team effort at onboarding	Write one pipeline file	Write pipeline file + vendor library + pin VERSION
App team effort per release	Zero	Re-vendor on every release
Rollback speed	Seconds (move tag)	Minutes to hours (update registry + re-vendor affected repos)
Infrastructure to maintain	None	Additional repo + access policies
Version self-identification	VERSION file in library commit	stable.txt in registry repo
Works for 200+ repos	Yes — scales linearly, zero per-repo work	No — requires touching every repo that needs the update
The separate VERSION repository solves the discovery problem but does not solve the consumption problem. App teams still need to manually re-vendor and update their pinned version after every release. At 200+ repositories this is operationally unscalable.
Channel tags solve both discovery and consumption in a single mechanism native to ADO and GitHub.
The VERSION file remains in the library repo as a self-identification artefact read by the telemetry task at run time. It is not the consumption mechanism.

Shared Platform Taskfile — Telemetry Implementation
The telemetry task is owned by the DevOps Guild and lives in telemetry/telemetry.yml. Two implementation rules apply:
Rule 1 — Read VERSION inside cmds:, not as a top-level vars: sh:
Task evaluates top-level vars eagerly for every included file during initialisation. Under a multi-hop include chain (app → .platform/taskfile.yml → telemetry/telemetry.yml), TASKFILE_DIR during that eager pass resolves to the entrypoint directory, not this file's directory. The cat VERSION call fails for every task in the library, not just telemetry. Reading inside cmds: uses the correct lazy per-task context.
Rule 2 — Use Task's built-in dateInZone instead of shelling out to date
Self-hosted Windows agents do not guarantee date -u availability without Git for Windows on PATH. Task's template functions require no shell process and behave identically on Windows, Linux, and macOS.
Correct implementation:
# telemetry/telemetry.yml
version: '3'

vars:
  TIMESTAMP: '{{dateInZone "2006-01-02T15:04:05Z" now "UTC"}}'  # built-in, Windows-safe

tasks:
  report:
    desc: Report platform telemetry
    # No dir: override — must resolve VERSION relative to this file, not the caller.
    cmds:
      - |
        set -euo pipefail
        PLATFORM_VERSION=$(cat "{{.TASKFILE_DIR}}/../VERSION")
        echo '{
          "repository":"'$BUILD_REPOSITORY_NAME'",
          "project":"'$SYSTEM_TEAMPROJECT'",
          "branch":"'$BUILD_SOURCEBRANCHNAME'",
          "environment":"'$ENVIRONMENT'",
          "buildId":"'$BUILD_BUILDID'",
          "pipeline":"'$BUILD_DEFINITIONNAME'",
          "platformVersion":"'"$PLATFORM_VERSION"'",
          "timestamp":"{{.TIMESTAMP}}"
        }'

telemetry:report is invoked at the end of both task ci and task cd inside the root Taskfile.yml. Application Taskfiles must not call it directly — it fires automatically.

Telemetry Payload
{
  "repository": "ClaimsAPI",
  "project": "Insurance",
  "branch": "main",
  "environment": "Production",
  "pipeline": "CI",
  "buildId": "8421",
  "platformVersion": "1.4.0",
  "timestamp": "2026-08-27T09:42:16Z"
}

The payload is sent to an Azure Monitor HTTP Data Collector endpoint configured via the TELEMETRY_ENDPOINT variable in the ADO Variable Group. Application teams do not configure this — it is injected by the platform template.

Azure DevOps Pipeline
The application's complete pipeline file:
resources:
  repositories:
    - repository: platform
      type: git
      name: DevOpsGuild/platform-taskfile-library
      ref: refs/tags/stable

extends:
  template: templates/azure-pipelines-thin.yml@platform
  parameters:
    environment: Production

Everything else — agent selection, variable groups, task ci, task cd, telemetry — is provided by the platform template. Application teams do not write script: task ci directly.

Telemetry Architecture
Azure DevOps Pipeline
        │
        ▼
Taskfile (resolved from refs/tags/stable)
        │
        ▼
telemetry:report — reads VERSION, emits JSON payload
        │
        ▼
Azure Monitor HTTP Data Collector API
        │
        ▼
Log Analytics — PlatformTelemetry_CL
        │
        ▼
Azure Workbook / Power BI

Log Analytics Table
Custom table: PlatformTelemetry_CL
Repository	Branch	Environment	Platform Version	Timestamp
ClaimsAPI	main	Prod	1.4.0	2026-08-27
BillingAPI	develop	QA	1.3.0	2026-08-27
PolicyAPI	main	Prod	1.4.0	2026-08-27
Dashboard
Executive Summary
Repositories                 285
Current Version              251
Upgrade Available             28
Unsupported                    6
Adoption Rate               88%

Version Distribution
v1.4.0  █████████████████████  251
v1.3.0  ████                    28
v1.2.0  █                        6

Repository Compliance
Repository	Platform Version	Latest	Status
ClaimsAPI	1.4.0	1.4.0	✅ Current
BillingAPI	1.3.0	1.4.0	⚠ Upgrade Available
PolicyAPI	1.2.0	1.4.0	❌ Unsupported
Team Adoption
Team	Current	Upgrade	Unsupported
Claims	18	1	0
Billing	12	3	1
Policy	9	0	0
Upgrade Trend
January   40%
February  58%
March     72%
April     88%

With channel tags, "Upgrade Available" rows appear only for teams on v1-stable or lts channels that have not yet opted into a newer channel — not for teams on stable, which self-updates automatically.

Version Governance
Support Policy
Status	Channel	Pipeline Behaviour
Current	On stable resolving to latest	✅ Continues
Upgrade Available	On v1-stable, newer minor exists	⚠ Warning in pipeline log
Deprecated	On v1-stable, v1 deprecation announced	⚠ Warning + Teams notification
Blocked	On an end-of-life channel	❌ Pipeline fails at template load
End-of-Life Enforcement
When a channel is retired, the platform template emits a blocking error before any task runs. App teams see:
Error: Platform Library channel v1-stable is end of life.
Migrate to refs/tags/stable (v2.x) — see migration guide at [wiki link].

This is enforced inside templates/azure-pipelines-thin.yml via a version check step, not via the Taskfile. No app repo change is required to enforce it — the template is updated centrally.

Release Lifecycle (DevOps Guild)
Four mandatory stages. stable is never moved manually — only by the promotion pipeline after all gates pass.
Stage 1: Merge to main
        │  Automated: library unit tests, lint
        ▼
Stage 2: Tag immutable version
        │  git tag v1.5.0  (never moves — audit trail)
        ▼
Stage 3: Pilot validation  ← MANUAL APPROVAL GATE
        │  Run 3–5 representative app pipelines against v1.5.0 explicitly
        │  (resources.ref: refs/tags/v1.5.0)
        ▼
Stage 4: Promote channel tag  ← MANUAL APPROVAL GATE
        │  git tag -f stable v1.5.0
        │  git push --force origin stable
        ▼
        All app pipelines pick up v1.5.0 on next run automatically

Rollback (bad release reaches stable):
git tag -f stable v1.4.0        # point back to last known-good
git push --force origin stable  # all pipelines self-heal on next run

Rollback does not require touching any application repository.

Major Version Migration (Breaking Changes)
When v2 introduces breaking changes, stable is NOT moved immediately:
stable    → v1.4.0   (unchanged — existing pipelines unaffected)
v2-stable → v2.0.0   (new channel — opt-in)

DevOps Guild publishes migration notes. App teams change one line when ready:
# Before
ref: refs/tags/stable     # was tracking v1

# After
ref: refs/tags/v2-stable  # now tracking v2

When adoption of v2 reaches an agreed threshold (e.g., 90%), stable is moved to v2 and v1-stable enters a deprecation window with a defined end-of-life date.

Future Platform Telemetry
The telemetry model is designed to evolve without requiring changes to application repositories. The only evolving component is the shared Platform Library.
Category	Examples
Platform	Library Version, Taskfile Version, Channel
Repository	Repository, Branch, Team, Business Unit
Pipeline	Build Duration, Build Status, Stage
Runtime	Windows / Linux, Agent Pool, Runner Type
Security	SAST Tool Version, Dependency Scan Status, SBOM Generated
Deployment	Environment, Region, Deployment Duration
CI Platform	Azure DevOps, GitHub Actions
This enables Platform Engineering to build a centralised operational dashboard for governance, adoption tracking, migration progress, and CI/CD health — with zero changes required in application repositories as new fields are added.
