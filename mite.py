import tkinter as tk
from tkinter import ttk, messagebox
import requests
from bs4 import BeautifulSoup
from datetime import datetime, date, timedelta
import re
import json
import os
import matplotlib.pyplot as plt
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from fake_useragent import UserAgent
import threading
import feedparser
from tkcalendar import DateEntry
import pygame
import sys

class TickActivityMonitor:
    def __init__(self, root):
        self.root = root
        self.root.title("Монитор активности клещей - Тюмень")
        self.root.geometry("1100x750")
        
        # Инициализация звука
        pygame.mixer.init()
        self.sound_enabled = True
        self.load_sounds()
        
        # Цветовая схема
        self.bg_color = "#0a0a1a"
        self.text_color = "#00ff99"
        self.highlight_color = "#ff66ff"
        self.button_color = "#1a3a3a"
        self.button_active_color = "#2a5a5a"
        
        # Настройка стилей
        self.setup_styles()
        
        # Создание главного холста
        self.canvas = tk.Canvas(root, highlightthickness=0, bg=self.bg_color)
        self.canvas.pack(fill=tk.BOTH, expand=True)
        
        # Неоновая обводка (толще)
        self.neon_border = None
        self.create_neon_border()
        self.animate_neon_border()
        
        # Данные
        self.data_file = "tick_data.json"
        self.default_data = {
            "current_week": {"cases": 0, "risk_level": "Нет данных", "date": ""},
            "previous_week": {"cases": 0, "risk_level": "Нет данных", "date": ""},
            "sources": [],
            "last_update": "никогда"
        }
        self.data = self.default_data.copy()
        
        # Создание интерфейса
        self.create_widgets()
        self.load_data()
        
        # Обработка изменения размера окна
        self.root.bind("<Configure>", self.on_window_resize)
        
        # Воспроизведение фоновой музыки
        self.play_background_sound()

    def load_sounds(self):
        """Загрузка звуковых эффектов"""
        try:
            self.background_sound = pygame.mixer.Sound("forest.wav") if os.path.exists("forest.wav") else None
            self.button_sound = pygame.mixer.Sound("button.wav") if os.path.exists("button.wav") else None
            self.update_sound = pygame.mixer.Sound("update.wav") if os.path.exists("update.wav") else None
        except:
            self.sound_enabled = False

    def play_background_sound(self):
        """Воспроизведение фонового звука"""
        if self.sound_enabled and self.background_sound:
            self.background_sound.set_volume(0.3)
            self.background_sound.play(loops=-1)

    def play_sound(self, sound):
        """Воспроизведение звукового эффекта"""
        if self.sound_enabled and sound:
            sound.set_volume(0.5)
            sound.play()

    def create_neon_border(self):
        """Создание неоновой обводки (толще)"""
        width = self.root.winfo_width()
        height = self.root.winfo_height()
        
        if width > 10 and height > 10:
            if hasattr(self, 'neon_border'):
                self.canvas.delete(self.neon_border)
            
            self.neon_border = self.canvas.create_rectangle(
                5, 5, width-5, height-5, 
                outline="#00ffff", width=5,
                tags=("neon_border",)
            )

    def animate_neon_border(self):
        """Анимация неоновой обводки"""
        colors = ["#00ffff", "#ff00ff", "#00ff99", "#ff6600", "#ffffff"]
        current_color = self.canvas.itemcget(self.neon_border, "outline") if self.neon_border else colors[0]
        next_color = colors[(colors.index(current_color) + 1) % len(colors)] if current_color in colors else colors[0]
        
        if self.neon_border:
            self.canvas.itemconfig(self.neon_border, outline=next_color)
        self.root.after(300, self.animate_neon_border)

    def on_window_resize(self, event):
        """Обработка изменения размера окна"""
        self.create_neon_border()

    def setup_styles(self):
        """Настройка стилей интерфейса"""
        self.style = ttk.Style()
        self.style.theme_use('alt')
        self.root.configure(bg=self.bg_color)
        
        self.style.configure('.', 
                           background=self.bg_color, 
                           foreground=self.text_color,
                           font=('Arial', 10))
        
        self.style.configure('TFrame', background=self.bg_color)
        
        self.style.configure('TButton', 
                           background=self.button_color, 
                           foreground=self.text_color,
                           font=('Arial', 10, 'bold'),
                           borderwidth=1)
        self.style.map('TButton', 
                      background=[('active', self.button_active_color)],
                      foreground=[('active', '#ffffff')])
        
        self.style.configure('TNotebook', background=self.bg_color)
        self.style.configure('TNotebook.Tab', 
                           background="#1a1a3a",
                           foreground=self.text_color,
                           padding=[10, 5],
                           font=('Arial', 10, 'bold'))
        self.style.map('TNotebook.Tab', 
                      background=[('selected', self.button_color)],
                      foreground=[('selected', self.highlight_color)])
        
        self.style.configure('Header.TLabel', 
                           font=('Arial', 16, 'bold'), 
                           foreground=self.highlight_color)
        
        self.style.configure('Data.TLabel', 
                           font=('Arial', 12, 'bold'), 
                           foreground='#00ff99')
        
        self.style.configure('Risk.TLabel', 
                           font=('Arial', 14, 'bold'))
        
        self.style.configure('DateEntry', 
                           fieldbackground=self.bg_color,
                           foreground=self.text_color,
                           background=self.button_color)

    def create_widgets(self):
        """Создание элементов интерфейса"""
        main_frame = ttk.Frame(self.canvas)
        self.canvas.create_window((10, 10), window=main_frame, anchor="nw", tags=("main_frame",))
        
        self.create_filter_panel(main_frame)
        
        self.notebook = ttk.Notebook(main_frame)
        self.notebook.pack(fill=tk.BOTH, expand=True, padx=10, pady=(0, 10))

        self.create_stats_tab()
        self.create_sources_tab()
        self.create_control_panel()

    def create_filter_panel(self, parent):
        """Создание панели фильтров"""
        filter_frame = ttk.LabelFrame(parent, text="Фильтр данных", style='TFrame')
        filter_frame.pack(fill=tk.X, padx=300, pady=20)

        ttk.Label(filter_frame, text="Начальная дата:").grid(row=0, column=0, padx=5, pady=5)
        self.start_date = DateEntry(filter_frame, 
                                  date_pattern='dd.mm.yyyy',
                                  background='darkblue', 
                                  foreground='white', 
                                  borderwidth=2)
        self.start_date.grid(row=0, column=1, padx=5, pady=5)

        ttk.Label(filter_frame, text="Конечная дата:").grid(row=0, column=2, padx=5, pady=5)
        self.end_date = DateEntry(filter_frame, 
                                date_pattern='dd.mm.yyyy',
                                background='darkblue', 
                                foreground='white', 
                                borderwidth=2)
        self.end_date.grid(row=0, column=3, padx=5, pady=5)

        apply_btn = ttk.Button(filter_frame, 
                             text="Применить фильтр", 
                             command=self.apply_date_filter)
        apply_btn.grid(row=0, column=4, padx=10, pady=5)
        apply_btn.bind("<Button-1>", lambda e: self.play_sound(self.button_sound))

    def create_stats_tab(self):
        """Создание вкладки со статистикой"""
        stats_tab = ttk.Frame(self.notebook)
        self.notebook.add(stats_tab, text="📊 Статистика активности")

        header = ttk.Label(stats_tab, 
                         text="АКТИВНОСТЬ КЛЕЩЕЙ В ТЮМЕНСКОЙ ОБЛАСТИ", 
                         style='Header.TLabel')
        header.pack(pady=10)

        data_frame = ttk.Frame(stats_tab)
        data_frame.pack(fill=tk.X, pady=10)

        ttk.Label(data_frame, text="Текущая неделя:").grid(row=0, column=0, padx=20, sticky=tk.W)
        self.current_data = ttk.Label(data_frame, text="0 случаев\n(дата неизвестна)", style='Data.TLabel')
        self.current_data.grid(row=1, column=0, padx=20)
        self.current_risk = ttk.Label(data_frame, text="Риск: Нет данных", style='Risk.TLabel')
        self.current_risk.grid(row=2, column=0, padx=20)

        ttk.Label(data_frame, text="Прошлая неделя:").grid(row=0, column=1, padx=20, sticky=tk.W)
        self.prev_data = ttk.Label(data_frame, text="0 случаев\n(дата неизвестна)", style='Data.TLabel')
        self.prev_data.grid(row=1, column=1, padx=20)
        self.prev_risk = ttk.Label(data_frame, text="Риск: Нет данных", style='Risk.TLabel')
        self.prev_risk.grid(row=2, column=1, padx=20)

        self.setup_graph(stats_tab)

    def setup_graph(self, parent):
        """Настройка графика"""
        graph_frame = ttk.Frame(parent)
        graph_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        self.figure = plt.Figure(figsize=(10, 5), dpi=100, facecolor=self.bg_color)
        self.ax = self.figure.add_subplot(111)
        self.ax.set_facecolor(self.bg_color)
        self.ax.tick_params(colors=self.text_color)
        for spine in self.ax.spines.values():
            spine.set_color(self.text_color)
        
        self.canvas_graph = FigureCanvasTkAgg(self.figure, graph_frame)
        self.canvas_graph.get_tk_widget().pack(fill=tk.BOTH, expand=True)

    def create_sources_tab(self):
        """Создание вкладки с источниками"""
        sources_tab = ttk.Frame(self.notebook)
        self.notebook.add(sources_tab, text="📰 Источники данных")
        
        self.sources_text = tk.Text(sources_tab, 
                                  wrap=tk.WORD, 
                                  bg="#1a3a3a",
                                  fg=self.text_color,
                                  font=('Arial', 10), 
                                  padx=10,
                                  pady=10,
                                  insertbackground=self.text_color,
                                  selectbackground=self.highlight_color)
        self.sources_text.pack(fill=tk.BOTH, expand=True)
        
        scrollbar = ttk.Scrollbar(self.sources_text)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.sources_text.config(yscrollcommand=scrollbar.set)
        scrollbar.config(command=self.sources_text.yview)

    def create_control_panel(self):
        """Создание панели управления"""
        control_frame = ttk.Frame(self.canvas)
        self.canvas.create_window((10, 10), window=control_frame, anchor="sw", tags=("control_frame",))
        control_frame.pack(fill=tk.X, pady=5)
        
        self.update_btn = ttk.Button(control_frame, 
                                   text="🔄 Обновить данные", 
                                   command=self.update_data_threaded)
        self.update_btn.pack(side=tk.LEFT, padx=5)
        
        self.sound_btn = ttk.Button(control_frame, 
                                   text="🔊 Звук Вкл/Выкл", 
                                   command=self.toggle_sound)
        self.sound_btn.pack(side=tk.LEFT, padx=5)
        
        self.update_label = ttk.Label(control_frame, style='Data.TLabel')
        self.update_label.pack(side=tk.RIGHT, padx=10)
        
        self.update_btn.bind("<Button-1>", lambda e: self.play_sound(self.button_sound))
        self.sound_btn.bind("<Button-1>", lambda e: self.play_sound(self.button_sound))

    def toggle_sound(self):
        """Включение/выключение звука"""
        self.sound_enabled = not self.sound_enabled
        if self.sound_enabled:
            self.play_background_sound()
            self.sound_btn.config(text="🔊 Звук Вкл")
        else:
            pygame.mixer.stop()
            self.sound_btn.config(text="🔇 Звук Выкл")

    def apply_date_filter(self):
        """Применение фильтра по датам"""
        start_date = self.start_date.get_date()
        end_date = self.end_date.get_date()
        
        if start_date > end_date:
            messagebox.showerror("Ошибка", "Начальная дата не может быть позже конечной")
            return
        
        filtered_data = []
        for src in self.data.get('sources', []):
            src_date = src['date']
            if isinstance(src_date, str):
                try:
                    src_date = datetime.strptime(src_date, '%d.%m.%Y').date()
                except ValueError:
                    continue
            
            if start_date <= src_date <= end_date:
                filtered_data.append(src)
        
        if not filtered_data:
            messagebox.showinfo("Информация", "Нет данных за выбранный период")
            return
        
        filtered_data.sort(key=lambda x: x['date'] if isinstance(x['date'], date) else datetime.strptime(x['date'], '%d.%m.%Y').date())
        
        self.update_filtered_graph(filtered_data, start_date, end_date)
        self.notebook.select(0)

    def update_filtered_graph(self, data, start_date, end_date):
        """Обновление графика с отфильтрованными данными"""
        weekly_data = {}
        for item in data:
            item_date = item['date'] if isinstance(item['date'], date) else datetime.strptime(item['date'], '%d.%m.%Y').date()
            year, week = item_date.isocalendar()[0], item_date.isocalendar()[1]
            key = f"{year}-{week}"
            if key not in weekly_data:
                weekly_data[key] = {
                    'cases': 0,
                    'start_date': item_date,
                    'end_date': item_date
                }
            weekly_data[key]['cases'] += item['cases']
            weekly_data[key]['end_date'] = max(weekly_data[key]['end_date'], item_date)
        
        weeks = []
        cases = []
        colors = []
        
        for week_data in sorted(weekly_data.values(), key=lambda x: x['start_date']):
            week_label = f"{week_data['start_date'].strftime('%d.%m')}-{week_data['end_date'].strftime('%d.%m')}"
            weeks.append(week_label)
            cases.append(week_data['cases'])
            risk_level = self.calculate_risk_level(week_data['cases'])
            colors.append(self.get_risk_color(risk_level))
        
        self.ax.clear()
        bars = self.ax.bar(weeks, cases, color=colors)
        self.ax.set_ylabel('Количество обращений', color=self.text_color)
        self.ax.set_title(f'Активность клещей {start_date.strftime("%d.%m.%Y")}-{end_date.strftime("%d.%m.%Y")}', 
                         color=self.highlight_color)
        
        for bar in bars:
            height = bar.get_height()
            self.ax.text(bar.get_x() + bar.get_width()/2., height,
                        f'{int(height)}',
                        ha='center', va='bottom', color='#ffffff')
        
        self.canvas_graph.draw()
        
        if len(weekly_data) >= 2:
            last_week = sorted(weekly_data.values(), key=lambda x: x['start_date'])[-1]
            prev_week = sorted(weekly_data.values(), key=lambda x: x['start_date'])[-2]
            
            self.current_data.config(text=f"{last_week['cases']} случаев\n"
                                      f"({last_week['start_date'].strftime('%d.%m')}-{last_week['end_date'].strftime('%d.%m')})")
            self.prev_data.config(text=f"{prev_week['cases']} случаев\n"
                                    f"({prev_week['start_date'].strftime('%d.%m')}-{prev_week['end_date'].strftime('%d.%m')})")
            
            self.current_risk.config(
                text=f"Риск: {self.calculate_risk_level(last_week['cases'])}",
                foreground=self.get_risk_color(self.calculate_risk_level(last_week['cases']))
            )
            self.prev_risk.config(
                text=f"Риск: {self.calculate_risk_level(prev_week['cases'])}",
                foreground=self.get_risk_color(self.calculate_risk_level(prev_week['cases']))
            )

    def parse_rospotrebnadzor(self):
        """Парсинг данных с сайта Роспотребнадзора"""
        web_data = self.parse_web_data()
        rss_data = self.parse_rss_feed()
        
        combined_results = []
        if web_data:
            combined_results.extend(web_data)
        if rss_data:
            combined_results.extend(rss_data)
        
        if combined_results:
            combined_results.sort(key=lambda x: x['date'], reverse=True)
            
            current_week_data = self.find_week_data(combined_results, 0)
            previous_week_data = self.find_week_data(combined_results, 1)
            
            return {
                'current_week': current_week_data,
                'previous_week': previous_week_data,
                'sources': combined_results[:100]  # 100 последних записей
            }
        return None

    def find_week_data(self, data, weeks_ago):
        """Находит данные за указанное количество недель назад"""
        if not data:
            return {"cases": 0, "date": datetime.now().date(), "risk_level": "Нет данных"}
            
        target_date = datetime.now().date() - timedelta(weeks=weeks_ago)
        
        for item in data:
            item_date = item['date'] if isinstance(item['date'], date) else datetime.strptime(item['date'], '%d.%m.%Y').date()
            if item_date <= target_date:
                return {
                    'cases': item['cases'],
                    'date': item_date,
                    'risk_level': self.calculate_risk_level(item['cases'])
                }
        
        return {
            'cases': data[-1]['cases'],
            'date': data[-1]['date'],
            'risk_level': self.calculate_risk_level(data[-1]['cases'])
        }

    def parse_web_data(self):
        """Парсинг данных с веб-сайта (100 записей)"""
        try:
            ua = UserAgent()
            headers = {
                'User-Agent': ua.random,
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
                'Accept-Language': 'ru-RU,ru;q=0.8,en-US;q=0.5,en;q=0.3',
            }
            
            base_url = "https://72.rospotrebnadzor.ru"
            search_url = f"{base_url}/search/?q=%D0%BA%D0%BB%D0%B5%D1%89%D0%B8"
            
            response = requests.get(search_url, headers=headers, timeout=15)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.text, 'html.parser')
            results = []
            
            news_items = soup.find_all('div', class_='search-item')[:100]
            
            for item in news_items:
                try:
                    title = item.find('a', class_='search-title').text.strip()
                    date_text = item.find('div', class_='search-date').text.strip()
                    content = item.find('div', class_='search-text').text.strip()
                    
                    date_match = re.search(r'\d{2}\.\d{2}\.\d{4}', date_text)
                    if not date_match:
                        continue
                        
                    date = datetime.strptime(date_match.group(), '%d.%m.%Y').date()
                    
                    cases = self.extract_case_number(title + " " + content)
                    if cases:
                        results.append({
                            'date': date,
                            'cases': cases,
                            'title': title,
                            'content': content[:200] + "...",
                            'url': base_url + item.find('a')['href'],
                            'source': 'Роспотребнадзор (веб)'
                        })
                except Exception as e:
                    print(f"Ошибка обработки новости: {str(e)}")
                    continue
            
            return results
            
        except Exception as e:
            print(f"Ошибка при парсинге веб-сайта: {str(e)}")
            return None

    def parse_rss_feed(self):
        """Парсинг RSS-ленты (100 записей)"""
        try:
            rss_url = "https://72.rospotrebnadzor.ru/rss/"
            feed = feedparser.parse(rss_url)
            results = []
            
            for entry in feed.entries[:100]:
                try:
                    date = datetime(*entry.published_parsed[:6]).date()
                    
                    if any(word in entry.title.lower() or word in entry.description.lower() 
                          for word in ['клещ', 'укус', 'энцефалит', 'присасыван']):
                        
                        cases = self.extract_case_number(entry.title + " " + entry.description)
                        if cases:
                            results.append({
                                'date': date,
                                'cases': cases,
                                'title': entry.title,
                                'content': entry.description[:200] + "...",
                                'url': entry.link,
                                'source': 'Роспотребнадзор (RSS)'
                            })
                except Exception as e:
                    print(f"Ошибка обработки RSS-записи: {str(e)}")
                    continue
            
            return results
            
        except Exception as e:
            print(f"Ошибка при парсинге RSS: {str(e)}")
            return None

    def extract_case_number(self, text):
        """Извлекает количество случаев из текста"""
        patterns = [
            r'зарегистрировано\D*(\d+)\D*обращ',
            r'выявлено\D*(\d+)\D*случа',
            r'(\d+)\D*укус',
            r'клещ\D*(\d+)'
        ]
        
        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                try:
                    return int(match.group(1))
                except ValueError:
                    continue
        return None

    def update_data(self):
        """Основной метод обновления данных"""
        try:
            web_data = self.parse_rospotrebnadzor()
            
            if web_data:
                self.process_new_data(web_data)
                messagebox.showinfo("Успех", "Данные успешно обновлены!")
                self.play_sound(self.update_sound)
            else:
                raise ValueError("Не удалось получить данные с сайта")
                
        except Exception as e:
            print(f"Ошибка при обновлении: {str(e)}")
            self.load_backup_data()
            messagebox.showwarning("Внимание", 
                f"Не удалось загрузить новые данные: {str(e)}\nИспользуются сохранённые данные.")

    def update_data_threaded(self):
        """Запуск обновления в отдельном потоке"""
        self.update_btn.config(state=tk.DISABLED)
        thread = threading.Thread(target=self.update_data)
        thread.daemon = True
        thread.start()
        self.root.after(100, self.check_thread, thread)

    def check_thread(self, thread):
        """Проверка завершения потока"""
        if thread.is_alive():
            self.root.after(100, self.check_thread, thread)
        else:
            self.update_btn.config(state=tk.NORMAL)

    def process_new_data(self, new_data):
        """Обработка новых данных"""
        self.data = {
            "current_week": {
                "cases": new_data['current_week']['cases'],
                "date": new_data['current_week']['date'].strftime('%d.%m.%Y'),
                "risk_level": self.calculate_risk_level(new_data['current_week']['cases'])
            },
            "previous_week": {
                "cases": new_data['previous_week']['cases'],
                "date": new_data['previous_week']['date'].strftime('%d.%m.%Y'),
                "risk_level": self.calculate_risk_level(new_data['previous_week']['cases'])
            },
            "sources": new_data['sources'],
            "last_update": datetime.now().strftime("%d.%m.%Y %H:%M:%S")
        }
        
        self.update_ui()
        self.save_data()

    def update_ui(self):
        """Обновление интерфейса"""
        current = self.data['current_week']
        prev = self.data['previous_week']
        
        self.current_data.config(text=f"{current['cases']} случаев\n({current['date']})")
        self.prev_data.config(text=f"{prev['cases']} случаев\n({prev['date']})")
        
        self.current_risk.config(
            text=f"Риск: {current['risk_level']}",
            foreground=self.get_risk_color(current['risk_level'])
        )
        self.prev_risk.config(
            text=f"Риск: {prev['risk_level']}",
            foreground=self.get_risk_color(prev['risk_level'])
        )
        
        self.update_graph()
        self.update_sources()
        self.update_label.config(text=f"Обновлено: {self.data.get('last_update', 'никогда')}")

    def update_graph(self):
        """Обновление графика"""
        self.ax.clear()
        
        if self.data["current_week"]["date"] and self.data["previous_week"]["date"]:
            weeks = [
                f"{self.data['previous_week']['date']}\n(прошлая)", 
                f"{self.data['current_week']['date']}\n(текущая)"
            ]
            cases = [
                self.data["previous_week"]["cases"],
                self.data["current_week"]["cases"]
            ]
            
            colors = [
                self.get_risk_color(self.data["previous_week"]["risk_level"]),
                self.get_risk_color(self.data["current_week"]["risk_level"])
            ]
            
            bars = self.ax.bar(weeks, cases, color=colors)
            self.ax.set_ylabel('Количество обращений', color=self.text_color)
            self.ax.set_title('Динамика активности клещей', color=self.highlight_color)
            
            for bar in bars:
                height = bar.get_height()
                self.ax.text(bar.get_x() + bar.get_width()/2., height,
                            f'{int(height)}',
                            ha='center', va='bottom', color='#ffffff')
            
            self.canvas_graph.draw()

    def update_sources(self):
        """Обновление списка источников"""
        self.sources_text.config(state=tk.NORMAL)
        self.sources_text.delete(1.0, tk.END)
        
        for src in self.data.get('sources', []):
            date_str = src['date'].strftime('%d.%m.%Y') if isinstance(src['date'], date) else src['date']
            self.sources_text.insert(tk.END, 
                                   f"Дата: {date_str}\n"
                                   f"Случаев: {src['cases']}\n"
                                   f"Источник: {src.get('source', 'Роспотребнадзор')}\n"
                                   f"Заголовок: {src.get('title', '')}\n"
                                   f"Ссылка: {src.get('url', '')}\n\n")
        
        self.sources_text.config(state=tk.DISABLED)

    def calculate_risk_level(self, cases):
        """Определение уровня риска"""
        if not isinstance(cases, int):
            return "Нет данных"
            
        if cases < 50:
            return "Низкий"
        elif 50 <= cases < 100:
            return "Умеренный"
        elif 100 <= cases < 150:
            return "Высокий"
        else:
            return "Очень высокий"

    def get_risk_color(self, risk_level):
        """Цвет для уровня риска"""
        colors = {
            "Низкий": "#00ff00",
            "Умеренный": "#ffff00",
            "Высокий": "#ff9900",
            "Очень высокий": "#ff0000",
            "Нет данных": "#00ffff"
        }
        return colors.get(risk_level, "#00ffff")

    def save_data(self):
        """Сохранение данных в файл"""
        try:
            data_to_save = self.data.copy()
            for src in data_to_save['sources']:
                if isinstance(src['date'], date):
                    src['date'] = src['date'].strftime('%d.%m.%Y')
            
            with open(self.data_file, 'w', encoding='utf-8') as f:
                json.dump(data_to_save, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"Ошибка при сохранении: {str(e)}")

    def load_data(self):
        """Загрузка данных из файла"""
        try:
            if os.path.exists(self.data_file):
                with open(self.data_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    
                    for src in data.get('sources', []):
                        if 'date' in src and isinstance(src['date'], str):
                            try:
                                src['date'] = datetime.strptime(src['date'], '%d.%m.%Y').date()
                            except ValueError:
                                print(f"Неизвестный формат даты: {src['date']}")
                                continue
                    
                    self.data = data
                    self.update_ui()
        except (FileNotFoundError, json.JSONDecodeError) as e:
            print(f"Ошибка загрузки: {str(e)}")
            self.data = self.default_data.copy()

    def load_backup_data(self):
        """Загрузка резервных данных"""
        self.load_data()

    def run(self):
        self.root.mainloop()

if __name__ == "__main__":
    try:
        root = tk.Tk()
        app = TickActivityMonitor(root)
        app.run()
    except Exception as e:
        print(f"Произошла ошибка: {str(e)}")
        sys.exit(1)