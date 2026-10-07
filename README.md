# AI Lecture Live v0.1

강의 중 참가자가 QR로 익명 설문에 참여하고, 강사가 실시간 통계·키워드·자유응답을 프로젝터에서 볼 수 있는 웹앱입니다.

## v0.1 핵심 기능

- `/admin` 관리자 로그인
- 강의 세션 생성 및 활성 세션 지정
- 기본 7문항 자동 생성 + 문구/선택지 수정
- `/today` 고정 주소: 현재 활성화된 강의로 자동 이동
- `/join/{세션코드}` 참가자 설문
- 익명 응답 저장, 동일 기기 재제출 시 기존 응답 갱신
- `/live/{세션코드}` 실시간 결과(2초 갱신)
- 업무 분야/불편 이유 그래프, AI 도움 기대 평균, 키워드 구름, 자유응답 카드
- `/qr/today.png` PPT용 고정 QR 자동 생성
- Cloud Run + Firestore 배포 구조

## 화면 주소

- `/` 서비스 홈
- `/admin` 관리자
- `/today` 오늘의 강의 참여 고정 주소
- `/join/{session}` 세션 참여
- `/live/{session}` 실시간 결과
- `/qr/today.png?download=1` 고정 QR PNG 저장

## 로컬 미리보기

Python 의존성을 설치한 뒤:

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate
# macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
```

로컬 저장 모드로 실행:

```bash
# Windows PowerShell
$env:DATA_BACKEND="local"
$env:ADMIN_PASSWORD="admin"
$env:SECRET_KEY="local-test-key"
python app.py
```

브라우저에서 `http://localhost:8080/admin`에 접속하고 비밀번호 `admin`으로 테스트합니다.

> `DATA_BACKEND=local`은 개발/미리보기 전용입니다. Cloud Run에서는 Firestore를 사용하세요.

## Cloud Run 배포 전 준비

1. Google Cloud 프로젝트에서 Cloud Run, Cloud Build, Firestore 관련 API를 사용 가능하게 합니다.
2. Firestore 데이터베이스를 Native mode로 생성합니다.
3. Cloud Run 서비스가 Firestore를 읽고 쓸 수 있는 서비스 계정 권한을 갖도록 합니다.
4. 다음 환경변수를 Cloud Run 서비스에 설정합니다.
   - `DATA_BACKEND=firestore`
   - `ADMIN_PASSWORD=강사용_비밀번호`
   - `SECRET_KEY=충분히_긴_임의문자열`

## 첫 배포 후 반드시 할 일

1. 배포된 서비스 URL의 `/admin`에 로그인합니다.
2. 첫 강의를 만듭니다.
3. 오늘의 강의로 활성화합니다.
4. 관리자 메인의 **고정 QR PNG 저장**을 눌러 `/today` QR을 받습니다.
5. 이 QR을 PPT에 넣습니다.

이 QR은 이후 강의가 바뀌어도 그대로 쓸 수 있습니다. 관리자에서 활성 세션만 변경하면 `/today`가 새 강의로 연결됩니다.

## Firestore 데이터 구조

```text
settings/global
  active_session_id

sessions/{session_id}
  title
  subtitle
  created_at
  questions[]

sessions/{session_id}/responses/{anonymous_client_id}
  answers{}
  submitted_at
```

이름, 기관명, 이메일 등 개인식별정보는 기본 질문에 포함하지 않습니다.

## GitHub에 올릴 때

이 폴더의 **내용물 전체**를 `kirakein-gif/ai-lecture-live` 저장소 루트에 업로드하면 됩니다. 폴더 자체를 한 단계 더 중첩해서 올리지 마세요.

## 다음 버전 후보

- 질문 추가/삭제 가능한 완전한 질문 빌더
- 응답 엑셀 다운로드
- 세션 복제
- AI 업무 재설계 분석
- 발표용 응답 선택/고정
- 강의별 누적 비교 통계
