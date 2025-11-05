"""Улучшенный ML модуль для прогнозирования активности клещей с LSTM, GRU, ансамблями и дополнительными фичами"""
import numpy as np
import pandas as pd
from datetime import datetime, date, timedelta
from logger_config import setup_logger
import json
import os

logger = setup_logger()

# Проверка доступности библиотек
try:
    from sklearn.linear_model import LinearRegression
    from sklearn.ensemble import RandomForestRegressor, VotingRegressor, GradientBoostingRegressor
    from sklearn.preprocessing import StandardScaler, MinMaxScaler
    from sklearn.model_selection import train_test_split, cross_val_score
    from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
    from sklearn.cluster import KMeans
    from sklearn.preprocessing import LabelEncoder
    SKLEARN_AVAILABLE = True
except ImportError:
    SKLEARN_AVAILABLE = False

try:
    from xgboost import XGBRegressor
    XGBOOST_AVAILABLE = True
except ImportError:
    XGBOOST_AVAILABLE = False

try:
    import tensorflow as tf
    from tensorflow import keras
    from tensorflow.keras.models import Sequential
    from tensorflow.keras.layers import LSTM, GRU, Dense, Dropout, Input
    from tensorflow.keras.optimizers import Adam
    TENSORFLOW_AVAILABLE = True
except ImportError:
    TENSORFLOW_AVAILABLE = False
    logger.warning("TensorFlow недоступен, LSTM/GRU модели отключены")

try:
    from scipy import stats
    SCIPY_AVAILABLE = True
except ImportError:
    SCIPY_AVAILABLE = False


class ModelMetrics:
    """Класс для расчета метрик качества моделей"""
    
    @staticmethod
    def calculate_metrics(y_true, y_pred):
        """Расчет метрик качества
        
        Returns:
            dict: Словарь с метриками (R², RMSE, MAPE, MAE)
        """
        try:
            y_true = np.array(y_true)
            y_pred = np.array(y_pred)
            
            # Удаляем NaN и Inf
            mask = np.isfinite(y_true) & np.isfinite(y_pred)
            y_true = y_true[mask]
            y_pred = y_pred[mask]
            
            if len(y_true) == 0:
                return {'r2': 0.0, 'rmse': float('inf'), 'mape': float('inf'), 'mae': float('inf')}
            
            # R²
            r2 = r2_score(y_true, y_pred)
            
            # RMSE
            rmse = np.sqrt(mean_squared_error(y_true, y_pred))
            
            # MAE
            mae = mean_absolute_error(y_true, y_pred)
            
            # MAPE (Mean Absolute Percentage Error)
            # Избегаем деления на ноль
            mask_nonzero = y_true != 0
            if mask_nonzero.sum() > 0:
                mape = np.mean(np.abs((y_true[mask_nonzero] - y_pred[mask_nonzero]) / y_true[mask_nonzero])) * 100
            else:
                mape = float('inf')
            
            return {
                'r2': float(r2),
                'rmse': float(rmse),
                'mape': float(mape),
                'mae': float(mae)
            }
        except Exception as e:
            logger.error(f"Ошибка расчета метрик: {str(e)}")
            return {'r2': 0.0, 'rmse': float('inf'), 'mape': float('inf'), 'mae': float('inf')}


