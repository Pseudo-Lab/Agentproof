"""Bind explicit search/read targets to later native shell edit observations.

Feedback is the default. Optional selected-file application snapshots explicit
targets before a command and projects retained definitions at normal shell exit.
Only leading comments declare targets. Metadata/recovery copies stay in .git.
Untracked files and killed shells are outside coverage. No inferred intent.
"""
import ast
import base64
import contextlib
import hashlib
import io
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parent))
import source_effects

PREFIX = '# aci-target:'


def declarations(command):
    """Read leading comments only, never a comment inside a heredoc/script."""
    found = []
    for line in command.splitlines():
        line = line.strip()
        if not line:
            continue
        if not line.startswith('#'):
            break
        if line.startswith(PREFIX):
            found.append(line[len(PREFIX):].strip())
    return found


def digest(data):
    return hashlib.sha256(data).hexdigest()


def resolve(source, symbols):
    tree, error = source_effects.parse(source, '<scope source>')
    if error:
        raise ValueError(f"{error['type']} at L{error['line']}: {error['message']}")
    nodes = source_effects.scope_nodes(tree)
    lines = source.splitlines(keepends=True)
    spans = []
    for symbol in dict.fromkeys(symbols):
        matches = [n for k, n in nodes.items() if k.rsplit('#', 1)[0] == symbol]
        if len(matches) != 1:
            raise ValueError(f'{symbol}: expected one current definition, found {len(matches)}')
        node = matches[0]
        start = min([getattr(node, 'lineno', 1),
                     *[d.lineno for d in getattr(node, 'decorator_list', [])]]) - 1
        end = getattr(node, 'end_lineno', len(lines))
        spans.append(dict(symbol=symbol, start=start, end=end,
                          sha256=digest(b''.join(lines[start:end]))))
    return sorted(spans, key=lambda s: (s['start'], -s['end']))


def outside(source, spans):
    """Exact source outside selected AST spans; selected parents cover children."""
    lines = source.splitlines(keepends=True)
    output, cursor = [], 0
    for span in spans:
        if span['start'] < cursor:
            continue
        output.extend(lines[cursor:span['start']])
        output.append(('<selected ' + span['symbol'] + '>\n').encode())
        cursor = span['end']
    output.extend(lines[cursor:])
    return b''.join(output)


def outside_tree(source, symbols):
    """Structural comparison only; AST equality is not semantic equivalence.

    Retain docstrings/constants, module statements and class attributes. Replace
    exactly the selected unique nodes with stable placeholders before comparison.
    """
    tree, error = source_effects.parse(source, '<scope source>')
    if error:
        raise ValueError(error['message'])
    nodes = source_effects.scope_nodes(tree)
    selected = {}
    for symbol in symbols:
        matches = [n for k, n in nodes.items() if k.rsplit('#', 1)[0] == symbol]
        if len(matches) != 1:
            raise ValueError(f'{symbol}: ambiguous or missing definition')
        selected[id(matches[0])] = symbol

    class Mask(ast.NodeTransformer):
        def visit(self, node):
            if id(node) in selected:
                return ast.Expr(value=ast.Constant(value='<selected ' + selected[id(node)] + '>'))
            return super().visit(node)

    return Mask().visit(tree)


def outside_ast(source, symbols):
    return ast.dump(outside_tree(source, symbols), include_attributes=False)


