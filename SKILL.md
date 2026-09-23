---
name: ado-classic-taskfile-migration
description: "Use when migrating an Azure DevOps Classic build or release pipeline to Azure DevOps YAML with yamlConvert, Taskfile, and a shared pipeline-templates repository. Discovers the converter, template library, and target application repository; exports and analyses the Classic definition; maps it to reusable ADO templates and Taskfile capabilities; creates or improves missing reusable templates with tests; implements and validates the application migration. Trigger phrases: migrate Classic pipeline, Classic to YAML, yamlConvert, Taskfile migration, Azure DevOps pipeline migration."
argument-hint: "Provide the application repository and Classic pipeline name, ID, or URL."
user-invocable: true
---

# Azure DevOps Classic-to-Taskfile Migration

## Purpose

Migrate one Azure DevOps Classic build or release pipeline to maintainable Azure DevOps YAML. Treat `yamlConvert` as the source-definition acquisition and first-pass conversion tool, and `pipeline-templates` as the governed source of reusable ADO templates and Taskfile capabilities.

The goal is behavioural parity with the Classic pipeline while reducing duplication. Do not translate every Classic task literally when an existing template or Taskfile capability already expresses the same intent.

## Expected Workspace Roles

This skill works in a multi-root workspace. Do not assume folder paths from a screenshot or require repositories to be named exactly as below.

| Role | Identify by | Responsibility |
|---|---|---|
| `yamlConvert` | Converter README/configuration plus conversion scripts or engine | Fetches/exports Classic definitions and produces an initial YAML representation |
| `pipeline-templates` | ADO template folders, Taskfile library, examples, and tests | Owns reusable templates, Taskfile capabilities, template tests, and release/versioning conventions |
| Application repository | Application source, infrastructure, scripts, and the pipeline being migrated | Owns application-specific Taskfile orchestration, configuration, and migrated pipeline entrypoint |

If more than one repository matches a role, inspect its README and configuration. Ask the user only if the correct target remains ambiguous.

## Guardrails

- Never modify, disable, or delete the Classic pipeline as part of migration work.
- Never copy secret values from Classic variables, variable groups, service connections, or logs into YAML, Taskfiles, source control, or migration notes.
- Keep approvals, environments, service connections, variable groups, triggers, agent pools, and secret binding in Azure DevOps YAML or project configuration; do not move them into Taskfiles.
- Keep CI and deployment separate. A pull-request validation must not deploy or receive production credentials.
- Preserve existing user changes. Inspect relevant files before editing and avoid unrelated refactors.
- Use existing patterns in `pipeline-templates` before introducing a new structure.
- A missing generic capability belongs in `pipeline-templates`; a one-application behaviour belongs in the application repository.

## Workflow

### 1. Discover the Tooling and Target

1. Locate the three workspace roles above.
2. Read the relevant READMEs, converter configuration, template-library entrypoints, examples, and test commands.
3. Identify the application repository and the exact Classic pipeline using a pipeline name, ID, URL, or application configuration.
4. Confirm whether the target is a build pipeline, release pipeline, or both. Migrate them separately if they have different lifecycle/security boundaries.
5. Record the existing application pipeline files and determine whether the repository already has a Taskfile, YAML pipeline, or local automation.

Do not use generic Azure DevOps REST or CLI calls if `yamlConvert` already provides a supported fetch/export mechanism. Use the converter's documented authentication flow and keep credentials outside tracked files.

### 2. Fetch and Characterise the Classic Pipeline

Use `yamlConvert` to export the exact Classic definition and its first-pass conversion. Treat its output as input for analysis, not as production-ready YAML.

Build a migration inventory before implementing anything:

| Classic element | Purpose | CI or CD | Inputs / secrets | Outputs / artifacts | Target mapping | Validation |
|---|---|---|---|---|---|---|
| Task, script, or phase | Why it exists | CI / CD | Variables, service connection, files | Artifact, deployment, side effect | Existing capability / improve / create / app-specific | Test or smoke check |

Capture at least:

- triggers, branch filters, schedules, path filters, and PR behaviour
- agent pool, operating system, tool installers, and demands
- build, test, quality, security, package, artifact, and release steps
- inline PowerShell/Bash, script files, working directories, and parameters
- artifact names, paths, publish/download relationships, and retention assumptions
- variable groups, secret variables, service connections, environments, approvals, checks, and manual interventions
- stages, dependencies, conditions, retries, continue-on-error behaviour, and failure gates
- deployment targets, Bicep/ARM inputs, rollback steps, and post-deploy health checks

Flag every task that relies on a deprecated extension, hidden variable, external share, agent-local path, or undocumented manual step. Do not silently omit it.

