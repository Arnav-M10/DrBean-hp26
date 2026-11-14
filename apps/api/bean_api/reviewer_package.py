"""Bounded deterministic reviewer ZIP from one immutable report snapshot."""
from __future__ import annotations

import csv
import hashlib
import io
import json
import zipfile

from .workflow import DomainError

MAX_PACKAGE_BYTES = 12 * 1024 * 1024
MAX_MEMBERS = 64


def json_bytes(value):
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False) + "\n").encode()


def build_reviewer_package(workflow, artifacts, actor, report_id):
    report = workflow.get(actor, report_id, "report")
    body = report["body"]
    files, references = {}, {}
    def add(name, content):
        if len(files) >= MAX_MEMBERS or sum(map(len, files.values())) + len(content) > MAX_PACKAGE_BYTES:
            raise DomainError("package_size_limit", "This report exceeds the bounded reviewer package size; download its artifacts individually.", 413)
        files[name] = content
    add("report.json", json_bytes(report))
    # Immutable authority receipts complement the frozen plan and job records.
    jobs = [body["run"], *(item["job"] for item in body.get("designs", []) if item.get("job"))]
    if body.get("followup"):
        jobs.append(body["followup"]["design_job"])
    with workflow.store.read() as conn:
        for index, approval_id in enumerate(sorted({job["approval_id"] for job in jobs}), 1):
            receipt = conn.execute("SELECT * FROM approvals WHERE id=? AND workspace_id=?",
                                   (approval_id, report["workspace_id"])).fetchone()
            if receipt is None:
                raise DomainError("package_incomplete", "The report's approval receipt is unavailable.", 409)
            add(f"approvals/{index}.json", json_bytes(dict(receipt)))
    datasets = {item["dataset"]["id"]: item["dataset"] for item in body.get("scenario_inputs", [])}
    datasets[body["dataset"]["id"]] = body["dataset"]
    for index, dataset in enumerate(sorted(datasets.values(), key=lambda d: d["id"]), 1):
        add(f"measurements/{index}.json", json_bytes(dataset))
        table = io.StringIO(newline="")
        writer = csv.writer(table)
        writer.writerow(["row_id", "elapsed_time_h", "concentration_mg_L", "hard_allowance_mg_L", "included"])
        for row in dataset["body"]["rows"]:
            writer.writerow([row["id"], row["time"], row["concentration"], row["hard_allowance"], row["included"]])
        add(f"measurements/{index}.csv", table.getvalue().encode())
    results = [item["body"]["result"] for item in body["evidence"]]
    results += [item["suggestion"]["body"] for item in body.get("designs", []) if item.get("suggestion")]
    if body.get("followup"):
        results.append(body["followup"]["design_result"]["body"])
    for result in results:
        for reference in result.get("artifacts", []):
            if reference["id"] in references and references[reference["id"]] != reference:
                raise DomainError("artifact_binding_mismatch", "Report artifact references conflict.")
            references[reference["id"]] = reference
    inventory, commands = [], []
    for index, reference in enumerate(sorted(references.values(), key=lambda r: r["id"]), 1):
        try:
            record, content = artifacts.read(actor, reference["id"])
        except DomainError as exc:
            if exc.code == "not_found":
                raise DomainError("package_incomplete", "A referenced native artifact is not retained locally; the reviewer package cannot be completed.", 409) from None
            raise
        workflow._same_workspace(report["workspace_id"], record)
        if any(record["body"][k] != reference[k] for k in ("sha256", "byte_size", "media_type")):
            raise DomainError("artifact_binding_mismatch", "Stored bytes differ from the frozen report reference.")
        prefix = f"evidence/{index}"
        add(prefix + ".native.json", content)
        add(prefix + ".anchors.json", json_bytes(record["body"]["anchor"]))
        inventory.append({"artifact_id": record["id"], **reference,
                          "native_file": prefix + ".native.json", "anchor_file": prefix + ".anchors.json"})
        command = "replay-native" if "projection_digest" in record["body"]["anchor"] else "replay"
        commands.append(f"/path/to/prepared/python -I -m counterdex {command} {prefix}.native.json --anchors {prefix}.anchors.json")
    readme = """# Dr. Bean reviewer package

Open report.json for reviewed inputs, assumptions, origin/provenance, plan limits,
scenario status and result facts. measurements/ provides exact rational JSON/CSV.
approvals/ contains immutable application approval receipts.
Native evidence and separately retained application anchors are in evidence/.
Raw source images are not included; their retained metadata/digests are in the report.
The snapshot may describe partial or interrupted work; inspect scenario states.

## Fresh scientific replay

Use a separately prepared compatible Counterdex environment (CPython 3.11 for
the current profile). This archive does not install or execute anything itself.
Extract it, open a terminal in its directory, and replace the interpreter path:

""" + ("\n".join(commands) if commands else "No native scientific artifacts were retained for this snapshot.") + """

Compare fresh integrity, expected binding, verification and replay separately.
Replay checks retained evidence; it does not repeat numerical discovery. Review
the supported model and the checker identity/source recorded in each packet.
An archive/manifest hash establishes byte integrity, not scientific truth or
independent authenticity of the supplied anchors. Keep any independently trusted
record identities or anchors when judging whether this is the expected experiment.
No witness found does not prove the claim; excluded selected candidates do not
establish global inconsistency. No live model calls were needed to export this ZIP.
"""
    add("README.md", readme.encode())
    manifest = {"format": "reviewer-package.v1", "report_id": report_id, "report_digest": report["digest"],
        "native_artifacts": inventory, "files": [{"path": path, "byte_size": len(content),
            "sha256": hashlib.sha256(content).hexdigest()} for path, content in sorted(files.items())]}
    add("manifest.json", json_bytes(manifest))
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w", compression=zipfile.ZIP_STORED) as archive:
        for path, content in sorted(files.items()):
            entry = zipfile.ZipInfo(path, date_time=(1980, 1, 1, 0, 0, 0))
            entry.external_attr = 0o100600 << 16
            archive.writestr(entry, content)
    content = stream.getvalue()
    if len(content) > MAX_PACKAGE_BYTES:
        raise DomainError("package_size_limit", "The complete ZIP exceeds the reviewer download limit.", 413)
    return content