def check(before, after, symbols):
    """Check containment, not whether the chosen repair is correct."""
    if not symbols:
        return dict(status='outside-target', detail='no target selected in this file')
    if before is None or after is None:
        return dict(status='unavailable', detail='creation/deletion is not a retained-symbol edit')
    try:
        old, new = resolve(before, symbols), resolve(after, symbols)
    except ValueError as error:
        return dict(status='unavailable', detail=str(error))
    result = dict(status='within-target' if outside(before, old) == outside(after, new)
                  else 'outside-target', before=old, after=new)
    if result['status'] == 'outside-target':
        result['outside_ast_changed'] = outside_ast(before, symbols) != outside_ast(after, symbols)
        effects = source_effects.analyze(before, after, '<scope source>')
        result['changed_functions'] = [s['symbol'].rsplit('#', 1)[0] for s in effects.get('scopes', [])
                                       if s['kind'] in ('FunctionDef', 'AsyncFunctionDef')
                                       and s['non_doc_ast_changed']]
        old_nodes = source_effects.scope_nodes(outside_tree(before, symbols))
        new_nodes = source_effects.scope_nodes(outside_tree(after, symbols))
        result['outside_functions'] = []
        for name in sorted(set(old_nodes) | set(new_nodes)):
            left, right = old_nodes.get(name), new_nodes.get(name)
            if not isinstance(right if right is not None else left, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            if left is None or right is None or ast.dump(left) != ast.dump(right):
                result['outside_functions'].append(name.rsplit('#', 1)[0])
    return result


def project(before, proposed, symbols):
    """Transplant selected retained definitions only, also used in CPU probes.

    Not called by the default feedback condition. Explicit targets are required;
    missing/ambiguous/renamed definitions and malformed input raise ValueError.
    This preserves outside bytes, not semantic correctness or dependencies.
    """
    if not symbols:
        raise ValueError('projection requires explicitly selected targets')
    old, new = resolve(before, symbols), resolve(proposed, symbols)
    replacements = {s['symbol']: s for s in new}
    source_lines = before.splitlines(keepends=True)
    proposed_lines = proposed.splitlines(keepends=True)
    outer, cursor = [], 0
    for span in old:
        if span['start'] < cursor:
            continue
        outer.append(span)
        cursor = span['end']
    for span in reversed(outer):
        replacement = replacements[span['symbol']]
        source_lines[span['start']:span['end']] = proposed_lines[replacement['start']:replacement['end']]
    projected = b''.join(source_lines)
    _, error = source_effects.parse(projected, '<scope projection>')
    if error:
        raise ValueError(f"projected source invalid: {error['message']}")
    if check(before, projected, symbols)['status'] != 'within-target':
        raise ValueError('projected source does not preserve outside text')
    return projected


def location():
    def git(*args):
        return subprocess.check_output(['git', *args], stderr=subprocess.DEVNULL).decode().strip()
    return Path(git('rev-parse', '--show-toplevel')), Path(git('rev-parse', '--absolute-git-dir')) / 'aci-edit-targets.json'


def save(path, state):
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps(state, ensure_ascii=False) + '\n')
    temporary.replace(path)


def command_state(state_path):
    pid = str(int(os.environ['ACI_EDIT_REPORT_PID']))
    return state_path.parent / ('aci-scope-command-' + pid + '.json')


def file_marker(path):
    """Filesystem effects only; exclude atime so reads do not imply edits."""
    stat = path.stat()
    return [stat.st_ino, stat.st_mtime_ns, stat.st_ctime_ns, stat.st_size]


def process_marker(pid):
    """Live process start time; orphan zombies in containers cannot finish hooks."""
    try:
        fields = Path(f'/proc/{pid}/stat').read_text().rpartition(')')[2].split()
        return None if fields[0] in ('Z', 'X') else fields[19]
    except FileNotFoundError:
        return None


def recover(command):
    """Finalize a dead shell's pending proposal before the next native command.

    Recovery also runs before mini's deadline git diff. Its stdout must stay a
    clean patch in that case, so retain the recovery facts in target state instead.
    This is not safe for concurrent external writers or combined edit/submission.
    """
    _, state_path = location()
    quiet = ('COMPLETE_TASK_AND_SUBMIT_FINAL_OUTPUT' in command or
             'git add -N . && git diff --binary HEAD' in command)
    for pending in sorted(state_path.parent.glob('aci-scope-command-*.json'), key=lambda p: p.stat().st_mtime_ns):
        pid = int(pending.stem.rsplit('-', 1)[1])
        metadata = json.loads(pending.read_text())
        alive = process_marker(pid)
        if alive is not None and metadata.get('owner_start', alive) == alive:
            continue
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            finish(pending)
        feedback = output.getvalue()
        if feedback:
            state = json.loads(state_path.read_text()) if state_path.exists() else dict(targets=[])
            state['last_recovery'] = dict(command_state=pending.name, feedback=feedback)
            save(state_path, state)
            if not quiet:
                print('[scope recovery] finalized an interrupted previous command before this command')
                print(feedback, end='')


