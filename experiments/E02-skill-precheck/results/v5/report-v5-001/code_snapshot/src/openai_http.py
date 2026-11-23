"""Minimal Responses API client over curl (no SDK, no automatic retries).

curl is used instead of urllib because python.org builds on macOS often lack a CA bundle.
The API key is passed to curl on stdin (-H @-), so it never appears in process arguments or logs.
"""
import json
import os
import subprocess
import tempfile
from pathlib import Path

API_URL = 'https://api.openai.com/v1/responses'


class APIError(Exception):
    pass


class _Obj:
    def __init__(self, d):
        for k, v in d.items():
            setattr(self, k, _Obj(v) if isinstance(v, dict) else v)


class _Response:
    def __init__(self, d):
        self.id = d.get('id')
        self.status = d.get('status', 'completed')
        self.output = d.get('output') or []  # list of dicts; agent copies them back verbatim
        self.usage = _Obj(d.get('usage') or {'input_tokens': 0, 'output_tokens': 0})
        texts = [c.get('text', '') for item in self.output if item.get('type') == 'message'
                 for c in item.get('content') or [] if c.get('type') == 'output_text']
        self.output_text = ''.join(texts)
        self.raw_model = d.get('model')
        self.incomplete_details = d.get('incomplete_details')


def load_key(env_file):
    key = os.environ.get('OPENAI_API_KEY')
    if not key and Path(env_file).is_file():
        for line in Path(env_file).read_text().splitlines():
            if line.strip().startswith('OPENAI_API_KEY='):
                key = line.split('=', 1)[1].strip().strip('"').strip("'")
    if not key:
        raise SystemExit(f'OPENAI_API_KEY not found in environment or {env_file}')
    return key


class HTTPClient:
    def __init__(self, key, timeout_s=180):
        self._key = key
        self.timeout_s = timeout_s
        self.responses = self

    def create(self, **kwargs):
        with tempfile.NamedTemporaryFile('w', suffix='.json', delete=False) as f:
            json.dump(kwargs, f, ensure_ascii=False)
            payload = f.name
        try:
            proc = subprocess.run(
                ['curl', '-sS', '--max-time', str(self.timeout_s), API_URL, '-H', '@-',
                 '-H', 'Content-Type: application/json', '--data-binary', f'@{payload}',
                 '-w', '\n%{http_code}'],
                input=f'Authorization: Bearer {self._key}\n', capture_output=True, text=True)
        finally:
            os.unlink(payload)
        if proc.returncode != 0:
            raise APIError(f'curl exit {proc.returncode}: {proc.stderr.strip()[:200]}')
        body, _, code = proc.stdout.rpartition('\n')
        try:
            data = json.loads(body)
        except json.JSONDecodeError:
            raise APIError(f'HTTP {code}: non-JSON body {body[:200]!r}')
        if code != '200' or 'error' in data and data['error']:
            raise APIError(f'HTTP {code}: {json.dumps(data.get("error"), ensure_ascii=False)[:300]}')
        return _Response(data)
