"""Модуль для работы с базой данных"""
from sqlalchemy import create_engine, Column, Integer, String, Date, DateTime, Text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session
from datetime import datetime, date, timedelta
import os
import json
from logger_config import setup_logger

Base = declarative_base()
logger = setup_logger()

class TickData(Base):
    """Модель для хранения данных о клещах"""
    __tablename__ = 'tick_data'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    date = Column(Date, nullable=False, index=True)
    cases = Column(Integer, nullable=False, default=0)
    risk_level = Column(String(50), nullable=False)
    source = Column(String(200), nullable=False)
    title = Column(Text)
    content = Column(Text)
    url = Column(Text)
    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)
    
    def __repr__(self):
        return f"<TickData(date={self.date}, cases={self.cases}, source={self.source})>"


class DatabaseManager:
    """Менеджер для работы с базой данных"""
    
    def __init__(self, database_url=None):
        """Инициализация менеджера БД"""
        if database_url is None:
            # Получаем из переменной окружения или используем значение по умолчанию
            database_url = os.getenv(
                'DATABASE_URL',
                'postgresql://mite_user:mite_password@localhost:5432/mite_tmn'
            )
        
        self.database_url = database_url
        self.engine = create_engine(database_url, pool_pre_ping=True)
        self.SessionLocal = sessionmaker(bind=self.engine, autocommit=False, autoflush=False)
        logger.info(f"Инициализация БД: {database_url.split('@')[1] if '@' in database_url else 'local'}")

    def create_tables(self):
        """Создание таблиц в БД"""
        try:
            Base.metadata.create_all(self.engine)
            logger.info("Таблицы БД созданы успешно")
        except Exception as e:
            logger.error(f"Ошибка создания таблиц: {str(e)}")
            raise

    def get_session(self) -> Session:
        """Получение сессии БД"""
        return self.SessionLocal()

    def calculate_risk_level(self, cases):
        """Определение уровня риска"""
        if not isinstance(cases, int) or cases == 0:
            return "Нет данных"
        
        # Загружаем конфигурацию
        try:
            config_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'config', 'config.json')
            if os.path.exists(config_path):
                with open(config_path, 'r', encoding='utf-8') as f:
                    config = json.load(f)
                    risk_config = config.get('risk_levels', {})
                    thresholds = {
                        'low': risk_config.get('low', {}).get('threshold', 50),
                        'moderate': risk_config.get('moderate', {}).get('threshold', 100),
                        'high': risk_config.get('high', {}).get('threshold', 150),
                        'very_high': risk_config.get('very_high', {}).get('threshold', 999999)
                    }
            else:
                thresholds = {'low': 50, 'moderate': 100, 'high': 150, 'very_high': 999999}
        except:
            thresholds = {'low': 50, 'moderate': 100, 'high': 150, 'very_high': 999999}
        
        if cases < thresholds['low']:
            return "Низкий"
        elif cases < thresholds['moderate']:
            return "Умеренный"
        elif cases < thresholds['high']:
            return "Высокий"
        else:
            return "Очень высокий"

    def save_tick_data(self, data_list):
        """Сохранение данных о клещах"""
        session = self.get_session()
        try:
            saved_count = 0
            for item in data_list:
                # Проверяем, существует ли запись
                existing = session.query(TickData).filter(
                    TickData.date == item['date'],
                    TickData.source == item.get('source', ''),
                    TickData.title == item.get('title', '')
                ).first()
                
                risk_level = item.get('risk_level') or self.calculate_risk_level(item.get('cases', 0))
                
                if existing:
                    # Обновляем существующую запись
                    existing.cases = item.get('cases', 0)
                    existing.risk_level = risk_level
                    existing.content = item.get('content', '')
                    existing.url = item.get('url', '')
                    existing.updated_at = datetime.now()
                else:
                    # Создаем новую запись
                    tick_data = TickData(
                        date=item['date'],
                        cases=item.get('cases', 0),
                        risk_level=risk_level,
                        source=item.get('source', 'Неизвестно'),
                        title=item.get('title', ''),
                        content=item.get('content', ''),
                        url=item.get('url', '')
                    )
                    session.add(tick_data)
                    saved_count += 1
            
            session.commit()
            logger.info(f"Сохранено {saved_count} новых записей в БД")
            return saved_count
        except Exception as e:
            session.rollback()
            logger.error(f"Ошибка при сохранении данных в БД: {str(e)}", exc_info=True)
            raise
        finally:
            session.close()

    def load_tick_data(self, limit=100, order_by_date_desc=True):
        """Загрузка данных о клещах"""
        session = self.get_session()
        try:
            query = session.query(TickData)
            
            if order_by_date_desc:
                query = query.order_by(TickData.date.desc())
            else:
                query = query.order_by(TickData.date.asc())
            
            if limit is not None:
                query = query.limit(limit)
            
            results = query.all()
            
            # Преобразуем в список словарей
            data_list = []
            for record in results:
                data_list.append({
                    'date': record.date,
                    'cases': record.cases,
                    'risk_level': record.risk_level,
                    'source': record.source,
                    'title': record.title or '',
                    'content': record.content or '',
                    'url': record.url or ''
                })
            
            logger.info(f"Загружено {len(data_list)} записей из БД")
            return data_list
        except Exception as e:
            logger.error(f"Ошибка при загрузке данных из БД: {str(e)}", exc_info=True)
            return []
        finally:
            session.close()

    def get_weekly_data(self, weeks_ago=0):
        """Получение данных за указанное количество недель назад"""
        session = self.get_session()
        try:
            from datetime import timedelta
            target_date = datetime.now().date() - timedelta(weeks=weeks_ago)
            
            # Находим ближайшую запись до или равную target_date
            record = session.query(TickData).filter(
                TickData.date <= target_date
            ).order_by(TickData.date.desc()).first()
            
            if record:
                return {
                    'cases': record.cases,
                    'date': record.date,
                    'risk_level': record.risk_level
                }
            else:
                return {
                    'cases': 0,
                    'date': target_date,
                    'risk_level': 'Нет данных'
                }
        except Exception as e:
            logger.error(f"Ошибка при получении недельных данных: {str(e)}")
            return {
                'cases': 0,
                'date': datetime.now().date(),
                'risk_level': 'Нет данных'
            }
        finally:
            session.close()

    def get_filtered_data(self, start_date, end_date):
        """Получение отфильтрованных данных по датам"""
        session = self.get_session()
        try:
            results = session.query(TickData).filter(
                TickData.date >= start_date,
                TickData.date <= end_date
            ).order_by(TickData.date.desc()).all()
            
            data_list = []
            for record in results:
                data_list.append({
                    'date': record.date,
                    'cases': record.cases,
                    'risk_level': record.risk_level,
                    'source': record.source,
                    'title': record.title or '',
                    'content': record.content or '',
                    'url': record.url or ''
                })
            
            return data_list
        except Exception as e:
            logger.error(f"Ошибка при фильтрации данных: {str(e)}")
            return []
        finally:
            session.close()

    def get_all_data_grouped_by_week(self):
        """Получение всех данных, сгруппированных по неделям"""
        session = self.get_session()
        try:
            import pandas as pd
            from sqlalchemy import func
            
            # Получаем все данные
            results = session.query(TickData).order_by(TickData.date.asc()).all()
            
            if not results:
                return []
            
            # Преобразуем в DataFrame
            data = [{
                'date': r.date,
                'cases': r.cases
            } for r in results]
            
            df = pd.DataFrame(data)
            df['date'] = pd.to_datetime(df['date'])
            
            # Группируем по неделям
            df['year_week'] = df['date'].dt.strftime('%Y-%U')
            weekly_data = df.groupby('year_week').agg({
                'cases': 'sum',
                'date': ['min', 'max']
            }).reset_index()
            
            weekly_data.columns = ['year_week', 'cases', 'start_date', 'end_date']
            weekly_data = weekly_data.sort_values('start_date')
            
            return weekly_data.to_dict('records')
        except Exception as e:
            logger.error(f"Ошибка при группировке данных: {str(e)}")
            return []
        finally:
            session.close()

