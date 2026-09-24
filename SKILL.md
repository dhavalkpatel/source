---
name: ado-classic-taskfile-migration
description: "Use when migrating an Azure DevOps Classic build or release pipeline to Azure DevOps YAML with yamlConvert, Taskfile, and a shared pipeline-templates repository. Discovers the converter, template library, and target application repository; exports and analyses the Classic definition; maps it to reusable ADO templates and Taskfile capabilities; creates or improves missing reusable templates with tests; implements and validates the application migration. Trigger phrases: migrate Classic pipeline, Classic to YAML, yamlConvert, Taskfile migration, Azure DevOps pipeline migration."
argument-hint: "Provide the application repository and Classic pipeline name, ID, or URL."
user-invocable: true
---

# Azure DevOps Classic-to-Taskfile Migration

## Purpose

Migrate one Azure DevOps Classic build or release pipeline to maintainable Azure DevOps YAML. Treat `yamlConvert` as the source-definition acquisition and first-pass conversion tool, and `pipeline-templates` as the governed source of reusable ADO templates and Taskfile capabilities.

The goal is behavioural parity with the Classic pipeline while reducing duplication. Do not translate every Classic task literally when an existing template or Taskfile capability already expresses the same intent. The migrated application `Taskfile.yml` is the platform-agnostic composition layer: thin Azure DevOps YAML invokes intent-level application tasks, and those application tasks invoke the selected reusable Taskfile capabilities. The same Taskfile contract must be callable from GitHub Actions later without changing application build, test, package, infrastructure, or deployment logic.

## Expected Workspace Roles

This skill works in a multi-root workspace. Do not assume folder paths from a screenshot or require repositories to be named exactly as below.

| Role | Identify by | Responsibility |
|---|---|---|
| `yamlConvert` | Converter README/configuration plus conversion scripts or engine | Fetches/exports Classic definitions and produces an initial YAML representation |
| `pipeline-templates` | ADO template folders, Taskfile library, examples, and tests | Owns reusable templates, Taskfile capabilities, template tests, and release/versioning conventions |
| Application repository | Application source, infrastructure, scripts, and the pipeline being migrated | Owns application-specific Taskfile orchestration, configuration, and migrated pipeline entrypoint |

If more than one repository matches a role, inspect its README and configuration. Ask the user only if the correct target remains ambiguous.

## Required Target Architecture

The migration must use this layering unless the target has a documented, approved exception:

```text
Azure DevOps pipeline entrypoint
				|
				| ADO-only: triggers, pools, variable groups, environments,
				| service connections, approvals, artifact wiring
				v
Shared thin ADO template from pipeline-templates
				|
				| checks out/obtains the Taskfile library, installs Task if needed,
				| injects approved environment values, invokes app task targets
				v
Application Taskfile.yml
				|
				| platform-agnostic composition: ci, package, deploy, verify
				| selects reusable capabilities and app-specific extension points
				v
Shared Taskfile templates from pipeline-templates/taskfile-library
				|
				| reusable build, test, scan, package, IaC, deploy capabilities
				v
Application scripts, source, IaC, and deployment configuration
```

### Responsibility Boundaries

| Layer | Owns | Must not own |
|---|---|---|
| Application ADO YAML | ADO triggers, repository resources, pool, variable groups, environments, approvals, service connections, and selection of a shared ADO entry template | Build commands, deployment commands, inline business scripts, or duplicated Taskfile logic |
| Shared ADO template | ADO bootstrap: checkout, Task installation, shared-library availability, approved environment injection, and calling application task targets | Technology-specific build/deploy implementation or application naming/business rules |
| Application `Taskfile.yml` | Platform-agnostic orchestration and selection of the application's reusable capabilities; thin wrappers for genuinely application-specific behaviour | ADO-only concepts such as service connections, approvals, pipeline variables, or secret values |
| Shared Taskfile library | Reusable implementation capabilities and their contracts | App-specific paths, resource names, business rules, or secrets |

The public application Taskfile contract should be stable and CI-platform-neutral, for example `task ci`, `task package`, `task deploy`, and `task verify`. Azure DevOps invokes those commands today; a GitHub workflow can invoke the same commands later without changing Taskfile logic. Taskfiles must use platform-neutral CLI and script behaviour; CI-platform-specific logging commands, task types, and secret syntax stay outside the Taskfile.

## Required Migration Output and Library Consumption

The migration output is Taskfile-backed. The converter's default inline Azure DevOps YAML is an intermediate analysis artefact, not a completed migration.

Run `yamlConvert` with its dual-output mode so it produces both:

