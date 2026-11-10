"""Offline native-test execution index and opt-in automatic V selection.

Run ``prepare OUTPUT_DIR [--timeout SECONDS] [-- NATIVE_ARGV...]`` on a clean
base before agent work. No issue, reference patch or evaluator labels are read.
The existing tracer records test contexts; source_effects owns scope identity.
Block fingerprints follow testmon's published idea of masking nested bodies,
without porting its pytest plugin or replacing any repository test runner.
"""
import argparse
import ast
import copy
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time

import related_tests as native
import source_effects

SCHEMA = 12
ENV_KEYS = ('PYTHONPATH', 'PYTHONHASHSEED', 'PYTEST_ADDOPTS', 'DJANGO_SETTINGS_MODULE',
            'OMP_NUM_THREADS', 'OPENBLAS_NUM_THREADS', 'MKL_NUM_THREADS', 'LANG',
            'LC_CTYPE', 'LC_ALL', 'TZ')
ENVIRONMENT = r'''
import sys, os, json, hashlib, glob
packages={}
for directory in sys.path:
    if not directory or not os.path.isdir(directory): continue
    for pattern in ('*.dist-info/METADATA','*.egg-info/PKG-INFO'):
        for path in glob.glob(os.path.join(directory,pattern)):
            with open(path,'rb') as f: packages[path]=hashlib.sha256(f.read()).hexdigest()
print(json.dumps({'python':sys.version,'executable':sys.executable,'packages':packages}))
'''


def digest(data):
    return hashlib.sha256(data).hexdigest()


def tools_identity():
    return {name: digest(Path(__file__).with_name(name).read_bytes()) for name in
            ('impact_tests.py', 'trace_test_execution.py', 'source_effects.py', 'aci_test_units.py',
             'related_tests.py', 'baseline_python.py')}


def environment(kind=None):
    result = subprocess.run(['python', '-c', ENVIRONMENT], capture_output=True, text=True,
                            check=True, timeout=20)
    keys = ENV_KEYS + (('SYMPY_USE_CACHE',) if (kind or runner()) == 'sympy' else ())
    return dict(runtime=json.loads(result.stdout), env={k: os.environ.get(k) for k in keys})


def runner(argv=None):
    """Bind the adapter to the explicit native command, not edited file names."""
    argv = argv or native.command([])
    if argv[:3] == ['python', '-m', 'pytest']:
        return 'pytest'
    if argv[:2] == ['python', 'tests/runtests.py']:
        return 'django'
    if argv[:2] == ['python', 'bin/test']:
        return 'sympy'
    raise ValueError('unsupported native runner command')


