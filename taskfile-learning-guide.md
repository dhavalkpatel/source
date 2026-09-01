# Taskfile Learning Guide

A structured reference for Task (go-task), based on the official guide at https://taskfile.dev/docs/guide. Examples use .NET build/restore commands (no Docker/containers — matches our current setup). Use this alongside the existing taskfile-ADO/ examples in this repo.

A Taskfile.yml is like a recipe book. Each "task" is one recipe. Steps in a recipe (cmds) are the instructions. Variables you can swap (vars) are like recipe ingredients you can change, for example which configuration to use: Debug or Release. Recipes can call other recipes (deps, task:) — for example "restore the NuGet packages" runs as a sub-recipe before "build the solution" runs as the main recipe.

## 1. What is Task, and why use it?

Task is a command runner. Instead of typing long, easy-to-forget commands such as `dotnet restore && dotnet build -c Release && dotnet test` every time, you write them once in a file, give that combo a short name like build or test, and from then on you just type `task build`.

It is similar in spirit to Makefiles or MSBuild targets, but it uses simple YAML with no Makefile-specific syntax quirks like tabs versus spaces, it is cross-platform and works the same on macOS, Linux, and Windows, and it has built-in smarts like skipping work that is already up to date, covered in section 8.

Task looks in the current folder for a file named, in this priority order: Taskfile.yml, taskfile.yml, Taskfile.yaml, taskfile.yaml, Taskfile.dist.yml, taskfile.dist.yml, Taskfile.dist.yaml, taskfile.dist.yaml.

If none is found, Task walks up the folder tree, the same way Git looks for a .git folder, until it finds one. This means you can run `task build` from any subfolder of your solution.

## 2. Running Taskfiles

| What you want | How | Note |
|---|---|---|
| Use a specific file | task --taskfile <path> | Skip auto-discovery and use this exact file |
| Pipe a Taskfile in | cat ./Taskfile.yml \| task -t - | Rarely needed day-to-day |
| Run one hosted online or in git | Task supports HTTP(S) and Git sources | Never run a remote Taskfile you don't trust — it's as capable as a shell script |
| Use a Taskfile in your home folder | task --global (-g) | For personal shortcuts that apply anywhere on your machine, not tied to one project |

## 3. Core structure

```yaml
version: '3'

vars:
  BUILD_CONFIG: Release

tasks:
  task-name:
    desc: Task description
    cmds:
      - command here
```

The tasks section is the table of contents, and each entry under it is one recipe. version always gets declared at the top — it tells Task which feature set to expect. desc shows up when you run `task --list`.

A one-line task can skip the cmds wrapper entirely:

```yaml
tasks:
  restore: dotnet restore
```

## 4. Dependencies (deps)

deps are the prep work a task needs before it can run — restoring NuGet packages before a build is the classic .NET example. Task runs all listed dependencies in parallel by default, not one at a time, so it's fast.

```yaml
build:
  deps: [restore]
  cmds:
    - dotnet build --configuration {{.BUILD_CONFIG}} --no-restore

restore:
  cmds:
    - dotnet restore
```

--no-restore on the build step avoids restoring twice, since the restore task already did it.

To stop the moment any one dependency fails, instead of letting the others keep running, add failfast:

```yaml
build:
  deps: [restore, lint]
  failfast: true
```

## 5. Including other Taskfiles

Once a Taskfile gets large, split it into smaller files — one for tests, one for packaging — and pull them into a main file. Each included file's tasks get a prefix, like a chapter name, so a task named unit inside tests becomes tests:unit.

```yaml
includes:
  tests: ./TestTasks.yml
  publish: ./PublishTasks.yml

tasks:
  ci:
    cmds:
      - task: tests:unit
      - task: publish:artifacts
```

Include options: optional true skips the file without erroring if it's missing, useful for optional local overrides. internal true hides every task from that included file out of --list while still leaving them runnable. flatten true merges tasks in without the chapter prefix. vars lets you hand the included file variables when you pull it in.

## 6. Environment variables

