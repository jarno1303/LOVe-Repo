import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import datetime
import sqlite3
import json
import random
from dataclasses import asdict

from config import COLORS, config, AppConfig, THEMES
from ui.components import ModernButton, AnimatedProgressBar

# Yritä tuoda Matplotlib
try:
    import matplotlib.pyplot as plt
    from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
    from matplotlib.figure import Figure
    MATPLOTLIB_AVAILABLE = True
except ImportError:
    MATPLOTLIB_AVAILABLE = False


class EnhancedPracticeView(tk.Frame):
    def __init__(self, parent, app, questions, session_name, time_limit=None, spaced_repetition=False):
        super().__init__(parent, bg=COLORS['light'])
        self.app = app
        self.questions = questions
        self.session_name = session_name
        self.time_limit = time_limit
        self.spaced_repetition = spaced_repetition
        
        self.current_question_index = 0
        self.corrects = 0
        self.start_time = datetime.datetime.now()
        self.question_start_time = None
        
        self.create_practice_interface()
        self.load_question()
        
        if time_limit:
            self.start_timer()
    
    def create_practice_interface(self):
        header_frame = tk.Frame(self, bg=COLORS['primary'], height=80)
        header_frame.pack(fill='x')
        header_frame.pack_propagate(False)
        
        header_content = tk.Frame(header_frame, bg=COLORS['primary'])
        header_content.pack(expand=True, fill='both', padx=30)
        
        self.session_label = tk.Label(header_content, text=self.session_name, font=('Segoe UI', 16, 'bold'), bg=COLORS['primary'], fg=COLORS['white'])
        self.session_label.pack(side='left', pady=25)
        
        right_info = tk.Frame(header_content, bg=COLORS['primary'])
        right_info.pack(side='right', pady=25)
        
        self.progress_label = tk.Label(right_info, text="", font=('Segoe UI', 12, 'bold'), bg=COLORS['primary'], fg=COLORS['white'])
        self.progress_label.pack()
        
        if self.time_limit:
            self.timer_label = tk.Label(right_info, text="", font=('Segoe UI', 11), bg=COLORS['primary'], fg=COLORS['white'])
            self.timer_label.pack()
        
        self.progress_bar = AnimatedProgressBar(self, width=self.winfo_reqwidth(), height=8)
        self.progress_bar.pack(fill='x', padx=20, pady=(10, 0))
        
        main_frame = tk.Frame(self, bg=COLORS['light'])
        main_frame.pack(fill='both', expand=True, padx=30, pady=20)
        
        self.question_frame = tk.Frame(main_frame, bg=COLORS['white'], relief='flat', bd=0)
        self.question_frame.pack(fill='x', pady=(0, 20))
        
        question_inner = tk.Frame(self.question_frame, bg=COLORS['white'])
        question_inner.pack(fill='both', expand=True, padx=30, pady=25)
        
        self.question_label = tk.Label(question_inner, text="", font=('Segoe UI', 14), bg=COLORS['white'], fg=COLORS['text_primary'], wraplength=800, justify="left")
        self.question_label.pack(fill='x')
        
        self.options_frame = tk.Frame(main_frame, bg=COLORS['light'])
        self.options_frame.pack(fill='x', pady=(0, 20))
        
        self.selected_option = tk.IntVar(value=-1)
        self.option_buttons = []
        
        btn_frame = tk.Frame(main_frame, bg=COLORS['light'])
        btn_frame.pack(fill='x')
        
        self.submit_btn = ModernButton(btn_frame, text="Vastaa", command=self.submit_answer, style='primary', size='large')
        self.submit_btn.pack(side='left')
        
        self.next_btn = ModernButton(btn_frame, text="Seuraava →", command=self.next_question, style='secondary', size='large')
        self.next_btn.pack(side='left', padx=(10, 0))
        self.next_btn.configure(state='disabled')
        
        back_btn = ModernButton(btn_frame, text="← Takaisin", command=self.end_session, style='ghost', size='medium')
        back_btn.pack(side='right')
    
    def load_question(self):
        if self.current_question_index >= len(self.questions):
            self.end_session()
            return
        
        self.question_start_time = datetime.datetime.now()
        question = self.questions[self.current_question_index]
        
        progress = ((self.current_question_index + 1) / len(self.questions)) * 100
        self.progress_label.config(text=f"Kysymys {self.current_question_index + 1}/{len(self.questions)}")
        self.progress_bar.set_progress(progress)
        
        self.question_label.config(text=question.question)
        
        for widget in self.options_frame.winfo_children():
            widget.destroy()
        
        self.option_buttons = []
        self.selected_option.set(-1)
        
        for i, option in enumerate(question.options):
            option_frame = tk.Frame(self.options_frame, bg=COLORS['white'], relief='flat', bd=1)
            option_frame.pack(fill='x', pady=5)
            rb = tk.Radiobutton(option_frame, text=f"{chr(65+i)}. {option}",
                                variable=self.selected_option, value=i,
                                font=('Segoe UI', 12), bg=COLORS['white'], fg=COLORS['text_primary'],
                                selectcolor=COLORS['primary'], relief='flat', bd=0,
                                padx=20, pady=15, cursor='hand2')
            rb.pack(fill='x', anchor='w')
            self.option_buttons.append((option_frame, rb))
        
        self.submit_btn.configure(state='normal')
        self.next_btn.configure(state='disabled')
    
    def submit_answer(self):
        if self.selected_option.get() == -1:
            self.app.show_toast("Valitse vastaus ensin", 'warning')
            return
        
        question = self.questions[self.current_question_index]
        user_answer = self.selected_option.get()
        is_correct = user_answer == question.correct
        
        time_taken = (datetime.datetime.now() - self.question_start_time).total_seconds()
        self.app.db_manager.update_question_stats(question.id, is_correct, time_taken)
        
        if is_correct:
            self.corrects += 1
        
        if self.spaced_repetition:
            performance_rating = 5 if is_correct else 2
            interval, ease_factor = self.app.spaced_repetition_manager.calculate_next_review(question, performance_rating)
            with sqlite3.connect(self.app.db_manager.db_path) as conn:
                conn.execute("UPDATE questions SET interval = ?, ease_factor = ? WHERE id = ?", (interval, ease_factor, question.id))
        
        self.show_answer_feedback(is_correct, question)
        self.app.check_and_show_achievements(context={'fast_answer': time_taken < 5})
        
        self.submit_btn.configure(state='disabled')
        self.next_btn.configure(state='normal')
    
    def show_answer_feedback(self, is_correct, question):
        for i, (option_frame, rb) in enumerate(self.option_buttons):
            if i == question.correct:
                option_frame.configure(bg=COLORS['success_light'])
                rb.configure(bg=COLORS['success_light'])
            elif i == self.selected_option.get() and not is_correct:
                option_frame.configure(bg=COLORS['danger'])
                rb.configure(bg=COLORS['danger'], fg=COLORS['white'])
        self.show_explanation_popup(question.explanation, is_correct)
    
    def show_explanation_popup(self, explanation, is_correct):
        from ui.components import ModernButton # Vältetään circular import
        popup = tk.Toplevel(self)
        popup.title("Selitys")
        popup.geometry("500x300")
        popup.configure(bg=COLORS['white'])
        popup.transient(self)
        popup.grab_set()
        
        popup.update_idletasks()
        x = self.winfo_rootx() + (self.winfo_width() - popup.winfo_width()) // 2
        y = self.winfo_rooty() + (self.winfo_height() - popup.winfo_height()) // 2
        popup.geometry(f"+{x}+{y}")
        
        header_color = COLORS['success'] if is_correct else COLORS['danger']
        header_text = "✅ Oikein!" if is_correct else "❌ Väärin"
        
        header_frame = tk.Frame(popup, bg=header_color, height=60)
        header_frame.pack(fill='x')
        header_frame.pack_propagate(False)
        
        header_label = tk.Label(header_frame, text=header_text, font=('Segoe UI', 16, 'bold'), bg=header_color, fg=COLORS['white'])
        header_label.pack(expand=True)
        
        content_frame = tk.Frame(popup, bg=COLORS['white'])
        content_frame.pack(fill='both', expand=True, padx=20, pady=20)
        
        explanation_label = tk.Label(content_frame, text=explanation, font=('Segoe UI', 11), bg=COLORS['white'], fg=COLORS['text_primary'], wraplength=450, justify='left')
        explanation_label.pack(fill='both', expand=True)
        
        close_btn = ModernButton(content_frame, text="Jatka", command=popup.destroy, style='primary')
        close_btn.pack(pady=(20, 0))
    
    def next_question(self):
        self.current_question_index += 1
        self.load_question()
    
    def start_timer(self):
        def update_timer():
            if hasattr(self, 'timer_label') and self.timer_label.winfo_exists():
                elapsed = (datetime.datetime.now() - self.start_time).total_seconds()
                remaining = max(0, self.time_limit - elapsed)
                minutes, seconds = int(remaining // 60), int(remaining % 60)
                self.timer_label.config(text=f"⏱️ {minutes:02d}:{seconds:02d}")
                if remaining <= 0:
                    self.end_session()
                    return
                self.after(1000, update_timer)
        update_timer()

    def end_session(self):
        total_questions = self.current_question_index
        if total_questions > 0: # Varmistetaan ettei jaeta nollalla
            self.app.stats_manager.end_session(total_questions, self.corrects)
        self.show_session_results()
    
    def show_session_results(self):
        self.pack_forget()
        results_frame = tk.Frame(self.master, bg=COLORS['light'])
        results_frame.pack(fill='both', expand=True, padx=30, pady=30)
        
        total_answered = self.current_question_index
        success_rate = (self.corrects / max(total_answered, 1)) * 100
        
        if success_rate >= 80:
            header_color, result_text = COLORS['success'], "🎉 Erinomaista!"
        elif success_rate >= 60:
            header_color, result_text = COLORS['warning'], "👍 Hyvin tehty!"
        else:
            header_color, result_text = COLORS['danger'], "📚 Harjoittelua vielä"
        
        header_frame = tk.Frame(results_frame, bg=header_color, height=100)
        header_frame.pack(fill='x')
        header_frame.pack_propagate(False)
        
        result_label = tk.Label(header_frame, text=result_text, font=('Segoe UI', 24, 'bold'), bg=header_color, fg=COLORS['white'])
        result_label.pack(expand=True)
        
        content_frame = tk.Frame(results_frame, bg=COLORS['white'])
        content_frame.pack(fill='both', expand=True, pady=20)
        
        stats_frame = tk.Frame(content_frame, bg=COLORS['white'])
        stats_frame.pack(expand=True, padx=50, pady=50)
        
        score_frame = tk.Frame(stats_frame, bg=COLORS['light'])
        score_frame.pack(pady=20)
        
        score_label = tk.Label(score_frame, text=f"{self.corrects}/{total_answered}", font=('Segoe UI', 36, 'bold'), bg=COLORS['light'], fg=COLORS['primary'])
        score_label.pack()
        
        percentage_label = tk.Label(score_frame, text=f"{success_rate:.1f}%", font=('Segoe UI', 18), bg=COLORS['light'], fg=COLORS['text_primary'])
        percentage_label.pack()
        
        elapsed = (datetime.datetime.now() - self.start_time).total_seconds()
        time_label = tk.Label(stats_frame, text=f"Aika: {int(elapsed//60)}:{int(elapsed%60):02d}", font=('Segoe UI', 14), bg=COLORS['white'], fg=COLORS['text_secondary'])
        time_label.pack(pady=10)
        
        actions_frame = tk.Frame(content_frame, bg=COLORS['white'])
        actions_frame.pack(pady=20)
        
        retry_btn = ModernButton(actions_frame, text="🔄 Aloita uudelleen", command=self.retry_session, style='secondary')
        retry_btn.pack(side='left', padx=10)
        
        home_btn = ModernButton(actions_frame, text="🏠 Päävalikkoon", command=self.app.show_main_menu, style='primary')
        home_btn.pack(side='left', padx=10)
    
    def retry_session(self):
        random.shuffle(self.questions)
        self.master.pack_forget()
        self.app.start_practice_session(self.questions, self.session_name, self.time_limit, self.spaced_repetition)

class EnhancedSimulationView(tk.Frame):
    def __init__(self, parent, app, questions):
        super().__init__(parent, bg=COLORS['light'])
        self.app = app
        self.questions = questions
        self.current_question_index = 0
        self.answers = [-1] * len(questions)
        self.start_time = datetime.datetime.now()
        self.time_limit = 3600
        
        self.create_simulation_interface()
        self.load_question()
        self.start_timer()
    
    def create_simulation_interface(self):
        header_frame = tk.Frame(self, bg=COLORS['danger'], height=80)
        header_frame.pack(fill='x')
        header_frame.pack_propagate(False)
        header_content = tk.Frame(header_frame, bg=COLORS['danger'])
        header_content.pack(expand=True, fill='both', padx=30)
        title_label = tk.Label(header_content, text="🎓 Koesimulaatio", font=('Segoe UI', 16, 'bold'), bg=COLORS['danger'], fg=COLORS['white'])
        title_label.pack(side='left', pady=25)
        right_info = tk.Frame(header_content, bg=COLORS['danger'])
        right_info.pack(side='right', pady=25)
        self.timer_label = tk.Label(right_info, text="", font=('Segoe UI', 14, 'bold'), bg=COLORS['danger'], fg=COLORS['white'])
        self.timer_label.pack()
        self.progress_label = tk.Label(right_info, text="", font=('Segoe UI', 11), bg=COLORS['danger'], fg=COLORS['white'])
        self.progress_label.pack()
        
        self.progress_bar = AnimatedProgressBar(self, width=self.winfo_reqwidth(), height=8)
        self.progress_bar.pack(fill='x', padx=20, pady=(10, 0))
        
        main_frame = tk.Frame(self, bg=COLORS['light'])
        main_frame.pack(fill='both', expand=True, padx=30, pady=20)
        
        nav_frame = tk.Frame(main_frame, bg=COLORS['white'], width=200)
        nav_frame.pack(side='left', fill='y', padx=(0, 20))
        nav_frame.pack_propagate(False)
        nav_title = tk.Label(nav_frame, text="Kysymykset", font=('Segoe UI', 12, 'bold'), bg=COLORS['white'], fg=COLORS['text_primary'])
        nav_title.pack(pady=10)
        
        self.nav_buttons_frame = tk.Frame(nav_frame, bg=COLORS['white'])
        self.nav_buttons_frame.pack(fill='both', expand=True, padx=10, pady=10)
        self.create_navigation_buttons()
        
        content_frame = tk.Frame(main_frame, bg=COLORS['light'])
        content_frame.pack(side='right', fill='both', expand=True)
        
        self.question_frame = tk.Frame(content_frame, bg=COLORS['white'])
        self.question_frame.pack(fill='x', pady=(0, 20))
        question_inner = tk.Frame(self.question_frame, bg=COLORS['white'])
        question_inner.pack(fill='both', expand=True, padx=25, pady=20)
        self.question_label = tk.Label(question_inner, text="", font=('Segoe UI', 14), bg=COLORS['white'], fg=COLORS['text_primary'], wraplength=600, justify="left")
        self.question_label.pack(fill='x')
        
        self.options_frame = tk.Frame(content_frame, bg=COLORS['light'])
        self.options_frame.pack(fill='x', pady=(0, 20))
        self.selected_option = tk.IntVar(value=-1)
        
        btn_frame = tk.Frame(content_frame, bg=COLORS['light'])
        btn_frame.pack(fill='x')
        self.prev_btn = ModernButton(btn_frame, text="← Edellinen", command=self.prev_question, style='secondary')
        self.prev_btn.pack(side='left')
        self.next_btn = ModernButton(btn_frame, text="Seuraava →", command=self.next_question, style='primary')
        self.next_btn.pack(side='left', padx=(10, 0))
        self.finish_btn = ModernButton(btn_frame, text="🏁 Lopeta koe", command=self.finish_simulation, style='warning')
        self.finish_btn.pack(side='right')

    def create_navigation_buttons(self):
        for i in range(len(self.questions)):
            row, col = i // 5, i % 5
            btn = tk.Button(self.nav_buttons_frame, text=str(i+1), font=('Segoe UI', 9), width=4, height=2,
                            bg=COLORS['light'], fg=COLORS['text_primary'], relief='flat', bd=1,
                            cursor='hand2', command=lambda idx=i: self.goto_question(idx))
            btn.grid(row=row, column=col, padx=2, pady=2)
            setattr(self, f'nav_btn_{i}', btn)

    def update_navigation_button(self, index):
        btn = getattr(self, f'nav_btn_{index}')
        if self.answers[index] != -1:
            btn.configure(bg=COLORS['success'])
        elif index == self.current_question_index:
            btn.configure(bg=COLORS['primary'])
        else:
            btn.configure(bg=COLORS['light'])

    def update_all_navigation_buttons(self):
        for i in range(len(self.questions)):
            self.update_navigation_button(i)

    def goto_question(self, index):
        self.save_current_answer()
        self.current_question_index = index
        self.load_question()

    def load_question(self):
        question = self.questions[self.current_question_index]
        progress = ((self.current_question_index + 1) / len(self.questions)) * 100
        self.progress_label.config(text=f"Kysymys {self.current_question_index + 1}/{len(self.questions)}")
        self.progress_bar.set_progress(progress)
        self.question_label.config(text=question.question)
        for widget in self.options_frame.winfo_children():
            widget.destroy()
        saved_answer = self.answers[self.current_question_index]
        self.selected_option.set(saved_answer)
        for i, option in enumerate(question.options):
            option_frame = tk.Frame(self.options_frame, bg=COLORS['white'], relief='flat', bd=1)
            option_frame.pack(fill='x', pady=5)
            rb = tk.Radiobutton(option_frame, text=f"{chr(65+i)}. {option}",
                                variable=self.selected_option, value=i,
                                font=('Segoe UI', 12), bg=COLORS['white'], fg=COLORS['text_primary'],
                                selectcolor=COLORS['primary'], relief='flat', bd=0, padx=20, pady=15,
                                cursor='hand2', command=self.save_current_answer)
            rb.pack(fill='x', anchor='w')
        self.update_all_navigation_buttons()
        self.prev_btn.configure(state='normal' if self.current_question_index > 0 else 'disabled')
        self.next_btn.configure(text="🏁 Viimeinen" if self.current_question_index == len(self.questions) - 1 else "Seuraava →")

    def save_current_answer(self):
        self.answers[self.current_question_index] = self.selected_option.get()
        self.update_navigation_button(self.current_question_index)

    def prev_question(self):
        if self.current_question_index > 0:
            self.save_current_answer()
            self.current_question_index -= 1
            self.load_question()

    def next_question(self):
        self.save_current_answer()
        if self.current_question_index < len(self.questions) - 1:
            self.current_question_index += 1
            self.load_question()
        else:
            self.finish_simulation()

    def start_timer(self):
        def update_timer():
            if self.winfo_exists():
                elapsed = (datetime.datetime.now() - self.start_time).total_seconds()
                remaining = max(0, self.time_limit - elapsed)
                minutes, seconds = int(remaining // 60), int(remaining % 60)
                self.timer_label.config(text=f"⏱️ {minutes:02d}:{seconds:02d}")
                if remaining <= 300: self.timer_label.configure(fg='#ffff00')
                if remaining <= 60: self.timer_label.configure(fg='#ff4444')
                if remaining <= 0:
                    self.finish_simulation()
                    return
                self.after(1000, update_timer)
        update_timer()

    def finish_simulation(self):
        self.save_current_answer()
        correct_count = sum(1 for i, answer in enumerate(self.answers) if answer == self.questions[i].correct)
        self.app.stats_manager.end_session(len(self.questions), correct_count)
        self.show_simulation_results(correct_count)

    def show_simulation_results(self, correct_count):
        self.pack_forget()
        total = len(self.questions)
        percentage = (correct_count / total) * 100 if total > 0 else 0
        passed = percentage >= 60
        results_frame = tk.Frame(self.master, bg=COLORS['light'])
        results_frame.pack(fill='both', expand=True, padx=30, pady=30)
        
        header_color = COLORS['success'] if passed else COLORS['danger']
        header_text = "🎉 HYVÄKSYTTY!" if passed else "❌ HYLÄTTY"
        header_frame = tk.Frame(results_frame, bg=header_color, height=120)
        header_frame.pack(fill='x')
        header_frame.pack_propagate(False)
        result_label = tk.Label(header_frame, text=header_text, font=('Segoe UI', 28, 'bold'), bg=header_color, fg=COLORS['white'])
        result_label.pack(expand=True)
        
        content_frame = tk.Frame(results_frame, bg=COLORS['white'])
        content_frame.pack(fill='both', expand=True, pady=20)
        center_frame = tk.Frame(content_frame, bg=COLORS['white'])
        center_frame.pack(expand=True, padx=100, pady=50)
        
        score_label = tk.Label(center_frame, text=f"{correct_count} / {total}", font=('Segoe UI', 48, 'bold'), bg=COLORS['white'], fg=COLORS['primary'])
        score_label.pack(pady=(0, 10))
        percentage_label = tk.Label(center_frame, text=f"{percentage:.1f}%", font=('Segoe UI', 24), bg=COLORS['white'], fg=COLORS['text_primary'])
        percentage_label.pack(pady=(0, 20))
        
        elapsed = (datetime.datetime.now() - self.start_time).total_seconds()
        time_label = tk.Label(center_frame, text=f"Aika: {int(elapsed//60)}:{int(elapsed%60):02d}", font=('Segoe UI', 14), bg=COLORS['white'], fg=COLORS['text_secondary'])
        time_label.pack(pady=(0, 30))
        
        actions_frame = tk.Frame(center_frame, bg=COLORS['white'])
        actions_frame.pack()
        review_btn = ModernButton(actions_frame, text="📖 Tarkasta vastaukset", command=lambda: self.show_review(correct_count), style='secondary')
        review_btn.pack(side='left', padx=10)
        home_btn = ModernButton(actions_frame, text="🏠 Päävalikkoon", command=self.app.show_main_menu, style='primary')
        home_btn.pack(side='left', padx=10)
        
        self.app.check_and_show_achievements(context={'simulation_perfect': correct_count == total})

    def show_review(self, correct_count):
        review_window = tk.Toplevel(self.app)
        review_window.title("Vastausten tarkastelu")
        review_window.geometry("800x600")
        review_window.configure(bg=COLORS['light'])
        
        canvas = tk.Canvas(review_window, bg=COLORS['light'])
        scrollbar = ttk.Scrollbar(review_window, orient="vertical", command=canvas.yview)
        scrollable_frame = tk.Frame(canvas, bg=COLORS['light'])
        scrollable_frame.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)
        
        for i, question in enumerate(self.questions):
            user_answer = self.answers[i]
            is_correct = user_answer == question.correct
            
            card_frame = tk.Frame(scrollable_frame, bg=COLORS['white'], relief='solid', bd=1)
            card_frame.pack(fill='x', padx=20, pady=10)
            
            header_color = COLORS['success'] if is_correct else COLORS['danger']
            header_text = f"Kysymys {i+1} - {'✅ Oikein' if is_correct else '❌ Väärin'}"
            header_frame = tk.Frame(card_frame, bg=header_color)
            header_frame.pack(fill='x')
            header_label = tk.Label(header_frame, text=header_text, font=('Segoe UI', 12, 'bold'), bg=header_color, fg=COLORS['white'])
            header_label.pack(pady=8)
            
            q_frame = tk.Frame(card_frame, bg=COLORS['white'])
            q_frame.pack(fill='x', padx=15, pady=10)
            question_text = tk.Label(q_frame, text=question.question, font=('Segoe UI', 11), bg=COLORS['white'], fg=COLORS['text_primary'], wraplength=700, justify='left')
            question_text.pack(anchor='w')
            
            for j, option in enumerate(question.options):
                if j == question.correct:
                    color, prefix = COLORS['success_light'], "✅"
                elif j == user_answer and not is_correct:
                    color, prefix = COLORS['danger'], "❌"
                else:
                    color, prefix = COLORS['white'], "  "
                
                option_label = tk.Label(q_frame, text=f"{prefix} {chr(65+j)}. {option}", font=('Segoe UI', 10), bg=color, fg=COLORS['text_primary'], anchor='w')
                option_label.pack(fill='x', padx=20, pady=2)
        
        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

class EnhancedStatsView(tk.Frame):
    """Parannettu tilastonäkymä"""
    def __init__(self, parent, app):
        super().__init__(parent, bg=COLORS['light'])
        self.app = app
        self.create_stats_interface()
    
    def create_stats_interface(self):
        title_frame = tk.Frame(self, bg=COLORS['light'])
        title_frame.pack(fill='x', pady=(0, 20))
        title_label = tk.Label(title_frame, text="📊 Oppimisanalytiikka", font=('Segoe UI', 24, 'bold'), bg=COLORS['light'], fg=COLORS['text_primary'])
        title_label.pack()
        
        notebook = ttk.Notebook(self)
        notebook.pack(expand=True, fill='both', padx=20, pady=10)
        
        overview_frame = tk.Frame(notebook, bg=COLORS['light'])
        notebook.add(overview_frame, text="📈 Yleiskatsaus")
        self.create_overview_tab(overview_frame)
        
        detailed_frame = tk.Frame(notebook, bg=COLORS['light'])
        notebook.add(detailed_frame, text="📋 Yksityiskohdat")
        self.create_detailed_tab(detailed_frame)
        
        if MATPLOTLIB_AVAILABLE:
            charts_frame = tk.Frame(notebook, bg=COLORS['light'])
            notebook.add(charts_frame, text="📊 Graafit")
            self.create_charts_tab(charts_frame)
        
        recommendations_frame = tk.Frame(notebook, bg=COLORS['light'])
        notebook.add(recommendations_frame, text="💡 Suositukset")
        self.create_recommendations_tab(recommendations_frame)
    
    def create_overview_tab(self, parent):
        canvas = tk.Canvas(parent, bg=COLORS['light'])
        scrollbar = ttk.Scrollbar(parent, orient="vertical", command=canvas.yview)
        scrollable_frame = tk.Frame(canvas, bg=COLORS['light'])
        scrollable_frame.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)
        
        analytics = self.app.stats_manager.get_learning_analytics()
        
        general_frame = tk.Frame(scrollable_frame, bg=COLORS['light'])
        general_frame.pack(fill='x', padx=20, pady=10)
        
        general_stats = analytics['general']
        stats_cards = [
            ("Kysymyksiä pankissa", str(general_stats.get('total_questions_in_db', 0)), "📚", COLORS['primary']),
            ("Vastattuja kysymyksiä", str(general_stats.get('answered_questions', 0)), "📝", COLORS['accent']),
            ("Onnistumisprosentti", f"{general_stats.get('avg_success_rate', 0)*100:.1f}%", "🎯", COLORS['success']),
            ("Yrityksiä yhteensä", str(general_stats.get('total_attempts', 0)), "🔢", COLORS['secondary'])
        ]
        
        for i, (title, value, icon, color) in enumerate(stats_cards):
            card = self.create_stat_card(general_frame, title, value, icon, color)
            card.grid(row=0, column=i, padx=10, pady=10, sticky='nsew')
            general_frame.grid_columnconfigure(i, weight=1)
        
        if analytics['categories']:
            cat_frame = tk.LabelFrame(scrollable_frame, text="Kategoriakohtaiset tulokset", font=('Segoe UI', 12, 'bold'), bg=COLORS['light'], fg=COLORS['text_primary'])
            cat_frame.pack(fill='x', padx=20, pady=20)
            for category in analytics['categories']:
                cat_item = tk.Frame(cat_frame, bg=COLORS['white'], relief='flat', bd=1)
                cat_item.pack(fill='x', padx=10, pady=5)
                name_label = tk.Label(cat_item, text=category['category'].title(), font=('Segoe UI', 11, 'bold'), bg=COLORS['white'], fg=COLORS['text_primary'])
                name_label.pack(side='left', padx=15, pady=10)
                progress_frame = tk.Frame(cat_item, bg=COLORS['white'])
                progress_frame.pack(side='right', padx=15, pady=10)
                success_rate = category.get('success_rate', 0) * 100
                progress_bar = AnimatedProgressBar(progress_frame, width=200, height=15)
                progress_bar.pack()
                progress_bar.set_progress(success_rate)
                percent_label = tk.Label(progress_frame, text=f"{success_rate:.1f}%", font=('Segoe UI', 10), bg=COLORS['white'], fg=COLORS['text_secondary'])
                percent_label.pack()
        
        if analytics['weekly_progress']:
            week_frame = tk.LabelFrame(scrollable_frame, text="Viikon edistyminen", font=('Segoe UI', 12, 'bold'), bg=COLORS['light'], fg=COLORS['text_primary'])
            week_frame.pack(fill='x', padx=20, pady=20)
            for day_data in analytics['weekly_progress'][-7:]:
                day_frame = tk.Frame(week_frame, bg=COLORS['white'])
                day_frame.pack(fill='x', padx=10, pady=2)
                date_label = tk.Label(day_frame, text=day_data['date'], font=('Segoe UI', 10), bg=COLORS['white'], fg=COLORS['text_secondary'])
                date_label.pack(side='left', padx=10, pady=5)
                stats_text = f"{day_data['corrects']}/{day_data['questions_answered']} oikein"
                stats_label = tk.Label(day_frame, text=stats_text, font=('Segoe UI', 10, 'bold'), bg=COLORS['white'], fg=COLORS['text_primary'])
                stats_label.pack(side='right', padx=10, pady=5)
        
        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
    
    def create_stat_card(self, parent, title, value, icon, color):
        card = tk.Frame(parent, bg=COLORS['white'], relief='flat', bd=1)
        accent = tk.Frame(card, bg=color, height=4)
        accent.pack(fill='x', side='top')
        content = tk.Frame(card, bg=COLORS['white'])
        content.pack(fill='both', expand=True, padx=20, pady=20)
        icon_label = tk.Label(content, text=icon, font=('Segoe UI', 24), bg=COLORS['white'], fg=color)
        icon_label.pack(pady=(0, 10))
        value_label = tk.Label(content, text=value, font=('Segoe UI', 20, 'bold'), bg=COLORS['white'], fg=COLORS['text_primary'])
        value_label.pack()
        title_label = tk.Label(content, text=title, font=('Segoe UI', 10), bg=COLORS['white'], fg=COLORS['text_secondary'])
        title_label.pack(pady=(5, 0))
        return card
    
    def create_detailed_tab(self, parent):
        canvas = tk.Canvas(parent, bg=COLORS['light'])
        scrollbar = ttk.Scrollbar(parent, orient="vertical", command=canvas.yview)
        scrollable_frame = tk.Frame(canvas, bg=COLORS['light'])
        scrollable_frame.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)
        
        analytics = self.app.stats_manager.get_learning_analytics()
        
        if analytics['difficulties']:
            diff_frame = tk.LabelFrame(scrollable_frame, text="Vaikeustasot", font=('Segoe UI', 12, 'bold'), bg=COLORS['light'], fg=COLORS['text_primary'])
            diff_frame.pack(fill='x', padx=20, pady=20)
            for difficulty in analytics['difficulties']:
                diff_item = tk.Frame(diff_frame, bg=COLORS['white'])
                diff_item.pack(fill='x', padx=10, pady=5)
                name_label = tk.Label(diff_item, text=difficulty['difficulty'].title(), font=('Segoe UI', 11, 'bold'), bg=COLORS['white'], fg=COLORS['text_primary'])
                name_label.pack(side='left', padx=15, pady=10)
                success_rate = difficulty.get('success_rate', 0) * 100
                rate_label = tk.Label(diff_item, text=f"{success_rate:.1f}%", font=('Segoe UI', 11), bg=COLORS['white'], fg=COLORS['text_secondary'])
                rate_label.pack(side='right', padx=15, pady=10)
        
        with sqlite3.connect(self.app.db_manager.db_path) as conn:
            conn.row_factory = sqlite3.Row
            sessions = conn.execute("SELECT * FROM study_sessions WHERE end_time IS NOT NULL ORDER BY start_time DESC LIMIT 10").fetchall()
        
        if sessions:
            session_frame = tk.LabelFrame(scrollable_frame, text="Viimeisimmät opiskelusessiot", font=('Segoe UI', 12, 'bold'), bg=COLORS['light'], fg=COLORS['text_primary'])
            session_frame.pack(fill='x', padx=20, pady=20)
            for session in sessions:
                session_item = tk.Frame(session_frame, bg=COLORS['white'])
                session_item.pack(fill='x', padx=10, pady=5)
                date_str = session['start_time'][:16]
                type_text = session['session_type'].title()
                info_label = tk.Label(session_item, text=f"{type_text} - {date_str}", font=('Segoe UI', 10, 'bold'), bg=COLORS['white'], fg=COLORS['text_primary'])
                info_label.pack(side='left', padx=15, pady=8)
                if session['questions_answered'] > 0:
                    success_rate = (session['questions_correct'] / session['questions_answered']) * 100
                    result_text = f"{session['questions_correct']}/{session['questions_answered']} ({success_rate:.1f}%)"
                else:
                    result_text = "Ei kysymyksiä"
                result_label = tk.Label(session_item, text=result_text, font=('Segoe UI', 10), bg=COLORS['white'], fg=COLORS['text_secondary'])
                result_label.pack(side='right', padx=15, pady=8)
        
        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
    
    def create_charts_tab(self, parent):
        if not MATPLOTLIB_AVAILABLE:
            error_label = tk.Label(parent, text="Matplotlib ei ole saatavilla.\nAsenna: pip install matplotlib", font=('Segoe UI', 12), bg=COLORS['light'], fg=COLORS['danger'])
            error_label.pack(expand=True)
            return
        
        canvas = tk.Canvas(parent, bg=COLORS['light'])
        scrollbar = ttk.Scrollbar(parent, orient="vertical", command=canvas.yview)
        scrollable_frame = tk.Frame(canvas, bg=COLORS['light'])
        scrollable_frame.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)
        
        analytics = self.app.stats_manager.get_learning_analytics()
        
        if analytics['categories']:
            fig1 = Figure(figsize=(12, 5), dpi=100)
            fig1.patch.set_facecolor(COLORS['light'])
            ax1 = fig1.add_subplot(121)
            categories = [cat['category'] for cat in analytics['categories']]
            success_rates = [cat.get('success_rate', 0) * 100 for cat in analytics['categories']]
            colors = [COLORS['primary'], COLORS['secondary'], COLORS['accent'], COLORS['success'], COLORS['warning']]
            bars = ax1.bar(range(len(categories)), success_rates, color=colors[:len(categories)])
            ax1.set_title('Onnistumisprosentit kategorioittain', fontsize=12, fontweight='bold')
            ax1.set_ylabel('Onnistumisprosentti (%)')
            ax1.set_xticks(range(len(categories)))
            ax1.set_xticklabels([cat[:8] + '..' if len(cat) > 8 else cat for cat in categories], rotation=45, ha='right')
            ax1.set_ylim(0, 100)
            for bar, rate in zip(bars, success_rates):
                height = bar.get_height()
                ax1.text(bar.get_x() + bar.get_width()/2., height + 1, f'{rate:.1f}%', ha='center', va='bottom', fontsize=9)
            
            ax2 = fig1.add_subplot(122)
            question_counts = [cat.get('question_count', 0) for cat in analytics['categories']]
            if sum(question_counts) > 0:
                ax2.pie(question_counts, labels=categories, autopct='%1.1f%%', startangle=90, colors=colors[:len(categories)])
                ax2.set_title('Kysymysjakauma kategorioittain', fontsize=12, fontweight='bold')
            fig1.tight_layout()
            
            chart_frame1 = tk.Frame(scrollable_frame, bg=COLORS['white'], relief='solid', bd=1)
            chart_frame1.pack(fill='x', padx=20, pady=10)
            chart_canvas1 = FigureCanvasTkAgg(fig1, chart_frame1)
            chart_canvas1.draw()
            chart_canvas1.get_tk_widget().pack(fill='both', expand=True, padx=10, pady=10)
        
        if analytics['weekly_progress']:
            fig2 = Figure(figsize=(12, 4), dpi=100)
            fig2.patch.set_facecolor(COLORS['light'])
            ax3 = fig2.add_subplot(111)
            dates = [day['date'] for day in analytics['weekly_progress']]
            success_rates = [(day['corrects'] / day['questions_answered']) * 100 if day['questions_answered'] > 0 else 0 for day in analytics['weekly_progress']]
            ax3.plot(dates, success_rates, marker='o', linewidth=2, markersize=6, color=COLORS['primary'])
            ax3.set_title('Päivittäinen onnistumisprosentti', fontsize=12, fontweight='bold')
            ax3.set_ylabel('Onnistumisprosentti (%)')
            ax3.set_xlabel('Päivämäärä')
            ax3.grid(True, alpha=0.3)
            ax3.set_ylim(0, 100)
            plt.setp(ax3.get_xticklabels(), rotation=45, ha='right')
            fig2.tight_layout()
            
            chart_frame2 = tk.Frame(scrollable_frame, bg=COLORS['white'], relief='solid', bd=1)
            chart_frame2.pack(fill='x', padx=20, pady=10)
            chart_canvas2 = FigureCanvasTkAgg(fig2, chart_frame2)
            chart_canvas2.draw()
            chart_canvas2.get_tk_widget().pack(fill='both', expand=True, padx=10, pady=10)
        
        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
    
    def create_recommendations_tab(self, parent):
        canvas = tk.Canvas(parent, bg=COLORS['light'])
        scrollbar = ttk.Scrollbar(parent, orient="vertical", command=canvas.yview)
        scrollable_frame = tk.Frame(canvas, bg=COLORS['light'])
        scrollable_frame.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)
        
        recommendations = self.app.stats_manager.get_recommendations()
        title_label = tk.Label(scrollable_frame, text="💡 Henkilökohtaiset suositukset", font=('Segoe UI', 18, 'bold'), bg=COLORS['light'], fg=COLORS['text_primary'])
        title_label.pack(pady=20)
        
        if recommendations:
            for i, rec in enumerate(recommendations):
                rec_card = tk.Frame(scrollable_frame, bg=COLORS['white'], relief='solid', bd=1)
                rec_card.pack(fill='x', padx=20, pady=10)
                header_frame = tk.Frame(rec_card, bg=COLORS['accent'])
                header_frame.pack(fill='x')
                header_label = tk.Label(header_frame, text=f"Suositus {i+1}", font=('Segoe UI', 11, 'bold'), bg=COLORS['accent'], fg=COLORS['white'])
                header_label.pack(pady=8)
                content_frame = tk.Frame(rec_card, bg=COLORS['white'])
                content_frame.pack(fill='both', expand=True, padx=20, pady=15)
                title_label = tk.Label(content_frame, text=rec['title'], font=('Segoe UI', 12, 'bold'), bg=COLORS['white'], fg=COLORS['text_primary'])
                title_label.pack(anchor='w', pady=(0, 5))
                desc_label = tk.Label(content_frame, text=rec['description'], font=('Segoe UI', 10), bg=COLORS['white'], fg=COLORS['text_secondary'], wraplength=600, justify='left')
                desc_label.pack(anchor='w', pady=(0, 10))
                
                if rec['action'] == 'practice_category':
                    action_btn = ModernButton(content_frame, text="Harjoittele →", command=lambda cat=rec['data']['category']: self.app.practice_category(cat), style='primary', size='small')
                elif rec['action'] == 'daily_practice':
                    action_btn = ModernButton(content_frame, text="Aloita harjoitus →", command=self.app.start_daily_challenge, style='success', size='small')
                else:
                    action_btn = ModernButton(content_frame, text="Siirry →", command=self.app.show_practice_menu, style='secondary', size='small')
                action_btn.pack(anchor='e')
        else:
            no_rec_label = tk.Label(scrollable_frame, text="Ei suosituksia tällä hetkellä.\nHarjoittele enemmän saadaksesi henkilökohtaisia suosituksia!", font=('Segoe UI', 12), bg=COLORS['light'], fg=COLORS['text_secondary'], justify='center')
            no_rec_label.pack(expand=True, pady=50)
        
        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

