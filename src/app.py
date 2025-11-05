"""Веб-приложение для мониторинга активности клещей"""
from flask import Flask, render_template, jsonify, request, send_file, make_response
from flask_caching import Cache
from flask_cors import CORS
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_jwt_extended import JWTManager, create_access_token, jwt_required, get_jwt_identity
from prometheus_client import Counter, Histogram, Gauge, generate_latest, CONTENT_TYPE_LATEST
from datetime import datetime, date, timedelta
import threading
import json
import os
import time
from io import BytesIO
from logger_config import setup_logger
from database import DatabaseManager
from parser import TickParser
from ml_predictor import TickPredictor
from cache_manager import CacheManager
from notifications import NotificationManager
from export_manager import ExportManager
from swagger_docs import get_swagger_json

app = Flask(__name__, template_folder='../templates', static_folder='../static')
logger = setup_logger()

# CORS
CORS(app)

# Rate limiting
limiter = Limiter(
    app=app,
    key_func=get_remote_address,
    default_limits=["200 per day", "50 per hour"]
)

# JWT
app.config['JWT_SECRET_KEY'] = os.getenv('JWT_SECRET_KEY', 'change-this-secret-key')
app.config['JWT_ACCESS_TOKEN_EXPIRES'] = timedelta(hours=1)
jwt = JWTManager(app)

# Кэширование
redis_url = os.getenv('REDIS_URL', 'redis://mite_tmn_redis:6379/0')
try:
    cache_config = {
        'CACHE_TYPE': 'redis',
        'CACHE_REDIS_URL': redis_url,
        'CACHE_DEFAULT_TIMEOUT': 300
    }
    cache = Cache(app, config=cache_config)
    cache_manager = CacheManager(redis_url)
    logger.info(f"Redis кэш инициализирован: {redis_url}")
except Exception as e:
    logger.warning(f"Ошибка инициализации кэша: {str(e)}")
    cache = None
    cache_manager = CacheManager(None)

# Prometheus метрики
request_count = Counter('http_requests_total', 'Total HTTP requests', ['method', 'endpoint'])
request_duration = Histogram('http_request_duration_seconds', 'HTTP request duration', ['method', 'endpoint'])
active_users = Gauge('active_users', 'Number of active users')
data_points = Gauge('data_points_total', 'Total data points in database')
cache_hits = Counter('cache_hits_total', 'Total cache hits', ['cache_key'])
cache_misses = Counter('cache_misses_total', 'Total cache misses', ['cache_key'])
parsing_errors = Counter('parsing_errors_total', 'Total parsing errors', ['source'])
ml_predictions = Counter('ml_predictions_total', 'Total ML predictions made')

# Инициализация компонентов
# Используем переменную окружения DATABASE_URL если доступна
database_url = os.getenv('DATABASE_URL', 'postgresql://mite_user:mite_password@db:5432/mite_tmn')
db = DatabaseManager(database_url)
parser = TickParser(db, logger)
ml_predictor = TickPredictor(db)
notification_manager = NotificationManager(app)
export_manager = ExportManager()

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
            
            # После обновления данных переобучаем ML модель
            try:
                historical_data = db.load_tick_data(limit=None, order_by_date_desc=False)
                if historical_data and len(historical_data) >= 10:
                    logger.info("Переобучение ML модели на обновленных данных")
                    ml_predictor.train_model(historical_data)
            except Exception as e:
                logger.warning(f"Ошибка при переобучении модели: {str(e)}")
            
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

@app.route('/api/map-data')
def get_map_data():
    """Получение данных для карты"""
    try:
        view = request.args.get('view', 'all')
        
        if view == 'week':
            # Данные за последнюю неделю
            start_date = date.today() - timedelta(days=7)
            data = db.get_filtered_data(start_date, date.today())
        elif view == 'month':
            # Данные за последний месяц
            start_date = date.today() - timedelta(days=30)
            data = db.get_filtered_data(start_date, date.today())
        else:
            # Все данные
            data = db.load_tick_data(limit=None, order_by_date_desc=False)
        
        # Обрабатываем данные для карты
        map_data = []
        for item in data:
            # Используем сохраненную локацию или извлекаем из текста
            location = item.get('location')
            if not location:
                location = extract_location_from_text(item.get('title', '') + ' ' + item.get('content', ''))
            
            if location:
                coordinates = get_tyumen_region_coordinates(location)
                if coordinates:
                    map_data.append({
                        'lat': coordinates[0],
                        'lng': coordinates[1],
                        'location': location,
                        'cases': item.get('cases', 0),
                        'date': item['date'].strftime('%d.%m.%Y') if isinstance(item['date'], date) else str(item['date']),
                        'source': item.get('source', ''),
                        'title': item.get('title', '')[:50]
                    })
        
        return jsonify({'locations': map_data})
    except Exception as e:
        logger.error(f"Ошибка получения данных карты: {str(e)}")
        return jsonify({'error': str(e)}), 500

