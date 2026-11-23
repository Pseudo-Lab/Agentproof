"""Candidate-only structural correspondence diagnostics (no benchmark inputs).

Inputs: a Python path and its before/after text. Outputs: review evidence, never
mandatory edits. The supported universe is explicit: same-file class inheritance
and direct same-file isinstance dispatch delegation. This is not sound alias or
interprocedural analysis. No issue IDs, gold, test labels, or domain symbols.
"""
import ast
import copy
import hashlib
import re
import textwrap


def dump(node):
    return ast.dump(node, include_attributes=False)


def own(fn):
    for statement in fn.body:
        stack = [statement]
        while stack:
            node = stack.pop()
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                continue
            yield node
            stack.extend(reversed(list(ast.iter_child_nodes(node))))


def params(fn):
    return {a.arg for a in fn.args.posonlyargs + fn.args.args + fn.args.kwonlyargs}


def instance_fields(fn):
    names = [a.arg for a in fn.args.posonlyargs + fn.args.args]
    if not names:
        return {}
    receiver = names[0]
    found = {}
    for n in own(fn):
        if isinstance(n, ast.Assign) and isinstance(n.value, ast.Name) and n.value.id in params(fn):
            for target in n.targets:
                if isinstance(target, ast.Attribute) and isinstance(target.value, ast.Name) and target.value.id == receiver:
                    found[target.attr] = n.value.id
    return found


def reads(fn):
    names = [a.arg for a in fn.args.posonlyargs + fn.args.args]
    if not names:
        return set()
    return {n.attr for n in own(fn) if isinstance(n, ast.Attribute) and isinstance(n.ctx, ast.Load)
            and isinstance(n.value, ast.Name) and n.value.id == names[0]}


class Rename(ast.NodeTransformer):
    def __init__(self, mapping, strings=False):
        self.mapping, self.strings = mapping, strings

    def visit_Name(self, n):
        n.id = self.mapping.get(n.id, n.id)
        return n

    def visit_Attribute(self, n):
        self.generic_visit(n)
        n.attr = self.mapping.get(n.attr, n.attr)
        return n

    def visit_keyword(self, n):
        self.generic_visit(n)
        n.arg = self.mapping.get(n.arg, n.arg)
        return n

    def visit_Constant(self, n):
        if isinstance(n.value, str):
            if self.strings:
                for old, new in self.mapping.items():
                    n.value = re.sub(r'\b' + re.escape(old) + r'\b', lambda m: new, n.value)
            else:
                n.value = self.mapping.get(n.value, n.value)
        return n


def contexts(fn, field, parameter):
    result = set()
    for n in own(fn):
        if not isinstance(n, (ast.Assign, ast.AnnAssign, ast.Return, ast.keyword)):
            continue
        # Exclude unrelated statements that would match without substitution.
        transformed = Rename({field: '_FIELD_', parameter: '_FIELD_'}).visit(copy.deepcopy(n))
        if dump(transformed) != dump(n):
            result.add(dump(transformed))
    return result


def class_groups(tree):
    classes = {n.name: n for n in tree.body if isinstance(n, ast.ClassDef)}
    edges = {name: set() for name in classes}
    for name, cls in classes.items():
        for base in cls.bases:
            if isinstance(base, ast.Name) and base.id in classes:
                edges[name].add(base.id)
                edges[base.id].add(name)
    groups, visited = [], set()
    for name in sorted(classes):
        if name in visited:
            continue
        group, pending = set(), [name]
        while pending:
            cur = pending.pop()
            if cur in group:
                continue
            group.add(cur)
            pending.extend(edges[cur] - group)
        visited.update(group)
        groups.append(group)
    methods = {name + '.' + fn.name: fn for name, cls in classes.items()
               for fn in cls.body if isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef))}
    return classes, groups, methods


def snippet(raw, fn, term=None):
    lines = raw.splitlines()
    wanted = {fn.lineno}
    for n in own(fn):
        if term is None or (isinstance(n, ast.Attribute) and n.attr == term):
            if hasattr(n, 'lineno'):
                wanted.update(range(max(fn.lineno, n.lineno - 1), min(fn.end_lineno, getattr(n, 'end_lineno', n.lineno) + 1) + 1))
    result, previous = [], None
    for i in sorted(wanted):
        if previous is not None and i != previous + 1:
            result.append('  ...')
        result.append(f'{i}: {lines[i-1]}')
        previous = i
    return '\n'.join(result)


def state_relations(path, before, after, old, new):
    old_classes, _, old_methods = class_groups(old)
    classes, groups, methods = class_groups(new)
    results, abstentions = [], []
    for group in groups:
        fresh, prior = {}, {}
        for cls in group:
            key = cls + '.__init__'
            if key not in methods or key not in old_methods:
                continue
            prev, cur = old_methods[key], methods[key]
            prior.update(instance_fields(prev))
            for field, parameter in instance_fields(cur).items():
                if parameter not in params(prev) and field not in instance_fields(prev):
                    fresh[field] = parameter
        family = {k: f for k, f in methods.items() if k.split('.')[0] in group}
        for field, parameter in fresh.items():
            scored = {}
            for previous, previous_param in prior.items():
                witnesses = [k for k, fn in family.items()
                    if k in old_methods and dump(fn) != dump(old_methods[k])
                    and contexts(fn, field, parameter) & contexts(fn, previous, previous_param)]
                if witnesses:
                    scored[previous] = witnesses
            if not scored:
                abstentions.append(dict(kind='state', field=field, reason='no_structural_analogy'))
                continue
            best = max(map(len, scored.values()))
            tied = [p for p, w in scored.items() if len(w) == best]
            # Two distinct method witnesses, not two syntactically identical lines.
            if best < 2 or len(tied) != 1:
                abstentions.append(dict(kind='state', field=field, reason='insufficient_or_ambiguous_witnesses', scores={k: len(v) for k, v in scored.items()}))
                continue
            previous = tied[0]
            for key, fn in family.items():
                if (key not in old_methods or dump(fn) != dump(old_methods[key])
                        or previous not in reads(fn) or field in reads(fn)):
                    continue
                results.append(dict(kind='state', path=path, family=sorted(group), new_field=field,
                    new_parameter=parameter, old_field=previous, old_parameter=prior[previous],
                    witnesses=scored[previous], target=key, line=fn.lineno,
                    score=len(scored[previous]), composite_reads=len(reads(fn)),
                    evidence=snippet(after, fn, previous),
                    meaning='Unchanged consumer of analogous old state. Review relevance; not proof this method must change.'))
    return results, abstentions