class EnhancedAchievementsView(tk.Frame):
    """Parannettu saavutusnäkymä"""
    
    def __init__(self, parent, app):
        super().__init__(parent, bg=COLORS['light'])
        self.app = app
        self.create_achievements_interface()
    
    def create_achievements_interface(self):
        title_frame = tk.Frame(self, bg=COLORS['light'])
        title_frame.pack(fill='x', pady=(0, 20))
        
        title_label = tk.Label(title_frame, text="🏆 Saavutukset", font=('Segoe UI', 24, 'bold'), bg=COLORS['light'], fg=COLORS['text_primary'])
        title_label.pack()
        
        unlocked_achievements = self.app.achievement_manager.get_unlocked_achievements()
        total_achievements = len(self.app.achievement_manager.ENHANCED_ACHIEVEMENTS)
        unlocked_count = len(unlocked_achievements)
        
        stats_label = tk.Label(title_frame, text=f"Avattu {unlocked_count}/{total_achievements} saavutusta", font=('Segoe UI', 12), bg=COLORS['light'], fg=COLORS['text_secondary'])
        stats_label.pack()
        
        progress_frame = tk.Frame(title_frame, bg=COLORS['light'])
        progress_frame.pack(pady=10)
        progress_bar = AnimatedProgressBar(progress_frame, width=300, height=20)
        progress_bar.pack()
        progress_bar.set_progress((unlocked_count / total_achievements) * 100 if total_achievements > 0 else 0)
        
        canvas = tk.Canvas(self, bg=COLORS['light'])
        scrollbar = ttk.Scrollbar(self, orient="vertical", command=canvas.yview)
        scrollable_frame = tk.Frame(canvas, bg=COLORS['light'])
        
        scrollable_frame.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )
        
        canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)
        
        achievements_grid = tk.Frame(scrollable_frame, bg=COLORS['light'])
        achievements_grid.pack(fill='both', expand=True, padx=20, pady=20)
        
        unlocked_ids = {ach.id for ach in unlocked_achievements}
        
        row, col = 0, 0
        for ach_id, achievement in self.app.achievement_manager.ENHANCED_ACHIEVEMENTS.items():
            is_unlocked = ach_id in unlocked_ids
            card = self.create_achievement_card(achievements_grid, achievement, is_unlocked)
            card.grid(row=row, column=col, padx=10, pady=10, sticky='nsew')
            col += 1
            if col >= 3:
                col = 0
                row += 1
        
        for i in range(3):
            achievements_grid.grid_columnconfigure(i, weight=1)
        
        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
    
    def create_achievement_card(self, parent, achievement, is_unlocked):
        bg_color = COLORS['gold'] if is_unlocked else COLORS['white']
        text_color = COLORS['white'] if is_unlocked else COLORS['text_primary']
        icon_color = COLORS['white'] if is_unlocked else COLORS['gold']
        
        card = tk.Frame(parent, bg=bg_color, relief='solid', bd=2 if is_unlocked else 1)
        content = tk.Frame(card, bg=bg_color)
        content.pack(fill='both', expand=True, padx=20, pady=20)
        
        icon_label = tk.Label(content, text=achievement.icon, font=('Segoe UI', 32), bg=bg_color, fg=icon_color)
        icon_label.pack(pady=(0, 10))
        name_label = tk.Label(content, text=achievement.name, font=('Segoe UI', 12, 'bold'), bg=bg_color, fg=text_color, wraplength=180, justify='center')
        name_label.pack(pady=(0, 5))
        desc_label = tk.Label(content, text=achievement.description, font=('Segoe UI', 9), bg=bg_color, fg=text_color, wraplength=180, justify='center')
        desc_label.pack(pady=(0, 10))
        
        status_text = "🔒 Lukittu"
        if is_unlocked:
            unlocked_achievement_data = next((ach for ach in self.app.achievement_manager.get_unlocked_achievements() if ach.id == achievement.id), None)
            status_text = "✅ Avattu"
            if unlocked_achievement_data and unlocked_achievement_data.unlocked_at:
                try:
                    date_obj = datetime.datetime.fromisoformat(unlocked_achievement_data.unlocked_at.replace('Z', '+00:00'))
                    status_text += f"\n{date_obj.strftime('%d.%m.%Y')}"
                except: pass
        
        status_label = tk.Label(content, text=status_text, font=('Segoe UI', 8), bg=bg_color, fg=text_color, justify='center')
        status_label.pack()
        
        return card

