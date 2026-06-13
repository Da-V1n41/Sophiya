import customtkinter as ctk
import tkinter as tk
import threading
import math
import datetime
from skills import UkrainianAIAssistant
from voice import speaker

# Системний трей (опціонально)
try:
    import pystray
    from PIL import Image, ImageDraw
    HAS_TRAY = True
except ImportError:
    HAS_TRAY = False

# --------------------------
# Тема
# --------------------------
ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

COLORS = {
    'bg':           '#0d1117',
    'panel':        '#161b22',
    'card':         '#1c2333',
    'card_user':    '#152238',
    'card_bot':     '#1a2332',
    'border':       '#30363d',
    'text':         '#e6edf3',
    'text_dim':     '#8b949e',
    'accent':       '#58a6ff',
    'accent_hover': '#79c0ff',
    'ai_on':        '#f0883e',
    'ai_off':       '#58a6ff',
    'green':        '#3fb950',
    'red':          '#f85149',
    'purple':       '#bc8cff',
    'input_bg':     '#1c2333',
}


class SophiyaUI:
    def __init__(self):
        self.assistant = UkrainianAIAssistant()
        self.is_listening = False
        self.wave_phase = 0.0
        self._pulse_phase = 0.0
        self._mini_window = None
        self._tray_icon = None
        self._mini_mode = False

        # Callbacks
        self.assistant.on_status_change = self._on_status
        self.assistant.on_message = self._on_message
        self.assistant.on_mode_change = self._on_mode_change
        self.assistant.on_listening_change = self._on_listening_change
        self.assistant.on_status_bar = self._on_status_bar

        self._build_window()

        # Bottom-up
        self._build_status_bar()
        self._build_input_bar()
        self._build_mic_button()

        # Top-down
        self._build_header()
        self._build_mode_bar()
        self._build_wave_canvas()
        self._build_chat()

        self._animate()

        # Гарячі клавіші
        self.root.bind('<space>', self._on_space)
        self.root.bind('<Escape>', lambda e: self.stop_listening())
        self.root.bind('<Return>', self._on_enter)

        # Системний трей
        self._setup_tray()

    # ============================================
    # Вікно
    # ============================================
    def _build_window(self):
        self.root = ctk.CTk()
        self.root.title("Софія")
        self.root.geometry("460x700")
        self.root.minsize(380, 520)
        self.root.configure(fg_color=COLORS['bg'])

        try:
            import sys, os
            if getattr(sys, 'frozen', False):
                _ico = os.path.join(sys._MEIPASS, 'icon.ico')
            else:
                _ico = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'icon.ico')
            self.root.iconbitmap(_ico)
        except Exception:
            pass

    # ============================================
    # Заголовок
    # ============================================
    def _build_header(self):
        header = ctk.CTkFrame(self.root, fg_color=COLORS['panel'], height=56, corner_radius=0)
        header.pack(fill='x', side='top')
        header.pack_propagate(False)

        # Аватар — градієнтне коло
        avatar = tk.Canvas(header, width=38, height=38, bg=COLORS['panel'], highlightthickness=0)
        avatar.pack(side='left', padx=(16, 10), pady=9)
        # Зовнішнє кільце
        avatar.create_oval(1, 1, 37, 37, fill='', outline=COLORS['accent'], width=2)
        # Внутрішнє коло
        avatar.create_oval(5, 5, 33, 33, fill=COLORS['accent'], outline='')
        avatar.create_text(19, 19, text="S", fill='white', font=('Segoe UI', 13, 'bold'))

        # Назва + статус
        name_frame = ctk.CTkFrame(header, fg_color='transparent')
        name_frame.pack(side='left', pady=8)

        ctk.CTkLabel(name_frame, text="Софія", font=("Segoe UI", 17, "bold"),
                     text_color=COLORS['text']).pack(anchor='w')
        self._header_status = ctk.CTkLabel(name_frame, text="офлайн",
                                           font=("Segoe UI", 10), text_color=COLORS['text_dim'])
        self._header_status.pack(anchor='w')

        # Кнопка мінімального режиму (праворуч у заголовку)
        ctk.CTkButton(
            header, text="▫", width=32, height=28,
            font=("Segoe UI", 14),
            fg_color='transparent', hover_color=COLORS['border'],
            text_color=COLORS['text_dim'],
            command=self._toggle_mini_mode,
        ).pack(side='right', padx=(0, 8))

    # ============================================
    # Режим ШІ
    # ============================================
    def _build_mode_bar(self):
        bar = ctk.CTkFrame(self.root, fg_color=COLORS['bg'], height=32)
        bar.pack(fill='x', side='top', padx=16, pady=(6, 0))

        # Пульсуючий індикатор
        self._mode_canvas = tk.Canvas(bar, width=14, height=14,
                                      bg=COLORS['bg'], highlightthickness=0)
        self._mode_canvas.pack(side='left', padx=(2, 8))
        self._mode_dot = self._mode_canvas.create_oval(3, 3, 11, 11,
                                                        fill=COLORS['text_dim'], outline='')

        self.mode_label = ctk.CTkLabel(bar, text="Звичайний режим",
                                       font=("Segoe UI", 10), text_color=COLORS['text_dim'])
        self.mode_label.pack(side='left')

        # Switch
        self.ai_switch = ctk.CTkSwitch(
            bar, text="ШІ", font=("Segoe UI", 10),
            text_color=COLORS['text_dim'],
            progress_color=COLORS['ai_on'],
            button_color=COLORS['text_dim'],
            button_hover_color=COLORS['text'],
            fg_color=COLORS['border'],
            width=42,
            command=self._toggle_ai_mode
        )
        self.ai_switch.pack(side='right', padx=2)

    def _toggle_ai_mode(self):
        is_on = bool(self.ai_switch.get())
        self.assistant.use_ai = is_on
        self._update_mode_display(is_on)

    def _update_mode_display(self, is_ai):
        if is_ai:
            self._mode_canvas.itemconfig(self._mode_dot, fill=COLORS['ai_on'])
            self.mode_label.configure(text="Режим ШІ", text_color=COLORS['ai_on'])
            if not self.ai_switch.get():
                self.ai_switch.select()
        else:
            self._mode_canvas.itemconfig(self._mode_dot, fill=COLORS['ai_off'])
            self.mode_label.configure(text="Звичайний режим", text_color=COLORS['text_dim'])
            if self.ai_switch.get():
                self.ai_switch.deselect()

    # ============================================
    # Хвилі + пульсуючий індикатор
    # ============================================
    def _build_wave_canvas(self):
        self.canvas = tk.Canvas(self.root, height=70, bg=COLORS['bg'], highlightthickness=0)
        self.canvas.pack(fill='x', side='top', padx=16, pady=(2, 0))

    def _animate(self):
        self.canvas.delete("all")
        w = self.canvas.winfo_width() or 430
        h = 70
        cy = h / 2

        speed = 0.12 if self.is_listening else 0.02
        self.wave_phase += speed
        t = self.wave_phase

        waves = [
            {'color': COLORS['accent'], 'amp': 15, 'freq': 0.025, 'offset': 0},
            {'color': COLORS['purple'], 'amp': 11, 'freq': 0.030, 'offset': 1.5},
            {'color': '#9b59b6',        'amp': 7,  'freq': 0.020, 'offset': 3.0},
        ]

        if self.is_listening:
            for wave in waves:
                wave['amp'] *= 2.5

        for wave in waves:
            pts = []
            for x in range(0, w, 3):
                fade = max(0, 1.0 - (abs(x - w / 2) / (w / 2)) ** 2)
                y = cy + math.sin(x * wave['freq'] + t + wave['offset']) * wave['amp'] * fade
                pts.extend([x, y])
            if len(pts) >= 4:
                self.canvas.create_line(*pts, fill=wave['color'], width=2, smooth=True)

        if not self.is_listening:
            self.canvas.create_line(0, cy, w, cy, fill=COLORS['border'], width=1, dash=(4, 4))

        # Пульсуючий індикатор
        if self.is_listening:
            self._pulse_phase += 0.08
            pulse = abs(math.sin(self._pulse_phase))
            r = int(59 + pulse * 196)
            g = int(169 + pulse * 86)
            b = int(245 - pulse * 100)
            color = f'#{r:02x}{g:02x}{b:02x}'
            self._mode_canvas.itemconfig(self._mode_dot, fill=color)

        self.root.after(33, self._animate)

    # ============================================
    # Чат з бульбашками
    # ============================================
    def _build_chat(self):
        self.chat_frame = ctk.CTkScrollableFrame(
            self.root,
            fg_color=COLORS['bg'],
            corner_radius=0,
            scrollbar_button_color=COLORS['border'],
            scrollbar_button_hover_color=COLORS['text_dim'],
        )
        self.chat_frame.pack(fill='both', expand=True, side='top', padx=8, pady=(4, 0))

    def _add_chat_message(self, sender, text):
        now = datetime.datetime.now().strftime('%H:%M')
        is_user = (sender == 'Ви')

        # Контейнер повідомлення
        msg_container = ctk.CTkFrame(self.chat_frame, fg_color='transparent')
        msg_container.pack(fill='x', padx=4, pady=2)

        # Бульбашка
        bubble_color = COLORS['card_user'] if is_user else COLORS['card_bot']
        anchor_side = 'e' if is_user else 'w'
        name_color = COLORS['accent'] if is_user else COLORS['green']

        bubble = ctk.CTkFrame(msg_container, fg_color=bubble_color, corner_radius=14)
        bubble.pack(anchor=anchor_side, padx=(40 if is_user else 4, 4 if is_user else 40))

        # Ім'я + час
        header_frame = ctk.CTkFrame(bubble, fg_color='transparent')
        header_frame.pack(fill='x', padx=12, pady=(8, 0))

        ctk.CTkLabel(header_frame, text=sender, font=("Segoe UI", 10, "bold"),
                     text_color=name_color).pack(side='left')
        ctk.CTkLabel(header_frame, text=now, font=("Segoe UI", 9),
                     text_color=COLORS['text_dim']).pack(side='right', padx=(8, 0))

        # Текст
        text_color = COLORS['text'] if is_user else '#c9d1d9'
        msg_label = ctk.CTkLabel(
            bubble, text=text, font=("Segoe UI", 11),
            text_color=text_color, wraplength=280,
            justify='left', anchor='w'
        )
        msg_label.pack(padx=12, pady=(2, 10), anchor='w')

        # Автоскрол
        self.chat_frame.after(50, lambda: self.chat_frame._parent_canvas.yview_moveto(1.0))

    # ============================================
    # Одна кнопка мікрофону (toggle)
    # ============================================
    def _build_mic_button(self):
        mic_frame = ctk.CTkFrame(self.root, fg_color=COLORS['bg'], corner_radius=0)
        mic_frame.pack(fill='x', side='bottom', padx=16, pady=(6, 6))

        self.mic_btn = ctk.CTkButton(
            mic_frame,
            text="Старт",
            font=("Segoe UI", 14, "bold"),
            fg_color=COLORS['card'],
            hover_color=COLORS['border'],
            text_color=COLORS['accent'],
            border_width=1,
            border_color=COLORS['border'],
            corner_radius=12,
            height=46,
            command=self._toggle_listening,
        )
        self.mic_btn.pack(fill='x')

    def _toggle_listening(self):
        if self.is_listening:
            self.stop_listening()
        else:
            self.start_listening()

    # ============================================
    # Поле вводу тексту
    # ============================================
    def _build_input_bar(self):
        input_frame = ctk.CTkFrame(self.root, fg_color=COLORS['bg'], corner_radius=0)
        input_frame.pack(fill='x', side='bottom', padx=16, pady=(0, 0))

        self.text_input = ctk.CTkEntry(
            input_frame,
            placeholder_text="Напишіть команду...",
            font=("Segoe UI", 11),
            fg_color=COLORS['input_bg'],
            text_color=COLORS['text'],
            placeholder_text_color=COLORS['text_dim'],
            border_width=1,
            border_color=COLORS['border'],
            corner_radius=10,
            height=38,
        )
        self.text_input.pack(side='left', fill='x', expand=True, padx=(0, 6))

        send_btn = ctk.CTkButton(
            input_frame,
            text=">>",
            font=("Segoe UI", 13, "bold"),
            fg_color=COLORS['card'],
            hover_color=COLORS['border'],
            text_color=COLORS['accent'],
            border_width=1,
            border_color=COLORS['border'],
            corner_radius=10,
            width=44, height=38,
            command=self._send_text,
        )
        send_btn.pack(side='right')

    def _send_text(self):
        text = self.text_input.get().strip()
        if not text:
            return
        self.text_input.delete(0, 'end')
        self._add_chat_message('Ви', text)
        # Обробка в окремому потоці (без перевірки імені)
        threading.Thread(target=self.assistant.process_command, args=(text.lower(), True), daemon=True).start()

    def _on_enter(self, event):
        # Enter відправляє текст тільки якщо фокус на полі вводу
        if self.root.focus_get() == self.text_input._entry:
            self._send_text()

    def _on_space(self, event):
        # Space toggle тільки якщо фокус НЕ на полі вводу
        if self.root.focus_get() != self.text_input._entry:
            self._toggle_listening()

    # ============================================
    # Статус бар
    # ============================================
    def _build_status_bar(self):
        status_frame = ctk.CTkFrame(self.root, fg_color=COLORS['panel'], height=26, corner_radius=0)
        status_frame.pack(fill='x', side='bottom')
        status_frame.pack_propagate(False)

        self.status_label = ctk.CTkLabel(
            status_frame, text="Натисніть Старт або Space",
            font=("Segoe UI", 9), text_color=COLORS['text_dim'], anchor='w'
        )
        self.status_label.pack(side='left', padx=10, pady=2)

        self._engine_label = ctk.CTkLabel(
            status_frame, text="Google API",
            font=("Segoe UI", 9), text_color=COLORS['text_dim'], anchor='e'
        )
        self._engine_label.pack(side='right', padx=10, pady=2)

    # ============================================
    # Callbacks
    # ============================================
    def _on_status(self, text):
        self.root.after(0, lambda: self.status_label.configure(text=text))
        # Оновлюємо міні-вікно кольором
        color = COLORS['green'] if 'Слухаю' in text else COLORS['text_dim']
        self._update_mini(text, dot_color=color)

    def _on_status_bar(self, engine):
        color = COLORS['text_dim'] if 'Google' in engine else '#ff9500'
        self.root.after(0, lambda: self._engine_label.configure(text=engine, text_color=color))

    def _on_message(self, sender, text):
        self.root.after(0, lambda: self._add_chat_message(sender, text))
        if sender == 'Софія':
            self._update_mini(f"Софія: {text}")

    def _on_mode_change(self, is_ai):
        self.root.after(0, lambda: self._update_mode_display(is_ai))

    def _on_listening_change(self, is_listening):
        self.is_listening = is_listening
        self.root.after(0, lambda: self._update_listening_ui(is_listening))

    def _update_listening_ui(self, active):
        if active:
            self._header_status.configure(text="слухаю...", text_color=COLORS['green'])
            self.mic_btn.configure(text="Слухаю...", text_color=COLORS['green'],
                                   border_color=COLORS['green'])
        else:
            self._header_status.configure(text="офлайн", text_color=COLORS['text_dim'])
            self.mic_btn.configure(text="Старт", text_color=COLORS['accent'],
                                   border_color=COLORS['border'])

    # ============================================
    # Старт / Стоп
    # ============================================
    def start_listening(self):
        if self.is_listening:
            return
        self.is_listening = True
        self._update_listening_ui(True)
        self.status_label.configure(text="Запускаю...")
        threading.Thread(target=self.assistant.start_listening, daemon=True).start()

    def stop_listening(self):
        if not self.is_listening:
            return
        self.assistant.stop_listening()
        self.is_listening = False
        self._update_listening_ui(False)
        self.status_label.configure(text="Зупинено")
        self._add_chat_message('Софія', 'Зупинено. Натисніть Старт щоб продовжити.')

    # ============================================
    # Системний трей
    # ============================================
    def _setup_tray(self):
        if not HAS_TRAY:
            print("[Tray] pystray/Pillow не знайдено — закриття стандартне")
            self.root.protocol("WM_DELETE_WINDOW", self._on_close_no_tray)
            return

        try:
            img = Image.new('RGBA', (64, 64), (0, 0, 0, 0))
            d = ImageDraw.Draw(img)
            d.ellipse([2, 2, 62, 62], fill=(100, 80, 200, 255))    # фіолетове коло
            d.ellipse([18, 18, 46, 46], fill=(255, 255, 255, 220))  # біла крапка всередині

            def _on_show(icon, item):
                self.root.after(0, self.root.deiconify)
                self.root.after(0, self.root.lift)
                self.root.after(0, self.root.focus_force)

            def _on_quit(icon, item):
                self._tray_icon.stop()
                self.root.after(0, self._quit_app)

            self._tray_icon = pystray.Icon(
                "Sophiya", img, "Софія",
                pystray.Menu(
                    pystray.MenuItem("Відкрити", _on_show, default=True),
                    pystray.MenuItem("Вимкнути", _on_quit),
                )
            )

            # daemon=True — поток вмирає разом з програмою при force-close
            threading.Thread(target=self._tray_icon.run, daemon=True).start()
            print("[Tray] Іконка запущена в треї")

            self.root.protocol("WM_DELETE_WINDOW", lambda: self.root.withdraw())

        except Exception as e:
            print(f"[Tray] Помилка: {e} — закриття стандартне")
            self.root.protocol("WM_DELETE_WINDOW", self._on_close_no_tray)

    def _on_close_no_tray(self):
        self._quit_app()

    def _quit_app(self):
        if self._tray_icon:
            try:
                self._tray_icon.stop()
            except Exception:
                pass
        self.assistant.stop_listening()
        try:
            import voice as _v
            _v.force_restore()
        except Exception:
            pass
        self.root.destroy()

    # ============================================
    # Мінімальний режим (floating widget)
    # ============================================
    def _toggle_mini_mode(self):
        if self._mini_mode:
            self._hide_mini_mode()
        else:
            self._show_mini_mode()

    def _show_mini_mode(self):
        if self._mini_window:
            return
        self._mini_mode = True

        win = tk.Toplevel(self.root)
        win.title("")
        win.geometry("260x90+20+20")
        win.attributes('-topmost', True)
        win.attributes('-alpha', 0.92)
        win.overrideredirect(True)   # Без рамки
        win.configure(bg='#0d1117')
        self._mini_window = win

        # Drag підтримка
        win._drag_x = 0
        win._drag_y = 0

        def _start_drag(e):
            win._drag_x = e.x
            win._drag_y = e.y

        def _drag(e):
            x = win.winfo_x() + e.x - win._drag_x
            y = win.winfo_y() + e.y - win._drag_y
            win.geometry(f"+{x}+{y}")

        # Статус рядок
        top_bar = tk.Frame(win, bg='#161b22', height=22)
        top_bar.pack(fill='x')
        top_bar.bind('<ButtonPress-1>', _start_drag)
        top_bar.bind('<B1-Motion>', _drag)

        self._mini_status_dot = tk.Canvas(top_bar, width=10, height=10,
                                          bg='#161b22', highlightthickness=0)
        self._mini_status_dot.pack(side='left', padx=(8, 4), pady=6)
        self._mini_dot_oval = self._mini_status_dot.create_oval(
            1, 1, 9, 9, fill=COLORS['text_dim'], outline='')

        tk.Label(top_bar, text="Софія", bg='#161b22',
                 fg=COLORS['text_dim'], font=('Segoe UI', 9)).pack(side='left')

        # Кнопка закрити міні-режим
        tk.Button(top_bar, text="✕", bg='#161b22', fg=COLORS['text_dim'],
                  bd=0, font=('Segoe UI', 9), activebackground='#30363d',
                  command=self._hide_mini_mode).pack(side='right', padx=6)

        # Текст останнього повідомлення
        self._mini_label = tk.Label(
            win, text="Натисніть Старт", bg='#0d1117',
            fg=COLORS['text'], font=('Segoe UI', 10),
            wraplength=240, justify='left', anchor='w'
        )
        self._mini_label.pack(fill='both', expand=True, padx=12, pady=6)
        self._mini_label.bind('<ButtonPress-1>', _start_drag)
        self._mini_label.bind('<B1-Motion>', _drag)

    def _hide_mini_mode(self):
        self._mini_mode = False
        if self._mini_window:
            self._mini_window.destroy()
            self._mini_window = None

    def _update_mini(self, text, dot_color=None):
        """Оновлює мінімальне вікно якщо воно відкрите"""
        if not self._mini_window:
            return
        short = text[:55] + '…' if len(text) > 55 else text
        self._mini_window.after(0, lambda: self._mini_label.configure(text=short))
        if dot_color:
            self._mini_window.after(0, lambda: self._mini_status_dot.itemconfig(
                self._mini_dot_oval, fill=dot_color))

    # ============================================
    # Запуск
    # ============================================
    def run(self):
        # Автозапуск слухання після повного відмалювання вікна
        self.root.after(300, self.start_listening)
        self.root.mainloop()


if __name__ == "__main__":
    app = SophiyaUI()
    app.run()
