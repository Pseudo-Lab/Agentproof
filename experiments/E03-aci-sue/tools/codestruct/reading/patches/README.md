# CodeStruct readCode UTF-8 correction

Pinned upstream: `d89efa473754f455d38ab47b4dc938cfc8334a0d`.
The original checkout stays unchanged. The vendored CLI differs only by
[0001-fix-utf8-node-text.patch](0001-fix-utf8-node-text.patch).

Tree-sitter offsets refer to UTF-8 bytes, but the original reader slices a Python
string with those offsets. A comment containing `café雪😀` before `def answer()`
causes its selector output to begin with `swer():` and include part of the next
statement. Read `node.text.decode('utf8')` at the three extraction sites instead.
Selection, summaries, limits, formatting and CLI behavior otherwise stay original.

| Artifact | SHA-256 |
| --- | --- |
| Original bin/readCode | `c5a38b117086a50bd93a50917999bf39179f5e2ea0e73e91eca3c28b4cc09ba5` |
| Patched bin/readCode | `fc073e470833807f016608749bbc1a0c37b9fdb97307de08529838d3453f256b` |
| Patch | `5e8470f5d85a7bb9a65ac943a7c625f4883b8955e23a0cab46196078826e6304` |

`tests/aci/test_search_understanding.py` applies this patch to the pinned original
and compares bytes, compares ASCII/raw/range output against upstream, and checks
Unicode function and class selection against the actual source. Reproduction:
`results/tool-interface-20261026/readCode-utf8-reproduction.txt`.

This is a disclosed correctness fix, not a new reading algorithm. Original
CC-BY-NC-4.0 license and NOTICE are preserved alongside the vendored code.
