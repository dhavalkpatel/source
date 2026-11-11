#!/usr/bin/env python3
"""Archive an Azure Repo into the archive tenant, or restore it to its origin tenant.

archive:   snapshot config -> mirror repo to archive org -> commit ARCHIVE.md + metadata on
           branch `archive-metadata` -> lock archive copy read-only -> disable source pipelines
           and disable/delete source repo.
unarchive: read metadata from the archive copy -> re-enable / restore / recreate source repo ->
           re-apply pipelines, policies, permissions and pipeline authorisations -> record the
           unarchive on the archive copy and rename it `<name>_unarchived-<timestamp>`.
"""
from __future__ import annotations

import argparse
import base64
import datetime as dt
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from urllib.parse import quote

import requests

VSRM = "vsrm.dev.azure.com"
VSSPS = "vssps.dev.azure.com"
PREVIEW = "7.1-preview.1"
GIT_NS_NAME = "Git Repositories"
GIT_BITS = {
    1: "Administer", 2: "Read", 4: "Contribute", 8: "ForcePush", 16: "CreateBranch",
    32: "CreateTag", 64: "ManageNote", 128: "PolicyExempt", 256: "CreateRepository",
    512: "DeleteRepository", 1024: "RenameRepository", 2048: "EditPolicies",
    4096: "RemoveOthersLocks", 8192: "ManagePermissions", 16384: "PullRequestContribute",
    32768: "PullRequestBypassPolicy",
}
# Everything that writes to the repo; Read stays allowed
READONLY_DENY = 4 | 8 | 16 | 32 | 64 | 128 | 16384 | 32768
META_BRANCH = "archive-metadata"
META_FILE = "archive-metadata.json"
DOC_FILE = "ARCHIVE.md"
BOT = {"user.name": "Repo Archive Pipeline", "user.email": "repo-archive@noreply.local"}
RESOURCE_APIS = {
    "endpoint": ("_apis/serviceendpoint/endpoints", "7.1"),
    "variablegroup": ("_apis/distributedtask/variablegroups", "7.1"),
    "securefile": ("_apis/distributedtask/securefiles", PREVIEW),
    "environment": ("_apis/distributedtask/environments", "7.1"),
    "queue": ("_apis/distributedtask/queues", PREVIEW),
}
BUILD_READONLY = {"id", "revision", "_links", "url", "uri", "createdDate", "authoredBy",
                  "latestBuild", "latestCompletedBuild", "metrics"}
RELEASE_READONLY = {"id", "revision", "_links", "url", "createdOn", "createdBy",
                    "modifiedOn", "modifiedBy", "lastRelease"}
SECRET_HINTS = ("password", "token", "secret", "key", "header")
# Writes are only retried when the server certainly did not process them
RETRY_READ = {429, 500, 502, 503, 504}
RETRY_WRITE = {429, 503}


# ---------------------------------------------------------------- ADO client / git

class AdoError(Exception):
    pass


def basic_token(pat: str) -> str:
    return base64.b64encode(f":{pat}".encode()).decode()


class Ado:
    def __init__(self, org: str, pat: str | None):
        if not pat:
            raise AdoError(f"No PAT supplied for org '{org}'")
        self.org = org
        self.pat = pat
        if os.environ.get("TF_BUILD"):
            # The base64 header form is not masked automatically by the agent
            print(f"##vso[task.setsecret]{basic_token(pat)}", flush=True)
        self.session = requests.Session()
        self.session.auth = ("", pat)
        self.session.headers["Accept"] = "application/json"

    def call(self, method, path, *, host="dev.azure.com", api="7.1", params=None,
             body=None, allow_404=False, raw=False):
        url = f"https://{host}/{self.org}/{path.lstrip('/')}"
        query = {"api-version": api, **(params or {})}
        is_read = method == "GET"
        for attempt in range(6):
            try:
                r = self.session.request(method, url, params=query, json=body, timeout=120)
            except (requests.ConnectionError, requests.Timeout) as e:
                if is_read and attempt < 5:
                    time.sleep(2 ** attempt)
                    continue
                raise AdoError(f"{method} {path}: {e}") from e
            retryable = r.status_code in (RETRY_READ if is_read else RETRY_WRITE)
            # A 500 carrying a typed server exception (TFxxxx) is deterministic
            if r.status_code == 500 and _server_exception(r):
                retryable = False
            if retryable and attempt < 5:
                time.sleep(_retry_after(r, attempt))
                continue
            break
        if allow_404 and r.status_code == 404:
            return None
        if r.status_code == 203 or (r.ok and "text/html" in r.headers.get("Content-Type", "")):
            raise AdoError(f"{method} {path}: authentication failed - check the PAT for '{self.org}'")
        if not r.ok:
            raise AdoError(f"{method} {path}: HTTP {r.status_code} {r.text[:500]}")
        if raw:
            return r
        return r.json() if r.content else None

    def list(self, path, **kwargs):
        params = dict(kwargs.pop("params", None) or {})
        items = []
        while True:
            r = self.call("GET", path, params=params, raw=True, **kwargs)
            items.extend(r.json().get("value", []))
            token = r.headers.get("x-ms-continuationtoken")
            if not token:
                return items
            params["continuationToken"] = token

    def action(self, ns_name, action):
        """Return (namespaceId, bit) for a named permission, resolved from the org."""
        if not hasattr(self, "_namespaces"):
            self._namespaces = self.list("_apis/securitynamespaces")
        for n in self._namespaces:
            if ns_name in (n.get("name"), n.get("displayName")):
                for act in n.get("actions") or []:
                    if act.get("name") == action:
                        return n["namespaceId"], act["bit"]
        raise AdoError(f"Permission '{ns_name}/{action}' not visible in '{self.org}' (PAT needs Security scope)")

    @property
    def git_ns(self):
        return self.action(GIT_NS_NAME, "GenericRead")[0]

    def has_permission(self, ns_name, action, token):
        ns, bit = self.action(ns_name, action)
        r = self.call("GET", f"_apis/permissions/{ns}/{bit}",
                      params={"tokens": token, "alwaysAllowAdministrators": "true"})
        return bool(r and r.get("value") and r["value"][0])


def _retry_after(r, attempt):
    try:
        return min(float(r.headers["Retry-After"]), 60)
    except (KeyError, ValueError):
        return 2 ** attempt


