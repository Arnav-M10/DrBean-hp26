"""Isolated placeholder records; never mutate or spend the real-provider ledger."""
from uuid import uuid4


class ControlledLedger:
    def __init__(self, workflow):
        self.workflow = workflow
        self.pending = {}

    def begin_attempt(self, context, metadata):
        actor, workspace = context["actor_id"], context["workspace_id"]
        self.workflow.authorize(actor, workspace)
        record = self.workflow.create_record(actor, workspace, "controlled_attempt", {
            "execution_lane": "controlled_placeholder", "external_provider_calls": 0,
            "actual_model_tokens": 0, "simulated_reservation": metadata, "context": context,
        }, uuid4().hex, operation="controlled-attempt")
        self.pending[record["id"]] = (actor, workspace)
        return record["id"]

    def finish_attempt(self, attempt_id, metadata):
        actor, workspace = self.pending.pop(attempt_id)
        self.workflow.create_record(actor, workspace, "controlled_outcome", {
            "attempt_id": attempt_id, "execution_lane": "controlled_placeholder",
            "external_provider_calls": 0, "actual_model_tokens": 0,
            "simulated_outcome": metadata,
        }, attempt_id, operation="controlled-outcome", parent_id=attempt_id)
