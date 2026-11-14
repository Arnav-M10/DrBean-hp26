"""Frozen evaluation manifest: cases, sources, holdouts, schedule and caps."""
from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timezone

from . import CONTRACT_REVISION, CONTRACT_SOURCE_SHA256, HARNESS_VERSION, WIRE_PROFILE
from .assertions import validate_assertion
from .budget import DEFAULT_CAPS, INVOCATION_LIMITS

CASE_IDS = [f"C{n:02d}" for n in range(1, 13)]
LANES = ("fixture_contract", "live_intake", "live_agent_controlled_tools", "actual_full_stack",
         "offline_real_science")
MODES = {
    "fixture_contract": "fixture_contract",
    "live_intake": "live_model_controlled_tools",
    "live_agent_controlled_tools": "live_model_controlled_tools",
    "actual_full_stack": "actual_full_stack",
    "offline_real_science": "actual_local_science_no_model",
}
# Per-lane evidence rules (manifest v2). Old lanes keep their v1 meaning; the live
# lanes are retained but disabled. offline_real_science is new: real API, worker
# and scientific tools, absent or controlled AI, verified zero model dispatch and
# no provider cohort.
LANE_RULES = {
    "fixture_contract": {"version": 1, "provider": ["controlled", "none"], "tools": None, "live_provider": False,
                         "cohort": False, "enabled": True, "zero_dispatch_required": False,
                         "meaning": "offline controlled model/application boundary; never evidence about Gemini or science"},
    "live_intake": {"version": 1, "provider": ["live"], "tools": None, "live_provider": True, "cohort": True,
                    "enabled": False, "zero_dispatch_required": False,
                    "meaning": "future live Gemini intake; NOT_RUN until a new explicit user instruction"},
    "live_agent_controlled_tools": {"version": 1, "provider": ["live"], "tools": "controlled", "live_provider": True,
                                    "cohort": True, "enabled": False, "zero_dispatch_required": False,
                                    "meaning": "future live Gemini agent decisions; NOT_RUN"},
    "actual_full_stack": {"version": 1, "provider": ["live"], "tools": "real", "live_provider": True, "cohort": True,
                          "enabled": False, "zero_dispatch_required": False,
                          "meaning": "v1 lane coupling real science to a live provider; retained, disabled, NOT_RUN"},
    "offline_real_science": {"version": 1, "provider": ["none", "controlled"], "tools": "real",
                             "live_provider": False, "cohort": False, "enabled": True, "zero_dispatch_required": True,
                             "meaning": "actual local API, worker and science through HTTP; zero external model dispatch"},
}
LIVE_ACTIVATION = ("disabled: live lanes are NOT_RUN. Activation requires a new explicit user instruction, one shared "
                   "accounted allocation, Owner 3's operator path and independent grading of predeclared cases. "
                   "The CLI has no switch for it.")
SCIENCE_PACKETS = ("hero-v1", "hero-v2", "changed-input-v1", "fixed-pair-regression-v1")
OFFLINE_SCIENCE_ENTRIES = (
    ("RS-HERO-FULL", "hero-v2", "real baseline, separate design approval, raw artifact download, fresh native replay"),
    ("RS-CHANGED-INPUT", "changed-input-v1", "changed scientific input: fresh identities and computation, "
                                             "original result unchanged"),
    ("RS-RETRY-CONCURRENT", "hero-v2", "concurrent and retried starts: one accepted run, no duplicate science"),
    ("RS-DESIGN-AUTHORITY", "hero-v2", "baseline approval cannot authorize design; pair, allowance and grid bound"),
    ("RS-FOLLOWUP", "hero-v2", "hypothetical readings: new lineage, new approval, per-candidate outcomes"),
    ("RS-CANCEL-RESTART", "hero-v2", "queued and running cancellation, worker restart: no orphan, no redispatch"),
    ("RS-ZERO-DISPATCH", "hero-v2", "whole lane: guard active in API and worker, zero external model dispatch"),
)
# Proposed pre-request maxima (tokens). Ceilings to enforce, not measurements:
# 8*3000 + 24*1600 = 62,400 input and 8*700 + 24*400 = 15,200 output.
REQUEST_ALLOCATION = {
    "intake": {"max_input_tokens": 3000, "max_output_tokens": 700},
    "agent": {"max_input_tokens": 1600, "max_output_tokens": 400},
}


def sha256_file(path: str) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(1 << 16), b""):
            digest.update(block)
    return digest.hexdigest()