def _server_exception(r):
    try:
        return "typeKey" in r.json()
    except ValueError:
        return False


def git(args, cwd=None, pat=None, config=None):
    # Credentials go through GIT_CONFIG_* env vars so they never appear on the command line
    cfg = dict(config or {})
    if pat:
        cfg["http.extraHeader"] = f"Authorization: Basic {basic_token(pat)}"
    env = {**os.environ, "GIT_TERMINAL_PROMPT": "0", "GIT_CONFIG_COUNT": str(len(cfg))}
    for i, (key, value) in enumerate(cfg.items()):
        env[f"GIT_CONFIG_KEY_{i}"] = key
        env[f"GIT_CONFIG_VALUE_{i}"] = value
    print(f"> git {' '.join(a for a in args if not a.startswith('http'))}", flush=True)
    subprocess.run(["git", *args], cwd=cwd, env=env, check=True)


# ---------------------------------------------------------------- helpers

def log(msg):
    print(msg, flush=True)


def warn(msg):
    print(f"##vso[task.logissue type=warning]{msg}", flush=True)


def utcnow():
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")


def p(name):
    return quote(name, safe="")


def archived_name(org, project, repo):
    return f"{org}_{project}_{repo}".replace(" ", "-")


def repo_token(project_id, repo_id):
    return f"repoV2/{project_id}/{repo_id}"


def run_info():
    base, proj, bid = (os.environ.get(k) for k in ("SYSTEM_COLLECTIONURI", "SYSTEM_TEAMPROJECT", "BUILD_BUILDID"))
    return {
        "at": utcnow(),
        "by": os.environ.get("BUILD_REQUESTEDFOR", os.environ.get("USER", "unknown")),
        "run": f"{base}{quote(proj)}/_build/results?buildId={bid}" if base and proj and bid else None,
    }


def find_repo(ado, project, name=None, repo_id=None):
    for r in ado.list(f"{p(project)}/_apis/git/repositories", params={"includeHidden": "true"}):
        if (repo_id and r["id"] == repo_id) or (name and r["name"].lower() == name.lower()):
            return r
    return None


def list_refs(ado, project, repo_id):
    refs = ado.list(f"{p(project)}/_apis/git/repositories/{repo_id}/refs")
    return sorted(
        ({"name": r["name"], "objectId": r["objectId"]} for r in refs
         if r["name"].startswith(("refs/heads/", "refs/tags/")) and r["name"] != f"refs/heads/{META_BRANCH}"),
        key=lambda r: r["name"],
    )


def verify_refs(ado, project, repo_id, expected):
    actual = list_refs(ado, project, repo_id)
    if actual != expected:
        diff = {r["name"] for r in expected} ^ {r["name"] for r in actual}
        raise AdoError(f"Ref verification failed for {ado.org}/{project} repo {repo_id}; differing refs: {sorted(diff)[:20]}")
    log(f"Verified {len(actual)} refs")


def repo_policies(ado, project, repo_id):
    configs = ado.list(f"{p(project)}/_apis/git/policy/configurations", params={"repositoryId": repo_id}, api=PREVIEW)
    return [c for c in configs if any(s.get("repositoryId") == repo_id for s in c.get("settings", {}).get("scope", []))]


def identity_names(ado, descriptors):
    names, ds = {}, sorted(descriptors)
    try:
        for i in range(0, len(ds), 50):
            res = ado.call("GET", "_apis/identities", host=VSSPS, params={"descriptors": ",".join(ds[i:i + 50])})
            for ident in res.get("value", []):
                if ident:
                    names[ident["descriptor"]] = ident.get("providerDisplayName") or ident.get("customDisplayName")
    except AdoError as e:
        warn(f"Could not resolve identity names: {e}")
    return names


def valid_users_descriptors(ado, project_name):
    descriptors = []
    for group in (f"[{project_name}]\\Project Valid Users", f"[{ado.org}]\\Project Collection Valid Users"):
        res = ado.call("GET", "_apis/identities", host=VSSPS,
                       params={"searchFilter": "General", "filterValue": group, "queryMembership": "None"})
        descriptors += [i["descriptor"] for i in res.get("value", []) if i]
    if not descriptors:
        raise AdoError(f"Could not resolve 'Valid Users' groups in '{ado.org}'")
    return descriptors


def set_readonly(ado, project_name, project_id, repo_id, readonly):
    descriptors = valid_users_descriptors(ado, project_name)
    token = repo_token(project_id, repo_id)
    if readonly:
        ado.call("POST", f"_apis/accesscontrolentries/{ado.git_ns}", body={
            "token": token, "merge": True,
            "accessControlEntries": [{"descriptor": d, "allow": 0, "deny": READONLY_DENY} for d in descriptors],
        })
        log("Archive copy locked read-only")
    else:
        ado.call("DELETE", f"_apis/accesscontrolentries/{ado.git_ns}", params={"token": token, "descriptors": ",".join(descriptors)})
        log("Archive copy unlocked")


def lfs(args, cwd, pat):
    if shutil.which("git-lfs"):
        git(["lfs", *args], cwd=cwd, pat=pat)
    else:
        warn("git-lfs not installed - LFS objects (if any) are not copied")


def copy_refs(mirror, url, pat):
    git(["remote", "add", "target", url], cwd=mirror)
    # Forced so a resumed run can overwrite a partial earlier push
    git(["push", "target", "+refs/heads/*:refs/heads/*", "+refs/tags/*:refs/tags/*"], cwd=mirror, pat=pat)
    lfs(["push", "--all", "target"], mirror, pat)


def load_record(ado, project, arepo, workdir):
    """Clone the archive-metadata branch into workdir and return the record, or None if absent."""
    refs = ado.list(f"{p(project)}/_apis/git/repositories/{arepo['id']}/refs", params={"filter": f"heads/{META_BRANCH}"})
    if not any(r["name"] == f"refs/heads/{META_BRANCH}" for r in refs):
        return None
    git(["clone", "-q", "--branch", META_BRANCH, "--single-branch", arepo["remoteUrl"], workdir], pat=ado.pat)
    with open(os.path.join(workdir, META_FILE)) as f:
        return json.load(f)


def git_version():
    try:
        out = subprocess.run(["git", "--version"], capture_output=True, text=True, check=True).stdout
    except (OSError, subprocess.CalledProcessError):
        return None
    m = re.search(r"(\d+)\.(\d+)", out)
    return (int(m[1]), int(m[2])) if m else None