def branches(fn):
    result = {}
    for n in own(fn):
        if (isinstance(n, ast.If) and isinstance(n.test, ast.Call)
                and isinstance(n.test.func, ast.Name) and n.test.func.id == 'isinstance'
                and len(n.test.args) == 2 and isinstance(n.test.args[0], ast.Name)
                and n.test.args[0].id in params(fn)):
            result[dump(n.test)] = n
    return result


def identity_returns(fn, parameter):
    result = []
    def walk(statements, guards):
        for node in statements:
            if isinstance(node, ast.Return) and isinstance(node.value, ast.Name) and node.value.id == parameter:
                result.append(dict(line=node.lineno, guards=guards, return_source=ast.unparse(node)))
            elif isinstance(node, ast.If):
                walk(node.body, guards + [ast.unparse(node.test)])
                walk(node.orelse, guards + ['not (' + ast.unparse(node.test) + ')'])
            elif isinstance(node, (ast.For, ast.While, ast.Try, ast.With)):
                # No invented path conditions for control constructs we do not model.
                continue
    walk(fn.body, [])
    return result


def dispatch_relations(path, before, after, old, new):
    old_functions = {n.name: n for n in old.body if isinstance(n, ast.FunctionDef)}
    functions = {n.name: n for n in new.body if isinstance(n, ast.FunctionDef)}
    result, abstentions = [], []
    for name, fn in functions.items():
        if name not in old_functions:
            continue
        prior, current = branches(old_functions[name]), branches(fn)
        changed = [key for key, node in current.items() if key in prior and
                   dump(ast.Module(body=node.body, type_ignores=[])) != dump(ast.Module(body=prior[key].body, type_ignores=[]))]
        if not changed:
            continue
        for key, branch in current.items():
            if key in changed or key not in prior or dump(ast.Module(body=branch.body, type_ignores=[])) != dump(ast.Module(body=prior[key].body, type_ignores=[])):
                continue
            if len(branch.body) != 1 or not isinstance(branch.body[0], ast.Return) or not isinstance(branch.body[0].value, ast.Call):
                continue
            call = branch.body[0].value
            arg = branch.test.args[0].id
            if not (call.args and isinstance(call.args[0], ast.Name) and call.args[0].id == arg):
                continue
            if not isinstance(call.func, ast.Name) or call.func.id not in functions:
                abstentions.append(dict(kind='dispatch', target=name, reason='unresolved_delegate', line=call.lineno))
                continue
            target = call.func.id
            helper = functions[target]
            if target == name or target not in old_functions or dump(helper) != dump(old_functions[target]):
                continue
            args = helper.args.posonlyargs + helper.args.args
            if not args:
                continue
            exits = identity_returns(helper, args[0].arg)
            if not exits:
                continue
            helper_calls_dispatcher = any(isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id == name for n in own(helper))
            if helper_calls_dispatcher:
                continue
            result.append(dict(kind='dispatch', path=path, dispatcher=name, target=target,
                line=helper.lineno, changed_guards=[ast.unparse(current[k].test) for k in changed],
                sibling_guard=ast.unparse(branch.test), delegation=ast.unparse(branch.body[0]),
                identity_exits=exits, score=len(changed), composite_reads=0,
                evidence=snippet(after, helper),
                meaning='Unchanged delegate has identity-return paths and no direct call back to dispatcher. Static review candidate, not proof of a reachable semantic error.'))
    return result, abstentions


def analyze(path, before, after):
    try:
        old, new = ast.parse(before), ast.parse(after)
    except SyntaxError as error:
        return dict(status='unparseable', error=str(error), candidates=[], abstentions=[])
    state, sa = state_relations(path, before, after, old, new)
    dispatch, da = dispatch_relations(path, before, after, old, new)
    candidates = sorted(state + dispatch, key=lambda r: (-r['score'], -r['composite_reads'], r['path'], r['line'], r['target']))
    return dict(status='examined', candidates=candidates, abstentions=sa + da)


def render(candidates, budget=5000):
    header = '[change relations] Review candidates, not required edits.\n'
    output, included = header, []
    for i, row in enumerate(candidates):
        if row['kind'] == 'state':
            relation = f"State {row['old_field']} -> {row['new_field']}; matching uses in {', '.join(row['witnesses'])}.\nUnchanged consumer: {row['target']}"
        else:
            relation = f"Changed dispatch: {', '.join(row['changed_guards'])}.\nSibling {row['sibling_guard']} -> {row['delegation']}\nDelegate: {row['target']}; identity exits: {row['identity_exits']}"
        card = f"\n{row['path']}:{row['line']}\n{relation}\n{row['evidence']}\n"
        if len(output) + len(card) + 100 <= budget:
            output += card
            included.append(i)
    if len(included) < len(candidates):
        output += f'\n[omitted for budget] {len(candidates)-len(included)} complete candidates\n'
    return output if candidates else '', included