def _schedule() -> dict:
    fixture = [{"entry_id": f"{case}-{variant}", "case_id": case, "variant": variant}
               for case in CASE_IDS for variant in "AB"]
    live = []
    for case, lane in (("C01", "live_intake"), ("C04", "live_intake"),
                       ("C08", "live_agent_controlled_tools"), ("C09", "live_agent_controlled_tools")):
        for attempt in (1, 2):
            live.append({"entry_id": f"{case}-A-live{attempt}", "case_id": case, "variant": "A", "lane": lane,
                         "scheduled_attempt": attempt})
    full = [
        {"entry_id": "FS-BASELINE", "lane": "actual_full_stack", "operation": "agent",
         "note": "real baseline agent invocation; approves the baseline scenario only"},
        {"entry_id": "FS-DESIGN", "lane": "actual_full_stack", "operation": "agent",
         "note": "distinct design agent invocation after separate human review and approval"},
    ]
    science = [{"entry_id": entry_id, "lane": "offline_real_science", "operation": "science", "packet": packet,
                "note": note} for entry_id, packet, note in OFFLINE_SCIENCE_ENTRIES]
    return {"fixture_contract": fixture, "live": live, "actual_full_stack": full, "offline_real_science": science}


def build(root: str) -> dict:
    cases, sources, holdouts = {}, {}, {}
    for case in CASE_IDS:
        rel = f"cases/{case}.json"
        cases[case] = {"file": rel, "sha256": sha256_file(os.path.join(root, rel))}
    source_dir = os.path.join(root, "sources")
    for name in sorted(os.listdir(source_dir)):
        if name.endswith(".png"):
            path = os.path.join(source_dir, name)
            target = holdouts if name.startswith("h") else sources
            target[name[:-4]] = {"file": f"sources/{name}", "sha256": sha256_file(path),
                                 "bytes": os.path.getsize(path),
                                 "expected": f"sources/expected/{name[:-4]}.json",
                                 "expected_sha256": sha256_file(os.path.join(source_dir, "expected",
                                                                            name[:-4] + ".json"))}
    return {
        "manifest_version": 1,
        "harness_version": HARNESS_VERSION,
        "contract": {"revision": CONTRACT_REVISION, "wire_profile": WIRE_PROFILE,
                     "source_sha256": CONTRACT_SOURCE_SHA256},
        "observation_schema": "eval-observation/v1",
        "modality": {"chosen": "image/png", "pdf": "not selected; unrun by decision"},
        "cases": cases,
        "sources": sources,
        "holdouts": {"status": "prepared and sealed by digest; not used for prompt tuning; ungraded",
                     "items": holdouts},
        "schedule": _schedule(),
        "caps": {"cohort": DEFAULT_CAPS, "invocation": INVOCATION_LIMITS, "request_allocation": REQUEST_ALLOCATION,
                 "max_scientific_jobs_in_portfolio": 2},
        "lanes": LANE_RULES,
        "live_activation": LIVE_ACTIVATION,
        "science_packets": {packet: {"file": f"cases/science/{packet}.json",
                                     "sha256": sha256_file(os.path.join(root, "cases", "science", packet + ".json"))}
                            for packet in SCIENCE_PACKETS},
        "ancestry_archive": "manifests/manifest-v<N>.json holds every superseded manifest byte-for-byte",
    }


