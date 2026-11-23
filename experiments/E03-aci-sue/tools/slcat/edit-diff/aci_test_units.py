"""Native test execution units and pytest outcomes (benchmark Python 3.6+).

Raw node IDs remain evidence, not cross-process identities. A Python function
unit includes all its parameters; custom collectors use their native file.
No parameter repr is edited, no items are filtered, and no assertions are merged.
Unittest cases use their observed TestCase class: a method descriptor need not
be a callable that the native loader can safely resolve without an instance.
"""
import json
import os
import sys
from pathlib import Path


def unittest_unit_for(test):
    cls = type(test)
    return dict(selector=cls.__module__ + '.' + cls.__qualname__, kind='class')


def unit_for(item):
    import pytest
    if isinstance(item, pytest.Function):
        # Older pytest leaves originalname=None for ordinary, undecorated
        # functions. Their native item name already is the function selector.
        name = item.originalname or (item.name if not hasattr(item, 'callspec') else None)
        if name:
            return dict(selector=item.parent.nodeid + '::' + name,
                        kind='function', file=str(item.fspath))
    # A non-Function item (e.g. a doctest or plugin-defined item) is executed
    # through the file its native collector actually supplied, not a name rule.
    return dict(selector=str(item.fspath), kind='file', file=str(item.fspath))


class PytestUnits:
    def __init__(self, root, progress=None, unit_stream=None):
        self.root = os.path.realpath(root)
        self.cases = {}
        self.progress = progress
        self.failures = {}
        self.events = []
        self.unit_stream = unit_stream
        self.stream_error = None

    def pytest_collection_finish(self, session):
        descriptors = [(item, unit_for(item)) for item in session.items]
        file_units = {u['file'] for item, u in descriptors if u['kind'] == 'file'}
        for item, unit in descriptors:
            # A selected file also executes its Python functions. Partition by
            # the native file when collectors are mixed, so selectors do not
            # overlap and cause duplicate execution of the same assertions.
            if unit['file'] in file_units:
                unit = dict(selector=unit['file'], kind='file', file=unit['file'])
            unit['file'] = os.path.relpath(os.path.realpath(unit['file']), self.root)
            if unit['kind'] == 'file':
                unit['selector'] = unit['file']
            case = self.cases.setdefault(item.nodeid, dict(
                unit=unit, reports=[], collected=0, started=0, finished=0))
            case['collected'] += 1
        if self.unit_stream:
            self.stream_members = {}
            for node, case in self.cases.items():
                self.stream_members.setdefault(case['unit']['selector'], []).append(node)

    def pytest_runtest_logstart(self, nodeid, location):
        if nodeid in self.cases:
            self.cases[nodeid]['started'] += 1

    def pytest_runtest_logreport(self, report):
        case = self.cases.get(report.nodeid)
        if case is not None:
            observed = dict(when=report.when, outcome=report.outcome,
                            wasxfail=getattr(report, 'wasxfail', None),
                            invocation=case['started'])
            if report.outcome == 'failed':
                native = getattr(report, 'longrepr', None)
                crash = getattr(native, 'reprcrash', None)
                message = getattr(crash, 'message', native)
                if isinstance(message, str):
                    observed['message'] = message
                if (getattr(crash, 'path', None) is not None
                        and isinstance(getattr(crash, 'lineno', None), int)):
                    observed['location'] = dict(path=str(crash.path), line=crash.lineno)
            case['reports'].append(observed)
            if self.progress and report.outcome == 'failed':
                crash = getattr(report.longrepr, 'reprcrash', None)
                self.failures.setdefault((report.nodeid, case['started']), []).append(
                    dict(when=report.when, detail=str(report.longrepr),
                         message=crash.message if crash is not None else str(report.longrepr)))

    def pytest_runtest_logfinish(self, nodeid, location):
        if nodeid in self.cases:
            case = self.cases[nodeid]
            case['finished'] += 1
            failures = self.failures.pop((nodeid, case['started']), [])
            if failures:
                self.events.append(dict(sequence=len(self.events) + 1, nodeid=nodeid,
                                        unit=case['unit']['selector'], invocation=case['started'],
                                        outcome='error' if any(r['when'] != 'call' for r in failures) else 'failed',
                                        reports=failures))
                self.publish_progress()
            if self.unit_stream:
                self.publish_unit(nodeid)

    def publish_unit(self, nodeid):
        """An observed boundary, not a promise that no later invocation occurs."""
        selector = self.cases[nodeid]['unit']['selector']
        members = self.stream_members[selector]
        unit = self.result(members)['units'][selector]
        failure = next((dict(nodeid=node, when=report['when'], message=report['message'])
                        for node in members for report in self.cases[node]['reports']
                        if report['outcome'] == 'failed' and 'message' in report), None)
        packet = dict(kind='unit_observation', id=self.unit_stream['id'],
                      side=self.unit_stream['side'], unit=selector, outcome=unit['outcome'],
                      collected=unit['collected_case_count'], executed=unit['executed_case_count'],
                      finished=sum(self.cases[node]['finished'] for node in members), failure=failure)
        try:
            # Native stdout/stderr retain their own log. This descriptor is a
            # private stream to the owning host, consumed before tests start.
            data = (json.dumps(packet) + '\n').encode()
            while data:
                data = data[os.write(self.unit_stream['fd'], data):]
        except OSError as error:
            self.stream_error = str(error)

    def publish_progress(self):
        """Completed failing cases only; the selected run and fresh comparison continue."""
        state = Path(self.progress['state'])
        path = state / (self.progress['id'] + '.progress.json')
        packet = dict(id=self.progress['id'], kind='test_progress',
                      start_revision=self.progress['start_revision'],
                      events=self.events, sequence=len(self.events), log_path=str(path),
                      completed_cases=sum(c['finished'] for c in self.cases.values()),
                      collected_cases=sum(c['collected'] for c in self.cases.values()))
        try:
            if json.loads((state / 'job.json').read_text())['id'] != packet['id']:
                return
            # Retain full native details separately from bounded observations.
            temporary = path.with_suffix('.tmp')
            temporary.write_text(json.dumps(packet))
            temporary.replace(path)
            temporary = state / (packet['id'] + '.progress-result.tmp')
            temporary.write_text(json.dumps(packet))
            temporary.replace(state / 'result.json')
        except (OSError, ValueError):
            # Cancellation or unavailable reporting storage must not change the
            # native assertion outcome. The final report remains authoritative.
            return

    def result(self, nodeids=None):
        units = {}
        cases = self.cases if nodeids is None else {node: self.cases[node] for node in nodeids}
        for nodeid, case in cases.items():
            descriptor = case['unit']
            unit = units.setdefault(descriptor['selector'], dict(
                kind=descriptor['kind'], file=descriptor['file'], cases={},
                collected_case_count=0, executed_case_count=0))
            unit['collected_case_count'] += case['collected']
            unit['executed_case_count'] += case['started']
            reports = case['reports']
            if case['started'] < case['collected'] or case['finished'] != case['started']:
                status = 'incomplete'
            elif any(r['outcome'] == 'failed' and r['when'] != 'call' for r in reports):
                status = 'error'
            elif any(r['outcome'] == 'failed' for r in reports):
                status = 'failed'
            elif any(r['outcome'] not in ('passed', 'skipped') for r in reports):
                status = 'incomplete'
            elif any(r['outcome'] == 'skipped' for r in reports):
                status = 'skipped'
            elif any(r['when'] == 'call' and r['outcome'] == 'passed' for r in reports):
                status = 'passed'
            else:
                status = 'incomplete'
            unit['cases'][nodeid] = status
        for unit in units.values():
            statuses = list(unit['cases'].values())
            if 'incomplete' in statuses:
                verdict = 'incomplete'
            elif any(s in ('failed', 'error') for s in statuses):
                verdict = 'failed'
            elif all(s == 'passed' for s in statuses):
                verdict = 'passed'
            elif 'passed' in statuses:
                verdict = 'partial'
            else:
                verdict = 'skipped'
            unit['outcome'] = verdict
        result = dict(schema=1, units=units, case_reports=cases,
                      case_units={n: c['unit'] for n, c in cases.items()})
        if self.stream_error:
            result['unit_stream_error'] = self.stream_error
        return result

    def write(self, path):
        with open(path, 'w') as output:
            json.dump(self.result(), output)


