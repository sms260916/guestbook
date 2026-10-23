# 작은 방명록

Day1~Day8에서 학습한 Python 기초 문법, HTTP 처리, 검증, 상태 저장을 연결한
단일 페이지 방명록입니다. 화면은 HTML과 CSS로 만들고 브라우저 JavaScript는 사용하지
않습니다. 데이터는 Python 내장 `sqlite3`로 된 SQLite 데이터베이스의 테이블 한 개에
저장합니다. 추가 패키지 설치는 필요하지 않습니다.

## Day1~Day8 학습 내용과 적용

| 학습 폴더 | 확인한 문법·방식 | 방명록 적용 |
| --- | --- | --- |
| Day1 | 변수, 조건문, 반복문, 리스트, 함수, 모듈 | 입력값 검사, 최근 글 목록 반복 출력 |
| Day2 | 자료형, 컬렉션, 함수로 값 계산 | 이름·내용을 문자열로 다루고 길이 확인 |
| Day3 | 함수와 클래스, 데이터와 동작의 구성 | 요청 처리 함수와 서버/요청 처리 클래스 |
| Day4 | `random`, 리스트 컴프리헨션, 인덱싱 | 불필요한 외부 패키지를 더하지 않고 표준 라이브러리 사용 |
| Day5 | 작업 폴더에 Day5 자료가 없음 | 적용 근거 없음 |
| Day6 | FastAPI, Pydantic, CRUD, 요청 검증 | 같은 CRUD 흐름을 표준 라이브러리와 SQLite로 간소화 |
| Day7 | HTTP 요청, async/await, 순차·병렬 처리 | 외부 호출이 없어 동기 요청만 사용 |
| Day8 | 입력·오류 검증, 상태 유지, 테스트 | 서버 측 입력 검증, 오류 응답, SQLite 영속 저장, unittest |

## 실행

Python 3.10 이상에서 저장소 루트(`Day1-Day8`의 상위 폴더)에서 실행합니다.

```powershell
python Day1-Day8\guestbook\app.py
```

브라우저에서 `http://127.0.0.1:8000`을 엽니다. 서버 종료는 실행 중인 터미널에서
`Ctrl+C`를 누릅니다.

## Render에 배포

Render는 GitHub 저장소에 연결해 Python 웹 서비스를 배포합니다. 이 폴더만 별도
GitHub 저장소로 만들면 설정이 가장 간단합니다.

### 1. GitHub에 코드 올리기

GitHub에서 새 저장소를 만듭니다. 빈 저장소로 만들고 README, 라이선스, `.gitignore`는
GitHub에서 미리 생성하지 않습니다. PowerShell에서 아래 명령을 실행합니다.

```powershell
cd C:\ai4\Day1-Day8\guestbook
git init
git add app.py index.html README.md test_app.py
git commit -m "Add guestbook app"
git branch -M main
git remote add origin https://github.com/<GitHub-ID>/<저장소이름>.git
git push -u origin main
```

`<GitHub-ID>`와 `<저장소이름>`은 본인의 값으로 바꿉니다. GitHub 로그인 또는 인증
요청이 나오면 본인의 GitHub 계정으로 인증합니다.

### 2. Render에서 웹 서비스 만들기

1. [Render Dashboard](https://dashboard.render.com/)에 로그인합니다.
2. **New + → Web Service**를 선택하고 GitHub를 연결합니다.
3. 방금 만든 저장소를 선택합니다.
4. 다음과 같이 설정합니다.

| 설정 | 값 |
| --- | --- |
| Language | Python 3 |
| Branch | `main` |
| Root Directory | 비워 둠 (이 폴더를 저장소로 만든 경우) |
| Build Command | `python -m compileall .` |
| Start Command | `python app.py` |
| Instance Type | Free |

5. 다른 고급 설정은 기본값으로 두고 **Create Web Service**를 누릅니다.
6. **Logs**에서 배포가 완료되었는지 확인하고 Render가 제공한 `onrender.com` 주소를 엽니다.

`requirements.txt`나 `pip install`은 필요하지 않습니다. 이 앱은 Python 표준 라이브러리만
사용합니다. Render가 제공하는 `PORT`를 앱이 자동으로 읽고 `0.0.0.0`에 바인딩하므로
포트를 고정하거나 별도 환경변수를 추가하지 않아도 됩니다. 코드를 수정해 같은 GitHub
브랜치에 push하면 Render가 다시 배포합니다.

이미 더 큰 저장소에 코드를 올린 경우에는 Render의 **Root Directory**에
`Day1-Day8/guestbook`을 입력합니다. 이때 Build Command는 `python -m compileall .`,
Start Command는 `python app.py`로 동일합니다.

### 무료 플랜의 SQLite 주의사항

무료 Render 웹 서비스의 파일 시스템은 임시 저장소입니다. 따라서 이 앱의 SQLite 파일과
방명록 글은 서비스 재배포·재시작·절전 시 사라질 수 있으며, 장기 보존용으로 사용할 수
없습니다. 무료 호스팅에서 SQLite 파일을 계속 보존하는 방법은 Render가 제공하지 않습니다.
SQLite 한 테이블을 유지하면서 데이터를 보존하려면 영구 디스크를 지원하는 유료 서비스가
필요합니다. 유료 서비스를 피하려면 저장 방식을 다른 데이터베이스로 바꾸는 설계 변경이
필요하므로, 현재의 SQLite 조건과 구분해 결정해야 합니다.

## 동작과 데이터

- 이름은 1~40자, 내용은 1~1000자만 저장합니다. 검증은 서버에서 수행합니다.
- 글은 `guestbook_entries` 테이블 하나에 저장합니다. 다른 테이블이나 관계는 없습니다.
- 새 글은 SQL 매개변수로 저장하고, 화면에는 최신 50개만 ID 내림차순으로 표시합니다.
- 작성 내용은 HTML에 넣기 전에 이스케이프하여 브라우저가 태그로 실행하지 않게 합니다.
- 기본 DB 파일은 이 폴더의 `guestbook.sqlite3`입니다. 다른 위치는 `GUESTBOOK_DB_PATH`
  환경변수로 지정할 수 있습니다.
- 배포 시 `HOST`와 `PORT` 환경변수를 사용할 수 있습니다. SQLite 파일이 서버 재시작
  후에도 유지되는지는 무료 호스팅의 영구 디스크 지원 여부에 달려 있습니다. 플랫폼이
  로컬 파일을 초기화하는 경우에는 영구 저장소 경로를 `GUESTBOOK_DB_PATH`에 지정해야
  합니다. 호스팅 서비스가 정해지면 해당 서비스의 실행 방식과 저장소 정책을 확인하세요.
- 목록 표시를 50개로 제한하지만 저장 글 수에는 상한을 두지 않습니다. 무료 서비스의
  디스크 할당량을 확인하고 운영 전에 보관 정책을 정하세요.

## 테스트

```powershell
python -m unittest discover -s Day1-Day8\guestbook -p "test_*.py"
```

테스트는 임시 데이터베이스와 로컬 HTTP 서버를 사용하며 기본 데이터베이스 파일을
만들지 않습니다.
