## Initial CPT retrieval diagnostics

Configuration:
- Hybrid retrieval: dense + BM42, RRF fusion
- Candidate count: 15
- Reranker: ms-marco-TinyBERT-L-2-v2
- FlashRank: 0.2.10
- Source snapshot: 20261114T213307398026Z

Observed supporting-passage ranks:

| Case | Hybrid | Reranked |
|---|---:|---:|
| Employer offer-letter checklist | 8 | 3 |
| Remote-work documentation | 2 | 11 |

Remote-work diagnostic:
- Full query–passage pair: 197 tokens; no truncation.
- Replacing only the target candidate's text with its exact
  remote-work excerpt improved its reranked position from 11 to 6.
- Other candidates were unchanged.
- This tested reranking only; it did not test retrieval after rechunking.

Interpretation:
- Reranking helped one case and hurt another.
- Mixed-topic content affected one passage's ranking.
- Neither disabling reranking nor changing chunking is yet
  established as a general improvement.
- These are exploratory observations, not aggregate benchmark metrics.

## Development baseline

Run: retrieval_20261115T025051543015Z.json
Pipeline: dense + BM42 → RRF → FlashRank
Candidates: 15
Final passages: 5
Development cases: 6

- Supporting-passage Hit@1: 4/6 (66.7%)
- Supporting-passage Hit@5: 5/6 (83.3%)
- Failed case at top 5: umd_cpt_remote_001

Labels identify selected sufficient supporting passages, not every
relevant chunk. Results cover one UMD CPT source snapshot and do not
measure generated-answer correctness.

## Hybrid versus reranked development comparison

Same six development questions; same 15 candidates per question.

| Pipeline | Supporting Hit@1 | Supporting Hit@5 |
|---|---:|---:|
| Hybrid RRF | 2/6 (33.3%) | 5/6 (83.3%) |
| Hybrid RRF + FlashRank | 4/6 (66.7%) | 5/6 (83.3%) |

Decision: retain FlashRank while investigating its regressions.
These exploratory results do not establish performance beyond this set.

The four pipelines have equal development Hit@5 but different misses.
Dense, sparse, and hybrid miss the offer-letter checklist at top 5.
Hybrid + FlashRank retrieves that checklist but misses remote-work
documentation. FlashRank improves the selected supporting passage's
rank on five of six questions and worsens it on one.

Next experiment: fuse hybrid and reranked orders with RRF.
Evaluate on development cases before considering a production change.

## Hybrid/reranked fusion experiment

Equal-weight RRF over hybrid and FlashRank orders.
Constant: 60. Tie-break: original hybrid rank.
Development cases: 6.

- Supporting Hit@1: 3/6 (50.0%)
- Supporting Hit@5: 6/6 (100.0%)
- Offer-letter and remote-documentation passages both ranked fifth.

Compared with FlashRank alone, fusion improved top-five coverage
but reduced first-result hits. The app currently uses four passages,
so the measured top-five improvement does not directly establish
an app improvement.

Decision: freeze this candidate configuration for held-out comparison.
Do not tune the fusion constant on held-out results.

## Held-out comparison

Run: held_out_20261115T032135512444Z.json
Four questions from the same UMD CPT snapshot.
Configurations frozen before inspecting results.

Complete labeled evidence coverage at both @4 and @5:
- Dense: 4/4
- Sparse: 4/4
- Hybrid: 4/4
- Hybrid + FlashRank: 3/4
- Hybrid/FlashRank RRF60 fusion: 3/4

All pipelines achieved any-evidence coverage of 4/4 at @4.
The development-set fusion improvement did not generalize here.

Decision: do not promote fusion. Production remains unchanged.
These held-out results have now been inspected; further tuning
against them makes them development evidence for future experiments.

## Generation outcome checks

Run: generation_20261115T140237357569Z.json
Four development examples with supplied passages; retrieval excluded.

Expected outcomes matched: 4/4.
Observed generation + validation latency: 1.121–3.166 seconds.

Cases covered:
- Sufficient remote-work evidence → cited answer
- Unrelated workshop evidence → insufficient evidence
- Unresolved pronoun → clarification
- Explicit workshop question → cited answer

One run per example. Outcome matching does not establish factual
correctness, citation support, or general abstention reliability.

## Source-wording ambiguity development checks

The saved HTML and extracted text for snapshot 20261114T213307398026Z
both contain the checklist item "The specific term internship or co-op".
No extraction correction or policy interpretation was applied.

