# Taskfile Learning Guide (Beginner-Friendly)

A structured, plain-English reference for [Task](https://taskfile.dev) (`go-task`), based on the
[official guide](https://taskfile.dev/docs/guide). Every section explains the concept in layman's
terms first, then shows the real YAML. Use this alongside the existing
[taskfile-ADO/](taskfile-ADO/) examples in this repo.

> **Analogy to keep in mind throughout:** a `Taskfile.yml` is like a **recipe book**. Each
> "task" is one recipe. Steps in a recipe (`cmds`) are the instructions. Ingredients you can
> swap (`vars`) are like recipe variables ("use 2 cups of X"). Recipes can call other recipes
> (`deps`, `task:`) — e.g., "make the dough" (a sub-recipe) before "bake the bread" (the main
> recipe).

---

## 1. What is Task, and why would you use it?

**In plain terms:** Task is a command runner. Instead of typing long, easy-to-forget commands
(`go build -o ./app . && ./app --flag=x`) every time, you write them once in a file, give that
combo a short name (like `build` or `deploy`), and from then on you just type `task build`.

It's similar in spirit to `Makefile`s or `npm run` scripts, but:
- Uses simple YAML (no Makefile-specific syntax quirks like tabs-vs-spaces).
- Cross-platform (works the same on macOS, Linux, Windows).
- Has built-in smarts like "don't redo this if nothing changed" (see §8) — so it saves time,
  not just typing.

**How it finds your recipe book:** Task looks in the current folder for a file named (in this
priority order):

```
Taskfile.yml, taskfile.yml, Taskfile.yaml, taskfile.yaml,
Taskfile.dist.yml, taskfile.dist.yml, Taskfile.dist.yaml, taskfile.dist.yaml
```

If it's not there, Task walks *up* the folder tree (like Git does when looking for `.git`)
until it finds one. So you can run `task build` from any subfolder of your project.

## 2. Running Taskfiles — the different ways to point Task at a file

| What you want | How | Plain-English note |
|---|---|---|
| Use a specific file | `task --taskfile <path>` | "Don't guess, use *this* file." |
| Pipe a Taskfile in | `cat ./Taskfile.yml \| task -t -` | Rarely needed day-to-day. |
| Run one hosted online/in git | Task supports HTTP(S)/Git sources | ⚠️ **Never** run a remote Taskfile you don't trust — it's just as capable as a shell script. |
| Use a Taskfile in your home folder | `task --global` (`-g`) | For personal shortcuts that apply anywhere on your machine, not tied to one project. |

## 3. The core structure — anatomy of a Taskfile

```yaml
version: '3'          # always declare this — tells Task which feature-set to expect

vars:
  GLOBAL_VAR: value    # a variable every task can use

tasks:
  task-name:
    desc: Task description   # shows up in `task --list`
    cmds:
      - command here          # the actual shell command(s) to run
```

Think of `tasks:` as the table of contents, and each entry under it as one recipe.

**Shortcut for tiny tasks** — if a task is just one line, skip the `cmds:` wrapper:

```yaml
tasks:
  build: go build -v -o ./app .
```

## 4. Dependencies (`deps`) — "do this first"

**Plain terms:** `deps` are the prep work a task needs before it can run — like preheating the
oven before you can bake. Task runs all listed dependencies **at the same time (in parallel)**
by default, not one-by-one, so it's fast.

```yaml
build:
  deps: [assets]          # "assets" runs first (in parallel with any other deps)
  cmds:
    - go build main.go

assets:
  cmds:
    - esbuild --bundle css/index.css > bundle.css
```

If you have several dependencies and want Task to stop the moment *any one* of them fails
(instead of letting the others keep running), add:

```yaml
build:
  deps: [assets, lint]
  failfast: true
```

## 5. Including other Taskfiles — splitting a big recipe book into chapters

**Plain terms:** Once your Taskfile gets big, split it into smaller files (e.g., one for
Docker stuff, one for docs) and pull them into a main file. Each included file's tasks get a
prefix, like a chapter name, so `serve` inside `documentation` becomes `docs:serve`.

```yaml
includes:
  docs: ./documentation
  docker: ./DockerTasks.yml

tasks:
  example:
    cmds:
      - task: docs:serve
      - task: docker:build
```

Useful include options:
- `optional: true` — don't error out if the file is missing (handy for optional local overrides).
- `internal: true` — hide every task from that included file out of `task --list` (still runnable, just not advertised).
- `flatten: true` — merge tasks in without the `chapter:` prefix.
- `vars:` — hand the included file some variables when you pull it in.

## 6. Environment variables — values passed to the command's shell

**Plain terms:** These aren't Task's own variables — they're the same `$ENV_VAR` style
variables your shell/programs already understand (like `$PATH`). Task just lets you set them
conveniently per-task or globally.

```yaml
env:                      # global — every task gets this
  GREETING: "Hey, there!"

tasks:
  greet:
    env:
      GREETING: "Hello!"   # only for this task — overrides the global one
    cmds:
      - echo $GREETING
```

**Loading from `.env` files** (like a settings file for secrets/config), checked in this order
— first match wins:

```yaml
dotenv:
  - .env.local        # your personal overrides, highest priority
  - .env.{{.ENV}}      # e.g. .env.production
  - .env               # the fallback defaults
```

## 7. Variables — Task's own "fill in the blank" system

**Plain terms:** `vars` are different from `env` — they're used *inside* the Taskfile itself
with `{{.NAME}}` syntax (Go template syntax), like a mail-merge placeholder. They can be
strings, true/false, numbers, lists, or maps (dictionaries).

```yaml
tasks:
  example:
    vars:
      STRING: "Hello"
      BOOL: true
      INT: 42
      ARRAY: [1, 2, 3]
      MAP:
        map: { A: 1, B: 2 }
    cmds:
      - echo {{.STRING}}          # prints: Hello
      - echo {{index .ARRAY 0}}   # prints: 1 (first item)
      - echo {{.MAP.A}}           # prints: 1
```

**Dynamic variables** — instead of a fixed value, run a shell command and use its output:

```yaml
vars:
  GIT_COMMIT:
    sh: git log -n 1 --format=%h   # e.g. "a1b2c3d" — the latest commit hash
```

**Precedence** — if the same variable name is set in multiple places, here's who wins, from
strongest to weakest (like layers overriding each other):

1. Set directly on the task itself
2. Passed in when calling the task (`task: X` with `vars:`)
3. Defined in an included Taskfile
4. Passed to an include (`includes: ... vars:`)
5. Global `vars:` at the top of the file
6. Plain environment variables (`env:` / shell)

**Secret variables** — mask a value so it doesn't show up in Task's verbose logs:

```yaml
vars:
  API_KEY:
    value: 'sk-secret-123'
    secret: true
```

⚠️ This only hides it from *logs* — it's **not** real secret storage. Still keep actual secrets
out of the Taskfile (use a vault, CI secret store, etc.).

## 8. Avoiding unnecessary work — Task's "don't redo work that's already done" features

This is one of Task's best time-savers — like `make`'s incremental builds, but easier to set up.

### Fingerprinting (`sources` / `generates`)
**Plain terms:** Tell Task "these are my inputs" and "this is my output." Task fingerprints
(hashes) them; if the inputs haven't changed since last time, it skips the task entirely and
tells you so.

```yaml
build:
  sources:
    - src/**/*.go
  generates:
    - ./app
  cmds:
    - go build -o ./app .
```

The fingerprint history lives in a hidden `.task/` folder (override its location with the
`TASK_TEMP_DIR` environment variable).

### Status checks
**Plain terms:** Instead of comparing file hashes, run your own custom "is this already done?"
check — like a bouncer checking if you already have a wristband before letting you in.

```yaml
deploy:
  status:
    - test -f ./vendor/autoload.php
  cmds:
    - composer install
```

### Preconditions
**Plain terms:** A hard requirement that must be true, or the task refuses to run at all (this
is different from `status` — it's not "skip if done," it's "refuse if invalid").

```yaml
generate:
  preconditions:
    - test -f .env
    - sh: '[ 1 = 0 ]'
      msg: "Invalid condition"     # shown to the user if this check fails
  cmds:
    - mkdir directory
```

Use `task --force` to override any of the above and run anyway.

## 9. Conditional execution (`if`) — only run when a condition is true

**Plain terms:** Like an `if` statement in code, but for whether a task or a single command
should run at all.

```yaml
# Skip the whole task unless in CI
deploy:
  if: '[ "$CI" = "true" ]'
  cmds:
    - ./deploy.sh

# Skip just one command
build:
  cmds:
    - cmd: echo "Production build"
      if: '[ "$ENV" = "production" ]'
    - go build ./...   # this always runs regardless

# Using Task's own template syntax instead of shell syntax
tasks:
  example:
    cmds:
      - cmd: echo "Enabled"
        if: '{{eq .FEATURE "true"}}'
```

## 10. Looping (`for`) — do the same thing for a list of things

**Plain terms:** Instead of copy-pasting the same command five times for five files, loop over
a list. `{{.ITEM}}` is the current item in the loop, like `item` in a `for item in list` loop.

```yaml
# Loop over a fixed list
- for: ['file1.txt', 'file2.txt']
  cmd: cat {{.ITEM}}

# Loop over every combination of two lists ("matrix" — like a spreadsheet grid)
- for:
    matrix:
      OS: ['windows', 'linux']
      ARCH: ['amd64', 'arm64']
  cmd: echo "{{.ITEM.OS}}/{{.ITEM.ARCH}}"
# Runs 4 times: windows/amd64, windows/arm64, linux/amd64, linux/arm64

# Loop over a variable's value (splits on spaces by default)
- for: { var: FILES }
  cmd: cat {{.ITEM}}

# Split differently, e.g. comma-separated
- for: { var: FILES, split: ',' }

# Give the loop variable a friendlier name than {{.ITEM}}
- for: { var: FILES, as: FILE }
  cmd: cat {{.FILE}}

# Loop over the same file list you declared as "sources" for the task
- for: sources
  cmd: echo {{.ITEM}}
```

## 11. Calling other tasks — chaining recipes together

**Plain terms:** A task can call other tasks by name, like one recipe saying "go make the
sauce recipe first, then come back here."

```yaml
main:
  cmds:
    - task: build
    - task: deploy
    - echo "Done"

# Pass variables into the called task, and silence its output
process:
  cmds:
    - task: handle
      vars:
        FILE: data.txt
        silent: true

# From inside an included ("chaptered") Taskfile, call a task from the main/root file
cmds:
  - task: :root-task
```

## 12. Advanced task features (quick-reference table)

| Feature | What it means in plain terms | Example |
|---|---|---|
| Platform restriction | "Only run this on Windows/Mac/Linux" | `platforms: [windows/amd64, windows/arm64]` |
| Hide from `--list` | Keep a helper task out of the public menu | `internal: true` |
| Alt names (aliases) | Nicknames for a task | `aliases: [gen]` |
| Custom display name | Change how the task's name shows in logs | `label: 'process-{{.FILE}}'` |
| Wildcard task names | One task definition handles many similar names | `start:*:*:` |
| Guaranteed cleanup | "No matter what happens, clean up after yourself" | `defer: rm -rf tmpdir/` |

**Wildcard example** — one task template answers to many names:

```yaml
start:*:*:
  vars:
    SERVICE: '{{index .MATCH 0}}'    # first * in the task name
    REPLICAS: '{{index .MATCH 1}}'   # second *
  cmds:
    - echo "Starting {{.SERVICE}} x{{.REPLICAS}}"
# Run with: task "start:api:3"  →  prints "Starting api x3"
```

**`defer`** is like a `finally` block: it always runs, even if an earlier command in the task
failed, and multiple `defer`s run in reverse order (last one added, first one run) — same idea
as unstacking plates.

```yaml
build:
  cmds:
    - mkdir -p tmpdir/
    - defer: rm -rf tmpdir/    # cleanup guaranteed, even if the build below fails
    - echo "Do work"
```

## 13. Requiring and validating variables — fail fast with a clear message

**Plain terms:** Instead of a task silently breaking because someone forgot to pass
`IMAGE_TAG`, make it a hard requirement up front, with an optional whitelist of allowed values.

```yaml
deploy:
  requires:
    vars:
      - IMAGE_NAME
      - IMAGE_TAG
      - name: ENV
        enum: [dev, staging, prod]   # only these three values are allowed
  cmds:
    - docker build -t {{.IMAGE_NAME}}:{{.IMAGE_TAG}}
```

You can also point the enum at a shared list instead of retyping it: `enum: { ref: .ALLOWED }`.

If you turn on `interactive: true` in a `.taskrc.yml` file, Task will *ask you* for any missing
required variable (with a pick-list for enums) instead of just failing — handy for local dev,
less so for CI.

## 14. Controlling output — keeping the terminal readable

| Setting | Plain-English effect |
|---|---|
| `output: 'group'` | Waits and prints each task's full output as one block — cleanest for CI logs. |
| `output: 'prefixed'` | Tags every line with `[task-name]` so you can tell tasks apart when several run at once. |
| `output: 'interleaved'` (default) | Just prints everything as it happens, mixed together. |
| `silent: true` | Don't even show *which command* is running — just its output (or nothing, if the command itself is silent). |
| `ignore_error: true` | "If this fails, don't stop everything — carry on." |
| `task --dry <task>` | Preview: prints what *would* run, without actually running it. Great for double-checking before a risky task. |

```yaml
version: '3'
output: prefixed

tasks:
  print:
    prefix: 'custom-prefix'
    cmds:
      - echo "Text"
```

## 15. Watching, listing, and inspecting tasks — day-to-day commands

```bash
task --list           # or -l   — show tasks that have a desc (the "public menu")
task --list-all        # or -a   — show everything, including internal/hidden tasks
task --summary release # show what a task WOULD do (deps, description, commands) without running it
task --status <tasks>  # exits with an error code if the task is NOT up to date — useful in CI gates
task --watch build      # re-runs "build" automatically every time a watched file changes
task --interval=500ms --watch build   # same, but check for changes every 500ms
```

`--watch` is like leaving a chef standing by, re-cooking the dish automatically every time you
tweak the recipe — great for local development loops.

Configuring watch directly in the Taskfile:

```yaml
interval: 500ms

build:
  watch: true
  sources: ['**/*.go']
  cmds: [go build]
```

## 16. Passing extra arguments and running things in parallel

```bash
task yarn -- install        # everything after "--" is forwarded as {{.CLI_ARGS}}
task --parallel js css      # run the "js" and "css" tasks at the same time
task --force build          # ignore fingerprint/status checks and run anyway
task --yes deploy           # auto-answer "yes" to any confirmation prompts (needed for CI)
```

```yaml
yarn:
  cmds:
    - yarn {{.CLI_ARGS}}     # "task yarn -- install" runs: yarn install
```

## 17. Confirmation prompts — a safety net for dangerous tasks

**Plain terms:** Like the "Are you sure?" popup before deleting something. Good for tasks that
could cause real damage (wiping a database, force-pushing, deleting a folder).

```yaml
dangerous:
  prompt: "Dangerous operation. Continue?"
  cmds:
    - rm -rf data/
```

You can stack multiple prompts (e.g., "are you sure?" then "are you REALLY sure?"). If someone
declines, Task exits with code `205`. In CI, where no one's there to answer, use `task --yes`
to skip the prompt automatically (only do this for tasks you trust running unattended).

## 18. Special built-in variables — values Task fills in for you

| Variable | Plain-English meaning |
|---|---|
| `{{.TASK}}` | The name of the task currently running |
| `{{.USER_WORKING_DIR}}` | The folder the user was in when they typed `task ...` |
| `{{.CHECKSUM}}` | The fingerprint hash of this task's `sources` |
| `{{.TIMESTAMP}}` | When this task last successfully ran |
| `{{.CLI_ARGS}}` | Whatever the user typed after `--` on the command line |
| `{{.EXIT_CODE}}` | The failing command's exit code — only meaningful inside a `defer` cleanup step |
| `{{.HOME}}` | The current user's home directory |
| `{{OS}}` / `{{ARCH}}` | What operating system / CPU architecture Task is running on |

## 19. Run control (`run`) — how to handle a task called more than once

**Plain terms:** If a task gets called multiple times (e.g., in a loop, or from several other
tasks) with different variables each time, `run:` decides whether to actually redo the work
each time, or skip repeats.

```yaml
generate:
  run: when_changed   # options: always (default) | once | when_changed
```

- `always` — run every single time it's called, no matter what.
- `once` — run only the very first time it's called; ignore later calls completely.
- `when_changed` — run once per *unique combination* of variables (e.g., `FILE: a` and
  `FILE: b` each run once, but a second call with `FILE: a` is skipped).

## 20. Shell options (`set` / `shopt`) — tweaking how commands are executed

**Plain terms:** These map to Bash's own `set` and `shopt` built-ins — power-user settings for
how strictly/flexibly the shell behaves.

```yaml
version: '3'
set: [pipefail]     # a pipeline fails if ANY command in it fails, not just the last one
shopt: [globstar]   # lets ** match across nested folders, not just one level
```

## 21. Changing directory for a task (`dir`)

**Plain terms:** "Run this command as if you `cd`'d into this folder first." Task creates the
folder automatically if it doesn't already exist.

```yaml
serve:
  dir: public/www
  cmds:
    - http-server
```

## 22. CI/CD integration notes

- **Colors**: Task automatically turns on colored output when it detects `CI=true` (most CI
  systems set this). You can force it on with `FORCE_COLOR=1` or off with `NO_COLOR=1`.
- **GitHub Actions**: when `GITHUB_ACTIONS=true`, a failing task automatically shows up as an
  annotated error in the workflow summary — no extra setup needed.
- **Interactive tools**: if a task launches something interactive (an editor, a wizard), mark
  it so Task doesn't try to capture/interleave its output oddly:

```yaml
edit:
  interactive: true
  cmds:
    - vim file.txt
```

## 23. Putting it all together — a realistic example

```yaml
version: '3'

vars:
  GO_FILES: '**/*.go'
  BUILD_DIR: './build'

env:
  CGO_ENABLED: '0'

tasks:
  default:                 # runs when you just type "task" with no name
    deps: [test]
    cmds:
      - task: build

  build:
    desc: Build the application
    sources:
      - '{{.GO_FILES}}'     # skip rebuilding if no .go files changed
    generates:
      - '{{.BUILD_DIR}}/app'
    cmds:
      - mkdir -p {{.BUILD_DIR}}
      - go build -o {{.BUILD_DIR}}/app .

  test:
    desc: Run tests
    sources:
      - '{{.GO_FILES}}'
    cmds:
      - go test -race ./...

  clean:
    cmds:
      - rm -rf {{.BUILD_DIR}}

  dev:
    watch: true              # auto re-run on file changes, for local development
    sources:
      - '{{.GO_FILES}}'
    cmds:
      - task: build
      - defer: task clean
      - {{.BUILD_DIR}}/app
```

Read it top to bottom like a story: "By default, test then build. Building only happens if Go
files changed, and produces `./build/app`. Testing always checks all Go files. Dev mode watches
for changes, rebuilds, cleans up afterward no matter what, then runs the app."

## Cheat sheet — most-used commands

```bash
task                 # run the "default" task
task <name>          # run a specific task
task -l              # list available tasks (with descriptions)
task -a              # list ALL tasks, including internal/hidden ones
task --summary <name> # preview what a task does, without running it
task --dry <name>    # print the commands that would run, without running them
task --watch <name>  # re-run automatically when files change
task --force <name>  # ignore "already up to date" checks and run anyway
task --parallel a b  # run tasks "a" and "b" at the same time
task a -- arg1 arg2  # forward extra args to task "a" as {{.CLI_ARGS}}
```

## Related in this repo

- [taskfile-ADO/Taskfile.yml](taskfile-ADO/Taskfile.yml) — real Taskfile used for the ADO pipeline.
- [taskfile-ADO/README.md](taskfile-ADO/README.md)
- [taskfile-template-plan.md](taskfile-template-plan.md)
- [platform-taskfile-library/](platform-taskfile-library/)

## Source

Official guide: https://taskfile.dev/docs/guide (full docs at https://taskfile.dev/docs/)
