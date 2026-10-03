이 프로젝트는 Harness 프레임워크를 사용한다. 아래 워크플로우에 따라 작업을 진행하라.

---

## 워크플로우

### A. 탐색

`/docs/` 하위 문서(PRD, ARCHITECTURE, ADR 등)를 읽고 프로젝트의 기획·아키텍처·설계 의도를 파악한다. 필요시 Explore 에이전트를 병렬로 사용한다.

### B. 논의

구현을 위해 구체화하거나 기술적으로 결정해야 할 사항이 있으면 사용자에게 제시하고 논의한다.

### C. Step 설계

사용자가 구현 계획 작성을 지시하면 여러 step으로 나뉜 초안을 작성해 피드백을 요청한다.

설계 원칙:

1. **Scope 최소화** — 하나의 step에서 하나의 레이어 또는 모듈만 다룬다. 여러 모듈을 동시에 수정해야 하면 step을 쪼갠다.
2. **자기완결성** — 각 step 파일은 독립된 Claude 세션에서 실행된다. "이전 대화에서 논의한 바와 같이" 같은 외부 참조는 금지한다. 필요한 정보는 전부 파일 안에 적는다.
3. **사전 준비 강제** — 관련 문서 경로와 이전 step에서 생성/수정된 파일 경로를 명시한다. 세션이 코드를 읽고 맥락을 파악한 뒤 작업하도록 유도한다.
4. **시그니처 수준 지시** — 함수/클래스의 인터페이스만 제시하고 내부 구현은 에이전트 재량에 맡긴다. 단, 설계 의도에서 벗어나면 안 되는 핵심 규칙(멱등성, 보안, 데이터 무결성 등)은 반드시 명시한다.
5. **AC는 실행기가 직접 돌리는 bash 블록** — "~가 동작해야 한다" 같은 서술이 아니라 실행 가능한 명령으로 쓴다. execute.py는 실행 시작 때 AC를 고정하고, 에이전트가 completed를 보고하면 프로젝트 루트에서 `bash -e -o pipefail -x`로 실행해(제한 600초) 통과해야만 완료로 확정한다.
   - **형식**: `## Acceptance Criteria` 아래에 ` ```bash ` 블록이 정확히 하나. 헤더가 없거나, 블록이 0개이거나 2개 이상이거나, 비어 있거나, fence가 닫히지 않았거나, Bash 가드가 막는 명령(`rm -rf`, `git reset --hard` 등)이 있으면 계획 오류다. execute.py가 실행 전에 모든 step을 검사해 한 번에 보고하고 멈춘다.
   - **명령**: CLAUDE.md "명령어"에 정의한 프로젝트 로컬 명령만 쓴다 (`python -m pytest`, `npx`, `uv run` 등). 환경 문제로 생긴 실패는 에이전트가 고칠 수 없어 재시도만 다 써 버린다.
   - **핵심 동작 직접 확인**: 이 step의 핵심 동작을 직접 확인하는 명령(특정 테스트 파일이나 케이스 지정)을 하나 이상 넣는다. `npm test` 하나뿐인 AC는 자기 보고와 다르지 않다.
   - **한 줄에 명령 하나**: `a && b`를 마지막 줄이 아닌 곳에 쓰면 `-e`가 있어도 `a`의 실패가 숨는다.
   - **금지**: 실패를 숨기는 `|| true`, 서버·watch·백그라운드 작업, 배포나 실제 DB 변경 같은 영구적인 변경.
   - **비밀값**: 비밀값이나 비밀값을 담은 환경변수를 넣지 않는다. `-x` 출력과 재시도 프롬프트에 그대로 노출된다.
   - **반복 실행**: 몇 번을 돌려도 결과가 같아야 한다.
   - **문서 작업 step**: 파일과 내용을 확인하는 명령을 둔다 (예: `test -f docs/API.md`, `grep -q "## 인증" docs/API.md`).
6. **주의사항은 구체적으로** — "조심해라" 대신 "X를 하지 마라. 이유: Y" 형식으로 적는다.
7. **네이밍** — step name은 kebab-case slug로, 해당 step의 핵심 모듈/작업을 한두 단어로 표현한다 (예: `project-setup`, `api-layer`, `auth-flow`).

### D. 파일 생성

사용자가 승인하면 아래 파일들을 생성한다.

#### D-1. `phases/index.json` (전체 현황)

여러 task를 관리하는 top-level 인덱스. 이미 존재하면 `phases` 배열에 새 항목을 추가한다.

```json
{
  "phases": [
    {
      "dir": "0-mvp",
      "status": "pending"
    }
  ]
}
```

- `dir`: task 디렉토리명.
- `status`: `"pending"` | `"completed"` | `"error"` | `"blocked"`. execute.py가 실행 중 자동으로 업데이트한다.
- 타임스탬프(`completed_at`, `failed_at`, `blocked_at`)는 execute.py가 상태 변경 시 자동 기록한다. 생성 시 넣지 않는다.

#### D-2. `phases/{task-name}/index.json` (task 상세)

```json
{
  "project": "<프로젝트명>",
  "phase": "<task-name>",
  "steps": [
    { "step": 0, "name": "project-setup", "status": "pending" },
    { "step": 1, "name": "core-types", "status": "pending" },
    { "step": 2, "name": "api-layer", "status": "pending" }
  ]
}
```

필드 규칙:

- `project`: 프로젝트명 (CLAUDE.md 참조).
- `phase`: task 이름. 디렉토리명과 일치시킨다.
- `steps[].step`: 0부터 시작하는 순번.
- `steps[].name`: kebab-case slug.
- `steps[].status`: 초기값은 모두 `"pending"`.

상태 전이와 기록 필드:

| 에이전트 보고 | 에이전트가 쓰는 필드 | execute.py의 처리 |
|------|-------------|----------|
| `completed` | `status`, `summary` | AC 게이트 통과 → `completed_at` 기록 후 커밋. 실패 → `pending`으로 되돌리고 `summary`를 지운 뒤 재시도 |
| `error` | `status`, `error_message` | 재시도. 마지막 시도까지 실패하면 `status: "error"`, `error_message`, `failed_at` 기록 (커밋하지 않음) |
| `blocked` | `status`, `blocked_reason` | `blocked_at` 기록 후 중단 |

- 에이전트는 자기 step의 `status`, `summary`, `error_message`, `blocked_reason`만 쓴다. execute.py는 호출 뒤 이 네 필드만 옮겨 index를 다시 쓰므로, 다른 step이나 다른 필드를 고쳐도 반영되지 않는다.
- `completed_at`, `failed_at`, `blocked_at`, `started_at`은 execute.py만 기록한다. `completed_at`은 **AC 게이트를 통과한 뒤에만** 기록된다.
- `completed`는 "검증해 달라"는 요청이다. `completed`인데 `completed_at`이 없으면 미검증 상태이고, 재실행하면 에이전트 없이 AC 게이트만 다시 돌린다.

`summary`는 step 완료 시 산출물을 한 줄로 요약한 것으로, execute.py가 다음 step 프롬프트에 컨텍스트로 누적 전달한다. 따라서 다음 step에 유용한 정보(생성된 파일, 핵심 결정 등)를 담아야 한다.

`created_at`은 execute.py가 최초 실행 시 task 레벨에 한 번만 기록한다. step 레벨의 `started_at`도 execute.py가 각 step 시작 시 자동 기록한다. 생성 시 넣지 않는다.

#### D-3. `phases/{task-name}/step{N}.md` (각 step마다 1개)

```markdown
# Step {N}: {이름}

