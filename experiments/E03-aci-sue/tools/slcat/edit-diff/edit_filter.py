"""Silent, observation-conditioned projection of native Python edits.

No model tool or intent oracle. A local statement/binding graph keeps dependent
changes together; unresolved observation identity abstains. Never import task code.
"""
import ast
import base64
from collections import defaultdict, deque
import difflib
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parent))
import edit_scope as scope
import source_effects

DEFS = (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)
FUNCS = (ast.FunctionDef, ast.AsyncFunctionDef)


def definition_header(node):
    """Construction of a binding, separately from its deferred implementation."""
    return ast.dump(type(node)(**{name: [] if name == 'body' else value
                                 for name, value in ast.iter_fields(node)}))


class InvalidSource(ValueError):
    """Unsupported source syntax, distinct from invalid callback state."""


class Syntax:
    """Statement identities and lexical bindings, local to one source version."""
    def __init__(self, raw):
        self.tree, error = source_effects.parse(raw, '<edit filter>')
        if error:
            raise InvalidSource(error['message'])
        self.nodes, self.parents, self.owner, self.defs = [], {}, {}, {}
        self.ambiguous = set()

        def walk(node, owner=''):
            self.owner[node] = owner
            if isinstance(node, ast.stmt):
                self.nodes.append(node)
            child_owner = owner
            if isinstance(node, DEFS):
                child_owner = '.'.join(filter(None, (owner, node.name)))
                if child_owner in self.defs:
                    self.ambiguous.add(child_owner)
                self.defs[child_owner] = node
            for child in ast.iter_child_nodes(node):
                self.parents[child] = node
                walk(child, child_owner)
        walk(self.tree)
        self.index = {node: i for i, node in enumerate(self.nodes)}
        # Structural ownership drives observations/diff units. Lexical scopes
        # separately govern names, including scopes with no statement node.
        self.lexical, self.scope_parent, self.scope_kind = {}, {'': None}, {'': ast.Module}

        def scoped(node, namespace=''):
            self.lexical[node] = namespace
            if isinstance(node, (*DEFS, ast.Lambda, ast.ListComp, ast.SetComp, ast.DictComp, ast.GeneratorExp)):
                inner = ('.'.join(filter(None, (self.owner[node], node.name))) if isinstance(node, DEFS)
                         else namespace + '.<' + type(node).__name__ + '@' + str(node.lineno) + ':' + str(node.col_offset) + '>')
                self.scope_parent[inner], self.scope_kind[inner] = namespace, type(node)
                if isinstance(node, (*FUNCS, ast.Lambda)):
                    args = node.args
                    self.lexical[args] = inner
                    for arg in [*args.posonlyargs, *args.args, *args.kwonlyargs, args.vararg, args.kwarg]:
                        if arg is not None:
                            self.lexical[arg] = inner
                            if arg.annotation is not None:
                                scoped(arg.annotation, namespace)
                    for value in [*args.defaults, *args.kw_defaults, getattr(node, 'returns', None),
                                  *getattr(node, 'decorator_list', [])]:
                        if value is not None:
                            scoped(value, namespace)
                    for body in ([node.body] if isinstance(node, ast.Lambda) else node.body):
                        scoped(body, inner)
                elif isinstance(node, ast.ClassDef):
                    for expression in [*node.bases, *node.keywords, *node.decorator_list]:
                        scoped(expression, namespace)
                    for body in node.body:
                        scoped(body, inner)
                else:
                    for i, generator in enumerate(node.generators):
                        self.lexical[generator] = inner
                        scoped(generator.iter, namespace if i == 0 else inner)
                        scoped(generator.target, inner)
                        for condition in generator.ifs:
                            scoped(condition, inner)
                    for expression in ([node.key, node.value] if isinstance(node, ast.DictComp) else [node.elt]):
                        scoped(expression, inner)
                return
            if isinstance(node, ast.NamedExpr):
                target_scope = namespace
                while self.scope_kind[target_scope] in (ast.ListComp, ast.SetComp, ast.DictComp, ast.GeneratorExp):
                    target_scope = self.scope_parent[target_scope]
                scoped(node.target, target_scope)
                scoped(node.value, namespace)
                return
            for child in ast.iter_child_nodes(node):
                scoped(child, namespace)
        scoped(self.tree)
        self.locals = defaultdict(set)
        self.globals = defaultdict(set)
        for node in ast.walk(self.tree):
            owner = self.lexical.get(node, self.owner[node])
            if isinstance(node, ast.Name) and isinstance(node.ctx, (ast.Store, ast.Del)):
                self.locals[owner].add(node.id)
            elif isinstance(node, DEFS):
                self.locals[owner].add(node.name)
            elif isinstance(node, (ast.Import, ast.ImportFrom)):
                self.locals[owner].update(a.asname or a.name.split('.')[0] for a in node.names)
            elif isinstance(node, ast.arg):
                self.locals[owner].add(node.arg)
            elif isinstance(node, ast.Global):
                self.globals[owner].update(node.names)
            elif isinstance(node, ast.ExceptHandler) and node.name:
                self.locals[owner].add(node.name)
        self.binders = defaultdict(set)
        self.uses = {}
        self.receivers = defaultdict(list)
        for node in self.nodes:
            uses, writes = self.references(node)
            self.uses[node] = uses
            for key in writes:
                self.binders[key].add(self.index[node])
        # Resolve receiver uses only after all declarations/stores are known.
        # Inheritance supplies possible bindings, not edges to whole classes.
        for node, receivers in self.receivers.items():
            for owners, name in receivers:
                self.uses[node].update(key for owner in owners for key in self.receiver_keys(owner, name))

    def definition_name(self, expression, owner):
        if isinstance(expression, ast.Name):
            namespace, name = self.name_key(owner, expression.id)
            return '.'.join(filter(None, (namespace, name)))
        if isinstance(expression, ast.Attribute):
            parent = self.definition_name(expression.value, owner)
            return parent + '.' + expression.attr if parent else None
        return None

    def base_names(self, owner):
        definition = self.defs.get(owner)
        if not isinstance(definition, ast.ClassDef):
            return []
        return [name for base in definition.bases
                if (name := self.definition_name(base, self.owner[definition])) and
                isinstance(self.defs.get(name), ast.ClassDef)]

    def receiver_keys(self, owner, name, seen=frozenset()):
        key = (owner, name)
        if owner in seen or key in self.binders:
            return {key}
        found = set()
        for base in self.base_names(owner):
            found.update(self.receiver_keys(base, name, seen | {owner}))
        return found or {key}

    def name_key(self, owner, name):
        current = owner
        while current:
            if name in self.globals[current]:
                return ('', name)
            if name in self.locals[current]:
                return (current, name)
            current = self.scope_parent.get(current)
            # Class namespaces are not enclosing lexical scopes for methods.
            while self.scope_kind.get(current) is ast.ClassDef:
                current = self.scope_parent[current]
        return ('', name)

    def references(self, statement):
        uses, writes = set(), set()
        def visit(node):
            if node is not statement and isinstance(node, ast.stmt):
                return
            owner = self.lexical.get(node, self.owner[node])
            if isinstance(node, ast.Name):
                key = self.name_key(owner, node.id)
                (uses if isinstance(node.ctx, ast.Load) else writes).add(key)
            elif isinstance(node, ast.Attribute):
                parent = self.owner[node]
                while parent and not isinstance(self.defs.get(parent), ast.ClassDef):
                    parent = parent.rpartition('.')[0]
                receiver_scope = (self.name_key(self.lexical.get(node.value, self.owner[node.value]), node.value.id)[0]
                                  if isinstance(node.value, ast.Name) else None)
                receiver = self.defs.get(receiver_scope)
                receiver_class = self.owner.get(receiver)
                if (isinstance(node.value, ast.Name) and node.value.id in ('self', 'cls') and
                        isinstance(receiver, FUNCS) and isinstance(self.defs.get(receiver_class), ast.ClassDef)):
                    owners = [receiver_class]
                elif (isinstance(node.value, ast.Call) and isinstance(node.value.func, ast.Name)
                      and node.value.func.id == 'super' and not node.value.args and not node.value.keywords
                      and self.name_key(owner, 'super') == ('', 'super') and 'super' not in self.locals['']):
                    owners = self.base_names(parent)
                else:
                    target = self.definition_name(node.value, owner)
                    owners = [target] if isinstance(self.defs.get(target), ast.ClassDef) else []
                if isinstance(node.ctx, ast.Load):
                    self.receivers[statement].append((owners, node.attr))
                else:
                    writes.update((receiver, node.attr) for receiver in owners)
            elif isinstance(node, ast.Dict):
                # Literal metadata/registration keys may name bindings without
                # Name nodes (e.g. a field schema). Only resolved identifiers
                # create edges; no schema names or task-specific exceptions.
                for item in node.keys:
                    if isinstance(item, ast.Constant) and isinstance(item.value, str) and item.value.isidentifier():
                        uses.add(self.name_key(owner, item.value))
                        if isinstance(self.defs.get(owner), ast.ClassDef):
                            self.receivers[statement].append(([owner], item.value))
            elif isinstance(node, DEFS):
                writes.add((owner, node.name))
            elif isinstance(node, ast.arg):
                writes.add((owner, node.arg))
            elif isinstance(node, ast.ExceptHandler) and node.name:
                writes.add((owner, node.name))
            elif isinstance(node, (ast.Import, ast.ImportFrom)):
                writes.update((owner, a.asname or a.name.split('.')[0]) for a in node.names)
            for child in ast.iter_child_nodes(node):
                visit(child)
        visit(statement)
        return uses, writes

    def implementation(self, node):
        qual = '.'.join(filter(None, (self.owner[node], node.name)))
        return {self.index[n] for n in self.nodes if self.owner[n] == qual}

    def line_node(self, line):
        candidates = [n for n in self.nodes if min([n.lineno, *[d.lineno for d in getattr(n, 'decorator_list', [])]]) <= line <= n.end_lineno]
        return min(candidates, key=lambda n: (n.end_lineno - n.lineno, -n.col_offset)) if candidates else None

    def effect_dependencies(self, owner=None):
        """Local may-alias heap flow, without executing code or naming mutators.

        Every call may mutate its actual arguments/receiver. Reads depend on
        earlier effects on overlapping abstract objects; call-graph edges then
        supply the implementation. Assignments transfer aliases, fresh values
        separate rebindings, branches join and loops reach a finite fixed point.
        Attribute paths share their root object conservatively. This supplements
        lexical def/use, not a complete model of Python's dynamic heap semantics.
        """
        dependencies = defaultdict(set)

        def name(node):
            return self.name_key(self.lexical[node], node.id)

        def origins(state, key):
            return state[0].get(key, {('binding', key)})

        def merge(*states):
            aliases = {key: set().union(*(origins(state, key) for state in states))
                       for key in set().union(*(state[0] for state in states))}
            effects = {key: set().union(*(state[1].get(key, set()) for state in states))
                       for key in set().union(*(state[1] for state in states))}
            return aliases, effects

        def affect(objects, index, state):
            for obj in objects:
                state[1].setdefault(obj, set()).add(index)

        def expression(node, index, state):
            if node is None:
                return set()
            if isinstance(node, ast.Name):
                objects = origins(state, name(node))
                if isinstance(node.ctx, ast.Load):
                    dependencies[index].update(set().union(*(state[1].get(obj, set()) for obj in objects)))
                return objects
            if isinstance(node, ast.NamedExpr):
                objects = expression(node.value, index, state)
                assign(node.target, objects, index, state)
                return objects
            if isinstance(node, ast.IfExp):
                expression(node.test, index, state)
                left, right = merge(state), merge(state)
                objects = expression(node.body, index, left) | expression(node.orelse, index, right)
                aliases, effects = merge(left, right)
                state[0].update(aliases); state[1].update(effects)
                return objects
            if isinstance(node, ast.BoolOp):
                objects = set()
                for value in node.values:
                    branch = merge(state)
                    objects.update(expression(value, index, branch))
                    aliases, effects = merge(state, branch)
                    state[0].update(aliases); state[1].update(effects)
                return objects
            if isinstance(node, ast.Lambda):
                # Creating a closure evaluates defaults, not its deferred body.
                for value in [*node.args.defaults, *node.args.kw_defaults]:
                    expression(value, index, state)
                return {('value', node)}
            if isinstance(node, ast.Attribute):
                return expression(node.value, index, state)
            if isinstance(node, ast.Subscript):
                objects = expression(node.value, index, state)
                expression(node.slice, index, state)
                return objects
            if isinstance(node, ast.Call):
                receiver = expression(node.func, index, state)
                objects = set().union(*(expression(arg, index, state) for arg in
                                        [*node.args, *[kw.value for kw in node.keywords]]))
                if isinstance(node.func, ast.Attribute):
                    objects.update(receiver)
                affect(objects, index, state)
                # An opaque return may alias its inputs or be a fresh object.
                return objects | {('value', node)}
            fresh = {('value', node)} if isinstance(node, ast.expr) else set()
            return fresh | set().union(*(expression(child, index, state) for child in ast.iter_child_nodes(node)))

        def assign(target, objects, index, state):
            if isinstance(target, ast.Name):
                state[0][name(target)] = objects
            elif isinstance(target, (ast.Tuple, ast.List)):
                for item in target.elts:
                    assign(item, objects, index, state)
            elif isinstance(target, ast.Starred):
                assign(target.value, objects, index, state)
            else:
                affect(expression(target, index, state), index, state)

        def block(statements, state):
            for node in statements:
                index = self.index[node]
                if isinstance(node, DEFS):
                    values = [*node.decorator_list]
                    if isinstance(node, FUNCS):
                        values += [*node.args.defaults, *node.args.kw_defaults, node.returns]
                    else:
                        values += [*node.bases, *[kw.value for kw in node.keywords]]
                    for value in values:
                        expression(value, index, state)
                    state[0][(self.lexical[node], node.name)] = {('value', node)}
                elif isinstance(node, (ast.Assign, ast.AnnAssign)):
                    objects = expression(node.value, index, state)
                    for target in node.targets if isinstance(node, ast.Assign) else [node.target]:
                        if node.value is not None:
                            assign(target, objects, index, state)
                elif isinstance(node, ast.AugAssign):
                    objects = expression(node.target, index, state) | expression(node.value, index, state)
                    affect(objects, index, state)
                    assign(node.target, objects, index, state)
                elif isinstance(node, ast.If):
                    expression(node.test, index, state)
                    state = merge(block(node.body, merge(state)), block(node.orelse, merge(state)))
                elif isinstance(node, (ast.For, ast.AsyncFor, ast.While, ast.Try)):
                    # Monotone union includes zero iterations and exceptional
                    # paths. It may retain extra dependencies, never pick one
                    # branch or a fixed number of loop iterations as truth.
                    entry = merge(state)
                    while True:
                        iteration = merge(state)
                        if isinstance(node, (ast.For, ast.AsyncFor)):
                            assign(node.target, expression(node.iter, index, iteration), index, iteration)
                        elif isinstance(node, ast.While):
                            expression(node.test, index, iteration)
                        if isinstance(node, ast.Try):
                            # Any body prefix may precede a handler. Preserve
                            # intermediate aliases as well as the normal exit.
                            for statement in node.body:
                                iteration = merge(iteration, block([statement], merge(iteration)))
                            branches = [iteration]
                            for handler in node.handlers:
                                branch = merge(iteration)
                                expression(handler.type, index, branch)
                                branches.append(block(handler.body, branch))
                            iteration = merge(*branches)
                        else:
                            iteration = block(node.body, iteration)
                        joined = merge(entry, state, iteration)
                        if joined == state:
                            break
                        state = joined
                    state = merge(state, block(node.orelse, merge(state)))
                    if isinstance(node, ast.Try):
                        state = block(node.finalbody, state)
                elif isinstance(node, (ast.With, ast.AsyncWith)):
                    for item in node.items:
                        objects = expression(item.context_expr, index, state)
                        affect(objects, index, state)
                        if item.optional_vars is not None:
                            assign(item.optional_vars, objects, index, state)
                    state = block(node.body, state)
                else:
                    for child in ast.iter_child_nodes(node):
                        expression(child, index, state)
            return state

        for definition in [self.tree, *[node for node in self.nodes if isinstance(node, DEFS)]]:
            qual = ('.'.join(filter(None, (self.owner[definition], definition.name)))
                    if isinstance(definition, DEFS) else '')
            if owner is None or qual == owner:
                block(definition.body, ({}, {}))
        return dependencies

    def graph(self, version, dependency_targets=None):
        edges = defaultdict(set)
        for node in self.nodes:
            key = (version, self.index[node])
            for name in self.uses[node]:
                for i in self.binders[name]:
                    if dependency_targets is not None and i not in dependency_targets:
                        continue
                    edges[key].add((version, i))
                    provider = self.nodes[i]
                    # Referencing a function needs its implementation; using a
                    # parameter needs only its declaration, not the whole body.
                    if isinstance(provider, FUNCS) and name == (self.owner[provider], provider.name):
                        edges[key].update((version, j) for j in self.implementation(provider)
                                          if dependency_targets is None or j in dependency_targets)
            parent = self.parents.get(node)
            while parent is not None and not isinstance(parent, (ast.stmt, ast.Module)):
                parent = self.parents.get(parent)
            if isinstance(parent, ast.stmt) and not isinstance(parent, DEFS):
                edges[key].add((version, self.index[parent]))
        return edges


