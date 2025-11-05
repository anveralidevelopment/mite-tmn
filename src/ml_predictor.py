"""Модуль для ML прогнозирования активности клещей"""
import numpy as np
import pandas as pd
from datetime import datetime, date, timedelta
try:
    from sklearn.linear_model import LinearRegression
    from sklearn.ensemble import RandomForestRegressor
    from sklearn.preprocessing import StandardScaler
    from sklearn.model_selection import train_test_split
    from sklearn.metrics import mean_absolute_error, mean_squared_error
    SKLEARN_AVAILABLE = True
except ImportError:
    SKLEARN_AVAILABLE = False
import os
import json
from logger_config import setup_logger

# Импорт улучшенных модулей
try:
    from enhanced_ml_predictor import (
        ModelMetrics, FeatureEngineering, LSTMModel, GRUModel,
        EnsembleModel, AnomalyDetector, LocationClusterer, PreventionRecommendations
    )
    ENHANCED_ML_AVAILABLE = True
    
    # Проверка доступности библиотек
    try:
        from xgboost import XGBRegressor
        XGBOOST_AVAILABLE = True
    except ImportError:
        XGBOOST_AVAILABLE = False
    
    try:
        import tensorflow as tf
        TENSORFLOW_AVAILABLE = True
    except ImportError:
        TENSORFLOW_AVAILABLE = False
except ImportError:
    ENHANCED_ML_AVAILABLE = False
    XGBOOST_AVAILABLE = False
    TENSORFLOW_AVAILABLE = False
    logger.warning("Улучшенные ML модули недоступны, используются базовые модели")

logger = setup_logger()