## 읽어야 할 파일

먼저 아래 파일들을 읽고 프로젝트의 아키텍처와 설계 의도를 파악하라:

- `/docs/ARCHITECTURE.md`
- `/docs/ADR.md`
- {이전 step에서 생성/수정된 파일 경로}

이전 step에서 만들어진 코드를 꼼꼼히 읽고, 설계 의도를 이해한 뒤 작업하라.

## 작업

{구체적인 구현 지시. 파일 경로, 클래스/함수 시그니처, 로직 설명을 포함.
코드 스니펫은 인터페이스/시그니처 수준만 제시하고, 구현체는 에이전트에게 맡겨라.
단, 설계 의도에서 벗어나면 안 되는 핵심 규칙은 명확히 박아넣어라.}

## Acceptance Criteria

```bash
{이 step의 핵심 동작을 직접 확인하는 명령. 예: python3 -m pytest tests/auth/test_session.py -q}
{회귀 확인 명령. CLAUDE.md "명령어"의 프로젝트 로컬 명령을 한 줄에 하나씩. 예: npm run build}
```

## 검증 절차

1. 위 AC 커맨드를 실행한다.
2. 아키텍처 체크리스트를 확인한다:
   - ARCHITECTURE.md 디렉토리 구조를 따르는가?
   - ADR 기술 스택을 벗어나지 않았는가?
   - CLAUDE.md CRITICAL 규칙을 위반하지 않았는가?