def dynamic_bindings(*trees):
    return any(isinstance(n, (ast.Nonlocal, ast.Global)) or
               isinstance(n, ast.ImportFrom) and any(a.name == '*' for a in n.names) or
               isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id in ('exec', 'eval')
               for tree in trees for n in ast.walk(tree))


def rebind_added_method(before, proposed, focus, old, new):
    """Normalize only if one version-bound observed owner satisfies the guards."""
    if not focus or focus.get('sha256') != scope.digest(before):
        return proposed, None
    owners = {}
    for observed in sorted({focus.get('root'), *focus.get('observed_roots', [])} - {None}):
        definition = old.defs.get(observed)
        owner = old.owner[definition] if isinstance(definition, FUNCS) else observed
        if observed not in old.ambiguous and isinstance(old.defs.get(owner), ast.ClassDef):
            owners.setdefault(owner, observed)
    supported = []
    for observed in owners.values():
        normalized, binding = _rebind_added_method(before, proposed, dict(focus, root=observed), old, new)
        if binding:
            supported.append((normalized, binding))
    return supported[0] if len(supported) == 1 else (proposed, None)


def _rebind_added_method(before, proposed, focus, old, new):
    """Return (normalized bytes, evidence), or abstain with None.

    Only a complete inserted method with an observed, compatible receiver is
    eligible. Existing method edits and ambiguous receiver types stay native.
    """
    observed = focus.get('root') if focus else None
    definition = old.defs.get(observed)
    target = old.owner[definition] if isinstance(definition, FUNCS) else observed
    definition = old.defs.get(target)
    if (not isinstance(definition, ast.ClassDef) or observed in old.ambiguous or target in old.ambiguous or
            focus.get('sha256') != scope.digest(before) or dynamic_bindings(old.tree)):
        return proposed, None
    a, b = before.splitlines(keepends=True), proposed.splitlines(keepends=True)
    first = definition.body[0]
    if first.lineno == definition.lineno:
        return proposed, None  # A one-line class has no reusable member indent.
    indent = a[first.lineno - 1][:first.col_offset]
    candidates = []
    for tag, i1, i2, j1, j2 in difflib.SequenceMatcher(None, a, b, autojunk=False).get_opcodes():
        if tag != 'insert':
            continue
        added = b''.join(b[j1:j2])
        try:
            fragment = Syntax(b'class _Insertion:\n' + added)
        except ValueError:
            continue
        tree = fragment.tree
        if len(tree.body) != 1 or not isinstance(tree.body[0], ast.ClassDef) or dynamic_bindings(tree):
            continue
        members = tree.body[0].body
        if len(members) != 1 or not isinstance(members[0], FUNCS):
            continue
        method = members[0]
        args = [*method.args.posonlyargs, *method.args.args]
        if (not args or args[0].arg not in ('self', 'cls') or
                any(isinstance(d, ast.Name) and d.id == 'staticmethod' for d in method.decorator_list)):
            continue
        if b[j1 + method.lineno - 2][:method.col_offset] != indent:
            continue  # Do not rewrite indentation inside multiline literals.
        if target + '.' + method.name in old.defs:
            continue
        receiver_key = ('_Insertion.' + method.name, args[0].arg)
        def bound_receiver(node):
            return isinstance(node, ast.Name) and fragment.name_key(fragment.lexical.get(node, fragment.owner[node]), node.id) == receiver_key
        if any(bound_receiver(n) and isinstance(n.ctx, (ast.Store, ast.Del)) for n in ast.walk(method)):
            continue
        attributes = {n.attr for n in ast.walk(method) if isinstance(n, ast.Attribute)
                      and isinstance(n.ctx, ast.Load) and isinstance(n.value, ast.Name)
                      and bound_receiver(n.value) and n.attr != method.name}
        known = lambda syntax, owner, name: any(syntax.binders.get(k) for k in syntax.receiver_keys(owner, name))
        if not attributes or not all(known(old, target, name) for name in attributes):
            continue
        actual, spill = None, False
        if new is not None:
            if dynamic_bindings(new.tree):
                continue
            matches = [n for n in new.nodes if type(n) is type(method) and
                       n.lineno == j1 + method.lineno - 1 and n.name == method.name]
            if len(matches) != 1:
                continue
            concrete = matches[0]
            spill = concrete.end_lineno > j2 or any(d.lineno <= j1 for d in concrete.decorator_list)
            if not spill and ast.dump(concrete) != ast.dump(method):
                continue
            actual = new.owner[concrete]
            if (actual == target and not spill) or not isinstance(new.defs.get(actual), ast.ClassDef):
                continue
            if new.owner[new.defs[actual]] != old.owner[definition]:
                continue  # Moving between lexical scopes could rebind free names.
            if actual != target and all(known(new, actual, name) for name in attributes):
                continue
            owners, pending = set(), [actual]
            opaque = False
            while pending:
                owner = pending.pop()
                if owner in owners:
                    continue
                owners.add(owner)
                cls = new.defs[owner]
                for base in cls.bases:
                    name = new.definition_name(base, new.owner[cls])
                    if name == 'object':
                        continue
                    if not isinstance(new.defs.get(name), ast.ClassDef):
                        opaque = True
                    else:
                        pending.append(name)
            if opaque or any(known(new, actual, name) for name in ('__getattr__', '__getattribute__')):
                continue
        elif old.owner[definition]:
            continue  # An invalid fragment cannot establish an enclosing closure.
        candidates.append((i1, j1, j2, method, attributes, actual, spill))
    if len(candidates) != 1:
        return proposed, None
    i1, j1, j2, method, attributes, actual, spill = candidates[0]
    remaining = b[:j1] + b[j2:]
    try:
        residual = Syntax(b''.join(remaining))
    except ValueError:
        return proposed, None
    if dynamic_bindings(residual.tree):
        return proposed, None
    cls = residual.defs.get(target)
    if not isinstance(cls, ast.ClassDef) or target + '.' + method.name in residual.defs:
        return proposed, None
    old_calls = {(old.owner[n], ast.dump(n)) for n in ast.walk(old.tree) if isinstance(n, ast.Call)}
    for call in (n for n in ast.walk(residual.tree) if isinstance(n, ast.Call)):
        if (residual.owner[call], ast.dump(call)) in old_calls:
            continue
        if isinstance(call.func, ast.Name) and call.func.id == method.name:
            return proposed, None
        if isinstance(call.func, ast.Attribute) and call.func.attr == method.name:
            owner = residual.owner[call]
            while owner and not isinstance(residual.defs.get(owner), ast.ClassDef):
                owner = owner.rpartition('.')[0]
            receiver = call.func.value
            local = isinstance(receiver, ast.Name) and receiver.id in ('self', 'cls') and owner == target
            named = residual.definition_name(receiver, residual.owner[call]) == target
            if not (local or named):
                return proposed, None
    inserted = b[j1:j2]
    if remaining[cls.end_lineno - 1] and not remaining[cls.end_lineno - 1].endswith((b'\n', b'\r')):
        return proposed, None
    normalized = b''.join(remaining[:cls.end_lineno] + [b'\n'] + inserted + remaining[cls.end_lineno:])
    try:
        check = Syntax(normalized)
    except ValueError:
        return proposed, None
    checked = check.defs.get(target + '.' + method.name)
    if checked is None or ast.dump(checked) != ast.dump(method):
        return proposed, None
    return normalized, dict(method=method.name, observed_root=observed, observed_owner=target, proposed_owner=actual,
                            receiver_attributes=sorted(attributes), scope_spill=spill,
                            normalized_span=[cls.end_lineno, cls.end_lineno + 1 + len(inserted)],
                            observed_sha256=focus['sha256'])