These aren't Task's own variables — they're the same $ENV_VAR (or %VAR% on Windows) style variables .NET tooling already reads, such as DOTNET_ENVIRONMENT or ASPNETCORE_ENVIRONMENT. Task just lets you set them conveniently per task or globally.

```yaml
env:
  DOTNET_NOLOGO: "true"

tasks:
  test:
    env:
      ASPNETCORE_ENVIRONMENT: "Test"
    cmds:
      - dotnet test
```

The task-level env overrides the global one for that task only.

Dotenv files are loaded in this order, with the first match winning:

```yaml
dotenv:
  - .env.local
  - .env.{{.ENV}}
  - .env
```

.env.local holds personal overrides with the highest priority, .env.{{.ENV}} targets a specific environment such as .env.staging, and .env is the fallback default.

## 7. Variables

vars are different from env — they're used inside the Taskfile itself with {{.NAME}} template syntax, similar to a mail-merge placeholder. They can be strings, booleans, numbers, lists, or maps.

```yaml
tasks:
  example:
    vars:
      SOLUTION: "MyApp.sln"
      RUN_TESTS: true
      RETRY_COUNT: 3
      PROJECTS: [Api, Worker, Shared]
      CONFIG_MAP:
        map: { Debug: "Debug", Release: "Release" }
    cmds:
      - echo {{.SOLUTION}}
      - echo {{index .PROJECTS 0}}
      - echo {{.CONFIG_MAP.Release}}
```

That prints MyApp.sln, then Api (the first list item), then Release.

Dynamic variables run a shell command and use its output instead of a fixed value:

```yaml
vars:
  GIT_COMMIT:
    sh: git log -n 1 --format=%h
```

That captures the latest commit hash, useful for a VersionSuffix.

If the same variable name is set in multiple places, precedence runs from strongest to weakest as follows: a value set directly on the task itself, a value passed in when calling the task with vars, a value defined in an included Taskfile, a value passed to an include, a global vars entry at the top of the file, and finally a plain environment variable.

Secret variables mask a value so it doesn't show up in Task's verbose logs:

```yaml
vars:
  NUGET_API_KEY:
    value: 'oy2xxxxxxxxxxxxxxxxxxxxxxxxxxxxxx'
    secret: true
```

This only hides the value from logs — it is not real secret storage. Keep real API keys and connection strings in a proper secret store such as Azure DevOps secret variables or Key Vault, not hardcoded in the Taskfile.

## 8. Avoiding unnecessary work

This is one of Task's best time-savers — similar to MSBuild's incremental build, but easier to configure yourself.

**Fingerprinting with sources and generates.** Tell Task which files are inputs and which file is the output. Task hashes them, and if the inputs haven't changed since last time, it skips the task entirely and reports that it's up to date.

```yaml
build:
  sources:
    - "**/*.cs"
    - "**/*.csproj"
  generates:
    - bin/{{.BUILD_CONFIG}}/**/*.dll
  cmds:
    - dotnet build --configuration {{.BUILD_CONFIG}}
```

The fingerprint history lives in a hidden .task/ folder, which you can relocate with the TASK_TEMP_DIR environment variable.

**Status checks** run your own custom check for whether the task is already done, instead of comparing file hashes.

```yaml
restore:
  status:
    - test -f obj/project.assets.json
  cmds:
    - dotnet restore
```

**Preconditions** are a hard requirement that must be true or the task refuses to run at all. This differs from status: it's not "skip if done," it's "refuse if invalid."

```yaml
publish:
  preconditions:
    - test -f MyApp.sln
    - sh: '[ "{{.BUILD_CONFIG}}" = "Release" ]'
      msg: "Publish must run with BUILD_CONFIG=Release"
  cmds:
    - dotnet publish --configuration {{.BUILD_CONFIG}} --output ./publish
```

Use `task --force` to override any of the above and run anyway.

## 9. Conditional execution (if)

if works like a conditional in code, controlling whether a task or a single command runs at all.

