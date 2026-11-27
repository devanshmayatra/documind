# Evaluation notes

The [32-question retrieval comparison](#expanded-32-question-retrieval-comparison-2026-11-26-eastern)
is the latest three-way comparison. Earlier experiments and generation checks
are recorded below in chronological order.

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

## Cross-passage checklist prompt revision (2026-11-26)

The generator prompt now explicitly asks checklist answers to inspect all
supplied passages for relevant footnotes and qualifications, include them
beside the affected item or in a short note, and cite their actual supporting
passage. It preserves all conditional branches and the document provider,
and forbids importing unrelated restrictions merely because they were retrieved.
Retrieval settings, JSON outcomes, and citation-ID validation are unchanged.

An offline replay uses the exact four saved passages from the checklist
case in end_to_end_20261115T142328883386Z.json. It exercises the actual
generate_grounded_answer and build_answer_prompt functions with only the
API client mocked. It verifies that the footnote at [S1] and checklist at
[S3] retain their text and citation mapping in the sent prompt, alongside
the new cross-passage instruction. All fourteen offline tests passed.

The mock deliberately returns the old incomplete answer: it still receives
citation_ids_valid, demonstrating that no semantic completeness validator
was added. These checks verify prompt plumbing, not a model behavior fix.
The omission remains unverified until a live answer is reviewed. When API
quota permits, run:
`python -m scripts.evaluate_end_to_end --case offer_letter_preserve_ambiguity`.
Review for both date-footnote conditions with citations, preserved ambiguity,
and no unrelated requirements. Retain prior reports for comparison.

## Checklist rerun: retrieval exception (2026-11-26)

Run: end_to_end_20261126T175650025037Z.json, executed by the user.
Embedding returned HTTP 200 in the supplied console log, but the case then
failed in retrieval with ResponseHandlingException and no numeric code.
No passages or answer were returned, and generation was not reached.
The log also reports that Qdrant server-version discovery failed; neither
that warning nor the saved exception establishes the underlying cause.
The revised prompt's effect remains unverified by a live answer.

The evaluator now records error_cause_type from Python's exception chain,
without exception messages or response bodies. An offline wrapped-timeout
test verifies that only the class names are captured. This improves future
diagnosis; it does not fix or identify the underlying retrieval failure.

## Retrieval retry: underlying ConnectError

Run: end_to_end_20261126T175854467891Z.json, executed by the user.
The retrieval-stage ResponseHandlingException now records its underlying
exception as ConnectError. Embedding succeeded; no passages were returned
and generation was not reached. This narrows the failure to a connection
problem rather than an observed answer or citation failure. It does not
identify DNS, endpoint, network, TLS, or cluster availability as the cause.
Stop repeating embedding/generation evaluations until Qdrant connectivity
is restored. Check cluster status and endpoint configuration first. No
production configuration, compatibility checks, or data were changed.

## Revised checklist prompt: completed live review

Run: end_to_end_20261126T180118110525Z.json, executed by the user.
One reference outcome matched, with zero execution errors. Retrieval and
generation succeeded; this does not establish the cause or resolution of
the preceding connection failures.

The retrieved point IDs, order, and passage text match the checklist case
from end_to_end_20261115T142328883386Z.json. Coding-assistant review finds
that the revised answer now includes both previously omitted qualifications:
dates within the semester of the CPT-associated course, and employer email
with a new later start date when the original date has passed OR will pass
by ISSS review. Both cite the actual footnote passage [S1]. The checklist
items cite [S3], the research-phase condition is retained, and the ambiguous
phrase remains quoted and explicitly unresolved. Remote-documentation
conditions are also supported by [S1].

However, the answer adds a winter-course exception summary from [S4]. It
mentions Fall/Winter or Winter/Spring continuity and the same weekly hours,
but does not explicitly preserve the same-employer condition or continuation
through the duration of Spring for the Winter/Spring branch. This extra
conditional summary is incomplete; do not label the entire answer a clean
grounding/completeness pass. The original date-footnote omission was absent
in this single observed run, while over-expansion introduced another review
concern. No automatic claim-support check exists.

This is development evidence, not benchmark accuracy or proof of a general
prompt improvement. The prompt and retrieval remain unchanged after review;
the original report is preserved, with review recorded here.

## Checklist scope and exception completeness revision (2026-11-26)

The prompt now distinguishes direct document footnotes/conditions from
separate course-registration exceptions or special eligibility scenarios.
General checklist answers should retain the former without adding the
latter unless the question asks about or explicitly establishes the scenario.
When an exception is relevant, every stated prerequisite must stay together;
partial prerequisites must not be presented as sufficient, and missing scope
must not be inferred. Retrieval and citation-ID validation are unchanged.

The checklist development case now includes review criteria for avoiding
unrequested winter-course expansion and preserving same-employer, weekly-hour,
and full-duration conditions if the exception is discussed nevertheless.
Offline prompt-delivery checks replay both the original omitted-footnote
report and the later incomplete-winter-exception report. All sixteen offline
tests passed. Mocked recorded answers still pass ID validation: these checks
do not demonstrate semantic correction. No new live model result is claimed.

Next check: `python -m scripts.evaluate_end_to_end --case offer_letter_preserve_ambiguity`.
Review the answer for retained direct footnote conditions, unresolved ambiguous
wording, and absence of the unrequested winter-course exception. Preserve all
prior runs; this remains iterative tuning on inspected development evidence.

## Checklist scope revision: generation service error

Run: end_to_end_20261126T180654698914Z.json, executed by the user.
The supplied console shows successful embedding and Qdrant query requests,
then HTTP 503 from generation. No answer was produced, so this run cannot
evaluate the revised checklist scope or exception-completeness behavior.
Record this as an execution failure, not a completed wrong outcome. The
previous answer's winter-exception concern remains unverified after revision.
No prompt or retrieval change is justified by this service response alone.
Keep the report and retry the same targeted case later rather than changing
the model or repeatedly tuning the prompt around an API execution failure.

Run: end_to_end_20261126T180918121242Z.json, subsequent user retry.
Again, four passages were retrieved, then generation failed with ServerError
503 and produced no answer. This is the second consecutive 503 for the
scope revision, not another observation of answer quality. Pause live reruns
for now; retain the current prompt and mark its model behavior unverified.
No model, retrieval, or prompt changes were made in response to these errors.

## Account-free shared answer cache (2026-11-26)

Added core/answer_cache.py (SQLite) and core/answer_service.py. The app has
no account gate and now checks the shared cache before rewriting/retrieval/
generation for eligible general first-turn questions. Matching lowercases
and normalizes whitespace only; it is not semantic similarity matching.
Answers, the question, and ordered source cards persist in data/cache/, which
is excluded from Git. TTL is 24 hours. The UI offers a shared-cache opt-out.
No visitor question list or persistent cross-refresh conversation was added.

Only citation_ids_valid answers with no citation errors and passages matching
current registered snapshot URLs, hashes, and retrieval timestamps are saved.
Retriever now forwards source_id and source_content_sha256 for this check.
Follow-ups, obvious personal/identifier questions, abstentions, API failures,
and unregistered uploads bypass storage. The personal-information heuristic
is not complete and is described as such in README. Valid IDs still do not
prove support; caching does not repair the known grounding limitations.

Indexing through upload_chunks invalidates and suspends cache reuse around
uploads, including partial failures. Fingerprints cover pipeline code,
registry/snapshot metadata, and the configured Qdrant endpoint. External
Qdrant edits bypass this invalidation and require manual cache clearing.
An interrupted indexing process leaves reuse disabled for operator review.
SQLite storage errors in the question path fall back to the existing RAG
pipeline. Public ingestion is disabled by default; the explicit environment
setting is for a trusted operator instance, not a public authentication scheme.

Verification: all 31 offline tests passed. Real SQLite checks cover persistence
across instances, normalization, TTL, pipeline and corpus invalidation, and
in-flight writes after failed updates. Actual answer-service checks verify a
second visitor bypasses all three pipeline calls while retaining citations
and source dates; opt-out, history, invalid IDs, source mismatches, API errors,
and unavailable storage are also checked. Application modules parse.
No live Gemini/Qdrant or Streamlit browser test was performed, no deployment
was made, and no latency/cost/accuracy improvement was measured. Hosting must
preserve the local cache disk; independent replicas do not share this SQLite
file. Existing retrieval algorithms, final_k=4, and generator prompt remain.

## F-1 Compass UI redesign (2026-11-26)

User approved a light reference-desk direction: off-white, charcoal, muted
red. Updated app.py, a dedicated stylesheet and compass SVG, and Streamlit's
light theme. Replaced legacy DocuMind presentation, model badges, decorative
emoji, and the unconditional Active indicator with UMD CPT scope, starter
questions, calmer chat controls, and readable numbered source cards. An
unavailable collection count now displays as unavailable rather than zero.
Source dates and Unknown values are unchanged in meaning; public ingestion
and shared-answer opt-out remain available under the existing rules.

All 31 offline regression tests passed. Real Streamlit AppTest checks also
passed for the empty state, public upload visibility, every starter's question
mapping, opt-out persistence, recorded chat/source rendering, and conversation
reset. Browser inspection covered the desktop workspace and a 390px mobile
layout: document width stayed at 390px and source dates remained separate.
UI preview used recorded development data and mocked services, not live
Gemini/Qdrant. The temporary preview server was stopped after verification.
No retrieval, ranking, generation, caching, or account-access behavior changed.
This is interface verification, not evidence of answer-quality improvement.

## Expanded UMD employment corpus (2026-11-26)

Indexed the UMD ISSS On-Campus Employment snapshot 20261126T194807975501Z
(4 chunks) and Unpaid Work snapshot 20261126T194808091994Z (6 chunks)
alongside the original CPT snapshot. Source update dates are unknown.
Production still uses hybrid retrieval, FlashRank and four final passages.
Evaluation suites ran sequentially with 30 seconds between cases.

- Development retrieval (`ranking_comparison_20261126T195203619505Z.json`).
  Hit@1 and Hit@5 were 2/6 and 4/6 for dense, 1/6 and 4/6 for sparse,
  1/6 and 5/6 for hybrid, and 4/6 and 5/6 after FlashRank. The remote-work
  supporting point moved from rank 11 in the prior reranked run to rank 13.
- Previously inspected held-out retrieval (`held_out_20261126T195353351141Z.json`).
  Dense, sparse and hybrid each covered all labeled groups for 4/4 questions
  at both cutoffs (4 and 5). FlashRank and RRF60 each covered 3/4 at both
  cutoffs. The research-exception question lost one of two groups.
- Live end-to-end (`end_to_end_20261126T195812032729Z.json`).
  All six cases retrieved four passages. On the two new development questions,
  inspection confirmed that rank 2 contained the partial-week rule and the
  full volunteer criteria respectively. All six generation requests returned
  HTTP 503. There were zero completed answers for status or claim review.
- Supplied-evidence generation (`generation_20261126T200505622584Z.json`).
  All eight cases returned Gemini HTTP 503. Across both generation suites,
  none of the 14 failed cases returned HTTP 429 or a scorable answer.

## Deployment evaluation (2026-11-26)

The paced live run `end_to_end_20261126T233822771665Z.json` matched
five reference statuses across six development cases, with one Gemini
HTTP 503 in the CPT date-footnote case and zero completed status mismatches.
The saved report retains the four retrieved passages per case.
The isolated retry `end_to_end_20261126T233902325791Z.json` retrieved
evidence, then hit Gemini HTTP 429. The date-footnote case remains
unscored in this evaluation.

Manual review of the completed outputs:

- The CPT offer-letter checklist included the separate date footnote,
  preserved the ambiguous checklist phrase, and kept the winter exception out.
- The term-interpretation case abstained, consistent with the ambiguous excerpt.
- The explicit-dates case cited the dates requirement and both footnote conditions.
- The on-campus case cited the Sunday-to-Saturday week and midweek 20-hour cap.
- The volunteering case cited all four criteria and stayed focused on
  volunteering. Its opening bullet presents the source's narrower summary
  (charitable or humanitarian organizations) as an additional criterion.
  The same answer also lists the broader nonprofit purposes from the formal
  criteria. Treat this as a wording limitation despite the expected status.

The Docker image built and returned HTTP 200 from Streamlit's health endpoint.
A separate in-container AppTest loaded the public UI with three saved source
snapshots and uploads disabled. All 32 offline tests and the offline Streamlit
checks passed. Deployment to a public host was outside this run.

## Expanded 32-question retrieval comparison (2026-11-26 Eastern)

The expanded source-authored set includes 18 CPT, seven on-campus employment,
and seven unpaid-work questions. Labels were written before running the three
variants and matched against the indexed versions of the three official UMD
snapshots (23, four, and six passages). Each evidence group is required for
complete coverage. Multiple matching passages can satisfy the same group.
The set overlaps topics in earlier development and held-out checks. It was
created from the indexed material and is not an independent held-out set.

The same Gemini embedding was shared between dense-only and hybrid per
question. Both retrieved 15 candidates from the live collection. FlashRank
reordered the hybrid list. The run waited five seconds between questions,
completed all 32, and used no generation calls. The report records snapshot
hashes, matching evidence IDs, and rankings. Results reflect the labeled
passages and these questions, so apparent misses can include unlabeled
support. The evaluation does not measure answer quality or live traffic.

| Retrieval | Hit@1 | Hit@5 | Complete evidence @4 |
| --- | ---: | ---: | ---: |
| Dense only | 24/32 | 31/32 | 31/32 |
| Hybrid | 25/32 | 31/32 | 30/32 |
| Hybrid + FlashRank | 24/32 | 32/32 | 31/32 |

FlashRank moved optional-internship evidence from rank 6 to 3 and the
fall/spring geographic limit from rank 5 to 1 relative to hybrid. It pushed
the research-exception caveat about approval from rank 2 to 14, leaving
that case with incomplete evidence at the production cutoff.
[Labeled question set](retrieval_comparison.json) ·
[Saved rankings and evidence IDs](runs/retrieval_comparison_20261127T012946079043Z.json)