1. A consumer-owned application `Taskfile.yml` containing application orchestration and genuinely application-specific tasks.
2. A thin Azure DevOps wrapper YAML that invokes the exact application Taskfile path and its public task targets.

Use the converter's documented command. Where `batch_migrate.py` and these options are available, the required invocation is equivalent to:

```bash
python batch_migrate.py \
	--excel axaiuk.xlsx \
	--output <migration-output> \
	--output-format both \
	--taskfile-library-source vendored \
	--taskfile-library-root .platform
```

Verify the converter's `--help` output before invoking it. Preserve the required semantics if the installed converter uses different option names.

### Application Taskfile Location and Exact Invocation

The consumer-owned `Taskfile.yml` may live at the application repository root or in the application's existing pipeline/build directory. The wrapper must pass its exact repository-relative path to the shared ADO template; it must never rely on Taskfile auto-discovery.

```yaml
# Application repository: azure-pipelines.yml
extends:
	template: ado-templates/taskfile-application.yml@pipelineTemplates
	parameters:
		taskfilePath: build/Taskfile.yml  # Exact path generated or chosen for this application
		ciTask: ci
		deployTask: deploy
		environment: nonprod
```

The shared ADO template invokes the explicit path, for example:

```text
task --taskfile build/Taskfile.yml ci
```

Its future GitHub Actions equivalent invokes the same path and target:

```text
task --taskfile build/Taskfile.yml ci
```

### Taskfile Library Consumption Modes

Choose one supported mode per application and record it in the migration inventory.

| Mode | Use when | Required behaviour |
|---|---|---|
| Vendored | Default for migrated applications and local developer use | Vendor the selected Taskfile capabilities and every required dependency from `pipeline-templates/taskfile-library/` under `.platform/`. Pin the source to an immutable release tag or commit and record the resolved version/commit. If the application includes the library root manifest, vendor all files that manifest includes. |
| Runtime consumption | The repository is approved to obtain the library during its build | The shared ADO/GitHub wrapper downloads or checks out the library into a controlled location before invoking the application Taskfile. Authenticate through a secret-backed source, service connection, or federated identity; pin an immutable tag/commit or use an approved channel; never embed credentials in YAML, Taskfiles, commands, or repository URLs. Record the resolved release tag and commit in build telemetry/logs. |

For both modes, the application Taskfile selects only the capabilities it needs. Its library path must be supplied through a non-secret variable such as `TASKFILE_LIBRARY_DIR`, with a safe default for vendored consumption. This allows the same application Taskfile to work locally, in Azure DevOps, and later in GitHub Actions.

### Required Composition Pattern

The exact library path and include syntax must follow `pipeline-templates` conventions. The resulting structure must be equivalent to this example:

```yaml
# Application repository: Taskfile.yml
version: '3'

vars:
	TASKFILE_LIBRARY_DIR: '{{.TASKFILE_LIBRARY_DIR | default ".platform"}}'

includes:
	dotnet:
		taskfile: '{{.TASKFILE_LIBRARY_DIR}}/build/dotnet.yml'
	dotnet-test:
		taskfile: '{{.TASKFILE_LIBRARY_DIR}}/test/dotnet.yml'
	sast:
		taskfile: '{{.TASKFILE_LIBRARY_DIR}}/security/sast.yml'
	bicep:
		taskfile: '{{.TASKFILE_LIBRARY_DIR}}/infra/bicep.yml'
	appservice:
		taskfile: '{{.TASKFILE_LIBRARY_DIR}}/deploy/azure-appservice.yml'

tasks:
	ci:
		cmds:
			- task: dotnet:build
			- task: dotnet-test:test
			- task: sast:sast
	deploy:
		cmds:
			- task: bicep:deploy
			- task: appservice:deploy
```

Only include capabilities needed by the application. For example, a Python Function should select Python build/test and Function deployment templates, not inherit .NET or App Service steps. `TASKFILE_LIBRARY_DIR` represents the controlled library checkout or installation location established by the shared ADO template; it must not contain a hard-coded developer-machine path.

The ADO pipeline should only select the shared entry template and application task targets, for example:

```yaml
# Application repository: azure-pipelines.yml
resources:
	repositories:
		- repository: pipelineTemplates
			type: git
			name: DevOpsGuild/pipeline-templates
			ref: refs/tags/v1.0.0

extends:
	template: ado-templates/taskfile-application.yml@pipelineTemplates
	parameters:
		taskfilePath: Taskfile.yml
		ciTask: ci
		deployTask: deploy
		environment: nonprod
```

Use the repository's supported channel/tag and template path rather than inventing these literal values. A PR/CI entry template must invoke only `ciTask`; deployment must be a separately gated template/stage that invokes `deployTask`.

