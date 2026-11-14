"""Report proposed startup-field presence without clients, secrets or probes.

Owner 2/4 must wire these proposed environment names into the server/launcher.
Presence here is not evidence that the running application consumes them.
"""
import json
import os


def main():
    mode = os.environ.get("BEAN_PROVIDER_MODE", "disabled")
    print(json.dumps({
        "configuration_contract": "proposed-owner-2-startup.v1",
        "mode": mode if mode in {"disabled", "controlled", "live"} else "invalid",
        "model_field_present": "BEAN_GEMINI_MODEL" in os.environ,
        "key_field_present": "BEAN_GEMINI_API_KEY" in os.environ,
        "account_decision_field_present": "BEAN_GEMINI_ACCOUNT_DECISION_ID" in os.environ,
        "application_wiring": "pending_owner_2_and_4",
        "reachability": "not_run",
        "live_qualification": "not_run",
        "generation_dispatches": 0,
    }, sort_keys=True))


if __name__ == "__main__":
    main()