The generation prompt now explicitly distinguishes an unclear source from
an unclear question. A supported checklist should quote and flag the
ambiguous item. A question requiring a definitive interpretation of that
item should produce insufficient_evidence unless supplied evidence resolves it.
The phrase alone must not become an academic-semester or literal-wording
requirement.

scripts/evaluate_generation.py now includes three additional development
cases using the preserved offer-letter excerpt: checklist ambiguity,
direct interpretation, and an explicit start/end-date control. Each includes
manual review criteria. The original four examples remain.

Validation: Python parsing and offline fixture-loading checks passed.
The user subsequently ran the live evaluation in the configured project
environment: generation_20261115T141322023701Z.json. All seven expected
outcomes matched. The saved answers were then reviewed by the coding
assistant against the supplied excerpts and new case criteria:

- remote_sufficient: preserves offer letter OR supporting documentation
  and the employer-provided remote-work address, with a citation.
- remote_insufficient: abstains on unrelated workshop evidence.
- ambiguous_question: requests clarification without inferring a referent.
- explicit_question: correctly states workshop attendance is not required.
- offer_letter_preserve_ambiguity: includes all supplied checklist items,
  preserves the address and research-phase conditions, quotes the ambiguous
  phrase, and explicitly flags its meaning as unclear. Neither interpretation
  is asserted as a requirement.
- offer_letter_term_interpretation: returns the fixed insufficient-evidence
  message without choosing a meaning or asking the user to clarify.
- offer_letter_explicit_dates: answers the explicit start/end-date question
  with a citation, without adding a requirement from the ambiguous item.

These observations support the intended behavior in this single development
run, not general factual accuracy or abstention reliability. Retrieval was
excluded. The offer-letter fixture stops before the start/end-date footnote;
it retains a dangling asterisk and does not test preservation of that
footnote's conditions. That remains a fixture limitation for a future check.
Review findings are recorded here; the original run JSON is unchanged and
its generated manual_review_status fields still say pending.
No claim-support validator was added; citation_ids_valid still checks IDs only.

## Date-footnote fixture extension (live run pending)

The offer-letter fixture now includes the complete date footnote from the
same preserved snapshot. The three existing offer-letter cases therefore
receive a longer excerpt than in generation_20261115T141322023701Z.json;
their results will not be a comparison with unchanged inputs.

Added offer_letter_date_footnote_conditions as an eighth development case.
Review must check the CPT-associated course semester restriction, both
timing triggers (start date has passed OR will pass by ISSS review), and an
email from the employer indicating a new later start date. It must not
invent permission to work or an approval guarantee, or use the footnote
to resolve the separate ambiguous checklist phrase. The general checklist
case's review criteria now also cover the footnote.

Offline validation passed: eight unique cases load, and all four offer-letter
fixtures contain the exact snapshot excerpt with the complete footnote.
Generation and retrieval code are unchanged. Reports now also record the
evaluator hash and derive their scope count from the actual case count.
Run `python -m scripts.evaluate_generation` in the configured project
environment, then review the saved answer text. No live result is claimed yet.

## Date-footnote run review

Run: generation_20261115T141607850959Z.json, executed by the user.
Seven expected outcomes matched out of eight scheduled cases. The remaining
case, offer_letter_explicit_dates, raised ClientError and produced no answer.
Its cause is unknown: this report contains only the exception class, not
an API error code. This is one execution error, not an observed wrong answer.

Coding-assistant review against the supplied evidence:
- The four original cases retain their expected behavior and supported text.
- The checklist includes the supplied requirements and conditions, flags the
  ambiguous phrase without resolving it, and includes the date footnote.
  It compresses the two timing triggers to "if the start date passes by the
  time ISSS reviews" rather than explicitly repeating "has passed or will pass".
  This is less explicit; it is not evidence of strict wording preservation.
- The direct interpretation question abstains as expected.
- The new footnote-specific answer preserves the CPT-course semester
  condition, both timing triggers, and the employer email with a new later
  start date. It invents neither work permission nor an approval guarantee.
- The errored case cannot be reviewed for answer content in this run.

The prompt is unchanged. The evaluator now supports --case for targeted
reruns, records numeric exception codes without raw error text, and reports
execution errors separately from completed outcome mismatches. Re-run with
`python -m scripts.evaluate_generation --case offer_letter_explicit_dates`.
Keep this original report; a later successful retry does not erase the error.
The report JSON remains unchanged; review is recorded here.

## Targeted explicit-date retry

Run: generation_20261115T141852562773Z.json, executed by the user.
Only offer_letter_explicit_dates was rerun. Outcome matched: 1/1;
execution errors: 0. Generator hash matches the preceding eight-case run.