## Guardrails

- Never modify, disable, or delete the Classic pipeline as part of migration work.
- Never copy secret values from Classic variables, variable groups, service connections, or logs into YAML, Taskfiles, source control, or migration notes.
- Keep approvals, environments, service connections, variable groups, triggers, agent pools, and secret binding in Azure DevOps YAML or project configuration; do not move them into Taskfiles.
- Keep CI and deployment separate. A pull-request validation must not deploy or receive production credentials.
- The application `Taskfile.yml` is the platform-agnostic composition boundary. Do not put build/test/deploy commands directly in ADO YAML when a Taskfile capability can own them.
- The shared ADO template must invoke application task targets such as `task ci` and `task deploy`; it must not choose an application's technology stack or invoke technology-specific Taskfiles directly.
- Do not treat a converter-generated inline ADO YAML pipeline as the completed migration; require `--output-format both` and preserve the consumer-owned Taskfile as the implementation layer.
- Never put repository credentials, access tokens, PATs, or signed download URLs in source control, Taskfiles, ADO YAML, command arguments, or logs. Use a secret-backed authenticated source or federated identity for runtime library consumption.
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

Use `yamlConvert` to export the exact Classic definition and run its dual-output conversion (`--output-format both`). Treat its output as input for analysis, not as production-ready YAML. Confirm that the result contains a consumer-owned Taskfile and an ADO wrapper before proceeding.

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

Search `pipeline-templates` before writing application YAML. Read the most relevant thin ADO entry template, Taskfile namespace, example application, and its neighbouring tests. Map the Classic workflow first to application task targets (`ci`, `package`, `deploy`, `verify`), then map each target to specific reusable Taskfile capabilities.

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

Create or update the application pipeline using the supported composition pattern from `pipeline-templates`. Use the existing template interface rather than reproducing its logic in the application YAML. The ADO template must call the application's intent-level Taskfile targets using the explicit generated/configured `taskfilePath`; it must not call `dotnet`, `bicep`, PowerShell scripts, or individual shared technology tasks directly.

Create or update an application `Taskfile.yml` only for application orchestration and genuinely app-specific tasks. It should:

- include the shared Taskfile library using the library's documented mechanism
- use a `TASKFILE_LIBRARY_DIR`-style non-secret input so vendored and runtime consumption resolve the same selected capabilities
- pass only approved, non-secret application inputs
- invoke supported namespaces/tasks rather than duplicating build, test, scan, package, or deployment commands
- set the correct working directory for application source and IaC operations
- keep deployment-specific configuration separate from CI

The resulting ADO YAML should remain thin and own only ADO concerns: triggers, repository resources, agent pool, template selection, variable groups, environments, service connections, approvals, and artifact wiring. The Taskfile library checkout/installation and `task <application-target>` invocation belong in the shared ADO template.

For every Classic inventory row, mark one of the following outcomes: `reused`, `shared capability added`, `shared capability improved`, `application-specific`, `manual gate retained`, or `out of scope`. No row may disappear without an explicit reason.

### 6. Validate Before Cutover

Validate in this order, using the repository's actual commands and tooling:

1. Run the focused test added for every shared-library change.
2. Run the relevant `pipeline-templates` test suite and lint/parse checks.
3. Validate the explicit Taskfile path and task graph, then run safe dry-run/summary commands where supported. Do not rely on Taskfile auto-discovery.
4. Validate ADO YAML/template expansion using the supported local validator, ADO API, or a non-production pipeline.
5. Run CI against the application in a non-production context.
6. For deployments, run Bicep `what-if` or equivalent plan first, then deploy only to the approved non-production environment.
7. Verify artifacts, test results, security gates, deployment outputs, and a post-deployment health check against the migration inventory.

If a validation result differs from Classic behaviour, determine whether it is an intentional improvement or a regression. Document the decision and keep the Classic pipeline as rollback until the application owner accepts the migrated pipeline.

## Definition of Done

A migration is complete only when:

- the exact Classic definition was fetched through `yamlConvert` or its documented equivalent
- `yamlConvert` produced both a consumer-owned application Taskfile and a thin ADO wrapper, rather than an inline-YAML-only result
- every Classic task/phase has a recorded mapping and validation outcome
- shared behaviour is reused from, or safely added to, `pipeline-templates`
- shared-library additions or improvements have passing focused tests
- application-specific logic is isolated to the application repository
- the ADO wrapper invokes the exact application Taskfile path, and that Taskfile can consume the selected library capabilities through the recorded vendored or runtime mode
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