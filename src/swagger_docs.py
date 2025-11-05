"""Swagger документация для API"""
from flask import jsonify

SWAGGER_DEFINITION = {
    "swagger": "2.0",
    "info": {
        "title": "Монитор активности клещей - API",
        "description": "API для мониторинга активности клещей в Тюменской области",
        "version": "2.0",
        "contact": {
            "name": "Разработчик",
            "url": "https://anverali.ru/"
        }
    },
    "basePath": "/api",
    "schemes": ["http", "https"],
    "tags": [
        {
            "name": "Статистика",
            "description": "Получение статистики активности клещей"
        },
        {
            "name": "Источники",
            "description": "Работа с источниками данных"
        },
        {
            "name": "Графики",
            "description": "Данные для построения графиков"
        },
        {
            "name": "Карта",
            "description": "Данные для интерактивной карты"
        },
        {
            "name": "Прогноз",
            "description": "ML прогнозы активности клещей"
        },
        {
            "name": "Новости",
            "description": "Лента новостей, сгенерированная ML"
        },
        {
            "name": "Экспорт",
            "description": "Экспорт данных в различных форматах"
        },
        {
            "name": "Аналитика",
            "description": "Аналитические данные и сравнения"
        },
        {
            "name": "Управление",
            "description": "Управление данными и обновления"
        }
    ],
    "paths": {
        "/stats": {
            "get": {
                "tags": ["Статистика"],
                "summary": "Получение статистики",
                "description": "Возвращает статистику текущей и прошлой недели",
                "responses": {
                    "200": {
                        "description": "Успешный ответ",
                        "schema": {
                            "type": "object",
                            "properties": {
                                "current_week": {
                                    "type": "object",
                                    "properties": {
                                        "cases": {"type": "integer"},
                                        "date": {"type": "string"},
                                        "risk_level": {"type": "string"}
                                    }
                                },
                                "previous_week": {
                                    "type": "object",
                                    "properties": {
                                        "cases": {"type": "integer"},
                                        "date": {"type": "string"},
                                        "risk_level": {"type": "string"}
                                    }
                                }
                            }
                        }
                    },
                    "500": {
                        "description": "Ошибка сервера"
                    }
                }
            }
        },
        "/sources": {
            "get": {
                "tags": ["Источники"],
                "summary": "Получение списка источников",
                "description": "Возвращает список источников данных с возможностью фильтрации и поиска",
                "parameters": [
                    {
                        "name": "limit",
                        "in": "query",
                        "type": "integer",
                        "description": "Максимальное количество записей",
                        "default": 20
                    },
                    {
                        "name": "search",
                        "in": "query",
                        "type": "string",
                        "description": "Поисковый запрос (поиск в заголовке и содержании)"
                    },
                    {
                        "name": "location",
                        "in": "query",
                        "type": "string",
                        "description": "Фильтр по локации"
                    },
                    {
                        "name": "source",
                        "in": "query",
                        "type": "string",
                        "description": "Фильтр по источнику"
                    },
                    {
                        "name": "risk_level",
                        "in": "query",
                        "type": "string",
                        "description": "Фильтр по уровню риска (Низкий, Умеренный, Высокий, Очень высокий)"
                    },
                    {
                        "name": "start_date",
                        "in": "query",
                        "type": "string",
                        "format": "date",
                        "description": "Начальная дата (YYYY-MM-DD)"
                    },
                    {
                        "name": "end_date",
                        "in": "query",
                        "type": "string",
                        "format": "date",
                        "description": "Конечная дата (YYYY-MM-DD)"
                    }
                ],
                "responses": {
                    "200": {
                        "description": "Успешный ответ",
                        "schema": {
                            "type": "object",
                            "properties": {
                                "sources": {
                                    "type": "array",
                                    "items": {"type": "object"}
                                },
                                "total": {"type": "integer"},
                                "filters_applied": {"type": "object"}
                            }
                        }
                    }
                }
            }
        },
        "/graph": {
            "get": {
                "tags": ["Графики"],
                "summary": "Данные для графика",
                "description": "Возвращает данные для построения графика активности",
                "parameters": [
                    {
                        "name": "start_date",
                        "in": "query",
                        "type": "string",
                        "format": "date",
                        "description": "Начальная дата (YYYY-MM-DD)"
                    },
                    {
                        "name": "end_date",
                        "in": "query",
                        "type": "string",
                        "format": "date",
                        "description": "Конечная дата (YYYY-MM-DD)"
                    }
                ],
                "responses": {
                    "200": {
                        "description": "Успешный ответ",
                        "schema": {
                            "type": "object",
                            "properties": {
                                "weeks": {"type": "array", "items": {"type": "string"}},
                                "cases": {"type": "array", "items": {"type": "integer"}},
                                "colors": {"type": "array", "items": {"type": "string"}}
                            }
                        }
                    }
                }
            }
        },
        "/map-data": {
            "get": {
                "tags": ["Карта"],
                "summary": "Данные для карты",
                "description": "Возвращает данные для интерактивной карты",
                "parameters": [
                    {
                        "name": "view",
                        "in": "query",
                        "type": "string",
                        "enum": ["all", "week", "month"],
                        "description": "Период отображения",
                        "default": "all"
                    }
                ],
                "responses": {
                    "200": {
                        "description": "Успешный ответ",
                        "schema": {
                            "type": "object",
                            "properties": {
                                "locations": {
                                    "type": "array",
                                    "items": {
                                        "type": "object",
                                        "properties": {
                                            "lat": {"type": "number"},
                                            "lng": {"type": "number"},
                                            "location": {"type": "string"},
                                            "cases": {"type": "integer"},
                                            "date": {"type": "string"},
                                            "source": {"type": "string"},
                                            "title": {"type": "string"}
                                        }
                                    }
                                }
                            }
                        }
                    }
                }
            }
        },
        "/forecast": {
            "get": {
                "tags": ["Прогноз"],
                "summary": "Прогноз активности на 2026 год",
                "description": "Возвращает ML прогноз активности клещей на 2026 год",
                "responses": {
                    "200": {
                        "description": "Успешный ответ",
                        "schema": {
                            "type": "object",
                            "properties": {
                                "forecast": {
                                    "type": "array",
                                    "items": {
                                        "type": "object",
                                        "properties": {
                                            "month": {"type": "string"},
                                            "total_cases": {"type": "integer"},
                                            "avg_weekly": {"type": "integer"}
                                        }
                                    }
                                },
                                "weekly_forecast": {
                                    "type": "array",
                                    "items": {"type": "object"}
                                }
                            }
                        }
                    }
                }
            }
        },
        "/news-feed": {
            "get": {
                "tags": ["Новости"],
                "summary": "Лента новостей",
                "description": "Возвращает автоматически сгенерированные новости на основе анализа данных",
                "responses": {
                    "200": {
                        "description": "Успешный ответ",
                        "schema": {
                            "type": "object",
                            "properties": {
                                "news": {
                                    "type": "array",
                                    "items": {
                                        "type": "object",
                                        "properties": {
                                            "text": {"type": "string"},
                                            "date": {"type": "string"},
                                            "location": {"type": "string"},
                                            "cases": {"type": "integer"},
                                            "type": {"type": "string"},
                                            "priority": {"type": "string"}
                                        }
                                    }
                                },
                                "count": {"type": "integer"}
                            }
                        }
                    }
                }
            }
        },
        "/export/{format}": {
            "get": {
                "tags": ["Экспорт"],
                "summary": "Экспорт данных",
                "description": "Экспорт данных в различных форматах (CSV, Excel, PDF)",
                "parameters": [
                    {
                        "name": "format",
                        "in": "path",
                        "type": "string",
                        "enum": ["csv", "excel", "pdf"],
                        "required": True,
                        "description": "Формат экспорта"
                    },
                    {
                        "name": "start_date",
                        "in": "query",
                        "type": "string",
                        "format": "date",
                        "description": "Начальная дата (YYYY-MM-DD)"
                    },
                    {
                        "name": "end_date",
                        "in": "query",
                        "type": "string",
                        "format": "date",
                        "description": "Конечная дата (YYYY-MM-DD)"
                    }
                ],
                "responses": {
                    "200": {
                        "description": "Файл для скачивания"
                    },
                    "400": {
                        "description": "Неподдерживаемый формат"
                    }
                }
            }
        },
        "/analytics/compare": {
            "get": {
                "tags": ["Аналитика"],
                "summary": "Сравнение с предыдущими годами",
                "description": "Сравнение данных активности клещей за последние 4 года",
                "responses": {
                    "200": {
                        "description": "Успешный ответ",
                        "schema": {
                            "type": "object",
                            "properties": {
                                "comparison": {
                                    "type": "object",
                                    "additionalProperties": {
                                        "type": "object",
                                        "properties": {
                                            "total_cases": {"type": "integer"},
                                            "records_count": {"type": "integer"},
                                            "avg_per_month": {"type": "number"}
                                        }
                                    }
                                }
                            }
                        }
                    }
                }
            }
        },
        "/update": {
            "post": {
                "tags": ["Управление"],
                "summary": "Обновление данных",
                "description": "Запускает процесс обновления данных из всех источников",
                "responses": {
                    "200": {
                        "description": "Обновление запущено",
                        "schema": {
                            "type": "object",
                            "properties": {
                                "status": {"type": "string"},
                                "message": {"type": "string"}
                            }
                        }
                    }
                }
            }
        },
        "/metrics": {
            "get": {
                "tags": ["Мониторинг"],
                "summary": "Prometheus метрики",
                "description": "Возвращает метрики Prometheus для мониторинга",
                "responses": {
                    "200": {
                        "description": "Метрики в формате Prometheus"
                    }
                }
            }
        }
    }
}


def get_swagger_json():
    """Возвращает JSON Swagger документации"""
    return jsonify(SWAGGER_DEFINITION)

