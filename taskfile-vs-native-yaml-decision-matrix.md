# Decision: CI/CD Approach for the Classic Pipeline Migration

| Item | Value |
|---|---|
| Status | Draft for team vote |
| Scope | Pipelines across the organisation: Classic to ADO YAML now, GitHub Actions later |
| Decision owner | DevOps Guild with Architecture |
| Decision method | Team vote (section 4) |

## 1. The Concerns

1. **Native task support.** Taskfile runs commands. It cannot call ADO tasks
   such as `AzureResourceManagerTemplateDeployment@3` or `CopyFiles@2`, or
   marketplace extensions.
2. **Long-term maintenance.** A shared Taskfile library is code the DevOps
   Guild must test, version, document and support for every consuming team.
   Native tasks are maintained by Microsoft or the extension vendor.
3. **App-team authoring experience.** With native YAML, a team finds the task
   in the docs, copies the snippet and sets inputs. With Taskfile, a team must
   vendor the library, learn which namespaces and variables to use, read the
   library docs or use the migration skill, then write both an application
   Taskfile and the wrapper YAML.

| Authoring step | Native YAML | Taskfile (hybrid) |
|---|---|---|
| Find a capability | Microsoft docs, ADO task assistant, GitHub Marketplace | Library README, `task --list`, migration skill |
| Use it | Copy snippet, set inputs | Vendor/pin library, include namespaces, set vars, reference the Taskfile from the wrapper |
| Debug | Per-task log in the CI UI | Wrapper step log; reproducible locally with `task` |
| Get help | Microsoft docs, community answers | DevOps Guild |

The question is: **which approach migrates Classic pipelines to YAML now with
the least effort and risk, while keeping the later move to GitHub Actions
largely automated?**

## 2. Options

| Option | Strengths | Trade-offs |
|---|---|---|
| A. Native ADO YAML | Familiar to app teams (copy a documented snippet); full native and marketplace task support; tasks maintained by Microsoft/vendors; GitHub Actions Importer converts it later | The GitHub move is a second, mostly automated conversion with a known list of manual steps |
| B. Taskfile-first | CI-agnostic logic; runs locally; GitHub move changes only the wrapper | Cannot use native tasks; shared library to build, test and support; steeper learning curve for app teams |
| C. Hybrid (native + Taskfile) | Native tasks for platform integration, Taskfile for logic | Two models for teams to learn and the Guild to support; library maintenance remains |

Dagger was excluded earlier because it requires containers and changes to the Windows agent estate (see `eval.md`).

## 3. Proposed Direction: Option A

The DevOps Guild migrates Classic pipelines to native ADO YAML, keeping the
later GitHub Actions move in mind so GitHub Actions Importer can convert them
with minor changes.

- App teams keep a familiar model: find the task in the docs, copy the snippet, set inputs.
- Native and marketplace tasks are used as-is, without reimplementation.
- There is no shared Taskfile library to build, test and support.

Accepted trade-off: the GitHub move is a second, mostly automated conversion
rather than a zero-change switch. Section 5 lists what it leaves for manual work.

## 4. Team Vote

1. Read sections 1, 2, 3 and 5.
2. Vote for one option. Record your main reason and any blocking concern.
3. A blocking concern (for example security, compliance or a pattern that cannot be converted) must be resolved before the decision is final, whatever the majority.
4. The decision owner breaks ties.

Before the vote, run `gh actions-importer audit azure-devops` so the team can
see how much of the estate converts automatically.

| Team member | Vote (A/B/C) | Main reason | Blocking concern (if any) |
|---|---|---|---|
| | | | |

## 5. Considerations That Affect the Decision

| Consideration | Why it matters |
|---|---|
| Importer manual work | [Per GitHub](https://docs.github.com/en/actions/migrating-to-github-actions/using-github-actions-importer-to-automate-migrations/migrating-from-azure-devops-with-github-actions-importer), secrets, service connections, unknown tasks, self-hosted agents, environments and approvals are migrated manually; gates and schedules are unsupported. This is the real cost of option A's second step |
| Marketplace/custom extensions | They become unknown steps in the Importer. One custom transformer per task type avoids fixing each pipeline by hand |
| Existing Taskfile work | The Taskfile library, migration skill and pilot templates were built for options B and C. Choosing A means retiring them or keeping their scripts as plain script files |
| Deployment groups (on-prem VMs, Telehouse) | Classic releases that deploy to on-prem VMs use ADO Deployment Groups: an ADO agent on each target machine. In YAML they become environments with VM resources, but GitHub has no equivalent and the Importer cannot convert them. These need self-hosted runners on the targets or a redesign under every option |
| OpenShift / Argo CD roadmap | Once workloads are containerised, deployment moves to GitOps, which reduces the value of any deployment tooling chosen now |

## Decision Record

| Date | Votes (A / B / C) | Selected option | Blocking concerns resolved | Approvers |
|---|---|---|---|---|
| | | | | |
