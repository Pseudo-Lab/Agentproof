# 조작 점검 기록

- `check-001-netbug.json`: **무효**. 컨테이너를 `--network none`으로 띄워 verifier가 pytest를 설치하지 못했다(모든 reward 0). `docker_env.py`를 고친 뒤 다시 점검했다.
- `check-002.json`, `check-003.json`: 유효. 6개 과제 통과, grid-dispatch는 조작 실패, suricata는 빌드 실패로 제외.
