"""Веб-приложение для мониторинга активности клещей"""
from flask import Flask, render_template, jsonify, request
from datetime import datetime, date, timedelta
import threading
import json
import os
import time
from logger_config import setup_logger
from database import DatabaseManager
from parser import TickParser

app = Flask(__name__, template_folder='../templates', static_folder='../static')
logger = setup_logger()

# Инициализация компонентов
# Используем переменную окружения DATABASE_URL если доступна
db = DatabaseManager(os.getenv('DATABASE_URL'))
parser = TickParser(db, logger)

# Инициализация БД при импорте (для gunicorn)
try:
    db.create_tables()
    logger.info("База данных инициализирована при старте")
except Exception as e:
    logger.error(f"Ошибка инициализации БД при старте: {str(e)}", exc_info=True)

# Функция для автоматического обновления данных
def auto_update_worker():
    """Рабочий поток для автоматического обновления данных"""
    while True:
        try:
            # Загружаем конфигурацию для получения интервала
            config_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'config', 'config.json')
            if os.path.exists(config_path):
                with open(config_path, 'r', encoding='utf-8') as f:
                    config = json.load(f)
                    interval_minutes = config.get('parsing', {}).get('auto_update_interval_minutes', 20)
            else:
                interval_minutes = 20
            
            logger.info(f"Автоматическое обновление данных запущено (интервал: {interval_minutes} минут)")
            parser.update_all_data()
            logger.info(f"Автоматическое обновление завершено. Следующее обновление через {interval_minutes} минут")
            
            # Ждем указанный интервал
            time.sleep(interval_minutes * 60)
        except Exception as e:
            logger.error(f"Ошибка в автоматическом обновлении: {str(e)}", exc_info=True)
            # При ошибке ждем 5 минут перед повторной попыткой
            time.sleep(5 * 60)

# Запуск автоматического обновления в отдельном потоке
update_thread = threading.Thread(target=auto_update_worker, daemon=True)
update_thread.start()
logger.info("Автоматический мониторинг запущен")

@app.route('/')
def index():
    """Главная страница"""
    return render_template('index.html')

@app.route('/api/stats')
def get_stats():
    """Получение статистики"""
    try:
        current_week = db.get_weekly_data(0)
        previous_week = db.get_weekly_data(1)
        
        return jsonify({
            'current_week': {
                'cases': current_week['cases'],
                'date': current_week['date'].strftime('%d.%m.%Y') if isinstance(current_week['date'], date) else str(current_week['date']),
                'risk_level': current_week['risk_level']
            },
            'previous_week': {
                'cases': previous_week['cases'],
                'date': previous_week['date'].strftime('%d.%m.%Y') if isinstance(previous_week['date'], date) else str(previous_week['date']),
                'risk_level': previous_week['risk_level']
            }
        })
    except Exception as e:
        logger.error(f"Ошибка получения статистики: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/sources')
def get_sources():
    """Получение списка источников"""
    try:
        limit = request.args.get('limit', 20, type=int)
        sources = db.load_tick_data(limit=limit, order_by_date_desc=True)
        
        # Преобразуем даты в строки
        for source in sources:
            if isinstance(source['date'], date):
                source['date'] = source['date'].strftime('%d.%m.%Y')
        
        return jsonify({'sources': sources})
    except Exception as e:
        logger.error(f"Ошибка получения источников: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/graph')
def get_graph_data():
    """Получение данных для графика"""
    try:
        start_date = request.args.get('start_date')
        end_date = request.args.get('end_date')
        
        if start_date and end_date:
            # Фильтрованные данные
            start = datetime.strptime(start_date, '%Y-%m-%d').date()
            end = datetime.strptime(end_date, '%Y-%m-%d').date()
            data = db.get_filtered_data(start, end)
        else:
            # Все данные
            data = db.load_tick_data(limit=None, order_by_date_desc=False)
        
        # Группируем по неделям
        import pandas as pd
        df = pd.DataFrame(data)
        if df.empty:
            return jsonify({'weeks': [], 'cases': [], 'colors': []})
        
        df['date'] = pd.to_datetime(df['date'])
        df['year_week'] = df['date'].dt.strftime('%Y-%U')
        weekly_data = df.groupby('year_week').agg({
            'cases': 'sum',
            'date': ['min', 'max']
        }).reset_index()
        
        weekly_data.columns = ['year_week', 'cases', 'start_date', 'end_date']
        weekly_data = weekly_data.sort_values('start_date')
        
        # Берем последние 8 недель
        weekly_data = weekly_data.tail(8)
        
        weeks = []
        cases = []
        colors = []
        
        for _, row in weekly_data.iterrows():
            week_label = f"{row['start_date'].strftime('%d.%m')}-{row['end_date'].strftime('%d.%m')}"
            weeks.append(week_label)
            cases.append(int(row['cases']))
            risk_level = calculate_risk_level(row['cases'])
            colors.append(get_risk_color(risk_level))
        
        return jsonify({
            'weeks': weeks,
            'cases': cases,
            'colors': colors
        })
    except Exception as e:
        logger.error(f"Ошибка получения данных графика: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/update', methods=['POST'])
def update_data():
    """Обновление данных"""
    try:
        # Запускаем парсинг в отдельном потоке
        thread = threading.Thread(target=parser.update_all_data)
        thread.daemon = True
        thread.start()
        
        return jsonify({'status': 'started', 'message': 'Обновление данных запущено'})
    except Exception as e:
        logger.error(f"Ошибка запуска обновления: {str(e)}")
        return jsonify({'error': str(e)}), 500

def calculate_risk_level(cases):
    """Определение уровня риска"""
    if not isinstance(cases, int) or cases == 0:
        return "Нет данных"
    if cases < 50:
        return "Низкий"
    elif cases < 100:
        return "Умеренный"
    elif cases < 150:
        return "Высокий"
    else:
        return "Очень высокий"

def get_risk_color(risk_level):
    """Цвет для уровня риска"""
    colors = {
        "Низкий": "#00c853",
        "Умеренный": "#ffd600",
        "Высокий": "#ff6f00",
        "Очень высокий": "#d32f2f",
        "Нет данных": "#9e9e9e"
    }
    return colors.get(risk_level, "#9e9e9e")

if __name__ == '__main__':
    # Инициализация БД
    try:
        db.create_tables()
        logger.info("База данных инициализирована")
    except Exception as e:
        logger.error(f"Ошибка инициализации БД: {str(e)}", exc_info=True)
    
    # Запуск приложения
    app.run(host='0.0.0.0', port=5000, debug=False)