def project(before, proposed, focus):
    """Return accepted bytes + internal facts; unchanged output on abstention."""
    if before == proposed:
        return proposed, {'status': 'unchanged'}
    old = Syntax(before)
    try:
        new = Syntax(proposed)
    except ValueError:
        new = None
    if not focus or focus.get('sha256') != scope.digest(before) or focus.get('root') not in old.defs:
        return proposed, {'status': 'abstained', 'reason': 'missing_or_stale_focus'}
    normalized, binding = rebind_added_method(before, proposed, focus, old, new)
    if binding:
        new = Syntax(normalized)
    if new is None:
        return proposed, {'status': 'abstained', 'reason': 'invalid_proposal'}
    if focus['root'] not in new.defs:
        # A deleted/renamed observation no longer identifies the replacement
        # implementation. Its former callers alone cannot establish new intent.
        return proposed, {'status': 'abstained', 'reason': 'retired_observation'}
    accepted, facts = slice_changes(before, normalized, focus, old, new, binding)
    # A supported intervention must leave a nonempty, valid repair. Otherwise
    # preserve the native proposal and its diagnostic/recovery path.
    if facts['status'] == 'abstained' or accepted == before:
        return proposed, facts if facts['status'] == 'abstained' else dict(status='abstained', reason='empty_projection')
    if binding:
        facts.update(status='projected', binding=binding, proposed_sha256=scope.digest(proposed),
                     accepted_sha256=scope.digest(accepted))
    return accepted, facts


