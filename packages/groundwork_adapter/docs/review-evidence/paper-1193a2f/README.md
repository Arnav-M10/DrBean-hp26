# Clean committed paper-science candidate

Owner 1 ran these checks at clean **1193a2f18ed108f53d4cbce942b2fa1dc3d6eef6**.
This includes the fixture-semantic and both-compatible HTTP regressions plus
regenerated current example packets. Scientific source digest remains
`510580863d6dbb13a569f7f28ad9822111a50356981208e08608827fcef4ee69`.

The full engine runner reports 306 tests, with a missing-backend DTO skip and an
optional HTTP class setup skip. The DTO separately passed under the backend;
`both-compatible-http/` retains the separately executed passing HTTP test and
native bytes/anchors, with clean flags before and after. This is the actual
committed regression, distinct from the earlier dirty development capture.

All 7 ordinary HTTP cases (214 predicates), 22 native controls and the required
offline scientific gate passed again. Commands and isolated explicit-runtime
environment are in `commands.json`; no credentials are retained. This is existing
source-image/science flow acceptance, not PDF parsing, Gemini accuracy or final
combined-paper release approval. The original candidate's full backend results
retain their own `8b29b3f` label; no backend production file changed between them.

Current checked-success and portable baseline replay commands also passed at
this commit. The initial `8b29b3f` CI engine failure was the documented examples'
source-identity mismatch, now corrected by regenerating current examples. Other
initial CI jobs passed; later CI results are reported separately in PR #33.

The subsequent genuinely unresolved HTTP regression, when delivered, is a later
candidate check and is not retroactively attributed to this run.
`SHA256SUMS.json` hashes all files except itself.