```yaml
publish:
  if: '[ "$CI" = "true" ]'
  cmds:
    - dotnet publish --configuration Release

build:
  cmds:
    - cmd: echo "Building Release"
      if: '[ "$BUILD_CONFIG" = "Release" ]'
    - dotnet build --configuration {{.BUILD_CONFIG}}

tasks:
  example:
    cmds:
      - cmd: echo "Running tests"
        if: '{{eq .RUN_TESTS "true"}}'
```

The first example skips the whole task unless CI is true. The second skips just one command inside build, while the plain dotnet build line always runs regardless. The third uses Task's own template syntax instead of a shell condition.

## 10. Looping (for)

Loop over a list instead of copy-pasting the same command for every project in a solution. {{.ITEM}} is the current item in the loop, the same idea as item in a for item in list loop.

```yaml
- for: [Api, Worker, Shared]
  cmd: dotnet build ./src/{{.ITEM}}/{{.ITEM}}.csproj
```

A matrix loop runs every combination of two lists, like a spreadsheet grid:

```yaml
- for:
    matrix:
      CONFIG: ['Debug', 'Release']
      RUNTIME: ['win-x64', 'linux-x64']
  cmd: dotnet publish -c {{.ITEM.CONFIG}} -r {{.ITEM.RUNTIME}} --self-contained
```

That runs four times: Debug/win-x64, Debug/linux-x64, Release/win-x64, and Release/linux-x64.

Looping over a variable's value splits on spaces by default:

```yaml
- for: { var: PROJECTS }
  cmd: dotnet test ./src/{{.ITEM}}
```

Use split for a different delimiter, such as a comma:

```yaml
- for: { var: PROJECTS, split: ',' }
```

Rename the loop variable to something friendlier than {{.ITEM}}:

```yaml
- for: { var: PROJECTS, as: PROJECT }
  cmd: dotnet test ./src/{{.PROJECT}}
```

Loop over the same file list already declared as sources for the task:

```yaml
- for: sources
  cmd: echo {{.ITEM}}
```

## 11. Calling other tasks

A task can call other tasks by name, the same way one recipe says to run the restore recipe first, then come back.

```yaml
ci:
  cmds:
    - task: restore
    - task: build
    - task: test
    - echo "Pipeline complete"
```

Variables can be passed into the called task, and its output silenced:

```yaml
package:
  cmds:
    - task: build
      vars:
        BUILD_CONFIG: Release
        silent: true
```

From inside an included Taskfile, call a task from the main root file with a leading colon:

```yaml
cmds:
  - task: :root-task
```

## 12. Advanced task features

| Feature | What it does | Example |
|---|---|---|
| Platform restriction | Only run this on a given OS/arch | platforms: [windows/amd64, linux/amd64] |
| Hide from --list | Keep a helper task out of the public menu | internal: true |
| Alt names (aliases) | Nicknames for a task | aliases: [b] for build |
| Custom display name | Change how the task's name shows in logs | label: 'build-{{.PROJECT}}' |
| Wildcard task names | One task definition handles many similar names | test:*: |
| Guaranteed cleanup | Runs no matter what happens, to clean up after a task | defer: rm -rf ./publish |

A wildcard task template answers to many names:

```yaml
test:*:
  vars:
    PROJECT: '{{index .MATCH 0}}'
  cmds:
    - dotnet test ./tests/{{.PROJECT}}.Tests
```

Running `task "test:Api"` runs `dotnet test ./tests/Api.Tests`.

defer works like a finally block: it always runs, even if an earlier command in the task failed, and multiple defer entries run in reverse order — last one added, first one run.

```yaml
package:
  cmds:
    - mkdir -p ./publish
    - defer: rm -rf ./publish
    - dotnet publish --configuration Release --output ./publish
```

Cleanup here is guaranteed even if the publish step fails.

## 13. Requiring and validating variables

Instead of a task silently breaking because someone forgot to pass BUILD_CONFIG, make it a hard requirement up front, with an optional whitelist of allowed values.

```yaml
publish:
  requires:
    vars:
      - SOLUTION
      - name: BUILD_CONFIG
        enum: [Debug, Release]
  cmds:
    - dotnet publish {{.SOLUTION}} --configuration {{.BUILD_CONFIG}}
```