### 3. Inspect and Map Available Templates

Search `pipeline-templates` before writing application YAML. Read the most relevant ADO template, Taskfile namespace, example application, and its neighbouring tests.

Classify each inventory row using this decision table:

| Finding | Action |
|---|---|
| Existing template/task has the required behaviour | Configure and reuse it |
| Existing capability is close but lacks a safe parameter, platform, or behaviour | Add a focused improvement to the shared library |
| Capability is broadly reusable across applications | Add a new shared ADO template and/or Taskfile namespace |
| Behaviour is unique to this application | Keep a thin app-owned Taskfile task or script; invoke shared capabilities around it |
| Requirement cannot be safely automated | Preserve it as an explicit ADO approval/manual validation and explain why |

Do not create a new template solely because the Classic pipeline has a unique name. Generalise only the stable delivery capability; leave application data, naming, and business-specific scripts in the app repository.

### 4. Apply TDD to Library Changes

When the migration exposes a missing or deficient shared capability, work in this order:

1. Find the template repository's existing test convention and add a failing contract test or fixture first.
2. The test must assert externally visible behaviour, such as generated YAML structure, required parameters, task ordering, artifact contract, working directory, or fail-fast validation.
3. Implement the smallest reusable Taskfile or ADO-template change that passes the test.
4. Run the focused test, then the template-library test suite.
5. Update examples and public documentation only when the reusable interface changes.

Useful migration contracts include:

- a .NET/App Service profile restores, builds, tests, scans, and publishes the expected artifact
- a Function profile does not invoke App Service deployment logic
- a PR/CI pipeline cannot invoke CD tasks or access deployment credentials
- a task that operates on app files uses the application working directory, not the installed library directory
- a missing required deployment parameter fails with a clear message before any side effect
- a failing test/security task prevents package or deployment stages

For application-specific migration logic, add the narrowest practical test: Pester for PowerShell, unit tests for scripts, Taskfile dry-run/summary checks, or a non-production smoke test.

### 5. Implement the Application Migration

Create or update the application pipeline using the supported composition pattern from `pipeline-templates`. Use the existing template interface rather than reproducing its logic in the application YAML.

Create or update an application `Taskfile.yml` only for application orchestration and genuinely app-specific tasks. It should:

- include the shared Taskfile library using the library's documented mechanism
- pass only approved, non-secret application inputs
- invoke supported namespaces/tasks rather than duplicating build, test, scan, package, or deployment commands
- set the correct working directory for application source and IaC operations
- keep deployment-specific configuration separate from CI

The resulting ADO YAML should remain thin and own only ADO concerns: triggers, repository resources, agent pool, template selection, variable groups, environments, service connections, approvals, and artifact wiring.

For every Classic inventory row, mark one of the following outcomes: `reused`, `shared capability added`, `shared capability improved`, `application-specific`, `manual gate retained`, or `out of scope`. No row may disappear without an explicit reason.

### 6. Validate Before Cutover

Validate in this order, using the repository's actual commands and tooling:

1. Run the focused test added for every shared-library change.
2. Run the relevant `pipeline-templates` test suite and lint/parse checks.
3. Validate Taskfile discovery and task graph, then run safe dry-run/summary commands where supported.
4. Validate ADO YAML/template expansion using the supported local validator, ADO API, or a non-production pipeline.
5. Run CI against the application in a non-production context.
6. For deployments, run Bicep `what-if` or equivalent plan first, then deploy only to the approved non-production environment.
7. Verify artifacts, test results, security gates, deployment outputs, and a post-deployment health check against the migration inventory.

If a validation result differs from Classic behaviour, determine whether it is an intentional improvement or a regression. Document the decision and keep the Classic pipeline as rollback until the application owner accepts the migrated pipeline.

## Definition of Done

A migration is complete only when:

- the exact Classic definition was fetched through `yamlConvert` or its documented equivalent
- every Classic task/phase has a recorded mapping and validation outcome
- shared behaviour is reused from, or safely added to, `pipeline-templates`
- shared-library additions or improvements have passing focused tests
- application-specific logic is isolated to the application repository
- the YAML pipeline passes template validation and succeeds in non-production
- CI/CD separation, secrets, approvals, and service connections remain governed by ADO
- the final handoff states assumptions, retained manual gates, unsupported/deferred items, rollback path, and evidence from validation

## Final Response Format

Report:

1. The Classic pipeline fetched and its identity.
2. The templates and Taskfile capabilities selected.
3. Shared templates/tasks created or improved, including tests run.
4. Application files created or changed.
5. Behaviour intentionally changed from Classic, if any.
6. Validation results, remaining manual gates, and cutover/rollback recommendation.