"""PUSH adapter for unmodified pytest-testmon, using the native pytest interpreter.

The upstream plugin owns tracing, change detection and selection. This adapter
freezes a public-base DB, queries a disposable copy and passes exact node IDs to
the existing current/base verifier. Unsupported/invalid queries never run all.
"""
import argparse
import json
import os
from pathlib import Path
import sqlite3
import shutil
import subprocess
import tempfile
import time

import impact_tests as identity
import related_tests as native

PLUGIN = ['-p', 'no:pytest-testmon', '-p', 'no:testmon', '-p', 'testmon.pytest_testmon']


def index_path():
    return Path(os.environ.get('ACI_TESTMON_INDEX', native.git(
        'rev-parse', '--git-path', 'aci-testmon/index.json').strip()))


def environment():
    result = identity.environment()
    directory = os.environ.get('ACI_TESTMON_PACKAGES')
    if directory:
        root = Path(directory)
        result['measurement_packages'] = {str(p.relative_to(root)): identity.digest(p.read_bytes())
            for p in sorted(root.rglob('*')) if p.is_file() and
            (p.suffix in ('.py', '.so') or p.name in ('METADATA', 'entry_points.disabled'))}
    return result


def install(target):
    """Add only measurement packages, never upgrade the repository's pytest."""
    kind = identity.runner()
    probe = subprocess.check_output(['python', '-c',
        'import sys,json; ' + ('import pytest; ' if kind == 'pytest' else '') +
        'print(json.dumps([list(sys.version_info[:2]),' +
        ('pytest.__version__' if kind == 'pytest' else '"0"') + ']))'], text=True)
    python, pytest = json.loads(probe)
    old = python < [3, 8] or int(pytest.split('.')[0]) < 7
    pins = ['pytest-testmon==1.3.3', 'coverage==6.2'] if old else [
        'pytest-testmon==2.1.3', 'coverage==7.6.1']
    if kind != 'pytest':
        # The core does not import pytest. Supply packaging only if absent.
        if subprocess.run(['python', '-c', 'import packaging'], capture_output=True).returncode:
            pins += ['packaging==21.3', 'pyparsing==2.4.7']
    subprocess.run(['python', '-m', 'pip', 'install', '--disable-pip-version-check',
                    '--no-deps', '--target', str(target), *pins], check=True)
    # Explicitly loaded measurement plugin only. Its pytest11 advertisement
    # otherwise leaks into nested pytester tests that clear pytest options.
    for entry in Path(target).glob('pytest_testmon-*.dist-info/entry_points.txt'):
        entry.rename(entry.with_name('entry_points.disabled'))


def capture(argv, output, database, flags, timeout, kind='pytest', execution_environment=None, backend='plugin'):
    env = dict(os.environ, **(execution_environment or {}))
    env.update(TESTMON_DATAFILE=str(database), PYTHONUNBUFFERED='1')
    if os.environ.get('ACI_TESTMON_PACKAGES'):
        env['PYTHONPATH'] = os.pathsep.join(filter(None, [os.environ['ACI_TESTMON_PACKAGES'],
                                                         env.get('PYTHONPATH')]))
    if kind == 'pytest' and backend == 'plugin':
        command = [argv[0], str(Path(__file__).with_name('testmon_capture.py')),
                   str(output), *argv[3:], *PLUGIN, *flags]
    else:
        command = [argv[0], str(Path(__file__).with_name('testmon_native.py')),
                   'select' if '--collect-only' in flags else 'prepare', str(output), kind, *argv[1:]]
    execution = native.run_tests(command, '.', env, timeout)
    output.with_suffix('.log').write_text(execution.pop('log'))
    record = json.loads(output.read_text()) if output.exists() else {}
    return execution, record


def prepare(output, timeout, argv):
    kind = identity.runner()
    backend = 'core'
    if kind == 'pytest':
        compatible = subprocess.run(['python', '-c', 'from _pytest.config import ExitCode'], capture_output=True)
        if compatible.returncode == 0:
            backend = 'plugin'
    if native.git('diff', '--name-only', 'HEAD').strip():
        raise ValueError('prepare requires a clean tracked base')
    if native.git('ls-files', '--others', '--exclude-standard', '*.py').strip():
        raise ValueError('prepare requires no untracked Python sources/tests')
    output = Path(output).resolve()
    output.mkdir(parents=True, exist_ok=True)
    if any(output.iterdir()):
        raise ValueError('use a new preparation directory')
    argv = argv or native.command([])
    prefix = native.command([])
    if argv[:len(prefix)] != prefix:
        raise ValueError('preserve the native runner prefix: ' + repr(prefix))
    start = time.monotonic()
    original_environment = environment()
    revision = native.revision()
    identity.clear_bytecode(native.git('ls-files', '*.py').splitlines())
    execution_environment = {'PYTHONUNBUFFERED': '1'}
    if kind == 'sympy' and not os.environ.get('PYTHONHASHSEED'):
        execution_environment['PYTHONHASHSEED'] = 'random'
    execution, observed = capture(argv, output / 'prepare.json', output / '.testmondata',
        ['--testmon', '--testmon-noselect'], timeout, kind, execution_environment, backend)
    record = dict(schema=1, method='pytest_testmon', base_commit=native.git('rev-parse', 'HEAD').strip(),
        base_tree=native.git('rev-parse', 'HEAD^{tree}').strip(), environment=original_environment,
        native_command=argv, runner=kind, backend=backend, execution_environment=execution_environment,
        files=observed.get('files', {}), native_ids=observed.get('native_ids', {}),
        full_native_suite=argv == native.command([]),
        tests=observed.get('tests', []), collection_paths=observed.get('collection_paths', []), execution=execution,
        preparation_seconds=time.monotonic() - start)
    (output / 'preparation.json').write_text(json.dumps(record, indent=2))
    if (execution['outcome'] not in ('passed', 'failed') or observed.get('collection_errors')
            or not observed.get('collect') or not record['tests']
            or set(record['tests']) != set(observed.get('completed', []))
            or not (output / '.testmondata').is_file()):
        raise ValueError('testmon preparation incomplete; see prepare.log')
    if kind != 'pytest' and set(execution['status']) - set(record['native_ids'].values()):
        raise ValueError('native outcomes lack testmon attribution; see prepare.log')
    if native.revision() != revision or environment() != original_environment:
        raise ValueError('base/environment changed during preparation')
    # Checkpoint before publishing a standalone immutable database.
    with sqlite3.connect(output / '.testmondata') as db:
        db.execute('PRAGMA wal_checkpoint(TRUNCATE)')
    record['database_sha256'] = identity.digest((output / '.testmondata').read_bytes())
    (output / 'index.json').write_text(json.dumps(record, indent=2))
    print(json.dumps(dict(tests=len(record['tests']), index=str(output / 'index.json'),
                          preparation_seconds=record['preparation_seconds'])))


