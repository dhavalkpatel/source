#!/usr/bin/env python3
"""pipeline_created_date.py — Scan a tenant for classic build/release pipelines and their creation dates.

USAGE:
    # Orgs + PATs from config file
    python scripts/pipeline_created_date.py --pats-config config/pats.yml

    # Single PAT, auto-discover every org the PAT's user belongs to
    # (PAT must be created with "All accessible organizations")
    python scripts/pipeline_created_date.py --pat $PAT

    # Single PAT, explicit org list
    python scripts/pipeline_created_date.py --pat $PAT --orgs org1 org2 --output out.csv

PAT resolution: --pats-config, else --pat / AZDO_PAT env var.
Required PAT scopes: Project and Team (Read), Build (Read), Release (Read);
plus User Profile (Read) for org auto-discovery.
"""
from __future__ import annotations

import argparse
import csv
import os
import sys
from typing import Any, Iterator
from urllib.parse import quote

import requests
import yaml

API_VERSION = "7.1"
VSSPS_URL = "https://app.vssps.visualstudio.com"
TIMEOUT = 30
CSV_FIELDS = [
    "org", "project", "type", "id", "name", "path",
    "created_date", "created_by", "last_modified", "revision",
]


def _load_pats(pats_config: str) -> dict[str, str]:
    with open(pats_config, encoding="utf-8") as fh:
        data = yaml.safe_load(fh) or {}
    orgs = data.get("organizations") or data.get("orgs") or {}
    return {
        str(k).strip(): str(v.get("pat") if isinstance(v, dict) else v).strip()
        for k, v in orgs.items()
        if v
    }


def _session(pat: str) -> requests.Session:
    s = requests.Session()
    s.auth = ("", pat)
    s.headers.update({"Accept": "application/json"})
    return s


def _get(session: requests.Session, url: str, params: dict[str, Any] | None = None) -> requests.Response:
    params = {"api-version": API_VERSION, **(params or {})}
    resp = session.get(url, params=params, timeout=TIMEOUT, allow_redirects=False)
    # Azure DevOps answers an invalid/expired PAT with 203 or a 302 to the sign-in page.
    if resp.status_code in (203, 302):
        raise RuntimeError(f"Authentication failed for {url} (HTTP {resp.status_code})")
    if not resp.ok:
        raise RuntimeError(f"HTTP {resp.status_code} for {url}: {resp.text[:200]}")
    return resp


def _paged(session: requests.Session, url: str, params: dict[str, Any] | None = None) -> Iterator[dict[str, Any]]:
    params = dict(params or {})
    while True:
        resp = _get(session, url, params)
        yield from resp.json().get("value", [])
        token = resp.headers.get("x-ms-continuationtoken")
        if not token:
            return
        params["continuationToken"] = token


def _discover_orgs(session: requests.Session) -> list[str]:
    me = _get(session, f"{VSSPS_URL}/_apis/profile/profiles/me").json()
    accounts = _get(session, f"{VSSPS_URL}/_apis/accounts", {"memberId": me["id"]}).json()
    return sorted(a["accountName"] for a in accounts.get("value", []))


def _list_projects(session: requests.Session, org: str) -> list[str]:
    url = f"https://dev.azure.com/{quote(org)}/_apis/projects"
    return [p["name"] for p in _paged(session, url, {"$top": 500})]


def _classic_builds(session: requests.Session, org: str, project: str) -> Iterator[dict[str, Any]]:
    base = f"https://dev.azure.com/{quote(org)}/{quote(project)}/_apis/build/definitions"
    # processType=1 → designer (classic) pipelines only; YAML is 2.
    for d in _paged(session, base, {"processType": 1, "$top": 500}):
        # The definition's createdDate is the latest revision date; revision 1 is the true creation.
        revisions = _get(session, f"{base}/{d['id']}/revisions").json().get("value", [])
        first = min(revisions, key=lambda r: r.get("revision", 0)) if revisions else {}
        yield {
            "org": org,
            "project": project,
            "type": "build",
            "id": d["id"],
            "name": d.get("name"),
            "path": d.get("path"),
            "created_date": first.get("changedDate") or d.get("createdDate"),
            "created_by": (first.get("changedBy") or {}).get("displayName"),
            "last_modified": d.get("createdDate"),
            "revision": d.get("revision"),
        }


def _classic_releases(session: requests.Session, org: str, project: str) -> Iterator[dict[str, Any]]:
    url = f"https://vsrm.dev.azure.com/{quote(org)}/{quote(project)}/_apis/release/definitions"
    for d in _paged(session, url, {"$top": 500}):
        yield {
            "org": org,
            "project": project,
            "type": "release",
            "id": d["id"],
            "name": d.get("name"),
            "path": d.get("path"),
            "created_date": d.get("createdOn"),
            "created_by": (d.get("createdBy") or {}).get("displayName"),
            "last_modified": d.get("modifiedOn"),
            "revision": d.get("revision"),
        }


def _org_sessions(args: argparse.Namespace) -> dict[str, requests.Session]:
    if args.pats_config:
        pats = _load_pats(args.pats_config)
        if args.orgs:
            pats = {o: p for o, p in pats.items() if o in args.orgs}
        if not pats:
            sys.exit("ERROR: No matching orgs with PATs found in config.")
        return {org: _session(pat) for org, pat in pats.items()}

    pat = args.pat or os.environ.get("AZDO_PAT", "").strip()
    if not pat:
        sys.exit("ERROR: Provide --pats-config, --pat, or set AZDO_PAT.")
    session = _session(pat)
    orgs = args.orgs or _discover_orgs(session)
    if not orgs:
        sys.exit("ERROR: No organizations discovered for this PAT.")
    return {org: session for org in orgs}


def main() -> None:
    parser = argparse.ArgumentParser(description="Scan all orgs/projects for classic pipeline creation dates.")
    parser.add_argument("--pats-config", help="YAML with per-org PATs (see config/pats.example.yml)")
    parser.add_argument("--pat", help="Single PAT (or set AZDO_PAT)")
    parser.add_argument("--orgs", nargs="+", help="Limit scan to these orgs (default: all)")
    parser.add_argument("--type", choices=["build", "release", "all"], default="all")
    parser.add_argument("--output", default="classic-pipelines.csv", help="CSV output path")
    args = parser.parse_args()

    try:
        org_sessions = _org_sessions(args)
    except RuntimeError as exc:
        sys.exit(f"ERROR: {exc}")

    scanners = []
    if args.type in ("build", "all"):
        scanners.append(_classic_builds)
    if args.type in ("release", "all"):
        scanners.append(_classic_releases)

    total = 0
    with open(args.output, "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=CSV_FIELDS)
        writer.writeheader()
        for org, session in org_sessions.items():
            try:
                projects = _list_projects(session, org)
            except RuntimeError as exc:
                print(f"[{org}] skipped: {exc}", file=sys.stderr)
                continue
            print(f"[{org}] {len(projects)} project(s)", file=sys.stderr)
            for project in projects:
                for scan in scanners:
                    count = 0
                    try:
                        for row in scan(session, org, project):
                            writer.writerow(row)
                            count += 1
                    except RuntimeError as exc:
                        print(f"  [{project}] {scan.__name__} failed: {exc}", file=sys.stderr)
                    total += count
                    if count:
                        print(f"  [{project}] {scan.__name__.lstrip('_')}: {count}", file=sys.stderr)
                fh.flush()

    print(f"\nDone. {total} classic pipeline(s) written to {args.output}")


if __name__ == "__main__":
    main()
