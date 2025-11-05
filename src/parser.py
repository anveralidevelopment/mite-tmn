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
    
    def parse_search_results_pages(self, base_url, search_url, headers, max_pages=13):
        """Парсинг всех страниц результатов поиска"""
        all_article_urls = []
        
        for page in range(1, max_pages + 1):
            try:
                # Формируем URL для страницы поиска
                if '?' in search_url:
                    page_url = f"{search_url}&page={page}"
                else:
                    page_url = f"{search_url}?page={page}"
                
                self.logger.info(f"Парсинг страницы поиска {page}: {page_url}")
                response = self.make_request_with_retry(page_url, headers)
                
                if not response or response.status_code != 200:
                    self.logger.debug(f"Не удалось загрузить страницу {page}")
                    break
                
                soup = BeautifulSoup(response.text, 'html.parser')
                
                # Ищем ссылки на статьи
                # По разным вариантам структуры страницы
                links = []
                
                # Вариант 1: ссылки в результатах поиска (div.search-result или div.search-item)
                search_items = soup.find_all('div', class_='search-result')
                if not search_items:
                    search_items = soup.find_all('div', class_='search-item')
                if not search_items:
                    # Ищем все div с результатами
                    search_items = soup.find_all('div', class_=re.compile(r'search|result|item'))
                
                for item in search_items:
                    # Ищем все ссылки внутри элемента
                    link_elems = item.find_all('a', href=True)
                    for link_elem in link_elems:
                        href = link_elem.get('href', '').strip()
                        if not href:
                            continue
                        # Убираем пробелы и лишние символы
                        href = href.strip()
                        if href.startswith('/content/') or href.startswith('/news/') or '/content/' in href:
                            if not href.startswith('http'):
                                full_url = base_url + href
                            else:
                                full_url = href
                            if full_url not in all_article_urls:
                                links.append(full_url)
                                all_article_urls.append(full_url)
                
                # Вариант 2: все ссылки на статьи в заголовках
                title_links = soup.find_all('a', href=re.compile(r'/content/|/news/'))
                for link in title_links:
                    href = link.get('href', '')
                    if href.startswith('/') or base_url in href:
                        full_url = base_url + href if not href.startswith('http') else href
                        if full_url not in all_article_urls:
                            links.append(full_url)
                            all_article_urls.append(full_url)
                
                # Вариант 3: ищем все ссылки, содержащие "content" в URL
                all_links = soup.find_all('a', href=True)
                for link in all_links:
                    href = link.get('href', '')
                    if '/content/' in href:
                        full_url = base_url + href if not href.startswith('http') else href
                        if full_url not in all_article_urls:
                            links.append(full_url)
                            all_article_urls.append(full_url)
                
                # Проверяем, есть ли следующая страница
                next_page = soup.find('a', string=re.compile(r'След|Next|›', re.IGNORECASE))
                if not next_page and page > 1:
                    # Если нет явной кнопки "Следующая", проверяем пагинацию
                    pagination = soup.find_all('a', href=re.compile(r'page=\d+'))
                    if not pagination or page >= max_pages:
                        break
                
                if not links:
                    self.logger.debug(f"На странице {page} не найдено ссылок, возможно это последняя страница")
                    break
                
                self.logger.info(f"На странице {page} найдено {len(links)} ссылок")
                time.sleep(1)  # Небольшая задержка между запросами
                
            except Exception as e:
                self.logger.warning(f"Ошибка при парсинге страницы {page}: {str(e)}")
                break
        
        self.logger.info(f"Всего найдено {len(all_article_urls)} уникальных статей")
        return all_article_urls
    
    def parse_article_page(self, article_url, headers):
        """Парсинг полного содержимого статьи"""
        try:
            response = self.make_request_with_retry(article_url, headers)
            if not response or response.status_code != 200:
                return None
            
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # Извлекаем заголовок
            title = ""
            title_elem = soup.find('h1') or soup.find('h2', class_='title') or soup.find('div', class_='title')
            if title_elem:
                title = title_elem.get_text(strip=True)
            
            # Извлекаем дату - ищем в разных местах
            date_text = ""
            
            # 1. Ищем в атрибуте datetime
            time_elem = soup.find('time', datetime=True)
            if time_elem:
                date_text = time_elem.get('datetime', '')
            
            # 2. Ищем в элементах с классом date
            if not date_text:
                date_elem = (soup.find('time') or 
                           soup.find('div', class_=re.compile(r'date|time|published', re.I)) or 
                           soup.find('span', class_=re.compile(r'date|time|published', re.I)) or
                           soup.find('p', class_=re.compile(r'date|time|published', re.I)))
                if date_elem:
                    date_text = date_elem.get_text(strip=True)
                    # Если не нашли текст, пробуем атрибут datetime
                    if not date_text and date_elem.has_attr('datetime'):
                        date_text = date_elem.get('datetime', '')
            
            # 3. Ищем дату в заголовке страницы (meta теги)
            if not date_text:
                meta_date = soup.find('meta', property='article:published_time') or \
                           soup.find('meta', attrs={'name': re.compile(r'date|published', re.I)})
                if meta_date:
                    date_text = meta_date.get('content', '')
            
            # 4. Ищем дату в тексте страницы (в начале статьи)
            if not date_text:
                # Ищем в первых параграфах или в начале контента
                body_text = soup.get_text()
                # Ищем дату в формате DD.MM.YYYY или YYYY-MM-DD в первых 2000 символах
                date_patterns = [
                    r'\d{2}\.\d{2}\.\d{4}',
                    r'\d{4}-\d{2}-\d{2}',
                    r'\d{1,2}\s+(января|февраля|марта|апреля|мая|июня|июля|августа|сентября|октября|ноября|декабря)\s+\d{4}'
                ]
                
                preview_text = body_text[:2000]  # Первые 2000 символов
                for pattern in date_patterns:
                    match = re.search(pattern, preview_text, re.IGNORECASE)
                    if match:
                        date_text = match.group()
                        # Проверяем, что это похоже на дату (не просто число в тексте)
                        # Проверяем контекст вокруг даты
                        start_pos = max(0, match.start() - 20)
                        end_pos = min(len(preview_text), match.end() + 20)
                        context = preview_text[start_pos:end_pos].lower()
                        # Если рядом есть слова "дата", "опубликовано", "создано" и т.д., это точно дата
                        if any(word in context for word in ['дата', 'опубликовано', 'создано', 'дата:', 'от']):
                            break
                        # Или если это формат DD.MM.YYYY и год между 2020 и 2025
                        if re.match(r'\d{2}\.\d{2}\.20[2-4]\d', match.group()):
                            break
                        # Или если это формат YYYY-MM-DD
                        if re.match(r'20[2-4]\d-\d{2}-\d{2}', match.group()):
                            break
            
            # Извлекаем полное содержимое статьи
            content = ""
            
            # Ищем основной контент статьи
            content_selectors = [
                'div.content',
                'div.article-content',
                'div.text',
                'div.news-content',
                'article',
                'div.main-content',
                'div[class*="content"]',
                'div[class*="text"]'
            ]
            
            for selector in content_selectors:
                content_elem = soup.select_one(selector)
                if content_elem:
                    # Удаляем скрипты и стили
                    for script in content_elem(['script', 'style', 'nav', 'footer', 'header']):
                        script.decompose()
                    content = content_elem.get_text('\n', strip=True)
                    if len(content) > 200:  # Если контент достаточно большой
                        break
            
            # Если не нашли, берем весь body
            if not content or len(content) < 200:
                body = soup.find('body')
                if body:
                    # Удаляем ненужные элементы
                    for elem in body(['script', 'style', 'nav', 'footer', 'header', 'aside']):
                        elem.decompose()
                    content = body.get_text('\n', strip=True)
            
            # Парсим дату с улучшенной логикой
            item_date = None
            
            # Сначала пытаемся распарсить через dateutil (более гибкий)
            if date_text:
                try:
                    parsed_date = date_parser.parse(date_text, fuzzy=True, dayfirst=True)
                    if parsed_date:
                        item_date = parsed_date.date()
                except:
                    pass
            
            # Если dateutil не сработал, пробуем регулярные выражения
            if not item_date and date_text:
                date_patterns = [
                    (r'\d{2}\.\d{2}\.\d{4}', '%d.%m.%Y'),
                    (r'\d{4}-\d{2}-\d{2}', '%Y-%m-%d'),
                    (r'\d{1,2}\.\d{1,2}\.\d{4}', '%d.%m.%Y'),
                    (r'\d{1,2}\s+(января|февраля|марта|апреля|мая|июня|июля|августа|сентября|октября|ноября|декабря)\s+\d{4}', None)
                ]
                
                for pattern, date_format in date_patterns:
                    match = re.search(pattern, date_text, re.IGNORECASE)
                    if match:
                        try:
                            if date_format:
                                # Формат DD.MM.YYYY или YYYY-MM-DD
                                item_date = datetime.strptime(match.group(), date_format).date()
                            else:
                                # Формат "01 января 2024"
                                months_ru = {
                                    'января': 1, 'февраля': 2, 'марта': 3, 'апреля': 4,
                                    'мая': 5, 'июня': 6, 'июля': 7, 'августа': 8,
                                    'сентября': 9, 'октября': 10, 'ноября': 11, 'декабря': 12
                                }
                                parts = match.group().split()
                                if len(parts) >= 3:
                                    day = int(parts[0])
                                    month = months_ru.get(parts[1].lower(), 1)
                                    year = int(parts[2])
                                    item_date = date(year, month, day)
                            
                            # Валидация даты
                            if item_date:
                                today = date.today()
                                # Проверяем, что дата не в будущем (с небольшим запасом на 1 день)
                                if item_date > today:
                                    self.logger.warning(f"Дата в будущем: {item_date}, используем текущую дату")
                                    item_date = today
                                # Проверяем, что дата не слишком старая (не раньше 2020 года)
                                elif item_date < date(2020, 1, 1):
                                    self.logger.warning(f"Дата слишком старая: {item_date}, пропускаем запись")
                                    item_date = None
                                    return None  # Пропускаем запись со слишком старой датой
                            
                            break
                        except Exception as e:
                            self.logger.debug(f"Ошибка парсинга даты '{match.group()}': {str(e)}")
                            continue
            
            # Если дата не найдена, пытаемся извлечь из URL
            if not item_date:
                # Ищем дату в URL (например, /2024/05/03/)
                url_date_match = re.search(r'/(\d{4})/(\d{2})/(\d{2})/', article_url)
                if url_date_match:
                    try:
                        year = int(url_date_match.group(1))
                        month = int(url_date_match.group(2))
                        day = int(url_date_match.group(3))
                        item_date = date(year, month, day)
                        # Валидация
                        today = date.today()
                        if item_date > today:
                            item_date = today
                        elif item_date < date(2020, 1, 1):
                            item_date = None
                            return None
                    except:
                        pass
            
            # Если дата все еще не найдена, логируем и пропускаем запись
            if not item_date:
                self.logger.warning(f"Не удалось определить дату для статьи {article_url}, пропускаем запись")
                return None  # Пропускаем записи без даты вместо использования текущей даты
            
            # Извлекаем количество случаев
            cases = self.extract_case_number(title + " " + content)
            if not cases and any(word in (title + " " + content).lower() for word in ['клещ', 'укус', 'энцефалит', 'присасыван']):
                cases = 0
            
            # Извлекаем локацию
            location = self.extract_location(title + " " + content)
            
            return {
                'date': item_date,
                'cases': cases,
                'title': title[:200] if title else "Без заголовка",
                'content': content[:5000] if len(content) > 5000 else content,  # Ограничиваем размер
                'url': article_url,
                'source': 'Роспотребнадзор (поиск)',
                'location': location
            }
            
        except Exception as e:
            self.logger.error(f"Ошибка при парсинге статьи {article_url}: {str(e)}")
            return None
    
    def parse_web_data(self):
        """Парсинг данных с веб-сайта через поиск"""
        try:
            ua = UserAgent()
            headers = {
                'User-Agent': ua.random,
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
                'Accept-Language': 'ru-RU,ru;q=0.8,en-US;q=0.5,en;q=0.3',
            }
            
            web_config = self.config.get('parsing', {}).get('sources', {}).get('web', {})
            base_url = web_config.get('base_url', 'https://72.rospotrebnadzor.ru')
            max_items = web_config.get('max_items', 200)
            
            # URL поиска с клещами
            search_url = f"{base_url}/search/?q=клещи&spell=1&where="
            
            self.logger.info(f"Начинаем парсинг поиска: {search_url}")
            
            # Парсим все страницы результатов поиска
            article_urls = self.parse_search_results_pages(base_url, search_url, headers, max_pages=13)
            
            if not article_urls:
                self.logger.warning("Не найдено статей в результатах поиска")
                return []
            
            # Ограничиваем количество статей
            article_urls = article_urls[:max_items]
            
            # Парсим каждую статью
            results = []
            for i, article_url in enumerate(article_urls, 1):
                try:
                    self.logger.info(f"Парсинг статьи {i}/{len(article_urls)}: {article_url}")
                    article_data = self.parse_article_page(article_url, headers)
                    if article_data:
                        results.append(article_data)
                    time.sleep(0.5)  # Небольшая задержка между запросами
                except Exception as e:
                    self.logger.warning(f"Ошибка при парсинге статьи {article_url}: {str(e)}")
                    continue
            
            self.logger.info(f"Получено {len(results)} записей с веб-сайта через поиск")
            return results
        except Exception as e:
            self.logger.error(f"Ошибка при парсинге веб-сайта: {str(e)}", exc_info=True)
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
                    
                    # Если не нашли в элементе, пробуем атрибут datetime
                    if not date_text and date_elem and date_elem.has_attr('datetime'):
                        date_text = date_elem.get('datetime', '')
                    
                    content_elem = item.find(['div', 'p'], class_=['content', 'text', 'description', 'excerpt'])
                    content = content_elem.text.strip() if content_elem else ""
                    
                    # Парсинг даты с улучшенной логикой
                    item_date = None
                    
                    # Пробуем dateutil
                    if date_text:
                        try:
                            parsed_date = date_parser.parse(date_text, fuzzy=True, dayfirst=True)
                            if parsed_date:
                                item_date = parsed_date.date()
                        except:
                            pass
                    
                    # Если dateutil не сработал, пробуем регулярные выражения
                    if not item_date and date_text:
                        date_match = re.search(r'\d{2}\.\d{2}\.\d{4}', date_text)
                        if date_match:
                            try:
                                item_date = datetime.strptime(date_match.group(), '%d.%m.%Y').date()
                            except:
                                pass
                        
                        if not item_date:
                            date_match = re.search(r'\d{4}-\d{2}-\d{2}', date_text)
                            if date_match:
                                try:
                                    item_date = datetime.strptime(date_match.group(), '%Y-%m-%d').date()
                                except:
                                    pass
                    
                    # Валидация даты
                    if item_date:
                        today = date.today()
                        if item_date > today:
                            self.logger.warning(f"Дата в будущем: {item_date}, используем текущую дату")
                            item_date = today
                        elif item_date < date(2020, 1, 1):
                            self.logger.warning(f"Дата слишком старая: {item_date}, пропускаем запись")
                            item_date = None
                            continue  # Пропускаем запись
                    
                    # Если дата не найдена, пропускаем запись
                    if not item_date:
                        self.logger.warning(f"Не удалось определить дату для новости, пропускаем")
                        continue
                    
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
                    
                    # Если не нашли в элементе, пробуем атрибут datetime
                    if not date_text and date_elem and date_elem.has_attr('datetime'):
                        date_text = date_elem.get('datetime', '')
                    
                    content_elem = item.find(['div', 'p'], class_=['content', 'text', 'description'])
                    content = content_elem.text.strip() if content_elem else ""
                    
                    # Парсинг даты с улучшенной логикой
                    item_date = None
                    
                    # Пробуем dateutil
                    if date_text:
                        try:
                            parsed_date = date_parser.parse(date_text, fuzzy=True, dayfirst=True)
                            if parsed_date:
                                item_date = parsed_date.date()
                        except:
                            pass
                    
                    # Если dateutil не сработал, пробуем регулярные выражения
                    if not item_date and date_text:
                        date_match = re.search(r'\d{2}\.\d{2}\.\d{4}', date_text)
                        if date_match:
                            try:
                                item_date = datetime.strptime(date_match.group(), '%d.%m.%Y').date()
                            except:
                                pass
                        
                        if not item_date:
                            date_match = re.search(r'\d{4}-\d{2}-\d{2}', date_text)
                            if date_match:
                                try:
                                    item_date = datetime.strptime(date_match.group(), '%Y-%m-%d').date()
                                except:
                                    pass
                    
                    # Валидация даты
                    if item_date:
                        today = date.today()
                        if item_date > today:
                            self.logger.warning(f"Дата в будущем: {item_date}, используем текущую дату")
                            item_date = today
                        elif item_date < date(2020, 1, 1):
                            self.logger.warning(f"Дата слишком старая: {item_date}, пропускаем запись")
                            item_date = None
                            continue  # Пропускаем запись
                    
                    # Если дата не найдена, пропускаем запись
                    if not item_date:
                        self.logger.warning(f"Не удалось определить дату для новости Тюмени, пропускаем")
                        continue
                    
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
        """Обновление всех данных из всех источников с улучшенной обработкой ошибок"""
        try:
            self.logger.info("Начинаем обновление данных из всех источников")
            
            all_data = []
            errors_summary = {}
            
            # Парсинг веб-сайта
            try:
                web_data = self.parse_web_data()
                if web_data:
                    all_data.extend(web_data)
                    self.logger.info(f"Получено {len(web_data)} записей с веб-сайта")
            except Exception as e:
                error_msg = f"Ошибка парсинга веб-сайта: {str(e)}"
                errors_summary['web'] = error_msg
                self.logger.error(error_msg, exc_info=True)
            
            # Парсинг RSS
            try:
                rss_data = self.parse_rss_feed()
                if rss_data:
                    all_data.extend(rss_data)
                    self.logger.info(f"Получено {len(rss_data)} записей из RSS")
            except Exception as e:
                error_msg = f"Ошибка парсинга RSS: {str(e)}"
                errors_summary['rss'] = error_msg
                self.logger.error(error_msg, exc_info=True)
            
            # Парсинг Telegram
            try:
                telegram_data = self.parse_telegram()
                if telegram_data:
                    all_data.extend(telegram_data)
                    self.logger.info(f"Получено {len(telegram_data)} записей из Telegram")
            except Exception as e:
                error_msg = f"Ошибка парсинга Telegram: {str(e)}"
                errors_summary['telegram'] = error_msg
                self.logger.error(error_msg, exc_info=True)
            
            # Парсинг новостей Роспотребнадзора
            try:
                rospotrebnadzor_config = self.config.get('parsing', {}).get('sources', {}).get('rospotrebnadzor_news', {})
                if rospotrebnadzor_config.get('enabled', False):
                    rospotrebnadzor_news = self.parse_rospotrebnadzor_news()
                    if rospotrebnadzor_news:
                        all_data.extend(rospotrebnadzor_news)
                        self.logger.info(f"Получено {len(rospotrebnadzor_news)} записей из новостей Роспотребнадзора")
            except Exception as e:
                error_msg = f"Ошибка парсинга новостей Роспотребнадзора: {str(e)}"
                errors_summary['rospotrebnadzor_news'] = error_msg
                self.logger.error(error_msg, exc_info=True)
            
            # Парсинг новостей Тюмени
            try:
                tyumen_config = self.config.get('parsing', {}).get('sources', {}).get('tyumen_news', {})
                if tyumen_config.get('enabled', False):
                    tyumen_news = self.parse_tyumen_news()
                    if tyumen_news:
                        all_data.extend(tyumen_news)
                        self.logger.info(f"Получено {len(tyumen_news)} записей из новостей Тюмени")
            except Exception as e:
                error_msg = f"Ошибка парсинга новостей Тюмени: {str(e)}"
                errors_summary['tyumen_news'] = error_msg
                self.logger.error(error_msg, exc_info=True)
            
            # Сохраняем данные в БД с улучшенной обработкой ошибок
            if all_data:
                self.logger.info(f"Всего получено {len(all_data)} записей, начинаем сохранение в БД")
                saved_count = 0
                error_count = 0
                duplicate_count = 0
                
                for i, data_item in enumerate(all_data, 1):
                    try:
                        # Валидация данных перед сохранением
                        if not self._validate_data_item(data_item):
                            error_count += 1
                            self.logger.debug(f"Запись {i} не прошла валидацию: {data_item.get('url', 'unknown')}")
                            continue
                        
                        # Проверяем, существует ли уже такая запись
                        existing = self.db.get_tick_data_by_url(data_item.get('url'))
                        if existing:
                            duplicate_count += 1
                            # Обновляем существующую запись только если есть изменения
                            try:
                                self.db.update_tick_data(existing['id'], data_item)
                            except Exception as e:
                                error_count += 1
                                self.logger.warning(f"Ошибка обновления записи {existing['id']}: {str(e)}")
                                continue
                        else:
                            # Создаем новую запись
                            try:
                                self.db.save_tick_data(data_item)
                                saved_count += 1
                            except Exception as e:
                                error_count += 1
                                self.logger.warning(f"Ошибка сохранения записи {i}: {str(e)}")
                                continue
                    except Exception as e:
                        error_count += 1
                        self.logger.warning(f"Неожиданная ошибка при обработке записи {i}: {str(e)}")
                        continue
                
                summary = f"Сохранено {saved_count} новых записей, обновлено {duplicate_count} существующих, ошибок: {error_count}"
                if errors_summary:
                    summary += f", ошибки источников: {', '.join(errors_summary.keys())}"
                self.logger.info(summary)
            else:
                if errors_summary:
                    self.logger.warning(f"Не получено данных из источников. Ошибки: {', '.join(errors_summary.keys())}")
                else:
                    self.logger.warning("Не получено данных из источников")
                
        except Exception as e:
            self.logger.error(f"Критическая ошибка при обновлении данных: {str(e)}", exc_info=True)
            raise  # Пробрасываем критическую ошибку выше
    
    def _validate_data_item(self, data_item):
        """Валидация элемента данных перед сохранением"""
        try:
            # Проверяем обязательные поля
            required_fields = ['date', 'cases', 'risk_level', 'source']
            for field in required_fields:
                if field not in data_item or data_item[field] is None:
                    return False
            
            # Валидация типов
            if not isinstance(data_item['date'], date):
                return False
            if not isinstance(data_item['cases'], int) or data_item['cases'] < 0:
                return False
            if not isinstance(data_item['risk_level'], str) or len(data_item['risk_level']) > 50:
                return False
            if not isinstance(data_item['source'], str) or len(data_item['source']) > 200:
                return False
            
            # Проверяем, что дата не в будущем (с небольшим запасом)
            from datetime import date as date_class
            today = date_class.today()
            if data_item['date'] > today:
                self.logger.warning(f"Дата в будущем: {data_item['date']}, пропускаем")
                return False
            
            return True
        except Exception as e:
            self.logger.debug(f"Ошибка валидации: {str(e)}")
            return False

