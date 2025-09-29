import tkinter as tk
from tkinter import ttk
import math
import webbrowser
import datetime
from config import COLORS

class ModernCard(tk.Frame):
    """Moderni kortti-komponentti varjoilla ja hover-efekteillä"""
    
    def __init__(self, parent, title, description, command, icon="", accent_color=None, **kwargs):
        super().__init__(parent, bg=COLORS['white'], relief='flat', bd=0, **kwargs)
        
        self.accent_color = accent_color or COLORS['primary']
        self.command = command
        self.create_card_content(title, description, command, icon)
        self.add_hover_effects()
        
        self.configure(padx=10, pady=10)
    
    def create_card_content(self, title, description, command, icon):
        content_frame = tk.Frame(self, bg=COLORS['white'])
        content_frame.pack(fill='both', expand=True, padx=20, pady=20)
        
        accent_frame = tk.Frame(self, bg=self.accent_color, height=4)
        accent_frame.pack(fill='x', side='top')
        
        if icon:
            icon_label = tk.Label(content_frame, text=icon, font=('Segoe UI', 24), bg=COLORS['white'], fg=self.accent_color)
            icon_label.pack(pady=(0, 10))
        
        title_label = tk.Label(content_frame, text=title, font=('Segoe UI', 14, 'bold'), bg=COLORS['white'], fg=COLORS['text_primary'])
        title_label.pack()
        
        desc_label = tk.Label(content_frame, text=description, font=('Segoe UI', 10), bg=COLORS['white'], fg=COLORS['text_secondary'], wraplength=200, justify='center')
        desc_label.pack(fill='x', pady=(10, 15))
        
        self.action_btn = ModernButton(content_frame, text="Aloita →", command=command, style='primary')
        self.action_btn.pack()
    
    def add_hover_effects(self):
        def on_enter(event):
            self.configure(bg=COLORS['light_hover'], relief='raised', bd=1)
            def update_bg_recursive(widget, bg_color):
                try:
                    if widget.winfo_class() not in ['Button']:
                        widget.configure(bg=bg_color)
                except: pass
                for child in widget.winfo_children():
                    update_bg_recursive(child, bg_color)
            update_bg_recursive(self, COLORS['light_hover'])
        
        def on_leave(event):
            self.configure(bg=COLORS['white'], relief='flat', bd=0)
            def update_bg_recursive(widget, bg_color):
                try:
                    if widget.winfo_class() not in ['Button']:
                        widget.configure(bg=bg_color)
                except: pass
                for child in widget.winfo_children():
                    update_bg_recursive(child, bg_color)
            update_bg_recursive(self, COLORS['white'])
        
        def bind_recursively(widget):
            widget.bind('<Enter>', on_enter)
            widget.bind('<Leave>', on_leave)
            widget.bind('<Button-1>', lambda e: self.command())
            for child in widget.winfo_children():
                if child.winfo_class() not in ['Button']:
                    bind_recursively(child)
        
        bind_recursively(self)

class ModernButton(tk.Button):
    """Moderni painike-komponentti"""
    
    def __init__(self, parent, text="", command=None, style='primary', size='medium', **kwargs):
        self.style = style
        self.size = size
        
        styles = {
            'primary': {'bg': COLORS['primary'], 'fg': COLORS['white'], 'hover_bg': COLORS['primary_light']},
            'secondary': {'bg': COLORS['secondary'], 'fg': COLORS['white'], 'hover_bg': COLORS['primary']},
            'success': {'bg': COLORS['success'], 'fg': COLORS['white'], 'hover_bg': COLORS['success_light']},
            'warning': {'bg': COLORS['warning'], 'fg': COLORS['dark'], 'hover_bg': COLORS['warning']},
            'danger': {'bg': COLORS['danger'], 'fg': COLORS['white'], 'hover_bg': '#ff5252'},
            'ghost': {'bg': COLORS['light'], 'fg': COLORS['primary'], 'hover_bg': COLORS['white']},
            'outline': {'bg': COLORS['white'], 'fg': COLORS['primary'], 'hover_bg': COLORS['light']}
        }
        
        sizes = {
            'small': {'font_size': 9, 'padx': 15, 'pady': 6},
            'medium': {'font_size': 11, 'padx': 20, 'pady': 8},
            'large': {'font_size': 13, 'padx': 30, 'pady': 12}
        }
        
        style_config = styles.get(style, styles['primary'])
        size_config = sizes.get(size, sizes['medium'])
        
        super().__init__(parent, text=text, command=command, font=('Segoe UI', size_config['font_size'], 'bold'),
                         bg=style_config['bg'], fg=style_config['fg'], relief='flat', bd=0,
                         padx=size_config['padx'], pady=size_config['pady'], cursor='hand2', **kwargs)
        
        self.style_config = style_config
        self.bind('<Enter>', self.on_enter)
        self.bind('<Leave>', self.on_leave)
    
    def on_enter(self, event):
        self.configure(bg=self.style_config['hover_bg'])
    
    def on_leave(self, event):
        self.configure(bg=self.style_config['bg'])

