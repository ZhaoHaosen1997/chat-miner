"""
v1.5.0 Chat-Miner GUI 窗口 — CustomTkinter + 系统托盘
实时统计 / 启动进度 / 托盘最小化 / 查看日志
"""
import os
import sys
import json
import ctypes
import threading
import subprocess
import logging
import urllib.request

logger = logging.getLogger(__name__)

# ---- 主题色 (indigo) ----
ACCENT = "#6366f1"
ACCENT_HOVER = "#4f46e5"

# ---- Windows 系统托盘 (ctypes, 零依赖) ----
WM_USER = 1024
WM_TRAY = WM_USER + 1
NIM_ADD, NIM_DELETE, NIM_MODIFY = 0, 2, 1
NIF_MESSAGE, NIF_ICON, NIF_TIP, NIF_INFO = 1, 2, 4, 16
WM_LBUTTONDBLCLK = 0x0203
WM_RBUTTONUP = 0x0205

class SystemTray:
    def __init__(self, icon_path: str, tip: str, on_restore, on_open, on_quit):
        self._icon_path = icon_path
        self._tip = tip
        self._on_restore = on_restore
        self._on_open = on_open
        self._on_quit = on_quit
        self._hwnd = None
        self._nid = None

    def create(self, hwnd):
        self._hwnd = hwnd
        icon = ctypes.windll.shell32.ExtractIconW(0, self._icon_path, 0)

        class NOTIFYICONDATA(ctypes.Structure):
            _fields_ = [
                ("cbSize", ctypes.c_uint32), ("hWnd", ctypes.c_void_p),
                ("uID", ctypes.c_uint32), ("uFlags", ctypes.c_uint32),
                ("uCallbackMessage", ctypes.c_uint32), ("hIcon", ctypes.c_void_p),
                ("szTip", ctypes.c_wchar * 128), ("dwState", ctypes.c_uint32),
                ("dwStateMask", ctypes.c_uint32), ("szInfo", ctypes.c_wchar * 256),
                ("uTimeoutOrVersion", ctypes.c_uint32), ("szInfoTitle", ctypes.c_wchar * 64),
                ("dwInfoFlags", ctypes.c_uint32)
            ]

        nid = NOTIFYICONDATA()
        nid.cbSize = ctypes.sizeof(NOTIFYICONDATA)
        nid.hWnd = hwnd
        nid.uID = 1
        nid.uFlags = NIF_MESSAGE | NIF_ICON | NIF_TIP
        nid.uCallbackMessage = WM_TRAY
        nid.hIcon = icon
        nid.szTip = self._tip
        self._nid = nid
        ctypes.windll.shell32.Shell_NotifyIconW(NIM_ADD, ctypes.byref(nid))

    def remove(self):
        if self._nid:
            ctypes.windll.shell32.Shell_NotifyIconW(NIM_DELETE, ctypes.byref(self._nid))
            self._nid = None

    def handle_msg(self, msg):
        if msg == WM_LBUTTONDBLCLK:
            self._on_restore()
        elif msg == WM_RBUTTONUP:
            self._show_menu()

    def _show_menu(self):
        import tkinter as tk
        menu = tk.Menu(None, tearoff=0, font=("Microsoft YaHei", 9),
                       bg="white", fg="#1e293b")
        menu.add_command(label="显示窗口", command=self._on_restore)
        menu.add_command(label="打开浏览器", command=self._on_open)
        menu.add_separator()
        menu.add_command(label="退出", command=self._on_quit)
        try:
            menu.tk_popup(*menu.tk.call("winfo", "pointerxy", "."))
        finally:
            menu.grab_release()