# ---------------------------------------------------------------- pre-checks

class Checks:
    def __init__(self):
        self.items, self._shown = [], 0

    def add(self, ok, name, detail="", level="fail"):
        self.items.append({"check": name, "status": "pass" if ok else level, "detail": detail})
        return ok

    def report(self):
        for c in self.items[self._shown:]:
            line = f"[{c['status'].upper():4}] {c['check']}" + (f" - {c['detail']}" if c["detail"] else "")
            warn(line) if c["status"] == "warn" else log(line)
        self._shown = len(self.items)
        failed = [c for c in self.items if c["status"] == "fail"]
        if failed:
            raise AdoError("Pre-check failed: " + "; ".join(f"{c['check']} ({c['detail']})" for c in failed))


def check_perms(checks, ado, label, ns_name, actions, token, level="fail"):
    try:
        missing = [act for act in actions if not ado.has_permission(ns_name, act, token)]
    except AdoError as e:
        return checks.add(False, f"{label} permissions", str(e), level)
    return checks.add(not missing, f"{label} permissions",
                      f"missing: {', '.join(missing)}" if missing else ", ".join(actions), level)


def precheck_basic(a, src, arc, checks):
    """Cheap checks that run before anything is collected or changed."""
    v = git_version()
    checks.add(bool(v) and v >= (2, 31), "git >= 2.31 on PATH", ".".join(map(str, v)) if v else "not found")
    lfs_ok = bool(shutil.which("git-lfs"))
    checks.add(lfs_ok, "git-lfs on PATH", "" if lfs_ok else "LFS objects will not be copied", "warn")
    for ado, label in ((src, "Source"), (arc, "Archive")):
        try:
            ado.git_ns
            checks.add(True, f"{label} PAT can read security namespaces", ado.org)
        except AdoError as e:
            checks.add(False, f"{label} PAT can read security namespaces", str(e))

    try:
        srepo = find_repo(src, a.source_project, name=a.repo)
    except AdoError as e:
        srepo = None
        checks.add(False, "Source project reachable", str(e))
    try:
        arc_project = arc.call("GET", f"_apis/projects/{p(a.archive_project)}", allow_404=True)
    except AdoError as e:
        arc_project = None
        checks.add(False, "Archive project reachable", str(e))
    name = archived_name(src.org, a.source_project, srepo["name"] if srepo else a.repo)
    existing = find_repo(arc, a.archive_project, name=name) if arc_project else None

    # When resuming, the origin may already be disabled or deleted by the failed run
    lvl = "warn" if existing and a.resume else "fail"
    checks.add(bool(srepo), "Source repo found", f"{src.org}/{a.source_project}/{a.repo}", lvl)
    if srepo:
        checks.add(not srepo.get("isDisabled"), "Source repo enabled", "" if not srepo.get("isDisabled") else "repo is disabled", lvl)
        check_perms(checks, src, "Source repo", GIT_NS_NAME, ["GenericRead", "DeleteRepository"],
                    repo_token(srepo["project"]["id"], srepo["id"]), lvl)

    checks.add(bool(arc_project), "Archive project found", f"{arc.org}/{a.archive_project}")
    if arc_project:
        if existing:
            checks.add(a.resume, "Archive copy name free",
                       f"{name} exists - " + ("resuming" if a.resume else "rerun with --resume to continue a failed archive"))
        else:
            checks.add(True, "Archive copy name free", name)
        check_perms(checks, arc, "Archive project", GIT_NS_NAME,
                    ["CreateRepository", "GenericContribute", "ManagePermissions"], f"repoV2/{arc_project['id']}")
        try:
            valid_users_descriptors(arc, a.archive_project)
            checks.add(True, "Archive 'Valid Users' groups resolvable (for read-only lock)")
        except AdoError as e:
            checks.add(False, "Archive 'Valid Users' groups resolvable (for read-only lock)", str(e))
    return srepo, arc_project, existing


def precheck_collected(a, src, meta, checks):
    """Checks that need the collected metadata (pipelines, size)."""
    builds, releases = meta["buildDefinitions"], meta["releaseDefinitions"]
    if not builds and not releases:
        checks.add(True, "No linked pipelines")
    else:
        names = ", ".join([f"build '{b['definition']['name']}'" for b in builds] +
                          [f"release '{r['definition']['name']}'" for r in releases])
        if not a.allow_pipelines:
            checks.add(False, "No linked pipelines",
                       f"{names} - retire pipelines first, or pass --allow-pipelines to disable them with the repo")
        else:
            checks.add(False, "Linked pipelines", f"will be disabled: {names}", "warn")
            for proj, pid in {(b["project"], b["projectId"]) for b in builds}:
                check_perms(checks, src, f"Build definitions in '{proj}'", "Build", ["EditBuildDefinition"], pid)
            for proj, pid in {(r["project"], r["projectId"]) for r in releases if not r.get("shared")}:
                check_perms(checks, src, f"Release definitions in '{proj}'", "ReleaseManagement", ["EditReleaseDefinition"], pid)
    shared = [r["definition"]["name"] for r in releases if r.get("shared")]
    if shared:
        checks.add(False, "Release pipelines exclusive to this repo",
                   f"also deploy other artifacts, will NOT be disabled: {', '.join(shared)}", "warn")
    need = 2 * (meta["source"]["repository"].get("size") or 0) + (200 << 20)
    free = shutil.disk_usage(tempfile.gettempdir()).free
    checks.add(free >= need, "Free disk space for mirror", f"need ~{need >> 20} MiB, free {free >> 20} MiB")


# ---------------------------------------------------------------- collect

