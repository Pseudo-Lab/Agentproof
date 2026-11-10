"""Native unittest/SymPy boundaries for the pinned testmon 1.3.3 core.

No trace or source-change algorithm is implemented here. Testmon owns coverage,
fingerprints, DB and change lookup. Native runners own discovery and execution.
Class/module fixture fingerprints attach only to tests in their actual scope.
"""
import inspect
import json
import os
import runpy
import sys
import time
import unittest


def main():
    action, output, kind = sys.argv[1:4]
    sys.path[0] = os.getcwd()
    native_path = sys.path[:]
    from testmon.testmon_core import Testmon, TestmonData
    # Old testmon imports pkg_resources, whose newer setuptools can append
    # vendored distributions to sys.path and expose extra pytest entry points.
    # Keep native discovery paths; only measurement imports use that side effect.
    sys.path[:] = native_path

    root = os.getcwd()
    data = TestmonData(root)
    if action == 'select':
        data.determine_stable()
        selected = set(data.unstable_nodeids)
        selected.update(node for node, outcome in data.all_nodes.items() if outcome['failed'])
        with open(output, 'w') as stream:
            json.dump({'tests': sorted(selected), 'select': True, 'collection_errors': []}, stream)
        data.db.con.close()
        return 0

    record = dict(tests=[], files={}, native_ids={}, completed=[], collection_errors=[],
                  collect=True, select=False, fixture_scopes={})
    pending, fixtures, restore = {}, {}, []
    current = [None]

    def patch(owner, name, replacement):
        restore.append((owner, name, getattr(owner, name)))
        setattr(owner, name, replacement)

    def node_for(test):
        cls = type(test)
        filename = os.path.relpath(inspect.getsourcefile(cls), root)
        return filename + '::' + test.id(), filename

    def begin(node, filename, native_id, scopes=()):
        recorder = Testmon(root)
        if node not in record['files']:
            record['tests'].append(node)
        record['files'][node] = filename
        record['native_ids'][node] = native_id
        record['fixture_scopes'][node] = list(scopes)
        recorder.start()
        return recorder, time.monotonic()

    def finish(node, measurement, failed):
        recorder, start = measurement
        fingerprints = recorder.stop_and_process(data, node)
        recorder.close()
        pending[node] = (fingerprints, {'call': {'outcome': 'failed' if failed else 'passed',
                                               'duration': time.monotonic() - start}})
        record['completed'].append(node)

    original = unittest.TestCase.run

    def test_run(test, result=None):
        # Nested unittest executions belong to their enclosing native test.
        if current[0] is not None:
            return original(test, result)
        node, filename = node_for(test)
        cls = type(test)
        scopes = ('module:' + cls.__module__, 'class:' + cls.__module__ + '.' + cls.__name__)
        measurement = begin(node, filename, test.id(), scopes)
        current[0] = node
        before = len(result.failures) + len(result.errors) if result is not None else 0
        failed = True
        try:
            returned = original(test, result)
            actual = result if result is not None else returned
            failed = len(actual.failures) + len(actual.errors) > before
            return returned
        finally:
            finish(node, measurement, failed)
            current[0] = None

    patch(unittest.TestCase, 'run', test_run)

    def fixture_wrapper(name, previous=False, module=False):
        original = getattr(unittest.TestSuite, name)

        def fixture(suite, *args):
            result = args[-1]
            cls = getattr(result, '_previousTestClass', None) if previous else type(args[0])
            if cls is None:
                return original(suite, *args)
            scope = ('module:' + cls.__module__) if module else ('class:' + cls.__module__ + '.' + cls.__name__)
            try:
                filename = os.path.relpath(inspect.getsourcefile(cls), root)
            except (TypeError, OSError):
                return original(suite, *args)
            recorder = Testmon(root)
            recorder.start()
            try:
                return original(suite, *args)
            finally:
                fingerprints = recorder.stop_and_process(data, filename + '::__fixture__')
                fixtures.setdefault(scope, []).extend(fingerprints)
                recorder.close()
        patch(unittest.TestSuite, name, fixture)

    if kind == 'django':
        fixture_wrapper('_handleClassSetUp')
        fixture_wrapper('_tearDownPreviousClass', previous=True)
        fixture_wrapper('_handleModuleFixture', module=True)
        fixture_wrapper('_handleModuleTearDown', previous=True, module=True)
    elif kind == 'sympy':
        try:
            from sympy.testing import runtests
        except ImportError:
            from sympy.utilities import runtests
        reporter = runtests.PyTestReporter
        original_begin = reporter.entering_test

        def sympy_begin(self, function):
            filename = self._active_file
            node = filename + '::' + function.__name__
            current[0] = (node, begin(node, filename, node))
            return original_begin(self, function)
        patch(reporter, 'entering_test', sympy_begin)

        def sympy_end(name):
            original_end = getattr(reporter, name)

            def end(self, *args, **kwargs):
                try:
                    return original_end(self, *args, **kwargs)
                finally:
                    if current[0] is not None:
                        node, measurement = current[0]
                        finish(node, measurement, name in ('test_fail', 'test_exception', 'test_xpass'))
                        current[0] = None
            patch(reporter, name, end)
        for name in ('test_pass', 'test_fail', 'test_exception', 'test_skip', 'test_xfail', 'test_xpass'):
            sympy_end(name)

    script, args = sys.argv[4], sys.argv[5:]
    sys.argv = [script] + args
    sys.path[0] = root if script == '-m' else os.path.dirname(os.path.abspath(script))
    code = 0
    try:
        if kind == 'pytest':
            import pytest
            failed = {}

            class Observer:
                def pytest_collection_finish(self, session):
                    record['tests'] = [item.nodeid for item in session.items]
                    record['files'] = {item.nodeid: os.path.relpath(str(item.fspath), root)
                                       for item in session.items}
                    record['collection_paths'] = list(session.config.args)

                def pytest_collectreport(self, report):
                    if report.failed:
                        record['collection_errors'].append(report.nodeid)

                def pytest_runtest_logreport(self, report):
                    if report.failed:
                        failed[report.nodeid] = True

                @pytest.hookimpl(hookwrapper=True)
                def pytest_runtest_protocol(self, item, nextitem):
                    node = item.nodeid
                    measurement = begin(node, os.path.relpath(str(item.fspath), root), node)
                    current[0] = node
                    try:
                        yield
                    finally:
                        finish(node, measurement, failed.get(node, False))
                        current[0] = None
            code = pytest.main(args[1:] + ['-p', 'no:testmon', '-p', 'no:pytest-testmon'], plugins=[Observer()])
        else:
            runpy.run_path(script, run_name='__main__')
    except SystemExit as error:
        code = error.code or 0
    except BaseException as error:
        record['collection_errors'].append(type(error).__name__ + ': ' + str(error))
        raise
    finally:
        for owner, name, method in reversed(restore):
            setattr(owner, name, method)
        # Use the same upstream DB records; only native fixture ownership is added.
        for node, (fingerprints, outcome) in pending.items():
            for scope in record['fixture_scopes'][node]:
                fingerprints += fixtures.get(scope, [])
            data.db.insert_node_fingerprints(node, fingerprints, outcome)
        data.db.con.close()
        record['exit_code'] = code
        with open(output, 'w') as stream:
            json.dump(record, stream)
    return code


if __name__ == '__main__':
    sys.exit(main())
