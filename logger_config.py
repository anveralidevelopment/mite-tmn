"""Модуль для настройки логирования"""
import logging
import os
from logging.handlers import RotatingFileHandler
import json

def setup_logger(config_path='config.json'):
    """Настройка логирования на основе конфигурации"""
    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            config = json.load(f)
    except FileNotFoundError:
        # Значения по умолчанию
        config = {
            "logging": {
                "enabled": True,
                "level": "INFO",
                "file": "app.log",
                "max_bytes": 10485760,
                "backup_count": 5
            }
        }
    
    log_config = config.get('logging', {})
    
    if not log_config.get('enabled', True):
        logging.basicConfig(level=logging.WARNING)
        return logging.getLogger('mite_tmn')
    
    logger = logging.getLogger('mite_tmn')
    logger.setLevel(getattr(logging, log_config.get('level', 'INFO')))
    
    # Обработчик для файла
    log_file = log_config.get('file', 'app.log')
    file_handler = RotatingFileHandler(
        log_file,
        maxBytes=log_config.get('max_bytes', 10485760),
        backupCount=log_config.get('backup_count', 5),
        encoding='utf-8'
    )
    file_handler.setLevel(logging.DEBUG)
    
    # Обработчик для консоли
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    
    # Формат логов
    formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    file_handler.setFormatter(formatter)
    console_handler.setFormatter(formatter)
    
    logger.addHandler(file_handler)
    logger.addHandler(console_handler)
    
    return logger

