"""Opt-in, source-only relation observations after edits; no generated tests.

HEAD is the base version, not the previous command: a relation may emerge over
several edits. The shell hook already limits invocation to tracked changes.
"""
import os
import subprocess
from pathlib import Path

import change_relations


def report(entries, budget):
    candidates = []
    for path, deleted, _ in entries:
        if deleted or not path.endswith('.py'):
            continue
        base = subprocess.run(['git', 'show', 'HEAD:' + path], capture_output=True)
        if base.returncode:
            continue
        try:
            before = base.stdout.decode('utf-8')
            after = Path(path).read_text(encoding='utf-8')
        except (OSError, UnicodeError):
            continue
        candidates.extend(change_relations.analyze(path, before, after)['candidates'])
    candidates.sort(key=lambda r: (-r['score'], -r['composite_reads'], r['path'], r['line'], r['target']))
    if budget < 150:
        return ''
    text, _ = change_relations.render(candidates, budget)
    return text.rstrip('\n')