def collect(src, project, repo):
    if repo.get("isDisabled"):
        raise AdoError(f"Repo '{repo['name']}' is disabled - enable it before archiving")
    pid, rid = repo["project"]["id"], repo["id"]

    log("Collecting refs, policies and permissions")
    log(f"Git security namespace: {src.git_ns}")
    acls = src.call("GET", f"_apis/accesscontrollists/{src.git_ns}", params={"token": repo_token(pid, rid), "recurse": "true"})["value"]
    meta = {
        "schemaVersion": 1,
        "status": "archived",
        "source": {
            "org": src.org, "project": project, "projectId": pid,
            "repository": {k: repo.get(k) for k in ("id", "name", "defaultBranch", "size", "remoteUrl", "webUrl")},
        },
        "refs": list_refs(src, project, rid),
        "policies": repo_policies(src, project, rid),
        "acls": acls,
        "identities": identity_names(src, {d for a in acls for d in a.get("acesDictionary", {})}),
        "repoPipelinePermissions": src.call(
            "GET", f"{p(project)}/_apis/pipelines/pipelinePermissions/repository/{pid}.{rid}", api=PREVIEW, allow_404=True),
        "serviceHooks": service_hooks(src, rid),
        "wikis": [w for w in src.list(f"{p(project)}/_apis/wiki/wikis") if w.get("repositoryId") == rid],
    }
    log("Collecting linked pipelines (all projects)")
    meta["buildDefinitions"], meta["releaseDefinitions"] = linked_pipelines(src, rid)
    log("Collecting service connections and pipeline resources")
    meta["pipelineResources"] = linked_resources(src, meta["buildDefinitions"], meta["releaseDefinitions"])
    return meta


def service_hooks(src, rid):
    out = []
    for s in src.list("_apis/hooks/subscriptions"):
        if (s.get("publisherInputs") or {}).get("repository") != rid:
            continue
        out.append({
            **{k: s.get(k) for k in ("id", "eventType", "publisherId", "consumerId", "consumerActionId", "status", "publisherInputs")},
            "consumerInputs": {k: v for k, v in (s.get("consumerInputs") or {}).items()
                               if not any(h in k.lower() for h in SECRET_HINTS)},
        })
    return out


def artifact_from_repo(art, rid, build_keys):
    ref = art.get("definitionReference") or {}
    did = str((ref.get("definition") or {}).get("id"))
    if art.get("type") == "Git":
        return did == rid
    if art.get("type") == "Build":
        return ((ref.get("project") or {}).get("id"), did) in build_keys
    return False


def linked_pipelines(src, rid):
    projects = src.list("_apis/projects")
    builds = []
    for proj in projects:
        pn = p(proj["name"])
        for d in src.list(f"{pn}/_apis/build/definitions",
                          params={"repositoryId": rid, "repositoryType": "TfsGit", "includeLatestBuilds": "true"}):
            builds.append({
                "project": proj["name"], "projectId": proj["id"],
                "lastRun": (d.get("latestBuild") or {}).get("finishTime"),
                "definition": src.call("GET", f"{pn}/_apis/build/definitions/{d['id']}"),
            })

    build_keys = {(b["projectId"], str(b["definition"]["id"])) for b in builds}
    releases = []
    for proj in projects:
        pn = p(proj["name"])
        try:
            defs = src.list(f"{pn}/_apis/release/definitions", host=VSRM, params={"$expand": "artifacts"})
        except AdoError as e:
            warn(f"Skipping releases in {proj['name']}: {e}")
            continue
        for d in defs:
            owned = [artifact_from_repo(art, rid, build_keys) for art in d.get("artifacts") or []]
            if not any(owned):
                continue
            last = src.call("GET", f"{pn}/_apis/release/deployments", host=VSRM,
                            params={"definitionId": d["id"], "queryOrder": "descending", "$top": 1})["value"]
            releases.append({
                "project": proj["name"], "projectId": proj["id"],
                # Also deploys artifacts from other repos -> never disabled by this script
                "shared": not all(owned),
                "lastDeployment": (last[0].get("completedOn") or last[0].get("startedOn")) if last else None,
                "definition": src.call("GET", f"{pn}/_apis/release/definitions/{d['id']}", host=VSRM),
            })
    return builds, releases


def resource_summary(rtype, item):
    if rtype == "endpoint":
        return {"type": item.get("type"), "url": item.get("url"),
                "authScheme": (item.get("authorization") or {}).get("scheme"), "isShared": item.get("isShared")}
    if rtype == "variablegroup":
        return {"variables": sorted((item.get("variables") or {}).keys())}
    if rtype == "queue":
        return {"pool": (item.get("pool") or {}).get("name")}
    return {}


def linked_resources(src, builds, releases):
    by_project = {}
    for b in builds:
        by_project.setdefault((b["projectId"], b["project"]), {"build": [], "release": []})["build"].append(b["definition"])
    for r in releases:
        by_project.setdefault((r["projectId"], r["project"]), {"build": [], "release": []})["release"].append(r["definition"])

    out = []
    for (pid, pname), defs in by_project.items():
        pn = p(pname)
        build_ids = {d["id"] for d in defs["build"]}
        blobs = {f"{kind}:{d['id']}": json.dumps(d) for kind in ("build", "release") for d in defs[kind]}
        for rtype, (path, api) in RESOURCE_APIS.items():
            try:
                items = src.list(f"{pn}/{path}", api=api)
            except AdoError as e:
                warn(f"Skipping {rtype} in {pname}: {e}")
                continue
            for item in items:
                res_id = str(item["id"])
                perms = src.call("GET", f"{pn}/_apis/pipelines/pipelinePermissions/{rtype}/{res_id}",
                                 api=PREVIEW, allow_404=True) or {}
                authorized = [x["id"] for x in perms.get("pipelines") or [] if x.get("authorized") and x["id"] in build_ids]
                open_access = bool((perms.get("allPipelines") or {}).get("authorized"))
                # Classic definitions reference service connections / secure files by GUID
                referenced = [k for k, blob in blobs.items() if rtype in ("endpoint", "securefile") and res_id in blob]
                if authorized or referenced or (open_access and build_ids):
                    out.append({
                        "type": rtype, "id": res_id, "name": item.get("name"), "project": pname, "projectId": pid,
                        "details": resource_summary(rtype, item), "authorizedPipelines": authorized,
                        "openAccess": open_access, "referencedBy": referenced,
                    })
    return out


# ---------------------------------------------------------------- document

def cell(value):
    if value in (None, "", []):
        return "–"
    return str(value).replace("|", "\\|").replace("\n", " ")


def bits(mask):
    return ", ".join(n for b, n in GIT_BITS.items() if mask & b) or "–"


def acl_scope(token):
    parts = token.split("/")[3:]
    if not parts:
        return "repository"
    try:
        return "/".join(parts[:2] + [bytes.fromhex(x).decode("utf-16-le") for x in parts[2:]])
    except ValueError:
        return "/".join(parts)