def command(argv, report):
    if argv[1:3] != ['-m', 'pytest']:
        raise ValueError('pytest unit reporting requires native python -m pytest argv')
    return [argv[0], os.path.abspath(__file__), str(report), *argv[3:]]


def comparison(current, baseline, requested):
    """Compare complete native units; never equate parameter instances by order."""
    result = dict(new=[], existing=[], fixed=[], unverified=[], passed=[])
    for selector in requested:
        after = current.get('units', {}).get(selector, {}).get('outcome')
        before = baseline.get('units', {}).get(selector, {}).get('outcome')
        if after not in ('passed', 'failed') or before not in ('passed', 'failed'):
            result['unverified'].append(selector)
        elif after == 'failed':
            result['new' if before == 'passed' else 'existing'].append(selector)
        else:
            result['fixed' if before == 'failed' else 'passed'].append(selector)
    return result


def failure_detail(current, baseline, requested):
    """Choose native diagnostic evidence; never match cases across processes.

    Unit pass-to-fail has priority. A unit failing on both sides has two
    independent diagnostic lists, not a text-based regression classifier.
    Missing or incomplete reports remain unavailable.
    """
    def messages(report, selector):
        unit = report.get('units', {}).get(selector, {})
        if unit.get('outcome') not in ('passed', 'failed'):
            return None
        found = []
        for nodeid in unit.get('cases', {}):
            case = report.get('case_reports', {}).get(nodeid)
            if case is None:
                return None
            for observed in case['reports']:
                if observed['outcome'] == 'failed':
                    if not isinstance(observed.get('message'), str):
                        return None
                    found.append((observed['when'], observed['message']))
        return found

    compared = comparison(current, baseline, requested)
    for selector in compared['new'] + compared['existing']:
        after, before = messages(current, selector), messages(baseline, selector)
        if after is None or before is None:
            continue
        if after:
            return dict(unit=selector, current=after, baseline=before,
                        kind='new_unit' if selector in compared['new'] else 'unpaired_summaries')
    return None


def main():
    report, args = sys.argv[1], sys.argv[2:]
    # Match python -m pytest's repository import root. The helper's own path
    # must not shadow an application module during native collection.
    sys.path[0] = os.getcwd()
    import pytest
    # Consume the internal context here so nested test subprocesses cannot
    # accidentally publish into their parent's callback channel.
    progress = json.loads(os.environ.pop('ACI_TESTS_PROGRESS', 'null'))
    unit_stream = json.loads(os.environ.pop('ACI_TESTS_UNIT_STREAM', 'null'))
    if unit_stream:
        os.set_inheritable(unit_stream['fd'], False)
    plugin = PytestUnits(os.getcwd(), progress=progress, unit_stream=unit_stream)
    try:
        raise SystemExit(pytest.main(args, plugins=[plugin]))
    finally:
        plugin.write(report)


if __name__ == '__main__':
    main()
