"""Fixed presentation selectors for computed adapter tiers, not LLM verdicts."""
from .errors import AdapterError


def interpretation(tier: str) -> dict:
    """Use only with a computed/freshly replayed tier, never an imported badge."""
    messages = {
        "checked_pair_separation": (
            "fixed_pair_separation",
            "Under the reviewed model and future hard allowance, a measurement at the selected time cannot fit both fixed parameter choices. It may exclude either or both. This does not identify the true parameters or establish the claimed interval."),
        "no_separation_established": (
            "sufficient_test_did_not_separate",
            "No reviewed feasible time passed the sufficient exact separation test for this pair. Conservative enclosures may prevent separation; this does not prove the trajectories are indistinguishable."),
        "numerical_guidance": (
            "numerical_pair_comparison",
            "These approximate scores compare two fixed choices over the evaluated subset of the reviewed grid. They do not establish historical compatibility, guaranteed separation, probability, or a globally best experiment."),
        "unavailable": (
            "no_supported_conclusion",
            "This operation established no supported fixed-pair conclusion. Its reason and retained partial results describe what remains unresolved.")}
    if tier not in messages:
        raise AdapterError("invalid_input", "Unknown scientific interpretation tier.")
    key, message = messages[tier]
    return {"key": key, "message": message}
