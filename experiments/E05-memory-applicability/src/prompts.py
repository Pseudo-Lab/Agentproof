""" Prompts and schema definitions for E05 — Memory Applicability Judgment."""

SYSTEM_PROMPT = """You are evaluating a language model agent playing an AlfWorld (TextWorld-ALFRED) household task.
The agent failed to complete the task. Your job is to diagnose the primary failure type in the specified step range [s, e] using the 7-label failure taxonomy."""

TAXONOMY_TEXT = """Failure Taxonomy (choose exactly one):
- strategy/goal_misinterpretation: The agent misunderstands what object, state change, or target receptacle the task goal requires.
- strategy/missing_processing_step: The agent acquires the target object and reaches or acts on receptacles without performing a required intermediate processing step (e.g., heating, cooling, cleaning, or using a desklamp).
- strategy/missing_destination: The agent fails to locate or visit the required destination receptacle despite having the object ready.
- strategy/exhaustive_rescan: The agent systematically scans many receptacles across the room without finding the needed object or making progress.
- strategy/loop: The agent repetitively cycles between the same few locations or repeats identical invalid/unproductive actions.
- operation/wrong_object_pick: The agent picks up an incorrect object type instead of the required target object.
- operation/move_command_avoidance: The agent fails at a specific step due to issuing an invalid or malformatted placement/movement command."""


def build_conservative_comparative_prompt(task_block: str, memory_block: str, s: int, e: int) -> str:
    """D5: Conservative Comparative Applicability Prompt (Baseline in pilot-span-tradeoff-n159)."""
    return f"""{task_block}

{TAXONOMY_TEXT}

{memory_block}

Compare your initial trajectory-only diagnosis (`initial_failure_type`) against the failure hypothesis suggested by the past memory across steps {s}–{e}:
1. Scope Match: Does the memory explain the primary failure inside the target interval [{s}, {e}], rather than a different phase of the episode?
2. Discriminative Support: Is there concrete evidence in steps {s}–{e} that specifically favors the memory's failure type OVER `initial_failure_type` (not merely generic facts consistent with both)?
3. Explanatory Relevance: Does the memory capture the root failure of steps {s}–{e} rather than a secondary symptom?

Respond with a JSON object only:
{{
  "initial_failure_type": "<taxonomy label from trajectory only>",
  "memory_failure_type": "<taxonomy label implied by memory>",
  "supporting_evidence": {{"status": "found" | "not_found", "steps": [int], "reason": "..."}},
  "contradicting_evidence": {{"status": "found" | "not_found", "steps": [int], "reason": "..."}},
  "comparative_judgment": {{"scope_match": "yes"|"no", "discriminative_support": "yes"|"no", "preferred_hypothesis": "initial"|"memory", "reason": "..."}},
  "decision": "apply_memory" | "keep_initial",
  "failure_type": "<final taxonomy label>"
}}"""


def build_span_structure_comparative_prompt(task_block: str, memory_block: str, s: int, e: int) -> str:
    """D6-G: Span-Structure Enhanced Comparative Prompt (Intervention in pilot-span-tradeoff-n159)."""
    return f"""{task_block}

{TAXONOMY_TEXT}

{memory_block}

Before choosing between your initial diagnosis (`initial_failure_type`) and the past memory's hypothesis (`memory_failure_type`) for steps {s}–{e}, analyze the interval structure:
1. Interval Onset (Step {s}): What specific action or state transition initiates this failure segment at Step {s}?
2. Interval Progression (Steps {s}–{e}): What behavior or missing requirement persists across the span?
3. Causal Role: Distinguish whether the observed actions are the underlying cause of failure, a downstream consequence, or an accompanying symptom.
4. Comparative Fit: Which hypothesis (`initial_failure_type` vs `memory_failure_type`) more accurately explains the full interval structure from Step {s} to Step {e}?

Respond with a JSON object only:
{{
  "initial_failure_type": "<taxonomy label from trajectory only>",
  "memory_failure_type": "<taxonomy label implied by memory>",
  "span_analysis": {{"onset_at_start": "...", "persistent_pattern": "...", "causal_role": "..."}},
  "supporting_evidence": {{"status": "found" | "not_found", "steps": [int], "reason": "..."}},
  "contradicting_evidence": {{"status": "found" | "not_found", "steps": [int], "reason": "..."}},
  "decision": "apply_memory" | "keep_initial",
  "failure_type": "<final taxonomy label>"
}}"""