def slice_changes(before, proposed, focus, old, new, binding=None):
    """Select supported diff units using already parsed source versions."""
    root = focus['root']
    duplicates = new.ambiguous - old.ambiguous
    selected = {root, *focus.get('anchors', {})}
    if duplicates or any(q == a or q.startswith(a + '.') for q in selected for a in old.ambiguous):
        return proposed, dict(status='abstained', reason='ambiguous_identity')
    if dynamic_bindings(old.tree, new.tree):
        return proposed, {'status': 'abstained', 'reason': 'dynamic_or_nonlocal_binding'}
    a, b = before.splitlines(keepends=True), proposed.splitlines(keepends=True)
    changes = []
    ranges = [(0, len(a), 0, len(b))]
    if binding:
        # Keep a normalized payload as its own insertion unit. Re-diffing it
        # without this origin boundary can merge a neighbouring, unrelated edit
        # into the supported method merely because their lines are adjacent.
        old_end = old.defs[binding['observed_owner']].end_lineno
        start, end = binding['normalized_span']
        ranges = [(0, old_end, 0, start), (old_end, old_end, start, end),
                  (old_end, len(a), end, len(b))]
    opcodes = [(tag, i1 + x1, i2 + x1, j1 + y1, j2 + y1)
               for x1, x2, y1, y2 in ranges
               for tag, i1, i2, j1, j2 in difflib.SequenceMatcher(None, a[x1:x2], b[y1:y2], autojunk=False).get_opcodes()]
    for tag, i1, i2, j1, j2 in opcodes:
        if tag == 'equal':
            continue
        if i2 - i1 == j2 - j1:
            # Text diff merges adjacent edits. Split aligned lines, then use AST
            # statement membership below to reunite syntactically coupled edits.
            changes.extend((tag, i, i + 1, j1 + i - i1, j1 + i - i1 + 1) for i in range(i1, i2))
        else:
            changes.append((tag, i1, i2, j1, j2))
    # Removed references do not license edits to their former providers. They
    # may still connect a wholly deleted provider needed for coordinated cleanup.
    deleted = {i for _, i1, i2, j1, j2 in changes if j1 == j2
               for i, node in enumerate(old.nodes)
               if min([node.lineno, *[d.lineno for d in getattr(node, 'decorator_list', [])]]) > i1
               and node.end_lineno <= i2}
    # A removed use can still require a changed binding's construction, e.g.
    # replacing explicit object mutations with a decorator. Do not expand old
    # implementation bodies merely because a now-replaced call used them.
    reconstructed = {old.index[old.defs[name]] for name in old.defs.keys() & new.defs.keys()
                     if definition_header(old.defs[name]) != definition_header(new.defs[name])}
    edges = old.graph(0, deleted | reconstructed)
    for key, deps in new.graph(1).items():
        edges[key].update(deps)
    # Exact unchanged statements bridge versions; definition identities bridge
    # changed bodies without relying on unstable line positions.
    identities = []
    for syntax in (old, new):
        found = defaultdict(list)
        for i, node in enumerate(syntax.nodes):
            name = (syntax.owner[node], type(node).__name__, node.name if isinstance(node, DEFS) else ast.dump(node))
            found[name].append(i)
        identities.append(found)
    for name in identities[0].keys() & identities[1].keys():
        left, right = identities[0][name], identities[1][name]
        if len(left) == len(right) == 1:
            x, y = (0, left[0]), (1, right[0])
            edges[x].add(y); edges[y].add(x)
    units = []
    for _, i1, i2, j1, j2 in changes:
        nodes = set()
        for version, syntax, lines, start, end in [(0, old, a, i1, i2), (1, new, b, j1, j2)]:
            for line in range(start, end):
                if lines[line].strip() and (node := syntax.line_node(line + 1)) is not None:
                    nodes.add((version, syntax.index[node]))
        units.append(nodes)
        for node in nodes:
            edges[node].update(nodes)
    # Index dependencies in reverse as well. Changed consumers and providers
    # form one repair group even through unchanged aliases/intermediary calls.
    # Unchanged nodes only carry the relation; they are not new edit anchors.
    changed_nodes = set().union(*units)
    consumers = defaultdict(set)
    for consumer, providers in edges.items():
        for provider in providers:
            consumers[provider].add(consumer)
    seeds = set()
    # A guarded relocation supports exactly its inserted member. It does not
    # widen the original observation to every member of the receiver class.
    if binding:
        member = new.defs[binding['observed_owner'] + '.' + binding['method']]
        seeds.add((1, new.index[member]))
        seeds.update((1, i) for i in new.implementation(member))
    root = focus['root']
    anchors = focus.get('anchors', {})
    if anchors:
        observed_methods = {q for q, locations in anchors.items() if locations is None}
        focused_changes = set()
        for version, index in changed_nodes:
            syntax = (old, new)[version]
            node = syntax.nodes[index]
            qual = '.'.join(filter(None, (syntax.owner[node], node.name))) if isinstance(node, DEFS) else syntax.owner[node]
            if any(qual == q or qual.startswith(q + '.') for q in observed_methods):
                focused_changes.add((version, index))
        seeds.update(focused_changes)
        for qual, locations in anchors.items():
            if qual not in old.defs:
                continue
            if locations is None:
                if not focused_changes:
                    seeds.add((0, old.index[old.defs[qual]]))
                    seeds.update((0, i) for i in old.implementation(old.defs[qual]))
            else:
                seeds.update((0, old.index[n]) for line in locations if (n := old.line_node(line)) is not None)
    else:
        # A class-only query carries owner evidence, not a dependency edge that
        # licenses its siblings/base classes. Finer subsequent queries narrow it.
        for nodes in units:
            for version, index in nodes:
                syntax = (old, new)[version]
                node = syntax.nodes[index]
                owner = syntax.owner[node]
                qual = '.'.join(filter(None, (owner, node.name))) if isinstance(node, DEFS) else owner
                if qual == root or qual.startswith(root + '.'):
                    seeds.add((version, index))
    # New direct members are insertion units, not nonexistent old line spans.
    if isinstance(old.defs[root], ast.ClassDef):
        for qual in new.defs.keys() - old.defs.keys():
            if qual.rpartition('.')[0] == root:
                seeds.add((1, new.index[new.defs[qual]]))
                seeds.update((1, i) for i in new.implementation(new.defs[qual]))
    visited, queue = set(seeds), deque(seeds)
    effect_scopes = set()
    reverse_seen = set()
    while queue:
        current = queue.popleft()
        version, index = current
        syntax = (old, new)[version]
        owner = syntax.owner[syntax.nodes[index]]
        # Expand effects only when the closure reaches their lexical body.
        # Each scope's whole transfer is still calculated, with identical may
        # edges. Deleted-only old dependencies need no analysis if none exist.
        if (version, owner) not in effect_scopes and (version == 1 or deleted):
            effect_scopes.add((version, owner))
            for consumer, providers in syntax.effect_dependencies(owner).items():
                edges[(version, consumer)].update((version, provider) for provider in providers
                                                  if provider != consumer and (version == 1 or provider in deleted))
        related = set(edges[current])
        if current in changed_nodes:
            pending = deque(consumers[current])
            while pending:
                consumer = pending.popleft()
                if consumer in reverse_seen:
                    continue
                reverse_seen.add(consumer)
                if consumer in changed_nodes:
                    related.add(consumer)
                else:
                    pending.extend(consumers[consumer])
        for child in related - visited:
            visited.add(child); queue.append(child)
    keep = [bool(nodes & visited) for nodes in units]
    if not any(keep):
        # Search is evidence, not proof of intent. With no supported changed
        # anchor, preserve the proposal, including additions under other owners.
        return proposed, dict(status='abstained', reason='no_changed_anchor')
    # Whitespace-only changes are not independently classified as bad edits.
    def documentation_only(nodes):
        return bool(nodes) and all(isinstance((old, new)[v].nodes[i], ast.Expr) and
            isinstance((old, new)[v].nodes[i].value, ast.Constant) and
            isinstance((old, new)[v].nodes[i].value.value, str) for v, i in nodes)
    keep = [value or not nodes or documentation_only(nodes) for value, nodes in zip(keep, units)]
    result = list(a)
    for change, retain in reversed(list(zip(changes, keep))):
        _, i1, i2, j1, j2 = change
        if retain:
            result[i1:i2] = b[j1:j2]
    result = b''.join(result)
    try:
        Syntax(result)
    except ValueError:
        return proposed, {'status': 'abstained', 'reason': 'invalid_projection'}
    return result, dict(status='accepted' if result == proposed else 'restored' if result == before else 'projected',
                        kept=sum(keep), dropped=len(keep)-sum(keep), root=root,
                        anchors=anchors, proposed_sha256=scope.digest(proposed), accepted_sha256=scope.digest(result))


