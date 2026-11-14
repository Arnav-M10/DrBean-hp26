"""Scientific paper-mapping checks, not application DTOs or approval authority.

The application owns source/page admission, authenticated human review,
immutable records and approvals. It must derive the facts below from those
records, never from an unaccepted model classification. This module performs
bounded exact conversions and narrower scientific checks, then reuses the
existing application projection. It does not parse PDFs, execute equations,
authenticate sources, or make statistical/clinical inferences.
"""

from fractions import Fraction

from .application import project_application
from .errors import AdapterError
from .exact import parse_rational, rational_text

PAPER_MAPPING_POLICY = "counterdex.paper-mapping.v1"

# Explicit, case-sensitive spellings only. No prefix guessing or unit inference.
_UNITS = {
    "time": ("h", {"h": Fraction(1), "min": Fraction(1, 60), "s": Fraction(1, 3600)}),
    "concentration": ("mg/L", {
        "mg/L": Fraction(1), "ug/mL": Fraction(1), "µg/mL": Fraction(1),
        "μg/mL": Fraction(1), "ng/mL": Fraction(1, 1000),
        "ug/L": Fraction(1, 1000), "µg/L": Fraction(1, 1000),
        "μg/L": Fraction(1, 1000), "mg/dL": Fraction(10), "g/L": Fraction(1000),
    }),
    "rate": ("1/h", {"1/h": Fraction(1), "1/min": Fraction(60), "1/s": Fraction(3600)}),
}


def convert_scalar(accepted_value: str, accepted_unit: str, *, quantity: str) -> dict:
    """Convert a reviewed exact scalar, retaining its input and operation.

    The accepted spelling may be a human correction. The caller must separately
    retain the original source spelling/unit, locator, correction and reason.
    This is unit arithmetic only; scientific range checks happen at projection.
    """
    if type(quantity) is not str or quantity not in _UNITS:
        raise AdapterError("unsupported_unit", "Choose time, concentration or rate.", ("quantity",))
    target, factors = _UNITS[quantity]
    if type(accepted_unit) is not str or accepted_unit not in factors:
        raise AdapterError("unsupported_unit", "This exact unit spelling has no reviewed conversion.", ("accepted_unit",))
    value = parse_rational(accepted_value, "accepted_value")
    factor = factors[accepted_unit]
    # Reapply scalar resource bounds after multiplication, too.
    normalized = rational_text(value * factor)
    parse_rational(normalized, "normalized_value")
    return {"policy": PAPER_MAPPING_POLICY, "quantity": quantity,
            "accepted_value": accepted_value, "accepted_unit": accepted_unit,
            "operation": "multiply_exact_rational", "factor": rational_text(factor),
            "normalized_value": normalized, "normalized_unit": target}


def oral_amplitude(*, bioavailability: str, dose_mg: str, volume_L: str,
                   ke_per_h: str, ka_per_h: str) -> dict:
    """Exact algebra for the reviewed single-dose first-order oral expression.

    A = F D ka / (V (ka-ke)). This verifies arithmetic for supplied quantities;
    it does not establish applicability or infer F, D or V from fitted A.
    Fixed F/D/V couple A to both rates. The independent native parameter box is
    not automatically an equivalent domain of physical parameters.
    """
    inputs = {"bioavailability": bioavailability, "dose_mg": dose_mg,
              "volume_L": volume_L, "ke_per_h": ke_per_h, "ka_per_h": ka_per_h}
    values = {key: parse_rational(value, key) for key, value in inputs.items()}
    for key, value in values.items():
        if value <= 0:
            raise AdapterError("unsupported_model", "The supported mapping requires positive quantities.", (key,))
    if values["bioavailability"] > 1:
        raise AdapterError("unsupported_model", "Bioavailability must not exceed one.", ("bioavailability",))
    if values["ke_per_h"] >= values["ka_per_h"]:
        raise AdapterError("unsupported_model", "Require ke < ka without relabeling either physical rate.", ("ka_per_h",))
    amplitude = (values["bioavailability"] * values["dose_mg"] * values["ka_per_h"]
                 / (values["volume_L"] * (values["ka_per_h"] - values["ke_per_h"])))
    normalized = rational_text(amplitude)
    parse_rational(normalized, "amplitude")
    return {"policy": PAPER_MAPPING_POLICY, "expression": "F*D*ka/(V*(ka-ke))",
            "inputs": inputs, "A": normalized, "unit": "mg/L",
            "domain_equivalence_established": False,
            "limitation": "A does not identify F, D or V separately; an independent A box may relax their coupled constraints."}


