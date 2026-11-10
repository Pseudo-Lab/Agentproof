# Condition E' (docs/editing-verification.md). mini runs every command as a new `bash -c`, which
# first reads BASH_ENV. Run the image's own BASH_ENV, then, in the command's shell only (shells it
# starts inherit the marker), report the edits the command made when it ends. The exit status is
# kept: bash returns the command's status after an EXIT trap.
# Only a command that changed tracked files reports (checksum of their diff at start and end), so
# mini's patch commands (`git add -N . && git diff ...`, the submit line) print nothing extra; a
# command that edits and submits at once is skipped, because its output is the patch.
. "$ACI_NEXT_BASH_ENV"
if [ -z "${ACI_EDIT_REPORT_PID:-}" ]; then
  export ACI_EDIT_REPORT_PID=$$
  ACI_EDIT_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
  ACI_EDIT_TOP=$PWD
  if [ "${ACI_EDIT_FILTER:-}" = 1 ]; then
    "$ACI_EDIT_DIR/.venv/bin/python" -I "$ACI_EDIT_DIR/edit_filter.py"
    # Native patch readers inside a compound edit/submit command must see the
    # accepted tree. Checkpoint before the ordinary `git diff` entry point.
    git() {
      if [ "${1:-}" = diff ]; then
        (cd "$ACI_EDIT_TOP" && "$ACI_EDIT_DIR/.venv/bin/python" -I "$ACI_EDIT_DIR/edit_filter.py" --checkpoint)
      fi
      command git "$@"
    }
  fi
  aci_edit_sum() {
    if [ "${ACI_TESTS_CONTEXT:-}" = impact ] || [ "${ACI_TESTS_CONTEXT:-}" = testmon ]; then
      (cd "$ACI_EDIT_TOP" && "$ACI_EDIT_DIR/.venv/bin/python" -I "$ACI_EDIT_DIR/related_tests.py" revision)
    else
      git -C "$ACI_EDIT_TOP" diff --no-ext-diff --diff-filter=MD HEAD 2>/dev/null | cksum
    fi
  }
  ACI_EDIT_START=$(aci_edit_sum)
  ACI_IMPACT_PATCH_ONLY=0
  if [ "${ACI_TESTS_CONTEXT:-}" = impact ] || [ "${ACI_TESTS_CONTEXT:-}" = testmon ]; then
    case $BASH_EXECUTION_STRING in *"git add -N . && git diff --binary HEAD"*) ACI_IMPACT_PATCH_ONLY=1 ;; esac
  fi
  if [ "${ACI_EDIT_SCOPE:-}" = 1 ]; then
    "$ACI_EDIT_DIR/.venv/bin/python" -I "$ACI_EDIT_DIR/edit_scope.py" "$BASH_EXECUTION_STRING"
    ACI_SCOPE_START_STATUS=$?
    if [ "${ACI_EDIT_BOUND:-}" = 1 ]; then
      [ "$ACI_SCOPE_START_STATUS" = 0 ] || exit "$ACI_SCOPE_START_STATUS"
      # Recovery may restore a previously interrupted proposal before this call.
      ACI_EDIT_START=$(aci_edit_sum)
    fi
  fi
  # V' (related_tests.py): a finished, unshown test result goes before this command's output, except
  # for the submit and patch-recovery commands, whose output is the patch.
  if [ "${ACI_EDIT_TESTS:-}" = 1 ] && [ -f "$(git rev-parse --absolute-git-dir 2>/dev/null)/aci-tests/result.json" ]; then
    case $BASH_EXECUTION_STRING in
      *COMPLETE_TASK_AND_SUBMIT_FINAL_OUTPUT*|*"git add -N . && git diff --binary HEAD"*) ;;
      *) "$ACI_EDIT_DIR/.venv/bin/python" -I "$ACI_EDIT_DIR/related_tests.py" deliver ;;
    esac
  fi
  trap 'if [ "${ACI_EDIT_FILTER:-}" = 1 ]; then
          (cd "$ACI_EDIT_TOP" && "$ACI_EDIT_DIR/.venv/bin/python" -I "$ACI_EDIT_DIR/edit_filter.py" --finish)
        fi
        if [ "${ACI_EDIT_BOUND:-}" = 1 ]; then
          (cd "$ACI_EDIT_TOP" && "$ACI_EDIT_DIR/.venv/bin/python" -I "$ACI_EDIT_DIR/edit_scope.py" --finish)
        fi
        case $BASH_EXECUTION_STRING in
          *COMPLETE_TASK_AND_SUBMIT_FINAL_OUTPUT*) ;;
          *) if [ "$ACI_IMPACT_PATCH_ONLY" = 1 ]; then :
             else
             if [ "${ACI_EDIT_SCOPE:-}" = 1 ] && { [ "${ACI_EDIT_SCOPE_APPLY:-}" = 1 ] || [ "${ACI_EDIT_SCOPE_RECEIPT:-}" = 1 ]; }; then
               (cd "$ACI_EDIT_TOP" && "$ACI_EDIT_DIR/.venv/bin/python" -I "$ACI_EDIT_DIR/edit_scope.py" --finish)
             fi
             [ "$(aci_edit_sum)" = "$ACI_EDIT_START" ] ||
             (cd "$ACI_EDIT_TOP" && "$ACI_EDIT_DIR/.venv/bin/python" -I "$ACI_EDIT_DIR/edit_report.py")
             fi ;;
        esac' EXIT
fi