class TickPredictor:
    """Класс для прогнозирования активности клещей с помощью ML"""
    
    def __init__(self, db, weather_api=None):
        self.db = db
        self.model = None
        self.scaler = StandardScaler()
        self.is_trained = False
        
        # Улучшенные компоненты
        self.feature_engineering = FeatureEngineering(weather_api=weather_api) if ENHANCED_ML_AVAILABLE else None
        self.model_metrics = ModelMetrics() if ENHANCED_ML_AVAILABLE else None
        self.anomaly_detector = AnomalyDetector() if ENHANCED_ML_AVAILABLE else None
        self.location_clusterer = LocationClusterer() if ENHANCED_ML_AVAILABLE else None
        self.prevention_recommendations = PreventionRecommendations() if ENHANCED_ML_AVAILABLE else None
        
        # Модели для ансамбля
        self.models = {}
        self.best_model_name = None
        self.model_metrics_history = {}
        
        # A/B тестирование
        self.ab_test_models = {}
        self.ab_test_results = {}
        
    def prepare_data(self, historical_data):
        """Подготовка данных для обучения модели с улучшенной обработкой edge cases"""
        try:
            # Edge case 1: Пустые или None данные
            if not historical_data:
                logger.warning("Исторические данные пусты")
                return None, None
            
            if not isinstance(historical_data, (list, tuple)):
                logger.warning(f"Неверный тип данных: {type(historical_data)}")
                return None, None
            
            if len(historical_data) < 10:
                logger.warning(f"Недостаточно данных для обучения модели: {len(historical_data)} < 10")
                return None, None
            
            # Преобразуем в DataFrame с обработкой ошибок
            try:
                df = pd.DataFrame(historical_data)
            except Exception as e:
                logger.error(f"Ошибка создания DataFrame: {str(e)}")
                return None, None
            
            # Edge case 2: Отсутствие обязательных полей
            required_fields = ['date', 'cases']
            missing_fields = [field for field in required_fields if field not in df.columns]
            if missing_fields:
                logger.warning(f"Отсутствуют обязательные поля: {missing_fields}")
                return None, None
            
            # Edge case 3: Некорректные даты
            try:
                df['date'] = pd.to_datetime(df['date'], errors='coerce')
                # Удаляем строки с некорректными датами
                invalid_dates = df['date'].isna().sum()
                if invalid_dates > 0:
                    logger.warning(f"Удалено {invalid_dates} записей с некорректными датами")
                    df = df.dropna(subset=['date'])
            except Exception as e:
                logger.error(f"Ошибка конвертации дат: {str(e)}")
                return None, None
            
            # Edge case 4: Некорректные значения cases
            try:
                df['cases'] = pd.to_numeric(df['cases'], errors='coerce').fillna(0).astype(int)
                # Удаляем отрицательные значения (если есть)
                negative_cases = (df['cases'] < 0).sum()
                if negative_cases > 0:
                    logger.warning(f"Исправлено {negative_cases} записей с отрицательными значениями")
                    df.loc[df['cases'] < 0, 'cases'] = 0
            except Exception as e:
                logger.error(f"Ошибка обработки cases: {str(e)}")
                return None, None
            
            if len(df) < 10:
                logger.warning(f"После очистки недостаточно данных: {len(df)} < 10")
                return None, None
            
            df = df.sort_values('date')
            
            # Группируем по неделям для более стабильных прогнозов
            try:
                df['year'] = df['date'].dt.year
                df['week'] = df['date'].dt.isocalendar().week
                df['year_week'] = df['year'].astype(str) + '_' + df['week'].astype(str).str.zfill(2)
            except Exception as e:
                logger.error(f"Ошибка группировки по неделям: {str(e)}")
                return None, None
            
            try:
                weekly_data = df.groupby('year_week').agg({
                    'cases': 'sum',
                    'date': 'min'
                }).reset_index()
            except Exception as e:
                logger.error(f"Ошибка агрегации данных: {str(e)}")
                return None, None
            
            weekly_data = weekly_data.sort_values('date')
            
            # Edge case 5: Недостаточно недель после группировки
            if len(weekly_data) < 8:
                logger.warning(f"Недостаточно недельных данных для обучения: {len(weekly_data)} < 8")
                return None, None
            
            # Edge case 6: Все значения cases равны нулю
            if weekly_data['cases'].sum() == 0:
                logger.warning("Все значения cases равны нулю")
                return None, None
            
            # Создаем признаки для модели
            features = []
            targets = []
            
            # Используем скользящее окно из 4 недель для предсказания следующей
            window_size = 4
            
            for i in range(window_size, len(weekly_data)):
                try:
                    # Признаки: значения за последние 4 недели
                    X = weekly_data['cases'].iloc[i-window_size:i].values
                    # Целевая переменная: значение на следующей неделе
                    y = weekly_data['cases'].iloc[i]
                    
                    # Edge case 7: Проверка на NaN или inf
                    if np.any(np.isnan(X)) or np.any(np.isinf(X)) or np.isnan(y) or np.isinf(y):
                        logger.debug(f"Пропуск примера {i} из-за NaN/Inf значений")
                        continue
                    
                    # Edge case 8: Проверка на разумность значений
                    if np.any(X < 0) or y < 0:
                        logger.debug(f"Пропуск примера {i} из-за отрицательных значений")
                        continue
                    
                    features.append(X)
                    targets.append(y)
                except Exception as e:
                    logger.debug(f"Ошибка обработки примера {i}: {str(e)}")
                    continue
            
            # Edge case 9: Недостаточно примеров после обработки
            if len(features) < 4:
                logger.warning(f"Недостаточно примеров для обучения после обработки: {len(features)} < 4")
                return None, None
            
            try:
                X = np.array(features)
                y = np.array(targets)
                
                # Edge case 10: Проверка финальных массивов
                if X.size == 0 or y.size == 0:
                    logger.warning("Пустые массивы после обработки")
                    return None, None
                
                if X.shape[0] != y.shape[0]:
                    logger.warning(f"Несоответствие размеров: X={X.shape}, y={y.shape}")
                    return None, None
                
            except Exception as e:
                logger.error(f"Ошибка создания массивов: {str(e)}")
                return None, None
            
            logger.info(f"Подготовлено {len(X)} примеров для обучения модели")
            return X, y
            
        except Exception as e:
            logger.error(f"Критическая ошибка при подготовке данных: {str(e)}", exc_info=True)
            return None, None
    
    def train_model(self, historical_data):
        """Обучение модели на исторических данных"""
        if not SKLEARN_AVAILABLE:
            logger.warning("scikit-learn недоступен, используем простое прогнозирование")
            return False
        try:
            X, y = self.prepare_data(historical_data)
            
            if X is None or y is None:
                logger.warning("Не удалось подготовить данные для обучения")
                return False
            
            # Разделяем на обучающую и тестовую выборки
            if len(X) > 5:
                X_train, X_test, y_train, y_test = train_test_split(
                    X, y, test_size=0.2, random_state=42
                )
            else:
                X_train, y_train = X, y
                X_test, y_test = None, None
            
            # Нормализуем данные
            X_train_scaled = self.scaler.fit_transform(X_train)
            
            # Используем улучшенное обучение с метриками и ансамблем
            if ENHANCED_ML_AVAILABLE and self.model_metrics:
                return self._train_enhanced_models(X_train, X_test, y_train, y_test, X_train_scaled, X_test_scaled)
            else:
                # Базовое обучение (старый код)
                try:
                    from xgboost import XGBRegressor
                    xgboost_available = True
                except ImportError:
                    xgboost_available = False
                    logger.debug("XGBoost недоступен, используем только scikit-learn модели")
                
                models = {
                    'linear': LinearRegression(),
                    'random_forest': RandomForestRegressor(n_estimators=100, max_depth=5, random_state=42)
                }
                
                if xgboost_available:
                    models['xgboost'] = XGBRegressor(n_estimators=100, max_depth=5, random_state=42, verbosity=0)
                
                best_model = None
                best_score = float('inf')
                
                for name, model in models.items():
                    try:
                        model.fit(X_train_scaled, y_train)
                        
                        if X_test is not None:
                            X_test_scaled = self.scaler.transform(X_test)
                            y_pred = model.predict(X_test_scaled)
                            score = mean_absolute_error(y_test, y_pred)
                        else:
                            y_pred_train = model.predict(X_train_scaled)
                            score = mean_absolute_error(y_train, y_pred_train)
                        
                        if score < best_score:
                            best_score = score
                            best_model = model
                            logger.info(f"Модель {name} показала MAE: {score:.2f}")
                    except Exception as e:
                        logger.warning(f"Ошибка при обучении модели {name}: {str(e)}")
                        continue
                
                if best_model is None:
                    logger.error("Не удалось обучить ни одну модель")
                    return False
                
                self.model = best_model
                self.is_trained = True
                
                logger.info(f"Модель успешно обучена. Лучшая MAE: {best_score:.2f}")
                return True
            
        except Exception as e:
            logger.error(f"Ошибка при обучении модели: {str(e)}", exc_info=True)
            return False
    
    def predict_next_weeks(self, historical_data, weeks_ahead=52):
        """Прогнозирование активности на следующие недели"""
        if not SKLEARN_AVAILABLE:
            return self._simple_predict(historical_data, weeks_ahead)
        try:
            if not self.is_trained or self.model is None:
                # Пытаемся обучить модель
                if not self.train_model(historical_data):
                    logger.warning("Модель не обучена, используем простой прогноз")
                    return self._simple_predict(historical_data, weeks_ahead)
            
            # Подготавливаем последние данные
            df = pd.DataFrame(historical_data)
            df['date'] = pd.to_datetime(df['date'])
            df = df.sort_values('date')
            
            # Группируем по неделям
            df['year'] = df['date'].dt.year
            df['week'] = df['date'].dt.isocalendar().week
            df['year_week'] = df['year'].astype(str) + '_' + df['week'].astype(str).str.zfill(2)
            
            weekly_data = df.groupby('year_week').agg({
                'cases': 'sum',
                'date': 'min'
            }).reset_index().sort_values('date')
            
            if len(weekly_data) < 4:
                return self._simple_predict(historical_data, weeks_ahead)
            
            # Берем последние 4 недели для прогноза
            last_values = weekly_data['cases'].iloc[-4:].values
            
            predictions = []
            current_values = last_values.copy()
            
            # Генерируем прогнозы на несколько недель вперед
            for i in range(weeks_ahead):
                # Подготавливаем признаки
                X = current_values[-4:].reshape(1, -1)
                X_scaled = self.scaler.transform(X)
                
                # Делаем прогноз
                pred = self.model.predict(X_scaled)[0]
                
                # Убеждаемся, что прогноз не отрицательный
                pred = max(0, int(pred))
                
                predictions.append(pred)
                
                # Обновляем окно для следующего прогноза
                current_values = np.append(current_values, pred)
            
            # Создаем даты для прогнозов
            last_date = weekly_data['date'].iloc[-1]
            forecast_dates = []
            current_date = last_date + timedelta(weeks=1)
            
            for i in range(weeks_ahead):
                forecast_dates.append(current_date)
                current_date += timedelta(weeks=1)
            
            # Формируем результат
            forecast = []
            for i, (pred_date, pred_value) in enumerate(zip(forecast_dates, predictions)):
                forecast.append({
                    'date': pred_date.date(),
                    'cases': pred_value,
                    'week_number': i + 1,
                    'is_forecast': True
                })
            
            logger.info(f"Сгенерировано {len(forecast)} прогнозов на будущее")
            return forecast
            
        except Exception as e:
            logger.error(f"Ошибка при прогнозировании: {str(e)}", exc_info=True)
            return self._simple_predict(historical_data, weeks_ahead)
    
    def _simple_predict(self, historical_data, weeks_ahead):
        """Простое прогнозирование на основе среднего значения"""
        try:
            if not historical_data:
                return []
            
            df = pd.DataFrame(historical_data)
            df['date'] = pd.to_datetime(df['date'])
            
            # Берем среднее значение за последние 8 недель
            recent_data = df.sort_values('date').tail(56)  # ~8 недель
            avg_cases = recent_data['cases'].mean() if len(recent_data) > 0 else 0
            
            # Генерируем прогнозы
            last_date = df['date'].max()
            forecast = []
            
            for i in range(weeks_ahead):
                pred_date = last_date + timedelta(weeks=i+1)
                forecast.append({
                    'date': pred_date.date(),
                    'cases': int(avg_cases),
                    'week_number': i + 1,
                    'is_forecast': True
                })
            
            logger.info(f"Сгенерировано {len(forecast)} простых прогнозов")
            return forecast
            
        except Exception as e:
            logger.error(f"Ошибка при простом прогнозировании: {str(e)}")
            return []
    
    def get_forecast_for_2026(self, historical_data):
        """Получение прогноза на 2026 год"""
        try:
            # Фильтруем данные за 2024-2025 годы
            df = pd.DataFrame(historical_data)
            df['date'] = pd.to_datetime(df['date'])
            
            # Берем данные с 2024 года
            start_date = datetime(2024, 1, 1).date()
            filtered_data = [d for d in historical_data if d['date'] >= start_date]
            
            if len(filtered_data) < 10:
                logger.warning("Недостаточно данных за 2024-2025 для прогноза на 2026")
                # Используем все доступные данные
                filtered_data = historical_data
            
            # Вычисляем сколько недель осталось до конца 2026
            today = date.today()
            end_2026 = date(2026, 12, 31)
            
            # Если уже 2026 или позже, прогнозируем до конца года
            if today.year >= 2026:
                weeks_ahead = (end_2026 - today).days // 7
            else:
                # Прогнозируем весь 2026 год
                start_2026 = date(2026, 1, 1)
                weeks_ahead = (end_2026 - start_2026).days // 7
            
            weeks_ahead = max(52, weeks_ahead)  # Минимум год
            
            forecast = self.predict_next_weeks(filtered_data, weeks_ahead)
            
            # Фильтруем только 2026 год
            forecast_2026 = [
                f for f in forecast 
                if f['date'].year == 2026
            ]
            
            logger.info(f"Сгенерирован прогноз на 2026 год: {len(forecast_2026)} недель")
            return forecast_2026
            
        except Exception as e:
            logger.error(f"Ошибка при получении прогноза на 2026: {str(e)}", exc_info=True)
            return []
    
    def generate_news_feed(self, historical_data, days_back=30):
        """Генерация ленты новостей на основе анализа данных"""
        try:
            if not historical_data or len(historical_data) < 5:
                return []
            
            df = pd.DataFrame(historical_data)
            df['date'] = pd.to_datetime(df['date'])
            df = df.sort_values('date')
            
            # Фильтруем данные за последние дни
            cutoff_date = datetime.now().date() - timedelta(days=days_back)
            recent_data = df[df['date'].dt.date >= cutoff_date].copy()
            
            if len(recent_data) == 0:
                return []
            
            news_items = []
            
            # 1. Анализ по локациям - всплески активности
            location_data = recent_data.groupby('location').agg({
                'cases': 'sum',
                'date': 'max'
            }).reset_index()
            location_data = location_data[location_data['location'].notna()]
            location_data = location_data.sort_values('cases', ascending=False)
            
            for _, row in location_data.head(10).iterrows():
                location = row['location']
                cases = row['cases']
                last_date = row['date'].date()
                
                if cases > 0:
                    # Сравниваем с предыдущим периодом
                    prev_cutoff = cutoff_date - timedelta(days=days_back)
                    prev_data = df[(df['date'].dt.date >= prev_cutoff) & 
                                   (df['date'].dt.date < cutoff_date) &
                                   (df['location'] == location)]
                    prev_cases = prev_data['cases'].sum() if len(prev_data) > 0 else 0
                    
                    if cases > prev_cases * 1.5 and cases >= 2:  # Всплеск на 50%+
                        news_items.append({
                            'text': f"Всплеск активности клещей в {location}, {cases} случаев за последние {days_back} дней",
                            'date': last_date,
                            'location': location,
                            'cases': cases,
                            'type': 'spike',
                            'priority': 'high' if cases >= 10 else 'medium'
                        })
                    elif cases >= 5:
                        news_items.append({
                            'text': f"Повышенная активность клещей в {location}, зарегистрировано {cases} случаев",
                            'date': last_date,
                            'location': location,
                            'cases': cases,
                            'type': 'activity',
                            'priority': 'medium'
                        })
            
            # 2. Анализ по дням - всплески за день
            daily_data = recent_data.groupby('date').agg({
                'cases': 'sum',
                'location': lambda x: ', '.join(x.dropna().unique()[:3])
            }).reset_index()
            daily_data = daily_data.sort_values('cases', ascending=False)
            
            for _, row in daily_data.head(5).iterrows():
                day_cases = row['cases']
                day_date = row['date'].date()
                locations = row['location']
                
                if day_cases >= 3:
                    # Среднее значение за предыдущие дни
                    prev_days = daily_data[daily_data['date'].dt.date < day_date]
                    avg_cases = prev_days['cases'].mean() if len(prev_days) > 0 else 0
                    
                    if day_cases > avg_cases * 2 and day_cases >= 3:
                        location_str = locations.split(',')[0] if locations else 'Тюменской области'
                        news_items.append({
                            'text': f"Всплеск активности клещей в {location_str}, {int(day_cases)} укуса за день ({day_date.strftime('%d.%m.%Y')})",
                            'date': day_date,
                            'location': location_str,
                            'cases': int(day_cases),
                            'type': 'daily_spike',
                            'priority': 'high'
                        })
            
            # 3. Анализ трендов - растущая активность
            weekly_data = recent_data.groupby(recent_data['date'].dt.isocalendar().week).agg({
                'cases': 'sum'
            }).reset_index()
            
            if len(weekly_data) >= 3:
                # Проверяем тренд
                recent_week = weekly_data['cases'].tail(1).values[0]
                prev_weeks = weekly_data['cases'].tail(3).head(2).mean()
                
                if recent_week > prev_weeks * 1.3 and recent_week >= 5:
                    news_items.append({
                        'text': f"Наблюдается рост активности клещей, за последнюю неделю зарегистрировано {int(recent_week)} случаев",
                        'date': datetime.now().date(),
                        'location': None,
                        'cases': int(recent_week),
                        'type': 'trend',
                        'priority': 'medium'
                    })
            
            # 4. Сводка по районам
            top_locations = location_data.head(3)
            if len(top_locations) > 0:
                total_cases = top_locations['cases'].sum()
                if total_cases >= 10:
                    locations_list = ', '.join(top_locations['location'].tolist())
                    news_items.append({
                        'text': f"Наибольшая активность клещей в районах: {locations_list} (всего {int(total_cases)} случаев)",
                        'date': datetime.now().date(),
                        'location': locations_list,
                        'cases': int(total_cases),
                        'type': 'summary',
                        'priority': 'low'
                    })
            
            # Сортируем по приоритету и дате
            priority_order = {'high': 3, 'medium': 2, 'low': 1}
            news_items.sort(key=lambda x: (priority_order.get(x['priority'], 0), x['date']), reverse=True)
            
            # Ограничиваем количество
            news_items = news_items[:20]
            
            logger.info(f"Сгенерировано {len(news_items)} новостных сообщений")
            return news_items
            
        except Exception as e:
            logger.error(f"Ошибка при генерации ленты новостей: {str(e)}", exc_info=True)
            return []

