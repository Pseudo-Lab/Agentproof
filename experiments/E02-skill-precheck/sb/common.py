"""Shared helpers for E02 v4: task config, skill materialization (E0/E1/S), hashing."""
import hashlib
import json
import shutil
from pathlib import Path

SB = Path(__file__).resolve().parent
EXPERIMENT = SB.parent
ROOT = EXPERIMENT.parents[1]
SKILL_ROOT_IN_CONTAINER = '/root/.claude/skills'


def load_tasks_config():
    return json.loads((SB / 'tasks.json').read_text())


def sha(data):
    return hashlib.sha256(data.encode() if isinstance(data, str) else data).hexdigest()


def tree_sha(d):
    h = hashlib.sha256()
    for p in sorted(Path(d).rglob('*')):
        if p.is_file():
            h.update(str(p.relative_to(d)).encode())
            h.update(p.read_bytes())
    return h.hexdigest()


def apply_edits(base_dir, edits):
    """Apply exact old->new replacements; each old string must occur exactly once."""
    for e in edits:
        f = Path(base_dir) / e['file']
        text = f.read_text()
        n = text.count(e['old'])
        if n != 1:
            raise ValueError(f"edit target occurs {n} times in {e['file']}: {e['old'][:60]!r}")
        f.write_text(text.replace(e['old'], e['new']))


def materialize_skills(task_dir, task_cfg, env, cond, dest):
    """Copy environment/skills to dest and apply the env/condition variant. Returns read_skill text or None."""
    if cond == 'A':
        return None
    src = Path(task_dir) / 'environment' / 'skills'
    shutil.copytree(src, dest)
    if env == 'E1':
        apply_edits(dest, task_cfg['skill_edits_E1'])
    if cond == 'S':
        f = Path(dest) / task_cfg['primary_skill_file']
        f.write_text(f.read_text().rstrip('\n') + '\n\n' + task_cfg['s_section'][env].strip() + '\n')
    return render_skill_text(dest)


def render_skill_text(skill_dir):
    parts = []
    for skill_md in sorted(Path(skill_dir).glob('*/SKILL.md')):
        name = skill_md.parent.name
        files = sorted(str(p.relative_to(skill_dir)) for p in skill_md.parent.rglob('*') if p.is_file())
        listing = '\n'.join(f'- {SKILL_ROOT_IN_CONTAINER}/{f}' for f in files)
        parts.append(f'===== 스킬: {name} ({SKILL_ROOT_IN_CONTAINER}/{name}) =====\n'
                     f'{skill_md.read_text()}\n\n[스킬 폴더 파일]\n{listing}')
    return '\n\n'.join(parts)
