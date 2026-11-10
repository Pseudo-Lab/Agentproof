# v5: authoritative workspace specifications and controlled check opportunities

Status: protocol frozen before the first real v5 request, 2026-11-09. Exploratory technical-report study, not the final seven-task preregistered confirmation study in CARD.md. Prior v3/v4 findings informed this design; no claims of fresh confirmatory hypotheses.

## Identifiable question

With a common declaration that current workspace specifications outrank a generic skill, does a generic pre-check improve complete output correctness over neutral hook opportunities when the evidence file is unpointed? Does a post-check correct skill-consistent wrong outputs, or merely other errors? Is any gain larger in mismatched E1 than matching E0?

Legacy limitation: v3 tells the agent to satisfy target_contract.json, but L3 does not declare the authority of its unmentioned evidence. Its score therefore reflects an underspecified discovery task as well as skill application. V5 declares workspace authority in every arm; it is a new prompt version and results will not be pooled with v3.

## Conditions

| Arm | After first read_skill | First completion attempt |
|---|---|---|
| B | none | accept |
| N | neutral continuation | one neutral completion message |
| C2 | compare 1–2 concrete premises with workspace evidence, list workspace first | neutral |
| V | neutral | validate output against current specifications; correct if needed |
| P | same pre-check as C2 | same validation as V |

N/C2/V/P have identical hook *opportunities*, not necessarily equal realized tool usage or text length. Conditions share tools, model, task/authority prompt, limits. No specific path, file-type hint, value, or answer is supplied in a hook. Post hook fires once. All outputs immediately before the post hook and at final stop are archived; no grader feedback is shown to the agent.

## Tasks and scope

Existing graph/csv/events generators and full graders unchanged. E0/E1 share inputs and contract; evidence differs. L3 is unpointed, L2 has the existing exact pointer. The common authority instruction is identical in all cells. Hidden L3 crosses all five arms, 3 tasks × 2 envs × 5 inputs × 5 arms = 150. Pointed L2 uses B only, 3 tasks × 2 envs × 5 inputs = 30. Therefore 180 planned trials. Input seeds 2026111001–2026111005, distinct from all earlier seeds. Task families are only three; input variation is not new task-family evidence.

Model: gpt-5.4-mini-2026-03-17, reasoning low, no temperature/model seed, no automatic retries. Four existing tools. Limits common to all arms: 20 requests, 20 tool calls, 300 seconds, cumulative 150k input / 20k output tokens; per response output cap 4096. The Python subprocess remains an imperfect local sandbox, not a network-isolated Docker environment. That limitation is explicit.

## Outcomes and diagnostics

- Primary outcome: full target grader pass AND normal agent completion. Errors and limits are non-success; also report API/infra separately.
- Diagnostic `correct`: target full grader passes, regardless of agent stop status (status remains separate).
- `skill_consistent_mismatch`: E1 target fails but output passes the *full E0 grader*. This identifies an output compatible with the fixed skill, not model intention or causal anchoring.
- `other_error`: neither full grader passes; includes mixed errors. Never force these into premise-use labels.
- `missing_output`: no required output.
- Explicit successful read_file of the exact evidence path is a lower-bound observation; Python file access can evade it. Preserve traces, do not interpret path mentions as comprehension.
- Archive before-post and final outputs. Report wrong→correct, other-error→correct, correct→wrong transitions separately. B gets its completion snapshot without another model request.

## Planned exploratory comparisons

1. E1 L3: C2−N and C2−B complete success. Report all task-family counts.
2. E1 L3: V−N, P−C2, P−V, plus normal E0 counterparts.
3. E1−E0 interaction for each intervention relative to N.
4. Manipulation: B E0−E1, and B L2−L3 separately within E0/E1. Lack of observed harm prevents a recovery claim; a small sample cannot establish no harm.
5. Pre/post correction transitions by task and condition, using full-output diagnostics.
6. Token usage, list-price cost, request/tool counts, errors, missing/unfinished cells.

Uncertainty: equal-task-family effects and 10,000 task-family bootstrap draws with fixed analysis seed 20261110. Only 3 task clusters: intervals are descriptive and may be degenerate; no generic significance or non-inferiority claims. Do not drop tasks based on performance. Do not add together incompatible v3/v4/v5 results.

## Cost and stopping

User authorized total $10, including existing 2026-11-09 runs. Start real v5 only after prior runs finish and subtract their conservative ledger costs. Freeze v5 cap as min($3.30, remaining authorization minus $0.10 reserve). Use atomic reservations across workers, serializable per-request spend, and conservative charge for requests whose billing is unknown after a transport error. Three consecutive infrastructure errors stop new work. No budget extension without explicit instruction. If budget stops the experiment, keep all attempted trials and report incomplete cells; never call it complete.