def assess_paper_scope(problem_record: dict | None, dataset_record: dict | None, *,
                       model_form: str | None = None, regimen: str | None = None,
                       response_kind: str | None = None, observation_kind: str | None = None,
                       source_claim_kind: str | None = None, question_kind: str | None = None,
                       allowance_basis: str | None = None, amplitude_scope: str | None = None,
                       reviewed_assumptions: tuple[str, ...] = ()) -> dict:
    """Classify scientific scope from application-authenticated review facts.

    This is a scientific helper, not an authoritative paper request schema.
    `reviewed_assumptions` names retained human decisions. Supplying strings here
    cannot approve a proposal or authorize execution. Owner 2 must bind facts,
    source/page/claim/review identities and current input heads in its records.

    An eligible result binds the existing normalized records/projection by
    digest; it grants neither mathematical verification nor source authenticity.
    """
    facts = {"model_form": model_form, "regimen": regimen, "response_kind": response_kind,
             "observation_kind": observation_kind, "source_claim_kind": source_claim_kind,
             "question_kind": question_kind, "allowance_basis": allowance_basis,
             "amplitude_scope": amplitude_scope}
    issues = []
    limitations = ["Eligibility is not source authentication, scientific verification or execution approval."]

    def issue(category, field, code, message):
        issues.append({"category": category, "field": field, "code": code, "message": message})

    def choice(field, allowed, category="unsupported_model"):
        value = facts[field]
        if value is None or value == "":
            issue("needs_measurements_or_assumptions", field, "review_required", "Review and specify " + field + ".")
        elif type(value) is not str or value not in allowed:
            issue(category, field, "unsupported_" + field, "This scientific mapping does not support the supplied " + field + ".")

    choice("model_form", {"two_rate_difference", "single_dose_oral_first_order"})
    choice("regimen", {"single_initial_event"})
    choice("response_kind", {"single_trajectory", "aggregate_mean"})
    choice("observation_kind", {"table_transcription"})
    choice("source_claim_kind", {"deterministic_interval", "confidence_interval", "prediction_interval",
                                 "point_estimate", "qualitative"}, "unsupported_claim_semantics")
    choice("question_kind", {"paper_deterministic_claim", "user_deterministic_robustness"}, "unsupported_claim_semantics")
    choice("amplitude_scope", {"independent_amplitude", "coupled_physical_parameters"})
    if allowance_basis not in ("reviewed_hard_bound", "hypothetical_hard_bound"):
        issue("needs_measurements_or_assumptions", "allowance_basis", "hard_bound_required",
              "Review a justified hard bound or a hypothetical sensitivity allowance; SD, SEM, CI, resolution and detection thresholds are not hard bounds.")
    if (question_kind == "paper_deterministic_claim"
            and source_claim_kind not in (None, "", "deterministic_interval")):
        issue("unsupported_claim_semantics", "question_kind", "statistical_claim_is_not_deterministic",
              "Retain the paper's claim type. A separate user robustness question may use a reviewed range without refuting that statistical claim.")
    if question_kind == "user_deterministic_robustness":
        limitations.append("This is the user's conditional deterministic question, not a refutation or reproduction of the paper's statistical result.")
    if allowance_basis == "hypothetical_hard_bound" and question_kind != "user_deterministic_robustness":
        issue("unsupported_claim_semantics", "question_kind", "hypothetical_bound_requires_user_question",
              "A hypothetical allowance requires a separate user robustness question, not a claim of reproducing the paper.")
    if amplitude_scope == "coupled_physical_parameters":
        issue("unsupported_model", "amplitude_scope", "coupled_domain_not_supported",
              "The native independent A/ke/ka box does not enforce constraints induced by fixed or bounded F, dose and volume.")
    if (model_form == "single_dose_oral_first_order"
            and question_kind not in (None, "", "user_deterministic_robustness")):
        issue("unsupported_model", "question_kind", "oral_domain_equivalence_not_established",
              "Algebraic amplitude substitution alone is not domain equivalence. Use a separately reviewed free-amplitude robustness question in this milestone.")
    if response_kind == "aggregate_mean":
        issue("needs_measurements_or_assumptions", "response_kind", "aggregate_binding_required",
              "Keep aggregate means in paper review until an explicit effective-mean-curve assumption, cohort/time alignment and per-mean bounds can be retained and exposed by the application. Do not treat means as individual trajectories.")

    if (type(reviewed_assumptions) not in (tuple, list) or len(reviewed_assumptions) > 32
            or any(type(x) is not str or not 1 <= len(x) <= 128 for x in reviewed_assumptions)):
        raise AdapterError("invalid_input", "Supply names of retained human review decisions.", ("reviewed_assumptions",))
    required = {"source_values", "model_applicability", "time_origin", "hard_allowances", "rate_meanings"}
    if question_kind == "user_deterministic_robustness":
        required.add("separate_user_question")
    if model_form == "single_dose_oral_first_order":
        required.add("independent_amplitude_relaxation")
    for name in sorted(required - set(reviewed_assumptions)):
        issue("needs_measurements_or_assumptions", "reviewed_assumptions." + name,
              "human_review_required", "Retain the human decision for " + name + ".")
    if allowance_basis == "hypothetical_hard_bound":
        limitations.append("Measurement allowances are hypothetical sensitivity assumptions, not reported experimental uncertainty.")
    if model_form == "single_dose_oral_first_order":
        limitations.append("Free amplitude is a reviewed relaxation; the checker does not infer bioavailability, dose or volume.")

    projection = None
    if problem_record is None or dataset_record is None:
        issue("needs_measurements_or_assumptions", "inputs", "measurements_and_problem_required",
              "Supply reviewed normalized dataset/problem records, including hard bounds, units, domain, closed ke target and elapsed-time origin.")
    else:
        # No parallel numerical admission model: existing exact projection remains
        # authoritative for the engine's narrower mathematical domain.
        try:
            projection = project_application(problem_record, dataset_record)
        except AdapterError as error:
            paths = error.field_paths or ("inputs",)
            category = "unsupported_model" if error.code == "unsupported_model" else "needs_measurements_or_assumptions"
            for path in paths:
                field_category = category
                if path == "dataset/body/rows" or path.endswith(("/time_unit", "/concentration_unit", "/rate_unit")):
                    field_category = "needs_measurements_or_assumptions"
                elif path.startswith("problem/body/target"):
                    field_category = "unsupported_claim_semantics"
                issue(field_category, path, error.code, str(error))
    precedence = ("unsupported_model", "unsupported_claim_semantics", "needs_measurements_or_assumptions")
    status = next((category for category in precedence if any(i["category"] == category for i in issues)), "eligible_supported_problem")
    bindings = None if projection is None else {
        "problem_id": projection["binding"]["problem"]["id"],
        "problem_digest": projection["binding"]["problem"]["digest"],
        "dataset_id": projection["binding"]["dataset"]["id"],
        "dataset_digest": projection["binding"]["dataset"]["digest"],
        "projection_digest": projection["projection_digest"],
    }
    return {"policy": PAPER_MAPPING_POLICY, "status": status, "issues": issues,
            "limitations": limitations, "input_binding": bindings,
            "execution_approved": False, "source_authenticity_verified": False,
            "mathematical_verification": "not_run"}