# ---- 自定义标题栏（隐藏系统标题栏用） ----
class LogWindow:
    def __init__(self, title="Chat-Miner", port=8856):
        self.title = title
        self.port = port
        self._running = False
        self._root = None
        self._tray = None
        self._window_visible = True
        # 统计
        self._stats_group = None
        self._stats_msg = None
        self._stats_analyzed = None
        self._progress = None
        self._status_label = None

    def start(self):
        import customtkinter as ctk

        logger.info("LogWindow.start: 初始化 CustomTkinter...")
        ctk.set_appearance_mode("light")
        ctk.set_default_color_theme("blue")

        logger.info("LogWindow.start: 创建 CTk 窗口...")
        self._root = ctk.CTk()
        root = self._root
        self._running = True

        from config import config
        root.title(f"Chat-Miner v{config.VERSION}")
        root.geometry("420x340")
        root.minsize(320, 300)
        root.configure(fg_color="#f8fafc")

        try:
            root.iconbitmap("assets/icon.ico")
        except Exception:
            pass

        # ---- 系统托盘 ----
        icon_path = os.path.join(os.path.dirname(os.path.abspath(sys.argv[0])),
                                 "assets", "icon.ico")
        if not os.path.exists(icon_path):
            icon_path = os.path.join(os.getcwd(), "assets", "icon.ico")
        if not os.path.exists(icon_path):
            icon_path = sys.executable  # fallback

        # 暂不启用托盘（v1.5.0: WndProc 子类化在 64 位有兼容问题）
        self._icon_path = icon_path

        # ---- 主卡片 ----
        card = ctk.CTkFrame(root, fg_color="white", corner_radius=16,
                            border_color="#e2e8f0", border_width=1)
        card.pack(fill="both", expand=True, padx=16, pady=16)

        # 图标
        ctk.CTkLabel(card, text="💬", font=("Segoe UI", 32),
                     text_color=ACCENT).pack(pady=(20, 4))

        # 标题
        ctk.CTkLabel(card, text="Chat-Miner", font=("Microsoft YaHei", 16, "bold"),
                     text_color="#1e293b").pack()
        from config import config
        ctk.CTkLabel(card, text=f"v{config.VERSION} · 群聊内容分析", font=ctk.CTkFont(family="Microsoft YaHei", size=12),
                     text_color="#94a3b8").pack(pady=(0, 10))

        # ---- 启动进度条 ----
        self._progress = ctk.CTkProgressBar(card, width=260, height=6,
                                            corner_radius=3, progress_color=ACCENT,
                                            fg_color="#e2e8f0")
        self._progress.pack(pady=(4, 6))
        self._progress.set(0)

        # ---- 状态文字 ----
        self._status_label = ctk.CTkLabel(card, text="正在初始化...",
                                          font=ctk.CTkFont(family="Microsoft YaHei", size=11), text_color="#94a3b8")
        self._status_label.pack(pady=(0, 6))

        # ---- 统计区（初始隐藏） ----
        stats_frame = ctk.CTkFrame(card, fg_color="#f8fafc", corner_radius=10)
        stats_frame.pack(fill="x", padx=24, pady=(4, 10))

        self._stats_group = ctk.CTkLabel(stats_frame, text="群: -",
                                         font=ctk.CTkFont(family="Microsoft YaHei", size=12), text_color="#475569")
        self._stats_group.grid(row=0, column=0, padx=10, pady=6, sticky="w")
        self._stats_msg = ctk.CTkLabel(stats_frame, text="消息: -",
                                       font=ctk.CTkFont(family="Microsoft YaHei", size=12), text_color="#475569")
        self._stats_msg.grid(row=0, column=1, padx=10, pady=6, sticky="w")
        self._stats_analyzed = ctk.CTkLabel(stats_frame, text="分析: -",
                                            font=ctk.CTkFont(family="Microsoft YaHei", size=12), text_color="#475569")
        self._stats_analyzed.grid(row=0, column=2, padx=10, pady=6, sticky="w")
        stats_frame.grid_columnconfigure((0, 1, 2), weight=1)

        # ---- 按钮（等宽居中） ----
        BTN_W = 120
        btn_font = ctk.CTkFont(family="Microsoft YaHei", size=12, weight="normal")
        btn_row = ctk.CTkFrame(card, fg_color="transparent")
        btn_row.pack(pady=(6, 0))

        ctk.CTkButton(btn_row, text="打开浏览器", width=BTN_W, height=38,
                       corner_radius=10, fg_color=ACCENT, hover_color=ACCENT_HOVER,
                       font=btn_font, command=self._open_browser
                       ).pack(side="left", padx=4)

        ctk.CTkButton(btn_row, text="查看日志", width=BTN_W, height=38,
                       corner_radius=10, fg_color="transparent", text_color=ACCENT,
                       border_color=ACCENT, border_width=1.5, hover_color="#eef2ff",
                       font=btn_font, command=self._open_log
                       ).pack(side="left", padx=4)

        ctk.CTkButton(btn_row, text="检查更新", width=BTN_W, height=38,
                       corner_radius=10, fg_color="transparent", text_color="#64748b",
                       border_color="#cbd5e1", border_width=1.5, hover_color="#f8fafc",
                       font=btn_font, command=self._check_update
                       ).pack(side="left", padx=4)

        # 快捷键
        root.bind("<Control-l>", lambda e: self._open_log())
        root.bind("<Control-b>", lambda e: self._open_browser())
        root.protocol("WM_DELETE_WINDOW", self._shutdown)

        # 启动阶段
        self._simulate_startup()
        root.mainloop()

    def _simulate_startup(self):
        """模拟启动进度（实际进度由 main.py 驱动）"""
        steps = [
            (0.25, "初始化数据库..."),
            (0.50, "加载群数据..."),
            (0.75, "启动服务..."),
            (1.0,  ""),
        ]

        def _step(i=0):
            if i >= len(steps):
                self._progress.pack_forget()
                self._status_label.configure(text="● 服务运行中")
                self._start_stats_poll()
                self._open_browser()
                return
            val, text = steps[i]
            self._progress.set(val)
            if text:
                self._status_label.configure(text=text)
            self._root.after(400, lambda: _step(i + 1))

        self._root.after(500, lambda: _step())

    def _start_stats_poll(self):
        """轮询 API 获取实时统计"""
        from config import config

        # 不走系统代理，否则 localhost 请求可能被路由到代理服务器导致连接失败
        _opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))

        def _poll():
            if not self._running:
                return
            try:
                req = urllib.request.Request(
                    f"http://127.0.0.1:{self.port}/api/stats/global",
                    headers={"User-Agent": f"chat-miner-gui/{config.VERSION}"})
                with _opener.open(req, timeout=3) as resp:
                    data = json.loads(resp.read())
                    s = data.get("data", {})
                # 直接同步更新（_poll 已在 tkinter 主线程）
                self._update_stats(
                    s.get("active_groups", "-"),
                    s.get("total_messages", "-"),
                    s.get("total_analyzed_days", "-"),
                )
            except Exception as e:
                logger.warning("GUI 统计轮询失败: %s", e)
            # v1.5.4: 从 DB 读取轮询间隔，fallback 30s
            try:
                from models.database import get_app_setting
                s = get_app_setting("poll_interval_stats_s")
                interval_s = int(s["value"]) if s and s.get("value") else 30
            except Exception:
                interval_s = 30
            self._root.after(interval_s * 1000, _poll)

        self._root.after(2000, _poll)

    def _update_stats(self, groups, msgs, analyzed):
        try:
            if self._stats_group:
                self._stats_group.configure(text=f"群: {groups}")
            if self._stats_msg:
                self._stats_msg.configure(text=f"消息: {msgs}")
            if self._stats_analyzed:
                self._stats_analyzed.configure(text=f"分析: {analyzed}")
        except Exception as e:
            logger.warning("GUI 统计标签更新失败: %s", e)

    def write_log(self, text: str, color: str = ""):
        pass  # 日志走文件

    def set_status(self, text: str, ok: bool = True):
        if self._root:
            self._root.after(0, lambda: self._status_label.configure(
                text=text, text_color="#22c55e" if ok else "#ef4444"))

    def _open_browser(self):
        import webbrowser
        webbrowser.open(f"http://localhost:{self.port}")

    def _open_log(self):
        log_path = os.path.join("logs", "chat_miner.log")
        # PowerShell 实时 tail + 日志级别着色 + HTTP 状态码着色
        color_script = (
            f'Get-Content -Path "{log_path}" -Wait -Tail 50 -Encoding UTF8 | '
            f'ForEach-Object {{ '
            f'if ($_ -match \\"- ERROR -\\" -or $_ -match \\" 5\\\\d\\\\d \\") {{ Write-Host $_ -ForegroundColor Red }} '
            f'elseif ($_ -match \\"- WARNING -\\" -or $_ -match \\" 4\\\\d\\\\d \\") {{ Write-Host $_ -ForegroundColor Yellow }} '
            f'elseif ($_ -match \\" 2\\\\d\\\\d \\" -or $_ -match \\" 3\\\\d\\\\d \\") {{ Write-Host $_ -ForegroundColor Green }} '
            f'elseif ($_ -match \\"- DEBUG -\\") {{ Write-Host $_ -ForegroundColor DarkGray }} '
            f'else {{ Write-Host $_ -ForegroundColor Gray }} }}'
        )
        subprocess.Popen(
            f'start "Chat-Miner 日志" powershell -NoExit -Command "{color_script}"',
            shell=True)

    def _check_update(self):
        """检查更新（后台线程，弹窗提示）"""
        from services.updater import check_update
        try:
            from config import config
            current = config.VERSION
        except Exception:
            current = "0.0.0"

        def _run():
            result = check_update(current)
            self._root.after(0, lambda: self._show_update_result(result))

        threading.Thread(target=_run, daemon=True).start()

    def _show_update_result(self, result):
        from tkinter import messagebox
        if result.error:
            messagebox.showwarning("检查更新", f"检查失败\n{result.error}")
        elif result.has_update:
            ok = messagebox.askyesno(
                "发现新版本",
                f"发现新版本 {result.latest}\n当前版本 {result.current}\n\n是否前往下载？")
            if ok:
                import webbrowser
                webbrowser.open(result.url or "https://github.com/ZhaoHaosen1997/chat-miner/releases")
        else:
            messagebox.showinfo("检查更新", f"已是最新版本\n{result.current}")

    def _minimize_to_tray(self):
        self._root.withdraw()
        self._window_visible = False

    def _restore(self):
        self._root.deiconify()
        self._root.lift()
        self._root.focus_force()
        self._window_visible = True

    def _shutdown(self):
        self._running = False
        try:
            if self._tray:
                self._tray.remove()
            self._root.destroy()
        except Exception:
            pass
        os._exit(0)


_log_window = None


def get_log_window(title: str = "Chat-Miner", port: int = 8856) -> LogWindow:
    global _log_window
    if _log_window is None:
        _log_window = LogWindow(title, port)
    return _log_window
