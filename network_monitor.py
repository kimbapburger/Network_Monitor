import tkinter as tk
from tkinter import ttk, messagebox, filedialog, simpledialog
import threading
import subprocess
import csv
import sqlite3
import platform
from datetime import datetime

# ── CONFIGURATION / 설정 ────────────────────────────────────────────────────

DB_NAME = "network_monitor.db"
DEFAULT_INTERVAL = 30        # Auto-refresh interval in seconds / 기본 자동 갱신 주기 (초)
PING_TIMEOUT = 1             # Ping timeout in seconds / Ping 타임아웃 (초)
OFFLINE_ALERT_COOLDOWN = 60  # Min seconds between repeated alerts / 반복 알림 최소 간격 (초)

# Status color scheme / 상태별 색상
STATUS_COLORS = {
    "온라인":  "#d4edda",   # green / 초록
    "오프라인": "#f8d7da",   # red / 빨강
    "점검중":  "#fff3cd",   # yellow / 노랑
}

# ── DATABASE / 데이터베이스 ──────────────────────────────────────────────────

def init_db():
    """
    Initialize DB: create hosts and ping_log tables.
    DB 초기화: 호스트 테이블과 핑 로그 테이블 생성.
    """
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()

    # Host list table / 호스트 목록 테이블
    cur.execute("""
    CREATE TABLE IF NOT EXISTS hosts (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        label       TEXT NOT NULL,       -- Display name / 표시 이름
        ip          TEXT NOT NULL,       -- IP or hostname / IP 또는 호스트명
        group_name  TEXT DEFAULT '기본', -- Group for organizing hosts / 그룹
        added_at    TEXT
    )
    """)

    # Ping history log table / 핑 이력 로그 테이블
    cur.execute("""
    CREATE TABLE IF NOT EXISTS ping_log (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        host_id     INTEGER,
        status      TEXT,               -- 온라인 / 오프라인
        response_ms REAL,               -- Response time in ms / 응답속도 (ms)
        checked_at  TEXT,
        FOREIGN KEY (host_id) REFERENCES hosts(id)
    )
    """)

    conn.commit()
    conn.close()


def get_hosts():
    """Return all hosts from DB. / DB에서 전체 호스트 목록 조회."""
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()
    cur.execute("SELECT id, label, ip, group_name, added_at FROM hosts ORDER BY group_name, label")
    rows = cur.fetchall()
    conn.close()
    return rows


def add_host(label, ip, group_name):
    """Insert a new host into DB. / 새 호스트 DB에 추가."""
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO hosts (label, ip, group_name, added_at) VALUES (?, ?, ?, ?)",
        (label, ip, group_name, now)
    )
    conn.commit()
    conn.close()


def delete_host(host_id):
    """Delete host and its ping history from DB. / 호스트 및 핑 이력 삭제."""
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()
    cur.execute("DELETE FROM ping_log WHERE host_id = ?", (host_id,))
    cur.execute("DELETE FROM hosts WHERE id = ?", (host_id,))
    conn.commit()
    conn.close()


def save_ping_log(host_id, status, response_ms):
    """Write a ping result to the log table. / 핑 결과를 로그 테이블에 기록."""
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO ping_log (host_id, status, response_ms, checked_at) VALUES (?, ?, ?, ?)",
        (host_id, status, response_ms, now)
    )
    conn.commit()
    conn.close()


def get_ping_history(host_id, limit=50):
    """Return the last N ping records for a host. / 특정 호스트의 최근 핑 이력 조회."""
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()
    cur.execute(
        "SELECT status, response_ms, checked_at FROM ping_log WHERE host_id=? ORDER BY id DESC LIMIT ?",
        (host_id, limit)
    )
    rows = cur.fetchall()
    conn.close()
    return rows


# ── PING ENGINE / 핑 엔진 ───────────────────────────────────────────────────

