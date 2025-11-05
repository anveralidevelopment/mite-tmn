"""Модуль для парсинга данных о клещах"""
import requests
from bs4 import BeautifulSoup
import feedparser
import re
from datetime import datetime, date
from dateutil import parser as date_parser
from fake_useragent import UserAgent
import time

class TickParser:
    """Класс для парсинга данных о клещах"""
    
    def __init__(self, db, logger):
        self.db = db
        self.logger = logger
        
        # Загружаем конфигурацию
        self.config = self._load_config()
    
    def _load_config(self):
        """Загрузка конфигурации"""
        try:
            import json
            import os
            config_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'config', 'config.json')
            if os.path.exists(config_path):
                with open(config_path, 'r', encoding='utf-8') as f:
                    return json.load(f)
            return {}
        except Exception as e:
            self.logger.error(f"Ошибка загрузки конфигурации: {str(e)}")
            return {}
    
    def make_request_with_retry(self, url, headers, max_retries=3, delay=2):
        """Выполнение HTTP запроса с повторами"""
        parsing_config = self.config.get('parsing', {})
        max_retries = parsing_config.get('retry_count', max_retries)
        delay = parsing_config.get('retry_delay', delay)
        timeout = parsing_config.get('timeout', 15)
        
        for attempt in range(max_retries):
            try:
                response = requests.get(url, headers=headers, timeout=timeout)
                response.raise_for_status()
                return response
            except requests.exceptions.RequestException as e:
                self.logger.warning(f"Попытка {attempt + 1}/{max_retries} не удалась: {str(e)}")
                if attempt < max_retries - 1:
                    time.sleep(delay)
                else:
                    return None
        return None
    
    def parse_web_data(self):
        """Парсинг данных с веб-сайта"""
        try:
            ua = UserAgent()
            headers = {
                'User-Agent': ua.random,
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
                'Accept-Language': 'ru-RU,ru;q=0.8,en-US;q=0.5,en;q=0.3',
            }
            
            web_config = self.config.get('parsing', {}).get('sources', {}).get('web', {})
            base_url = web_config.get('base_url', 'https://72.rospotrebnadzor.ru')
            max_items = web_config.get('max_items', 100)
            
            # Пробуем разные варианты URL для поиска
            search_urls = [
                f"{base_url}/search/?q=%D0%BA%D0%BB%D0%B5%D1%89%D0%B8",  # Основной поиск
                f"{base_url}/search/?q=%D0%BA%D0%BB%D0%B5%D1%89",  # Альтернативный поиск
                f"{base_url}/search/",  # Общая страница поиска
                f"{base_url}/news/",  # Страница новостей
                f"{base_url}/press/",  # Пресс-релизы
                f"{base_url}/",  # Главная страница
                f"{base_url}/category/news/",  # Категория новостей
            ]
            
            response = None
            for search_url in search_urls:
                self.logger.info(f"Попытка парсинга веб-сайта: {search_url}")
                response = self.make_request_with_retry(search_url, headers)
                if response and response.status_code == 200:
                    self.logger.info(f"Успешно получен доступ к: {search_url}")
                    break
                else:
                    self.logger.debug(f"Не удалось получить доступ к: {search_url}")
            
            if not response or response.status_code != 200:
                self.logger.warning("Не удалось получить доступ ни к одному URL веб-сайта Роспотребнадзора")
                return []
            
            soup = BeautifulSoup(response.text, 'html.parser')
            results = []
            
            news_items = soup.find_all('div', class_='search-item')
            if not news_items:
                news_items = soup.find_all('div', class_='news-item')
            if not news_items:
                news_items = soup.find_all('article')
            
            news_items = news_items[:max_items]
            
            for item in news_items:
                try:
                    title_elem = item.find('a', class_='search-title') or item.find('a', class_='title') or item.find('h3') or item.find('h2') or item.find('a')
                    if not title_elem:
                        continue
                    title = title_elem.text.strip() if title_elem else ""
                    
                    date_elem = item.find('div', class_='search-date') or item.find('div', class_='date') or item.find('time')
                    date_text = date_elem.text.strip() if date_elem else ""
                    
                    content_elem = item.find('div', class_='search-text') or item.find('div', class_='content') or item.find('p')
                    content = content_elem.text.strip() if content_elem else ""
                    
                    date_match = re.search(r'\d{2}\.\d{2}\.\d{4}', date_text)
                    if not date_match:
                        date_match = re.search(r'\d{4}-\d{2}-\d{2}', date_text)
                        if date_match:
                            item_date = datetime.strptime(date_match.group(), '%Y-%m-%d').date()
                        else:
                            continue
                    else:
                        item_date = datetime.strptime(date_match.group(), '%d.%m.%Y').date()
                    
                    cases = self.extract_case_number(title + " " + content)
                    if not cases and any(word in (title + " " + content).lower() for word in ['клещ', 'укус', 'энцефалит', 'присасыван']):
                        cases = 0
                    
                    link_elem = item.find('a')
                    url = base_url + link_elem['href'] if link_elem and link_elem.get('href') else ""
                    
                    if title or content:
                        location = self.extract_location(title + " " + content)
                        results.append({
                            'date': item_date,
                            'cases': cases,
                            'title': title[:100] if title else "Без заголовка",
                            'content': content[:200] + "..." if len(content) > 200 else content,
                            'url': url,
                            'source': 'Роспотребнадзор (веб)',
                            'location': location
                        })
                except Exception as e:
                    self.logger.debug(f"Ошибка обработки новости: {str(e)}")
                    continue
            
            self.logger.info(f"Получено {len(results)} записей с веб-сайта")
            return results
        except Exception as e:
            self.logger.error(f"Ошибка при парсинге веб-сайта: {str(e)}")
            return []
    
    def parse_rss_feed(self):
        """Парсинг RSS-ленты"""
        try:
            web_config = self.config.get('parsing', {}).get('sources', {}).get('web', {})
            rss_url = web_config.get('rss_url', 'https://72.rospotrebnadzor.ru/rss/')
            max_items = web_config.get('max_items', 100)
            
            self.logger.info(f"Парсинг RSS-ленты: {rss_url}")
            feed = feedparser.parse(rss_url)
            results = []
            
            for entry in feed.entries[:max_items]:
                try:
                    if hasattr(entry, 'published_parsed') and entry.published_parsed:
                        entry_date = datetime(*entry.published_parsed[:6]).date()
                    else:
                        try:
                            entry_date = date_parser.parse(entry.get('published', '')).date()
                        except:
                            entry_date = datetime.now().date()
                    
                    title = entry.get('title', '')
                    description = entry.get('description', '')
                    text = (title + " " + description).lower()
                    
                    if any(word in text for word in ['клещ', 'укус', 'энцефалит', 'присасыван']):
                        cases = self.extract_case_number(title + " " + description)
                        if not cases:
                            cases = 0
                        
                        location = self.extract_location(title + " " + description)
                        results.append({
                            'date': entry_date,
                            'cases': cases,
                            'title': title[:100] if title else "Без заголовка",
                            'content': description[:200] + "..." if len(description) > 200 else description,
                            'url': entry.get('link', ''),
                            'source': 'Роспотребнадзор (RSS)',
                            'location': location
                        })
                except Exception as e:
                    self.logger.debug(f"Ошибка обработки RSS-записи: {str(e)}")
                    continue
            
            self.logger.info(f"Получено {len(results)} записей из RSS")
            return results
        except Exception as e:
            self.logger.error(f"Ошибка при парсинге RSS: {str(e)}")
            return []
    
    def parse_telegram(self):
        """Парсинг данных из Telegram-канала"""
        try:
            telegram_config = self.config.get('parsing', {}).get('sources', {}).get('telegram', {})
            url = telegram_config.get('url', 'https://t.me/s/tu_ymen72')
            max_items = telegram_config.get('max_items', 50)
            
            ua = UserAgent()
            headers = {
                'User-Agent': ua.random,
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
                'Accept-Language': 'ru-RU,ru;q=0.8,en-US;q=0.5,en;q=0.3',
            }
            
            self.logger.info(f"Парсинг Telegram: {url}")
            response = self.make_request_with_retry(url, headers)
            
            if not response:
                return []
            
            soup = BeautifulSoup(response.text, 'html.parser')
            results = []
            
            messages = soup.find_all('div', class_='tgme_widget_message')
            
            for message in messages[:max_items]:
                try:
                    if not message.find('div', class_='tgme_widget_message_text'):
                        continue
                    
                    text = message.find('div', class_='tgme_widget_message_text').get_text('\n', strip=True)
                    
                    if not any(word in text.lower() for word in ['клещ', 'укус', 'энцефалит', 'присасыван']):
                        continue
                    
                    time_tag = message.find('time', class_='time')
                    if not time_tag or not time_tag.has_attr('datetime'):
                        continue
                    
                    message_date = date_parser.parse(time_tag['datetime']).date()
                    cases = self.extract_case_number(text)
                    if not cases:
                        cases = 0
                    
                    location = self.extract_location(text)
                    results.append({
                        'date': message_date,
                        'cases': cases,
                        'title': text[:100] + "..." if len(text) > 100 else text or "Без заголовка",
                        'content': text[:200] + "..." if len(text) > 200 else text,
                        'url': url,
                        'source': 'Telegram (Тюмень 72)',
                        'location': location
                    })
                except Exception as e:
                    self.logger.debug(f"Ошибка обработки сообщения Telegram: {str(e)}")
                    continue
            
            self.logger.info(f"Получено {len(results)} записей из Telegram")
            return results
        except Exception as e:
            self.logger.error(f"Ошибка при парсинге Telegram: {str(e)}")
            return []
    
    def extract_location(self, text):
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

    def extract_case_number(self, text):
        """Извлекает количество случаев из текста"""
        patterns = [
            r'зарегистрировано\D*(\d+)\D*обращ',
            r'выявлено\D*(\d+)\D*случа',
            r'(\d+)\D*укус',
            r'клещ\D*(\d+)',
            r'(\d+)\s*(?:случа[ея]в|обращени[ий])',
            r'(\d+)\s*(?:человек|жител[ей])',
            r'обратилось\D*(\d+)',
            r'поступило\D*(\d+)\D*обращ',
            r'(\d+)\D*пострадал',
            r'(\d+)\D*присасыван'
        ]
        
        # Сначала ищем точные совпадения
        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                try:
                    num = int(match.group(1))
                    # Проверяем что число разумное (не больше 10000)
                    if 0 < num <= 10000:
                        return num
                except ValueError:
                    continue
        
        # Ищем числа рядом с ключевыми словами
        keywords = ['клещ', 'укус', 'обращение', 'случай', 'присасывание']
        for keyword in keywords:
            pattern = rf'{keyword}[^\d]*(\d{{1,4}})'
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                try:
                    num = int(match.group(1))
                    if 0 < num <= 10000:
                        return num
                except ValueError:
                    continue
        
        return 0
    
    def calculate_risk_level(self, cases):
        """Определение уровня риска"""
        if not isinstance(cases, int) or cases == 0:
            return "Нет данных"
        
        risk_config = self.config.get('risk_levels', {})
        thresholds = {
            'low': risk_config.get('low', {}).get('threshold', 50),
            'moderate': risk_config.get('moderate', {}).get('threshold', 100),
            'high': risk_config.get('high', {}).get('threshold', 150),
            'very_high': risk_config.get('very_high', {}).get('threshold', 999999)
        }
        
        if cases < thresholds['low']:
            return "Низкий"
        elif cases < thresholds['moderate']:
            return "Умеренный"
        elif cases < thresholds['high']:
            return "Высокий"
        else:
            return "Очень высокий"
    
    def parse_rospotrebnadzor_news(self):
        """Парсинг новостей с сайта Роспотребнадзора"""
        try:
            ua = UserAgent()
            headers = {
                'User-Agent': ua.random,
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
                'Accept-Language': 'ru-RU,ru;q=0.8,en-US;q=0.5,en;q=0.3',
            }
            
            web_config = self.config.get('parsing', {}).get('sources', {}).get('rospotrebnadzor_news', {})
            base_url = web_config.get('base_url', 'https://72.rospotrebnadzor.ru')
            max_items = web_config.get('max_items', 50)
            
            # Пробуем разные варианты URL для новостей
            news_urls = [
                f"{base_url}/news/",  # Страница новостей
                f"{base_url}/news",  # Без слэша
                f"{base_url}/press/",  # Пресс-релизы
                f"{base_url}/press",  # Без слэша
                f"{base_url}/category/news/",  # Категория новостей
                f"{base_url}/category/press/",  # Категория прессы
                f"{base_url}/announcements/",  # Анонсы
                f"{base_url}/",  # Главная страница
                f"{base_url}/search/?q=%D0%BA%D0%BB%D0%B5%D1%89%D0%B8",  # Поиск по клещам
                f"{base_url}/search/?q=%D0%BA%D0%BB%D0%B5%D1%89",  # Альтернативный поиск
            ]
            
            response = None
            for news_url in news_urls:
                self.logger.info(f"Попытка парсинга новостей Роспотребнадзора: {news_url}")
                response = self.make_request_with_retry(news_url, headers)
                if response and response.status_code == 200:
                    # Проверяем, что страница содержит релевантный контент
                    if 'клещ' in response.text.lower() or len(response.text) > 1000:
                        self.logger.info(f"Успешно получен доступ к новостям: {news_url}")
                        break
                    else:
                        self.logger.debug(f"Страница доступна, но не содержит релевантного контента: {news_url}")
            
            if not response or response.status_code != 200:
                self.logger.warning("Не удалось получить доступ к новостям Роспотребнадзора")
                return []
            
            soup = BeautifulSoup(response.text, 'html.parser')
            results = []
            
            news_items = soup.find_all(['article', 'div'], class_=['news-item', 'article-item', 'item'])
            if not news_items:
                news_items = soup.find_all('div', class_='content')[:max_items]
            
            news_items = news_items[:max_items]
            
            for item in news_items:
                try:
                    title_elem = item.find(['h1', 'h2', 'h3', 'h4', 'a'], class_=['title', 'news-title', 'article-title'])
                    if not title_elem:
                        title_elem = item.find(['h1', 'h2', 'h3', 'h4'])
                    if not title_elem:
                        continue
                    title = title_elem.text.strip() if title_elem else ""
                    
                    date_elem = item.find(['time', 'span', 'div'], class_=['date', 'time', 'news-date'])
                    date_text = date_elem.text.strip() if date_elem else ""
                    
                    content_elem = item.find(['div', 'p'], class_=['content', 'text', 'description', 'excerpt'])
                    content = content_elem.text.strip() if content_elem else ""
                    
                    # Парсинг даты
                    date_match = re.search(r'\d{2}\.\d{2}\.\d{4}', date_text)
                    if not date_match:
                        date_match = re.search(r'\d{4}-\d{2}-\d{2}', date_text)
                        if date_match:
                            item_date = datetime.strptime(date_match.group(), '%Y-%m-%d').date()
                        else:
                            continue
                    else:
                        item_date = datetime.strptime(date_match.group(), '%d.%m.%Y').date()
                    
                    cases = self.extract_case_number(title + " " + content)
                    if not cases and any(word in (title + " " + content).lower() for word in ['клещ', 'укус', 'энцефалит', 'присасыван', 'боррелиоз']):
                        cases = 0
                    
                    link_elem = item.find('a', href=True)
                    url = base_url + link_elem['href'] if link_elem and link_elem.get('href') and not link_elem['href'].startswith('http') else (link_elem['href'] if link_elem and link_elem.get('href') else "")
                    
                    if title or content:
                        results.append({
                            'date': item_date,
                            'cases': cases,
                            'title': title[:100] if title else "Без заголовка",
                            'content': content[:200] + "..." if len(content) > 200 else content,
                            'url': url,
                            'source': 'Роспотребнадзор (новости)'
                        })
                except Exception as e:
                    self.logger.debug(f"Ошибка обработки новости: {str(e)}")
                    continue
            
            self.logger.info(f"Получено {len(results)} записей из новостей Роспотребнадзора")
            return results
        except Exception as e:
            self.logger.error(f"Ошибка при парсинге новостей Роспотребнадзора: {str(e)}")
            return []
    
    def parse_tyumen_news(self):
        """Парсинг новостей с сайта администрации Тюмени"""
        try:
            ua = UserAgent()
            headers = {
                'User-Agent': ua.random,
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
                'Accept-Language': 'ru-RU,ru;q=0.8,en-US;q=0.5,en;q=0.3',
            }
            
            tyumen_config = self.config.get('parsing', {}).get('sources', {}).get('tyumen_news', {})
            # Пробуем альтернативные URL
            search_urls = [
                'https://www.tyumen-city.ru/news/',
                'https://www.tyumen-city.ru/',
                'https://t-i.ru/news/',
                'https://www.tyumen-city.ru/search/?q=%D0%BA%D0%BB%D0%B5%D1%89'
            ]
            max_items = tyumen_config.get('max_items', 30)
            
            response = None
            for search_url in search_urls:
                self.logger.info(f"Попытка парсинга новостей Тюмени: {search_url}")
                response = self.make_request_with_retry(search_url, headers)
                if response and response.status_code == 200:
                    break
            
            if not response or response.status_code != 200:
                self.logger.warning("Не удалось получить доступ к новостям Тюмени")
                return []
            
            soup = BeautifulSoup(response.text, 'html.parser')
            results = []
            
            news_items = soup.find_all(['article', 'div'], class_=['news', 'item', 'article'])
            if not news_items:
                news_items = soup.find_all('div', class_='search-result')[:max_items]
            
            news_items = news_items[:max_items]
            
            for item in news_items:
                try:
                    title_elem = item.find(['a', 'h2', 'h3'], class_=['title', 'link'])
                    if not title_elem:
                        continue
                    title = title_elem.text.strip() if title_elem else ""
                    
                    date_elem = item.find(['time', 'span'], class_=['date', 'time'])
                    date_text = date_elem.text.strip() if date_elem else ""
                    
                    content_elem = item.find(['div', 'p'], class_=['content', 'text', 'description'])
                    content = content_elem.text.strip() if content_elem else ""
                    
                    # Парсинг даты
                    date_match = re.search(r'\d{2}\.\d{2}\.\d{4}', date_text)
                    if not date_match:
                        date_match = re.search(r'\d{4}-\d{2}-\d{2}', date_text)
                        if date_match:
                            item_date = datetime.strptime(date_match.group(), '%Y-%m-%d').date()
                        else:
                            continue
                    else:
                        item_date = datetime.strptime(date_match.group(), '%d.%m.%Y').date()
                    
                    text = (title + " " + content).lower()
                    if not any(word in text for word in ['клещ', 'укус', 'энцефалит', 'присасыван', 'боррелиоз']):
                        continue
                    
                    cases = self.extract_case_number(title + " " + content)
                    if not cases:
                        cases = 0
                    
                    link_elem = item.find('a', href=True)
                    url = link_elem['href'] if link_elem and link_elem.get('href') else ""
                    if url and not url.startswith('http'):
                        url = 'https://www.tyumen-city.ru' + url
                    
                    if title or content:
                        results.append({
                            'date': item_date,
                            'cases': cases,
                            'title': title[:100] if title else "Без заголовка",
                            'content': content[:200] + "..." if len(content) > 200 else content,
                            'url': url,
                            'source': 'Администрация Тюмени'
                        })
                except Exception as e:
                    self.logger.debug(f"Ошибка обработки новости: {str(e)}")
                    continue
            
            self.logger.info(f"Получено {len(results)} записей из новостей Тюмени")
            return results
        except Exception as e:
            self.logger.error(f"Ошибка при парсинге новостей Тюмени: {str(e)}")
            return []

    def update_all_data(self):
        """Обновление всех данных"""
        try:
            self.logger.info("Начало обновления данных")
            web_data = self.parse_web_data()
            rss_data = self.parse_rss_feed()
            telegram_data = self.parse_telegram()
            
            combined_results = []
            combined_results.extend(web_data)
            combined_results.extend(rss_data)
            combined_results.extend(telegram_data)
            
            # Парсинг новостей Роспотребнадзора (если включен)
            rospotrebnadzor_config = self.config.get('parsing', {}).get('sources', {}).get('rospotrebnadzor_news', {})
            if rospotrebnadzor_config.get('enabled', True):
                rospotrebnadzor_news = self.parse_rospotrebnadzor_news()
                combined_results.extend(rospotrebnadzor_news)
            else:
                rospotrebnadzor_news = []
            
            # Парсинг новостей Тюмени (если включен)
            tyumen_config = self.config.get('parsing', {}).get('sources', {}).get('tyumen_news', {})
            if tyumen_config.get('enabled', False):
                tyumen_news = self.parse_tyumen_news()
                combined_results.extend(tyumen_news)
            else:
                tyumen_news = []
            
            self.logger.info(f"Всего найдено: веб={len(web_data)}, RSS={len(rss_data)}, Telegram={len(telegram_data)}, Роспотребнадзор новости={len(rospotrebnadzor_news)}, Тюмень новости={len(tyumen_news)}, всего={len(combined_results)}")
            
            if combined_results:
                combined_results.sort(key=lambda x: x['date'], reverse=True)
                
                # Добавляем risk_level
                for item in combined_results:
                    item['risk_level'] = self.calculate_risk_level(item.get('cases', 0))
                
                # Сохраняем в БД
                saved_count = self.db.save_tick_data(combined_results)
                self.logger.info(f"Данные успешно обновлены. Сохранено новых записей: {saved_count}")
            else:
                self.logger.warning("Новые данные не найдены")
        except Exception as e:
            self.logger.error(f"Ошибка при обновлении данных: {str(e)}", exc_info=True)

