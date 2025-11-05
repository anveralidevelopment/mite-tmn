"""Модуль для настройки логирования"""
import logging
import os
from logging.handlers import RotatingFileHandler
import json

def setup_logger(config_path=None):
    """Настройка логирования на основе конфигурации"""
    if config_path is None:
        # Определяем путь к config.json относительно текущего файла
        import os
        base_dir = os.path.dirname(os.path.dirname(__file__))
        config_path = os.path.join(base_dir, 'config', 'config.json')
    
    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            config = json.load(f)
    except FileNotFoundError:
        # Значения по умолчанию
        config = {
            "logging": {
                "enabled": True,
                "level": "INFO",
                "file": "logs/app.log",
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
    log_file = log_config.get('file', 'logs/app.log')
    # Убеждаемся что путь относительный от корня проекта
    if not os.path.isabs(log_file):
        base_dir = os.path.dirname(os.path.dirname(__file__))
        log_file = os.path.join(base_dir, log_file)
    # Создаем директорию для логов если её нет
    log_dir = os.path.dirname(log_file)
    if log_dir and not os.path.exists(log_dir):
        os.makedirs(log_dir, exist_ok=True)
    file_handler = RotatingFileHandler(
        log_file,
        maxBytes=log_config.get('max_bytes', 10485760),
        backupCount=log_config.get('backup_count', 5),
        encoding='utf-8'
    )
    file_handler.setLevel(logging.DEBUG)
    
    # Обработчик для консоли с правильной кодировкой для Windows
    import sys
    if sys.platform == 'win32':
        import codecs
        # Настраиваем кодировку консоли для Windows
        if hasattr(sys.stdout, 'reconfigure'):
            try:
                sys.stdout.reconfigure(encoding='utf-8')
                sys.stderr.reconfigure(encoding='utf-8')
            except:
                pass
    console_handler = logging.StreamHandler(sys.stdout)
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

