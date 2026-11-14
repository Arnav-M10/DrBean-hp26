# Counterdex scientific boundary review history

This is an automated second-reader code and argument review by another coding
agent. It is not a human mathematical sign-off, a formal proof, or an independent
proof-system implementation. This records the initial release review; the
Counterdex rename qualification is tracked separately in
[VALIDATION.md](VALIDATION.md). The reviewed files are `exact.py`, `models.py`,
`analytical.py`, `arithmetic.py`, `resource.py`, `checked.py`, `pipeline.py`,
`replay.py`, `replay_numeric.py`, `identity.py`, and the capability descriptor.

The analytic argument matches the implemented calculation. For rational
`0 <= u <= 1`, the alternating exponential partial sums give
`S33 <= exp(-u) <= S32`. Exact downward/upward rounding onto the `2^-128` lattice
preserves enclosure. Repeated squaring preserves it because both endpoints are
nonnegative. The fixed argument and bit limits bound construction; there is no
adaptive precision search. Interval subtraction and positive scaling by `A`
then enclose the declared concentration formula. Direct differentiation verifies
the initial conditions and fixed linear ODE; the explicit solution exists for
every nonnegative time. This supports this analytic template only.

Historical compatibility requires the **entire** freshly computed enclosure to
lie inside every included observation's closed hard-allowance band. Strict
disjointness proves that the selected candidate violates that observation.
An overlapping enclosure that is not contained remains inconclusive. A failed
construction is not measurement incompatibility. Row-specific allowances,
excluded rows, exact claim endpoints, and problem identity remain distinct.

Fresh replay parses the exported pair bytes, checks their byte identity and the
installed source manifest, binds the independently supplied problem identity,
associates candidate IDs with exact vectors, and recomputes the exact historical
and feasible-grid enclosures. Reuse requires both selected candidates to refer
to the same pair artifact. Stored badges and margins are not proof inputs.
Centers and radii come from the fresh enclosures; only
`abs(p1-p2)-e1-e2-2*eta > 0` establishes separation. Equality means touching bands.
The conclusion concerns only the selected pair; either or both may fail a later
measurement, without establishing uniqueness or global incompatibility.

The review identified and the implementation corrected:

- Directly constructed vectors could lose extra elements during serialization.
- Exact work could bypass the requested evidence tier or a smaller wall budget.
- Source artifacts could be retained without the required pair association.
- Recorded runtime metadata, work counts, tier, and execution state needed
  validation alongside fresh mathematical checking.
- A complete replay record could claim new construction outside its frozen
  construction/extension scope.

The source-association attack was executed: an unrelated source artifact and
changed work count initially passed replay. After correction, the same attack
was rejected with `candidate_mismatch`; a construction-scope mutation was
rejected with `recorded_result_mismatch`. Numerical-record replay checks finite
stored arithmetic, row coverage, and ranking only. It does not establish the
truth of recorded numerical predictions or grant compatibility status.

This reviewer ran **26 persistent model/boundary tests**, all passing, plus
**eight initial independent ad-hoc controls** for exact execution, reuse,
cancellation, limits, and invalid-versus-inconclusive interpretation. The two
replay attacks above were rerun after correction. These results are narrower
than release qualification; the implementation owner's separate execution ledger
covers the complete suite, package-install checks, and source identity.

The supported exact gate is native CPython 3.11 replay with the matching prepared
source. Browser replay is unavailable. Owner 2 must still enforce actual
approval, workspace and revision authority, durable operation identity, atomic
publication, and process supervision for the hard wall limit. Cooperative
cancellation does not replace that supervisor. No review here validates an
instrument's allowance, the suitability of the model, or honest data collection.
The backend's Python 3.12/3.13 environment has not been qualified for this
standalone CPython 3.11 package. The public rename does not change that gate.
