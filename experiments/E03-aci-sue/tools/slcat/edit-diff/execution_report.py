"""Optional current-source execution facts for V; no test selection or oracle."""
import ast
import difflib
import hashlib
import subprocess
from pathlib import Path


def locations(before, after):
    """Current-side changed statement starts and edited conditional headers.

    Candidate locations are later filtered by the repository interpreter's actual
    bytecode line table. Deletion effects have no invented current-side anchor.
    """
    changed=set()
    for tag,_,_,start,end in difflib.SequenceMatcher(None,before.splitlines(),after.splitlines(),autojunk=False).get_opcodes():
        if tag!='equal':changed.update(range(start+1,end+1))
    tree=ast.parse(after);statements=set();branches=[]
    for node in ast.walk(tree):
        if not isinstance(node,ast.stmt):continue
        end=node.test.end_lineno if isinstance(node,ast.If) else node.end_lineno
        header=isinstance(node,ast.If)
        if not header and hasattr(node,'body'):continue
        if not changed.intersection(range(node.lineno,end+1)):continue
        statements.add(node.lineno)
        if header:
            branches.append(dict(condition_line=node.lineno,
                condition=' '.join((ast.get_source_segment(after,node.test) or '').split()),
                true_line=node.body[0].lineno,
                false_line=node.orelse[0].lineno if node.orelse else None))
    return dict(statements=sorted(statements),branches=branches)


def capture(sources):
    files={};unavailable={}
    for path in sources:
        if not path.endswith('.py'):
            unavailable[path]='non-Python source';continue
        original=subprocess.run(['git','show','HEAD:'+path],capture_output=True)
        if original.returncode:
            unavailable[path]='base source unavailable';continue
        try:
            raw=Path(path).read_bytes()
            sites=locations(original.stdout.decode('utf-8'),raw.decode('utf-8'))
            files[path]=dict(sites,sha256=hashlib.sha256(raw).hexdigest())
        except (OSError,UnicodeError,SyntaxError) as e:unavailable[path]=type(e).__name__
    return dict(files=files,unavailable=unavailable)


def configuration(plan, root):
    lines={}
    for path,record in plan['files'].items():
        ns=set(record['statements'])
        for branch in record['branches']:
            ns.update(branch[k] for k in ['condition_line','true_line','false_line'] if branch[k] is not None)
        if ns:lines[path]=sorted(ns)
    return dict(root=str(root),files=list(lines),lines=lines,
                source_hashes={p:plan['files'][p]['sha256'] for p in lines})


def summarize(plan, profile, result):
    facts=[];missing=[]
    states=result['status']
    reason=('run_incomplete' if result['outcome'] not in ('passed','failed')
            else 'no_recognized_tests' if not states
            else 'test_attribution_missing' if any(t not in profile.get('context_files',{}) for t in states)
            else None)
    config=configuration(plan,Path.cwd())
    if not config['files']:
        reason='source_unavailable' if plan['unavailable'] else 'no_current_statement_sites'
    if reason:
        return dict(state='unverified',reason=reason,facts=[],unavailable=plan['unavailable'])
    expected=config['source_hashes']
    if any(profile.get(key)!=expected for key in ['source_hashes_before','source_hashes_after']):
        return dict(state='unverified',reason='source_changed_or_unverified',facts=[],unavailable=plan['unavailable'])
    contexts=profile.get('contexts',{});shared=contexts.get('__shared_setup__',{})
    for path,record in plan['files'].items():
        if path not in config['files']:continue
        compiled=profile.get('executable_lines',{}).get(path)
        if compiled is None:
            missing.append(path);continue
        compiled=set(compiled);tested=set()
        for test in states:tested.update(contexts.get(test,{}).get(path,[]))
        def observed(line):
            if line not in compiled:return 'unobservable'
            return 'test' if line in tested else 'shared_only' if line in shared.get(path,[]) else 'unobserved'
        for line in record['statements']:
            if line in compiled:facts.append(dict(path=path,line=line,kind='statement',observed=observed(line)))
        for branch in record['branches']:
            facts.append(dict(path=path,line=branch['condition_line'],kind='condition',condition=branch['condition'],
                observed=observed(branch['condition_line']),true_line=branch['true_line'],true_observed=observed(branch['true_line']),
                false_line=branch['false_line'],false_observed=observed(branch['false_line']) if branch['false_line'] is not None else None))
    unavailable=dict(plan['unavailable'],**{p:'bytecode locations unavailable' for p in missing})
    if missing and not facts:
        return dict(state='unverified',reason='bytecode_locations_unavailable',facts=[],unavailable=unavailable)
    return dict(state='observed',facts=facts,unavailable=unavailable)


def lines(record):
    if record['state']!='observed':
        return ['[changed code] execution unverified: '+record['reason']]
    statements=[f for f in record['facts'] if f['kind']=='statement']
    unobserved=sum(f['observed']=='unobserved' for f in statements)
    shared=sum(f['observed']=='shared_only' for f in statements)
    output=[f"[changed code] {len(statements)} current statement locations; {unobserved} not observed; {shared} shared setup only; not a correctness check"]
    if record['unavailable']:
        output.append(f"[changed code] {len(record['unavailable'])} source files unavailable; see evidence")
    conditions={(f['path'],f['line']) for f in record['facts'] if f['kind']=='condition'}
    for fact in sorted(record['facts'],key=lambda f:f['kind']!='condition'):
        if fact['kind']=='condition':
            output.append(f"[condition] {fact['path']}:{fact['line']} condition={fact['observed']}; "
                          f"true entry {fact['true_line']}={fact['true_observed']}; "
                          f"false entry {fact['false_line']}={fact['false_observed']}; {fact['condition']}")
        elif fact['observed']!='test' and (fact['path'],fact['line']) not in conditions:
            output.append(f"[changed statement] {fact['path']}:{fact['line']} {fact['observed']}")
    return output
