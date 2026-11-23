"""Literal-stdin/result adapter for pinned CodeStruct replace_node.

No new selector, indentation, splice, or syntax algorithm. Other CLI modes retain
their native launcher. This opt-in transport reports the upstream function's
status instead of the original CLI's always-zero exit status.
"""
import argparse
import contextlib
import difflib
import io
import json
from pathlib import Path
import runpy
import sys


def apply(path, selector, replacement):
    source = Path(__file__).resolve().parent / 'upstream/ast_edit/bin/editCode'
    captured = io.StringIO()
    with contextlib.redirect_stdout(captured):
        editor = runpy.run_path(str(source))
    before = Path(path).read_bytes()
    with contextlib.redirect_stdout(captured):
        result = editor['ProductionAstOperations'].execute_operation(
            path, editor['get_language_parser'](path)[1], 'replace_node', selector,
            replacement=replacement)
    after = Path(path).read_bytes()
    success = result.get('status') == 'success'
    status = 'applied' if success and after != before else 'unchanged' if success else 'failed'
    record = dict(status=status, path=path, selector=selector, changed=after != before)
    if not success:
        record['detail'] = result.get('message', captured.getvalue())[:1200]
    return record, before, after


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('path')
    parser.add_argument('operation', choices=['replace_node'])
    parser.add_argument('selector')
    parser.add_argument('--replacement-stdin', action='store_true', required=True)
    args = parser.parse_args()
    try:
        record, before, after = apply(args.path, args.selector, sys.stdin.read())
    except (OSError, ValueError) as error:
        print('[node edit] ' + json.dumps(dict(status='failed', path=args.path,
              selector=args.selector, detail=str(error))))
        return 2
    print('[node edit] ' + json.dumps(record, ensure_ascii=True))
    if before != after:
        diff = ''.join(difflib.unified_diff(before.decode('utf8').splitlines(keepends=True),
                       after.decode('utf8').splitlines(keepends=True), fromfile=args.path,
                       tofile=args.path, n=3))
        print('[node diff]')
        print(diff[:1600], end='' if diff[:1600].endswith('\n') else '\n')
        if len(diff) > 1600:
            print('[node diff] additional text omitted')
        print('[node diff] end')
    return 0 if record['status'] in {'applied', 'unchanged'} else 1


if __name__ == '__main__':
    sys.exit(main())