def begin():
    """Snapshot current bytes, never last-report/HEAD bytes, for selected files."""
    root, state_path = location()
    state = json.loads(state_path.read_text()) if state_path.exists() else dict(targets=[])
    records = []
    for relative in dict.fromkeys(t['path'] for t in state['targets']):
        path = root / relative
        # HEAD membership excludes intent-to-add entries. Other paths remain native.
        tracked = subprocess.run(['git', 'cat-file', '-e', 'HEAD:' + relative],
                                 cwd=root, capture_output=True).returncode == 0
        if not tracked or not path.is_file() or path.resolve() != path:
            print('[scope apply] ' + relative + ': unsupported; no writeback protection')
            continue
        source = path.read_bytes()
        targets = [t for t in state['targets'] if t['path'] == relative]
        error = None
        try:
            spans = resolve(source, [t['symbol'] for t in targets])
            hashes = {s['symbol']: s['sha256'] for s in spans}
            if any(hashes[t['symbol']] != t['sha256'] for t in targets):
                error = 'stale selection; select current definitions again'
        except ValueError as exc:
            error = 'selection unavailable: ' + str(exc)
        records.append(dict(path=relative, source=base64.b64encode(source).decode(),
                            mode=path.stat().st_mode & 0o777, targets=targets, error=error,
                            file_marker=file_marker(path)))
    save(command_state(state_path), dict(files=records, owner_start=process_marker(os.environ['ACI_EDIT_REPORT_PID'])))