def state_location():
    root, _ = scope.location()
    directory = Path(scope.bound_git(root, 'rev-parse', '--absolute-git-dir').decode().strip()) / 'aci-edit-filter'
    directory.mkdir(exist_ok=True)
    return root, directory


def observation_blocks(rendered):
    blocks = defaultdict(str)
    filename = None
    for line in rendered.splitlines():
        if match := re.search(r'<file>(.*?)</file>', line):
            filename = match[1]
        elif filename:
            blocks[filename] += line + '\n'
    return blocks


def observation_path(directory, identity):
    if not re.fullmatch(r'[0-9a-f]{32}', identity):
        raise ValueError('invalid observation identity')
    return directory / ('observation-' + identity + '.jsonl')


def confirm_observations(directory, receipt):
    """Confirm complete G evidence in an actual, later native observation."""
    path = observation_path(directory, receipt['identity'])
    if not path.exists():
        return
    for line in path.read_text().splitlines():
        event = json.loads(line)
        if not event['rendered'] or not any(event['rendered'] in text for text in receipt['contents']):
            continue
        if any(not Path(p).is_file() or scope.digest(Path(p).read_bytes()) != revision
               for p, revision in event['versions'].items()):
            continue
        # Reuse G's captured path identities, not another path/search resolver.
        paths = event['paths']
        repo = SimpleNamespace(abspath=lambda p: paths[p]['absolute'],
                               rel=lambda p: paths[p]['relative'],
                               display=lambda p: paths[p]['display'])
        try:
            record_observation(repo, event['names'], event['candidates'], event['records'],
                               event['rendered'], _confirmed=True)
        except InvalidSource as exc:
            # An unsupported query grants no evidence. Later queries and the
            # next edit's snapshot must still run, including syntax repairs.
            log(directory, dict(status='abstained', reason='invalid_observation', detail=str(exc)))
    path.unlink()


