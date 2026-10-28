"""S/U/E action restriction on mini's native loop; no model-controlled shell.

This controller is our experimental policy, not Agentless/AutoCodeRover's runner.
Tool descriptions/signatures and CLI implementations come from pinned upstreams.
Selecting a tool in the next/previous stage performs that action and changes stage;
there is no separate LLM call or empty action for a stage transition.
"""

import ast
import json
from pathlib import Path
import shlex

import yaml

from minisweagent.exceptions import FormatError, Submitted
from minisweagent.run.benchmarks import swebench
from minisweagent.run.benchmarks.aci import BudgetAgent, DeadlineModel, patch_command

ROOT = Path(__file__).resolve().parents[4]


def tool_definitions():
    """Adapt upstream metadata, without importing a second agent framework."""
    search = ROOT / "tools/search"
    tree = ast.parse((search / "upstream/auto-code-rover/app/search/search_backend.py").read_text())
    methods = next(node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == "SearchBackend")
    names = {path.name for path in (search / "bin").iterdir()}
    definitions = {}
    for method in methods.body:
        if isinstance(method, ast.FunctionDef) and method.name in names:
            definitions[method.name] = {
                "stage": "S", "executable": f"/root/aci-tools/search/bin/{method.name}",
                "docstring": ast.get_docstring(method),
                "arguments": [{"name": arg.arg, "type": "string", "required": True}
                              for arg in method.args.args if arg.arg != "self"],
            }
    for stage, bundle, relative in (
        ("U", "understanding", "tools/understanding/codestruct/upstream/CodeStruct/SWE-agent/tools/ast_read/config.yaml"),
        ("E", "editing", "tools/editing/upstream/ast_edit.yaml"),
        ("E", "editing", "tools/editing/upstream/str_replace.yaml"),
    ):
        for name, definition in yaml.safe_load((ROOT / relative).read_text())["tools"].items():
            definitions[name] = definition | {"stage": stage, "executable": f"/root/aci-tools/{bundle}/bin/{name}"}
    for name, description, arguments in (
        ("view_diff", "Inspect the current patch. Optional paths selects files with native git pathspecs; omit for all changes.",
         [{"name": "paths", "type": "array", "required": False}]),
        ("submit", "Submit the current patch and finish. Optional paths selects the intended source files with native git pathspecs; omit for all changes.",
         [{"name": "paths", "type": "array", "required": False}]),
        ("run_tests", "Run the repository test runner: pytest, or Django runtests.py. Supply paths/labels and runner options in targets; an empty array runs its default selection. New or modified tests are allowed.",
         [{"name": "targets", "type": "array", "required": True}]),
    ):
        definitions[name] = {"stage": None, "docstring": description, "arguments": arguments}
    return definitions


DEFINITIONS = tool_definitions()


def schema(name):
    definition = DEFINITIONS[name]
    properties = {}
    for arg in definition["arguments"]:
        properties[arg["name"]] = {"type": arg["type"], "description": arg.get("description", arg["name"])}
        if arg["type"] == "array":
            properties[arg["name"]].update(items={"type": "string"})
    return {"type": "function", "function": {
        "name": name, "description": definition["docstring"],
        "parameters": {"type": "object", "properties": properties,
                       "required": [arg["name"] for arg in definition["arguments"] if arg.get("required")]},
    }}


def cli_command(name, values):
    """Quote data once, protect option-like text, and use only fixed executables."""
    definition = DEFINITIONS[name]
    positional, options = [], []
    for arg in definition["arguments"]:
        if arg["name"] not in values:
            continue
        # CodeStruct's command formatter maps null to empty text; argparse owns
        # CLI types and path semantics, including numeric strings and /tmp paths.
        value = "" if values[arg["name"]] is None else str(values[arg["name"]])
        if "argument_format" in arg:
            # Upstream formats here are '--flag {{value}}'. '=' preserves leading '-'.
            flag, placeholder = arg["argument_format"].split()
            assert flag.startswith("--") and placeholder == "{{value}}"
            options.append(f"{flag}={value}")
        else:
            positional.append(value)
    command = shlex.join([definition["executable"], *options, "--", *positional])
    return "exec " + command


