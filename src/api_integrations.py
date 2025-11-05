"""Модуль для интеграции с внешними API (медицинские учреждения, погода)"""
import requests
from datetime import date, timedelta
from logger_config import setup_logger
import os
import json

logger = setup_logger()


class MedicalAPI:
    """Класс для работы с API медицинских учреждений"""
    
    def __init__(self, config=None):
        self.config = config or {}
        self.api_url = self.config.get('api_url', '')
        self.api_key = os.getenv('MEDICAL_API_KEY', self.config.get('api_key', ''))
        self.enabled = self.config.get('enabled', False) and bool(self.api_url and self.api_key)
    
    def get_tick_statistics(self, start_date=None, end_date=None):
        """Получение статистики по клещам из API медицинских учреждений
        
        Args:
            start_date: Начальная дата
            end_date: Конечная дата
        
        Returns:
            list: Список словарей с данными
        """
        if not self.enabled:
            logger.debug("API медицинских учреждений отключено")
            return []
        
        try:
            params = {}
            if start_date:
                params['start_date'] = start_date.strftime('%Y-%m-%d')
            if end_date:
                params['end_date'] = end_date.strftime('%Y-%m-%d')
            
            headers = {
                'Authorization': f'Bearer {self.api_key}',
                'Content-Type': 'application/json'
            }
            
            response = requests.get(
                f"{self.api_url}/api/tick-statistics",
                params=params,
                headers=headers,
                timeout=15
            )
            
            if response.status_code == 200:
                data = response.json()
                results = []
                
                for item in data.get('results', []):
                    results.append({
                        'date': date.fromisoformat(item.get('date', date.today().isoformat())),
                        'cases': item.get('cases', 0),
                        'title': item.get('title', ''),
                        'content': item.get('description', ''),
                        'url': item.get('url', ''),
                        'source': 'API медицинских учреждений',
                        'location': item.get('location')
                    })
                
                logger.info(f"Получено {len(results)} записей из API медицинских учреждений")
                return results
            else:
                logger.warning(f"Ошибка API медицинских учреждений: {response.status_code}")
                return []
                
        except Exception as e:
            logger.error(f"Ошибка при запросе к API медицинских учреждений: {str(e)}")
            return []


class WeatherAPI:
    """Класс для работы с API погоды"""
    
    def __init__(self, config=None):
        self.config = config or {}
        self.api_url = self.config.get('api_url', 'https://api.openweathermap.org/data/2.5')
        self.api_key = os.getenv('WEATHER_API_KEY', self.config.get('api_key', ''))
        self.enabled = self.config.get('enabled', False) and bool(self.api_key)
        # Координаты Тюмени
        self.lat = 57.1522
        self.lon = 65.5272
    
    def get_weather_data(self, target_date=None):
        """Получение данных о погоде для корреляции
        
        Args:
            target_date: Дата для получения погоды (опционально)
        
        Returns:
            dict: Словарь с данными о погоде
        """
        if not self.enabled:
            logger.debug("API погоды отключено")
            return None
        
        try:
            if target_date is None:
                target_date = date.today()
            
            # Используем исторические данные или текущие
            url = f"{self.api_url}/weather"
            params = {
                'lat': self.lat,
                'lon': self.lon,
                'appid': self.api_key,
                'units': 'metric',
                'lang': 'ru'
            }
            
            response = requests.get(url, params=params, timeout=10)
            
            if response.status_code == 200:
                data = response.json()
                return {
                    'temperature': data.get('main', {}).get('temp'),
                    'humidity': data.get('main', {}).get('humidity'),
                    'pressure': data.get('main', {}).get('pressure'),
                    'description': data.get('weather', [{}])[0].get('description', ''),
                    'date': target_date
                }
            else:
                logger.warning(f"Ошибка API погоды: {response.status_code}")
                return None
                
        except Exception as e:
            logger.error(f"Ошибка при запросе к API погоды: {str(e)}")
            return None
    
    def correlate_weather_with_cases(self, tick_data, weather_data):
        """Корреляция данных о погоде с активностью клещей
        
        Args:
            tick_data: Список данных о клещах
            weather_data: Список данных о погоде
        
        Returns:
            dict: Словарь с корреляциями
        """
        # TODO: Реализовать корреляционный анализ
        # Можно использовать scipy.stats или numpy для расчета корреляции
        return {
            'temperature_correlation': 0.0,
            'humidity_correlation': 0.0,
            'notes': 'Корреляционный анализ не реализован'
        }

