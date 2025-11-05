"""Модуль для парсинга местных новостных сайтов"""
import requests
from bs4 import BeautifulSoup
from fake_useragent import UserAgent
import re
from datetime import datetime, date
from logger_config import setup_logger
import time

logger = setup_logger()


class LocalNewsParser:
    """Класс для парсинга местных новостных сайтов"""
    
    def __init__(self, config, logger_instance=None):
        self.config = config
        self.logger = logger_instance or logger
    
    def parse_local_news_site(self, base_url, search_query="клещ", max_items=30):
        """Парсинг местного новостного сайта
        
        Args:
            base_url: Базовый URL сайта
            search_query: Поисковый запрос
            max_items: Максимальное количество статей
        
        Returns:
            list: Список словарей с данными
        """
        try:
            ua = UserAgent()
            headers = {
                'User-Agent': ua.random,
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
                'Accept-Language': 'ru-RU,ru;q=0.8,en-US;q=0.5,en;q=0.3',
            }
            
            self.logger.info(f"Парсинг местного новостного сайта: {base_url}")
            
            # Пробуем разные варианты поиска
            search_urls = [
                f"{base_url}/search?q={search_query}",
                f"{base_url}/search/?query={search_query}",
                f"{base_url}/news/?search={search_query}",
                f"{base_url}/?s={search_query}",
            ]
            
            response = None
            for search_url in search_urls:
                try:
                    response = requests.get(search_url, headers=headers, timeout=15)
                    if response.status_code == 200:
                        break
                except:
                    continue
            
            if not response or response.status_code != 200:
                # Пробуем главную страницу
                try:
                    response = requests.get(base_url, headers=headers, timeout=15)
                except:
                    self.logger.warning(f"Не удалось получить доступ к {base_url}")
                    return []
            
            if response.status_code != 200:
                return []
            
            soup = BeautifulSoup(response.text, 'html.parser')
            results = []
            
            # Ищем статьи
            articles = soup.find_all(['article', 'div'], class_=re.compile(r'article|news|item|post', re.I))
            if not articles:
                articles = soup.find_all('div', class_='content')[:max_items]
            
            articles = articles[:max_items]
            
            for article in articles:
                try:
                    # Извлекаем заголовок
                    title_elem = article.find(['h1', 'h2', 'h3', 'a'], class_=re.compile(r'title|heading', re.I))
                    if not title_elem:
                        title_elem = article.find(['h1', 'h2', 'h3'])
                    
                    if not title_elem:
                        continue
                    
                    title = title_elem.get_text(strip=True)
                    
                    # Проверяем наличие ключевых слов
                    if not any(word in title.lower() for word in ['клещ', 'укус', 'энцефалит']):
                        continue
                    
                    # Извлекаем дату
                    date_elem = article.find(['time', 'span'], class_=re.compile(r'date|time', re.I))
                    date_text = date_elem.get_text(strip=True) if date_elem else ""
                    
                    if date_elem and date_elem.has_attr('datetime'):
                        date_text = date_elem.get('datetime', '')
                    
                    # Извлекаем содержимое
                    content_elem = article.find(['div', 'p'], class_=re.compile(r'content|text|excerpt', re.I))
                    content = content_elem.get_text(strip=True) if content_elem else ""
                    
                    # Извлекаем ссылку
                    link_elem = article.find('a', href=True)
                    url = link_elem.get('href', '') if link_elem else ""
                    if url and not url.startswith('http'):
                        url = base_url.rstrip('/') + '/' + url.lstrip('/')
                    
                    # Парсим дату (используем базовый парсер)
                    # Для этого нужно будет интегрировать с основным парсером
                    item_date = None
                    if date_text:
                        try:
                            from dateutil import parser as date_parser
                            item_date = date_parser.parse(date_text, fuzzy=True, dayfirst=True).date()
                        except:
                            pass
                    
                    if not item_date:
                        item_date = date.today()
                    
                    # Извлекаем количество случаев
                    text = title + " " + content
                    cases_match = re.search(r'(\d+)\s*(?:укус|случа|обращ|клещ)', text, re.IGNORECASE)
                    cases = int(cases_match.group(1)) if cases_match else 0
                    
                    # Извлекаем локацию
                    location_match = re.search(r'(Тюмень|Тобольск|Ишим|Ялуторовск|Армизон|район)', text, re.IGNORECASE)
                    location = location_match.group(1) if location_match else None
                    
                    results.append({
                        'date': item_date,
                        'cases': cases,
                        'title': title[:200] if len(title) > 200 else title,
                        'content': content[:500] if len(content) > 500 else content,
                        'url': url,
                        'source': f'Местные новости ({base_url})',
                        'location': location
                    })
                    
                except Exception as e:
                    self.logger.debug(f"Ошибка обработки статьи: {str(e)}")
                    continue
            
            self.logger.info(f"Получено {len(results)} записей с {base_url}")
            return results
            
        except Exception as e:
            self.logger.error(f"Ошибка при парсинге {base_url}: {str(e)}")
            return []