def finish(snapshot_path=None):
    """Per-file writeback before diff/V scheduling. Native command already ran."""
    root, state_path = location()
    snapshot_path = snapshot_path or command_state(state_path)
    if not snapshot_path.exists():
        return
    pending = json.loads(snapshot_path.read_text())
    if pending.get('bound'):
        return finish_bound(root, state_path, snapshot_path, pending)
    snapshots = pending['files']
    state = json.loads(state_path.read_text()) if state_path.exists() else dict(targets=[])
    lines, receipts, changed_proposal = [], [], False
    apply = os.environ.get('ACI_EDIT_SCOPE_APPLY') == '1'
    for item in snapshots:
        relative, before = item['path'], base64.b64decode(item['source'])
        path = root / relative
        if path.resolve() != path or not path.parent.is_dir() or (path.exists() and not path.is_file()):
            if apply:
                lines.append(f'[scope apply] {relative}: unsupported path change; left as produced')
            else:
                receipts.append(f'[edit outcome] {relative}: observation unavailable; path type or target changed')
            continue
        after = path.read_bytes() if path.is_file() else None
        if after == before:
            if (os.environ.get('ACI_EDIT_SCOPE_RECEIPT') == '1' and item.get('file_marker') is not None
                    and file_marker(path) != item['file_marker']):
                receipts.append(f'[edit outcome] {relative}: unchanged content; filesystem metadata changed '
                                'but source bytes are identical. If a code change was intended, inspect the current target.')
            continue
        if not apply:
            continue  # Observation-only mode never changes a proposed edit.
        symbols = [t['symbol'] for t in item['targets']]
        detail = ''
        try:
            if item['error']:
                raise ValueError(item['error'])
            if after is None:
                raise ValueError('selected file was deleted; retained definitions required')
            current = project(before, after, symbols)
            status = 'accepted' if current == after else 'projected'
        except ValueError as exc:
            current, status, detail = before, 'rejected', str(exc)
        if current != after:
            recovery = state_path.parent / 'aci-scope-recovery' / snapshot_path.stem.rsplit('-', 1)[1] / relative
            recovery.parent.mkdir(parents=True, exist_ok=True)
            # A deletion has no proposed file; the pre-command file is restored.
            if after is not None:
                recovery.write_bytes(after)
            if (path.read_bytes() if path.is_file() else None) != after:
                lines.append(f'[scope apply] {relative}: concurrent change; left as produced')
                continue
            fd, temporary = tempfile.mkstemp(prefix='.aci-scope-', dir=path.parent)
            try:
                with os.fdopen(fd, 'wb') as stream:
                    stream.write(current)
                os.chmod(temporary, item['mode'])
                os.replace(temporary, path)
            finally:
                Path(temporary).unlink(missing_ok=True)
            changed_proposal = True
            if after is not None:
                detail += ('; ' if detail else '') + 'proposal saved at ' + str(recovery.relative_to(root))
        if not item['error']:
            spans = {s['symbol']: s for s in resolve(current, symbols)}
            for target in state['targets']:
                if target['path'] == relative and target['symbol'] in spans:
                    target.update({k: spans[target['symbol']][k] for k in ('sha256', 'start', 'end')})
                    target['file_sha256'] = digest(current)
        meaning = {'accepted': 'selected changes retained',
                   'projected': 'selected definitions retained; outside bytes restored',
                   'rejected': 'pre-command file restored'}[status]
        lines.append(f'[scope apply] {relative}: {status}; {meaning}' + ('; ' + detail if detail else ''))
    if state_path.exists():
        save(state_path, state)
    snapshot_path.unlink()
    receipt_budget = max(0, int(os.environ.get('ACI_OUTPUT_CHARS', '5000')) - 300)
    receipt_used = 0
    for receipt in receipts:
        if receipt_used + len(receipt) + 1 > receipt_budget:
            print('[edit outcome] additional unchanged-file facts omitted')
            break
        print(receipt)
        receipt_used += len(receipt) + 1
    if lines:
        # Reserve the state/verification note before optional per-file details.
        print('[edit scope apply] current files after command; other files remain native')
        if changed_proposal:
            print('[scope apply] command output/tests preceded writeback; rerun verification on current files')
        budget = max(0, int(os.environ.get('ACI_OUTPUT_CHARS', '5000')) - 300 - receipt_used)
        for line in lines:
            if len(line) + 1 > budget:
                print('[scope apply] additional file details omitted')
                break
            print(line)
            budget -= len(line) + 1
        print('[edit scope apply] end')


def select(command):
    requested = declarations(command)
    if not requested:
        return []
    root, state_path = location()
    state = dict(targets=[], error=None)
    try:
        if requested != ['clear']:
            for item in dict.fromkeys(requested):
                path, symbol = item.rsplit('::', 1)
                absolute = Path(path).absolute()
                relative = absolute.relative_to(root).as_posix()
                if absolute.resolve() != absolute or '.git' in Path(relative).parts or absolute.suffix != '.py':
                    raise ValueError('target must be a regular Python source path inside the repository')
                source = absolute.read_bytes()
                span = resolve(source, [symbol])[0]
                state['targets'].append(dict(path=relative, symbol=symbol, sha256=span['sha256'],
                                             file_sha256=digest(source), start=span['start'], end=span['end']))
    except (ValueError, OSError) as error:
        state = dict(targets=[], error=str(error))
    save(state_path, state)
    if state['error']:
        return ['[edit target] selection invalid; previous targets cleared: ' + state['error']]
    if not state['targets']:
        return ['[edit target] cleared']
    return [f"[edit target] {t['path']}::{t['symbol']} L{t['start'] + 1}-{t['end']} @{t['sha256'][:12]}"
            for t in state['targets']]


def bound_git(root, *args):
    return subprocess.check_output(['git', *args], cwd=root, stderr=subprocess.DEVNULL)


def python_changes(root, head):
    return [p for p in bound_git(root, 'diff', '--no-ext-diff', '--no-renames',
                                '--name-only', '-z', head, '--', '*.py').decode().split('\0') if p]


