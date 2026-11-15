# Theoph subject 4

The [R datasets manual](https://stat.ethz.ch/R-manual/R-devel/library/datasets/html/Theoph.html) attributes these observations to a Robert Upton study reported by Boeckmann, Sheiner, and Beal in *NONMEM Users Guide, Part V* (1994). Twelve participants have 11 serum concentration readings each after an oral dose. The manual's worked example selects subject 4, so this case uses the same subject. Selection was based on the published example and its zero time-zero reading, before running a Counterdex search.

The observation file preserves the five data columns in source order from the [Rdatasets CSV export](https://vincentarelbundock.github.io/Rdatasets/csv/datasets/Theoph.csv), rows 34–44. The downloaded full export's SHA-256 was `f9b77033090644cf38c83056c25c8137bca71cf629d7c0159a72ef18095726b0`. `Wt` is kg, `Dose` is mg/kg, `Time` is elapsed hours from oral administration, and `conc` is mg/L. The import file retains all 11 readings and adds the allowance column. Weight and dose are metadata and are omitted from the three-column import.

The time-zero row records 0 mg/L and is retained. The source describes time since administration and gives no separate predose observation for this subject. Other subjects have nonzero time-zero readings, including subjects 1, 7, and 10. Counterdex assumes zero initial concentration; this case does not subtract a baseline or pool subjects. For a fixed positive dose and distinct positive rates, the [R SSfol equation](https://stat.ethz.ch/R-manual/R-devel/library/stats/html/SSfol.html) has the difference-of-exponentials shape used by the supported concentration model. Here a free scale absorbs the dose and other constant factors. Matching the equation's form does not establish that all observations fit the assumed model.

## Run the example

1. Open the classic workspace at the launcher origin, import [subject-04-drbean.csv](subject-04-drbean.csv), and leave all rows included.
2. Name the experiment `theoph_subject_04`, set time zero to oral dose administration, and select **Actual measurements**.
3. Record **0.50 mg/L per row, analyst-chosen sensitivity assumption** as the hard allowance origin. The dataset supplies no deterministic error bounds.
4. Use the exploratory closed claim `ke ∈ [0.10, 0.17] h⁻¹`. The target and search box are analysis choices. Use `A ∈ [0.001, 30] mg/L`, `ke ∈ [0.015, 0.35] h⁻¹`, and `ka ∈ [0.4, 8] h⁻¹`.
5. Review and separately approve the manual check. Report the observed outcome under the stated assumptions. A bounded search can remain inconclusive. This case illustrates a public experimental workflow and supplies no instrument calibration, laboratory validation, or measured time savings.

## Observed result

On application commit `d7abf3b33476cdecae3d4ec5779794255eff1941`, the import showed 11 included readings at 11 distinct times. The manually approved job completed and recorded one evidence record. The result was **No counterexample found**, with checker verification `not_checked`, input binding `matches`, and replay `unsupported`. The bounded search did not establish the exploratory range or model adequacy. This run did not use Gemini.
