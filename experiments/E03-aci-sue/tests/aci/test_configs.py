"""Native mini config composition, prompt/tool conditions and gold separation."""
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from datasets import load_dataset
from jinja2 import StrictUndefined, Template
from minisweagent.agents.default import AgentConfig
from minisweagent.config import get_config_from_spec
from minisweagent.environments.docker import DockerEnvironmentConfig
from minisweagent.models import get_model
from minisweagent.utils.serialize import recursive_merge
from minisweagent.run.benchmarks.export_dataset import export_dataset

ROOT = Path(__file__).resolve().parents[2]


def config(condition='baseline', model='gemma4-31b', *, tool_first=False):
    paths = [
        'swebench.yaml', ROOT / 'src/minisweagent/config/extra/aci-common.yaml',
        ROOT / f'src/minisweagent/config/extra/model-{model}.yaml', ROOT / f'src/minisweagent/config/extra/aci-{condition}.yaml',
        ROOT / 'src/minisweagent/config/extra/aci-wall600.yaml']
    if tool_first:
        paths.append('aci-tool-first.yaml')
    return recursive_merge(*(get_config_from_spec(str(path)) for path in paths))


class NativeConfigTests(unittest.TestCase):
    def test_defaults_and_model_profiles_load_in_original_classes(self):
        reference = get_config_from_spec('swebench.yaml')
        for path in (ROOT / 'src/minisweagent/config/extra').glob('model-*.yaml'):
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
        for condition in ('baseline', 's', 'u', 'e', 'su', 'se', 'ue', 'sue',
                          'u-agentless', 'su-agentless', 'ue-agentless', 'sue-agentless'):
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
        for condition in ('baseline', 'sue', 'sue-agentless'):
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


class DatasetExportTests(unittest.TestCase):
    def test_native_dataset_loader_reads_export_without_gold(self):
        with tempfile.TemporaryDirectory() as temporary:
            folder = Path(temporary)
            row = {'instance_id': 'repo__issue-1', 'repo': 'owner/repo', 'base_commit': 'abc',
                   'problem_statement': 'Fix addition', 'patch': 'GOLD', 'test_patch': 'TEST',
                   'hints_text': 'HINT', 'FAIL_TO_PASS': '["secret-test"]'}
            cfg = {'dataset': 'fixture', 'revision': 'pinned', 'split': 'test',
                   'instances': [{'instance_id': row['instance_id'], 'base_commit': 'abc'}]}
            (folder / 'dataset.json').write_text(json.dumps(cfg))
            with patch('datasets.load_dataset', return_value=[row]) as loader:
                export_dataset(folder / 'dataset.json', folder / 'agent', folder / 'eval.json')
            loader.assert_called_once_with('fixture', revision='pinned', split='test')
            exported = list(load_dataset(str(folder / 'agent'), split='test'))
            self.assertEqual(exported, [{key: row[key] for key in ('instance_id', 'repo', 'problem_statement', 'base_commit')}])
            self.assertEqual(json.loads((folder / 'eval.json').read_text()), [row])