def extract_location_from_text(text):
    """Извлечение названия населенного пункта из текста"""
    import re
    
    # Список основных населенных пунктов Тюменской области
    locations = [
        'Тюмень', 'Тобольск', 'Ишим', 'Ялуторовск', 'Заводоуковск',
        'Голышманово', 'Вагай', 'Упорово', 'Омутинское', 'Армизонское',
        'Бердюжье', 'Абатское', 'Викулово', 'Сорокино', 'Юргинское',
        'Нижняя Тавда', 'Ярково', 'Казанское', 'Исетское', 'Сладково'
    ]
    
    text_lower = text.lower()
    for location in locations:
        if location.lower() in text_lower:
            return location
    
    # Попытка найти упоминание района
    district_patterns = [
        r'(\w+)\s*район',
        r'(\w+)\s*округ',
        r'(\w+)\s*муниципалитет'
    ]
    
    for pattern in district_patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            return match.group(1)
    
    return None

def get_tyumen_region_coordinates(location):
    """Получение координат для населенного пункта Тюменской области"""
    # Координаты основных населенных пунктов
    coordinates_map = {
        'Тюмень': [57.1522, 65.5272],
        'Тобольск': [58.1981, 68.2597],
        'Ишим': [56.1125, 69.4903],
        'Ялуторовск': [56.6517, 66.3128],
        'Заводоуковск': [56.5014, 66.5514],
        'Голышманово': [56.3989, 68.3697],
        'Вагай': [57.9353, 69.0278],
        'Упорово': [56.3189, 66.2708],
        'Омутинское': [56.4783, 67.6556],
        'Армизонское': [56.0903, 67.7014],
        'Бердюжье': [55.8069, 68.5397],
        'Абатское': [56.2797, 70.4500],
        'Викулово': [56.8167, 70.6167],
        'Сорокино': [56.1289, 67.3944],
        'Юргинское': [56.8250, 67.3958],
        'Нижняя Тавда': [57.6733, 66.1744],
        'Ярково': [57.4103, 67.0664],
        'Казанское': [55.6417, 69.2333],
        'Исетское': [56.4856, 65.3278],
        'Сладково': [55.5278, 70.3389]
    }
    
    # Прямое совпадение
    if location in coordinates_map:
        return coordinates_map[location]
    
    # Поиск по частичному совпадению
    location_lower = location.lower()
    for key, coords in coordinates_map.items():
        if key.lower() in location_lower or location_lower in key.lower():
            return coords
    
    # Если не найдено, возвращаем центр Тюменской области
    return [57.0, 65.5]

@app.route('/api/forecast')
def get_forecast():
    """Получение прогноза активности клещей на 2026 год"""
    try:
        # Загружаем исторические данные
        historical_data = db.load_tick_data(limit=None, order_by_date_desc=False)
        
        if not historical_data or len(historical_data) < 10:
            return jsonify({
                'error': 'Недостаточно данных для прогноза',
                'forecast': []
            })
        
        # Получаем прогноз на 2026 год
        forecast = ml_predictor.get_forecast_for_2026(historical_data)
        
        # Группируем по месяцам для удобства отображения
        month_names_ru = {
            1: 'Январь', 2: 'Февраль', 3: 'Март', 4: 'Апрель',
            5: 'Май', 6: 'Июнь', 7: 'Июль', 8: 'Август',
            9: 'Сентябрь', 10: 'Октябрь', 11: 'Ноябрь', 12: 'Декабрь'
        }
        
        monthly_forecast = {}
        for item in forecast:
            month_key = item['date'].strftime('%Y-%m')
            if month_key not in monthly_forecast:
                month_name = month_names_ru.get(item['date'].month, item['date'].strftime('%B'))
                monthly_forecast[month_key] = {
                    'month': f"{month_name} {item['date'].year}",
                    'total_cases': 0,
                    'weeks': []
                }
            monthly_forecast[month_key]['total_cases'] += item['cases']
            monthly_forecast[month_key]['weeks'].append(item)
        
        # Преобразуем в список и сортируем
        monthly_list = sorted(monthly_forecast.items())
        
        forecast_data = []
        for month_key, month_data in monthly_list:
            forecast_data.append({
                'month': month_data['month'],
                'month_key': month_key,
                'total_cases': month_data['total_cases'],
                'avg_weekly': int(month_data['total_cases'] / len(month_data['weeks'])) if month_data['weeks'] else 0
            })
        
        return jsonify({
            'forecast': forecast_data,
            'weekly_forecast': [
                {
                    'date': item['date'].strftime('%d.%m.%Y'),
                    'cases': item['cases'],
                    'week': item['week_number']
                }
                for item in forecast[:52]  # Первые 52 недели (год)
            ]
        })
    except Exception as e:
        logger.error(f"Ошибка получения прогноза: {str(e)}", exc_info=True)
        return jsonify({'error': str(e), 'forecast': []}), 500

