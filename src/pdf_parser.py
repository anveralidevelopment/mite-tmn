"""Модуль для парсинга PDF документов"""
import requests
from io import BytesIO
from logger_config import setup_logger
import re
from datetime import date
from dateutil import parser as date_parser

logger = setup_logger()

try:
    import PyPDF2
    PDF_AVAILABLE = True
except ImportError:
    PDF_AVAILABLE = False
    logger.warning("PyPDF2 не установлен, парсинг PDF отключен")

try:
    import pytesseract
    from PIL import Image
    OCR_AVAILABLE = True
except ImportError:
    OCR_AVAILABLE = False
    logger.debug("pytesseract/PIL не установлены, OCR отключен")


class PDFParser:
    """Класс для парсинга PDF документов"""
    
    def __init__(self, logger_instance=None):
        self.logger = logger_instance or logger
    
    def parse_pdf_url(self, pdf_url):
        """Парсинг PDF по URL
        
        Args:
            pdf_url: URL PDF файла
        
        Returns:
            dict: Словарь с данными или None
        """
        if not PDF_AVAILABLE:
            self.logger.warning("PyPDF2 недоступен, парсинг PDF невозможен")
            return None
        
        try:
            # Скачиваем PDF
            response = requests.get(pdf_url, timeout=30)
            if response.status_code != 200:
                return None
            
            pdf_file = BytesIO(response.content)
            pdf_reader = PyPDF2.PdfReader(pdf_file)
            
            # Извлекаем текст из всех страниц
            text = ""
            for page in pdf_reader.pages:
                text += page.extract_text() + "\n"
            
            if not text or len(text) < 50:
                return None
            
            # Проверяем наличие ключевых слов
            if not any(word in text.lower() for word in ['клещ', 'укус', 'энцефалит', 'присасыван']):
                return None
            
            # Извлекаем дату
            date_patterns = [
                r'\d{2}\.\d{2}\.\d{4}',
                r'\d{4}-\d{2}-\d{2}',
                r'\d{1,2}\s+(января|февраля|марта|апреля|мая|июня|июля|августа|сентября|октября|ноября|декабря)\s+\d{4}'
            ]
            
            item_date = None
            for pattern in date_patterns:
                match = re.search(pattern, text, re.IGNORECASE)
                if match:
                    try:
                        item_date = date_parser.parse(match.group(), fuzzy=True, dayfirst=True).date()
                        break
                    except:
                        continue
            
            if not item_date:
                item_date = date.today()
            
            # Извлекаем количество случаев
            cases_match = re.search(r'(\d+)\s*(?:укус|случа|обращ|клещ)', text, re.IGNORECASE)
            cases = int(cases_match.group(1)) if cases_match else 0
            
            # Извлекаем локацию
            location_match = re.search(r'(Тюмень|Тобольск|Ишим|Ялуторовск|Армизон|район)', text, re.IGNORECASE)
            location = location_match.group(1) if location_match else None
            
            # Извлекаем заголовок (первые строки)
            lines = text.split('\n')
            title = lines[0][:200] if lines else "PDF документ"
            
            return {
                'date': item_date,
                'cases': cases,
                'title': title,
                'content': text[:2000] if len(text) > 2000 else text,
                'url': pdf_url,
                'source': 'PDF документ',
                'location': location
            }
            
        except Exception as e:
            self.logger.error(f"Ошибка парсинга PDF {pdf_url}: {str(e)}")
            return None
    
    def parse_pdf_from_image(self, image_url):
        """Парсинг PDF с изображениями через OCR
        
        Args:
            image_url: URL изображения
        
        Returns:
            dict: Словарь с данными или None
        """
        if not OCR_AVAILABLE:
            self.logger.warning("OCR недоступен, парсинг изображений невозможен")
            return None
        
        try:
            # Скачиваем изображение
            response = requests.get(image_url, timeout=30)
            if response.status_code != 200:
                return None
            
            image = Image.open(BytesIO(response.content))
            
            # Извлекаем текст через OCR
            text = pytesseract.image_to_string(image, lang='rus+eng')
            
            if not text or len(text) < 50:
                return None
            
            # Аналогично parse_pdf_url обрабатываем текст
            # (можно вынести общую логику)
            
            return None  # TODO: Реализовать обработку OCR текста
            
        except Exception as e:
            self.logger.error(f"Ошибка OCR {image_url}: {str(e)}")
            return None