class FeatureEngineering:
    """Класс для создания дополнительных фичей"""
    
    def __init__(self, weather_api=None):
        self.weather_api = weather_api
        self.holidays_ru = self._load_russian_holidays()
    
    def _load_russian_holidays(self):
        """Загрузка списка российских праздников"""
        holidays = []
        current_year = date.today().year
        
        for year in range(current_year - 2, current_year + 3):
            # Новый год
            holidays.extend([
                date(year, 1, 1),  # Новый год
                date(year, 1, 2),  # Продолжение новогодних каникул
                date(year, 1, 3),
                date(year, 1, 4),
                date(year, 1, 5),
                date(year, 1, 6),
                date(year, 1, 7),  # Рождество
                date(year, 1, 8),
            ])
            # День защитника Отечества
            holidays.append(date(year, 2, 23))
            # Международный женский день
            holidays.append(date(year, 3, 8))
            # День Победы
            holidays.append(date(year, 5, 9))
            # День России
            holidays.append(date(year, 6, 12))
            # День народного единства
            holidays.append(date(year, 11, 4))
        
        return set(holidays)
    
    def create_features(self, df, historical_data=None):
        """Создание дополнительных фичей для модели
        
        Args:
            df: DataFrame с данными
            historical_data: Исторические данные для расчета трендов
        
        Returns:
            DataFrame: DataFrame с дополнительными фичами
        """
        df = df.copy()
        
        # Временные фичи
        df['year'] = pd.to_datetime(df['date']).dt.year
        df['month'] = pd.to_datetime(df['date']).dt.month
        df['week'] = pd.to_datetime(df['date']).dt.isocalendar().week
        df['day_of_year'] = pd.to_datetime(df['date']).dt.dayofyear
        df['day_of_week'] = pd.to_datetime(df['date']).dt.dayofweek
        df['is_weekend'] = (pd.to_datetime(df['date']).dt.dayofweek >= 5).astype(int)
        
        # Праздники
        df['is_holiday'] = pd.to_datetime(df['date']).dt.date.isin(self.holidays_ru).astype(int)
        
        # Сезонность (синусы и косинусы для циклических признаков)
        df['month_sin'] = np.sin(2 * np.pi * df['month'] / 12)
        df['month_cos'] = np.cos(2 * np.pi * df['month'] / 12)
        df['day_of_year_sin'] = np.sin(2 * np.pi * df['day_of_year'] / 365)
        df['day_of_year_cos'] = np.cos(2 * np.pi * df['day_of_year'] / 365)
        
        # Тренды (если есть исторические данные)
        if historical_data is not None and len(historical_data) > 0:
            hist_df = pd.DataFrame(historical_data)
            hist_df['date'] = pd.to_datetime(hist_df['date'])
            hist_df = hist_df.sort_values('date')
            
            # Скользящие средние
            for window in [7, 14, 30]:
                hist_df[f'ma_{window}'] = hist_df['cases'].rolling(window=window, min_periods=1).mean()
            
            # Последние значения для расчета трендов
            if len(hist_df) > 0:
                last_week_avg = hist_df['cases'].tail(7).mean()
                last_month_avg = hist_df['cases'].tail(30).mean()
                
                df['last_week_avg'] = last_week_avg
                df['last_month_avg'] = last_month_avg
                df['trend_ratio'] = last_week_avg / max(last_month_avg, 1)
        
        # Погодные данные (если доступны)
        if self.weather_api and self.weather_api.enabled:
            try:
                weather_data = []
                for d in df['date'].unique():
                    w = self.weather_api.get_weather_data(pd.to_datetime(d).date())
                    if w:
                        weather_data.append({
                            'date': pd.to_datetime(d),
                            'temperature': w.get('temperature', 0),
                            'humidity': w.get('humidity', 0),
                            'pressure': w.get('pressure', 0)
                        })
                
                if weather_data:
                    weather_df = pd.DataFrame(weather_data)
                    df = df.merge(weather_df, on='date', how='left')
                    df['temperature'] = df['temperature'].fillna(0)
                    df['humidity'] = df['humidity'].fillna(0)
                    df['pressure'] = df['pressure'].fillna(0)
            except Exception as e:
                logger.warning(f"Ошибка получения погодных данных: {str(e)}")
        
        return df