3. 결과에 따라 `phases/{task-name}/index.json`의 해당 step을 업데이트한다:
   - 성공 → `"status": "completed"`, `"summary": "산출물 한 줄 요약"`. completed를 기록하면 실행기가 AC로 다시 검증한다.
   - AC를 통과시키지 못함 → `"status": "error"`, `"error_message": "구체적 에러 내용"`
   - 사용자 개입 필요 (API 키, 외부 인증, 수동 설정 등) → `"status": "blocked"`, `"blocked_reason": "구체적 사유"` 후 즉시 중단
4. 커밋하지 마라. 실행기가 검증한 뒤 커밋한다.
5. AC 블록, docs/, CLAUDE.md, 다른 step의 상태를 수정하지 마라.

## 금지사항

- {이 step에서 하지 말아야 할 것. "X를 하지 마라. 이유: Y" 형식}
- 기존 테스트를 깨뜨리지 마라
```

### E. 실행

```bash
python3 scripts/execute.py {task-name}        # 순차 실행
python3 scripts/execute.py {task-name} --push  # 실행 후 push
```

execute.py가 자동으로 처리하는 것:

- 사전 검사 — `claude`·`git` 설치 여부와, 아직 확정되지 않은 모든 step의 AC를 실행 전에 검사하고 고정
- `feat-{task-name}` 브랜치 생성/checkout
- 가드레일 주입 — CLAUDE.md + docs/*.md 내용을 매 step 프롬프트에 포함
- 컨텍스트 누적 — 완료된 step의 summary를 다음 step 프롬프트에 전달
- AC 게이트 출력을 피드백 — completed 보고 뒤 고정된 AC를 직접 실행하고, 실패하면 출력 끝부분을 다음 프롬프트에 넣어 최대 3회까지 재시도한다. Claude 호출 시간 초과(1800초)도 한 번의 시도로 센다
- 검증 통과 후 2단계 커밋 — 코드 변경(`feat`)과 메타데이터(`chore`)를 분리 커밋. 에이전트는 커밋하지 않음 (에이전트가 커밋하면 `reset --soft`로 되돌림)
- 타임스탬프 — started_at, completed_at, failed_at, blocked_at 자동 기록

에러 복구:

- **실패한 코드는 커밋되지 않고 working tree에 남는다.** `git status`로 새 파일까지 확인하고, `git diff`로 내용을 확인한다.
- **이어서 고치려면**: 코드를 그대로 두고 `phases/{task-name}/index.json`에서 해당 step의 `status`를 `"pending"`으로 바꾸고 `error_message`를 삭제한 뒤 재실행한다.
- **버리려면**: 사용자가 직접 `git restore`, `git clean`을 실행한 뒤 위처럼 `pending`으로 되돌린다. Bash 가드가 에이전트의 `git clean -f`를 막는다.
- **AC를 고쳤다면**: 이미 완료된 step이라도 해당 step의 `status`를 `"pending"`으로 되돌린다. 실행기는 AC가 바뀌었는지 비교하지 않으므로, 되돌리지 않으면 옛 AC 기준의 완료가 그대로 남는다.
- **blocked 발생 시**: `blocked_reason`에 적힌 사유를 해결한 뒤, `status`를 `"pending"`으로 바꾸고 `blocked_reason`을 삭제한 뒤 재실행한다.