def table(headers, rows):
    lines = ["| " + " | ".join(headers) + " |", "|" + "---|" * len(headers)]
    lines += ["| " + " | ".join(cell(c) for c in row) + " |" for row in rows]
    return "\n".join(lines) if rows else "_None_"


def render_doc(meta):
    s, arc, repo = meta["source"], meta.get("archive") or {}, meta["source"]["repository"]
    ids = meta.get("identities") or {}
    branches = [r for r in meta["refs"] if r["name"].startswith("refs/heads/")]
    tags = [r for r in meta["refs"] if r["name"].startswith("refs/tags/")]
    rpp = meta.get("repoPipelinePermissions") or {}
    out = [
        f"# Archive record: {s['org']} / {s['project']} / {repo['name']}",
        "",
        table(["Field", "Value"], [
            ["Status", f"**{meta['status'].upper()}**"],
            ["Source", f"{s['org']} / {s['project']} / {repo['name']} (`{repo['id']}`)"],
            ["Archive copy", f"{arc.get('org')} / {arc.get('project')} / {arc.get('repoName')}"],
            ["Default branch", repo.get("defaultBranch")],
            ["Size (bytes)", repo.get("size")],
            ["Branches / tags", f"{len(branches)} / {len(tags)}"],
            ["Source repo after archive", meta.get("sourceAction")],
        ]),
        "",
        "## How to restore",
        "",
        "Run the `repo-archive` pipeline with `action=unarchive`, "
        f"`sourceOrg={s['org']}`, `sourceProject={s['project']}`, `repoName={repo['name']}`.",
        "It re-enables (or restores / recreates) the source repo and re-applies branch policies, permissions,",
        "build/release definitions and pipeline authorisations listed below. Service hooks and code wikis",
        "must be re-created manually **only** if the repo had to be recreated with a new id.",
        "",
        "## History",
        "",
        table(["Action", "When (UTC)", "By", "Run"], [[h["action"], h["at"], h["by"], h.get("run")] for h in meta.get("history", [])]),
        "",
        "## Pre-checks",
        "",
        table(["Check", "Result", "Detail"], [[c["check"], c["status"], c["detail"]] for c in meta.get("preflight", [])]),
        "",
        f"## Branches & tags ({len(meta['refs'])})",
        "",
        table(["Ref", "Object id"], [[r["name"], f"`{r['objectId']}`"] for r in meta["refs"]]),
        "",
        f"## Branch policies ({len(meta['policies'])})",
        "",
        table(["Type", "Branch", "Enabled", "Blocking", "Settings"], [
            [c["type"].get("displayName"),
             ", ".join(f"{sc.get('refName') or '*'} ({sc.get('matchKind', 'exact')})" for sc in c["settings"].get("scope", [])),
             c.get("isEnabled"), c.get("isBlocking"),
             json.dumps({k: v for k, v in c["settings"].items() if k != "scope"})[:300]]
            for c in meta["policies"]]),
        "",
        "## Repository permissions (explicit entries)",
        "",
        table(["Identity", "Scope", "Allow", "Deny"], [
            [ids.get(d, d), acl_scope(acl["token"]), bits(e.get("allow", 0)), bits(e.get("deny", 0))]
            for acl in meta["acls"] for d, e in acl.get("acesDictionary", {}).items()]),
        "",
        f"## Pipelines building from this repo ({len(meta['buildDefinitions'])})",
        "",
        table(["Project", "Id", "Name", "Kind", "Queue status", "Last run"], [
            [b["project"], b["definition"]["id"], b["definition"]["name"],
             "YAML" if (b["definition"].get("process") or {}).get("type") == 2 else "Classic",
             b["definition"].get("queueStatus"), b.get("lastRun")]
            for b in meta["buildDefinitions"]]),
        "",
        f"## Release pipelines deploying this repo ({len(meta['releaseDefinitions'])})",
        "",
        table(["Project", "Id", "Name", "Shared", "Disabled", "Last deployment"], [
            [r["project"], r["definition"]["id"], r["definition"]["name"], r.get("shared", False),
             r["definition"].get("isDisabled", False), r.get("lastDeployment")]
            for r in meta["releaseDefinitions"]]),
        "",
        "_Shared release pipelines also deploy other artifacts and are left enabled on archive._"
        if any(r.get("shared") for r in meta["releaseDefinitions"]) else "",
        "",
        f"## Service connections & pipeline resources ({len(meta['pipelineResources'])})",
        "",
        table(["Type", "Name", "Project", "Details", "Authorised pipelines", "Open to all", "Referenced by"], [
            [r["type"], r["name"], r["project"], json.dumps(r["details"]) if r["details"] else None,
             ", ".join(map(str, r["authorizedPipelines"])), r["openAccess"], ", ".join(r["referencedBy"])]
            for r in meta["pipelineResources"]]),
        "",
        "## Pipelines authorised to use this repo",
        "",
        table(["Pipeline id", "Authorised"], [[x["id"], x.get("authorized")] for x in rpp.get("pipelines") or []])
        + ("\n\n_Open to all pipelines._" if (rpp.get("allPipelines") or {}).get("authorized") else ""),
        "",
        f"## Service hooks ({len(meta['serviceHooks'])})",
        "",
        table(["Id", "Event", "Consumer", "Action", "Status"], [
            [h["id"], h["eventType"], h["consumerId"], h["consumerActionId"], h["status"]] for h in meta["serviceHooks"]]),
        "",
        f"## Code wikis ({len(meta['wikis'])})",
        "",
        table(["Name", "Mapped path", "Versions"], [
            [w["name"], w.get("mappedPath"), ", ".join(v.get("version", "") for v in w.get("versions") or [])] for w in meta["wikis"]]),
        "",
    ]
    return "\n".join(out)


def write_outputs(out_dir, meta):
    os.makedirs(out_dir, exist_ok=True)
    with open(os.path.join(out_dir, META_FILE), "w") as f:
        json.dump(meta, f, indent=2)
    with open(os.path.join(out_dir, DOC_FILE), "w") as f:
        f.write(render_doc(meta))


def commit_record(workdir, meta, url, pat, message):
    write_outputs(workdir, meta)
    git(["add", "-A"], cwd=workdir)
    git(["commit", "-q", "-m", message], cwd=workdir, config=BOT)
    git(["push", "-q", url, f"HEAD:refs/heads/{META_BRANCH}"], cwd=workdir, pat=pat)