def freeze(root: str) -> dict:
    """Write manifest.json. A changed manifest gets a new version and keeps its ancestry."""
    path = os.path.join(root, "manifest.json")
    manifest = build(root)
    if os.path.exists(path):
        with open(path, encoding="utf-8") as handle:
            previous = json.load(handle)
        comparable = {k: v for k, v in previous.items() if k not in ("frozen_at", "manifest_version", "supersedes")}
        if comparable == {k: v for k, v in manifest.items() if k != "manifest_version"}:
            return previous
        manifest["manifest_version"] = previous["manifest_version"] + 1
        manifest["supersedes"] = previous.get("supersedes", []) + [
            {"manifest_version": previous["manifest_version"], "sha256": sha256_file(path),
             "archived": f"manifests/manifest-v{previous['manifest_version']}.json"}]
        archive = os.path.join(root, "manifests", f"manifest-v{previous['manifest_version']}.json")
        os.makedirs(os.path.dirname(archive), exist_ok=True)
        if not os.path.exists(archive):  # keep ancestors byte-identical so old attempts stay interpretable
            with open(path, "rb") as source, open(archive, "wb") as target:
                target.write(source.read())
    manifest["frozen_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(manifest, handle, indent=2, sort_keys=True)
        handle.write("\n")
    return manifest


def load(root: str) -> dict:
    with open(os.path.join(root, "manifest.json"), encoding="utf-8") as handle:
        return json.load(handle)


def load_case(root: str, case_id: str) -> dict:
    with open(os.path.join(root, "cases", f"{case_id}.json"), encoding="utf-8") as handle:
        return json.load(handle)


def verify(root: str) -> list[str]:
    """Problems with the frozen manifest; an empty list means it verifies."""
    problems = []
    manifest = load(root)
    pinned = [(v["file"], v["sha256"]) for v in manifest["cases"].values()]
    for group in (manifest["sources"], manifest["holdouts"]["items"]):
        for item in group.values():
            pinned += [(item["file"], item["sha256"]), (item["expected"], item["expected_sha256"])]
    for rel, digest in pinned:
        path = os.path.join(root, rel)
        if not os.path.exists(path):
            problems.append(f"missing frozen file {rel}")
        elif sha256_file(path) != digest:
            problems.append(f"frozen file changed without a manifest version: {rel}")
    if sorted(manifest["cases"]) != CASE_IDS:
        problems.append("the portfolio is not exactly C01..C12")
    seen_ids = set()
    for case_id in manifest["cases"]:
        try:
            case = load_case(root, case_id)
        except (OSError, ValueError) as error:
            problems.append(f"{case_id}: unreadable ({error})")
            continue
        if sorted(case["variants"]) != ["A", "B"]:
            problems.append(f"{case_id}: needs exactly variants A and B")
        for letter, variant in case["variants"].items():
            if not variant.get("expected"):
                problems.append(f"{case_id}-{letter}: no expected assertions")
            for assertion in variant.get("expected", []):
                try:
                    validate_assertion(assertion)
                except ValueError as error:
                    problems.append(f"{case_id}-{letter}: {error}")
                if assertion.get("id") in seen_ids:
                    problems.append(f"duplicate assertion id {assertion.get('id')}")
                seen_ids.add(assertion.get("id"))
            source = variant.get("input", {}).get("source")
            if source and source not in manifest["sources"]:
                problems.append(f"{case_id}-{letter}: source {source} is not a frozen source")
    if len(manifest["schedule"]["fixture_contract"]) != 24:
        problems.append("fixture schedule is not 24 entries")
    live = manifest["schedule"]["live"]
    alloc = manifest["caps"]["request_allocation"]
    limits = manifest["caps"]["invocation"]
    requests = tokens_in = tokens_out = 0
    for kind, count in (("intake", sum(e["lane"] == "live_intake" for e in live)),
                        ("agent", sum(e["lane"] != "live_intake" for e in live)
                         + len(manifest["schedule"]["actual_full_stack"]))):
        n = count * limits[kind]["provider_requests"]
        requests += n
        tokens_in += n * alloc[kind]["max_input_tokens"]
        tokens_out += n * alloc[kind]["max_output_tokens"]
    cohort = manifest["caps"]["cohort"]
    if (requests > cohort["provider_requests"] or tokens_in > cohort["input_tokens"]
            or tokens_out > cohort["output_tokens"]):
        problems.append(f"scheduled live maxima exceed cohort caps: {requests} requests, "
                        f"{tokens_in} in, {tokens_out} out")
    problems += _verify_v2(root, manifest)
    return problems


def _verify_v2(root: str, manifest: dict) -> list[str]:
    """Ancestry, science packets and lane rules (manifest version 2 and later)."""
    problems = []
    for ancestor in manifest.get("supersedes", []):
        archived = ancestor.get("archived")
        path = os.path.join(root, archived) if archived else None
        if not path or not os.path.exists(path):
            problems.append(f"superseded manifest v{ancestor['manifest_version']} is not archived")
        elif sha256_file(path) != ancestor["sha256"]:
            problems.append(f"archived manifest v{ancestor['manifest_version']} does not match its recorded digest")
    if manifest["manifest_version"] < 2:
        return problems
    for packet, item in manifest.get("science_packets", {}).items():
        path = os.path.join(root, item["file"])
        if not os.path.exists(path):
            problems.append(f"missing science packet {item['file']}")
        elif sha256_file(path) != item["sha256"]:
            problems.append(f"science packet changed without a manifest version: {item['file']}")
    lanes = manifest.get("lanes", {})
    if sorted(lanes) != sorted(LANES):
        problems.append("lane rules do not cover exactly the declared lanes")
    for lane, rule in lanes.items():
        if rule.get("live_provider") and rule.get("enabled"):
            problems.append(f"live lane {lane} is enabled; live lanes stay NOT_RUN without a new user instruction")
        if not rule.get("live_provider") and "live" in rule.get("provider", []):
            problems.append(f"offline lane {lane} admits a live provider")
    for entry in manifest["schedule"].get("offline_real_science", []):
        if entry.get("packet") not in manifest.get("science_packets", {}):
            problems.append(f"{entry['entry_id']}: unknown science packet {entry.get('packet')}")
    return problems