def ping_host(ip):
    """
    Ping a single IP. Returns (status, response_ms).
    단일 IP Ping. (상태, 응답속도ms) 반환.
    """
    system = platform.system()

    # Build OS-appropriate ping command / OS별 ping 명령어 구성
    if system == "Windows":
        cmd = ["ping", "-n", "1", "-w", str(PING_TIMEOUT * 1000), ip]
    else:
        cmd = ["ping", "-c", "1", "-W", str(PING_TIMEOUT), ip]

    start = datetime.now()
    try:
        result = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=PING_TIMEOUT + 1   # Safety timeout / 안전 타임아웃
        )
        elapsed = (datetime.now() - start).total_seconds() * 1000  # ms

        if result.returncode == 0:
            # Try to extract ms from ping output / 핑 출력에서 ms 추출 시도
            output = result.stdout.decode(errors="ignore")
            ms = parse_ping_ms(output, elapsed)
            return "온라인", round(ms, 1)
        else:
            return "오프라인", None

    except (subprocess.TimeoutExpired, FileNotFoundError):
        return "오프라인", None


def parse_ping_ms(output, fallback_ms):
    """
    Extract response time from ping output text.
    핑 출력 텍스트에서 응답시간 파싱.
    """
    import re
    # Windows: "time=10ms" or "시간=10ms" / 윈도우 출력 패턴
    match = re.search(r'[Tt]ime[<=](\d+\.?\d*)ms', output)
    if match:
        return float(match.group(1))
    # Linux/Mac: "time=10.3 ms" / 리눅스/맥 출력 패턴
    match = re.search(r'time=(\d+\.?\d*)\s*ms', output)
    if match:
        return float(match.group(1))
    return fallback_ms


# ── MAIN APPLICATION / 메인 애플리케이션 ────────────────────────────────────