def summary(meta):
    s = meta["source"]
    log(f"Repo          : {s['org']}/{s['project']}/{s['repository']['name']} ({s['repository']['id']})")
    for label, key in (("Refs", "refs"), ("Policies", "policies"), ("ACLs", "acls"),
                       ("Build defs", "buildDefinitions"), ("Release defs", "releaseDefinitions"),
                       ("Resources", "pipelineResources"), ("Service hooks", "serviceHooks"), ("Wikis", "wikis")):
        log(f"{label:<14}: {len(meta.get(key) or [])}")


# ---------------------------------------------------------------- archive

def retire_source(src, meta, action):
    # Idempotent: a resumed run may find some of this already done
    for b in meta["buildDefinitions"]:
        path = f"{p(b['project'])}/_apis/build/definitions/{b['definition']['id']}"
        d = src.call("GET", path, allow_404=True)
        if not d:
            warn(f"Build definition {b['project']}/{b['definition']['name']} not found - skipped")
            continue
        if d.get("queueStatus") != "disabled":
            d["queueStatus"] = "disabled"
            src.call("PUT", path, body=d)
        log(f"Disabled build definition {b['project']}/{d['name']}")
    for r in meta["releaseDefinitions"]:
        if r.get("shared"):
            log(f"Kept release definition {r['project']}/{r['definition']['name']} enabled (shared with other artifacts)")
            continue
        pn = p(r["project"])
        d = src.call("GET", f"{pn}/_apis/release/definitions/{r['definition']['id']}", host=VSRM, allow_404=True)
        if not d:
            warn(f"Release definition {r['project']}/{r['definition']['name']} not found - skipped")
            continue
        if not d.get("isDisabled"):
            d["isDisabled"] = True
            src.call("PUT", f"{pn}/_apis/release/definitions", host=VSRM, body=d)
        log(f"Disabled release definition {r['project']}/{d['name']}")
    s = meta["source"]
    path = f"{p(s['project'])}/_apis/git/repositories/{s['repository']['id']}"
    if action == "delete":
        src.call("DELETE", path, allow_404=True)
        log("Source repo deleted (recoverable from recycle bin for 30 days)")
    else:
        src.call("PATCH", path, body={"isDisabled": True})
        log("Source repo disabled")


def do_archive(a, src, arc):
    log("Pre-checks")
    checks = Checks()
    srepo, arc_project, existing = precheck_basic(a, src, arc, checks)
    checks.report()
    name = existing["name"] if existing else archived_name(src.org, a.source_project, srepo["name"])

    with tempfile.TemporaryDirectory() as tmp:
        record = os.path.join(tmp, "record")
        meta = load_record(arc, a.archive_project, existing, record) if existing else None
        resumed = meta is not None
        if resumed:
            if meta.get("status") != "archived":
                raise AdoError(f"Record on {name} has status '{meta.get('status')}' - nothing to resume")
            # Use the recorded snapshot: the origin may already be partly retired
            log("Resume: copy and record already exist - re-applying lock and retiring origin")
        else:
            if not srepo:
                raise AdoError("Source repo not found and no archive record to resume from")
            meta = collect(src, a.source_project, srepo)
            precheck_collected(a, src, meta, checks)
            checks.report()
            meta["archive"] = {"org": arc.org, "project": a.archive_project, "projectId": arc_project["id"],
                               "repoName": name, "repoId": existing["id"] if existing else None,
                               "metadataBranch": META_BRANCH}
            meta["sourceAction"] = a.source_action
            meta["history"] = [{"action": "archived", **run_info()}]
            meta["preflight"] = checks.items
        summary(meta)
        write_outputs(a.out, meta)
        if a.dry_run:
            log(f"Dry run - would {'resume ' if existing else ''}archive to {arc.org}/{a.archive_project}/{name} "
                f"and {meta['sourceAction']} the source")
            return

        target = existing
        if not resumed:
            srepo_meta = meta["source"]["repository"]
            mirror = os.path.join(tmp, "mirror.git")
            git(["clone", "-q", "--mirror", srepo_meta["remoteUrl"], mirror], pat=src.pat)
            if meta["refs"]:
                lfs(["fetch", "--all", "origin"], mirror, src.pat)
            if not target:
                target = arc.call("POST", f"{p(a.archive_project)}/_apis/git/repositories",
                                  body={"name": name, "project": {"id": arc_project["id"]}})
                log(f"Created {arc.org}/{a.archive_project}/{name}")
            meta["archive"].update(repoId=target["id"], webUrl=target.get("webUrl"))
            if meta["refs"]:
                copy_refs(mirror, target["remoteUrl"], arc.pat)
            verify_refs(arc, a.archive_project, target["id"], meta["refs"])
            if srepo_meta.get("defaultBranch"):
                arc.call("PATCH", f"{p(a.archive_project)}/_apis/git/repositories/{target['id']}",
                         body={"defaultBranch": srepo_meta["defaultBranch"]})
            os.makedirs(record)
            git(["init", "-q", "-b", META_BRANCH], cwd=record)
            commit_record(record, meta, target["remoteUrl"], arc.pat,
                          f"Archive record for {src.org}/{a.source_project}/{srepo_meta['name']}")
        set_readonly(arc, a.archive_project, arc_project["id"], target["id"], True)

    retire_source(src, meta, meta["sourceAction"])
    write_outputs(a.out, meta)
    log(f"Archived. Review record: {target.get('webUrl')}?version=GB{META_BRANCH}&path=/{DOC_FILE}")


# ---------------------------------------------------------------- unarchive