class SettingsView(tk.Frame):
    """Asetukset-näkymä"""
    
    def __init__(self, parent, app):
        super().__init__(parent, bg=COLORS['light'])
        self.app = app
        self.create_settings_interface()

    def _on_mousewheel(self, event, canvas):
        if event.delta:
            canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")
        elif event.num == 4:
            canvas.yview_scroll(-1, "units")
        elif event.num == 5:
            canvas.yview_scroll(1, "units")

    def _bind_mousewheel(self, widget, canvas):
        widget.bind("<MouseWheel>", lambda e, c=canvas: self._on_mousewheel(e, c))
        widget.bind("<Button-4>", lambda e, c=canvas: self._on_mousewheel(e, c))
        widget.bind("<Button-5>", lambda e, c=canvas: self._on_mousewheel(e, c))
        for child in widget.winfo_children():
            self._bind_mousewheel(child, canvas)
    
    def create_settings_interface(self):
        title_label = tk.Label(self, text="⚙️ Asetukset", font=('Segoe UI', 24, 'bold'), bg=COLORS['light'], fg=COLORS['text_primary'])
        title_label.pack(pady=(20, 10))
        
        top_actions_frame = tk.Frame(self, bg=COLORS['light'])
        top_actions_frame.pack(fill='x', padx=20, pady=(0, 20))

        save_btn = ModernButton(top_actions_frame, text="💾 Tallenna asetukset", command=self.save_settings, style='success', size='medium')
        save_btn.pack(side='left', padx=(0,10))
        reset_btn = ModernButton(top_actions_frame, text="🔄 Palauta oletukset", command=self.reset_settings, style='warning', size='medium')
        reset_btn.pack(side='left')
        
        scroll_container = tk.Frame(self, bg=COLORS['light'])
        scroll_container.pack(fill='both', expand=True)

        canvas = tk.Canvas(scroll_container, bg=COLORS['light'], highlightthickness=0)
        scrollbar = ttk.Scrollbar(scroll_container, orient="vertical", command=canvas.yview)
        scrollable_frame = tk.Frame(canvas, bg=COLORS['light'])
        scrollable_frame.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)

        general_frame = tk.LabelFrame(scrollable_frame, text="Yleiset asetukset", font=('Segoe UI', 12, 'bold'), bg=COLORS['light'], fg=COLORS['text_primary'])
        general_frame.pack(fill='x', padx=20, pady=10)

        goal_frame = tk.Frame(general_frame, bg=COLORS['light'])
        goal_frame.pack(fill='x', padx=10, pady=10)
        goal_label = tk.Label(goal_frame, text="Päivittäinen kysymystavoite:", font=('Segoe UI', 11), bg=COLORS['light'], fg=COLORS['text_primary'])
        goal_label.pack(side='left')
        self.goal_var = tk.IntVar(value=config.daily_goal)
        goal_spinbox = tk.Spinbox(goal_frame, from_=5, to=100, width=10, textvariable=self.goal_var, font=('Segoe UI', 11))
        goal_spinbox.pack(side='right')

        theme_frame = tk.Frame(general_frame, bg=COLORS['light'])
        theme_frame.pack(fill='x', padx=10, pady=10)
        theme_label = tk.Label(theme_frame, text="Teema:", font=('Segoe UI', 11), bg=COLORS['light'], fg=COLORS['text_primary'])
        theme_label.pack(side='left')
        self.theme_var = tk.StringVar(value=config.theme)
        theme_combo = ttk.Combobox(theme_frame, textvariable=self.theme_var, values=list(THEMES.keys()), state='readonly')
        theme_combo.pack(side='right')

        notifications_frame = tk.LabelFrame(scrollable_frame, text="Notifikaatiot", font=('Segoe UI', 12, 'bold'), bg=COLORS['light'], fg=COLORS['text_primary'])
        notifications_frame.pack(fill='x', padx=20, pady=10)
        self.notification_vars = {}
        for key, value in config.notifications.items():
            var = tk.BooleanVar(value=value)
            self.notification_vars[key] = var
            cb = tk.Checkbutton(notifications_frame, text=self.get_notification_text(key), variable=var, font=('Segoe UI', 11), bg=COLORS['light'], fg=COLORS['text_primary'])
            cb.pack(anchor='w', padx=10, pady=5)

        advanced_frame = tk.LabelFrame(scrollable_frame, text="Kehittyneet asetukset", font=('Segoe UI', 12, 'bold'), bg=COLORS['light'], fg=COLORS['text_primary'])
        advanced_frame.pack(fill='x', padx=20, pady=10)

        sr_frame = tk.Frame(advanced_frame, bg=COLORS['light'])
        sr_frame.pack(fill='x', padx=10, pady=10)
        self.sr_var = tk.BooleanVar(value=config.spaced_repetition_enabled)
        sr_cb = tk.Checkbutton(sr_frame, text="Älykäs kertaus käytössä", variable=self.sr_var, font=('Segoe UI', 11), bg=COLORS['light'], fg=COLORS['text_primary'])
        sr_cb.pack(anchor='w')

        animations_frame = tk.Frame(advanced_frame, bg=COLORS['light'])
        animations_frame.pack(fill='x', padx=10, pady=10)
        self.animations_var = tk.BooleanVar(value=config.animations)
        animations_cb = tk.Checkbutton(animations_frame, text="Animaatiot käytössä", variable=self.animations_var, font=('Segoe UI', 11), bg=COLORS['light'], fg=COLORS['text_primary'])
        animations_cb.pack(anchor='w')
        
        data_frame = tk.LabelFrame(scrollable_frame, text="📊 Tiedonhallinta", font=('Segoe UI', 12, 'bold'), bg=COLORS['light'], fg=COLORS['text_primary'])
        data_frame.pack(fill='x', padx=20, pady=20)
        import_frame = tk.Frame(data_frame, bg=COLORS['light'])
        import_frame.pack(fill='x', padx=15, pady=15)
        import_btn = ModernButton(import_frame, text="📥 Tuo kysymyksiä", command=self.app.import_questions_from_json)
        import_btn.pack(side='left', padx=5)
        export_btn = ModernButton(import_frame, text="📤 Vie käyttäjätiedot", command=self.export_data, style='secondary')
        export_btn.pack(side='left', padx=5)

        danger_frame = tk.LabelFrame(scrollable_frame, text="⚠️ Vaarallinen alue", font=('Segoe UI', 12, 'bold'), bg=COLORS['light'], fg=COLORS['danger'])
        danger_frame.pack(fill='x', padx=20, pady=20)
        reset_db_btn = ModernButton(danger_frame, text="🗑️ Nollaa kaikki tiedot", command=self.reset_database, style='danger')
        reset_db_btn.pack(pady=15)
        
        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        self._bind_mousewheel(scrollable_frame, canvas)
    
    def get_notification_text(self, key):
        texts = {'achievements': 'Saavutusnotifikaatiot', 'daily_reminders': 'Päivittäiset muistutukset', 'study_suggestions': 'Opiskelusuositukset', 'streak_warnings': 'Sarjan katkeamisvaroitukset'}
        return texts.get(key, key)
    
    def save_settings(self):
        config.daily_goal = self.goal_var.get()
        config.theme = self.theme_var.get()
        config.spaced_repetition_enabled = self.sr_var.get()
        config.animations = self.animations_var.get()
        for key, var in self.notification_vars.items():
            config.notifications[key] = var.get()
        self.app.db_manager.save_user_stat('config', asdict(config))
        self.app.show_toast("Asetukset tallennettu!", 'success')
    
    def reset_settings(self):
        if messagebox.askyesno("Vahvista", "Haluatko varmasti palauttaa oletusasetukset?"):
            global config
            config = AppConfig()
            self.goal_var.set(config.daily_goal)
            self.theme_var.set(config.theme)
            self.sr_var.set(config.spaced_repetition_enabled)
            self.animations_var.set(config.animations)
            for key, var in self.notification_vars.items():
                var.set(config.notifications[key])
            self.app.show_toast("Oletusasetukset palautettu!", 'info')
    
    def export_data(self):
        filename = filedialog.asksaveasfilename(defaultextension=".json", filetypes=[("JSON files", "*.json"), ("All files", "*.*")], title="Vie käyttäjätiedot")
        if filename:
            try:
                export_data = {
                    'config': asdict(config),
                    'stats': self.app.stats_manager.get_learning_analytics(),
                    'achievements': [asdict(ach) for ach in self.app.achievement_manager.get_unlocked_achievements()],
                    'export_date': datetime.datetime.now().isoformat()
                }
                with open(filename, 'w', encoding='utf-8') as f:
                    json.dump(export_data, f, indent=2, ensure_ascii=False)
                self.app.show_toast(f"Tiedot viety tiedostoon:\n{filename}", 'success')
            except Exception as e:
                self.app.show_toast(f"Viennissä tapahtui virhe: {str(e)}", 'error')
                
    def reset_database(self):
        if messagebox.askyesno("⚠️ VAROITUS", "Tämä poistaa KAIKKI tiedot pysyvästi...\nHaluatko varmasti jatkaa?") and \
           messagebox.askyesno("Viimeinen varoitus", "Oletko TÄYSIN VARMA?\nTämä ei ole peruutettavissa!"):
            try:
                success, error = self.app.db_manager.clear_all_tables()
                if success:
                    self.app.show_toast("Tietokanta nollattu. Sovellus käynnistetään uudelleen.", 'info')
                    self.app.after(1500, self.app.restart_app)
                else:
                    raise error
            except Exception as e:
                self.app.show_toast(f"Virhe tietokannan nollaamisessa: {str(e)}", 'error')  