@app.route('/api/news-feed')
def get_news_feed():
    """Получение ленты новостей, сгенерированной ML"""
    try:
        # Загружаем исторические данные
        historical_data = db.load_tick_data(limit=None, order_by_date_desc=False)
        
        if not historical_data or len(historical_data) < 5:
            return jsonify({
                'error': 'Недостаточно данных для генерации новостей',
                'news': []
            })
        
        # Генерируем новости
        news_items = ml_predictor.generate_news_feed(historical_data, days_back=30)
        
        # Форматируем для фронтенда
        formatted_news = []
        for item in news_items:
            formatted_news.append({
                'text': item['text'],
                'date': item['date'].strftime('%d.%m.%Y') if isinstance(item['date'], date) else str(item['date']),
                'location': item.get('location', ''),
                'cases': item.get('cases', 0),
                'type': item.get('type', 'info'),
                'priority': item.get('priority', 'low')
            })
        
        return jsonify({
            'news': formatted_news,
            'count': len(formatted_news)
        })
    except Exception as e:
        logger.error(f"Ошибка получения ленты новостей: {str(e)}", exc_info=True)
        return jsonify({'error': str(e), 'news': []}), 500

@app.route('/api/export/<format>')
@limiter.limit("10 per hour")
def export_data(format):
    """Экспорт данных в различных форматах"""
    try:
        format = format.lower()
        if format not in ['csv', 'excel', 'pdf']:
            return jsonify({'error': 'Неподдерживаемый формат'}), 400
        
        # Получаем параметры фильтрации
        start_date = request.args.get('start_date')
        end_date = request.args.get('end_date')
        
        if start_date and end_date:
            data = db.get_filtered_data(
                datetime.strptime(start_date, '%Y-%m-%d').date(),
                datetime.strptime(end_date, '%Y-%m-%d').date()
            )
        else:
            data = db.load_tick_data(limit=None, order_by_date_desc=False)
        
        # Преобразуем даты в строки для экспорта
        export_data_list = []
        for item in data:
            export_item = item.copy()
            if isinstance(export_item.get('date'), date):
                export_item['date'] = export_item['date'].strftime('%d.%m.%Y')
            export_data_list.append(export_item)
        
        if format == 'csv':
            buffer = export_manager.export_to_csv(export_data_list)
            return send_file(
                buffer,
                mimetype='text/csv',
                as_attachment=True,
                download_name=f'tick_data_{datetime.now().strftime("%Y%m%d")}.csv'
            )
        elif format == 'excel':
            buffer = export_manager.export_to_excel(export_data_list)
            return send_file(
                buffer,
                mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
                as_attachment=True,
                download_name=f'tick_data_{datetime.now().strftime("%Y%m%d")}.xlsx'
            )
        elif format == 'pdf':
            buffer = export_manager.export_to_pdf(
                export_data_list,
                title=f"Отчет о активности клещей ({start_date or 'все данные'})"
            )
            return send_file(
                buffer,
                mimetype='application/pdf',
                as_attachment=True,
                download_name=f'tick_data_{datetime.now().strftime("%Y%m%d")}.pdf'
            )
    except Exception as e:
        logger.error(f"Ошибка экспорта данных: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/analytics/compare')
def compare_years():
    """Сравнение данных с предыдущими годами"""
    try:
        current_year = datetime.now().year
        years = [current_year - i for i in range(4)]  # Последние 4 года
        
        comparison = {}
        for year in years:
            start_date = date(year, 1, 1)
            end_date = date(year, 12, 31)
            year_data = db.get_filtered_data(start_date, end_date)
            
            total_cases = sum(item.get('cases', 0) for item in year_data)
            comparison[year] = {
                'total_cases': total_cases,
                'records_count': len(year_data),
                'avg_per_month': total_cases / 12 if len(year_data) > 0 else 0
            }
        
        return jsonify({'comparison': comparison})
    except Exception as e:
        logger.error(f"Ошибка сравнения годов: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/swagger.json')
def swagger_json():
    """Swagger JSON документация"""
    return get_swagger_json()

@app.route('/api/docs')
def api_docs():
    """HTML страница с Swagger UI"""
    return render_template('swagger.html')

@app.route('/api/metrics')
def metrics():
    """Prometheus метрики"""
    try:
        # Обновляем метрику количества данных
        try:
            all_data = db.load_tick_data(limit=None)
            data_points.set(len(all_data))
        except:
            pass
        
        return generate_latest(), 200, {'Content-Type': CONTENT_TYPE_LATEST}
    except Exception as e:
        logger.error(f"Ошибка генерации метрик: {str(e)}")
        return '', 500

@app.route('/api/update', methods=['POST'])
@limiter.limit("5 per hour")
def update_data():
    """Обновление данных"""
    try:
        # Запускаем парсинг в отдельном потоке
        thread = threading.Thread(target=parser.update_all_data)
        thread.daemon = True
        thread.start()
        
        # Очищаем кэш после обновления
        if cache_manager.enabled:
            cache_manager.clear_pattern('stats_*')
            cache_manager.clear_pattern('graph_*')
            cache_manager.clear_pattern('sources_*')
        
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

