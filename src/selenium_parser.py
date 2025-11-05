"""Модуль для парсинга JS-сайтов через Selenium"""
from logger_config import setup_logger
import time

logger = setup_logger()

try:
    from selenium import webdriver
    from selenium.webdriver.chrome.options import Options
    from selenium.webdriver.chrome.service import Service
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC
    from selenium.common.exceptions import TimeoutException, WebDriverException
    SELENIUM_AVAILABLE = True
except ImportError:
    SELENIUM_AVAILABLE = False
    logger.warning("Selenium не установлен, парсинг JS-сайтов отключен")


class SeleniumParser:
    """Класс для парсинга JavaScript-сайтов через Selenium"""
    
    def __init__(self, logger_instance=None, headless=True):
        self.logger = logger_instance or logger
        self.headless = headless
        self.driver = None
        self._init_driver()
    
    def _init_driver(self):
        """Инициализация Selenium WebDriver"""
        if not SELENIUM_AVAILABLE:
            return
        
        try:
            chrome_options = Options()
            if self.headless:
                chrome_options.add_argument('--headless')
            chrome_options.add_argument('--no-sandbox')
            chrome_options.add_argument('--disable-dev-shm-usage')
            chrome_options.add_argument('--disable-gpu')
            chrome_options.add_argument('--window-size=1920,1080')
            chrome_options.add_argument('--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36')
            
            # Пробуем создать драйвер
            try:
                self.driver = webdriver.Chrome(options=chrome_options)
            except:
                # Если Chrome недоступен, пробуем Firefox
                try:
                    from selenium.webdriver.firefox.options import Options as FirefoxOptions
                    firefox_options = FirefoxOptions()
                    if self.headless:
                        firefox_options.add_argument('--headless')
                    self.driver = webdriver.Firefox(options=firefox_options)
                except:
                    self.logger.warning("Не удалось инициализировать Selenium WebDriver")
                    self.driver = None
            
            if self.driver:
                self.driver.set_page_load_timeout(30)
                self.logger.info("Selenium WebDriver инициализирован")
                
        except Exception as e:
            self.logger.warning(f"Ошибка инициализации Selenium: {str(e)}")
            self.driver = None
    
    def parse_js_page(self, url, wait_for_element=None, timeout=10):
        """Парсинг страницы с JavaScript
        
        Args:
            url: URL страницы
            wait_for_element: CSS селектор элемента для ожидания (опционально)
            timeout: Таймаут ожидания (секунды)
        
        Returns:
            str: HTML содержимое страницы или None
        """
        if not SELENIUM_AVAILABLE or not self.driver:
            self.logger.warning("Selenium недоступен, используем обычный requests")
            return None
        
        try:
            self.logger.info(f"Парсинг JS-страницы через Selenium: {url}")
            self.driver.get(url)
            
            # Ждем загрузки страницы
            if wait_for_element:
                try:
                    WebDriverWait(self.driver, timeout).until(
                        EC.presence_of_element_located((By.CSS_SELECTOR, wait_for_element))
                    )
                except TimeoutException:
                    self.logger.warning(f"Элемент {wait_for_element} не найден на странице")
            
            # Дополнительное ожидание для загрузки динамического контента
            time.sleep(2)
            
            # Получаем HTML после выполнения JavaScript
            html = self.driver.page_source
            return html
            
        except WebDriverException as e:
            self.logger.error(f"Ошибка Selenium при парсинге {url}: {str(e)}")
            return None
        except Exception as e:
            self.logger.error(f"Неожиданная ошибка при парсинге {url}: {str(e)}")
            return None
    
    def close(self):
        """Закрытие WebDriver"""
        if self.driver:
            try:
                self.driver.quit()
            except:
                pass
            self.driver = None
    
    def __del__(self):
        """Деструктор для закрытия драйвера"""
        self.close()