def bound_record(path):
    if not path.exists() and not path.is_symlink():
        return dict(source=None, mode=None)
    if path.resolve() != path or not path.is_file():
        raise ValueError('unsupported path type: ' + str(path))
    return dict(source=base64.b64encode(path.read_bytes()).decode(), mode=path.stat().st_mode & 0o777)


def begin_bound(command):
    """Bind this command to versions carried from G, before any shell effects.

    Store only dirty files and declared files. Other existing clean Python files
    can be reconstructed from the recorded HEAD if an undeclared edit occurs.
    """
    root, state_path = location()
    head = bound_git(root, 'rev-parse', 'HEAD').decode().strip()
    targets, records = {}, {}
    for item in dict.fromkeys(declarations(command)):
        try:
            address, expected = item.rsplit('@', 1)
            path, symbol = address.rsplit('::', 1)
        except ValueError:
            raise ValueError('use path.py::Qualified.name@VERSION from a current grep result') from None
        absolute = Path(path).absolute()
        relative = absolute.relative_to(root).as_posix()
        if (absolute.resolve() != absolute or '.git' in absolute.parts or absolute.suffix != '.py'
                or not re.fullmatch(r'[0-9a-f]{12}', expected)):
            raise ValueError('target must be an existing Python path and a 12-digit edit-version')
        bound_git(root, 'cat-file', '-e', f'{head}:{relative}')
        source = absolute.read_bytes()
        if digest(source)[:12] != expected:
            raise ValueError(f'{relative}: stale edit-version; search/read the current source again')
        resolve(source, [symbol])  # exact unique identity; includes decorators
        targets.setdefault(relative, []).append(symbol)
        records[relative] = bound_record(absolute)
    for relative in python_changes(root, head):
        # Newly created files, even staged/intent-to-add, are outside this pilot.
        if subprocess.run(['git', 'cat-file', '-e', f'{head}:{relative}'], cwd=root,
                          capture_output=True).returncode == 0:
            records.setdefault(relative, bound_record(root / relative))
    save(command_state(state_path), dict(bound=True, head=head, targets=targets, files=records,
                                         owner_start=process_marker(os.environ['ACI_EDIT_REPORT_PID'])))


def finish_bound(root, state_path, snapshot_path, pending):
    """Validate the whole existing-Python proposal; never project partial edits."""
    changed, failures = [], []
    for relative in sorted(set(pending['files']) | set(python_changes(root, pending['head']))):
        if relative in pending['files']:
            old = pending['files'][relative]
        else:
            try:
                source = bound_git(root, 'show', f"{pending['head']}:{relative}")
                mode = int(bound_git(root, 'ls-tree', pending['head'], '--', relative).split()[0], 8) & 0o777
                old = dict(source=base64.b64encode(source).decode(), mode=mode)
            except subprocess.CalledProcessError:
                continue  # new files remain native
        current = bound_record(root / relative)
        if current == old:
            continue
        before = base64.b64decode(old['source']) if old['source'] is not None else None
        after = base64.b64decode(current['source']) if current['source'] is not None else None
        changed.append((relative, old, current))
        result = check(before, after, pending['targets'].get(relative, []))
        if result['status'] != 'within-target' or current['mode'] != old['mode']:
            failures.append(f"{relative}: {result.get('detail') or result['status']}" +
                            ('; mode changed' if current['mode'] != old['mode'] else ''))
    if not changed:
        snapshot_path.unlink()
        return
    if failures:
        recovery = state_path.parent / 'aci-scope-recovery' / snapshot_path.stem.rsplit('-', 1)[1]
        recovery.mkdir(parents=True, exist_ok=True)
        save(recovery / 'proposal.json', dict(head=pending['head'], targets=pending['targets'],
                                             failures=failures, changes=[dict(path=p, before=b, proposed=a)
                                                                        for p, b, a in changed]))
        # All validation precedes restoration. No concurrent external writer is supported.
        for relative, before, after in changed:
            path = root / relative
            if bound_record(path) != after:
                raise ValueError('concurrent source change; recovery preserved, cannot safely restore ' + relative)
            if before['source'] is None:
                path.unlink(missing_ok=True)
                continue
            fd, temporary = tempfile.mkstemp(prefix='.aci-bound-', dir=path.parent)
            try:
                with os.fdopen(fd, 'wb') as stream:
                    stream.write(base64.b64decode(before['source']))
                os.chmod(temporary, before['mode'])
                os.replace(temporary, path)
            finally:
                Path(temporary).unlink(missing_ok=True)
        print(f'[bound edit] rejected; all {len(changed)} changed existing Python files restored')
        print('[bound edit] ' + '; '.join(failures))
        print('[bound edit] proposal saved: ' + str((recovery / 'proposal.json').relative_to(root)))
        print('[bound edit] command output/tests preceded rejection; inspect targets and retry, then verify current files')
    else:
        print(f'[bound edit] accepted; {len(changed)} existing Python files; scope/version checks only, not correctness')
        for relative, _, current in changed:
            version = digest(base64.b64decode(current['source']))[:12]
            print(f'[bound edit] {relative} [edit-version: {version}]')
    snapshot_path.unlink()


