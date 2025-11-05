"""Модуль для управления кэшированием с Redis"""
import redis
import json
import pickle
from datetime import timedelta
from logger_config import setup_logger
import os

logger = setup_logger()


class CacheManager:
    """Менеджер кэша с использованием Redis"""
    
    def __init__(self, redis_url=None):
        """Инициализация менеджера кэша"""
        if redis_url is None:
            redis_url = os.getenv('REDIS_URL', 'redis://localhost:6379/0')
        
        try:
            self.redis_client = redis.from_url(redis_url, decode_responses=False)
            self.redis_client.ping()
            self.enabled = True
            logger.info("Redis кэш подключен успешно")
        except Exception as e:
            logger.warning(f"Redis недоступен, кэширование отключено: {str(e)}")
            self.redis_client = None
            self.enabled = False
    
    def get(self, key):
        """Получение значения из кэша"""
        if not self.enabled:
            return None
        
        try:
            value = self.redis_client.get(key)
            if value:
                return pickle.loads(value)
            return None
        except Exception as e:
            logger.warning(f"Ошибка получения из кэша {key}: {str(e)}")
            return None
    
    def set(self, key, value, timeout=300):
        """Сохранение значения в кэш"""
        if not self.enabled:
            return False
        
        try:
            serialized = pickle.dumps(value)
            self.redis_client.setex(key, timeout, serialized)
            return True
        except Exception as e:
            logger.warning(f"Ошибка сохранения в кэш {key}: {str(e)}")
            return False
    
    def delete(self, key):
        """Удаление ключа из кэша"""
        if not self.enabled:
            return False
        
        try:
            self.redis_client.delete(key)
            return True
        except Exception as e:
            logger.warning(f"Ошибка удаления из кэша {key}: {str(e)}")
            return False
    
    def clear_pattern(self, pattern):
        """Очистка ключей по паттерну"""
        if not self.enabled:
            return False
        
        try:
            keys = self.redis_client.keys(pattern)
            if keys:
                self.redis_client.delete(*keys)
            return True
        except Exception as e:
            logger.warning(f"Ошибка очистки паттерна {pattern}: {str(e)}")
            return False
    
    def clear_all(self):
        """Очистка всего кэша"""
        if not self.enabled:
            return False
        
        try:
            self.redis_client.flushdb()
            return True
        except Exception as e:
            logger.warning(f"Ошибка очистки кэша: {str(e)}")
            return False

