# Follow-up experiment protocol

## Scope

Keep the outcome as Plan quality. The old 12 cases remain the anchor set. Four challenge cases were authored and frozen before this run to reduce the ceiling risk seen in the prior run; they are analyzed as a separate `challenge` layer. Mock/smoke scenarios are not included in real performance results, and no scenario is tuned to force a 100% outcome.

## Conditions

| Group | Planner | Candidate count and synthesis |
|---|---|---|
| A | `gpt-6.1-sol` | One plan |
| B | `gpt-6-luna` | One plan |
| C | `gpt-6-luna` | Three homogeneous candidates, then Luna synthesis |
| D | `gpt-6-luna` | Five homogeneous candidates, then Luna synthesis |
| E | `gpt-6-luna` | Three role-diverse candidates (planner, risk/dependency reviewer, verification/recovery reviewer), then Luna synthesis |

All model calls use a 12,000 completion-token cap. Scoring uses `gpt-6.1-terra`, distinct from the generator models. It is still an OpenAI judge, so this reduces direct same-model evaluation but does not establish provider-independent or human-validated correctness. The judge receives the same task, reference checklist, and final Plan; it does not receive group, model identity, or candidate plans. Deterministic JSON-contract checks remain in place.

## Cases and planned scale

Run the original 12 cases plus `challenge_cases.json`: 16 tasks × 5 groups × 3 repeats = 240 planned Plan outcomes. The four frozen challenge tasks test incompatible rollout constraints, restricted-data analysis, explicit schedule infeasibility, and recovery objectives. The challenge layer is reported separately; the original 12 stay comparable as an anchor. No code execution or task completion is measured.

With one generation attempt per sample, the design makes up to 768 generation calls plus 240 judge calls (1,008 total); invalid plans skip judge calls. Retries add attempts and are included in cumulative cost. This is not an equal-dollar-budget test: report the observed quality-cost curve and actual recorded spend.

## Cost and attempt ledger

Each request has a unique `call_id`, stage, model, timestamp, latency, status, returned input/output/cache usage, configured rate, and estimated cost. A request without reliable usage is retained with `cost_usd: null` and `billing_status: unknown`; it is never counted as zero. HTTP and transport failures record the status/error class without saving response bodies or authorization data. Resume attempts remain separate record files. The summary uses the latest outcome per task × group × repeat for quality and all recorded API attempts for cumulative spend.

The recorded dollar figure is a token-based estimate using the standard short-context rates in `experiment.toml`, not an invoice. Reconcile it with provider billing when available.

## Reproduction

Run the mock smoke check separately; its scores are synthetic and excluded from the real run:

```powershell
python run.py --mock --engine python --limit 2 --repeat 1
```

Run the real experiment with the frozen anchor plus challenge set:

```powershell
python run.py --engine python --include-challenge --repeat 3 --sample-workers 3
```

The command prints the new run directory. `--sample-workers 3` runs independent cells concurrently; candidate calls inside C/D/E are also parallel. The invocation records the execution mode and resume history. To resume after interruption:

```powershell
python resume_run.py runs/real_<run-id> --sample-workers 3
```

The package records every attempt and summarizes retries in cumulative spend. Do not compare a partial run as though it were complete. `OPENAI_API_KEY` must be set in the current environment. Real API calls are billable.
