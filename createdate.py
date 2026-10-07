#!/usr/bin/env python3
"""pipeline_created_date.py — Fetch the creation date of a classic build/release pipeline.

USAGE:
    python scripts/pipeline_created_date.py --org myorg --project myproj --pipeline-id 42 --pat $PAT
    python scripts/pipeline_created_date.py --org myorg --project myproj --pipeline-name "CI-Main" \\
        --pats-config config/pats.yml
    python scripts/pipeline_created_date.py --org myorg --project myproj --pipeline-id 7 \\
        --type release --pat $PAT

PAT resolution order: --pat, AZDO_PAT env var, --pats-config (entry for --org).
Required PAT scopes: Build (Read), Release (Read).
"""
from __future__ import annotations

import os
import sys

_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
_LIGHTCLI_ROOT = os.path.dirname(_SCRIPT_DIR)
if _LIGHTCLI_ROOT not in sys.path:
    sys.path.insert(0, _LIGHTCLI_ROOT)

import argparse
import json
from typing import Any

import yaml

from engine.extractor.azure_api_client import AzureDevOpsApiClient

API_VERSION = "7.1"


def _load_pats(pats_config: str) -> dict[str, str]:
    with open(pats_config, encoding="utf-8") as fh:
        data = yaml.safe_load(fh) or {}
    orgs = data.get("organizations") or data.get("orgs") or {}
    return {
        str(k).strip(): str(v.get("pat") if isinstance(v, dict) else v).strip()
        for k, v in orgs.items()
        if v
    }


def _resolve_pat(args: argparse.Namespace) -> str:
    if args.pat:
        return args.pat
    env_pat = os.environ.get("AZDO_PAT", "").strip()
    if env_pat:
        return env_pat
    if args.pats_config:
        pats = _load_pats(args.pats_config)
        if args.org in pats:
            return pats[args.org]
        sys.exit(f"ERROR: No PAT for org '{args.org}' in {args.pats_config}")
    sys.exit("ERROR: Provide --pat, set AZDO_PAT, or pass --pats-config.")


def _find_build_ids(client: AzureDevOpsApiClient, name: str) -> list[int]:
    url = f"{client.base_url}/_apis/build/definitions"
    data = client._request("GET", url, params={"name": name, "api-version": API_VERSION})
    return [int(d["id"]) for d in data.get("value", []) if "id" in d]


def _find_release_ids(client: AzureDevOpsApiClient, name: str) -> list[int]:
    url = f"{client.vsrm_base_url}/_apis/release/definitions"
    params = {"searchText": name, "isExactNameMatch": "true", "api-version": API_VERSION}
    data = client._request("GET", url, params=params)
    return [int(d["id"]) for d in data.get("value", []) if "id" in d]


def _build_created(client: AzureDevOpsApiClient, pipeline_id: int) -> dict[str, Any]:
    definition = client._request(
        "GET",
        f"{client.base_url}/_apis/build/definitions/{pipeline_id}",
        params={"api-version": API_VERSION},
    )
    # Definition's own createdDate reflects the latest revision; revision 1 is the true creation.
    revisions = client._request(
        "GET",
        f"{client.base_url}/_apis/build/definitions/{pipeline_id}/revisions",
        params={"api-version": API_VERSION},
    ).get("value", [])
    first = min(revisions, key=lambda r: r.get("revision", 0)) if revisions else {}
    return {
        "type": "build",
        "id": pipeline_id,
        "name": definition.get("name"),
        "path": definition.get("path"),
        "createdDate": first.get("changedDate") or definition.get("createdDate"),
        "createdBy": (first.get("changedBy") or {}).get("displayName"),
        "currentRevision": definition.get("revision"),
        "lastModifiedDate": definition.get("createdDate"),
    }


def _release_created(client: AzureDevOpsApiClient, pipeline_id: int) -> dict[str, Any]:
    definition = client._request(
        "GET",
        f"{client.vsrm_base_url}/_apis/release/definitions/{pipeline_id}",
        params={"api-version": API_VERSION},
    )
    return {
        "type": "release",
        "id": pipeline_id,
        "name": definition.get("name"),
        "path": definition.get("path"),
        "createdDate": definition.get("createdOn"),
        "createdBy": (definition.get("createdBy") or {}).get("displayName"),
        "currentRevision": definition.get("revision"),
        "lastModifiedDate": definition.get("modifiedOn"),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Fetch classic pipeline creation date.")
    parser.add_argument("--org", required=True)
    parser.add_argument("--project", required=True)
    target = parser.add_mutually_exclusive_group(required=True)
    target.add_argument("--pipeline-id", type=int)
    target.add_argument("--pipeline-name")
    parser.add_argument("--type", choices=["build", "release"], default="build")
    parser.add_argument("--pat")
    parser.add_argument("--pats-config")
    parser.add_argument("--json", action="store_true", help="Output JSON")
    args = parser.parse_args()

    client = AzureDevOpsApiClient(args.org, args.project, _resolve_pat(args))

    if args.pipeline_id is not None:
        ids = [args.pipeline_id]
    else:
        finder = _find_build_ids if args.type == "build" else _find_release_ids
        ids = finder(client, args.pipeline_name)
        if not ids:
            sys.exit(f"ERROR: No {args.type} pipeline named '{args.pipeline_name}' found.")

    fetch = _build_created if args.type == "build" else _release_created
    try:
        results = [fetch(client, pid) for pid in ids]
    except RuntimeError as exc:
        sys.exit(f"ERROR: {exc}")

    if args.json:
        print(json.dumps(results, indent=2))
        return
    for r in results:
        print(
            f"[{r['type']}] #{r['id']} {(r['path'] or '').rstrip(chr(92))}\\{r['name']}\n"
            f"  Created:       {r['createdDate']} by {r['createdBy']}\n"
            f"  Last modified: {r['lastModifiedDate']} (rev {r['currentRevision']})"
        )


if __name__ == "__main__":
    main()