class LSTMModel:
    """Класс для создания и обучения LSTM модели"""
    
    def __init__(self, sequence_length=7, units=50, dropout=0.2):
        self.sequence_length = sequence_length
        self.units = units
        self.dropout = dropout
        self.model = None
        self.scaler = MinMaxScaler()
    
    def build_model(self, input_shape):
        """Построение архитектуры LSTM модели"""
        if not TENSORFLOW_AVAILABLE:
            return None
        
        try:
            model = Sequential([
                Input(shape=input_shape),
                LSTM(self.units, return_sequences=True),
                Dropout(self.dropout),
                LSTM(self.units // 2, return_sequences=False),
                Dropout(self.dropout),
                Dense(25, activation='relu'),
                Dense(1)
            ])
            
            model.compile(optimizer=Adam(learning_rate=0.001), loss='mse', metrics=['mae'])
            return model
        except Exception as e:
            logger.error(f"Ошибка построения LSTM модели: {str(e)}")
            return None
    
    def prepare_sequences(self, data, target_col='cases'):
        """Подготовка последовательностей для LSTM"""
        try:
            values = data[target_col].values.reshape(-1, 1)
            scaled_values = self.scaler.fit_transform(values)
            
            X, y = [], []
            for i in range(self.sequence_length, len(scaled_values)):
                X.append(scaled_values[i - self.sequence_length:i])
                y.append(scaled_values[i])
            
            return np.array(X), np.array(y)
        except Exception as e:
            logger.error(f"Ошибка подготовки последовательностей: {str(e)}")
            return None, None
    
    def train(self, X, y, epochs=50, batch_size=32, validation_split=0.2):
        """Обучение LSTM модели"""
        if not TENSORFLOW_AVAILABLE or self.model is None:
            return False
        
        try:
            self.model.fit(
                X, y,
                epochs=epochs,
                batch_size=batch_size,
                validation_split=validation_split,
                verbose=0
            )
            return True
        except Exception as e:
            logger.error(f"Ошибка обучения LSTM: {str(e)}")
            return False
    
    def predict(self, X):
        """Прогнозирование"""
        if not TENSORFLOW_AVAILABLE or self.model is None:
            return None
        
        try:
            predictions = self.model.predict(X, verbose=0)
            return self.scaler.inverse_transform(predictions)
        except Exception as e:
            logger.error(f"Ошибка прогнозирования LSTM: {str(e)}")
            return None


class GRUModel:
    """Класс для создания и обучения GRU модели"""
    
    def __init__(self, sequence_length=7, units=50, dropout=0.2):
        self.sequence_length = sequence_length
        self.units = units
        self.dropout = dropout
        self.model = None
        self.scaler = MinMaxScaler()
    
    def build_model(self, input_shape):
        """Построение архитектуры GRU модели"""
        if not TENSORFLOW_AVAILABLE:
            return None
        
        try:
            model = Sequential([
                Input(shape=input_shape),
                GRU(self.units, return_sequences=True),
                Dropout(self.dropout),
                GRU(self.units // 2, return_sequences=False),
                Dropout(self.dropout),
                Dense(25, activation='relu'),
                Dense(1)
            ])
            
            model.compile(optimizer=Adam(learning_rate=0.001), loss='mse', metrics=['mae'])
            return model
        except Exception as e:
            logger.error(f"Ошибка построения GRU модели: {str(e)}")
            return None
    
    def prepare_sequences(self, data, target_col='cases'):
        """Подготовка последовательностей для GRU"""
        try:
            values = data[target_col].values.reshape(-1, 1)
            scaled_values = self.scaler.fit_transform(values)
            
            X, y = [], []
            for i in range(self.sequence_length, len(scaled_values)):
                X.append(scaled_values[i - self.sequence_length:i])
                y.append(scaled_values[i])
            
            return np.array(X), np.array(y)
        except Exception as e:
            logger.error(f"Ошибка подготовки последовательностей: {str(e)}")
            return None, None
    
    def train(self, X, y, epochs=50, batch_size=32, validation_split=0.2):
        """Обучение GRU модели"""
        if not TENSORFLOW_AVAILABLE or self.model is None:
            return False
        
        try:
            self.model.fit(
                X, y,
                epochs=epochs,
                batch_size=batch_size,
                validation_split=validation_split,
                verbose=0
            )
            return True
        except Exception as e:
            logger.error(f"Ошибка обучения GRU: {str(e)}")
            return False
    
    def predict(self, X):
        """Прогнозирование"""
        if not TENSORFLOW_AVAILABLE or self.model is None:
            return None
        
        try:
            predictions = self.model.predict(X, verbose=0)
            return self.scaler.inverse_transform(predictions)
        except Exception as e:
            logger.error(f"Ошибка прогнозирования GRU: {str(e)}")
            return None


class EnsembleModel:
    """Ансамбль моделей"""
    
    def __init__(self, models, weights=None):
        self.models = models
        self.weights = weights or [1.0 / len(models)] * len(models)
    
    def predict(self, X):
        """Прогнозирование ансамблем"""
        predictions = []
        
        for model in self.models:
            try:
                if hasattr(model, 'predict'):
                    pred = model.predict(X)
                    predictions.append(pred)
            except Exception as e:
                logger.warning(f"Ошибка прогнозирования модели в ансамбле: {str(e)}")
                continue
        
        if not predictions:
            return None
        
        # Взвешенное усреднение
        predictions = np.array(predictions)
        weights = np.array(self.weights[:len(predictions)])
        weights = weights / weights.sum()
        
        return np.average(predictions, axis=0, weights=weights)


class AnomalyDetector:
    """Детектор аномалий"""
    
    @staticmethod
    def detect_anomalies(data, method='zscore', threshold=3.0):
        """Детекция аномалий в данных
        
        Args:
            data: Массив значений
            method: Метод ('zscore', 'iqr')
            threshold: Порог для детекции
        
        Returns:
            list: Индексы аномальных значений
        """
        try:
            data = np.array(data)
            
            if method == 'zscore':
                if not SCIPY_AVAILABLE:
                    return []
                z_scores = np.abs(stats.zscore(data))
                anomalies = np.where(z_scores > threshold)[0]
            elif method == 'iqr':
                Q1 = np.percentile(data, 25)
                Q3 = np.percentile(data, 75)
                IQR = Q3 - Q1
                lower_bound = Q1 - 1.5 * IQR
                upper_bound = Q3 + 1.5 * IQR
                anomalies = np.where((data < lower_bound) | (data > upper_bound))[0]
            else:
                return []
            
            return anomalies.tolist()
        except Exception as e:
            logger.error(f"Ошибка детекции аномалий: {str(e)}")
            return []


class LocationClusterer:
    """Кластеризация локаций по активности"""
    
    @staticmethod
    def cluster_locations(data, n_clusters=5):
        """Кластеризация локаций по активности клещей
        
        Args:
            data: DataFrame с колонками 'location' и 'cases'
            n_clusters: Количество кластеров
        
        Returns:
            dict: Словарь {location: cluster_id}
        """
        try:
            if not SKLEARN_AVAILABLE:
                return {}
            
            location_stats = data.groupby('location').agg({
                'cases': ['sum', 'mean', 'count']
            }).reset_index()
            location_stats.columns = ['location', 'total_cases', 'avg_cases', 'count']
            
            if len(location_stats) < n_clusters:
                n_clusters = len(location_stats)
            
            if n_clusters < 2:
                return {loc: 0 for loc in location_stats['location']}
            
            features = location_stats[['total_cases', 'avg_cases', 'count']].values
            
            kmeans = KMeans(n_clusters=n_clusters, random_state=42, n_init=10)
            clusters = kmeans.fit_predict(features)
            
            result = dict(zip(location_stats['location'], clusters))
            return result
        except Exception as e:
            logger.error(f"Ошибка кластеризации локаций: {str(e)}")
            return {}


class PreventionRecommendations:
    """Генерация рекомендаций по профилактике"""
    
    @staticmethod
    def generate_recommendations(prediction_data, risk_level):
        """Генерация рекомендаций на основе прогноза
        
        Args:
            prediction_data: Данные прогноза
            risk_level: Уровень риска
        
        Returns:
            list: Список рекомендаций
        """
        recommendations = []
        
        if risk_level in ['high', 'very_high']:
            recommendations.append({
                'type': 'urgent',
                'text': 'Высокая активность клещей прогнозируется. Рекомендуется использовать репелленты и носить закрытую одежду.',
                'priority': 'high'
            })
            recommendations.append({
                'type': 'prevention',
                'text': 'После прогулок на природе обязательно осматривайте тело и одежду на наличие клещей.',
                'priority': 'medium'
            })
            recommendations.append({
                'type': 'vaccination',
                'text': 'Рассмотрите возможность вакцинации против клещевого энцефалита.',
                'priority': 'medium'
            })
        
        elif risk_level == 'moderate':
            recommendations.append({
                'type': 'prevention',
                'text': 'Умеренная активность клещей. Будьте внимательны при посещении лесов и парков.',
                'priority': 'medium'
            })
        
        # Рекомендации на основе сезона
        if prediction_data:
            try:
                month = pd.to_datetime(prediction_data[0].get('date', date.today())).month
                if month in [4, 5, 6, 7, 8, 9]:  # Весна-лето-осень
                    recommendations.append({
                        'type': 'seasonal',
                        'text': 'Пик активности клещей приходится на весенне-летний период. Будьте особенно осторожны.',
                        'priority': 'medium'
                    })
            except:
                pass
        
        return recommendations