def blocks(source, path):
    """Qualified AST blocks, with child bodies excluded from the parent hash.

    Headers/decorators stay in the parent: changing a signature, adding a new
    function or changing class/module execution can affect import/setup users.
    Body line ranges assign measured lines to the innermost executable scope.
    """
    tree, error = source_effects.parse(source, path)
    if error:
        raise ValueError(error['message'])
    result = {}
    for key, node in source_effects.scope_nodes(tree).items():
        masked = copy.deepcopy(node)

        class Mask(ast.NodeTransformer):
            def visit(self, child):
                if child is not masked and isinstance(child, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
                    child.body = [ast.Pass()]
                    return child
                return super().visit(child)

        masked = Mask().visit(masked)
        start = node.body[0].lineno if not isinstance(node, ast.Module) and node.body else 1
        end = getattr(node, 'end_lineno', len(source.splitlines()))
        result[key] = dict(sha256=digest(ast.dump(masked, include_attributes=False).encode()),
                           start=start, end=end)
    return result


def dependencies(profile, definitions, context_ids):
    """Keep every witnessing test; equal coverage never deduplicates assertions."""
    result = {}
    for context, files in profile['contexts'].items():
        for path, lines in files.items():
            scopes = definitions.get(path, {})
            reached = set()
            for line in lines:
                matches = [key for key, block in scopes.items() if block['start'] <= line <= block['end']]
                # Module/class execution and function headers can affect a
                # reached body; nested bodies are already masked in their hashes.
                reached.update(matches)
            for key in reached:
                result.setdefault(path, {}).setdefault(key, []).append(context_ids[context])
    return result


def contexts_for(data, path, block, field='dependencies'):
    """Resolve one block's lossless context references, retaining every witness."""
    references = data[field].get(path, {}).get(block, [])
    names = data['context_names']
    if any(type(i) is not int or not 0 <= i < len(names) for i in references):
        raise ValueError('invalid index context reference')
    return [names[i] for i in references]


def index_path():
    return Path(os.environ.get('ACI_TESTS_INDEX', native.git('rev-parse', '--git-path',
                                                         'aci-test-index/index.json').strip()))


def clear_bytecode(files):
    # Timestamp/size .pyc validation can accept a same-second, same-size edit.
    for name in files:
        path = Path(name)
        if path.suffix == '.py':
            for cache in [path.with_suffix('.pyc'), *path.parent.glob('__pycache__/' + path.stem + '.*.pyc')]:
                cache.unlink(missing_ok=True)


def compile_index(record, profile, sources):
    """Pure measurement-to-index compilation, without executing any tests.

    Producer provenance remains immutable. A new consumer fingerprint does not
    claim the measurements were made by the current tracer, or repair a failed
    independent native-parity audit.
    """
    start = time.monotonic()
    hashes = {p: digest(raw) for p, raw in sources.items()}
    if record['execution']['outcome'] not in ('passed', 'failed'):
        raise ValueError('measurement did not complete; recollect after resolving the cause')
    if any(profile.get(k) != hashes for k in ('source_hashes_before', 'source_hashes_after')):
        raise ValueError('measurement/source identity differs')
    if 'raw_contexts' not in profile or 'fixture_owners' not in profile:
        raise ValueError('measurement lacks raw execution/fixture provenance')
    collected = profile.get('collected', {})
    if not collected or set(collected) - set(profile['completed']):
        raise ValueError('some collected tests lack completed execution contexts')
    units = profile.get('test_units', {})
    if record['runner'] == 'django':
        if set(collected) != set(units.get('case_units', {})):
            raise ValueError('collected unittest cases lack native execution units; recollect')
    if record['runner'] == 'pytest':
        if set(collected) != set(units.get('case_units', {})):
            raise ValueError('collected pytest cases lack native execution units')
        if any(u['outcome'] == 'incomplete' for u in units['units'].values()):
            raise ValueError('some native execution units did not complete')
    missing = set(record['execution']['status']) - set(collected)
    if missing:
        raise ValueError('native outcomes lack trace attribution: ' + ', '.join(sorted(missing)[:3]))
    definitions, unavailable = {}, {}
    measured = {path for files in profile['contexts'].values() for path in files}
    for path, raw in sources.items():
        if path not in measured:
            continue
        try:
            definitions[path] = blocks(raw, path)
        except ValueError as error:
            unavailable[path] = str(error)
    names = list(dict.fromkeys([*profile['contexts'], *profile['raw_contexts']]))
    context_ids = {name: i for i, name in enumerate(names)}
    data = dict(schema=SCHEMA, **record, source_sha256=hashes, blocks=definitions,
                context_names=names, unavailable_sources=unavailable,
                dependencies=dependencies(profile, definitions, context_ids),
                observed_dependencies=dependencies({'contexts': profile['raw_contexts']}, definitions, context_ids),
                fixture_owners=profile['fixture_owners'], file_aliases=profile.get('file_aliases', []),
                tests=collected, opaque_contexts=profile['opaque_contexts'], test_units=units,
                collection_paths=profile.get('collection_paths', []),
                durations=profile['durations'], trace_scope=profile['trace_scope'],
                measurement_tools=record['tools'])
    data['tools'] = tools_identity()
    data['indexing_seconds'] = time.monotonic() - start
    return data


def publish(output, data):
    data['measurement_artifacts'] = {name: digest((output / name).read_bytes()) for name in
                                    ('preparation.json', 'profile.json', 'trace-config.json', 'prepare.log')}
    (output / 'index.tmp').write_text(json.dumps(data))
    (output / 'index.tmp').replace(output / 'index.json')
    print(json.dumps(dict(index=str(output / 'index.json'), tests=len(data['tests']),
                         full_native_suite=data['full_native_suite'],
                         preparation_seconds=data['preparation_seconds'],
                         indexing_seconds=data['indexing_seconds'])))


def recompile(measurement, output):
    """Explicitly compile preserved observations against the same clean base."""
    measurement, output = Path(measurement).resolve(), Path(output).resolve()
    if output.exists():
        raise ValueError('recompilation requires a new output directory')
    record = json.loads((measurement / 'preparation.json').read_text())
    profile = json.loads((measurement / 'profile.json').read_text())
    if native.git('diff', '--name-only', 'HEAD').strip() or native.git('ls-files', '--others', '--exclude-standard', '*.py').strip():
        raise ValueError('recompilation requires a clean base')
    if (record['base_commit'] != native.git('rev-parse', 'HEAD').strip() or
            record['base_tree'] != native.git('rev-parse', 'HEAD^{tree}').strip() or
            record['environment'] != environment(record['runner']) or
            record['runner'] != runner(record['native_command'])):
        raise ValueError('measurement base/environment differs')
    config = json.loads((measurement / 'trace-config.json').read_text())
    sources = {p: Path(p).read_bytes() for p in config['files']}
    data = compile_index(record, profile, sources)
    if data['source_sha256'] != config['source_hashes']:
        raise ValueError('measurement configuration/source differs')
    output.mkdir(parents=True)
    for name in ('preparation.json', 'profile.json', 'trace-config.json', 'prepare.log'):
        (output / name).write_bytes((measurement / name).read_bytes())
    data['recompiled_from'] = str(measurement)
    publish(output, data)


def prepare(output, timeout, argv):
    """Only preparation executes the full native command; publish after checks."""
    output = Path(output).resolve()
    output.mkdir(parents=True, exist_ok=True)
    if (output / 'index.json').exists():
        raise ValueError('index already exists; use a new preparation directory')
    if native.git('diff', '--name-only', 'HEAD').strip():
        raise ValueError('prepare requires a clean tracked base')
    if native.git('ls-files', '--others', '--exclude-standard', '*.py').strip():
        raise ValueError('prepare requires no untracked Python sources/tests')
    start = time.monotonic()
    base = native.git('rev-parse', 'HEAD').strip()
    tree = native.git('rev-parse', 'HEAD^{tree}').strip()
    if not base or not tree:
        raise ValueError('prepare requires a Git base')
    full = not argv
    argv = argv or native.command([])
    kind = runner(argv)
    identity = environment(kind)
    execution_environment = {'PYTHONUNBUFFERED': '1'}
    if kind == 'sympy' and not os.environ.get('PYTHONHASHSEED'):
        # Native SymPy otherwise reexecutes without this process's tracer.
        # "random" retains a fresh hash seed per Python invocation, not PairedV.
        execution_environment['PYTHONHASHSEED'] = 'random'
    if not argv or argv[0] != 'python':
        raise ValueError('native argv must start with the benchmark python')
    files = [p for p in native.git('ls-files', '-z', '*.py').split('\0') if p and Path(p).is_file()]
    sources = {p: Path(p).read_bytes() for p in files}
    clear_bytecode(files)
    hashes = {p: digest(raw) for p, raw in sources.items()}
    config = dict(root=str(Path.cwd()), files=files, source_hashes=hashes, index=True, runner=kind)
    config_path, profile_path = output / 'trace-config.json', output / 'profile.json'
    config_path.write_text(json.dumps(config))
    traced = [argv[0], str(Path(__file__).with_name('trace_test_execution.py')),
              str(config_path), str(profile_path), *argv[1:]]
    # GNU timeout owns a separate foreground process group, including test children.
    execution = native.run_tests(['timeout', '--signal=TERM', '--kill-after=5', str(timeout), *traced],
                                 '.', dict(os.environ, **execution_environment), timeout + 10)
    (output / 'prepare.log').write_text(execution.pop('log'))
    record = dict(base_commit=base, base_tree=tree, runner=kind, native_command=argv,
                  traced_command=traced, full_native_suite=full, environment=identity,
                  tools=tools_identity(), execution=execution,
                  execution_environment=execution_environment,
                  preparation_seconds=time.monotonic() - start)
    (output / 'preparation.json').write_text(json.dumps(record, indent=2))
    if execution['outcome'] not in ('passed', 'failed') or not profile_path.exists():
        raise ValueError('native preparation incomplete; see preparation.json and prepare.log')
    profile = json.loads(profile_path.read_text())
    if native.git('diff', '--name-only', 'HEAD').strip() or environment(kind) != identity:
        raise ValueError('base/environment changed during preparation')
    data = compile_index(record, profile, sources)
    data['preparation_seconds'] = time.monotonic() - start
    record['preparation_seconds'] = data['preparation_seconds']
    (output / 'preparation.json').write_text(json.dumps(record, indent=2))
    publish(output, data)


def load(path):
    data = json.loads(Path(path).read_text())
    if data['schema'] != SCHEMA or data['base_commit'] != native.git('rev-parse', 'HEAD').strip():
        raise ValueError('index/base version mismatch')
    if data['base_tree'] != native.git('rev-parse', 'HEAD^{tree}').strip():
        raise ValueError('index/base tree mismatch')
    if data['tools'] != tools_identity():
        raise ValueError('index implementation mismatch; prepare again')
    if (data['runner'] != runner(data['native_command']) or
            data['environment'] != environment(data['runner'])):
        raise ValueError('index native runner/environment mismatch')
    return data


def changed_paths():
    tracked = native.git('diff', '--name-only', '-z', 'HEAD').split('\0')
    new = native.git('ls-files', '--others', '--exclude-standard', '-z').split('\0')
    return list(dict.fromkeys(p for p in tracked + new if p))


def selection(sources):
    start = time.monotonic()
    path = index_path()
    result = dict(method='base_execution_index', index=str(path), files=[], tests=[],
                  full_suite_fallback=False, dependency_completeness='unknown',
                  observed_scope_complete=False, selection_complete=False)
    try:
        data = load(path)
        changed = list(dict.fromkeys(changed_paths() + list(sources)))
        clear_bytecode(changed)
        direct, reasons, affected = set(), [], {}
        for source in changed:
            if source not in data['blocks']:
                reasons.append(source + ': source not indexed')
                continue
            before = data['blocks'][source]
            raw = Path(source).read_bytes() if Path(source).is_file() else b''
            if digest(raw) == data['source_sha256'][source]:
                continue
            try:
                after = blocks(raw, source)
                modified = {k for k in before if k not in after or before[k]['sha256'] != after[k]['sha256']}
                # Exact-text-only edits may affect source inspection. Do not call them safe.
                if not modified:
                    modified = set(before)
            except ValueError:
                modified = set(before)
            affected[source] = sorted(modified)
            for key in modified:
                contexts = set(contexts_for(data, source, key))
                if '__shared_setup__' in contexts:
                    reasons.append(source + ': changed block was also executed outside a test context')
                direct.update(contexts - {'__shared_setup__'})
        if affected or reasons:
            opaque = set(data['opaque_contexts'])
            if opaque:
                reasons.append('preparation has untraced child/thread or replaced-tracer contexts; additional dependencies unknown')
        if (affected or reasons) and not direct:
            reasons.append('no attributed dependent test; impact unknown')
        tests = [t for t in data['tests'] if t in direct]
        result.update(tests=tests, files=list(dict.fromkeys(data['tests'][t] for t in tests)),
                      affected_blocks=affected, unchecked_reasons=list(dict.fromkeys(reasons)),
                      # Full observation cannot prove behavioral dependency
                      # completeness (e.g. values cached across test contexts).
                      observed_scope_complete=not reasons and data['full_native_suite'],
                      indexed_full_native_suite=data['full_native_suite'],
                      index_sha256=digest(path.read_bytes()), indexed_tests=len(data['tests']))
        result['execution_environment'] = data['execution_environment']
        if tests:
            if data['runner'] == 'sympy':
                # bin/test has substring-based -k, not exact heterogeneous node IDs.
                result['command'] = native.command(result['files'], runner=data['runner'])
                result['execution_unit'] = 'native_file'
            else:
                descriptors = data['test_units']['case_units']
                units = list(dict.fromkeys(descriptors[t]['selector'] for t in tests))
                if data['runner'] == 'django':
                    result['command'] = native.command([], runner=data['runner']) + units
                    result['execution_unit'] = 'native_unittest_class'
                else:
                    result['command'] = [arg for arg in data['native_command']
                                         if arg not in data['collection_paths']] + units
                    result['execution_unit'] = 'native_pytest_unit'
                result['units'] = units
                result['unit_members'] = {u: [t for t, d in descriptors.items() if d['selector'] == u]
                                          for u in units}
            if os.environ.get('ACI_TESTS_PREPARED_BASELINE') == '1':
                if result['execution_unit'] == 'native_pytest_unit':
                    reference = {u: data['test_units']['units'][u]['outcome'] for u in result['units']}
                else:
                    members = (dict.fromkeys(t for ts in result['unit_members'].values() for t in ts)
                               if 'unit_members' in result else
                               {t: None for t, file in data['tests'].items() if file in result['files']})
                    reference = {t: data['execution']['status'].get(t, 'unobserved') for t in members}
                result['preparation_reference'] = dict(status=reference, command=data['native_command'],
                                                       index_sha256=result['index_sha256'])
        else:
            result['detail'] = '; '.join(result['unchecked_reasons']) or 'no indexed dependency selected; no test run or correctness claim'
    except (OSError, ValueError, KeyError, TypeError, subprocess.SubprocessError) as error:
        result.update(unchecked_reasons=[str(error)], selection_complete=False,
                      detail=str(error), index_unavailable=True)
    result['lookup_seconds'] = time.monotonic() - start
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='action', required=True)
    prep = sub.add_parser('prepare')
    prep.add_argument('output', type=Path)
    prep.add_argument('--timeout', type=int, default=3600)
    check = sub.add_parser('check')
    check.add_argument('index', type=Path)
    compile_command = sub.add_parser('compile')
    compile_command.add_argument('measurement', type=Path)
    compile_command.add_argument('output', type=Path)
    sub.add_parser('select')
    # Native arguments follow -- and are never interpreted as shell text.
    raw = sys.argv[1:]
    split = raw.index('--') if '--' in raw else len(raw)
    args = parser.parse_args(raw[:split])
    argv = raw[split + 1:]
    if args.action == 'prepare':
        prepare(args.output, args.timeout, argv)
    elif args.action == 'compile':
        recompile(args.measurement, args.output)
    elif args.action == 'check':
        data = load(args.index)
        print(json.dumps(dict(tests=len(data['tests']), full_native_suite=data['full_native_suite'])))
    else:
        print(json.dumps(selection([]), indent=2))


if __name__ == '__main__':
    main()
