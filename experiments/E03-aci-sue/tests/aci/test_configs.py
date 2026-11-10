"""Native mini config composition, prompt/tool conditions and gold separation."""
import importlib.util
from pathlib import Path
import unittest
from unittest.mock import AsyncMock, patch

from jinja2 import StrictUndefined, Template
from minisweagent.agents.default import AgentConfig
from minisweagent.config import get_config_from_spec
from minisweagent.environments.docker import DockerEnvironmentConfig
from minisweagent.models import get_model
from minisweagent.utils.serialize import recursive_merge

ROOT = Path(__file__).resolve().parents[2]


def config(condition='baseline', model='gemma4-31b', *, tool_first=False):
    paths = [
        'swebench.yaml', ROOT / 'configs/aci-common.yaml',
        ROOT / f'configs/model-{model}.yaml', ROOT / f'configs/aci-{condition}.yaml',
        ROOT / 'configs/aci-wall600.yaml']
    if tool_first:
        paths.append(ROOT / 'configs/aci-tool-first.yaml')
    return recursive_merge(*(get_config_from_spec(str(path)) for path in paths))


class NativeConfigTests(unittest.TestCase):
    def test_defaults_and_model_profiles_load_in_original_classes(self):
        reference = get_config_from_spec('swebench.yaml')
        for path in (ROOT / 'configs').glob('model-*.yaml'):
            value = config(model=path.stem.removeprefix('model-'))
            AgentConfig(**value['agent'])
            DockerEnvironmentConfig(image='fixture:latest', **value['environment'])
            model = get_model(config=value['model'])
            self.assertEqual(value['agent']['instance_template'], reference['agent']['instance_template'])
            self.assertEqual(value['model']['observation_template'], reference['model']['observation_template'])
            self.assertEqual(value['environment']['env']['BASH_ENV'], reference['environment']['env']['BASH_ENV'])
            self.assertEqual(model.config.model_kwargs['seed'], 42)
            self.assertEqual(value['agent']['step_limit'], 0)
            self.assertEqual(value['agent']['cost_limit'], 0)
            self.assertEqual(value['agent']['wall_time_limit_seconds'], 600)

    def test_all_conditions_match_installed_commands_to_rendered_prompt(self):
        names = {'s': ('search', 'search_method'), 'e': ('editing', 'editCode')}
        reference = config()
        for condition in ('baseline', 'sue'):
            value = config(condition)
            active = '' if condition == 'baseline' else condition.split('-')[0]
            prompt = Template(value['agent']['system_template'], undefined=StrictUndefined).render(env=value['environment']['env'])
            mounts = ' '.join(value['environment']['run_args'])
            for key, (directory, command) in names.items():
                self.assertEqual(command in prompt, key in active)
                self.assertEqual(f'/tools/{directory},' in mounts, key in active)
            implementation = value['environment']['env']['ACI_U_IMPLEMENTATION']
            for name, command in (('codestruct', 'readCode'), ('agentless', 'agentless_skeleton')):
                enabled = 'u' in active and implementation == name
                self.assertEqual(command in prompt, enabled)
                self.assertEqual(f'/tools/understanding/{name},' in mounts, enabled)
            for command in ('str_replace PATH', 'create_file PATH'):
                self.assertEqual(command in prompt, 'e' in active)
            self.assertNotIn('str_replace_editor', prompt)
            self.assertNotIn('/data/', mounts)
            self.assertNotIn('swerex', mounts)
            value['environment']['env'] = reference['environment']['env']
            value['environment']['run_args'] = reference['environment']['run_args']
            self.assertEqual(value, reference)
        rendered = Template(reference['agent']['system_template']).render(env=reference['environment']['env'])
        self.assertEqual(rendered.strip(), get_config_from_spec('swebench.yaml')['agent']['system_template'].strip())

    def test_tool_priority_changes_instructions_only_and_leaves_baseline_unchanged(self):
        for condition in ('baseline', 'sue'):
            optional = config(condition)
            priority = config(condition, tool_first=True)
            render = lambda cfg: Template(cfg['agent']['system_template'], undefined=StrictUndefined).render(env=cfg['environment']['env'])
            if condition == 'baseline':
                self.assertEqual(render(optional), render(priority))
            else:
                self.assertNotEqual(render(optional), render(priority))
                self.assertIn('start with these search commands', render(priority))
                self.assertIn('before shell/Python rewrites', render(priority))
                self.assertNotIn('before shell/Python rewrites', render(optional))
            priority['environment']['env']['ACI_TOOL_POLICY'] = 'optional'
            self.assertEqual(priority, optional)

    def test_legacy_execution_packages_are_not_runtime_dependencies(self):
        self.assertIsNone(importlib.util.find_spec('sweagent'))
        self.assertIsNone(importlib.util.find_spec('swerex'))


    def test_staged_request_uses_named_tools_and_recovers_patch_paths(self):
        from e03_aci.aci_staged import StagedModel, patch_command
        model = StagedModel(model_name="openai/fixture", cost_tracking="ignore_errors",
                            model_kwargs={"parallel_tool_calls": False})
        response = object()
        with patch("e03_aci.aci_staged.litellm.acompletion", new_callable=AsyncMock,
                   return_value=response) as request:
            self.assertIs(model._query([]), response)
        names = {tool["function"]["name"] for tool in request.call_args.kwargs["tools"]}
        self.assertIn("search_method", names)
        self.assertIn("submit", names)
        self.assertNotIn("bash", names)
        self.assertNotIn("editCode", names)
        self.assertFalse(request.call_args.kwargs["parallel_tool_calls"])
        self.assertEqual(patch_command(["a b.py"]),
                         "git add -N . && git diff --binary HEAD -- 'a b.py' ':!patch.txt'")
