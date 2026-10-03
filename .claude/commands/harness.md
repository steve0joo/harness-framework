이 프로젝트는 Harness 프레임워크를 사용한다. 아래 워크플로우에 따라 작업을 진행하라.

사용자 입력: $ARGUMENTS

---

## 진입

`docs/PRD.md`의 "기획 상태" 섹션을 보고 시작 지점을 정한다.

| 기획 상태 | 시작 지점 |
|---|---|
| 섹션이 없음 | A. 탐색 |
| `미시작` 또는 `<단계> (초안)` | 0. 기획. 기록된 단계부터 이어서 |
| `확정 (YYYY-MM-DD)` | A. 탐색. 사용자가 재기획을 요청하면 0. 기획의 "재기획" |

docs를 직접 채워 기획을 건너뛰려면 "기획 상태"를 `확정 (YYYY-MM-DD)`으로 바꾸거나 섹션을 지운다.

---

## 워크플로우

### 0. 기획

아이디어에서 docs를 만든다. 기획 중간 파일은 만들지 않고, 단계마다 공식 docs의 담당 섹션을 갱신한다. docs는 실행 때 모든 step 프롬프트에 그대로 들어가므로, 현재 결정만 서로 모순 없이 남긴다.

**아이디어**: `미시작`이면 사용자 입력을 아이디어로 쓴다. 비어 있으면 무엇을 누구를 위해 만들려는지 5~10줄로 써 달라고 묻고 기다린다.

**기획 상태** (PRD 맨 위):

```markdown
## 기획 상태
- 단계: 2-아키텍처 (초안)        <!-- 미시작 | <단계> (초안) | 확정 (YYYY-MM-DD) -->
- 열린 질문:
  - 결제 수단은 카드만 지원하는가?
```

- `단계`는 지금 작업 중인 단계다. 단계를 시작할 때 `<단계> (초안)`으로 기록하고, 다음 단계로 넘어갈 때 바꾼다.
- `열린 질문`에는 사용자의 답이 필요한 질문만 둔다. 답을 받으면 docs에 반영하고 목록에서 지운다.
- 이어서 진행할 때는 대화 기록이 아니라 이 섹션과 docs를 **파일에서 다시 읽고** 기록된 단계부터 시작한다.

**단계**:

| 단계 | 하는 일 | 반영할 곳 | 하지 말 것 |
|---|---|---|---|
| 0-아이디어 | 프로젝트명, 누가 어떤 문제를 겪는지, 핵심 저니가 끝났을 때의 상태(성공 기준), 필수 제약을 확인한다. 기술은 미정이어도 된다. 빠진 게 있으면 질문한다 | PRD 제목·`목표`·`사용자`, CLAUDE.md 제목 | 아이디어에 없는 내용 덧붙이기 |
| 1-유저 플로우 | 사용자, 핵심 저니, 화면과 상태 흐름. **UI가 있는지 정한다.** 없으면 `docs/UI_GUIDE.md`와 PRD `디자인` 섹션을 지운다 | PRD `유저 플로우`·`핵심 기능` | 기술 결정 |
| 2-아키텍처 | 스택, 구성요소, 데이터 흐름과 데이터 모델, 테스트 배치. UI가 있으면 `UI_GUIDE.md`도 채운다 | `ARCHITECTURE.md`, `ADR.md`, `UI_GUIDE.md`, CLAUDE.md `기술 스택`·`아키텍처 규칙` | 유저 플로우에 없는 기능 추가 |
| 3-리스크 | 엣지 케이스, 에러 처리, 보안. 항목마다 필수 / 권장 / 나중 등급을 붙인다 | ARCHITECTURE `에러 처리·보안`. 꼭 지켜야 할 규칙은 CLAUDE.md `CRITICAL`로 | 항목 삭제 |
| 4-MVP | docs를 **파일에서 다시 읽고** 군더더기를 잘라낸다 | 전체 docs. 잘라낸 항목은 PRD `MVP 제외 사항`으로, 실제 명령어는 CLAUDE.md "명령어"로 | 보안·데이터 무결성 "필수" 항목 빼기 |

**진행 규칙**:

- **갱신 방식**: 담당 섹션을 정리해 갱신하고, 영향받는 다른 문서도 함께 맞춘다. 덧붙이기만 하거나 파일 전체를 새로 쓰지 않는다.
- **보존 규칙**
  - ADR은 유효한 결정의 이유와 트레이드오프를 유지한다.
  - 바뀐 결정은 새 ADR로 쓰고, 옛 항목은 "ADR-00N으로 대체됨" 한 줄만 남긴다.
  - CLAUDE.md의 기본 개발 규칙(TDD, conventional commits)은 유지한다.
- **범위 우선**: 파일에 확정된 범위가 대화 기억보다 우선한다. 제외한 아이디어는 사용자가 명시적으로 되살릴 때만 다시 들인다.
- **기본 진행**: 대화에는 바뀐 내용 요약과 열린 질문만 남긴다. 단계마다 승인을 받는다.
- **빠른 경로**: 사용자가 원하면(예: "끝까지 진행") 열린 질문이 없는 단계는 멈추지 않고 이어 간다. **4-MVP 확정만은 항상 승인을 받는다.**
- **4-MVP 판정 기준**
  - 핵심 저니 하나가 끝까지 동작하는 데 필요한가?
  - 빼면 데이터 손실이나 보안 사고가 나는가?
  - 한 번만 쓰이는 추상화, 미래를 대비한 설정, 당장 쓸 일 없는 인프라는 뺀다.
  - docs 분량도 줄인다.
- **확정 전 점검**
  - docs가 MVP 범위와 일치하는가? 잘라낸 항목은 PRD `MVP 제외 사항`에만 남고, 기능·아키텍처·규칙에는 남지 않았는가?
  - 템플릿 placeholder(`{...}` 안내 문구)가 남아 있지 않은가? `grep -n '{' CLAUDE.md docs/*.md`로 찾아 확인한다.
- **확정**: 승인을 받으면 `단계`를 `확정 (YYYY-MM-DD)`로 바꾸고 `열린 질문` 목록을 비운다. 그다음 B. 논의로 이어 간다.
- **재기획**: 확정된 상태에서 사용자가 요청하면, 바뀌는 내용이 처음 영향을 주는 단계의 `(초안)`으로 되돌리고 그 단계부터 진행한다. `phases/`에 아직 실행하지 않은(`pending`) step이 있으면, 새 docs 기준으로 C. Step 설계에서 다시 설계해야 한다고 안내한다.

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