class NetworkMonitorApp:
    """
    Main application class. Holds all state and UI.
    메인 앱 클래스. 상태와 UI를 모두 관리.
    """

    def __init__(self, root):
        self.root = root
        self.root.title("네트워크 모니터링 대시보드")
        self.root.geometry("1000x620")
        self.root.configure(bg="#1a1a2e")  # Dark navy background / 다크 네이비 배경
        self.root.resizable(True, True)

        # Runtime state / 런타임 상태
        self.host_status = {}      # {host_id: ("온라인"/"오프라인", ms)} 현재 상태 캐시
        self.alert_sent_at = {}    # {host_id: datetime} 마지막 알림 시각 (쿨다운용)
        self.is_monitoring = False # 자동 갱신 실행 중 여부
        self.monitor_thread = None
        self.interval_var = tk.IntVar(value=DEFAULT_INTERVAL)
        self.search_var = tk.StringVar()

        init_db()
        self._build_ui()
        self._refresh_table()

    # ── UI CONSTRUCTION / UI 구성 ────────────────────────────────────────────

    def _build_ui(self):
        """Build the full UI layout. / 전체 UI 레이아웃 구성."""
        self._build_toolbar()
        self._build_summary_bar()
        self._build_table()
        self._build_button_bar()
        self._build_statusbar()

    def _build_toolbar(self):
        """Top toolbar with title, search, and interval control. / 상단 툴바: 제목·검색·주기 설정."""
        bar = tk.Frame(self.root, bg="#16213e", pady=8)
        bar.pack(fill="x")

        tk.Label(bar, text="🌐  Network Monitor", bg="#16213e", fg="#e0e0e0",
                 font=("맑은 고딕", 15, "bold")).pack(side="left", padx=16)

        # Right side controls / 오른쪽 컨트롤
        right = tk.Frame(bar, bg="#16213e")
        right.pack(side="right", padx=12)

        # Auto-refresh interval / 자동 갱신 주기
        tk.Label(right, text="갱신 주기(초):", bg="#16213e", fg="#aaa",
                 font=("맑은 고딕", 9)).pack(side="left", padx=(0, 4))
        tk.Spinbox(right, from_=5, to=300, textvariable=self.interval_var,
                   width=5, font=("맑은 고딕", 9)).pack(side="left", padx=(0, 10))

        # Start / Stop monitoring buttons / 모니터링 시작·정지 버튼
        self.btn_start = tk.Button(right, text="▶ 모니터링 시작",
                                   command=self._start_monitoring,
                                   bg="#0f3460", fg="#4fc3f7",
                                   font=("맑은 고딕", 9, "bold"),
                                   relief="flat", padx=8, pady=4, cursor="hand2")
        self.btn_start.pack(side="left", padx=2)

        self.btn_stop = tk.Button(right, text="■ 정지",
                                  command=self._stop_monitoring,
                                  bg="#3a0000", fg="#ef9a9a",
                                  font=("맑은 고딕", 9),
                                  relief="flat", padx=8, pady=4,
                                  cursor="hand2", state="disabled")
        self.btn_stop.pack(side="left", padx=2)

        # Search box / 검색창
        search_frame = tk.Frame(bar, bg="#16213e")
        search_frame.pack(side="right", padx=8)
        tk.Entry(search_frame, textvariable=self.search_var, width=20,
                 bg="#0f3460", fg="white", insertbackground="white",
                 relief="flat", font=("맑은 고딕", 9)).pack(side="left", padx=(0, 4), ipady=4)
        tk.Label(search_frame, text="🔍", bg="#16213e", fg="#aaa").pack(side="left")
        self.search_var.trace_add("write", lambda *_: self._refresh_table())

    def _build_summary_bar(self):
        """Summary cards: total / online / offline counts. / 요약 카드: 전체·온라인·오프라인 수."""
        self.summary_frame = tk.Frame(self.root, bg="#1a1a2e", pady=8)
        self.summary_frame.pack(fill="x", padx=16)

        self.lbl_total   = self._summary_card("전체",    "0", "#4fc3f7")
        self.lbl_online  = self._summary_card("온라인",  "0", "#81c784")
        self.lbl_offline = self._summary_card("오프라인", "0", "#e57373")
        self.lbl_checking = self._summary_card("점검중",  "0", "#ffb74d")

    def _summary_card(self, label, value, color):
        """Create a single summary stat card. / 요약 카드 위젯 하나 생성."""
        card = tk.Frame(self.summary_frame, bg="#16213e", padx=20, pady=8,
                        relief="flat", bd=0)
        card.pack(side="left", padx=(0, 10))

        lbl_val = tk.Label(card, text=value, bg="#16213e", fg=color,
                           font=("맑은 고딕", 22, "bold"))
        lbl_val.pack()
        tk.Label(card, text=label, bg="#16213e", fg="#888",
                 font=("맑은 고딕", 9)).pack()
        return lbl_val

    def _build_table(self):
        """Main Treeview table for host status. / 호스트 상태 메인 트리뷰 표."""
        frame = tk.Frame(self.root, bg="#1a1a2e")
        frame.pack(fill="both", expand=True, padx=16, pady=(0, 4))

        # Custom dark style for Treeview / 트리뷰 다크 테마 스타일 설정
        style = ttk.Style()
        style.theme_use("clam")
        style.configure("Dark.Treeview",
                         background="#0f3460",
                         foreground="#e0e0e0",
                         fieldbackground="#0f3460",
                         rowheight=26,
                         font=("맑은 고딕", 10))
        style.configure("Dark.Treeview.Heading",
                         background="#16213e",
                         foreground="#4fc3f7",
                         font=("맑은 고딕", 10, "bold"),
                         relief="flat")
        style.map("Dark.Treeview",
                  background=[("selected", "#1565c0")],
                  foreground=[("selected", "white")])

        cols = ("ID", "그룹", "이름", "IP 주소", "상태", "응답속도(ms)", "마지막 확인")
        self.tree = ttk.Treeview(frame, columns=cols, show="headings",
                                 style="Dark.Treeview")

        col_widths = (40, 90, 150, 140, 80, 110, 155)
        for col, w in zip(cols, col_widths):
            self.tree.heading(col, text=col)
            self.tree.column(col, width=w, anchor="center")

        # Status color tags / 상태별 색상 태그
        self.tree.tag_configure("온라인",  background="#1b3a2a", foreground="#81c784")
        self.tree.tag_configure("오프라인", background="#3a1a1a", foreground="#e57373")
        self.tree.tag_configure("점검중",  background="#2a2a1a", foreground="#ffb74d")

        vsb = ttk.Scrollbar(frame, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=vsb.set)

        self.tree.pack(side="left", fill="both", expand=True)
        vsb.pack(side="right", fill="y")

        # Double-click to view ping history / 더블클릭 시 핑 이력 팝업
        self.tree.bind("<Double-1>", self._show_history)

    def _build_button_bar(self):
        """Action buttons below the table. / 표 아래 액션 버튼 바."""
        bar = tk.Frame(self.root, bg="#1a1a2e", pady=6)
        bar.pack(fill="x", padx=16)

        btns = [
            ("➕ 호스트 추가",    self._open_add_host,    "#0d6efd"),
            ("🗑 호스트 삭제",    self._delete_selected,  "#dc3545"),
            ("🔄 지금 새로고침",  self._ping_all_now,     "#198754"),
            ("📋 핑 이력 보기",   self._show_history,     "#6f42c1"),
            ("📄 CSV 내보내기",   self._export_csv,       "#fd7e14"),
        ]
        for text, cmd, color in btns:
            tk.Button(bar, text=text, command=cmd,
                      bg=color, fg="white",
                      font=("맑은 고딕", 9),
                      relief="flat", padx=10, pady=5,
                      cursor="hand2").pack(side="left", padx=4)

    def _build_statusbar(self):
        """Bottom status bar with last refresh time. / 하단 상태 바: 마지막 갱신 시각."""
        bar = tk.Frame(self.root, bg="#16213e", pady=4)
        bar.pack(fill="x", side="bottom")

        self.lbl_status = tk.Label(bar, text="대기 중...", bg="#16213e", fg="#888",
                                   font=("맑은 고딕", 9))
        self.lbl_status.pack(side="left", padx=12)

        self.lbl_monitor_state = tk.Label(bar, text="● 모니터링 중지",
                                          bg="#16213e", fg="#e57373",
                                          font=("맑은 고딕", 9, "bold"))
        self.lbl_monitor_state.pack(side="right", padx=12)

    # ── TABLE REFRESH / 표 갱신 ──────────────────────────────────────────────

    def _refresh_table(self):
        """Reload host list from DB and repaint the table. / DB에서 호스트 목록 재조회 후 표 갱신."""
        keyword = self.search_var.get().lower()

        for item in self.tree.get_children():
            self.tree.delete(item)

        hosts = get_hosts()
        online_count = offline_count = checking_count = 0

        for host in hosts:
            hid, label, ip, group, added_at = host

            # Apply search filter / 검색 필터 적용
            if keyword and keyword not in label.lower() and keyword not in ip.lower() and keyword not in group.lower():
                continue

            # Get cached status or default / 캐시된 상태 또는 기본값
            status, ms = self.host_status.get(hid, ("점검중", None))
            ms_str = f"{ms} ms" if ms is not None else "-"
            last_check = self._last_check_time(hid)

            tag = status
            if status == "온라인":   online_count += 1
            elif status == "오프라인": offline_count += 1
            else:                     checking_count += 1

            self.tree.insert("", tk.END,
                             values=(hid, group, label, ip, status, ms_str, last_check),
                             tags=(tag,))

        # Update summary cards / 요약 카드 갱신
        total = len([h for h in hosts if not keyword or keyword in h[1].lower() or keyword in h[2].lower()])
        self.lbl_total.config(text=str(total))
        self.lbl_online.config(text=str(online_count))
        self.lbl_offline.config(text=str(offline_count))
        self.lbl_checking.config(text=str(checking_count))

    def _last_check_time(self, host_id):
        """Get the timestamp of the most recent ping for a host. / 가장 최근 핑 시각 조회."""
        conn = sqlite3.connect(DB_NAME)
        cur = conn.cursor()
        cur.execute(
            "SELECT checked_at FROM ping_log WHERE host_id=? ORDER BY id DESC LIMIT 1",
            (host_id,)
        )
        row = cur.fetchone()
        conn.close()
        return row[0] if row else "-"

    # ── PING LOGIC / 핑 로직 ────────────────────────────────────────────────

    def _ping_all_now(self):
        """
        Ping all hosts in a background thread to avoid freezing the UI.
        UI가 멈추지 않도록 백그라운드 스레드에서 전체 호스트 핑 실행.
        """
        hosts = get_hosts()
        if not hosts:
            messagebox.showinfo("알림", "등록된 호스트가 없습니다.")
            return

        self.lbl_status.config(text="⏳ 핑 확인 중...")
        self.root.update_idletasks()

        def run():
            for host in hosts:
                hid, label, ip, group, _ = host
                # Update UI to show "점검중" / 점검 중 상태 표시
                self.host_status[hid] = ("점검중", None)
                self.root.after(0, self._refresh_table)

                status, ms = ping_host(ip)
                self.host_status[hid] = (status, ms)
                save_ping_log(hid, status, ms)

                # Alert if host just went offline / 오프라인 감지 시 알림
                if status == "오프라인":
                    self._maybe_alert(hid, label, ip)

            # Final UI update on main thread / 최종 UI 갱신 (메인 스레드에서)
            self.root.after(0, self._on_ping_complete)

        threading.Thread(target=run, daemon=True).start()

    def _on_ping_complete(self):
        """Called after all pings finish. / 전체 핑 완료 후 호출."""
        now = datetime.now().strftime("%H:%M:%S")
        self.lbl_status.config(text=f"마지막 갱신: {now}")
        self._refresh_table()

    def _maybe_alert(self, host_id, label, ip):
        """
        Show offline alert popup with cooldown to avoid spam.
        쿨다운 적용으로 반복 알림 방지 후 오프라인 팝업 표시.
        """
        now = datetime.now()
        last = self.alert_sent_at.get(host_id)

        # Only alert if cooldown has passed / 쿨다운 지난 경우에만 알림
        if last is None or (now - last).total_seconds() > OFFLINE_ALERT_COOLDOWN:
            self.alert_sent_at[host_id] = now
            # Run popup on main thread / 팝업은 메인 스레드에서 실행
            self.root.after(0, lambda: messagebox.showwarning(
                "⚠️ 오프라인 감지",
                f"호스트가 응답하지 않습니다!\n\n이름: {label}\nIP: {ip}\n\n확인 시각: {now.strftime('%H:%M:%S')}"
            ))

    # ── AUTO MONITORING / 자동 모니터링 ─────────────────────────────────────

    def _start_monitoring(self):
        """Start the auto-refresh loop. / 자동 갱신 루프 시작."""
        if self.is_monitoring:
            return
        self.is_monitoring = True
        self.btn_start.config(state="disabled")
        self.btn_stop.config(state="normal")
        self.lbl_monitor_state.config(text="● 모니터링 중", fg="#81c784")
        self._monitoring_loop()

    def _stop_monitoring(self):
        """Stop the auto-refresh loop. / 자동 갱신 루프 정지."""
        self.is_monitoring = False
        self.btn_start.config(state="normal")
        self.btn_stop.config(state="disabled")
        self.lbl_monitor_state.config(text="● 모니터링 중지", fg="#e57373")

    def _monitoring_loop(self):
        """
        Recursive scheduler: ping all, then schedule next run.
        재귀 스케줄러: 핑 실행 후 다음 실행 예약.
        """
        if not self.is_monitoring:
            return
        self._ping_all_now()
        interval_ms = self.interval_var.get() * 1000   # seconds → ms / 초 → 밀리초
        self.root.after(interval_ms, self._monitoring_loop)

    # ── HOST MANAGEMENT / 호스트 관리 ───────────────────────────────────────

    def _open_add_host(self):
        """Popup form to add a new host. / 새 호스트 추가 팝업 폼."""
        win = tk.Toplevel(self.root)
        win.title("호스트 추가")
        win.geometry("360x260")
        win.configure(bg="#1a1a2e")
        win.grab_set()

        fields = [("이름 (예: 게이트웨이)", ""), ("IP 주소 (예: 192.168.1.1)", ""), ("그룹", "기본")]
        entries = []

        for i, (label, default) in enumerate(fields):
            tk.Label(win, text=label, bg="#1a1a2e", fg="#ccc",
                     font=("맑은 고딕", 10)).grid(row=i, column=0, padx=16, pady=8, sticky="w")
            e = tk.Entry(win, width=26, bg="#0f3460", fg="white",
                         insertbackground="white", font=("맑은 고딕", 10))
            e.insert(0, default)
            e.grid(row=i, column=1, padx=8, pady=8)
            entries.append(e)

        def save():
            label_val = entries[0].get().strip()
            ip_val    = entries[1].get().strip()
            group_val = entries[2].get().strip() or "기본"

            if not label_val or not ip_val:
                messagebox.showwarning("입력 오류", "이름과 IP를 모두 입력하세요.", parent=win)
                return

            add_host(label_val, ip_val, group_val)
            self._refresh_table()
            win.destroy()

        tk.Button(win, text="추가", command=save,
                  bg="#0d6efd", fg="white", font=("맑은 고딕", 10),
                  relief="flat", padx=16, pady=6).grid(
            row=3, column=0, columnspan=2, pady=16)

    def _delete_selected(self):
        """Delete the selected host after confirmation. / 선택 호스트 확인 후 삭제."""
        sel = self.tree.selection()
        if not sel:
            messagebox.showwarning("선택 없음", "삭제할 호스트를 선택하세요.")
            return

        values = self.tree.item(sel[0])["values"]
        hid, label = values[0], values[2]

        if messagebox.askyesno("삭제 확인", f"'{label}' 호스트를 삭제하시겠습니까?\n핑 이력도 함께 삭제됩니다."):
            delete_host(hid)
            self.host_status.pop(hid, None)
            self._refresh_table()

    # ── PING HISTORY / 핑 이력 ───────────────────────────────────────────────

    def _show_history(self, event=None):
        """Show ping history popup for the selected host. / 선택 호스트 핑 이력 팝업."""
        sel = self.tree.selection()
        if not sel:
            messagebox.showwarning("선택 없음", "이력을 볼 호스트를 선택하세요.")
            return

        values = self.tree.item(sel[0])["values"]
        hid, label, ip = values[0], values[2], values[3]

        history = get_ping_history(hid)

        win = tk.Toplevel(self.root)
        win.title(f"핑 이력 — {label} ({ip})")
        win.geometry("480x380")
        win.configure(bg="#1a1a2e")

        tk.Label(win, text=f"🖧  {label}  |  {ip}",
                 bg="#1a1a2e", fg="#4fc3f7",
                 font=("맑은 고딕", 12, "bold")).pack(pady=10)

        cols = ("상태", "응답속도(ms)", "확인 시각")
        tree = ttk.Treeview(win, columns=cols, show="headings", style="Dark.Treeview", height=14)
        for col in cols:
            tree.heading(col, text=col)
            tree.column(col, anchor="center", width=140)

        tree.tag_configure("온라인",  background="#1b3a2a", foreground="#81c784")
        tree.tag_configure("오프라인", background="#3a1a1a", foreground="#e57373")

        if not history:
            tree.insert("", tk.END, values=("기록 없음", "-", "-"))
        else:
            for status, ms, checked_at in history:
                ms_str = f"{ms} ms" if ms is not None else "-"
                tree.insert("", tk.END, values=(status, ms_str, checked_at), tags=(status,))

        tree.pack(fill="both", expand=True, padx=12, pady=(0, 12))

    # ── CSV EXPORT / CSV 내보내기 ────────────────────────────────────────────

    def _export_csv(self):
        """Export current table view to CSV. / 현재 표 데이터를 CSV로 내보내기."""
        rows = [self.tree.item(i)["values"] for i in self.tree.get_children()]
        if not rows:
            messagebox.showwarning("내보내기", "내보낼 데이터가 없습니다.")
            return

        path = filedialog.asksaveasfilename(
            defaultextension=".csv",
            filetypes=[("CSV 파일", "*.csv"), ("모든 파일", "*.*")],
            initialfile=f"network_status_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
        )
        if not path:
            return

        # utf-8-sig for Korean Excel compatibility / 한글 Excel 호환 BOM 인코딩
        with open(path, "w", newline="", encoding="utf-8-sig") as f:
            writer = csv.writer(f)
            writer.writerow(["ID", "그룹", "이름", "IP 주소", "상태", "응답속도(ms)", "마지막 확인"])
            writer.writerows(rows)

        messagebox.showinfo("완료", f"CSV 저장 완료:\n{path}")


# ── ENTRY POINT / 진입점 ────────────────────────────────────────────────────

def main():
    root = tk.Tk()
    app = NetworkMonitorApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
