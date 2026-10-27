"""Docker plumbing for running SkillsBench tasks with our own agent loop.

One container per trial, built from the task's environment/Dockerfile (pinned SkillsBench commit).
Agent phase runs with --network none. The verifier phase copies verifier/ to /verifier, attaches the
default bridge network (test.sh installs pytest) and runs `bash /verifier/test.sh`.
"""
import json
import re
import shlex
import subprocess
import time
import uuid
from pathlib import Path

DOCKER = 'docker'


class DockerError(Exception):
    pass


def _run(args, timeout=None, input_text=None, check=True):
    proc = subprocess.run([DOCKER, *args], capture_output=True, text=True, timeout=timeout, input=input_text)
    if check and proc.returncode != 0:
        raise DockerError(f'docker {" ".join(args[:3])}… exit {proc.returncode}: {proc.stderr.strip()[:400]}')
    return proc


def parse_task_md(path):
    """Return (frontmatter dict subset, body). Minimal YAML reader for the fields we need."""
    text = Path(path).read_text()
    m = re.match(r'^---\n(.*?)\n---\n(.*)$', text, re.S)
    if not m:
        return {}, text
    fm, body = m.group(1), m.group(2).strip()
    meta = {}
    section = None
    for line in fm.splitlines():
        if re.match(r'^\S', line):
            section = line.split(':', 1)[0].strip()
            continue
        mm = re.match(r'^\s+(\w+):\s*(.*)$', line)
        if mm and section in ('verifier', 'agent', 'sandbox'):
            k, v = mm.group(1), mm.group(2).strip().strip("'\"")
            try:
                v = float(v) if '.' in v else int(v)
            except ValueError:
                pass
            meta[f'{section}.{k}'] = v
    return meta, body


def image_tag(task, commit):
    return f'agentproof-e02/{task}:{commit[:7]}'


def build_image(task_dir, task, commit, timeout=1800):
    tag = image_tag(task, commit)
    if _run(['image', 'inspect', tag], check=False).returncode == 0:
        return tag
    env_dir = Path(task_dir) / 'environment'
    t0 = time.time()
    proc = _run(['build', '-t', tag, str(env_dir)], timeout=timeout, check=False)
    if proc.returncode != 0:
        raise DockerError(f'build failed for {task} after {time.time() - t0:.0f}s: {proc.stderr[-800:]}')
    return tag


def workdir_of(tag, meta):
    if meta.get('sandbox.workdir'):
        return str(meta['sandbox.workdir'])
    wd = _run(['image', 'inspect', tag, '--format', '{{.Config.WorkingDir}}']).stdout.strip()
    return wd or '/root'


class Container:
    def __init__(self, tag, workdir, cpus=2, memory_mb=4096, offline=True):
        self.name = f'e02-{uuid.uuid4().hex[:10]}'
        self.workdir = workdir
        # Start on the default bridge, then detach it for the agent phase. (A container started with
        # --network none cannot be attached to bridge later, which the verifier needs.)
        _run(['run', '-d', '--name', self.name, f'--cpus={min(cpus, 2)}',
              f'--memory={min(int(memory_mb), 3072)}m', '-w', workdir, tag, 'sleep', 'infinity'])
        if offline:
            self.disconnect()

    def disconnect(self):
        _run(['network', 'disconnect', 'bridge', self.name], timeout=60)
        rc, _, _ = self.exec('getent hosts pypi.org >/dev/null 2>&1', timeout=20)
        if rc == 0:
            raise DockerError('network still reachable after disconnect')

    def connect(self):
        proc = _run(['network', 'connect', 'bridge', self.name], timeout=60, check=False)
        if proc.returncode != 0 and 'already exists' not in proc.stderr:
            raise DockerError(f'network connect failed: {proc.stderr.strip()[:300]}')

    def exec(self, cmd, timeout=60, stdin=None, workdir=None):
        args = ['exec', '-i' if stdin is not None else '-t', '-w', workdir or self.workdir, self.name,
                'bash', '-lc', cmd]
        if stdin is None:
            args.remove('-t')
        try:
            proc = _run(args, timeout=timeout, input_text=stdin, check=False)
            return proc.returncode, proc.stdout, proc.stderr
        except subprocess.TimeoutExpired:
            # kill whatever is still running from this exec
            _run(['exec', self.name, 'bash', '-lc', 'pkill -f -- "' + cmd[:40].replace('"', '') + '" || true'],
                 timeout=10, check=False)
            return 124, '', f'timeout after {timeout}s'

    def put_dir(self, src, dest):
        self.exec(f'mkdir -p {shlex.quote(str(Path(dest).parent))}', timeout=20)
        _run(['cp', str(src), f'{self.name}:{dest}'], timeout=120)

    def get(self, src, dest):
        return _run(['cp', f'{self.name}:{src}', str(dest)], timeout=120, check=False).returncode == 0

    def snapshot(self, paths):
        """sha256 of files under paths (to detect agent tampering with inputs)."""
        cmd = ' '.join(shlex.quote(p) for p in paths)
        rc, out, _ = self.exec(f'find {cmd} -type f -print0 2>/dev/null | sort -z | xargs -0 sha256sum 2>/dev/null | sha256sum',
                               timeout=60)
        return out.strip()

    def run_verifier(self, verifier_dir, timeout=900):
        self.put_dir(verifier_dir, '/verifier')
        self.connect()
        rc, out, err = self.exec('bash /verifier/test.sh', timeout=timeout, workdir=self.workdir)
        _, reward, _ = self.exec('cat /logs/verifier/reward.txt 2>/dev/null', timeout=20)
        try:
            reward = float(reward.strip())
        except ValueError:
            reward = None
        _, ctrf, _ = self.exec('cat /logs/verifier/ctrf.json 2>/dev/null', timeout=20)
        try:
            summary = json.loads(ctrf)['results']['summary']
        except (json.JSONDecodeError, KeyError, TypeError):
            summary = None
        return {'reward': reward, 'exit': rc, 'tests': summary, 'log_tail': (out + err)[-3000:]}

    def remove(self):
        _run(['rm', '-f', self.name], timeout=60, check=False)
