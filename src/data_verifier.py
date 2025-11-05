"""Модуль для верификации и проверки дубликатов данных"""
from datetime import date, timedelta
from logger_config import setup_logger
import hashlib
import json

logger = setup_logger()


class DataVerifier:
    """Класс для верификации данных и проверки дубликатов"""
    
    def __init__(self, db):
        self.db = db
        self.seen_hashes = set()
    
    def calculate_data_hash(self, data_item):
        """Вычисляет хеш для проверки дубликатов
        
        Args:
            data_item: Словарь с данными
        
        Returns:
            str: MD5 хеш данных
        """
        # Создаем строку для хеширования из ключевых полей
        key_fields = {
            'date': str(data_item.get('date', '')),
            'title': data_item.get('title', '').lower().strip()[:200],
            'source': data_item.get('source', ''),
            'url': data_item.get('url', '')
        }
        
        # Сортируем для консистентности
        key_string = json.dumps(key_fields, sort_keys=True, ensure_ascii=False)
        return hashlib.md5(key_string.encode('utf-8')).hexdigest()
    
    def is_duplicate(self, data_item):
        """Проверяет, является ли запись дубликатом
        
        Args:
            data_item: Словарь с данными
        
        Returns:
            tuple: (is_duplicate: bool, existing_record: dict or None)
        """
        try:
            # Проверяем по хешу
            data_hash = self.calculate_data_hash(data_item)
            if data_hash in self.seen_hashes:
                return True, None
            
            # Проверяем в БД по URL
            url = data_item.get('url')
            if url:
                existing = self.db.get_tick_data_by_url(url)
                if existing:
                    self.seen_hashes.add(data_hash)
                    return True, existing
            
            # Проверяем по дате, источнику и заголовку
            item_date = data_item.get('date')
            source = data_item.get('source', '')
            title = data_item.get('title', '').strip()
            
            if item_date and source and title:
                # Ищем похожие записи за последние 7 дней
                start_date = item_date - timedelta(days=7)
                all_data = self.db.get_filtered_data(start_date, item_date)
                
                for existing_item in all_data:
                    if (existing_item.get('source') == source and
                        existing_item.get('title', '').strip().lower() == title.lower() and
                        abs((existing_item.get('date') - item_date).days) <= 1):
                        self.seen_hashes.add(data_hash)
                        return True, existing_item
            
            # Не дубликат
            self.seen_hashes.add(data_hash)
            return False, None
            
        except Exception as e:
            logger.warning(f"Ошибка проверки дубликата: {str(e)}")
            return False, None
    
    def _is_tick_season(self, item_date):
        """Проверка, является ли дата сезоном активности клещей
        
        Клещи активны с конца апреля (примерно с 20 числа) по начало октября (до первых заморозков)
        В Тюменской области это примерно: 20 апреля - 10 октября
        
        Args:
            item_date: date object
        
        Returns:
            bool: True если это сезон активности клещей
        """
        if not item_date or not isinstance(item_date, date):
            return False
        
        month = item_date.month
        
        # Май, июнь, июль, август, сентябрь - точно сезон
        if month in [5, 6, 7, 8, 9]:
            return True
        
        # Апрель - с 20 числа
        if month == 4:
            return item_date.day >= 20
        
        # Октябрь - до 10 числа
        if month == 10:
            return item_date.day <= 10
        
        # Ноябрь, декабрь, январь, февраль, март - не сезон
        return False
    
    def verify_data_quality(self, data_item):
        """Проверяет качество данных
        
        Args:
            data_item: Словарь с данными
        
        Returns:
            tuple: (is_valid: bool, issues: list)
        """
        issues = []
        
        # Проверка обязательных полей
        required_fields = ['date', 'cases', 'source']
        for field in required_fields:
            if field not in data_item or data_item[field] is None:
                issues.append(f"Отсутствует обязательное поле: {field}")
        
        # Проверка типов
        if 'date' in data_item and not isinstance(data_item['date'], date):
            issues.append("Неверный тип поля date")
        
        if 'cases' in data_item:
            if not isinstance(data_item['cases'], int):
                issues.append("Неверный тип поля cases")
            elif data_item['cases'] < 0:
                issues.append("Отрицательное значение cases")
            elif data_item['cases'] > 10000:
                issues.append("Неправдоподобно большое значение cases")
        
        # Проверка даты
        if 'date' in data_item and isinstance(data_item['date'], date):
            today = date.today()
            if data_item['date'] > today:
                issues.append("Дата в будущем")
            elif data_item['date'] < date(2020, 1, 1):
                issues.append("Дата слишком старая")
            
            # Проверка сезонности клещей (только если есть случаи укусов)
            if data_item.get('cases', 0) > 0:
                if not self._is_tick_season(data_item['date']):
                    issues.append(
                        f"Дата {data_item['date']} вне сезона активности клещей "
                        f"(20 апреля - 10 октября)"
                    )
        
        # Проверка источника
        if 'source' in data_item:
            source = data_item['source']
            if not source or len(source) > 200:
                issues.append("Неверный формат source")
        
        # Проверка URL
        if 'url' in data_item and data_item.get('url'):
            url = data_item['url']
            if not url.startswith(('http://', 'https://')):
                issues.append("Неверный формат URL")
        
        return len(issues) == 0, issues
    
    def clear_cache(self):
        """Очищает кэш хешей"""
        self.seen_hashes.clear()

