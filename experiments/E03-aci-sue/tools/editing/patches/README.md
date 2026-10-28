# CodeStruct UTF-8 offset correction

The pinned checkout at `external/CodeStruct` remains unchanged. The static copy
in `tools/editing/upstream/` includes exactly the unified patch listed in
`manifest.json`. There is no runtime copy or patch step. Tests check the recorded
patch, original executable, and resulting executable SHA-256 hashes. Retained `lib/`
files remain byte-identical to the pinned source. The unused MCP servers
`coderead_server.py`, `codewrite_server.py`, and the standalone `install_languages.py`
are omitted; `manifest.json` records those omissions.

Upstream commit: `d89efa473754f455d38ab47b4dc938cfc8334a0d`.

| Artifact | SHA-256 |
| --- | --- |
| Original `bin/editCode` | `03bdb4b569a4f8c00b2d5ce404dce68741849176a24bec9ff43ac297118f4201` |
| Patched `bin/editCode` | `4e5694d3df1491a5941ecf3c5ad4e62d5da00553b99ff964e37e102646ffa694` |
| `0001-fix-utf8-node-offsets.patch` | `39a2f60645a1a458cbb772ff31d872001f7a0faa017e2e36c9773a4164240b67` |

Tree-sitter reports UTF-8 **byte** offsets. The original editor used these directly
as Python string indices. With non-ASCII text before or inside a target, a valid
edit could silently remove an unrelated following statement while returning
success. The original and staged editor reproduced the same bug; the audit proof
is under `.cache/audit-codestruct-unicode/` in the validated workspace.

This patch only converts node boundaries to character indices before string
slicing and indentation lookup. It covers the existing `replace_node`,
`insert_node`, `delete_node`, and CLI `replace_in_node` paths. The native tool
continues to expose the original three operations. Selector matching, node
selection, insertion policy, indentation normalization, Python syntax rejection,
CLI output, and exit-code behavior are preserved. No editor algorithm is replaced.
Diagnostic helpers in `lib/` are not changed by this mutation-boundary fix.

`tests/aci/test_editing_verification.py` verifies all manifest hashes and compares original/patched CLI
behavior. Regressions cover multibyte text before/inside nodes, scoped methods,
function/class insertion, deletion, and an out-of-node string replacement that
must be rejected. ASCII and Unicode appearing only after the target retain the
original behavior. The vendored executable must equal the exact recorded patch
result, and its library files must remain original.

The original CC-BY-NC-4.0 copyright and license notices remain in the vendored
source. This local patch is a disclosed correctness fix to the selected upstream
editing component, not a new implementation of the CodeStruct method.

The bundle also includes the original `str_replace/bin/str_replace` and
`str_replace/bin/create_file` from the same CodeStruct pin. These two files are
byte-identical to upstream; shell launchers select the private Python runtime.
The CLI tests compare outputs and mutations against the originals, including
nonunique-match rejection, deletion, nested file creation and overwrite behavior.