def restore_repo(src, meta, arepo, arc_pat, tmp):
    s = meta["source"]
    project, old = s["project"], s["repository"]
    pn = p(project)
    repo = find_repo(src, project, repo_id=old["id"])
    if not repo:
        deleted = src.list(f"{pn}/_apis/git/recycleBin/repositories", api=PREVIEW)
        if any(r["id"] == old["id"] for r in deleted):
            src.call("PATCH", f"{pn}/_apis/git/recycleBin/repositories/{old['id']}", api=PREVIEW, body={"deleted": False})
            log("Source repo restored from recycle bin")
            repo = find_repo(src, project, repo_id=old["id"])

    recreated = False
    if not repo:
        if find_repo(src, project, name=old["name"]):
            raise AdoError(f"A different repo named '{old['name']}' now exists in {src.org}/{project}")
        repo = src.call("POST", f"{pn}/_apis/git/repositories", body={"name": old["name"], "project": {"id": s["projectId"]}})
        recreated = True
        log(f"Source repo recreated with new id {repo['id']}")
        if meta["refs"]:
            mirror = os.path.join(tmp, "mirror.git")
            git(["clone", "-q", "--mirror", arepo["remoteUrl"], mirror], pat=arc_pat)
            git(["update-ref", "-d", f"refs/heads/{META_BRANCH}"], cwd=mirror)
            lfs(["fetch", "--all", "origin"], mirror, arc_pat)
            copy_refs(mirror, repo["remoteUrl"], src.pat)

    if repo.get("isDisabled"):
        src.call("PATCH", f"{pn}/_apis/git/repositories/{repo['id']}", body={"isDisabled": False})
        log("Source repo re-enabled")
    verify_refs(src, project, repo["id"], meta["refs"])
    if old.get("defaultBranch") and repo.get("defaultBranch") != old["defaultBranch"]:
        src.call("PATCH", f"{pn}/_apis/git/repositories/{repo['id']}", body={"defaultBranch": old["defaultBranch"]})
    return repo, recreated


def find_build_def(src, pn, d0):
    """Find a definition recreated by an earlier (failed) unarchive, to avoid duplicates."""
    for d in src.list(f"{pn}/_apis/build/definitions", params={"name": d0["name"]}):
        if d.get("path") == d0.get("path"):
            return src.call("GET", f"{pn}/_apis/build/definitions/{d['id']}")
    return None


def find_release_def(src, pn, d0):
    for d in src.list(f"{pn}/_apis/release/definitions", host=VSRM,
                      params={"searchText": d0["name"], "isExactNameMatch": "true"}):
        if d.get("path", "\\") == d0.get("path", "\\"):
            return src.call("GET", f"{pn}/_apis/release/definitions/{d['id']}", host=VSRM)
    return None


def restore_builds(src, meta, old_id, new_id):
    id_map = {}
    for b in meta["buildDefinitions"]:
        d0 = b["definition"]
        pn = p(b["project"])
        path = f"{pn}/_apis/build/definitions/{d0['id']}"
        cur = src.call("GET", path, allow_404=True)
        if cur is None:
            try:
                src.call("PATCH", path, params={"deleted": "false"})
                cur = src.call("GET", path, allow_404=True)
            except AdoError:
                cur = None
        if cur is None:
            cur = find_build_def(src, pn, d0)
        if cur is None:
            body = {k: v for k, v in d0.items() if k not in BUILD_READONLY}
            if body["repository"].get("id") == old_id:
                body["repository"]["id"] = new_id
            cur = src.call("POST", f"{pn}/_apis/build/definitions", body=body)
            log(f"Recreated build definition {b['project']}/{cur['name']} as id {cur['id']}")
        else:
            if cur["repository"].get("id") == old_id:
                cur["repository"]["id"] = new_id
            cur["queueStatus"] = d0.get("queueStatus", "enabled")
            src.call("PUT", f"{pn}/_apis/build/definitions/{cur['id']}", body=cur)
            log(f"Restored build definition {b['project']}/{cur['name']} ({cur['queueStatus']})")
        id_map[(b["projectId"], d0["id"])] = cur["id"]
    return id_map


def restore_releases(src, meta, old_id, new_id, id_map):
    for r in meta["releaseDefinitions"]:
        d0 = r["definition"]
        pn = p(r["project"])
        cur = (src.call("GET", f"{pn}/_apis/release/definitions/{d0['id']}", host=VSRM, allow_404=True)
               or find_release_def(src, pn, d0))
        body = cur or {k: v for k, v in d0.items() if k not in RELEASE_READONLY}
        for art in body.get("artifacts") or []:
            ref = art.get("definitionReference") or {}
            dref = ref.get("definition") or {}
            if art.get("type") == "Git" and dref.get("id") == old_id:
                dref["id"] = new_id
            elif art.get("type") == "Build" and str(dref.get("id", "")).isdigit():
                key = ((ref.get("project") or {}).get("id"), int(dref["id"]))
                if key in id_map:
                    dref["id"] = str(id_map[key])
        # Shared releases were never disabled; keep whatever state their owners set since
        if not (r.get("shared") and cur):
            body["isDisabled"] = d0.get("isDisabled", False)
        src.call("PUT" if cur else "POST", f"{pn}/_apis/release/definitions", host=VSRM, body=body)
        log(f"{'Restored' if cur else 'Recreated'} release definition {r['project']}/{d0['name']}")


def restore_policies(src, meta, new_id, id_map):
    s = meta["source"]
    old_id = s["repository"]["id"]
    existing = {c["id"] for c in repo_policies(src, s["project"], new_id)}
    for c in meta["policies"]:
        if c["id"] in existing:
            continue
        settings = json.loads(json.dumps(c["settings"]).replace(old_id, new_id))
        if "buildDefinitionId" in settings:
            settings["buildDefinitionId"] = id_map.get((s["projectId"], settings["buildDefinitionId"]), settings["buildDefinitionId"])
        src.call("POST", f"{p(s['project'])}/_apis/policy/configurations", body={
            "isEnabled": c.get("isEnabled", True), "isBlocking": c.get("isBlocking", True),
            "type": {"id": c["type"]["id"]}, "settings": settings,
        })
        log(f"Recreated policy '{c['type'].get('displayName')}'")


def restore_acls(src, meta, old_id, new_id):
    names = meta.get("identities") or {}
    failed = 0
    for acl in meta["acls"]:
        token = acl["token"].replace(old_id, new_id)
        aces = [{"descriptor": d, "allow": e.get("allow", 0), "deny": e.get("deny", 0)}
                for d, e in (acl.get("acesDictionary") or {}).items()]
        try:
            src.call("POST", f"_apis/accesscontrollists/{src.git_ns}", body={"value": [{
                "token": token, "inheritPermissions": acl.get("inheritPermissions", True),
                "acesDictionary": {x["descriptor"]: x for x in aces}}]})
            continue
        except AdoError as e:
            warn(f"ACL on {acl_scope(token)} failed as a whole ({e}) - retrying entry by entry")
        for ace in aces:
            try:
                src.call("POST", f"_apis/accesscontrolentries/{src.git_ns}",
                         body={"token": token, "merge": False, "accessControlEntries": [ace]})
            except AdoError as e:
                failed += 1
                warn(f"Could not restore permission for {names.get(ace['descriptor'], ace['descriptor'])} "
                     f"on {acl_scope(token)}: {e}")
    log(f"Re-applied {len(meta['acls'])} ACLs" + (f" ({failed} entries failed - see warnings)" if failed else ""))