class EnhancedSimulationView(tk.Frame):
    def __init__(self, parent, app, questions):
        super().__init__(parent, bg=COLORS['light'])
        self.app = app
        self.questions = questions
        self.current_question_index = 0
        self.answers = [-1] * len(questions)
        self.start_time = datetime.datetime.now()
        self.time_limit = 3600
        
        self.create_simulation_interface()
        self.load_question()
        self.start_timer()
    
    def create_simulation_interface(self):
        header_frame = tk.Frame(self, bg=COLORS['danger'], height=80)
        header_frame.pack(fill='x')
        header_frame.pack_propagate(False)
        header_content = tk.Frame(header_frame, bg=COLORS['danger'])
        header_content.pack(expand=True, fill='both', padx=30)
        title_label = tk.Label(header_content, text="🎓 Koesimulaatio", font=('Segoe UI', 16, 'bold'), bg=COLORS['danger'], fg=COLORS['white'])
        title_label.pack(side='left', pady=25)
        right_info = tk.Frame(header_content, bg=COLORS['danger'])
        right_info.pack(side='right', pady=25)
        self.timer_label = tk.Label(right_info, text="", font=('Segoe UI', 14, 'bold'), bg=COLORS['danger'], fg=COLORS['white'])
        self.timer_label.pack()
        self.progress_label = tk.Label(right_info, text="", font=('Segoe UI', 11), bg=COLORS['danger'], fg=COLORS['white'])
        self.progress_label.pack()
        
        self.progress_bar = AnimatedProgressBar(self, width=self.winfo_reqwidth(), height=8)
        self.progress_bar.pack(fill='x', padx=20, pady=(10, 0))
        
        main_frame = tk.Frame(self, bg=COLORS['light'])
        main_frame.pack(fill='both', expand=True, padx=30, pady=20)
        
        nav_frame = tk.Frame(main_frame, bg=COLORS['white'], width=200)
        nav_frame.pack(side='left', fill='y', padx=(0, 20))
        nav_frame.pack_propagate(False)
        nav_title = tk.Label(nav_frame, text="Kysymykset", font=('Segoe UI', 12, 'bold'), bg=COLORS['white'], fg=COLORS['text_primary'])
        nav_title.pack(pady=10)
        
        self.nav_buttons_frame = tk.Frame(nav_frame, bg=COLORS['white'])
        self.nav_buttons_frame.pack(fill='both', expand=True, padx=10, pady=10)
        self.create_navigation_buttons()
        
        content_frame = tk.Frame(main_frame, bg=COLORS['light'])
        content_frame.pack(side='right', fill='both', expand=True)
        
        self.question_frame = tk.Frame(content_frame, bg=COLORS['white'])
        self.question_frame.pack(fill='x', pady=(0, 20))
        question_inner = tk.Frame(self.question_frame, bg=COLORS['white'])
        question_inner.pack(fill='both', expand=True, padx=25, pady=20)
        self.question_label = tk.Label(question_inner, text="", font=('Segoe UI', 14), bg=COLORS['white'], fg=COLORS['text_primary'], wraplength=600, justify="left")
        self.question_label.pack(fill='x')
        
        self.options_frame = tk.Frame(content_frame, bg=COLORS['light'])
        self.options_frame.pack(fill='x', pady=(0, 20))
        self.selected_option = tk.IntVar(value=-1)
        
        btn_frame = tk.Frame(content_frame, bg=COLORS['light'])
        btn_frame.pack(fill='x')
        self.prev_btn = ModernButton(btn_frame, text="← Edellinen", command=self.prev_question, style='secondary')
        self.prev_btn.pack(side='left')
        self.next_btn = ModernButton(btn_frame, text="Seuraava →", command=self.next_question, style='primary')
        self.next_btn.pack(side='left', padx=(10, 0))
        self.finish_btn = ModernButton(btn_frame, text="🏁 Lopeta koe", command=self.finish_simulation, style='warning')
        self.finish_btn.pack(side='right')

    def create_navigation_buttons(self):
        for i in range(len(self.questions)):
            row, col = i // 5, i % 5
            btn = tk.Button(self.nav_buttons_frame, text=str(i+1), font=('Segoe UI', 9), width=4, height=2,
                            bg=COLORS['light'], fg=COLORS['text_primary'], relief='flat', bd=1,
                            cursor='hand2', command=lambda idx=i: self.goto_question(idx))
            btn.grid(row=row, column=col, padx=2, pady=2)
            setattr(self, f'nav_btn_{i}', btn)

    def update_navigation_button(self, index):
        btn = getattr(self, f'nav_btn_{index}')
        if self.answers[index] != -1:
            btn.configure(bg=COLORS['success'])
        elif index == self.current_question_index:
            btn.configure(bg=COLORS['primary'])
        else:
            btn.configure(bg=COLORS['light'])

    def update_all_navigation_buttons(self):
        for i in range(len(self.questions)):
            self.update_navigation_button(i)

    def goto_question(self, index):
        self.save_current_answer()
        self.current_question_index = index
        self.load_question()

    def load_question(self):
        question = self.questions[self.current_question_index]
        progress = ((self.current_question_index + 1) / len(self.questions)) * 100
        self.progress_label.config(text=f"Kysymys {self.current_question_index + 1}/{len(self.questions)}")
        self.progress_bar.set_progress(progress)
        self.question_label.config(text=question.question)
        for widget in self.options_frame.winfo_children():
            widget.destroy()
        saved_answer = self.answers[self.current_question_index]
        self.selected_option.set(saved_answer)
        for i, option in enumerate(question.options):
            option_frame = tk.Frame(self.options_frame, bg=COLORS['white'], relief='flat', bd=1)
            option_frame.pack(fill='x', pady=5)
            rb = tk.Radiobutton(option_frame, text=f"{chr(65+i)}. {option}",
                                variable=self.selected_option, value=i,
                                font=('Segoe UI', 12), bg=COLORS['white'], fg=COLORS['text_primary'],
                                selectcolor=COLORS['primary'], relief='flat', bd=0, padx=20, pady=15,
                                cursor='hand2', command=self.save_current_answer)
            rb.pack(fill='x', anchor='w')
        self.update_all_navigation_buttons()
        self.prev_btn.configure(state='normal' if self.current_question_index > 0 else 'disabled')
        self.next_btn.configure(text="🏁 Viimeinen" if self.current_question_index == len(self.questions) - 1 else "Seuraava →")

    def save_current_answer(self):
        self.answers[self.current_question_index] = self.selected_option.get()
        self.update_navigation_button(self.current_question_index)

    def prev_question(self):
        if self.current_question_index > 0:
            self.save_current_answer()
            self.current_question_index -= 1
            self.load_question()

    def next_question(self):
        self.save_current_answer()
        if self.current_question_index < len(self.questions) - 1:
            self.current_question_index += 1
            self.load_question()
        else:
            self.finish_simulation()

    def start_timer(self):
        def update_timer():
            if self.winfo_exists():
                elapsed = (datetime.datetime.now() - self.start_time).total_seconds()
                remaining = max(0, self.time_limit - elapsed)
                minutes, seconds = int(remaining // 60), int(remaining % 60)
                self.timer_label.config(text=f"⏱️ {minutes:02d}:{seconds:02d}")
                if remaining <= 300: self.timer_label.configure(fg='#ffff00')
                if remaining <= 60: self.timer_label.configure(fg='#ff4444')
                if remaining <= 0:
                    self.finish_simulation()
                    return
                self.after(1000, update_timer)
        update_timer()

    def finish_simulation(self):
        self.save_current_answer()
        correct_count = sum(1 for i, answer in enumerate(self.answers) if answer == self.questions[i].correct)
        self.app.stats_manager.end_session(len(self.questions), correct_count)
        self.show_simulation_results(correct_count)

    def show_simulation_results(self, correct_count):
        self.pack_forget()
        total = len(self.questions)
        percentage = (correct_count / total) * 100 if total > 0 else 0
        passed = percentage >= 60
        results_frame = tk.Frame(self.master, bg=COLORS['light'])
        results_frame.pack(fill='both', expand=True, padx=30, pady=30)
        
        header_color = COLORS['success'] if passed else COLORS['danger']
        header_text = "🎉 HYVÄKSYTTY!" if passed else "❌ HYLÄTTY"
        header_frame = tk.Frame(results_frame, bg=header_color, height=120)
        header_frame.pack(fill='x')
        header_frame.pack_propagate(False)
        result_label = tk.Label(header_frame, text=header_text, font=('Segoe UI', 28, 'bold'), bg=header_color, fg=COLORS['white'])
        result_label.pack(expand=True)
        
        content_frame = tk.Frame(results_frame, bg=COLORS['white'])
        content_frame.pack(fill='both', expand=True, pady=20)
        center_frame = tk.Frame(content_frame, bg=COLORS['white'])
        center_frame.pack(expand=True, padx=100, pady=50)
        
        score_label = tk.Label(center_frame, text=f"{correct_count} / {total}", font=('Segoe UI', 48, 'bold'), bg=COLORS['white'], fg=COLORS['primary'])
        score_label.pack(pady=(0, 10))
        percentage_label = tk.Label(center_frame, text=f"{percentage:.1f}%", font=('Segoe UI', 24), bg=COLORS['white'], fg=COLORS['text_primary'])
        percentage_label.pack(pady=(0, 20))
        
        elapsed = (datetime.datetime.now() - self.start_time).total_seconds()
        time_label = tk.Label(center_frame, text=f"Aika: {int(elapsed//60)}:{int(elapsed%60):02d}", font=('Segoe UI', 14), bg=COLORS['white'], fg=COLORS['text_secondary'])
        time_label.pack(pady=(0, 30))
        
        actions_frame = tk.Frame(center_frame, bg=COLORS['white'])
        actions_frame.pack()
        review_btn = ModernButton(actions_frame, text="📖 Tarkasta vastaukset", command=lambda: self.show_review(correct_count), style='secondary')
        review_btn.pack(side='left', padx=10)
        home_btn = ModernButton(actions_frame, text="🏠 Päävalikkoon", command=self.app.show_main_menu, style='primary')
        home_btn.pack(side='left', padx=10)
        
        self.app.check_and_show_achievements(context={'simulation_perfect': correct_count == total})

    def show_review(self, correct_count):
        review_window = tk.Toplevel(self.app)
        review_window.title("Vastausten tarkastelu")
        review_window.geometry("800x600")
        review_window.configure(bg=COLORS['light'])
        
        canvas = tk.Canvas(review_window, bg=COLORS['light'])
        scrollbar = ttk.Scrollbar(review_window, orient="vertical", command=canvas.yview)
        scrollable_frame = tk.Frame(canvas, bg=COLORS['light'])
        scrollable_frame.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)
        
        for i, question in enumerate(self.questions):
            user_answer = self.answers[i]
            is_correct = user_answer == question.correct
            
            card_frame = tk.Frame(scrollable_frame, bg=COLORS['white'], relief='solid', bd=1)
            card_frame.pack(fill='x', padx=20, pady=10)
            
            header_color = COLORS['success'] if is_correct else COLORS['danger']
            header_text = f"Kysymys {i+1} - {'✅ Oikein' if is_correct else '❌ Väärin'}"
            header_frame = tk.Frame(card_frame, bg=header_color)
            header_frame.pack(fill='x')
            header_label = tk.Label(header_frame, text=header_text, font=('Segoe UI', 12, 'bold'), bg=header_color, fg=COLORS['white'])
            header_label.pack(pady=8)
            
            q_frame = tk.Frame(card_frame, bg=COLORS['white'])
            q_frame.pack(fill='x', padx=15, pady=10)
            question_text = tk.Label(q_frame, text=question.question, font=('Segoe UI', 11), bg=COLORS['white'], fg=COLORS['text_primary'], wraplength=700, justify='left')
            question_text.pack(anchor='w')
            
            for j, option in enumerate(question.options):
                if j == question.correct:
                    color, prefix = COLORS['success_light'], "✅"
                elif j == user_answer and not is_correct:
                    color, prefix = COLORS['danger'], "❌"
                else:
                    color, prefix = COLORS['white'], "  "
                
                option_label = tk.Label(q_frame, text=f"{prefix} {chr(65+j)}. {option}", font=('Segoe UI', 10), bg=color, fg=COLORS['text_primary'], anchor='w')
                option_label.pack(fill='x', padx=20, pady=2)
        
        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")     