def load(path):
    data = json.loads(path.read_text())
    if data['schema'] != 1 or data['method'] != 'pytest_testmon':
        raise ValueError('not a testmon preparation')
    if identity.runner() != data['runner']:
        raise ValueError('testmon database/native runner mismatch')
    if (data['base_commit'] != native.git('rev-parse', 'HEAD').strip()
            or data['base_tree'] != native.git('rev-parse', 'HEAD^{tree}').strip()):
        raise ValueError('testmon database/base mismatch')
    if data['environment'] != environment():
        raise ValueError('testmon database/environment mismatch')
    database = path.parent / '.testmondata'
    if data['database_sha256'] != identity.digest(database.read_bytes()):
        raise ValueError('testmon database changed after preparation')
    return data


def selection(sources):
    start = time.monotonic()
    result = dict(method='pytest_testmon', files=[], tests=[], full_suite_fallback=False)
    try:
        path = index_path()
        data = load(path)
        if data['backend'] == 'core':
            # Native core selection covers recorded tests, not new discovery.
            changed = identity.changed_paths()
            if any(not p.endswith('.py') or p in data['files'].values()
                   or p in native.git('ls-files', '--others', '--exclude-standard').splitlines()
                   for p in changed):
                raise ValueError('native testmon index cannot validate changed test discovery/configuration')
        state = native.state_dir()
        identity.clear_bytecode(identity.changed_paths())
        with tempfile.TemporaryDirectory(prefix='testmon-query-', dir=state) as directory:
            database = Path(directory) / '.testmondata'
            # prepare checkpointed and hashed this closed DB. Copy before
            # opening: WAL-mode SQLite can require writable sidecars even in ro.
            shutil.copyfile(path.parent / '.testmondata', database)
            output = state / 'testmon-selection.json'
            output.unlink(missing_ok=True)
            execution, observed = capture(data['native_command'], output, database,
                ['--testmon', '--testmon-forceselect', '--testmon-nocollect', '--collect-only'],
                int(os.environ.get('ACI_TESTMON_QUERY_TIMEOUT', '60')), data['runner'],
                data['execution_environment'], data['backend'])
        if (execution['timed_out'] or execution['returncode'] not in (0, 5)
                or observed.get('collection_errors') or not observed.get('select')):
            raise ValueError('testmon query incomplete; see ' + str(output.with_suffix('.log')))
        tests = observed['tests']
        files = observed.get('files', data['files'])
        result.update(tests=tests, files=list(dict.fromkeys(files[t] for t in tests)),
            indexed_tests=len(data['tests']), indexed_full_native_suite=data['full_native_suite'],
            execution_unit='native_test_id', query_log=str(output.with_suffix('.log')),
            runner=data['runner'], execution_environment=data['execution_environment'],
            index_sha256=identity.digest(path.read_bytes()))
        if tests:
            # Keeping a preparation directory/file alongside node IDs would
            # make pytest execute that whole scope again.
            if data['runner'] == 'pytest':
                result['command'] = [arg for arg in data['native_command']
                                     if arg not in data['collection_paths']] + [
                                         '-p', 'no:testmon', '-p', 'no:pytest-testmon', *tests]
            elif data['runner'] == 'django':
                result['command'] = native.command([]) + [data['native_ids'][t] for t in tests]
            else:
                result['command'] = native.command(result['files'])
                result['execution_unit'] = 'native_file'
        else:
            result['detail'] = 'testmon selected no tests; no test run or correctness claim'
    except (OSError, ValueError, KeyError, TypeError, sqlite3.Error, subprocess.SubprocessError) as error:
        result.update(unavailable=True, detail=str(error))
    result['lookup_seconds'] = time.monotonic() - start
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='action', required=True)
    commands.add_parser('install').add_argument('target', type=Path)
    prepare_parser = commands.add_parser('prepare')
    prepare_parser.add_argument('output', type=Path)
    prepare_parser.add_argument('--timeout', type=int, default=3600)
    commands.add_parser('check').add_argument('path', type=Path)
    commands.add_parser('select').add_argument('sources', nargs='*')
    import sys
    argv = sys.argv[1:]
    if '--' in argv:
        cut = argv.index('--')
        args, native_args = parser.parse_args(argv[:cut]), argv[cut + 1:]
    else:
        args, native_args = parser.parse_args(argv), []
    if args.action == 'install':
        install(args.target)
    elif args.action == 'prepare':
        prepare(args.output, args.timeout, native_args)
    elif args.action == 'check':
        load(args.path)
        print('testmon database matches base and environment')
    else:
        print(json.dumps(selection(args.sources), indent=2))


if __name__ == '__main__':
    main()
