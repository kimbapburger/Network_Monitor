# 🌐 Network Monitoring Dashboard

> Python · Tkinter · SQLite 기반 실시간 네트워크 호스트 모니터링 데스크톱 애플리케이션

![Python](https://img.shields.io/badge/Python-3.8%2B-3776AB?logo=python&logoColor=white)
![Tkinter](https://img.shields.io/badge/GUI-Tkinter-informational)
![SQLite](https://img.shields.io/badge/DB-SQLite-003B57?logo=sqlite&logoColor=white)
![License](https://img.shields.io/badge/License-MIT-green)

---

## 프로젝트 소개

IP 주소 또는 호스트명을 등록하고 **ICMP Ping**으로 실시간 생존 여부를 확인하는 네트워크 모니터링 도구입니다.  
보안관제·헬프데스크 환경에서 서버·네트워크 장비의 상태를 한눈에 파악할 수 있으며,  
오프라인 감지 시 즉시 팝업 알림을 제공합니다.

---

## 주요 기능

| 기능 | 설명 |
|------|------|
| 호스트 등록/삭제 | IP·이름·그룹을 지정해 모니터링 대상 관리 |
| 실시간 Ping 모니터링 | ICMP Ping으로 온라인/오프라인 상태 확인 |
| 응답속도(ms) 측정 | 각 호스트의 핑 응답시간 표시 |
| 자동 갱신 | 설정한 주기(초)마다 자동으로 전체 핑 실행 |
| 오프라인 알림 팝업 | 호스트 미응답 감지 시 즉시 경고 팝업 (쿨다운 적용) |
| 핑 이력 조회 | 호스트별 최근 50건 핑 기록 팝업 조회 |
| 실시간 검색 | 이름·IP·그룹 키워드 즉시 필터링 |
| CSV 내보내기 | 현재 모니터링 현황을 CSV로 저장 |

---

## 화면 구성

```
┌────────────────────────────────────────────────────────────────┐
│     Network Monitor          [검색창]  [▶시작] [■정지]           │ ← 툴바
├──────────┬───────────┬──────────────┬──────────────────────────┤
│  전체 5   │ 온라인 3   │  오프라인 1   │  점검중 1                 │ ← 요약 카드
├──────────┴───────────┴──────────────┴──────────────────────────┤
│ ID │ 그룹  │ 이름       │ IP 주소       │ 상태   │ 응답(ms)       │
│  1 │ 서버  │ Web-Server │ 192.168.1.10  │ 온라인  │ 3.2 ms      │  ← 초록
│  2 │ 서버  │ DB-Server  │ 192.168.1.11  │ 오프라인│    -         │ ← 빨강
│  3 │ 네트워크│ Gateway  │ 192.168.1.1   │ 온라인  │ 1.1 ms       │
├────────────────────────────────────────────────────────────────┤
│ [추가] [삭제] [새로고침] [이력] [CSV]                             │← 버튼 바
├────────────────────────────────────────────────────────────────┤
│  마지막 갱신: 14:23:05                    ● 모니터링 중           │  ← 상태 바
└────────────────────────────────────────────────────────────────┘
```

---

## 프로젝트 구조

```
network-monitor/
├── network_monitor.py     # 메인 애플리케이션 (단일 파일)
├── network_monitor.db     # SQLite DB (첫 실행 시 자동 생성)
├── requirements.txt
└── README.md
```

---

## 기술 스택

| 항목 | 내용 |
|------|------|
| 언어 | Python 3.8+ |
| GUI | Tkinter / ttk |
| DB | SQLite3 |
| 네트워크 | subprocess (ICMP Ping) |
| 멀티스레딩 | threading (UI 블로킹 방지) |
| 내보내기 | csv (표준 라이브러리) |

> 외부 라이브러리 없이 Python 표준 라이브러리만으로 동작합니다.

---

## 설치 및 실행

### 1. 저장소 클론
```bash
git clone https://github.com/<your-username>/network-monitor.git
cd network-monitor
```

### 2. 실행
```bash
python network_monitor.py
```

> 별도 pip 설치 없이 바로 실행 가능합니다.

---

## 사용 방법

1. **호스트 추가** — ` 호스트 추가` 버튼 → 이름·IP·그룹 입력
2. **즉시 확인** — ` 지금 새로고침` 버튼으로 전체 핑 실행
3. **자동 모니터링** — 갱신 주기 설정 후 ` 모니터링 시작` 클릭
4. **이력 조회** — 호스트 행 더블클릭 또는 ` 핑 이력 보기` 클릭
5. **내보내기** — ` CSV 내보내기`로 현재 상태 저장

---

## DB 스키마

```sql
-- 모니터링 대상 호스트
CREATE TABLE hosts (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    label       TEXT NOT NULL,       -- 표시 이름
    ip          TEXT NOT NULL,       -- IP 또는 호스트명
    group_name  TEXT DEFAULT '기본', -- 그룹 분류
    added_at    TEXT                 -- 등록 일시
);

-- 핑 이력 로그
CREATE TABLE ping_log (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    host_id     INTEGER,             -- hosts.id 참조
    status      TEXT,                -- 온라인 / 오프라인
    response_ms REAL,                -- 응답속도 (ms)
    checked_at  TEXT,                -- 확인 일시
    FOREIGN KEY (host_id) REFERENCES hosts(id)
);
```

---

##  주의사항

- Ping 실행에는 **관리자 권한**이 필요할 수 있습니다 (Windows: 일반 권한으로도 동작)
- 방화벽에서 ICMP를 차단한 경우 오프라인으로 표시될 수 있습니다
- 대량의 호스트(50개 이상) 모니터링 시 갱신 주기를 넉넉하게 설정 권장

---

##  향후 개선 계획

- [ ] 이메일 / 소리 알림 추가
- [ ] 응답속도 추이 그래프 (matplotlib)
- [ ] 포트 스캔 기능 연동
- [ ] 호스트 그룹별 필터 탭
- [ ] 모니터링 리포트 PDF 출력

---

##  라이선스

MIT License © 2026