class EnhancedStatsView(tk.Frame):
    """Parannettu tilastonäkymä"""
    def __init__(self, parent, app):
        super().__init__(parent, bg=COLORS['light'])
        self.app = app
        self.create_stats_interface()
    
    def create_stats_interface(self):
        title_frame = tk.Frame(self, bg=COLORS['light'])
        title_frame.pack(fill='x', pady=(0, 20))
        title_label = tk.Label(title_frame, text="📊 Oppimisanalytiikka", font=('Segoe UI', 24, 'bold'), bg=COLORS['light'], fg=COLORS['text_primary'])
        title_label.pack()
        
        notebook = ttk.Notebook(self)
        notebook.pack(expand=True, fill='both', padx=20, pady=10)
        
        overview_frame = tk.Frame(notebook, bg=COLORS['light'])
        notebook.add(overview_frame, text="📈 Yleiskatsaus")
        self.create_overview_tab(overview_frame)
        
        detailed_frame = tk.Frame(notebook, bg=COLORS['light'])
        notebook.add(detailed_frame, text="📋 Yksityiskohdat")
        self.create_detailed_tab(detailed_frame)
        
        if MATPLOTLIB_AVAILABLE:
            charts_frame = tk.Frame(notebook, bg=COLORS['light'])
            notebook.add(charts_frame, text="📊 Graafit")
            self.create_charts_tab(charts_frame)
        
        recommendations_frame = tk.Frame(notebook, bg=COLORS['light'])
        notebook.add(recommendations_frame, text="💡 Suositukset")
        self.create_recommendations_tab(recommendations_frame)
    
    def create_overview_tab(self, parent):
        canvas = tk.Canvas(parent, bg=COLORS['light'])
        scrollbar = ttk.Scrollbar(parent, orient="vertical", command=canvas.yview)
        scrollable_frame = tk.Frame(canvas, bg=COLORS['light'])
        scrollable_frame.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)
        
        analytics = self.app.stats_manager.get_learning_analytics()
        
        general_frame = tk.Frame(scrollable_frame, bg=COLORS['light'])
        general_frame.pack(fill='x', padx=20, pady=10)
        
        general_stats = analytics['general']
        stats_cards = [
            ("Kysymyksiä pankissa", str(general_stats.get('total_questions_in_db', 0)), "📚", COLORS['primary']),
            ("Vastattuja kysymyksiä", str(general_stats.get('answered_questions', 0)), "📝", COLORS['accent']),
            ("Onnistumisprosentti", f"{general_stats.get('avg_success_rate', 0)*100:.1f}%", "🎯", COLORS['success']),
            ("Yrityksiä yhteensä", str(general_stats.get('total_attempts', 0)), "🔢", COLORS['secondary'])
        ]
        
        for i, (title, value, icon, color) in enumerate(stats_cards):
            card = self.create_stat_card(general_frame, title, value, icon, color)
            card.grid(row=0, column=i, padx=10, pady=10, sticky='nsew')
            general_frame.grid_columnconfigure(i, weight=1)
        
        if analytics['categories']:
            cat_frame = tk.LabelFrame(scrollable_frame, text="Kategoriakohtaiset tulokset", font=('Segoe UI', 12, 'bold'), bg=COLORS['light'], fg=COLORS['text_primary'])
            cat_frame.pack(fill='x', padx=20, pady=20)
            for category in analytics['categories']:
                cat_item = tk.Frame(cat_frame, bg=COLORS['white'], relief='flat', bd=1)
                cat_item.pack(fill='x', padx=10, pady=5)
                name_label = tk.Label(cat_item, text=category['category'].title(), font=('Segoe UI', 11, 'bold'), bg=COLORS['white'], fg=COLORS['text_primary'])
                name_label.pack(side='left', padx=15, pady=10)
                progress_frame = tk.Frame(cat_item, bg=COLORS['white'])
                progress_frame.pack(side='right', padx=15, pady=10)
                success_rate = category.get('success_rate', 0) * 100
                progress_bar = AnimatedProgressBar(progress_frame, width=200, height=15)
                progress_bar.pack()
                progress_bar.set_progress(success_rate)
                percent_label = tk.Label(progress_frame, text=f"{success_rate:.1f}%", font=('Segoe UI', 10), bg=COLORS['white'], fg=COLORS['text_secondary'])
                percent_label.pack()
        
        if analytics['weekly_progress']:
            week_frame = tk.LabelFrame(scrollable_frame, text="Viikon edistyminen", font=('Segoe UI', 12, 'bold'), bg=COLORS['light'], fg=COLORS['text_primary'])
            week_frame.pack(fill='x', padx=20, pady=20)
            for day_data in analytics['weekly_progress'][-7:]:
                day_frame = tk.Frame(week_frame, bg=COLORS['white'])
                day_frame.pack(fill='x', padx=10, pady=2)
                date_label = tk.Label(day_frame, text=day_data['date'], font=('Segoe UI', 10), bg=COLORS['white'], fg=COLORS['text_secondary'])
                date_label.pack(side='left', padx=10, pady=5)
                stats_text = f"{day_data['corrects']}/{day_data['questions_answered']} oikein"
                stats_label = tk.Label(day_frame, text=stats_text, font=('Segoe UI', 10, 'bold'), bg=COLORS['white'], fg=COLORS['text_primary'])
                stats_label.pack(side='right', padx=10, pady=5)
        
        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
    
    def create_stat_card(self, parent, title, value, icon, color):
        card = tk.Frame(parent, bg=COLORS['white'], relief='flat', bd=1)
        accent = tk.Frame(card, bg=color, height=4)
        accent.pack(fill='x', side='top')
        content = tk.Frame(card, bg=COLORS['white'])
        content.pack(fill='both', expand=True, padx=20, pady=20)
        icon_label = tk.Label(content, text=icon, font=('Segoe UI', 24), bg=COLORS['white'], fg=color)
        icon_label.pack(pady=(0, 10))
        value_label = tk.Label(content, text=value, font=('Segoe UI', 20, 'bold'), bg=COLORS['white'], fg=COLORS['text_primary'])
        value_label.pack()
        title_label = tk.Label(content, text=title, font=('Segoe UI', 10), bg=COLORS['white'], fg=COLORS['text_secondary'])
        title_label.pack(pady=(5, 0))
        return card
    
    def create_detailed_tab(self, parent):
        canvas = tk.Canvas(parent, bg=COLORS['light'])
        scrollbar = ttk.Scrollbar(parent, orient="vertical", command=canvas.yview)
        scrollable_frame = tk.Frame(canvas, bg=COLORS['light'])
        scrollable_frame.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)
        
        analytics = self.app.stats_manager.get_learning_analytics()
        
        if analytics['difficulties']:
            diff_frame = tk.LabelFrame(scrollable_frame, text="Vaikeustasot", font=('Segoe UI', 12, 'bold'), bg=COLORS['light'], fg=COLORS['text_primary'])
            diff_frame.pack(fill='x', padx=20, pady=20)
            for difficulty in analytics['difficulties']:
                diff_item = tk.Frame(diff_frame, bg=COLORS['white'])
                diff_item.pack(fill='x', padx=10, pady=5)
                name_label = tk.Label(diff_item, text=difficulty['difficulty'].title(), font=('Segoe UI', 11, 'bold'), bg=COLORS['white'], fg=COLORS['text_primary'])
                name_label.pack(side='left', padx=15, pady=10)
                success_rate = difficulty.get('success_rate', 0) * 100
                rate_label = tk.Label(diff_item, text=f"{success_rate:.1f}%", font=('Segoe UI', 11), bg=COLORS['white'], fg=COLORS['text_secondary'])
                rate_label.pack(side='right', padx=15, pady=10)
        
        with sqlite3.connect(self.app.db_manager.db_path) as conn:
            conn.row_factory = sqlite3.Row
            sessions = conn.execute("SELECT * FROM study_sessions WHERE end_time IS NOT NULL ORDER BY start_time DESC LIMIT 10").fetchall()
        
        if sessions:
            session_frame = tk.LabelFrame(scrollable_frame, text="Viimeisimmät opiskelusessiot", font=('Segoe UI', 12, 'bold'), bg=COLORS['light'], fg=COLORS['text_primary'])
            session_frame.pack(fill='x', padx=20, pady=20)
            for session in sessions:
                session_item = tk.Frame(session_frame, bg=COLORS['white'])
                session_item.pack(fill='x', padx=10, pady=5)
                date_str = session['start_time'][:16]
                type_text = session['session_type'].title()
                info_label = tk.Label(session_item, text=f"{type_text} - {date_str}", font=('Segoe UI', 10, 'bold'), bg=COLORS['white'], fg=COLORS['text_primary'])
                info_label.pack(side='left', padx=15, pady=8)
                if session['questions_answered'] > 0:
                    success_rate = (session['questions_correct'] / session['questions_answered']) * 100
                    result_text = f"{session['questions_correct']}/{session['questions_answered']} ({success_rate:.1f}%)"
                else:
                    result_text = "Ei kysymyksiä"
                result_label = tk.Label(session_item, text=result_text, font=('Segoe UI', 10), bg=COLORS['white'], fg=COLORS['text_secondary'])
                result_label.pack(side='right', padx=15, pady=8)
        
        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
    
    def create_charts_tab(self, parent):
        if not MATPLOTLIB_AVAILABLE:
            error_label = tk.Label(parent, text="Matplotlib ei ole saatavilla.\nAsenna: pip install matplotlib", font=('Segoe UI', 12), bg=COLORS['light'], fg=COLORS['danger'])
            error_label.pack(expand=True)
            return
        
        canvas = tk.Canvas(parent, bg=COLORS['light'])
        scrollbar = ttk.Scrollbar(parent, orient="vertical", command=canvas.yview)
        scrollable_frame = tk.Frame(canvas, bg=COLORS['light'])
        scrollable_frame.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)
        
        analytics = self.app.stats_manager.get_learning_analytics()
        
        if analytics['categories']:
            fig1 = Figure(figsize=(12, 5), dpi=100)
            fig1.patch.set_facecolor(COLORS['light'])
            ax1 = fig1.add_subplot(121)
            categories = [cat['category'] for cat in analytics['categories']]
            success_rates = [cat.get('success_rate', 0) * 100 for cat in analytics['categories']]
            colors = [COLORS['primary'], COLORS['secondary'], COLORS['accent'], COLORS['success'], COLORS['warning']]
            bars = ax1.bar(range(len(categories)), success_rates, color=colors[:len(categories)])
            ax1.set_title('Onnistumisprosentit kategorioittain', fontsize=12, fontweight='bold')
            ax1.set_ylabel('Onnistumisprosentti (%)')
            ax1.set_xticks(range(len(categories)))
            ax1.set_xticklabels([cat[:8] + '..' if len(cat) > 8 else cat for cat in categories], rotation=45, ha='right')
            ax1.set_ylim(0, 100)
            for bar, rate in zip(bars, success_rates):
                height = bar.get_height()
                ax1.text(bar.get_x() + bar.get_width()/2., height + 1, f'{rate:.1f}%', ha='center', va='bottom', fontsize=9)
            
            ax2 = fig1.add_subplot(122)
            question_counts = [cat.get('question_count', 0) for cat in analytics['categories']]
            if sum(question_counts) > 0:
                ax2.pie(question_counts, labels=categories, autopct='%1.1f%%', startangle=90, colors=colors[:len(categories)])
                ax2.set_title('Kysymysjakauma kategorioittain', fontsize=12, fontweight='bold')
            fig1.tight_layout()
            
            chart_frame1 = tk.Frame(scrollable_frame, bg=COLORS['white'], relief='solid', bd=1)
            chart_frame1.pack(fill='x', padx=20, pady=10)
            chart_canvas1 = FigureCanvasTkAgg(fig1, chart_frame1)
            chart_canvas1.draw()
            chart_canvas1.get_tk_widget().pack(fill='both', expand=True, padx=10, pady=10)
        
        if analytics['weekly_progress']:
            fig2 = Figure(figsize=(12, 4), dpi=100)
            fig2.patch.set_facecolor(COLORS['light'])
            ax3 = fig2.add_subplot(111)
            dates = [day['date'] for day in analytics['weekly_progress']]
            success_rates = [(day['corrects'] / day['questions_answered']) * 100 if day['questions_answered'] > 0 else 0 for day in analytics['weekly_progress']]
            ax3.plot(dates, success_rates, marker='o', linewidth=2, markersize=6, color=COLORS['primary'])
            ax3.set_title('Päivittäinen onnistumisprosentti', fontsize=12, fontweight='bold')
            ax3.set_ylabel('Onnistumisprosentti (%)')
            ax3.set_xlabel('Päivämäärä')
            ax3.grid(True, alpha=0.3)
            ax3.set_ylim(0, 100)
            plt.setp(ax3.get_xticklabels(), rotation=45, ha='right')
            fig2.tight_layout()
            
            chart_frame2 = tk.Frame(scrollable_frame, bg=COLORS['white'], relief='solid', bd=1)
            chart_frame2.pack(fill='x', padx=20, pady=10)
            chart_canvas2 = FigureCanvasTkAgg(fig2, chart_frame2)
            chart_canvas2.draw()
            chart_canvas2.get_tk_widget().pack(fill='both', expand=True, padx=10, pady=10)
        
        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
    
    def create_recommendations_tab(self, parent):
        canvas = tk.Canvas(parent, bg=COLORS['light'])
        scrollbar = ttk.Scrollbar(parent, orient="vertical", command=canvas.yview)
        scrollable_frame = tk.Frame(canvas, bg=COLORS['light'])
        scrollable_frame.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)
        
        recommendations = self.app.stats_manager.get_recommendations()
        title_label = tk.Label(scrollable_frame, text="💡 Henkilökohtaiset suositukset", font=('Segoe UI', 18, 'bold'), bg=COLORS['light'], fg=COLORS['text_primary'])
        title_label.pack(pady=20)
        
        if recommendations:
            for i, rec in enumerate(recommendations):
                rec_card = tk.Frame(scrollable_frame, bg=COLORS['white'], relief='solid', bd=1)
                rec_card.pack(fill='x', padx=20, pady=10)
                header_frame = tk.Frame(rec_card, bg=COLORS['accent'])
                header_frame.pack(fill='x')
                header_label = tk.Label(header_frame, text=f"Suositus {i+1}", font=('Segoe UI', 11, 'bold'), bg=COLORS['accent'], fg=COLORS['white'])
                header_label.pack(pady=8)
                content_frame = tk.Frame(rec_card, bg=COLORS['white'])
                content_frame.pack(fill='both', expand=True, padx=20, pady=15)
                title_label = tk.Label(content_frame, text=rec['title'], font=('Segoe UI', 12, 'bold'), bg=COLORS['white'], fg=COLORS['text_primary'])
                title_label.pack(anchor='w', pady=(0, 5))
                desc_label = tk.Label(content_frame, text=rec['description'], font=('Segoe UI', 10), bg=COLORS['white'], fg=COLORS['text_secondary'], wraplength=600, justify='left')
                desc_label.pack(anchor='w', pady=(0, 10))
                
                if rec['action'] == 'practice_category':
                    action_btn = ModernButton(content_frame, text="Harjoittele →", command=lambda cat=rec['data']['category']: self.app.practice_category(cat), style='primary', size='small')
                elif rec['action'] == 'daily_practice':
                    action_btn = ModernButton(content_frame, text="Aloita harjoitus →", command=self.app.start_daily_challenge, style='success', size='small')
                else:
                    action_btn = ModernButton(content_frame, text="Siirry →", command=self.app.show_practice_menu, style='secondary', size='small')
                action_btn.pack(anchor='e')
        else:
            no_rec_label = tk.Label(scrollable_frame, text="Ei suosituksia tällä hetkellä.\nHarjoittele enemmän saadaksesi henkilökohtaisia suosituksia!", font=('Segoe UI', 12), bg=COLORS['light'], fg=COLORS['text_secondary'], justify='center')
            no_rec_label.pack(expand=True, pady=50)
        
        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")     
        
                                                