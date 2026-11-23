"""Public configurations load the expected tool family and preserve SLACT's interface."""
from pathlib import Path

import pytest
from jinja2 import StrictUndefined, Template
from minisweagent.agents.default import AgentConfig
from minisweagent.config import get_config_from_spec
from minisweagent.environments.docker import DockerEnvironmentConfig
from minisweagent.models import get_model
from minisweagent.utils.serialize import recursive_merge

ROOT = Path(__file__).resolve().parents[2]


def config(condition='baseline', model='gemma4-31b'):
    return recursive_merge(*(get_config_from_spec(str(p)) for p in [
        'swebench.yaml', ROOT/'configs/aci-common.yaml', ROOT/f'configs/model-{model}.yaml',
        ROOT/f'configs/aci-{condition}.yaml', ROOT/'configs/aci-wall600.yaml']))


def prompt(value):
    return Template(value['agent']['system_template'], undefined=StrictUndefined).render(
        env=value['environment']['env']).strip()


@pytest.mark.parametrize('condition', ['baseline', 'slcat', 'codestruct', 'swe-agent'])
def test_conditions_load_and_mount_existing_sources(condition):
    value = config(condition)
    AgentConfig(**value['agent'])
    DockerEnvironmentConfig(image='fixture:latest', **value['environment'])
    get_model(config=value['model'])
    for argument in value['environment']['run_args']:
        if argument.startswith('type=bind,'):
            source = next(part[4:] for part in argument.split(',') if part.startswith('src='))
            assert (ROOT/source).exists(), source
            assert not source.startswith('./data/')
    assert value['agent']['wall_time_limit_seconds'] == 600


def test_slcat_preserves_baseline_prompt_and_model_configuration():
    base, ours = config(), config('slcat')
    assert prompt(base) == prompt(ours)
    assert base['agent'] == ours['agent']
    assert base['model'] == ours['model']
    assert ours['environment']['env']['ACI_EDIT_TESTS'] == '1'
    for flag in ('ACI_TOOL_S', 'ACI_TOOL_U', 'ACI_TOOL_E'):
        assert ours['environment']['env'][flag] == '0'


def test_comparator_instructions_describe_the_installed_commands():
    codestruct = prompt(config('codestruct'))
    assert 'readCode' in codestruct and 'editCode' in codestruct
    swe = prompt(config('swe-agent'))
    assert 'scroll_down' in swe and 'edit' in swe and 'open' in swe
    assert 'readCode' not in swe


@pytest.mark.parametrize('model', ['gemma4-31b', 'qwen35-27b'])
def test_model_profiles_keep_seed_and_native_loop(model):
    value = config(model=model)
    assert value['model']['model_kwargs']['seed'] == 42
    assert value['agent']['step_limit'] == 0
    assert value['agent']['cost_limit'] == 0