Only Debug or Release are accepted for BUILD_CONFIG. An enum can also point at a shared list instead of retyping it, using enum: { ref: .ALLOWED }.

With interactive: true set in a .taskrc.yml file, Task will prompt for any missing required variable, with a pick-list for enums, instead of just failing. That's handy for local dev, less so for CI.

## 14. Controlling output

| Setting | Effect |
|---|---|
| output: 'group' | Waits and prints each task's full output as one block — cleanest for CI logs such as Azure DevOps |
| output: 'prefixed' | Tags every line with [task-name] so parallel tasks stay distinguishable |
| output: 'interleaved' (default) | Prints everything as it happens, mixed together |
| silent: true | Suppresses the "running this command" line, showing only its output |
| ignore_error: true | Continues past a failure instead of stopping everything |
| task --dry <task> | Prints what would run without actually running it |

```yaml
version: '3'
output: prefixed

tasks:
  test:
    prefix: 'unit-tests'
    cmds:
      - dotnet test
```

## 15. Watching, listing, and inspecting tasks

```bash
task --list
task --list-all
task --summary publish
task --status <tasks>
task --watch test
task --interval=500ms --watch test
```

`task --list` (or -l) shows tasks that have a desc — the public menu. `task --list-all` (or -a) shows everything, including internal or hidden tasks. `task --summary publish` shows what a task would do — its deps, description, and commands — without running it. `task --status <tasks>` exits with an error code if the task is not up to date, useful as a CI gate. `task --watch test` re-runs test automatically every time a watched file changes, and the interval flag controls how often it checks.

Watch can also be configured directly in the Taskfile:

```yaml
interval: 500ms

test:
  watch: true
  sources: ["**/*.cs"]
  cmds: [dotnet test]
```

## 16. Passing extra arguments and running in parallel

```bash
task test -- --filter Category=Smoke
task --parallel restore lint
task --force build
task --yes publish
```

Everything after -- is forwarded to the task as {{.CLI_ARGS}}. --parallel runs multiple named tasks at the same time. --force ignores fingerprint and status checks and runs anyway. --yes auto-answers any confirmation prompts, which is needed for unattended CI runs.

```yaml
test:
  cmds:
    - dotnet test {{.CLI_ARGS}}
```

Running `task test -- --filter Category=Smoke` adds that filter to the dotnet test command.

## 17. Confirmation prompts

A prompt works like an "are you sure?" popup before something risky, useful for tasks that could cause real damage such as publishing to production or wiping a folder.

```yaml
publish-prod:
  prompt: "This publishes to PRODUCTION. Continue?"
  cmds:
    - dotnet publish --configuration Release
```

Multiple prompts can be stacked, for example "are you sure?" followed by "are you really sure?" If someone declines, Task exits with code 205. In CI, where no one is there to answer, use `task --yes` to skip the prompt automatically, only for tasks trusted to run unattended.

## 18. Special built-in variables

| Variable | Meaning |
|---|---|
| {{.TASK}} | The name of the task currently running |
| {{.USER_WORKING_DIR}} | The folder the user was in when they typed task ... |
| {{.CHECKSUM}} | The fingerprint hash of this task's sources |
| {{.TIMESTAMP}} | When this task last successfully ran |
| {{.CLI_ARGS}} | Whatever the user typed after -- on the command line |
| {{.EXIT_CODE}} | The failing command's exit code, meaningful only inside a defer cleanup step |
| {{.HOME}} | The current user's home directory |
| {{OS}} / {{ARCH}} | The operating system and CPU architecture Task is running on |

## 19. Run control (run)

If a task gets called multiple times — for example in a loop over projects, or from several other tasks — with different variables each time, run decides whether to redo the work each time or skip repeats.

```yaml
restore:
  run: when_changed
```

always runs every single time it's called, no matter what, and is the default. once runs only the first time it's called, ignoring later calls completely. when_changed runs once per unique combination of variables, so a second call with the same variables is skipped.

