"""Optional public-test retrieval from the issue and/or original definitions.

terms/lexical_pool reuse the CPU evidence implementation (issue_code_view.py,
test_adequacy.py). Query choices reuse the public issue and declared HEAD
definitions; candidate patch text never supplies the query.
No issue-specific rules, execution profiles, hidden labels or model calls.
"""
from collections import Counter
import hashlib
import json
import math
from pathlib import Path
import re
import subprocess

import edit_scope


def terms(text):
    result = []
    for word in re.findall(r'[A-Za-z_][A-Za-z_0-9]*', text):
        pieces = re.sub(r'([a-z0-9])([A-Z])', r'\1 \2', word).replace('_', ' ').lower().split()
        result.extend(dict.fromkeys([word.lower(), *pieces]))
    return result


def lexical_pool(root, test_files, issue, changed_source, limit=8):
    docs = {}
    for path in test_files:
        try:
            docs[path] = Counter(terms(path + '\n' + (root / path).read_text(errors='replace')))
        except OSError:
            continue
    frequency = Counter(t for d in docs.values() for t in d)
    idf = {t: 1 + math.log((len(docs) + 1) / (n + 1)) for t, n in frequency.items()}
    query = {t: math.log1p(n) * idf[t] for t, n in Counter(terms(issue + '\n' + changed_source)).items() if t in idf}
    qnorm = math.sqrt(sum(v * v for v in query.values()))
    scored = []
    for path, d in docs.items():
        vector = {t: math.log1p(n) * idf[t] for t, n in d.items()}
        norm = math.sqrt(sum(v * v for v in vector.values()))
        score = sum(v * query.get(t, 0) for t, v in vector.items()) / (qnorm * norm) if qnorm and norm else 0
        if score:
            scored.append(dict(path=path, score=score))
    return sorted(scored, key=lambda r: (-r['score'], r['path']))[:limit]


def select(sources, test_files, limit, context='scope'):
    """Return files + provenance, or a reason for the unchanged native fallback."""
    try:
        if not sources:
            raise ValueError('no changed source')
        root, state_path = edit_scope.location()
        selected, parts = [], []
        if context == 'scope':
            state = json.loads(state_path.read_text())
            if state.get('error'):
                raise ValueError('invalid active selection')
            for path in dict.fromkeys(sources):
                symbols = [t['symbol'] for t in state['targets'] if t['path'] == path]
                if not symbols:
                    raise ValueError('a changed source has no declared target')
                blob = subprocess.run(['git', 'show', 'HEAD:' + path], cwd=root, capture_output=True, check=True).stdout
                spans = edit_scope.resolve(blob, symbols)
                lines = blob.splitlines(keepends=True)
                # Parents cover children once; duplicate overlapping text must not
                # change lexical weights merely because both identities were named.
                numbers = sorted({i for span in spans for i in range(span['start'], span['end'])})
                parts.append(b''.join(lines[i] for i in numbers).decode('utf-8'))
                selected.append(dict(path=path, symbols=symbols, spans=spans,
                                     head_sha256=hashlib.sha256(blob).hexdigest()))
        elif context != 'issue':
            raise ValueError('unknown retrieval context')
        issue_path = state_path.parent / 'aci-test-issue.json'
        issue = json.loads(issue_path.read_text()) if issue_path.exists() else ''
        if not isinstance(issue, str):
            raise ValueError('public issue is not text')
        if context == 'issue' and not issue.strip():
            raise ValueError('public issue is empty or missing')
        query = '\n'.join(parts)
        ranking = lexical_pool(root, test_files, issue, query, limit)
        if not ranking:
            raise ValueError('no scored public test')
        method = 'public_issue_lexical' if context == 'issue' else 'declared_scope_lexical'
        return dict(method=method, files=[r['path'] for r in ranking], ranking=ranking,
                    targets=selected, query_sha256=hashlib.sha256(query.encode()).hexdigest(),
                    issue_sha256=hashlib.sha256(issue.encode()).hexdigest())
    except (OSError, ValueError, KeyError, TypeError, subprocess.CalledProcessError) as error:
        return dict(method='module', scope_fallback=str(error))
