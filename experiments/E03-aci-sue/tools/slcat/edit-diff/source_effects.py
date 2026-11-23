"""Describe Python source changes without importing code or judging intent.

The AST helpers are shared with the existing offline docstring audit. Comparison
uses this analysis interpreter, not necessarily the repository's runtime. An
unchanged AST excluding docstrings does NOT imply semantic equivalence (__doc__
is observable). Scope names pair syntactically; renames are additions/removals.
"""
import ast
import copy
import hashlib
import json
import sys
import warnings


def scope_nodes(tree):
    found = {}

    def visit(node, scope):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            scope = scope + ([node.name] if hasattr(node, 'name') else [])
            key = '.'.join(scope) or '<module>'
            key += f'#{sum(k.split("#")[0] == key for k in found)}'
            found[key] = node
        for child in ast.iter_child_nodes(node):
            visit(child, scope)

    visit(tree, [])
    return found


def docstrings(tree):
    found = {}
    for key, node in scope_nodes(tree).items():
        if node.body and isinstance(node.body[0], ast.Expr):
            value = node.body[0].value
            if isinstance(value, ast.Constant) and isinstance(value.value, str):
                found[key] = dict(start=node.body[0].lineno, end=node.body[0].end_lineno, value=value.value)
    return found


def without_docstrings(tree):
    tree = copy.deepcopy(tree)
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)) and node.body:
            first = node.body[0]
            if isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant) and isinstance(first.value.value, str):
                node.body = node.body[1:]
    return ast.dump(tree, include_attributes=False)


def parse(source, path):
    try:
        with warnings.catch_warnings():
            warnings.simplefilter('ignore')
            tree = ast.parse(source, filename=path)
            compile(source, path, 'exec')
        return tree, None
    except (SyntaxError, ValueError) as e:
        return None, dict(type=type(e).__name__, message=str(e), line=getattr(e, 'lineno', None),
                          text=getattr(e, 'text', None))


def analyze(before, after, path, baseline='previous report'):
    """Compare known bytes; None denotes an absent file, never unknown content."""
    result = dict(path=path, baseline=baseline, interpreter=sys.version.split()[0],
                  before_sha256=hashlib.sha256(before).hexdigest() if before is not None else None,
                  after_sha256=hashlib.sha256(after).hexdigest() if after is not None else None)
    old, old_error = parse(before or b'', path)
    new, new_error = parse(after or b'', path)
    result.update(before_error=old_error, after_error=new_error)
    if old is None or new is None:
        result['state'] = 'analysis_unavailable'
        return result
    result.update(state='compared', ast_equal=ast.dump(old) == ast.dump(new),
                  non_doc_ast_equal=without_docstrings(old) == without_docstrings(new),
                  file_state='deleted' if after is None else 'added' if before is None else 'modified')
    a, b = scope_nodes(old), scope_nodes(new)
    old_docs, new_docs = docstrings(old), docstrings(new)
    scopes = []
    for name in sorted(set(a) | set(b)):
        left, right = a.get(name), b.get(name)
        changed = left is None or right is None or without_docstrings(left) != without_docstrings(right)
        x, y = old_docs.get(name), new_docs.get(name)
        doc_changed = (x or {}).get('value') != (y or {}).get('value')
        if not changed and not doc_changed:
            continue
        node = right if right is not None else left
        item = dict(symbol=name, kind=type(node).__name__,
                    state='removed' if right is None else 'added' if left is None else 'modified',
                    non_doc_ast_changed=changed, line=getattr(right, 'lineno', None),
                    end_line=getattr(right, 'end_lineno', None))
        if doc_changed:
            displaced = next((n for n in right.body[1:] if isinstance(n, ast.Expr)
                              and isinstance(n.value, ast.Constant) and x and n.value.value == x['value']), None) if right else None
            item['docstring'] = dict(state='added' if x is None else 'removed' if y is None else 'changed',
                                    before_lines=[x['start'], x['end']] if x else None,
                                    after_lines=[y['start'], y['end']] if y else None,
                                    displaced_to_line=displaced.lineno if displaced else None)
        if right is not None:
            body = right.body[1:] if name in new_docs else right.body
            item['first_non_doc_statement'] = getattr(body[0], 'lineno', None) if body else None
        scopes.append(item)
    result['scopes'] = scopes
    return result


BEGIN = '[edit structure] syntactic effects; not a correctness verdict'
END = '[edit structure] end'
OMITTED = '[edit structure] additional facts omitted'


def render(records, budget):
    """Whole-line facts under the existing observation budget; no extra source."""
    if not records:
        return []
    lines = [BEGIN]
    remaining = budget - sum(len(s) + 1 for s in (BEGIN, END, OMITTED))
    if remaining < 0:
        return []
    facts = []
    for record in records:
        path = json.dumps(record['path'], ensure_ascii=True)
        version = (record.get('after_sha256') or 'absent')[:12]
        facts.append(f"[source] {path} @{version}; baseline={record['baseline']}; AST interpreter={record['interpreter']}")
        if record['state'] == 'analysis_unavailable':
            for side in ('before', 'after'):
                error = record.get(side + '_error')
                if error:
                    facts.append(f"[structure] {side} unavailable: {error['type']} at L{error['line']}: "
                                 + json.dumps(error['message'], ensure_ascii=True))
            continue
        facts.append('[structure] AST excluding docstrings: ' + ('unchanged' if record['non_doc_ast_equal'] else 'changed'))
        for scope in record['scopes']:
            # Parent scopes also change when a child changes. Omit only the module
            # aggregate; retain named scopes so wrong-class/function edits are visible.
            if scope['kind'] == 'Module' and 'docstring' not in scope:
                continue
            fact = f"[scope] {scope['symbol']} L{scope['line']}: {scope['state']}"
            if scope.get('first_non_doc_statement') is not None:
                fact += f"; first non-doc statement L{scope['first_non_doc_statement']}"
            doc = scope.get('docstring')
            if doc:
                fact += f"; __doc__ {doc['state']}"
                if doc.get('after_lines'):
                    fact += f" (L{doc['after_lines'][0]}-{doc['after_lines'][1]})"
                if doc.get('displaced_to_line'):
                    fact += f"; former docstring is now an ordinary string at L{doc['displaced_to_line']}"
            facts.append(fact)
    for fact in facts:
        if len(fact) + 1 > remaining:
            lines.append(OMITTED)
            break
        lines.append(fact)
        remaining -= len(fact) + 1
    return [*lines, END]
