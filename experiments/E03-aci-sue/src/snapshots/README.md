# 실행 당시 코드

`baseline.tar.gz`, `intervention.tar.gz`는 mini 디렉토리 구조를 보존한 당시 코드다.
`*-vs-mini.patch`는 mini 2.4.6 commit `04d809ceab9df28f9adaed044884180159172930` 대비
포함된 mini 소스·설정·pyproject 변경을 보여준다. 도구 코드는 archive에 있다.
[upstream pin](../../configs/upstreams.lock.json)을 함께 제공한다.

`provenance.json`에는 원본/public archive 해시, 포함 파일별 해시, 생략·보완 목록이 있다.
소스 바이트는 유지하고 tar 소유자·시간을 정규화했다. 로컬 에이전트 지침, 개발 문서,
egg-info, 일부 테스트·smoke fixture를 생략했다.
Baseline의 LICENSE.md와 serving 환경 3개 파일은 staged snapshot에서 보완했다.
당시 자체 변경분은 미커밋 상태이며 실제 서버 정보는 각 run의 로그·fingerprint로 확인한다.

각 upstream LICENSE/NOTICE를 보존했다. CodeStruct 코드는 CC-BY-NC-4.0을 따른다.
현재 작업 폴더의 후속 리팩터링은 이 snapshot 이후에 진행되었다.
