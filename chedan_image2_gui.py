"""
GPT Image Generation UI Panel - Stress Test & Batch Generation
Usage: python gpt_image_ui.py
"""
import tkinter as tk
from tkinter import ttk, filedialog, messagebox, scrolledtext
import httpx
import base64
import json
import time
import os
import io
import re
import sys
import subprocess
import threading
import queue
import tempfile
import configparser
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime

try:
    from PIL import Image, ImageOps, ImageTk
    HAS_PIL = True
except ImportError:
    HAS_PIL = False

BASE_URL = "https://sp.chedankj.com/v1"
REQUEST_TIMEOUT = 600
RETRIES = 3
RETRY_STATUSES = {502, 504, 522, 524}
LOGO_FILENAME = "chedankj-cd-egg-solid-logo.png"
MAX_EDIT_INPUT_BYTES = 4 * 1024 * 1024

COLORS = {
    "bg": "#f5fbfb",
    "surface": "#ffffff",
    "surface_alt": "#ecf9f8",
    "border": "#d5e7e8",
    "text": "#17252a",
    "muted": "#60777b",
    "brand": "#08a9a7",
    "brand_dark": "#078b89",
    "accent": "#f4b629",
    "danger": "#d94841",
    "console": "#111827",
    "console_text": "#d7f7f3",
}

if sys.platform == "win32":
    UI_FONT_FAMILY = "Microsoft YaHei UI"
    TEXT_FONT_FAMILY = "Microsoft YaHei UI"
    MONO_FONT_FAMILY = "Consolas"
elif sys.platform == "darwin":
    UI_FONT_FAMILY = "PingFang SC"
    TEXT_FONT_FAMILY = "PingFang SC"
    MONO_FONT_FAMILY = "Menlo"
else:
    UI_FONT_FAMILY = "Noto Sans CJK SC"
    TEXT_FONT_FAMILY = "Noto Sans CJK SC"
    MONO_FONT_FAMILY = "DejaVu Sans Mono"


def get_app_dir():
    if getattr(sys, "frozen", False):
        return os.path.dirname(os.path.abspath(sys.executable))
    return os.path.dirname(os.path.abspath(__file__))


def get_data_dir():
    if sys.platform == "darwin" and getattr(sys, "frozen", False):
        return os.path.join(
            os.path.expanduser("~/Library/Application Support"),
            "Chedan Image2",
        )
    return get_app_dir()


def get_default_output_dir():
    if sys.platform == "darwin" and getattr(sys, "frozen", False):
        return os.path.join(os.path.expanduser("~/Pictures"), "Chedan Image2")
    return os.path.join(APP_DIR, "output_images")


APP_DIR = get_app_dir()
DATA_DIR = get_data_dir()
CONFIG_PATH = os.path.join(DATA_DIR, "config.ini")
DEFAULT_OUTPUT_DIR = get_default_output_dir()


def resource_path(filename):
    candidates = [
        os.path.join(APP_DIR, filename),
        os.path.join(os.path.dirname(os.path.abspath(__file__)), filename),
    ]
    if sys.platform == "darwin" and getattr(sys, "frozen", False):
        contents_dir = os.path.dirname(os.path.dirname(os.path.abspath(sys.executable)))
        candidates.append(os.path.join(contents_dir, "Resources", filename))
    bundle_dir = getattr(sys, "_MEIPASS", None)
    if bundle_dir:
        candidates.insert(1, os.path.join(bundle_dir, filename))

    for path in candidates:
        if os.path.exists(path):
            return path
    return None


def open_path(path):
    if sys.platform == "win32":
        os.startfile(path)
    elif sys.platform == "darwin":
        subprocess.run(["open", path], check=False)
    else:
        subprocess.run(["xdg-open", path], check=False)


# ── Config ──────────────────────────────────────────────────────────────────
DEFAULTS = {
    "api_key": "",
    "model": "gpt-image-2",
    "size": "4K 横图 16:9   3840×2160",
    "custom_size": "",
    "custom_width": "",
    "custom_height": "",
    "quality": "high",
    "output_format": "png",
    "compression": "100",
    "task_copies": "1",
    "concurrency": "1",
    "output_dir": DEFAULT_OUTPUT_DIR,
    "prompt": "一只西瓜在跳舞",
}


def load_config():
    cfg = configparser.ConfigParser()
    cfg["settings"] = dict(DEFAULTS)
    if os.path.exists(CONFIG_PATH):
        cfg.read(CONFIG_PATH, encoding="utf-8")
    return cfg


def save_config(cfg):
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        cfg.write(f)


# ── Presets ──────────────────────────────────────────────────────────────────
SIZE_PRESETS = {
    # ── 1:1 方图 ──
    "1K 方图 1:1    1024×1024": "1024x1024",
    "2K 方图 1:1    2048×2048": "2048x2048",
    # ── 16:9 横图 ──
    "1K 横图 16:9   1792×1008": "1792x1008",
    "2K 横图 16:9   2048×1152": "2048x1152",
    "2.5K 横图 16:9 2560×1440": "2560x1440",
    "3K 横图 16:9   3072×1728": "3072x1728",
    "4K 横图 16:9   3840×2160": "3840x2160",
    # ── 9:16 竖图 ──
    "1K 竖图 9:16   1008×1792": "1008x1792",
    "2K 竖图 9:16   1152×2048": "1152x2048",
    "4K 竖图 9:16   2160×3840": "2160x3840",
    # ── 3:2 ──
    "1K 横图 3:2    1536×1024": "1536x1024",
    "1K 竖图 2:3    1024×1536": "1024x1536",
    # ── auto ──
    "auto (模型自动选择)": "auto",
}

QUALITY_OPTIONS = ["auto", "low", "medium", "high"]
FORMAT_OPTIONS = ["png", "jpeg", "webp"]


class ImageGenApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Chedan Image2")
        self.root.geometry("1440x920")
        self.root.minsize(1120, 760)
        self.root.resizable(True, True)
        self.root.configure(bg=COLORS["bg"])

        self.running = False
        self.executor = None
        self.stats = {"total": 0, "success": 0, "fail": 0, "total_time": 0.0}
        self.batch_tasks = []
        self.next_task_id = 1
        self.lock = threading.Lock()
        self.ui_queue = queue.Queue()
        self.logo_photo = None
        self.logo_icon = None

        self.cfg = load_config()
        self._configure_styles()
        self._load_logo_assets()
        self._build_ui()
        self._load_from_config()
        self._sync_action_buttons()
        self._drain_ui_queue()

        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

    def _cfg_get(self, key):
        return self.cfg.get("settings", key, fallback=DEFAULTS.get(key, ""))

    # ── UI ───────────────────────────────────────────────────────────────────
    def _configure_styles(self):
        style = ttk.Style(self.root)
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass

        self.root.option_add("*Font", (UI_FONT_FAMILY, 10))
        style.configure("App.TFrame", background=COLORS["bg"])
        style.configure("Surface.TFrame", background=COLORS["surface"])
        style.configure("Header.TFrame", background=COLORS["surface"])
        style.configure("Section.TLabelframe", background=COLORS["surface"], bordercolor=COLORS["border"], relief="solid")
        style.configure(
            "Section.TLabelframe.Label",
            background=COLORS["surface"],
            foreground=COLORS["brand_dark"],
            font=(UI_FONT_FAMILY, 10, "bold"),
        )
        style.configure("TLabel", background=COLORS["surface"], foreground=COLORS["text"])
        style.configure("Muted.TLabel", background=COLORS["surface"], foreground=COLORS["muted"])
        style.configure("Title.TLabel", background=COLORS["surface"], foreground=COLORS["text"], font=(UI_FONT_FAMILY, 18, "bold"))
        style.configure("Subtitle.TLabel", background=COLORS["surface"], foreground=COLORS["muted"], font=(UI_FONT_FAMILY, 9))
        style.configure("Badge.TLabel", background=COLORS["surface_alt"], foreground=COLORS["brand_dark"], padding=(10, 5))
        style.configure("Metric.TLabel", background=COLORS["surface"], foreground=COLORS["muted"], font=(UI_FONT_FAMILY, 9))
        style.configure("MetricValue.TLabel", background=COLORS["surface"], foreground=COLORS["text"], font=(UI_FONT_FAMILY, 16, "bold"))
        style.configure("TEntry", fieldbackground="#ffffff", bordercolor=COLORS["border"], lightcolor=COLORS["border"], darkcolor=COLORS["border"], padding=6)
        style.configure("TCombobox", fieldbackground="#ffffff", bordercolor=COLORS["border"], arrowsize=14, padding=4)
        style.configure("TSpinbox", fieldbackground="#ffffff", bordercolor=COLORS["border"], padding=4)
        style.configure("TCheckbutton", background=COLORS["surface"], foreground=COLORS["text"])
        style.configure("TRadiobutton", background=COLORS["surface"], foreground=COLORS["text"])
        style.configure("TButton", padding=(12, 7))
        style.configure("Treeview", background="#ffffff", fieldbackground="#ffffff", foreground=COLORS["text"], rowheight=28, bordercolor=COLORS["border"])
        style.configure("Treeview.Heading", background=COLORS["surface_alt"], foreground=COLORS["text"], font=(UI_FONT_FAMILY, 9, "bold"))
        style.configure("Primary.TButton", background=COLORS["brand"], foreground="#ffffff", bordercolor=COLORS["brand"], padding=(18, 9))
        style.map("Primary.TButton", background=[("active", COLORS["brand_dark"]), ("disabled", "#9fcfce")])
        style.configure("Danger.TButton", foreground=COLORS["danger"], padding=(14, 8))
        style.configure("Horizontal.TProgressbar", background=COLORS["brand"], troughcolor="#e8f1f2", bordercolor="#e8f1f2", lightcolor=COLORS["brand"], darkcolor=COLORS["brand"])

    def _load_logo_assets(self):
        logo_path = resource_path(LOGO_FILENAME)
        if not logo_path:
            return

        try:
            if HAS_PIL:
                logo = Image.open(logo_path)
                header_logo = logo.resize((46, 46), Image.LANCZOS)
                icon_logo = logo.resize((256, 256), Image.LANCZOS)
                self.logo_photo = ImageTk.PhotoImage(header_logo)
                self.logo_icon = ImageTk.PhotoImage(icon_logo)
            else:
                self.logo_photo = tk.PhotoImage(file=logo_path)
                self.logo_icon = self.logo_photo
            self.root.iconphoto(True, self.logo_icon)
        except Exception:
            self.logo_photo = None
            self.logo_icon = None

    def _section(self, parent, title):
        frame = ttk.LabelFrame(parent, text=title, style="Section.TLabelframe", padding=(16, 12))
        return frame

    def _metric(self, parent, label, value="0"):
        box = ttk.Frame(parent, style="Surface.TFrame", padding=(10, 8))
        ttk.Label(box, text=label, style="Metric.TLabel").pack(anchor=tk.W)
        value_label = ttk.Label(box, text=value, style="MetricValue.TLabel")
        value_label.pack(anchor=tk.W, pady=(3, 0))
        return box, value_label

    def _build_ui(self):
        main = ttk.Frame(self.root, style="App.TFrame", padding=14)
        main.pack(fill=tk.BOTH, expand=True)

        header = ttk.Frame(main, style="Header.TFrame", padding=(18, 14))
        header.pack(fill=tk.X, pady=(0, 14))
        if self.logo_photo:
            ttk.Label(header, image=self.logo_photo, style="TLabel").pack(side=tk.LEFT, padx=(0, 12))

        title_box = ttk.Frame(header, style="Header.TFrame")
        title_box.pack(side=tk.LEFT)
        ttk.Label(title_box, text="Chedan Image2", style="Title.TLabel").pack(anchor=tk.W)
        ttk.Label(title_box, text="批量生图与编辑控制台", style="Subtitle.TLabel").pack(anchor=tk.W, pady=(2, 0))

        self.stats_label = ttk.Label(header, text="就绪", style="Muted.TLabel")
        self.stats_label.pack(side=tk.RIGHT)

        body = ttk.Frame(main, style="App.TFrame")
        body.pack(fill=tk.BOTH, expand=True)
        body.columnconfigure(0, weight=6, uniform="main")
        body.columnconfigure(1, weight=5, uniform="main")
        body.rowconfigure(0, weight=1)

        left = ttk.Frame(body, style="Surface.TFrame", padding=(0, 0))
        left.grid(row=0, column=0, sticky="nsew", padx=(0, 8))
        right = ttk.Frame(body, style="Surface.TFrame", padding=(0, 0))
        right.grid(row=0, column=1, sticky="nsew", padx=(8, 0))
        right.rowconfigure(0, weight=1)
        right.columnconfigure(0, weight=1)

        key_frame = self._section(left, "API 设置")
        key_frame.pack(fill=tk.X, pady=(0, 10))
        key_frame.columnconfigure(1, weight=1)
        ttk.Label(key_frame, text="API Key").grid(row=0, column=0, sticky=tk.W, padx=(0, 10))
        self.apikey_var = tk.StringVar()
        self.apikey_entry = ttk.Entry(key_frame, textvariable=self.apikey_var, show="*")
        self.apikey_entry.grid(row=0, column=1, sticky="ew", padx=(0, 8))
        self.show_key_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(key_frame, text="显示", variable=self.show_key_var, command=self._toggle_key_visibility).grid(row=0, column=2, padx=(0, 8))
        ttk.Button(key_frame, text="保存配置", command=self._save_all_config).grid(row=0, column=3)

        mode_frame = self._section(left, "生成模式")
        mode_frame.pack(fill=tk.X, pady=(0, 10))
        self.mode_var = tk.StringVar(value="text2img")
        ttk.Radiobutton(mode_frame, text="文生图", variable=self.mode_var, value="text2img", command=self._on_mode_change).pack(side=tk.LEFT, padx=(0, 18))
        ttk.Radiobutton(mode_frame, text="图生图 (图+文)", variable=self.mode_var, value="img2img", command=self._on_mode_change).pack(side=tk.LEFT)

        self.img_frame = self._section(left, "输入图片 (可多选，自动拼合)")
        self.img_paths = []
        self.img_path_var = tk.StringVar()
        self.img_frame.columnconfigure(0, weight=1)
        ttk.Entry(self.img_frame, textvariable=self.img_path_var).grid(row=0, column=0, sticky="ew", padx=(0, 8))
        ttk.Button(self.img_frame, text="选择图片", command=self._pick_image).grid(row=0, column=1, padx=(0, 8))
        ttk.Button(self.img_frame, text="清空", command=self._clear_images).grid(row=0, column=2)

        self.prompt_frame = self._section(left, "提示词 Prompt")
        self.prompt_frame.pack(fill=tk.BOTH, expand=True, pady=(0, 10))
        prompt_tools = ttk.Frame(self.prompt_frame, style="Surface.TFrame")
        prompt_tools.pack(fill=tk.X, pady=(0, 8))
        ttk.Button(prompt_tools, text="粘贴", command=self._paste_prompt_text).pack(side=tk.LEFT, padx=(0, 8))
        ttk.Button(prompt_tools, text="清空", command=self._clear_prompt_text).pack(side=tk.LEFT)
        self.prompt_text = tk.Text(
            self.prompt_frame,
            height=8,
            wrap=tk.WORD,
            undo=True,
            maxundo=100,
            relief=tk.FLAT,
            bg="#ffffff",
            fg=COLORS["text"],
            insertbackground=COLORS["brand"],
            highlightthickness=1,
            highlightbackground=COLORS["border"],
            highlightcolor=COLORS["brand"],
            padx=10,
            pady=10,
            font=(TEXT_FONT_FAMILY, 10),
        )
        self.prompt_text.pack(fill=tk.BOTH, expand=True)
        self.prompt_text.bind("<Control-a>", self._select_all_prompt_text)
        self.prompt_text.bind("<Control-A>", self._select_all_prompt_text)

        param_frame = self._section(left, "输出参数")
        param_frame.pack(fill=tk.X)
        for col in range(6):
            param_frame.columnconfigure(col, weight=1)

        ttk.Label(param_frame, text="尺寸预设").grid(row=0, column=0, sticky=tk.W)
        self.size_var = tk.StringVar()
        ttk.Combobox(param_frame, textvariable=self.size_var, values=list(SIZE_PRESETS.keys()), state="readonly").grid(row=1, column=0, columnspan=3, sticky="ew", padx=(0, 10), pady=(4, 8))

        ttk.Label(param_frame, text="自定义宽").grid(row=0, column=3, sticky=tk.W)
        self.custom_width_var = tk.StringVar()
        ttk.Entry(param_frame, textvariable=self.custom_width_var, width=8).grid(row=1, column=3, sticky="ew", padx=(0, 8), pady=(4, 8))
        ttk.Label(param_frame, text="自定义高").grid(row=0, column=4, sticky=tk.W)
        self.custom_height_var = tk.StringVar()
        ttk.Entry(param_frame, textvariable=self.custom_height_var, width=8).grid(row=1, column=4, sticky="ew", padx=(0, 8), pady=(4, 8))
        size_note = ttk.Label(
            param_frame,
            text="自定义尺寸不填则使用预设。最大长边 3840；宽高比≤3:1；总像素 655360-8294400；宽高都需为 16 的倍数。",
            style="Muted.TLabel",
            wraplength=680,
        )
        size_note.grid(row=2, column=0, columnspan=6, sticky="ew", pady=(0, 10))

        ttk.Label(param_frame, text="质量").grid(row=3, column=0, sticky=tk.W)
        self.quality_var = tk.StringVar()
        ttk.Combobox(param_frame, textvariable=self.quality_var, values=QUALITY_OPTIONS, width=10, state="readonly").grid(row=4, column=0, sticky="ew", padx=(0, 10), pady=(4, 0))

        ttk.Label(param_frame, text="格式").grid(row=3, column=1, sticky=tk.W)
        self.format_var = tk.StringVar()
        ttk.Combobox(param_frame, textvariable=self.format_var, values=FORMAT_OPTIONS, width=10, state="readonly").grid(row=4, column=1, sticky="ew", padx=(0, 10), pady=(4, 0))

        ttk.Label(param_frame, text="压缩").grid(row=3, column=2, sticky=tk.W)
        self.compression_var = tk.IntVar(value=100)
        ttk.Spinbox(param_frame, from_=0, to=100, textvariable=self.compression_var, width=8).grid(row=4, column=2, sticky="ew", padx=(0, 10), pady=(4, 0))

        ttk.Label(param_frame, text="模型").grid(row=3, column=3, sticky=tk.W)
        self.model_var = tk.StringVar()
        ttk.Entry(param_frame, textvariable=self.model_var).grid(row=4, column=3, columnspan=3, sticky="ew", pady=(4, 0))

        right_tabs = ttk.Notebook(right)
        right_tabs.grid(row=0, column=0, sticky="nsew")
        queue_tab = ttk.Frame(right_tabs, style="Surface.TFrame", padding=(0, 8, 0, 0))
        log_tab = ttk.Frame(right_tabs, style="Surface.TFrame", padding=(0, 8, 0, 0))
        queue_tab.columnconfigure(0, weight=1)
        queue_tab.rowconfigure(0, weight=1)
        log_tab.columnconfigure(0, weight=1)
        log_tab.rowconfigure(0, weight=1)
        right_tabs.add(queue_tab, text="任务队列")
        right_tabs.add(log_tab, text="运行日志")

        batch_frame = self._section(queue_tab, "批量任务")
        batch_frame.grid(row=0, column=0, sticky="nsew", pady=(0, 10))
        batch_frame.rowconfigure(5, weight=1)
        for col in range(4):
            batch_frame.columnconfigure(col, weight=1)
        ttk.Label(batch_frame, text="添加份数").grid(row=0, column=0, sticky=tk.W)
        self.task_copies_var = tk.IntVar(value=1)
        ttk.Spinbox(batch_frame, from_=1, to=1000, textvariable=self.task_copies_var, width=8).grid(row=1, column=0, sticky="ew", padx=(0, 10), pady=(4, 10))
        ttk.Label(batch_frame, text="并发线程").grid(row=0, column=1, sticky=tk.W)
        self.concurrency_var = tk.IntVar(value=1)
        ttk.Spinbox(batch_frame, from_=1, to=50, textvariable=self.concurrency_var, width=8).grid(row=1, column=1, sticky="ew", pady=(4, 10))

        ttk.Label(batch_frame, text="输出目录").grid(row=2, column=0, sticky=tk.W)
        self.outdir_var = tk.StringVar()
        ttk.Entry(batch_frame, textvariable=self.outdir_var).grid(row=3, column=0, columnspan=3, sticky="ew", padx=(0, 8), pady=(4, 0))
        ttk.Button(batch_frame, text="浏览", command=self._pick_outdir).grid(row=3, column=3, sticky="ew", pady=(4, 0))

        task_buttons = ttk.Frame(batch_frame, style="Surface.TFrame")
        task_buttons.grid(row=4, column=0, columnspan=4, sticky="ew", pady=(12, 6))
        ttk.Button(task_buttons, text="添加当前任务", command=self._add_batch_task).pack(side=tk.LEFT, padx=(0, 8))
        ttk.Button(task_buttons, text="打开结果", command=self._open_selected_result).pack(side=tk.LEFT, padx=(0, 8))
        ttk.Button(task_buttons, text="查看错误", command=self._show_selected_error).pack(side=tk.LEFT, padx=(0, 8))
        ttk.Button(task_buttons, text="删除选中", command=self._delete_batch_task).pack(side=tk.LEFT, padx=(0, 8))
        ttk.Button(task_buttons, text="清空任务", command=self._clear_batch_tasks).pack(side=tk.LEFT)

        task_table_frame = ttk.Frame(batch_frame, style="Surface.TFrame")
        task_table_frame.grid(row=5, column=0, columnspan=4, sticky="nsew")
        task_table_frame.rowconfigure(0, weight=1)
        task_table_frame.columnconfigure(0, weight=1)

        self.task_tree = ttk.Treeview(
            task_table_frame,
            columns=("idx", "mode", "prompt", "image", "size", "status", "result", "error"),
            show="headings",
            height=12,
            selectmode="browse",
        )
        self.task_tree.heading("idx", text="#")
        self.task_tree.heading("mode", text="模式")
        self.task_tree.heading("prompt", text="提示词")
        self.task_tree.heading("image", text="图片")
        self.task_tree.heading("size", text="尺寸")
        self.task_tree.heading("status", text="状态")
        self.task_tree.heading("result", text="结果")
        self.task_tree.heading("error", text="错误原因")
        self.task_tree.column("idx", width=34, anchor=tk.CENTER, stretch=False)
        self.task_tree.column("mode", width=62, anchor=tk.CENTER, stretch=False)
        self.task_tree.column("prompt", width=220, stretch=True)
        self.task_tree.column("image", width=84, stretch=False)
        self.task_tree.column("size", width=90, anchor=tk.CENTER, stretch=False)
        self.task_tree.column("status", width=70, anchor=tk.CENTER, stretch=False)
        self.task_tree.column("result", width=126, stretch=False)
        self.task_tree.column("error", width=180, stretch=True)
        self.task_tree.grid(row=0, column=0, sticky="nsew")
        task_vscroll = ttk.Scrollbar(task_table_frame, orient=tk.VERTICAL, command=self.task_tree.yview)
        task_vscroll.grid(row=0, column=1, sticky="ns")
        task_hscroll = ttk.Scrollbar(task_table_frame, orient=tk.HORIZONTAL, command=self.task_tree.xview)
        task_hscroll.grid(row=1, column=0, sticky="ew")
        self.task_tree.configure(yscrollcommand=task_vscroll.set, xscrollcommand=task_hscroll.set)
        self.task_tree.bind("<Double-1>", lambda _event: self._open_or_show_selected_task())

        action_frame = self._section(queue_tab, "执行控制")
        action_frame.grid(row=1, column=0, sticky="ew", pady=(0, 10))
        action_frame.columnconfigure(0, weight=1)
        action_frame.columnconfigure(1, weight=1)
        self.start_btn = ttk.Button(action_frame, text="运行任务队列", style="Primary.TButton", command=self._start, state=tk.DISABLED)
        self.start_btn.grid(row=0, column=0, sticky="ew", padx=(0, 8))
        self.stop_btn = ttk.Button(action_frame, text="停止", style="Danger.TButton", command=self._stop, state=tk.DISABLED)
        self.stop_btn.grid(row=0, column=1, sticky="ew")

        progress_frame = self._section(queue_tab, "进度")
        progress_frame.grid(row=2, column=0, sticky="ew", pady=(0, 10))
        self.progress_var = tk.DoubleVar(value=0)
        ttk.Progressbar(progress_frame, variable=self.progress_var, maximum=100).pack(fill=tk.X, pady=(0, 12))
        metrics = ttk.Frame(progress_frame, style="Surface.TFrame")
        metrics.pack(fill=tk.X)
        metrics.columnconfigure((0, 1, 2, 3), weight=1)
        success_box, self.success_value = self._metric(metrics, "成功", "0")
        fail_box, self.fail_value = self._metric(metrics, "失败", "0")
        total_box, self.total_value = self._metric(metrics, "总数", "0")
        avg_box, self.avg_value = self._metric(metrics, "平均耗时", "0.0s")
        success_box.grid(row=0, column=0, sticky="ew", padx=(0, 8))
        fail_box.grid(row=0, column=1, sticky="ew", padx=(0, 8))
        total_box.grid(row=0, column=2, sticky="ew", padx=(0, 8))
        avg_box.grid(row=0, column=3, sticky="ew")

        log_frame = self._section(log_tab, "运行日志")
        log_frame.grid(row=0, column=0, sticky="nsew")
        log_frame.rowconfigure(1, weight=1)
        log_frame.columnconfigure(0, weight=1)
        log_tools = ttk.Frame(log_frame, style="Surface.TFrame")
        log_tools.grid(row=0, column=0, sticky="ew", pady=(0, 8))
        ttk.Label(log_tools, text="运行开始后会实时显示提交、完成和错误信息。", style="Muted.TLabel").pack(side=tk.LEFT)
        ttk.Button(log_tools, text="清空日志", command=self._clear_log).pack(side=tk.RIGHT)
        self.log = scrolledtext.ScrolledText(
            log_frame,
            height=22,
            wrap=tk.WORD,
            font=(MONO_FONT_FAMILY, 9),
            bg=COLORS["console"],
            fg=COLORS["console_text"],
            insertbackground=COLORS["console_text"],
            relief=tk.FLAT,
            padx=10,
            pady=10,
        )
        self.log.grid(row=1, column=0, sticky="nsew")

    # ── Config IO ────────────────────────────────────────────────────────────
    def _load_from_config(self):
        self.apikey_var.set(self._cfg_get("api_key"))
        self.model_var.set(self._cfg_get("model"))
        self.size_var.set(self._cfg_get("size"))
        custom_width = self._cfg_get("custom_width")
        custom_height = self._cfg_get("custom_height")
        legacy_custom_size = self._cfg_get("custom_size")
        if (not custom_width or not custom_height) and legacy_custom_size:
            parsed = self._parse_size(legacy_custom_size)
            if parsed:
                custom_width, custom_height = str(parsed[0]), str(parsed[1])
        self.custom_width_var.set(custom_width)
        self.custom_height_var.set(custom_height)
        self.quality_var.set(self._cfg_get("quality"))
        self.format_var.set(self._cfg_get("output_format"))
        self.compression_var.set(int(self._cfg_get("compression")))
        task_copies = self.cfg.get("settings", "task_copies", fallback=self._cfg_get("total_requests"))
        self.task_copies_var.set(int(task_copies))
        self.concurrency_var.set(int(self._cfg_get("concurrency")))
        self.outdir_var.set(self._cfg_get("output_dir"))
        prompt = self._cfg_get("prompt")
        self.prompt_text.delete("1.0", tk.END)
        self.prompt_text.insert("1.0", prompt)

        if self.apikey_var.get():
            self._log(f"已从 config.ini 加载配置 (API Key: {self.apikey_var.get()[:8]}...)")
        else:
            self._log("请先配置 API Key 并点击 [保存配置]")

    def _gather_config(self):
        self.cfg["settings"]["api_key"] = self.apikey_var.get().strip()
        self.cfg["settings"]["model"] = self.model_var.get().strip()
        self.cfg["settings"]["size"] = self.size_var.get()
        self.cfg["settings"]["custom_width"] = self.custom_width_var.get().strip()
        self.cfg["settings"]["custom_height"] = self.custom_height_var.get().strip()
        if self.custom_width_var.get().strip() and self.custom_height_var.get().strip():
            self.cfg["settings"]["custom_size"] = f"{self.custom_width_var.get().strip()}x{self.custom_height_var.get().strip()}"
        else:
            self.cfg["settings"]["custom_size"] = ""
        self.cfg["settings"]["quality"] = self.quality_var.get()
        self.cfg["settings"]["output_format"] = self.format_var.get()
        self.cfg["settings"]["compression"] = str(self.compression_var.get())
        self.cfg["settings"]["task_copies"] = str(self.task_copies_var.get())
        self.cfg["settings"]["concurrency"] = str(self.concurrency_var.get())
        self.cfg["settings"]["output_dir"] = self.outdir_var.get().strip()
        self.cfg["settings"]["prompt"] = self.prompt_text.get("1.0", tk.END).strip()

    def _save_all_config(self):
        self._gather_config()
        save_config(self.cfg)
        self._log(f"配置已保存到 {CONFIG_PATH}")

    def _on_close(self):
        self._gather_config()
        save_config(self.cfg)
        self.root.destroy()

    # ── Helpers ──────────────────────────────────────────────────────────────
    def _toggle_key_visibility(self):
        self.apikey_entry.config(show="" if self.show_key_var.get() else "*")

    def _paste_prompt_text(self):
        try:
            text = self.root.clipboard_get()
        except tk.TclError:
            return
        self.prompt_text.insert(tk.INSERT, text)
        self.prompt_text.focus_set()

    def _clear_prompt_text(self):
        self.prompt_text.delete("1.0", tk.END)
        self.prompt_text.focus_set()

    def _select_all_prompt_text(self, _event=None):
        self.prompt_text.tag_add(tk.SEL, "1.0", tk.END)
        self.prompt_text.mark_set(tk.INSERT, "1.0")
        self.prompt_text.see(tk.INSERT)
        return "break"

    def _on_mode_change(self):
        if self.mode_var.get() == "img2img":
            self.img_frame.pack(fill=tk.X, pady=(0, 5), before=self.prompt_text.master)
        else:
            self.img_frame.pack_forget()

    def _pick_image(self):
        paths = filedialog.askopenfilenames(filetypes=[("Images", "*.png *.jpg *.jpeg *.webp")])
        if paths:
            self.img_paths = list(paths)
            self.img_path_var.set(self._image_summary(self.img_paths))

    def _clear_images(self):
        self.img_paths = []
        self.img_path_var.set("")

    def _image_summary(self, paths):
        if not paths:
            return ""
        if len(paths) == 1:
            return paths[0]
        first = os.path.basename(paths[0])
        return f"{len(paths)} 张图片，首张：{first}"

    def _pick_outdir(self):
        d = filedialog.askdirectory()
        if d:
            self.outdir_var.set(d)

    def _run_on_ui(self, callback, *args):
        self.ui_queue.put((callback, args))

    def _drain_ui_queue(self):
        while True:
            try:
                callback, args = self.ui_queue.get_nowait()
            except queue.Empty:
                break
            try:
                callback(*args)
            except tk.TclError:
                pass
        try:
            self.root.after(80, self._drain_ui_queue)
        except tk.TclError:
            pass

    def _make_task_from_form(self, show_errors=True):
        prompt = self.prompt_text.get("1.0", tk.END).strip()
        if not prompt:
            if show_errors:
                messagebox.showwarning("提示", "请输入 Prompt")
            return None

        mode = self.mode_var.get()
        img_paths = []
        if mode == "img2img":
            img_paths = list(self.img_paths)
            if not img_paths:
                if show_errors:
                    messagebox.showwarning("提示", "请至少选择一张输入图片")
                return None
            for path in img_paths:
                if not os.path.exists(path):
                    if show_errors:
                        messagebox.showwarning("提示", f"输入图片不存在：{path}")
                    return None

        size = self._get_size()
        size_error = self._validate_size(size)
        if size_error:
            if show_errors:
                messagebox.showwarning("提示", size_error)
            return None

        return {
            "id": self.next_task_id,
            "mode": mode,
            "prompt": prompt,
            "size": size,
            "quality": self.quality_var.get(),
            "model": self.model_var.get(),
            "output_format": self.format_var.get(),
            "compression": self.compression_var.get(),
            "img_paths": img_paths,
            "status": "等待中",
            "output_path": "",
            "error": "",
        }

    def _add_batch_task(self):
        if self.running:
            messagebox.showwarning("提示", "任务运行中，暂不能添加队列任务")
            return
        task = self._make_task_from_form(show_errors=True)
        if not task:
            return
        copies = max(1, self.task_copies_var.get())
        first_id = self.next_task_id
        for _ in range(copies):
            item = dict(task)
            item["id"] = self.next_task_id
            item["status"] = "等待中"
            item["output_path"] = ""
            item["error"] = ""
            self.batch_tasks.append(item)
            self.next_task_id += 1
        self._refresh_task_table()
        if copies == 1:
            self._log(f"已添加任务 #{first_id}：{task['prompt'][:40]}")
        else:
            self._log(f"已添加 {copies} 条任务 #{first_id}-#{self.next_task_id - 1}：{task['prompt'][:40]}")

    def _delete_batch_task(self):
        if self.running:
            messagebox.showwarning("提示", "任务运行中，暂不能删除队列任务")
            return
        selected = self.task_tree.selection()
        if not selected:
            return
        selected_id = int(selected[0])
        self.batch_tasks = [task for task in self.batch_tasks if task["id"] != selected_id]
        self._refresh_task_table()

    def _clear_batch_tasks(self):
        if self.running:
            messagebox.showwarning("提示", "任务运行中，暂不能清空队列")
            return
        self.batch_tasks.clear()
        self.stats = {"total": 0, "success": 0, "fail": 0, "total_time": 0.0}
        self.progress_var.set(0)
        self._update_stats_label()
        self._refresh_task_table()

    def _has_runnable_tasks(self):
        for task in self.batch_tasks:
            if self._is_completed_task(task):
                continue
            return True
        return False

    def _is_completed_task(self, task):
        output_path = task.get("output_path")
        return task.get("status") == "完成" and output_path and os.path.exists(output_path)

    def _sync_action_buttons(self):
        if self.running:
            self.start_btn.config(state=tk.DISABLED)
            self.stop_btn.config(state=tk.NORMAL)
        else:
            self.start_btn.config(state=tk.NORMAL if self._has_runnable_tasks() else tk.DISABLED)
            self.stop_btn.config(state=tk.DISABLED)

    def _refresh_task_table(self):
        for item in self.task_tree.get_children():
            self.task_tree.delete(item)

        for index, task in enumerate(self.batch_tasks, start=1):
            prompt = task["prompt"].replace("\n", " ")
            if len(prompt) > 34:
                prompt = prompt[:34] + "..."
            img_paths = task.get("img_paths") or []
            if len(img_paths) == 1:
                image_name = os.path.basename(img_paths[0])
            elif len(img_paths) > 1:
                image_name = f"{len(img_paths)} 张"
            else:
                image_name = "-"
            result_name = os.path.basename(task.get("output_path") or "") or "-"
            error_text = task.get("error") or "-"
            if len(error_text) > 42:
                error_text = error_text[:42] + "..."
            mode_label = "图生图" if task["mode"] == "img2img" else "文生图"
            self.task_tree.insert(
                "",
                tk.END,
                iid=str(task["id"]),
                values=(index, mode_label, prompt, image_name, task["size"], task["status"], result_name, error_text),
            )
        self._sync_action_buttons()

    def _set_task_status(self, task_id, status):
        if task_id is None:
            return

        changed = False
        for task in self.batch_tasks:
            if task["id"] == task_id:
                task["status"] = status
                changed = True
                break
        if not changed:
            return

        def update():
            self._refresh_task_table()

        self._run_on_ui(update)

    def _set_task_output(self, task_id, output_path):
        if task_id is None:
            return

        for task in self.batch_tasks:
            if task["id"] == task_id:
                task["output_path"] = output_path
                task["error"] = ""
                break

        self._run_on_ui(self._refresh_task_table)

    def _set_task_error(self, task_id, error):
        if task_id is None:
            return

        for task in self.batch_tasks:
            if task["id"] == task_id:
                task["error"] = str(error or "")
                break

        self._run_on_ui(self._refresh_task_table)

    def _selected_task(self):
        selected = self.task_tree.selection()
        if not selected:
            return None
        selected_id = int(selected[0])
        for task in self.batch_tasks:
            if task["id"] == selected_id:
                return task
        return None

    def _open_selected_result(self):
        task = self._selected_task()
        if not task:
            messagebox.showinfo("提示", "请先选择一条已完成任务")
            return

        output_path = task.get("output_path")
        if not output_path or not os.path.exists(output_path):
            messagebox.showinfo("提示", "这条任务还没有可打开的结果文件")
            return

        try:
            open_path(output_path)
        except OSError as exc:
            messagebox.showerror("打开失败", str(exc))

    def _show_selected_error(self):
        task = self._selected_task()
        if not task:
            messagebox.showinfo("提示", "请先选择一条任务")
            return
        error = task.get("error")
        if not error:
            messagebox.showinfo("错误原因", "这条任务没有错误信息。")
            return
        messagebox.showerror(f"任务 #{task['id']} 错误原因", error)

    def _open_or_show_selected_task(self):
        task = self._selected_task()
        if not task:
            return
        if task.get("status") == "失败" and task.get("error"):
            self._show_selected_error()
            return
        self._open_selected_result()

    def _mark_unfinished_stopped(self):
        changed = False
        for task in self.batch_tasks:
            if task["status"] in ("等待中", "运行中"):
                task["status"] = "已停止"
                if not task.get("error"):
                    task["error"] = "任务被停止，尚未完成。"
                changed = True
        if not changed:
            return

        def update():
            self._refresh_task_table()

        self._run_on_ui(update)

    def _log(self, msg):
        ts = datetime.now().strftime("%H:%M:%S")
        self._run_on_ui(self._append_log, f"[{ts}] {msg}")

    def _append_log(self, msg):
        self.log.insert(tk.END, msg + "\n")
        self.log.see(tk.END)

    def _clear_log(self):
        self.log.delete("1.0", tk.END)

    def _update_stats_label(self):
        s = self.stats
        avg = (s["total_time"] / s["success"]) if s["success"] else 0

        def update():
            self.stats_label.config(text=f"成功 {s['success']} / 失败 {s['fail']}")
            self.success_value.config(text=str(s["success"]))
            self.fail_value.config(text=str(s["fail"]))
            self.total_value.config(text=str(s["total"]))
            self.avg_value.config(text=f"{avg:.1f}s")

        self._run_on_ui(update)

    def _update_progress(self):
        total = self.stats["total"]
        done = self.stats["success"] + self.stats["fail"]
        self._run_on_ui(lambda: self.progress_var.set(done / total * 100 if total else 0))

    def _get_size(self):
        custom_width = self.custom_width_var.get().strip()
        custom_height = self.custom_height_var.get().strip()
        if custom_width or custom_height:
            return f"{custom_width}x{custom_height}"
        return SIZE_PRESETS.get(self.size_var.get(), "1024x1024")

    def _parse_size(self, size):
        if size == "auto":
            return None
        match = re.fullmatch(r"\s*(\d+)\s*[xX×]\s*(\d+)\s*", size or "")
        if not match:
            return None
        return int(match.group(1)), int(match.group(2))

    def _get_api_key(self):
        return (
            self.apikey_var.get().strip()
            or os.environ.get("IMAGE2_API_KEY", "").strip()
            or os.environ.get("OPENAI_API_KEY", "").strip()
        )

    def _prepare_edit_input(self, img_paths, task_id):
        if not img_paths:
            return None, False
        if len(img_paths) == 1 and os.path.getsize(img_paths[0]) <= MAX_EDIT_INPUT_BYTES:
            return img_paths[0], False
        if not HAS_PIL:
            raise Exception("多图编辑或压缩大图需要 Pillow 支持")

        temp_path = self._compose_edit_images(img_paths, task_id)
        return temp_path, True

    def _compose_edit_images(self, img_paths, task_id):
        count = len(img_paths)
        cols = max(1, int(count ** 0.5))
        while cols * cols < count:
            cols += 1
        rows = (count + cols - 1) // cols

        attempts = [
            (768, 86),
            (640, 82),
            (512, 78),
            (448, 74),
            (384, 70),
        ]
        last_path = None
        for cell_size, quality in attempts:
            margin = max(16, cell_size // 32)
            label_h = 32
            canvas_w = cols * cell_size + (cols + 1) * margin
            canvas_h = rows * (cell_size + label_h) + (rows + 1) * margin
            canvas = Image.new("RGB", (canvas_w, canvas_h), "#ffffff")

            for index, path in enumerate(img_paths):
                image = Image.open(path)
                image = ImageOps.exif_transpose(image).convert("RGB")
                image.thumbnail((cell_size, cell_size), Image.LANCZOS)
                col = index % cols
                row = index // cols
                x = margin + col * (cell_size + margin) + (cell_size - image.width) // 2
                y = margin + row * (cell_size + label_h + margin) + (cell_size - image.height) // 2
                canvas.paste(image, (x, y))

            fd, temp_path = tempfile.mkstemp(prefix=f"image2_task_{task_id}_", suffix=".jpg")
            os.close(fd)
            canvas.save(temp_path, "JPEG", quality=quality, optimize=True)
            last_path = temp_path
            if os.path.getsize(temp_path) <= MAX_EDIT_INPUT_BYTES:
                return temp_path

            try:
                os.remove(temp_path)
            except OSError:
                pass

        if last_path and os.path.exists(last_path):
            return last_path
        raise Exception("多图拼接后仍超过 4MB，建议减少输入图片数量或先压缩图片")

    def _validate_size(self, size):
        if size == "auto":
            return None
        parsed = self._parse_size(size)
        if not parsed:
            return "请填写正确的宽和高，例如宽 2048、高 2048；不填则使用尺寸预设。"

        width, height = parsed
        long_edge = max(width, height)
        short_edge = min(width, height)
        pixels = width * height

        if width <= 0 or height <= 0:
            return "宽度和高度必须大于 0。"
        if width % 16 != 0 or height % 16 != 0:
            return "宽度和高度都必须是 16 的倍数，这是当前接口的尺寸要求。"
        if long_edge > 3840:
            return "长边不能超过 3840 像素。"
        if long_edge / short_edge > 3:
            return "宽高比不能超过 3:1。"
        if pixels < 655360 or pixels > 8294400:
            return "总像素必须在 655360 到 8294400 之间。"
        return None

    # ── API call ─────────────────────────────────────────────────────────────
    def _call_api(self, task_id, prompt, size, quality, model, output_format,
                  compression, api_key, img_paths=None, queue_task_id=None):
        """Single API request (runs in thread)."""
        if not self.running:
            self._set_task_status(queue_task_id, "已停止")
            return

        img_paths = img_paths or []
        mode_str = "图生图" if img_paths else "文生图"
        self._set_task_status(queue_task_id, "运行中")
        self._log(f"[#{task_id}] {mode_str} | size={size} quality={quality} format={output_format}")

        start = time.time()
        temp_input = None
        try:
            edit_input, is_temp_input = self._prepare_edit_input(img_paths, task_id)
            if is_temp_input:
                temp_input = edit_input
                self._log(f"[#{task_id}] 已将 {len(img_paths)} 张输入图自动拼合为接口输入图")

            result_b64 = self._call_images_api(
                task_id, prompt, size, quality, model,
                output_format, compression, api_key, edit_input)

            elapsed = time.time() - start

            if result_b64:
                outdir = self.outdir_var.get()
                os.makedirs(outdir, exist_ok=True)
                ts = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
                raw = base64.b64decode(result_b64)
                raw, ext = self._format_image_bytes(raw, output_format, compression)
                filename = f"img_{ts}_{task_id}.{ext}"
                filepath = os.path.join(outdir, filename)
                with open(filepath, "wb") as f:
                    f.write(raw)

                res_str = ""
                if HAS_PIL:
                    try:
                        img = Image.open(io.BytesIO(raw))
                        w, h = img.size
                        res_str = f" | {w}x{h}"
                    except Exception:
                        pass

                with self.lock:
                    self.stats["success"] += 1
                    self.stats["total_time"] += elapsed
                self._set_task_output(queue_task_id, filepath)
                self._set_task_status(queue_task_id, "完成")
                self._log(f"[#{task_id}] OK {elapsed:.1f}s | {len(raw)/1024:.0f}KB{res_str} | {filename}")
            else:
                with self.lock:
                    self.stats["fail"] += 1
                self._set_task_error(queue_task_id, "接口返回成功但响应中没有图片数据。")
                self._set_task_status(queue_task_id, "失败")
                self._log(f"[#{task_id}] FAIL {elapsed:.1f}s | 无图片数据")

        except Exception as e:
            elapsed = time.time() - start
            with self.lock:
                self.stats["fail"] += 1
            self._set_task_error(queue_task_id, str(e))
            self._set_task_status(queue_task_id, "失败")
            self._log(f"[#{task_id}] FAIL {elapsed:.1f}s | {e}")
        finally:
            if temp_input:
                try:
                    os.remove(temp_input)
                except OSError:
                    pass

        self._update_stats_label()
        self._update_progress()

    def _format_image_bytes(self, raw, output_format, compression):
        fmt = (output_format or "png").lower()
        if fmt == "png":
            return raw, "png"
        if fmt not in ("jpeg", "webp"):
            raise Exception(f"不支持的输出格式: {output_format}")
        if not HAS_PIL:
            raise Exception("保存 jpeg/webp 需要安装 Pillow；请选择 png 或安装 Pillow。")

        quality = max(0, min(100, int(compression)))
        with Image.open(io.BytesIO(raw)) as img:
            out = io.BytesIO()
            if fmt == "jpeg":
                if img.mode in ("RGBA", "LA", "P"):
                    img = img.convert("RGB")
                img.save(out, format="JPEG", quality=quality, optimize=True)
                return out.getvalue(), "jpg"

            img.save(out, format="WEBP", quality=quality, method=6)
            return out.getvalue(), "webp"

    def _extract_image_b64(self, payload, api_key):
        """从 Images API 响应中提取图片；兼容 base64 和 URL 两种返回。"""
        data = payload.get("data") if isinstance(payload, dict) else None
        if not isinstance(data, list):
            return None

        for item in data:
            if not isinstance(item, dict):
                continue

            for key in ("b64_json", "base64", "image_b64"):
                b64 = item.get(key)
                if b64:
                    return b64

            url = item.get("url")
            if url:
                img_resp = httpx.get(
                    url,
                    headers={"Authorization": f"Bearer {api_key}"},
                    timeout=REQUEST_TIMEOUT,
                )
                if img_resp.status_code != 200:
                    raise Exception(f"下载图片失败 HTTP {img_resp.status_code}: {img_resp.text[:500]}")
                return base64.b64encode(img_resp.content).decode("utf-8")

        return None

    def _error_text(self, resp):
        """保留足够长的服务端错误，避免 503 根因被截断。"""
        if not resp.text:
            return str(resp.status_code)
        try:
            err = resp.json().get("error", {})
            if isinstance(err, dict) and err.get("message"):
                return err.get("message")
        except Exception:
            pass
        return resp.text[:1000]

    def _request_with_retries(self, do_request):
        for attempt in range(1, RETRIES + 1):
            try:
                resp = do_request()
            except httpx.RequestError as exc:
                raise Exception(f"网络请求失败: {exc}") from exc

            if resp.status_code == 200:
                return resp
            if resp.status_code in RETRY_STATUSES and attempt < RETRIES:
                self._log(f"HTTP {resp.status_code}，正在重试 {attempt}/{RETRIES} ...")
                continue
            return resp

        raise Exception("请求重试后仍失败")

    def _call_images_api(self, task_id, prompt, size, quality, model,
                         output_format, compression, api_key, img_path=None):
        """Text2img via /images/generations; img2img via /images/edits."""
        common_fields = {
            "model": model,
            "prompt": prompt,
            "n": 1,
            "quality": quality,
            "response_format": "b64_json",
        }
        if size != "auto":
            common_fields["size"] = size

        if img_path:
            ext = os.path.splitext(img_path)[1].lstrip(".").lower()
            mime = {"png": "image/png", "jpg": "image/jpeg",
                    "jpeg": "image/jpeg", "webp": "image/webp",
                    "gif": "image/gif"}.get(ext, "image/png")
            endpoint = f"{BASE_URL}/images/edits"
            data = {k: str(v) for k, v in common_fields.items()}

            def do_request():
                with open(img_path, "rb") as f:
                    return httpx.post(
                        endpoint,
                        headers={"Authorization": f"Bearer {api_key}"},
                        data=data,
                        files={"image": (os.path.basename(img_path), f, mime)},
                        timeout=REQUEST_TIMEOUT,
                    )

            resp = self._request_with_retries(do_request)
        else:
            endpoint = f"{BASE_URL}/images/generations"

            def do_request():
                return httpx.post(
                    endpoint,
                    headers={
                        "Content-Type": "application/json",
                        "Authorization": f"Bearer {api_key}",
                    },
                    json=common_fields,
                    timeout=REQUEST_TIMEOUT,
                )

            resp = self._request_with_retries(do_request)

        if resp.status_code != 200:
            raise Exception(f"HTTP {resp.status_code}: {self._error_text(resp)}")

        try:
            payload = resp.json()
        except json.JSONDecodeError:
            raise Exception(f"响应不是 JSON: {resp.text[:500]}")

        image_b64 = self._extract_image_b64(payload, api_key)
        if not image_b64:
            preview = json.dumps(payload, ensure_ascii=False)[:800]
            raise Exception(f"响应中没有图片数据: {preview}")
        return image_b64

    # ── Start / Stop ─────────────────────────────────────────────────────────
    def _start(self):
        api_key = self._get_api_key()
        if not api_key:
            messagebox.showwarning("提示", "请先配置 API Key")
            return

        if not self.batch_tasks:
            messagebox.showwarning("提示", "任务列表为空。请先点击 [添加当前任务]，再运行任务队列。")
            self._log("任务列表为空：请先添加任务，再运行队列。")
            return

        concurrency = self.concurrency_var.get()

        runnable_tasks = []
        skipped_done = 0
        for task in self.batch_tasks:
            if self._is_completed_task(task):
                skipped_done += 1
                continue

            copied = dict(task)
            if copied["mode"] == "img2img":
                img_paths = copied.get("img_paths") or []
                if not img_paths:
                    messagebox.showwarning("提示", f"任务 #{copied['id']} 没有输入图片")
                    return
                for path in img_paths:
                    if not os.path.exists(path):
                        messagebox.showwarning("提示", f"任务 #{copied['id']} 的输入图片不存在：{path}")
                        return
            size_error = self._validate_size(copied["size"])
            if size_error:
                messagebox.showwarning("提示", f"任务 #{copied['id']} 尺寸错误：{size_error}")
                return
            copied["status"] = "等待中"
            copied["error"] = ""
            runnable_tasks.append(copied)

        if not runnable_tasks:
            messagebox.showinfo("提示", "队列里没有需要运行的任务。已完成的任务不会重复执行。")
            self._log("队列里没有需要运行的任务：已完成任务已跳过。")
            return

        runnable_ids = {task["id"] for task in runnable_tasks}
        for task in self.batch_tasks:
            if task["id"] in runnable_ids:
                task["status"] = "等待中"
                task["error"] = ""
        self._refresh_task_table()

        total = len(runnable_tasks)

        # Auto save config
        self._gather_config()
        save_config(self.cfg)

        # Reset
        self.stats = {"total": total, "success": 0, "fail": 0, "total_time": 0.0}
        self.progress_var.set(0)
        self._update_stats_label()
        self.running = True
        self.start_btn.config(state=tk.DISABLED)
        self.stop_btn.config(state=tk.NORMAL)
        self.stats_label.config(text=f"运行中 0 / {total}")

        skip_text = f" | 跳过已完成:{skipped_done}" if skipped_done else ""
        self._log(f"═══ 开始运行任务队列 | 待运行:{total} 并发:{concurrency}{skip_text} ═══")

        def run():
            self.executor = ThreadPoolExecutor(max_workers=concurrency)
            futures = {}
            for index, task in enumerate(runnable_tasks, start=1):
                if not self.running:
                    self._set_task_status(task.get("id"), "已停止")
                    break
                f = self.executor.submit(
                    self._call_api,
                    index,
                    task["prompt"],
                    task["size"],
                    task["quality"],
                    task["model"],
                    task["output_format"],
                    task["compression"],
                    api_key,
                    task.get("img_paths"),
                    task.get("id"),
                )
                futures[f] = task

            for f in as_completed(futures):
                try:
                    f.result()
                except Exception as exc:
                    task = futures.get(f, {})
                    with self.lock:
                        self.stats["fail"] += 1
                    self._set_task_error(task.get("id"), str(exc))
                    self._set_task_status(task.get("id"), "失败")
                    self._log(f"后台任务异常: {exc}")
                    self._update_stats_label()
                    self._update_progress()

            self.executor.shutdown(wait=False)
            self.running = False
            s = self.stats
            avg = (s["total_time"] / s["success"]) if s["success"] else 0
            self._log(f"═══ 完成 | 成功:{s['success']} 失败:{s['fail']}/{s['total']} 平均耗时:{avg:.1f}s 总耗时:{s['total_time']:.1f}s ═══")
            self._mark_unfinished_stopped()
            self._run_on_ui(self._sync_action_buttons)
            self._run_on_ui(lambda: self.stats_label.config(text=f"完成 成功 {s['success']} / 失败 {s['fail']}"))

        threading.Thread(target=run, daemon=True).start()

    def _stop(self):
        self.running = False
        self._log(">>> 正在停止...")
        self._mark_unfinished_stopped()
        self.stop_btn.config(state=tk.DISABLED)


if __name__ == "__main__":
    root = tk.Tk()
    app = ImageGenApp(root)
    root.mainloop()
