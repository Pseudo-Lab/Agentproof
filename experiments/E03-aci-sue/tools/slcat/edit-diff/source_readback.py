"""Bounded current-source windows from the existing post-command diff hunks.

This only reads tracked changed files. It does not execute source, infer edit
correctness, add syntax checks or change the background verification policy.
"""
from pathlib import Path
import re

BEGIN = '[readback] current source after this command'
END = '[readback] end'
OMITTED = '[readback] additional source omitted'
HUNK = re.compile(r'^@@ -\d+(?:,\d+)? \+(\d+)(?:,(\d+))? @@')


def source_lines(entries):
    for path, deleted, diff in entries:
        if deleted:
            yield [f'[readback] {path}: deleted']
            continue
        try:
            text = Path(path).read_text(encoding='utf-8')
        except (OSError, UnicodeError):
            yield [f'[readback] {path}: source unavailable']
            continue
        if '\0' in text:
            yield [f'[readback] {path}: binary source omitted']
            continue
        lines = text.splitlines()
        if not lines:
            yield [f'[readback] {path}: empty file']
            continue
        ranges=[]
        for line in diff:
            match=HUNK.match(line)
            if not match:
                continue
            start,count=int(match[1]),int(match[2] or 1)
            if count:
                start,end=max(1,start),min(len(lines),start+count-1)
                if ranges and start<=ranges[-1][1]+1:
                    ranges[-1]=(ranges[-1][0],max(end,ranges[-1][1]))
                else:
                    ranges.append((start,end))
        for start,end in ranges:
            yield [f'<file>{path}</file>',f'[readback] lines {start}-{end}',
                   *(f'{n}:{lines[n-1]}' for n in range(start,end+1))]


def render(entries, budget):
    """Return a complete delimited report, with whole source lines only.

The existing runner still caps the *combined* command output. This budget is
only the remaining post-command report allowance, not a stdout-capture layer.
"""
    reserved=sum(len(s)+1 for s in [BEGIN,OMITTED,END])
    if budget<reserved:
        return ''
    remaining=budget-reserved
    output=[BEGIN];shown=False;omitted=False
    for block in source_lines(entries):
        # Keep the file/range header together with at least one source row.
        first=3 if block[0].startswith('<file>') else 1
        cost=sum(len(s)+1 for s in block[:first])
        if cost>remaining:
            omitted=True;break
        output.extend(block[:first]);remaining-=cost;shown=True
        for line in block[first:]:
            if len(line)+1>remaining:
                omitted=True;break
            output.append(line);remaining-=len(line)+1
        if omitted:
            break
    if not shown and not omitted:
        return ''
    if omitted:
        output.append(OMITTED)
    output.append(END)
    result='\n'.join(output)+'\n'
    assert len(result)<=budget
    return result
