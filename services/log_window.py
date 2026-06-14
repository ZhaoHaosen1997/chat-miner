"""
v1.4.0 Chat-Miner GUI 窗口
轻量卡片风格，日志通过外部 cmd 窗口查看
仅在 PyInstaller frozen 模式下启用
"""
import sys
import os
import subprocess
import threading
import logging
import queue

logger = logging.getLogger(__name__)

BG       = "#f8fafc"
CARD     = "#ffffff"
ACCENT   = "#6366f1"
ACCENT2  = "#818cf8"
TEXT     = "#1e293b"
TEXT_DIM = "#64748b"
BORDER   = "#e2e8f0"
GREEN    = "#22c55e"
RED      = "#ef4444"
FONT     = ("Microsoft YaHei", 10)
FONT_SM  = ("Microsoft YaHei", 9)
FONT_BIG = ("Microsoft YaHei", 13, "bold")


class LogWindow:
    """轻量卡片风格 GUI 窗口"""

    def __init__(self, title: str = "Chat-Miner", port: int = 8856):
        self.title = title
        self.port = port
        self._tk = None
        self._dot = None
        self._status_text = None
        self._running = False
        self._log_path = None

    def start(self):
        import tkinter as tk

        self._tk = tk.Tk()
        self._running = True
        root = self._tk

        root.title(f"Chat-Miner v1.4.0")
        root.geometry("420x300")
        root.minsize(340, 240)
        root.resizable(True, True)
        root.configure(bg=BG)

        try:
            root.iconbitmap("assets/icon.ico")
        except Exception:
            pass

        card = tk.Frame(root, bg=CARD, highlightbackground=BORDER,
                        highlightthickness=1, bd=0)
        card.pack(fill="both", expand=True, padx=20, pady=20)

        # 图标
        tk.Label(card, text="💬", font=("Segoe UI", 36), bg=CARD).pack(pady=(28, 8))

        # 标题
        tk.Label(card, text="Chat-Miner", font=FONT_BIG, bg=CARD, fg=TEXT).pack()
        tk.Label(card, text=f"v1.4.0 · 群聊内容分析", font=FONT_SM,
                 bg=CARD, fg=TEXT_DIM).pack(pady=(2, 12))

        # 状态
        row = tk.Frame(card, bg=CARD)
        row.pack(pady=(4, 10))
        self._dot = tk.Label(row, text="●", font=("Segoe UI", 8), bg=CARD, fg=GREEN)
        self._dot.pack(side="left", padx=(0, 6))
        self._status_text = tk.Label(row, text=f"服务运行中 · 端口 {self.port}",
                                      font=FONT, bg=CARD, fg=TEXT_DIM)
        self._status_text.pack(side="left")

        # 按钮
        btn_row = tk.Frame(card, bg=CARD)
        btn_row.pack(pady=(4, 0))
        self._btn(btn_row, "  打开浏览器  ", self._open_browser, True)
        self._btn(btn_row, "  查看日志  ", self._open_log)
        self._btn(btn_row, "  退出  ", self._shutdown)

        # 快捷键
        root.bind("<Control-l>", lambda e: self._open_log())
        root.bind("<Control-q>", lambda e: self._shutdown())
        root.protocol("WM_DELETE_WINDOW", self._minimize)

        root.mainloop()

    def _btn(self, parent, text, cmd, primary=False):
        import tkinter as tk
        bg = ACCENT if primary else CARD
        fg = "white" if primary else ACCENT
        bd = 0 if primary else 1
        b = tk.Button(parent, text=text, command=cmd,
                      font=FONT_SM, bg=bg, fg=fg, bd=bd,
                      activebackground=ACCENT2 if primary else "#f1f5f9",
                      activeforeground="white" if primary else ACCENT,
                      padx=18, pady=5, cursor="hand2",
                      highlightbackground=BORDER if not primary else None)
        b.pack(side="left", padx=4)

    def write_log(self, text: str, color: str = ""):
        pass  # 日志走文件，GUI 不展示

    def set_status(self, text: str, ok: bool = True):
        if self._tk:
            self._tk.after(0, lambda: self._set_status(text, ok))

    def _set_status(self, text: str, ok: bool = True):
        try:
            self._status_text.configure(text=text)
            self._dot.configure(fg=GREEN if ok else RED)
        except Exception:
            pass

    def _open_browser(self):
        import webbrowser
        webbrowser.open(f"http://localhost:{self.port}")

    def _open_log(self):
        """打开外部 cmd 窗口，用 PowerShell 实时 tail 日志"""
        log_path = self._log_path or os.path.join(
            os.path.dirname(os.path.abspath(sys.argv[0])), "logs", "chat_miner.log")
        if not os.path.exists(log_path):
            # 尝试相对于 cwd 的路径
            log_path = os.path.join("logs", "chat_miner.log")
        ps_cmd = (
            f'Get-Content -Path "{log_path}" -Wait -Tail 30 '
            f'-Encoding UTF8'
        )
        cmd = f'start "Chat-Miner 日志" powershell -NoExit -Command "{ps_cmd}"'
        subprocess.Popen(cmd, shell=True)

    def _minimize(self):
        self._tk.iconify()

    def _shutdown(self):
        self._running = False
        try:
            self._tk.destroy()
        except Exception:
            pass
        os._exit(0)


_log_window = None


def get_log_window(title: str = "Chat-Miner", port: int = 8856) -> LogWindow:
    global _log_window
    if _log_window is None:
        _log_window = LogWindow(title, port)
    return _log_window
