"""Модуль для парсинга данных из VK"""
import requests
from bs4 import BeautifulSoup
from fake_useragent import UserAgent
import re
from datetime import datetime, date
from dateutil import parser as date_parser
from logger_config import setup_logger
import time

logger = setup_logger()


class VKParser:
    """Класс для парсинга данных из VK"""
    
    def __init__(self, config, logger_instance=None):
        self.config = config
        self.logger = logger_instance or logger
        self.vk_token = None  # Для будущего использования VK API
    
    def parse_vk_group(self, group_url, max_items=20):
        """Парсинг публичной группы VK через веб-интерфейс
        
        Args:
            group_url: URL группы VK
            max_items: Максимальное количество постов
        
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
            
            self.logger.info(f"Парсинг VK группы: {group_url}")
            
            # Пробуем разные варианты URL
            vk_urls = [
                group_url,
                group_url.replace('vk.com/', 'vk.com/wall-'),
                f"{group_url}?w=wall-",
            ]
            
            response = None
            for vk_url in vk_urls:
                try:
                    response = requests.get(vk_url, headers=headers, timeout=15)
                    if response.status_code == 200 and 'клещ' in response.text.lower():
                        break
                except:
                    continue
            
            if not response or response.status_code != 200:
                self.logger.warning("Не удалось получить доступ к VK группе")
                return []
            
            soup = BeautifulSoup(response.text, 'html.parser')
            results = []
            
            # Ищем посты в VK (структура может отличаться)
            posts = soup.find_all('div', class_=re.compile(r'post|wall_item|post_content', re.I))
            if not posts:
                # Альтернативный поиск
                posts = soup.find_all('div', attrs={'data-post-id': True})
            
            posts = posts[:max_items]
            
            for post in posts:
                try:
                    # Извлекаем текст поста
                    text_elem = post.find('div', class_=re.compile(r'text|post_text|wall_post_text', re.I))
                    if not text_elem:
                        text_elem = post.find('div', class_='wall_post_text')
                    
                    if not text_elem:
                        continue
                    
                    text = text_elem.get_text('\n', strip=True)
                    
                    # Проверяем наличие ключевых слов
                    if not any(word in text.lower() for word in ['клещ', 'укус', 'энцефалит', 'присасыван']):
                        continue
                    
                    # Извлекаем дату
                    date_elem = post.find('time') or post.find('span', class_=re.compile(r'date|time', re.I))
                    item_date = None
                    
                    if date_elem:
                        if date_elem.has_attr('datetime'):
                            try:
                                item_date = date_parser.parse(date_elem['datetime']).date()
                            except:
                                pass
                        
                        if not item_date:
                            date_text = date_elem.get_text(strip=True)
                            # Пробуем распарсить дату из текста
                            try:
                                item_date = date_parser.parse(date_text, fuzzy=True, dayfirst=True).date()
                            except:
                                pass
                    
                    if not item_date:
                        item_date = date.today()
                    
                    # Извлекаем количество случаев
                    cases_match = re.search(r'(\d+)\s*(?:укус|случа|обращ|клещ)', text, re.IGNORECASE)
                    cases = int(cases_match.group(1)) if cases_match else 0
                    
                    # Извлекаем локацию
                    location_match = re.search(r'(Тюмень|Тобольск|Ишим|Ялуторовск|Армизон|район)', text, re.IGNORECASE)
                    location = location_match.group(1) if location_match else None
                    
                    # Извлекаем ссылку на пост
                    link_elem = post.find('a', href=re.compile(r'/wall-|post_id'))
                    url = link_elem.get('href', '') if link_elem else group_url
                    if url and not url.startswith('http'):
                        url = 'https://vk.com' + url
                    
                    results.append({
                        'date': item_date,
                        'cases': cases,
                        'title': text[:100] + "..." if len(text) > 100 else text or "Без заголовка",
                        'content': text[:500] if len(text) > 500 else text,
                        'url': url,
                        'source': 'VK (Тюмень)',
                        'location': location
                    })
                    
                except Exception as e:
                    self.logger.debug(f"Ошибка обработки VK поста: {str(e)}")
                    continue
            
            self.logger.info(f"Получено {len(results)} записей из VK")
            return results
            
        except Exception as e:
            self.logger.error(f"Ошибка при парсинге VK: {str(e)}")
            return []