class AnimatedProgressBar(tk.Frame):
    """Animoitu edistymispalkki"""
    
    def __init__(self, parent, width=400, height=20, **kwargs):
        super().__init__(parent, **kwargs)
        
        self.width = width
        self.height = height
        self.progress = 0
        self.target_progress = 0
        
        self.canvas = tk.Canvas(self, width=width, height=height, bg=COLORS['light'], highlightthickness=0)
        self.canvas.pack()
        
        self.draw_background()
        self.animation_id = None
    
    def draw_background(self):
        self.canvas.create_rectangle(0, 0, self.width, self.height, fill='#E0E0E0', outline='#CCCCCC', width=1)
    
    def set_progress(self, percentage, animate=True):
        self.target_progress = max(0, min(100, percentage))
        if animate:
            self.animate_to_target()
        else:
            self.progress = self.target_progress
            self.update_visual()
    
    def animate_to_target(self):
        if self.animation_id:
            self.after_cancel(self.animation_id)
        
        def animate_step():
            diff = self.target_progress - self.progress
            if abs(diff) < 0.5:
                self.progress = self.target_progress
                self.update_visual()
                return
            self.progress += diff * 0.1
            self.update_visual()
            self.animation_id = self.after(16, animate_step)
        
        animate_step()
    
    def update_visual(self):
        self.canvas.delete("progress")
        if self.progress > 0:
            progress_width = (self.width * self.progress) / 100
            steps = 20
            for i in range(steps):
                x = (progress_width * i) / steps
                width = progress_width / steps
                ratio = i / steps
                r = int(102 * (1 - ratio) + 118 * ratio)
                g = int(126 * (1 - ratio) + 75 * ratio)
                b = int(234 * (1 - ratio) + 162 * ratio)
                color = f"#{r:02x}{g:02x}{b:02x}"
                self.canvas.create_rectangle(x, 1, x + width, self.height - 1, fill=color, outline="", tags="progress")

class Breadcrumb(tk.Frame):
    """Breadcrumb-navigaatio"""
    
    def __init__(self, parent, **kwargs):
        super().__init__(parent, bg=COLORS['light'], **kwargs)
        self.items = []
    
    def set_path(self, path_items):
        for widget in self.winfo_children():
            widget.destroy()
        self.items = path_items
        for i, (name, callback) in enumerate(path_items):
            if i > 0:
                sep_label = tk.Label(self, text=" › ", bg=COLORS['light'], fg=COLORS['text_secondary'], font=('Segoe UI', 10))
                sep_label.pack(side='left')
            if callback and i < len(path_items) - 1:
                link = tk.Label(self, text=name, bg=COLORS['light'], fg=COLORS['primary'], font=('Segoe UI', 10, 'underline'), cursor='hand2')
                link.bind('<Button-1>', lambda e, cb=callback: cb())
                link.pack(side='left')
            else:
                current = tk.Label(self, text=name, bg=COLORS['light'], fg=COLORS['text_primary'], font=('Segoe UI', 10, 'bold'))
                current.pack(side='left')

class NotificationToast(tk.Toplevel):
    """Toast-notifikaatio"""
    
    def __init__(self, parent, message, toast_type='info', duration=3000):
        super().__init__(parent)
        self.overrideredirect(True)
        self.attributes('-topmost', True)
        
        colors = {'info': COLORS['primary'], 'success': COLORS['success'], 'warning': COLORS['warning'], 'error': COLORS['danger']}
        bg_color = colors.get(toast_type, COLORS['primary'])
        
        frame = tk.Frame(self, bg=bg_color, padx=20, pady=10)
        frame.pack(fill='both', expand=True)
        
        label = tk.Label(frame, text=message, bg=bg_color, fg=COLORS['white'], font=('Segoe UI', 10, 'bold'))
        label.pack()
        
        self.update_idletasks()
        x = parent.winfo_rootx() + parent.winfo_width() - self.winfo_width() - 20
        y = parent.winfo_rooty() + 80
        self.geometry(f"+{x}+{y}")
        
        self.after(duration, self.destroy)
        self.after(duration - 500, lambda: self.attributes('-alpha', 0.7))
        self.after(duration - 250, lambda: self.attributes('-alpha', 0.3))