## 20. Shell options (set / shopt)

These map to Bash's own set and shopt built-ins — settings for how strictly or flexibly the shell behaves.

```yaml
version: '3'
set: [pipefail]
shopt: [globstar]
```

pipefail makes a pipeline fail if any command in it fails, not just the last one. globstar lets ** match across nested folders instead of just one level.

## 21. Changing directory for a task (dir)

dir runs a command as if you had cd'd into that folder first. Task creates the folder automatically if it doesn't already exist.

```yaml
publish:
  dir: src/Api
  cmds:
    - dotnet publish --configuration Release --output ../../publish
```

## 22. CI/CD integration notes

Task automatically turns on colored output when it detects CI=true, which most CI systems including Azure DevOps set by default. Force it on with FORCE_COLOR=1 or off with NO_COLOR=1.

When GITHUB_ACTIONS=true, a failing task automatically shows up as an annotated error in the workflow summary, with no extra setup needed.

If a task launches something interactive, such as an editor or a wizard, mark it so Task doesn't try to capture or interleave its output oddly:

```yaml
edit:
  interactive: true
  cmds:
    - vim appsettings.json
```

## 23. Full example — .NET build pipeline, no Docker

```yaml
version: '3'

vars:
  SOLUTION: "MyApp.sln"
  BUILD_CONFIG: Release
  PUBLISH_DIR: "./publish"

env:
  DOTNET_NOLOGO: "true"
  DOTNET_CLI_TELEMETRY_OPTOUT: "true"

tasks:
  default:
    deps: [restore]
    cmds:
      - task: build

  restore:
    desc: Restore NuGet packages
    status:
      - test -f obj/project.assets.json
    cmds:
      - dotnet restore {{.SOLUTION}}

  build:
    desc: Build the solution
    deps: [restore]
    sources:
      - "**/*.cs"
      - "**/*.csproj"
    generates:
      - "**/bin/{{.BUILD_CONFIG}}/**/*.dll"
    cmds:
      - dotnet build {{.SOLUTION}} --configuration {{.BUILD_CONFIG}} --no-restore

  test:
    desc: Run unit tests
    deps: [build]
    cmds:
      - dotnet test {{.SOLUTION}} --configuration {{.BUILD_CONFIG}} --no-build

  publish:
    desc: Publish a deployable output
    deps: [test]
    requires:
      vars: [BUILD_CONFIG]
    cmds:
      - dotnet publish {{.SOLUTION}} --configuration {{.BUILD_CONFIG}} --output {{.PUBLISH_DIR}}

  clean:
    desc: Remove build and publish output
    cmds:
      - dotnet clean {{.SOLUTION}}
      - rm -rf {{.PUBLISH_DIR}}

  dev:
    desc: Watch source and re-run tests on change
    watch: true
    sources:
      - "**/*.cs"
    cmds:
      - task: test
```

Read top to bottom: by default, restore runs then build runs. Build depends on restore and only runs if .cs or .csproj files changed. Test depends on a successful build. Publish depends on tests passing and refuses to run without a BUILD_CONFIG. Dev mode watches for source changes and re-runs tests automatically.

## Cheat sheet

```bash
task
task <name>
task -l
task -a
task --summary <name>
task --dry <name>
task --watch <name>
task --force <name>
task --parallel a b
task test -- --filter Category=Smoke
```

task with no name runs default. task followed by a name runs that specific task, for example task build. -l lists available tasks with descriptions, -a lists all tasks including internal ones. --summary previews what a task does without running it. --dry prints the commands that would run without running them. --watch re-runs automatically when files change. --force ignores "already up to date" checks. --parallel runs multiple tasks at the same time. Anything after -- forwards as {{.CLI_ARGS}}.

## Related in this repo

- taskfile-ADO/Taskfile.yml — real Taskfile used for the ADO pipeline
- taskfile-ADO/README.md
- taskfile-template-plan.md
- platform-taskfile-library/

## Source

Official guide: https://taskfile.dev/docs/guide (full docs at https://taskfile.dev/docs/)