Coding-assistant review: the answer states that the letter must include
specific internship/co-op start and end dates and cites [S1], which directly
supports the claim. It does not infer a requirement from the ambiguous
"specific term" item. This meets the narrow case criteria; it does not test
full footnote coverage, which is covered by the separate footnote case.

The eight-case run and targeted retry together provide observed expected
outcomes for all eight development cases, with one recorded API execution
error before retry. This is not a single clean 8/8 run and does not establish
general answer accuracy or API reliability. The earlier error's cause remains
unknown. Original report JSON files are preserved; review is recorded here.

## First-turn end-to-end development check (live run pending)

Added scripts/evaluate_end_to_end.py for the four offer-letter development
questions. It calls the app's rewrite_query with empty history, then hybrid
retrieval plus FlashRank with initial_k=15 and final_k=4, then generation.
Supplied fixture passages are not passed to generation. No production
retrieval settings or generation prompts were changed.

Reports save actual retrieved text, point IDs, citation IDs in display order,
scores, source-card metadata including independent freshness fields, answers,
implementation hashes, and stage-specific errors with numeric codes only.
Reference snapshot labels do not verify the live collection's version.
Reference outcome matches compare against supplied-evidence expectations;
they cannot establish evidence coverage or answer support. Review both the
retrieved passages and claims, including whether an abstention is appropriate
when retrieval omits required evidence. This tests first-turn backend behavior,
not conversational rewriting with history or Streamlit rendering.

Four offline orchestration tests passed, covering production settings, live
evidence rather than fixture leakage, error handling, and empty retrieval.
All ten current offline tests passed together. No new live result is claimed.
Run `python -m scripts.evaluate_end_to_end` in the configured project environment.
Use `--case CASE_ID` to retry one case if needed. Reports use end_to_end_*.json.

## First end-to-end run review

Run: end_to_end_20261115T142328883386Z.json, executed by the user.
Three reference outcomes matched; one generation-stage ClientError with
numeric code 429 interrupted the footnote case. There were no completed
reference-outcome mismatches, but status matching hid a content omission.

Coding-assistant review of actual retrieved evidence and answers:
- offer_letter_preserve_ambiguity: checklist evidence is [S3] at rank 3;
  the complete date footnote is [S1] at rank 1. The answer preserves the
  checklist, conditional research statement, and ambiguity. Its added remote
  documentation statement is supported by [S1]. However, it omits the
  semester restriction and employer-email timing condition required by the
  case criteria, even though [S1] supplies both. This is a generation
  completeness failure for this case, not a retrieval miss or invalid ID.
- offer_letter_term_interpretation: the checklist phrase is available in
  [S2], but the passages do not establish either proposed interpretation.
  Insufficient-evidence abstention is appropriate.
- offer_letter_explicit_dates: the date requirement is supported by [S1];
  the added CPT-course semester restriction is supported by [S2]. No
  requirement is inferred from the ambiguous phrase. Meets the narrow criteria.
- offer_letter_date_footnote_conditions: the complete required footnote is
  retrieved at rank 1. Generation failed with 429, so no answer can be reviewed.
  This is an execution error, not a missing-evidence result.

All sixteen saved passages retain retrieved_at=2026-11-14T21:33:07.398026+00:00
and source_updated_at=null. This verifies freshness forwarding in this
backend run, not Streamlit rendering or a policy update date.

The original report is preserved. Do not describe 3/4 reference outcome
matches as answer accuracy. Generation and retrieval settings are unchanged.
After the API rate limit permits, retry only the interrupted case with
`python -m scripts.evaluate_end_to_end --case offer_letter_date_footnote_conditions`.
The checklist's omission of a condition in a separate retrieved passage
remains open for a focused generation change and subsequent development check.

## End-to-end footnote retry: repeated rate limit

Run: end_to_end_20261115T142526130747Z.json, executed by the user.
The targeted footnote case again retrieved four passages, with the complete
footnote at rank 1 (point 4a95b113-edd3-53bd-a38d-ceb9cea70b06), then failed
at generation with ClientError code 429. No answer was produced. This is
another execution error; reference_outcome_match is null, not an observed
wrong answer. The case remains unreviewed end to end for generated content.

Do not continue immediate retries. The saved numeric code establishes a
rate/quota-limit response but does not identify its quota category or reset
time. No change to the model, retrieval, or generation prompt was made for
this retry. The earlier checklist completeness omission remains a separate
open issue. Original run reports are preserved.
