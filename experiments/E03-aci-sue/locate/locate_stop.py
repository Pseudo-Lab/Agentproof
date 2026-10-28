"""Localization-only evaluation: end a mini run once the model is shown a gold line.

LocateStopAgent is the experiment's BudgetAgent unchanged, plus one check after
each batch of observations: if, by the rule in src/localization_metrics.py, any
gold line of the instance was shown, the run ends with exit_status "Located" and
an empty submission. Editing and testing budget is therefore not spent.

Set ACI_LOCATE_TASKS to an evaluator JSON with instance_id/base_commit/patch, put
this directory on PYTHONPATH and add aci-locate-stop.yaml after the other configs.
Only gold files are loaded, which is all the stop decision needs; the full
metrics are recomputed afterwards from the saved trajectory.
"""
import importlib.util
import json
import os
from functools import cache
from pathlib import Path

from minisweagent.exceptions import InterruptAgentFlow
from minisweagent.run.benchmarks.aci import BudgetAgent

_spec = importlib.util.spec_from_file_location(
    "localization_metrics", Path(__file__).resolve().parents[1] / "src" / "localization_metrics.py")
metrics = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(metrics)


class Located(InterruptAgentFlow):
    """The model has been shown at least one gold line."""


@cache
def tasks(path):
    return {task["instance_id"]: task for task in json.loads(Path(path).read_text())}


class LocateStopAgent(BudgetAgent):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        task = tasks(os.environ["ACI_LOCATE_TASKS"])[self.instance_id]
        blocks = metrics.gold_blocks(task["patch"])
        self.locate_source = metrics.BaseSource(task)
        self.locate_source.fetch(set(blocks))
        self.locate_source.fetched &= set(blocks)
        self.locate_blocks = {p: b for p, b in blocks.items() if p in self.locate_source.fetched}
        self.locate_gold = {(p, n) for p, sets in self.locate_blocks.items() for b in sets for n in b}

    def execute_actions(self, message):
        commands = {}
        for call in message.get("tool_calls") or []:
            try:
                commands[call["id"]] = json.loads(call["function"]["arguments"]).get("command", "")
            except (KeyError, TypeError, ValueError):
                commands[call["id"]] = ""
        observations = super().execute_actions(message)
        for observation in observations:
            if observation.get("role") != "tool":
                continue
            command = commands.get(observation.get("tool_call_id"), "")
            seen = metrics.visible_lines(command, observation.get("content"), self.locate_source, self.locate_blocks)
            if seen & self.locate_gold:
                raise Located({"role": "exit", "content": "Located",
                               "extra": {"exit_status": "Located", "submission": ""}})
        return observations