class Calculator(tk.Toplevel):
    """Yksinkertainen laskin-popup"""
    
    def __init__(self, parent):
        super().__init__(parent)
        self.title("Laskin")
        self.geometry("300x400")
        self.resizable(False, False)
        self.configure(bg=COLORS['light'])
        self.transient(parent)
        self.grab_set()
        self.expression = ""
        
        self.display_var = tk.StringVar()
        display = tk.Entry(self, textvariable=self.display_var, font=('Segoe UI', 24), relief='flat', bg=COLORS['light_hover'], justify='right', state='readonly')
        display.pack(fill='x', padx=10, pady=10, ipady=10)
        
        buttons_frame = tk.Frame(self, bg=COLORS['light'])
        buttons_frame.pack(fill='both', expand=True, padx=5, pady=5)
        
        buttons = ['7', '8', '9', '/', '4', '5', '6', '*', '1', '2', '3', '-', 'C', '0', '.', '+']
        row, col = 0, 0
        for button_text in buttons:
            btn = ModernButton(buttons_frame, text=button_text, command=lambda t=button_text: self.on_button_click(t), style='secondary' if button_text in '/*-+' else 'primary')
            btn.grid(row=row, column=col, padx=5, pady=5, sticky="nsew")
            col += 1
            if col > 3:
                col = 0
                row += 1
        
        equals_btn = ModernButton(buttons_frame, text="=", command=lambda: self.on_button_click('='), style='success', size='large')
        equals_btn.grid(row=4, column=0, columnspan=4, padx=5, pady=5, sticky="nsew")
        
        for i in range(4):
            buttons_frame.grid_columnconfigure(i, weight=1)
        for i in range(5):
            buttons_frame.grid_rowconfigure(i, weight=1)
    
    def on_button_click(self, caption):
        if caption == 'C':
            self.expression = ""
        elif caption == '=':
            try:
                self.expression = str(eval(self.expression))
            except Exception:
                self.expression = "Virhe"
        else:
            if self.expression == "Virhe":
                self.expression = ""
            self.expression += caption
        self.display_var.set(self.expression)

class AchievementPopup(tk.Toplevel):
    """Parannettu saavutuspopup"""
    
    def __init__(self, parent, achievement):
        super().__init__(parent)
        self.achievement = achievement
        self.title("Uusi saavutus!")
        self.geometry("450x250")
        self.configure(bg=COLORS['gold'])
        self.resizable(False, False)
        self.overrideredirect(True)
        self.attributes('-topmost', True)
        
        self.update_idletasks()
        x = parent.winfo_rootx() + (parent.winfo_width() - self.winfo_width()) // 2
        y = parent.winfo_rooty() + (parent.winfo_height() - self.winfo_height()) // 2
        self.geometry(f"+{x}+{y}")
        
        self.create_popup_content()
        self.animate_in()
        self.after(4000, self.animate_out)
    
    def create_popup_content(self):
        main_frame = tk.Frame(self, bg=COLORS['gold'], padx=30, pady=25)
        main_frame.pack(fill='both', expand=True)
        
        icon_label = tk.Label(main_frame, text=self.achievement.icon, font=('Segoe UI', 48), bg=COLORS['gold'], fg=COLORS['white'])
        icon_label.pack(pady=(0, 15))
        
        title_label = tk.Label(main_frame, text="🎉 Uusi saavutus avattu!", font=('Segoe UI', 16, 'bold'), bg=COLORS['gold'], fg=COLORS['white'])
        title_label.pack(pady=(0, 10))
        
        name_label = tk.Label(main_frame, text=self.achievement.name, font=('Segoe UI', 18, 'bold'), bg=COLORS['gold'], fg=COLORS['white'])
        name_label.pack(pady=(0, 8))
        
        desc_label = tk.Label(main_frame, text=self.achievement.description, font=('Segoe UI', 12), bg=COLORS['gold'], fg=COLORS['white'], wraplength=350, justify='center')
        desc_label.pack(pady=(0, 20))
        
        close_btn = ModernButton(main_frame, text="Jatka", command=self.animate_out, style='ghost', size='medium')
        close_btn.configure(bg=COLORS['white'], fg=COLORS['gold'])
        close_btn.pack()
    
    def animate_in(self):
        self.attributes('-alpha', 0.0)
        self.fade_in(0.0)
    
    def fade_in(self, alpha):
        alpha += 0.1
        self.attributes('-alpha', alpha)
        if alpha < 1.0:
            self.after(50, lambda: self.fade_in(alpha))
    
    def animate_out(self):
        self.fade_out(1.0)
    
    def fade_out(self, alpha):
        alpha -= 0.1
        self.attributes('-alpha', alpha)
        if alpha > 0.0:
            self.after(50, lambda: self.fade_out(alpha))
        else:
            self.destroy()