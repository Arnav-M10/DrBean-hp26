"""Versioned provenance binding for rechecking an admitted observation revision.

This composes the existing application projection and fixed-candidate checker.
The caller must freshly replay the complete parent native packet before passing
its decoded payload and results here. Proposal records are the application's
normalized ObservationProposalBody, not a new approval or authorization DTO.
The new run/scenario is anchored by the outer packet; this binding separately
preserves the parent scope without requiring both runs to share a scenario.
"""

from copy import deepcopy

from .application import (APPLICATION_BODY_CAP, _identifier, _object,
                          verify_application_binding)
from .errors import AdapterError
from .exact import artifact_digest, canonical_bytes
from .historical import normalize_candidates
from .models import digest_value, fields, normalize_problem, text_value

FOLLOWUP_BINDING = "counterdex.followup-binding.v1"
FOLLOWUP_FIELDS = {"schema_version", "application", "observation_proposal", "parent"}
PROPOSAL_FIELDS = {"dataset_id", "experiment_id", "observable", "origin", "row",
                   "source_description", "change_reason", "generating_choices",
                   "time_unit", "concentration_unit"}


def _mismatch(message: str, path: str) -> AdapterError:
    return AdapterError("wrong_specification_binding", message, (path,))


def _proposal(value: dict) -> dict:
    record = _object(value, "observation_proposal")
    if record.get("kind", "observation_proposal") != "observation_proposal":
        raise _mismatch("Expected an observation proposal record.", "observation_proposal")
    identifier = _identifier(record.get("id"), "observation_proposal/id")
    digest = digest_value(record.get("digest"), "observation_proposal/digest")
    body = fields(record.get("body"), PROPOSAL_FIELDS, "observation_proposal/body")
    encoded = canonical_bytes(body)
    if len(encoded) > APPLICATION_BODY_CAP:
        raise AdapterError("resource_exhaustion", "Observation provenance exceeds its byte cap.",
                           ("observation_proposal/body",))
    # The backend hashes observation proposal bodies directly. These records
    # are not members of the DB-SC-1 semantic-digest namespace.
    if artifact_digest(encoded) != digest:
        raise _mismatch("Observation body differs from its record digest.", "observation_proposal/digest")
    for key in ("dataset_id", "experiment_id"):
        _identifier(body[key], "observation_proposal/body/" + key)
    for key, expected in (("observable", "concentration"), ("time_unit", "h"),
                          ("concentration_unit", "mg/L")):
        if body[key] != expected:
            raise AdapterError("unsupported_model", "Observation units and observable must match the admitted model.",
                               ("observation_proposal/body/" + key,))
    if body["origin"] not in ("actual", "transcription", "hypothetical"):
        raise AdapterError("invalid_input", "Declare the original observation origin.",
                           ("observation_proposal/body/origin",))
    for key in ("source_description", "change_reason"):
        if type(body[key]) is not str or not 1 <= len(body[key]) <= 2000:
            raise AdapterError("invalid_input", "Retain the complete bounded observation provenance.",
                               ("observation_proposal/body/" + key,))
    choices = body["generating_choices"]
    if (type(choices) is not dict or len(choices) > 16
            or any(type(k) is not str or type(v) is not str for k, v in choices.items())
            or bool(choices) != (body["origin"] == "hypothetical")):
        raise AdapterError("invalid_input", "Only hypothetical readings require and retain generating choices.",
                           ("observation_proposal/body/generating_choices",))
    row = fields(body["row"], {"id", "time", "concentration", "hard_allowance", "included",
                               "original_values", "source_asset_id", "notes"}, "observation_proposal/body/row")
    if row["included"] is not True:
        raise _mismatch("The appended follow-up reading must be included.", "observation_proposal/body/row/included")
    if row["source_asset_id"] is not None:
        raise AdapterError("unsupported_model", "Source-derived observations require the separate exact intake-review lineage.",
                           ("observation_proposal/body/row/source_asset_id",))
    originals = row["original_values"]
    if (type(originals) is not dict or len(originals) > 12 or any(
            type(k) is not str or type(v) is not str or len(k) > 128 or len(v) > 256
            for k, v in originals.items())):
        raise AdapterError("invalid_input", "Original observation spellings exceed the application bounds.",
                           ("observation_proposal/body/row/original_values",))
    if type(row["notes"]) is not str or len(row["notes"]) > 2000:
        raise AdapterError("invalid_input", "Observation notes exceed the application bounds.",
                           ("observation_proposal/body/row/notes",))
    return deepcopy({"id": identifier, "digest": digest, "body": body})


