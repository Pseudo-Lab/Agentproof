# E02 controlled follow-up: independent design review

Reviewed 2026-11-09 against repository source; no external API requests executed. This review addresses the new controlled follow-up, not a relabeling of ongoing legacy replications.

## P0 — declare evidence authority equally in every arm

The existing task asks for output satisfying `target_contract.json`, then instructs the agent to stop calling tools once output is written ([tasks.py:30](../src/tasks.py#L30)). L3 removes the only explicit evidence pointer ([tasks.py:92](../src/tasks.py#L92), [tasks.py:112](../src/tasks.py#L112)). Yet grading depends on the environment-specific evidence: edge keys, comma interpretation, and reporting timezone ([tasks.py:119](../src/tasks.py#L119), [tasks.py:189](../src/tasks.py#L189)). CSV deliberately makes the input insufficient to determine interpretation ([tasks.py:65](../src/tasks.py#L65)). UTC timestamps likewise do not determine the intended reporting timezone.

Consequently, legacy L3 is not just hard-to-find evidence: which unmentioned file has normative authority is underspecified. Failure cannot by itself establish irrational skill anchoring. A check intervention may repair the task specification as well as agent behavior.

**Required common wording, inserted in all new arms before the skill:**

> target_contract.json은 기본 요구사항입니다. 작업 공간에 제공된 현재 환경의 근거가 입력 해석과 출력 세부사항을 정하며, 스킬의 일반 절차와 충돌하면 현재 환경의 근거를 우선합니다. 필요한 확인을 마치고 결과를 작성한 뒤 완료를 알리세요.

This supplies an authority rule without identifying a filename, directory, file type, value, or E0/E1. L3 should therefore be described as **unpointed evidence**, not an undisclosed requirement. L2 adds only the existing path pointer. Apply the common wording to both locations and both environments. Remove the incompatible unconditional post-write tool prohibition. Keep the old instruction and results versioned; do not pool old/new results.

## P1 — smallest informative five-arm experiment

Use the three existing controlled tasks, E0/E1, L3, and fresh input seeds. Run:

| Arm | After skill | First completion attempt |
|---|---|---|
| B | None | None |
| N | Neutral continuation | One neutral completion message |
| C2 | Generic premise comparison + workspace listing; no file-type clues | Same neutral message |
| V | Same neutral continuation | Validation and correction message |
| P | Same C2 | Same validation message |

N/C2/V/P form a 2×2 comparison of pre-check and post-validation, controlling hook positions and completion opportunities. B is an extra estimate of hook/continuation overhead. Do not call neutral prompts inert: they can alter behavior. Keep the same message role, timing, tool/model/token limits, and maximum one post hook in matched arms. The original hook is developer-role ([agent.py:189](../src/agent.py#L189)); changing role changes the treatment.

**Minimum useful run:** 3 fresh input seeds × 3 tasks × 2 environments × 5 arms = 90 L3 trials; add B/L2 at those same seeds/environments = 18 trials; total 108. Randomize condition order inside task–seed–environment blocks. This is a small mechanistic follow-up, not a well-powered benchmark. Three seeds are new instances, not three new task families. If affordability is confirmed before any outcomes, increase whole balanced blocks rather than selectively adding successful tasks.

Source caveat: legacy `repeats` reuse a single `plan['input_seed']` ([run.py:125](../src/run.py#L125), [run.py:170](../src/run.py#L170)); a fresh order seed alone does not produce fresh inputs. Record per-trial input seeds explicitly. No model sampling seed is transmitted ([run.py:153](../src/run.py#L153)); avoid claiming deterministic paired model draws.

## P1 — identify correction separately from final success

At the first completed model response with no tool call, copy every output file and record grades **before** injecting the post hook. Existing code stops immediately at this point ([agent.py:173](../src/agent.py#L173)); snapshots must be taken before resuming the loop, not reconstructed from the last write. Snapshot B too, and represent missing/invalid output explicitly. Do not expose oracle scores or grader explanations to the model.

For each matched post comparison (V−N, P−C2), report before/after transitions: failure→success, success→failure, unchanged success, unchanged failure; output hashes; post-hook requests, tools, tokens, cost. Since post conditions share their pre treatment, pre-hook success should be comparable in expectation. Within-run repair is evidence of correction during the continuation, while the randomized between-arm contrast estimates validation beyond neutral continuation.

A repaired final artifact alone does not show that a particular skill premise was corrected. Grade the snapshot and final output against both environment oracles. Call an E1 failure **exactly skill-consistent** only when it fails E1 but fully passes E0. Existing CSV/events graders use complete other-environment equality ([tasks.py:251](../src/tasks.py#L251)); graph's `premise_from_other_env` is weaker, triggering on alternate edge keys before verifying all edges ([tasks.py:233](../src/tasks.py#L233)). Use complete dual grading uniformly. Mixed errors remain **undetermined**, not “not skill related.” An exact E0 artifact establishes compatibility with the skill, not the model's psychological cause.

Keep evidence opening and workspace listing exploratory. Current detectors match argument strings/regexes ([run.py:79](../src/run.py#L79)), so they do not prove successful read, understanding, or use. Audit traces for all small-run failure→success transitions and a balanced sample of unchanged failures; distinguish successful tool return from a path mention.

## P2 — contrasts and honest scope

Freeze contrasts before launch: primary C2−N in E1/L3 (pre-check beyond continuation); exploratory V−N and P−C2 (post-validation); P−V (pre-check conditional on validation); P−N (combined policy); N−B (hook overhead). Also report C2−B for continuity with the card's historical question ([CARD.md:78](../CARD.md#L78)), but do not change which contrast is primary after seeing results.

Report task-specific counts and equal-task average differences. E0 is necessary for harms and for the difference-in-differences `(X−N)E1 − (X−N)E0`. B/L2 versus B/L3 checks the pointer manipulation, and B/E0 versus B/E1 at L3 checks whether mismatch harms baseline behavior. Oracle literal failure is a technical manipulation check, not proof of behavioral harm ([RESEARCH_MEMO.md:105](../presentation/w6/RESEARCH_MEMO.md#L105)).

Do not call non-significance “no effect” or establish harmlessness from ceiling E0. Three task clusters are insufficient for strong population-level inference; any task bootstrap interval is descriptive and highly discrete. Repeated draws improve within-task precision but do not justify claims about unseen tasks, public benchmarks, or models. Existing pilot-based selection of hidden evidence and validation remains part of the provenance even with fresh seeds ([CARD.md:119](../CARD.md#L119)).

## P0 — global budget and failure accounting

The historical controlled C2 estimate is about $0.012/trial ([CARD.md:279](../CARD.md#L279)); 108 trials would be about $1.30 at that rate, but neutral/post continuations can increase cost. Reserve a conservative new-run cap of $2.4 **only if** completed plus in-flight legacy commitments leave that much below the already approved $10 global total. Do not treat every run's cap as a new allowance. Record committed/in-flight costs; stop before another request's conservative cost bound would breach the global limit ([agent.py:142](../src/agent.py#L142)). No new dollar authorization is implied by this review.

Keep infrastructure/API failures in an execution-policy success denominator; additionally report artifact success among evaluable trials and the explicit error counts. Do not silently replace failures or rerun selectively. If budget stops a block, disclose the incomplete block and achieved cell counts; avoid presenting the intended 108 as completed. The current memo already shows that API-error exclusion changes interpretation ([RESEARCH_MEMO.md:133](../presentation/w6/RESEARCH_MEMO.md#L133)).

**Permissible chapter claim after this run:** evidence about generic pre-check and post-validation on three controlled, explicitly authoritative but path-unpointed task families. Legacy replications test stability of earlier results; they do not supply the missing controls or validate a new treatment.
