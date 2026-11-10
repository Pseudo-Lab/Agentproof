"""Python 3.6-compatible observer of upstream pytest/testmon; no selection logic."""
import json
import os
import sys


def main():
    output, args = sys.argv[1], sys.argv[2:]
    sys.path[0] = os.getcwd()
    import pytest
    native_path = sys.path[:]
    from testmon import pytest_testmon  # noqa: F401; preload without leaking import path changes
    sys.path[:] = native_path

    record = dict(tests=[], files={}, completed=[], collection_errors=[])

    class Observer:
        def pytest_collection_finish(self, session):
            record['tests'] = [item.nodeid for item in session.items]
            record['collection_paths'] = list(session.config.args)
            record['files'] = {item.nodeid: os.path.relpath(str(item.fspath))
                               for item in session.items}
            conf = getattr(session.config, 'testmon_config', None)
            if conf is not None:
                record['select'] = conf[2] if isinstance(conf, tuple) else conf.select
                record['collect'] = conf[1] if isinstance(conf, tuple) else conf.collect

        def pytest_collectreport(self, report):
            if report.failed:
                record['collection_errors'].append(report.nodeid)

        def pytest_runtest_logfinish(self, nodeid, location):
            record['completed'].append(nodeid)

    try:
        code = pytest.main(args, plugins=[Observer()])
        record['exit_code'] = int(code)
    finally:
        with open(output, 'w') as stream:
            json.dump(record, stream)
    return code


if __name__ == '__main__':
    sys.exit(main())
