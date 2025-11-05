"""Модуль для отправки уведомлений"""
try:
    from flask_mail import Mail, Message
    FLASK_MAIL_AVAILABLE = True
except ImportError:
    FLASK_MAIL_AVAILABLE = False

try:
    from telegram import Bot
    from telegram.error import TelegramError
    TELEGRAM_AVAILABLE = True
except ImportError:
    TELEGRAM_AVAILABLE = False

import os
import json
from logger_config import setup_logger
from datetime import datetime, date

logger = setup_logger()


class NotificationManager:
    """Менеджер уведомлений (Email, Telegram)"""
    
    def __init__(self, app=None):
        """Инициализация менеджера уведомлений"""
        self.mail = None
        self.telegram_bot = None
        self.config = self._load_config()
        
        if app:
            self.init_app(app)
        
        self._init_telegram()
    
    def _load_config(self):
        """Загрузка конфигурации"""
        try:
            import os
            config_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'config', 'config.json')
            if os.path.exists(config_path):
                with open(config_path, 'r', encoding='utf-8') as f:
                    return json.load(f)
            return {}
        except Exception as e:
            logger.error(f"Ошибка загрузки конфигурации: {str(e)}")
            return {}
    
    def init_app(self, app):
        """Инициализация Flask-Mail"""
        if not FLASK_MAIL_AVAILABLE:
            logger.warning("Flask-Mail недоступен, email уведомления отключены")
            return
        
        mail_config = self.config.get('mail', {})
        if mail_config.get('enabled', False):
            app.config['MAIL_SERVER'] = mail_config.get('server', 'smtp.gmail.com')
            app.config['MAIL_PORT'] = mail_config.get('port', 587)
            app.config['MAIL_USE_TLS'] = mail_config.get('use_tls', True)
            app.config['MAIL_USERNAME'] = mail_config.get('username', '')
            app.config['MAIL_PASSWORD'] = mail_config.get('password', '')
            app.config['MAIL_DEFAULT_SENDER'] = mail_config.get('from', '')
            
            self.mail = Mail(app)
            logger.info("Flask-Mail инициализирован")
    
    def _init_telegram(self):
        """Инициализация Telegram бота"""
        if not TELEGRAM_AVAILABLE:
            logger.warning("python-telegram-bot недоступен, Telegram уведомления отключены")
            return
        
        telegram_config = self.config.get('telegram', {}).get('bot', {})
        if telegram_config.get('enabled', False):
            token = telegram_config.get('token', os.getenv('TELEGRAM_BOT_TOKEN', ''))
            if token:
                try:
                    self.telegram_bot = Bot(token=token)
                    logger.info("Telegram бот инициализирован")
                except Exception as e:
                    logger.warning(f"Ошибка инициализации Telegram бота: {str(e)}")
    
    def send_email(self, subject, recipients, body, html=None):
        """Отправка email уведомления"""
        if not self.mail:
            logger.warning("Email не настроен")
            return False
        
        try:
            msg = Message(
                subject=subject,
                recipients=recipients,
                body=body,
                html=html
            )
            self.mail.send(msg)
            logger.info(f"Email отправлен: {subject} -> {recipients}")
            return True
        except Exception as e:
            logger.error(f"Ошибка отправки email: {str(e)}")
            return False
    
    def send_telegram(self, chat_id, message, parse_mode='HTML'):
        """Отправка Telegram уведомления"""
        if not self.telegram_bot:
            logger.warning("Telegram бот не настроен")
            return False
        
        try:
            self.telegram_bot.send_message(
                chat_id=chat_id,
                text=message,
                parse_mode=parse_mode
            )
            logger.info(f"Telegram сообщение отправлено в {chat_id}")
            return True
        except TelegramError as e:
            logger.error(f"Ошибка отправки Telegram: {str(e)}")
            return False
    
    def notify_spike(self, location, cases, date, previous_cases=0):
        """Уведомление о всплеске активности"""
        increase = ((cases - previous_cases) / previous_cases * 100) if previous_cases > 0 else 0
        
        subject = f"⚠️ Всплеск активности клещей в {location}"
        message = f"""
⚠️ <b>Всплеск активности клещей</b>

📍 <b>Локация:</b> {location}
📊 <b>Случаев:</b> {cases}
📈 <b>Рост:</b> +{increase:.1f}% (было {previous_cases})
📅 <b>Дата:</b> {date.strftime('%d.%m.%Y') if isinstance(date, date) else date}

⚠️ Рекомендуется соблюдать меры предосторожности!
        """.strip()
        
        # Email
        email_config = self.config.get('mail', {})
        if email_config.get('enabled', False):
            recipients = email_config.get('recipients', [])
            if recipients:
                self.send_email(
                    subject=subject,
                    recipients=recipients,
                    body=message.replace('<b>', '').replace('</b>', ''),
                    html=f"<html><body><pre>{message}</pre></body></html>"
                )
        
        # Telegram
        telegram_config = self.config.get('telegram', {}).get('bot', {})
        if telegram_config.get('enabled', False):
            chat_ids = telegram_config.get('chat_ids', [])
            for chat_id in chat_ids:
                self.send_telegram(chat_id, message)
        
        return True
    
    def notify_high_activity(self, location, cases, date):
        """Уведомление о высокой активности"""
        subject = f"🔴 Высокая активность клещей в {location}"
        message = f"""
🔴 <b>Высокая активность клещей</b>

📍 <b>Локация:</b> {location}
📊 <b>Случаев:</b> {cases}
📅 <b>Дата:</b> {date.strftime('%d.%m.%Y') if isinstance(date, date) else date}

⚠️ Будьте осторожны при выходе на природу!
        """.strip()
        
        # Email
        email_config = self.config.get('mail', {})
        if email_config.get('enabled', False):
            recipients = email_config.get('recipients', [])
            if recipients:
                self.send_email(
                    subject=subject,
                    recipients=recipients,
                    body=message.replace('<b>', '').replace('</b>', ''),
                    html=f"<html><body><pre>{message}</pre></body></html>"
                )
        
        # Telegram
        telegram_config = self.config.get('telegram', {}).get('bot', {})
        if telegram_config.get('enabled', False):
            chat_ids = telegram_config.get('chat_ids', [])
            for chat_id in chat_ids:
                self.send_telegram(chat_id, message)
        
        return True