def record_observation(repo, names, candidates, records, rendered, *, _confirmed=False):
    """Direct observers consume G output; mini must first confirm final visibility."""
    root, directory = state_location()
    blocks = observation_blocks(rendered)
    identity = os.environ.get('ACI_EDIT_OBSERVATION_ID')
    if identity and not _confirmed:
        # Preserve hidden matched definitions because they constrain ambiguity;
        # other hidden match rows and context cannot supply observation evidence.
        definitions = {(d['abs'], d['line']) for d in candidates}
        records = [(filename, line, matched, '') for filename, line, matched, _ in records
                   if matched and ((repo.abspath(filename), line) in definitions or
                                   re.search(rf'^{line}:', blocks.get(repo.display(filename), ''), re.M))]
        filenames = {d['path'] for d in candidates} | {r[0] for r in records}
        paths = {p: dict(absolute=repo.abspath(p), relative=repo.rel(p), display=repo.display(p))
                 for p in filenames}
        visible = {v['absolute'] for v in paths.values() if v['display'] in blocks}
        visible.update(d['abs'] for d in candidates if
                       f"[definition] {d['kind']} {d['qual']} {d['path']}:{d['start']}-{d['end']}" in rendered)
        versions = {p: scope.digest(Path(p).read_bytes()) for p in visible if p.endswith('.py')}
        with observation_path(directory, identity).open('a') as stream:
            stream.write(json.dumps(dict(names=names, candidates=candidates, records=records,
                                         rendered=rendered, paths=paths, versions=versions)) + '\n')
        return
    path = directory / 'focus.json'
    state = json.loads(path.read_text()) if path.exists() else {}
    previous = {relative: dict(focus) for relative, focus in state.items()}
    observed = defaultdict(set)

    def remember(relative, raw, qual):
        observed[relative].add((scope.digest(raw), qual))

    visible_files = set(blocks)
    visible = [d for d in candidates if
               f"[{d['kind']} {d['qual']}, lines {d['start']}-{d['end']}" in blocks.get(d['path'], '') or
               f"[definition] {d['kind']} {d['qual']} {d['path']}:{d['start']}-{d['end']}" in rendered]
    direct = {(repo.abspath(filename), line) for filename, line, matched, _ in records if matched}
    for name in dict.fromkeys(n for _, n, _ in names):
        alternatives = [d for d in candidates if d['name'] == name]
        matched_definitions = [d for d in alternatives if (d['abs'], d['line']) in direct]
        alternatives = matched_definitions or alternatives
        choices = [d for d in visible if d in alternatives]
        classes = [d for d in choices if d['kind'] == 'class']
        if len(classes) == 1 and sum(d['kind'] == 'class' for d in alternatives) == 1:
            d = classes[0]
            relative = repo.rel(d['path'])
            raw = Path(repo.abspath(d['path'])).read_bytes()
            syntax = Syntax(raw)
            if d['qual'] in syntax.defs and d['qual'] not in syntax.ambiguous:
                state[relative] = dict(root=d['qual'], sha256=scope.digest(raw), anchors={})
                remember(relative, raw, d['qual'])
        else:
            for d in choices:
                relative = repo.rel(d['path'])
                raw = Path(repo.abspath(d['path'])).read_bytes()
                focus = state.get(relative)
                if focus and focus['sha256'] != scope.digest(raw):
                    focus = None
                if focus and focus.get('root') and (d['qual'] == focus['root'] or d['qual'].startswith(focus['root'] + '.')):
                    focus['anchors'][d['qual']] = None
                    remember(relative, raw, d['qual'])
                elif len(alternatives) == 1:
                    state[relative] = dict(root=d['qual'], sha256=scope.digest(raw), anchors={d['qual']: None})
                    remember(relative, raw, d['qual'])
                elif not focus or not focus.get('root'):
                    # Keep ambiguity as constraints, not edit permission. A later
                    # observed member can identify which receiver class was read.
                    if not focus:
                        focus = state[relative] = dict(root=None, sha256=scope.digest(raw), anchors={}, candidates={})
                    focus.setdefault('candidates', {}).setdefault(name, [])
                    if d['qual'] not in focus['candidates'][name]:
                        focus['candidates'][name].append(d['qual'])
    # A syntactic identifier is only a definition-lookup hint. Without any
    # candidate, an unprefixed query can still expose a local value/statement.
    # Explicit definition searches and hidden/ambiguous candidates retain the
    # definition rules above. Match rows stay distinct from extra context rows.
    if not names or (not candidates and not any(prefix for prefix, _, _ in names)):
        per_file = defaultdict(list)
        for filename, line, match, text in records:
            if repo.display(filename) not in visible_files:
                continue
            if match and re.search(rf'^{line}:', blocks[repo.display(filename)], re.M):
                per_file[filename].append(line)
        for filename, lines in per_file.items():
            if not filename.endswith('.py') or not lines:
                continue
            raw = Path(repo.abspath(filename)).read_bytes()
            syntax = Syntax(raw)
            functions = {syntax.owner[n] for line in lines if (n := syntax.line_node(line)) is not None}
            functions = {q for q in functions if isinstance(syntax.defs.get(q), FUNCS)}
            if len(functions) == 1:
                qual = next(iter(functions)); relative = repo.rel(filename)
                remember(relative, raw, qual)
                prior = state.get(relative, {})
                parent = qual.rpartition('.')[0]
                if prior.get('sha256') == scope.digest(raw) and isinstance(syntax.defs.get(parent), ast.ClassDef):
                    candidates = prior.get('candidates', {})
                    resolved = {q: None for values in candidates.values() for q in values if q.rpartition('.')[0] == parent}
                    if prior.get('root') == parent or resolved:
                        prior.update(root=parent, anchors={**prior.get('anchors', {}), **resolved, qual: lines})
                        prior.pop('candidates', None)
                        continue
                state[relative] = dict(root=qual, sha256=scope.digest(raw), anchors={qual: lines})
    for relative, focus in state.items():
        roots = {qual for revision, qual in observed[relative] if revision == focus['sha256']}
        prior = previous.get(relative, {})
        if prior.get('sha256') == focus['sha256']:
            roots.update(prior.get('observed_roots', []))
            roots.add(prior.get('root'))
        roots.add(focus.get('root'))
        focus['observed_roots'] = sorted(roots - {None})
    scope.save(path, state)