def authorize(src, project, resource, pipelines, all_pipelines=False):
    body = {"pipelines": [{"id": i, "authorized": True} for i in pipelines]}
    if all_pipelines:
        body["allPipelines"] = {"authorized": True}
    if pipelines or all_pipelines:
        src.call("PATCH", f"{p(project)}/_apis/pipelines/pipelinePermissions/{resource}", api=PREVIEW, body=body)


def restore_pipeline_permissions(src, meta, new_id, id_map):
    s = meta["source"]
    rpp = meta.get("repoPipelinePermissions") or {}
    authorize(src, s["project"], f"repository/{s['projectId']}.{new_id}",
              [id_map.get((s["projectId"], x["id"]), x["id"]) for x in rpp.get("pipelines") or [] if x.get("authorized")],
              bool((rpp.get("allPipelines") or {}).get("authorized")))
    for r in meta["pipelineResources"]:
        try:
            authorize(src, r["project"], f"{r['type']}/{r['id']}",
                      [id_map.get((r["projectId"], i), i) for i in r["authorizedPipelines"]])
        except AdoError as e:
            warn(f"Could not re-authorise {r['type']} '{r['name']}': {e}")
    log("Pipeline authorisations re-applied")


def do_unarchive(a, src, arc):
    name = archived_name(src.org, a.source_project, a.repo)
    arepo = find_repo(arc, a.archive_project, name=name)
    if not arepo:
        raise AdoError(f"No archive copy {arc.org}/{a.archive_project}/{name}")

    with tempfile.TemporaryDirectory() as tmp:
        record = os.path.join(tmp, "record")
        meta = load_record(arc, a.archive_project, arepo, record)
        if meta is None:
            raise AdoError(f"{arc.org}/{a.archive_project}/{name} has no '{META_BRANCH}' branch - archive never completed")
        if meta.get("status") != "archived":
            raise AdoError(f"Archive record status is '{meta.get('status')}', expected 'archived'")
        summary(meta)
        if a.dry_run:
            write_outputs(a.out, meta)
            log(f"Dry run - would restore {src.org}/{a.source_project}/{a.repo} from {arc.org}/{a.archive_project}/{name}")
            return

        old_id = meta["source"]["repository"]["id"]
        repo, recreated = restore_repo(src, meta, arepo, arc.pat, tmp)
        new_id = repo["id"]
        id_map = restore_builds(src, meta, old_id, new_id)
        restore_releases(src, meta, old_id, new_id, id_map)
        restore_policies(src, meta, new_id, id_map)
        restore_acls(src, meta, old_id, new_id)
        restore_pipeline_permissions(src, meta, new_id, id_map)
        if new_id != old_id:
            for h in meta["serviceHooks"]:
                warn(f"Recreate service hook {h['eventType']} -> {h['consumerId']} (old id {h['id']}) manually")
            for w in meta["wikis"]:
                warn(f"Re-publish code wiki '{w['name']}' manually")

        meta["status"] = "unarchived"
        meta["source"]["repository"]["id"] = new_id
        meta["history"].append({"action": "unarchived", **run_info(), "recreated": recreated, "previousRepoId": old_id})
        new_name = f"{name}_unarchived-{dt.datetime.now(dt.timezone.utc):%Y%m%d%H%M}"
        meta["archive"]["repoName"] = new_name

        aproj_id = arepo["project"]["id"]
        set_readonly(arc, a.archive_project, aproj_id, arepo["id"], False)
        try:
            commit_record(record, meta, arepo["remoteUrl"], arc.pat, f"Unarchived to {src.org}/{a.source_project}")
        finally:
            set_readonly(arc, a.archive_project, aproj_id, arepo["id"], True)
        arc.call("PATCH", f"{p(a.archive_project)}/_apis/git/repositories/{arepo['id']}", body={"name": new_name})
        log(f"Archive copy kept read-only as {new_name}")

    write_outputs(a.out, meta)
    log(f"Unarchived {src.org}/{a.source_project}/{a.repo}")


# ---------------------------------------------------------------- main

def main():
    env = os.environ.get
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("action", nargs="?", choices=["archive", "unarchive"], default=env("RA_ACTION"))
    ap.add_argument("--source-org", default=env("RA_SOURCE_ORG"))
    ap.add_argument("--source-project", default=env("RA_SOURCE_PROJECT"))
    ap.add_argument("--repo", default=env("RA_REPO"))
    ap.add_argument("--archive-org", default=env("RA_ARCHIVE_ORG"))
    ap.add_argument("--archive-project", default=env("RA_ARCHIVE_PROJECT"))
    ap.add_argument("--source-action", choices=["disable", "delete"], default=env("RA_SOURCE_ACTION", "disable"))
    ap.add_argument("--dry-run", choices=["true", "false"], default=env("RA_DRY_RUN", "true").lower())
    ap.add_argument("--resume", action="store_true", default=env("RA_RESUME", "false").lower() == "true",
                    help="archive: continue a previously failed run using the existing archive copy")
    ap.add_argument("--allow-pipelines", action="store_true",
                    default=env("RA_ALLOW_PIPELINES", "false").lower() == "true",
                    help="archive: allow repos with linked pipelines (they are disabled with the repo)")
    ap.add_argument("--out", default=env("RA_OUT", "out"))
    a = ap.parse_args()
    a.dry_run = a.dry_run == "true"
    missing = [k for k in ("action", "source_org", "source_project", "repo", "archive_org", "archive_project") if not getattr(a, k)]
    if missing:
        ap.error(f"missing: {', '.join(missing)}")

    try:
        src = Ado(a.source_org, env("SOURCE_PAT"))
        arc = Ado(a.archive_org, env("ARCHIVE_PAT"))
        (do_archive if a.action == "archive" else do_unarchive)(a, src, arc)
    except (AdoError, subprocess.CalledProcessError) as e:
        print(f"##vso[task.logissue type=error]{e}", flush=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