def project_followup(projection: dict, *, observation_proposal: dict,
                     parent_packet: dict, parent_scientific: dict, parent_replay: dict) -> dict:
    """Bind one reviewed appended row and the original one or two exact vectors.

    The parent may be a baseline discovery or design. The new row uses its own
    exact admitted time and allowance; a design recommendation never rewrites
    either. The backend remains responsible for review, revisions and approval.
    Full proposal provenance remains in this wrapper even where the scientific
    application mapping uses a conservative aggregate hypothetical category.
    """
    supplied = _object(projection, "projection")
    current = verify_application_binding(supplied.get("binding"))
    if current != supplied:
        raise _mismatch("The supplied application projection was changed.", "projection")
    proposal = _proposal(observation_proposal)
    parent = _object(parent_packet, "parent_packet")
    operation = parent.get("operation")
    if operation not in ("investigate", "design"):
        raise _mismatch("Recheck requires original baseline or design evidence.", "parent_packet/operation")
    replay = _object(parent_replay, "parent_replay")
    if replay.get("replay") != "passed":
        raise AdapterError("incomplete_export", "Complete parent evidence must freshly replay before rechecking.",
                           ("parent_replay",))
    parent_binding = _object(parent.get("binding"), "parent_packet/binding")
    previous = verify_application_binding(parent_binding.get("application") if operation == "design" else parent_binding)
    previous_binding, binding = previous["binding"], current["binding"]
    scientific = _object(parent_scientific, "parent_scientific")
    if scientific.get("problem") != previous["problem"]:
        raise _mismatch("Parent scientific inputs differ from their application projection.", "parent_scientific/problem")
    old, new = previous_binding["dataset"], binding["dataset"]
    prior, revised, body = old["body"], new["body"], proposal["body"]
    expected_origin = "hypothetical" if "hypothetical" in (prior["origin"], body["origin"]) else prior["origin"]
    expected_dataset = {**prior, "parent_id": old["id"], "rows": [*prior["rows"], body["row"]],
                        "origin": expected_origin, "change_reason": body["change_reason"]}
    if (new["id"] == old["id"] or revised != expected_dataset
            or body["dataset_id"] != old["id"] or body["experiment_id"] != prior["experiment_id"]):
        raise _mismatch("Follow-up must append exactly the proposed row while preserving its parent dataset.",
                        "application/dataset")
    old_problem, new_problem = previous_binding["problem"], binding["problem"]
    expected_problem = {**old_problem["body"], "dataset_id": new["id"], "dataset_digest": new["digest"]}
    if new_problem["id"] == old_problem["id"] or new_problem["body"] != expected_problem:
        raise _mismatch("Follow-up needs a new problem identity with the original model, domain and claim.",
                        "application/problem")
    if operation == "investigate":
        if scientific.get("operation") != "bounded_discovery":
            raise _mismatch("Baseline lineage must identify actual candidate discovery.", "parent_scientific/operation")
        payloads = scientific.get("candidates")
    else:
        payloads = _object(scientific.get("design"), "parent_scientific/design").get("candidates")
    originals = normalize_candidates(normalize_problem(previous["problem"]), payloads)
    checked = replay.get("candidate_results")
    if type(checked) is not list or len(checked) != len(originals):
        raise AdapterError("incomplete_export", "Fresh checks for every original candidate are required.", ("parent_replay/candidate_results",))
    candidates = []
    for candidate in originals:
        source = candidate.to_payload()
        matches = [item for item in checked if type(item) is dict and item.get("candidate_id") == source["id"]]
        if (len(matches) != 1 or matches[0].get("verification") != "valid"
                or ((operation == "investigate" or "parameters" in matches[0])
                    and matches[0].get("parameters") != source["parameters"])):
            raise AdapterError("candidate_mismatch", "Original vectors must match their fresh compatible historical checks.",
                               ("parent_replay/candidate_results",))
        candidates.append({**source, "problem_digest": current["projection_digest"], "source_artifact_digest": None})
    # Re-admit against the new scientific problem without adjusting a vector.
    normalize_candidates(normalize_problem(current["problem"]), candidates)
    parent_metadata = {"operation": operation,
        "run_id": text_value(parent.get("run_id"), "parent_packet/run_id", identifier=True),
        "scenario_id": text_value(parent.get("scenario_id"), "parent_packet/scenario_id", identifier=True),
        "problem_id": old_problem["id"], "problem_digest": old_problem["digest"],
        "dataset_id": old["id"], "dataset_digest": old["digest"],
        "projection_digest": previous["projection_digest"]}
    followup = {"schema_version": FOLLOWUP_BINDING, "application": binding,
                "observation_proposal": proposal, "parent": parent_metadata}
    return deepcopy({"binding": followup, "problem": current["problem"],
                     "projection_digest": current["projection_digest"], "candidates": candidates})


def verify_followup_binding(binding: dict, *, parent_packet: dict,
                            parent_scientific: dict, parent_replay: dict) -> dict:
    """Reproduce provenance and vector selection after the caller replays history."""
    binding = fields(binding, FOLLOWUP_FIELDS, "binding")
    if binding["schema_version"] != FOLLOWUP_BINDING:
        raise AdapterError("unsupported_model", "Unsupported follow-up binding profile.", ("binding/schema_version",))
    result = project_followup(verify_application_binding(binding["application"]),
        observation_proposal=binding["observation_proposal"], parent_packet=parent_packet,
        parent_scientific=parent_scientific, parent_replay=parent_replay)
    if result["binding"] != binding:
        raise _mismatch("Stored follow-up lineage differs from fresh reconstruction.", "binding")
    return result