def pending_path(directory):
    return directory / ('pending-' + str(int(os.environ['ACI_EDIT_REPORT_PID'])) + '.json')


def rebase_focus(before, accepted, focus):
    """Rebase known accepted edits only; an external/stale change never rebases."""
    syntax = Syntax(accepted)
    if focus.get('root') not in syntax.defs or focus['root'] in syntax.ambiguous:
        return None
    anchors = {}
    ops = difflib.SequenceMatcher(None, before.splitlines(), accepted.splitlines(), autojunk=False).get_opcodes()
    for name, locations in focus.get('anchors', {}).items():
        if name not in syntax.defs:
            return None
        if locations is None:
            anchors[name] = None
            continue
        updated = []
        for line in locations:
            for _, i1, i2, j1, j2 in ops:
                if i1 <= line - 1 < i2 and j2 > j1:
                    target = j1 + min(line - 1 - i1, j2 - j1 - 1) + 1
                    node = syntax.line_node(target)
                    if node is None or syntax.owner[node] != name:
                        return None
                    updated.append(target)
                    break
            else:
                return None
        anchors[name] = updated
    return dict(root=focus['root'], sha256=scope.digest(accepted), anchors=anchors,
                observed_roots=sorted(q for q in focus.get('observed_roots', [focus['root']])
                                      if q in syntax.defs and q not in syntax.ambiguous),
                observed_sha256=focus.get('observed_sha256', focus['sha256']))