def assess(snapshots):
    _, state_path = location()
    state = json.loads(state_path.read_text()) if state_path.exists() else dict(targets=[])
    records = []
    for path, before, after, baseline in snapshots:
        targets = [t for t in state['targets'] if t['path'] == path]
        if not state['targets']:
            result = dict(status='unbound', detail='no active edit target')
        else:
            result = check(before, after, [t['symbol'] for t in targets])
            if result.get('before'):
                old = {s['symbol']: s['sha256'] for s in result['before']}
                if any(old.get(t['symbol']) != t['sha256'] for t in targets):
                    result['status'] = 'stale-selection'
                    result['detail'] = 'selected source differs from previous observed source; select again'
                else:
                    new = {s['symbol']: s for s in result['after']}
                    for target in targets:
                        target.update({k: new[target['symbol']][k] for k in ('sha256', 'start', 'end')})
        records.append(dict(path=path, baseline=baseline, **result))
    if state_path.exists():
        save(state_path, state)
    return records


def render(records, budget):
    if not records:
        return []
    begin = '[edit scope] observed changes since previous report; edits remain applied'
    end = '[edit scope] end'
    omitted = '[edit scope] additional facts omitted'
    remaining = budget - sum(len(s) + 1 for s in (begin, end, omitted))
    if remaining < 0:
        return []
    lines = [begin]
    for record in records:
        status = record['status']
        structural = os.environ.get('ACI_EDIT_SCOPE_STRUCTURE') == '1'
        if structural and status == 'outside-target' and record.get('outside_ast_changed') is False:
            status = 'outside-text-only'
        line = f"[scope] {record['path']}: {status}"
        if status == 'outside-text-only':
            line += '; unselected AST unchanged; outside text/comments differ (not a correctness verdict)'
        if record.get('detail'):
            line += '; ' + record['detail']
        if structural and record.get('outside_functions'):
            line += '; functions outside targets: ' + ', '.join(record['outside_functions'])
        elif record.get('changed_functions'):
            line += '; changed functions: ' + ', '.join(record['changed_functions'])
        if len(line) + 1 > remaining:
            lines.append(omitted)
            break
        lines.append(line)
        remaining -= len(line) + 1
    return [*lines, end]


if __name__ == '__main__':
    if sys.argv[1] == '--finish':
        finish()
    else:
        if os.environ.get('ACI_EDIT_BOUND') == '1':
            try:
                recover(sys.argv[1])
                begin_bound(sys.argv[1])
            except (ValueError, OSError, subprocess.CalledProcessError) as error:
                print('[bound edit] command not run: ' + str(error))
                sys.exit(73)
            sys.exit(0)
        if os.environ.get('ACI_EDIT_SCOPE_APPLY') == '1':
            recover(sys.argv[1])
        if declarations(sys.argv[1]):
            print('\n'.join(select(sys.argv[1])))
        if any(os.environ.get(flag) == '1' for flag in ('ACI_EDIT_SCOPE_APPLY', 'ACI_EDIT_SCOPE_RECEIPT')):
            begin()