def test_command(targets, *, django=False):
    targets = targets if isinstance(targets, list) else [targets]
    argv = (["python", "tests/runtests.py", "--settings=test_sqlite", "--parallel=1"] if django
            else ["python", "-m", "pytest", "-q"])
    return "exec " + shlex.join([*argv, *targets])


class StagedModel(DeadlineModel):
    stage = "S"
    started_search = False
    started_reading = False

    def available_names(self):
        # Initial S -> U -> E is the staged condition; common controls are always
        # available. Once entered, a stage is not revoked by further exploration.
        stages = {None, "S"}
        if self.started_search:
            stages.add("U")
        if self.started_reading:
            stages.add("E")
        return [name for name, item in DEFINITIONS.items() if item["stage"] in stages]

    def _query(self, messages, **kwargs):
        return super()._query(messages, tools=[schema(name) for name in self.available_names()],
                              parallel_tool_calls=False, **kwargs)

    def _parse_actions(self, response):
        try:
            calls = response.choices[0].message.tool_calls or []
            if len(calls) != 1:
                raise ValueError("Return exactly one named tool call per response.")
            call = calls[0]
            name = call.function.name
            if name not in self.available_names():
                raise ValueError(f"Tool {name!r} is unavailable in stage {self.stage}. Available: {self.available_names()}")
            values = json.loads(call.function.arguments)
            if not isinstance(values, dict):
                raise ValueError("Tool arguments must be a JSON object.")
            required = {arg["name"] for arg in DEFINITIONS[name]["arguments"] if arg.get("required")}
            if missing := required - values.keys():
                raise ValueError(f"Missing required arguments: {sorted(missing)}")
            # Match mini's required-field extraction, not a second type system.
            values = {arg["name"]: values[arg["name"]] for arg in DEFINITIONS[name]["arguments"]
                      if arg["name"] in values}
            action = {"tool": name, "arguments": values, "tool_call_id": call.id, "stage_before": self.stage}
            if "executable" in DEFINITIONS[name]:
                action["command"] = cli_command(name, values)
            return [action]
        except (ValueError, TypeError) as error:
            raise FormatError({"role": "user", "content": f"Tool input error: {error}. Use one available named tool; no shell is available.",
                               "extra": {"interrupt_type": "FormatError"}}) from error


class StagedAgent(BudgetAgent):
    def execute_actions(self, message):
        action, = message["extra"]["actions"]
        name, values = action["tool"], action["arguments"]
        try:
            if name == "run_tests":
                action["command"] = test_command(values["targets"], django=self.instance_id.startswith("django__"))
            elif name in {"view_diff", "submit"}:
                action["command"] = patch_command(values.get("paths"))
            output = self.env.execute(action)
        except (ValueError, TypeError) as error:
            output = {"returncode": 64, "output": str(error), "exception_info": ""}
        # These CLIs sometimes report semantic failures with returncode=0.
        # Stage means the operation attempted, not a claim of successful search/edit.
        if stage := DEFINITIONS[name]["stage"]:
            self.model.stage = stage
            self.model.started_search |= stage == "S"
            self.model.started_reading |= stage == "U"
        action["stage_after"] = self.model.stage
        output.setdefault("extra", {}).update(stage=self.model.stage, tool=name)
        observations = self.add_messages(*self.model.format_observation_messages(message, [output], self.get_template_vars()))
        if name == "submit" and output["returncode"] == 0:
            raise Submitted({"role": "exit", "content": "Submitted", "extra": {
                "exit_status": "Submitted", "submission": output["output"]}})
        return observations


def main():
    original = swebench.ProgressTrackingAgent
    swebench.ProgressTrackingAgent = StagedAgent
    try:
        from minisweagent.run.benchmarks.aci_staged import StagedModel as ConfiguredModel
        with ConfiguredModel.portal_provider:
            swebench.app()
    finally:
        swebench.ProgressTrackingAgent = original


if __name__ == "__main__":
    main()