def log(directory, record):
    with (directory / 'decisions.jsonl').open('a') as stream:
        stream.write(json.dumps(record, ensure_ascii=False) + '\n')


def begin():
    root, directory = state_location()
    for path in sorted(directory.glob('pending-*.json')):
        pending = json.loads(path.read_text())
        alive = scope.process_marker(path.stem.split('-')[-1])
        if alive is None or alive != pending['owner_start']:
            finish(path)
    if receipt := os.environ.get('ACI_EDIT_VISIBLE'):
        confirm_observations(directory, json.loads(receipt))
    head = scope.bound_git(root, 'rev-parse', 'HEAD').decode().strip()
    records = {}
    for relative in scope.python_changes(root, head):
        if subprocess.run(['git', 'cat-file', '-e', f'{head}:{relative}'], cwd=root, capture_output=True).returncode == 0:
            records[relative] = scope.bound_record(root / relative)
    scope.save(pending_path(directory), dict(head=head, files=records,
               owner_start=scope.process_marker(os.environ['ACI_EDIT_REPORT_PID'])))


def finish(snapshot=None):
    root, directory = state_location()
    snapshot = snapshot or pending_path(directory)
    if not snapshot.exists():
        return
    pending = json.loads(snapshot.read_text())
    focus_path = directory / 'focus.json'
    foci = json.loads(focus_path.read_text()) if focus_path.exists() else {}
    changed = []
    for relative in sorted(set(pending['files']) | set(scope.python_changes(root, pending['head']))):
        prior = pending['files'].get(relative)
        if prior is None:
            try:
                before = scope.bound_git(root, 'show', f"{pending['head']}:{relative}")
                mode = int(scope.bound_git(root, 'ls-tree', pending['head'], '--', relative).split()[0], 8) & 0o777
            except subprocess.CalledProcessError:
                continue  # New files are outside first-version writeback coverage.
        else:
            if prior['source'] is None:
                continue
            before = base64.b64decode(prior['source']); mode = prior['mode']
        path = root / relative
        if not path.is_file() or path.resolve() != path:
            log(directory, dict(path=relative, status='abstained', reason='deleted_or_changed_path_type'))
            continue
        proposed = path.read_bytes()
        if proposed == before:
            continue
        try:
            accepted, facts = project(before, proposed, foci.get(relative))
        except ValueError as exc:
            accepted, facts = proposed, dict(status='abstained', reason='invalid_before', detail=str(exc))
        changed.append((relative, before, proposed, accepted, mode, facts))
    for relative, before, proposed, accepted, mode, facts in changed:
        path = root / relative
        if accepted != proposed:
            # Human-review evidence only; exact byte identities remain hashes.
            # Kept out of model observations and collected after the run.
            facts['projection_diff'] = ''.join(difflib.unified_diff(
                proposed.decode('utf-8', errors='backslashreplace').splitlines(keepends=True),
                accepted.decode('utf-8', errors='backslashreplace').splitlines(keepends=True),
                fromfile=relative + ' (proposed)', tofile=relative + ' (accepted)'))
            recovery = directory / 'proposals' / (scope.digest(proposed) + '.py')
            recovery.parent.mkdir(exist_ok=True)
            recovery.write_bytes(proposed)
            if path.read_bytes() != proposed:
                log(directory, dict(path=relative, status='abstained', reason='concurrent_writer'))
                continue
            fd, temporary = tempfile.mkstemp(prefix='.aci-edit-', dir=path.parent)
            try:
                with os.fdopen(fd, 'wb') as stream:
                    stream.write(accepted)
                os.chmod(temporary, mode)
                os.replace(temporary, path)
            finally:
                Path(temporary).unlink(missing_ok=True)
        if relative in foci and foci[relative]['sha256'] == scope.digest(before) and accepted != before:
            try:
                rebased = rebase_focus(before, accepted, foci[relative])
            except ValueError:
                rebased = None
            if rebased:
                foci[relative] = rebased
            else:
                foci.pop(relative)
        log(directory, dict(path=relative, **facts) | dict(
            before_sha256=scope.digest(before), proposed_sha256=scope.digest(proposed),
            accepted_sha256=scope.digest(accepted)))
    scope.save(focus_path, foci)
    snapshot.unlink()


def main():
    try:
        if sys.argv[1:] == ['--checkpoint']:
            finish()
            begin()
        else:
            finish() if sys.argv[1:] == ['--finish'] else begin()
    except Exception as exc:
        # Instrumentation must not change native command output/status. Preserve
        # failed pending state for the next recovery attempt and record coverage.
        try:
            _, directory = state_location()
            log(directory, dict(status='error', error=type(exc).__name__, detail=str(exc)))
        except Exception:
            pass


if __name__ == '__main__':
    main()
