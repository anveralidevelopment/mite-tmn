// JavaScript для веб-приложения
let activityChart = null;
let forecastChart = null;
let comparisonChart = null;
let map = null;
let mapMarkers = [];
let isDarkTheme = localStorage.getItem('darkTheme') === 'true';

// Загрузка данных при старте
document.addEventListener('DOMContentLoaded', function() {
    loadStats();
    loadGraph();
    loadSources();
    loadForecast();
    loadNewsFeed();
    loadComparison();
    initMap();
    loadMapData();
    
    // Устанавливаем даты по умолчанию (последние 2 месяца)
    const endDate = new Date();
    const startDate = new Date();
    startDate.setMonth(startDate.getMonth() - 2);
    
    document.getElementById('endDate').value = endDate.toISOString().split('T')[0];
    document.getElementById('startDate').value = startDate.toISOString().split('T')[0];
    
    // Применяем сохраненную тему
    if (isDarkTheme) {
        document.body.classList.add('dark-theme');
    }
    updateThemeIcon();
});

// Инициализация карты
function initMap() {
    // Центр карты - Тюменская область
    map = L.map('map', {
        attributionControl: false
    }).setView([57.1522, 65.5272], 7);
    
    // Используем OpenStreetMap - это международный открытый проект картографии
    // Тайлы карты загружаются с серверов OpenStreetMap
    L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
        maxZoom: 18,
        subdomains: ['a', 'b', 'c']
    }).addTo(map);
    
    // Добавляем свою кастомную атрибуцию без ссылки на Leaflet
    L.control.attribution({
        prefix: '© Карты России | OpenStreetMap'
    }).addTo(map);
}

// Загрузка данных для карты
async function loadMapData(view = 'all') {
    try {
        const response = await fetch(`/api/map-data?view=${view}`);
        const data = await response.json();
        
        // Удаляем старые маркеры
        mapMarkers.forEach(marker => map.removeLayer(marker));
        mapMarkers = [];
        
        if (data.locations && data.locations.length > 0) {
            // Группируем по локациям для объединения случаев
            const locationMap = {};
            
            data.locations.forEach(item => {
                const key = `${item.lat}-${item.lng}`;
                if (!locationMap[key]) {
                    locationMap[key] = {
                        lat: item.lat,
                        lng: item.lng,
                        location: item.location,
                        cases: 0,
                        sources: [],
                        dates: []
                    };
                }
                locationMap[key].cases += item.cases;
                locationMap[key].sources.push(item.source);
                locationMap[key].dates.push(item.date);
            });
            
            // Добавляем маркеры на карту
            Object.values(locationMap).forEach(loc => {
                const riskColor = getRiskColorForCases(loc.cases);
                const icon = L.divIcon({
                    className: 'custom-marker',
                    html: `<div style="background-color: ${riskColor}; width: 20px; height: 20px; border-radius: 50%; border: 2px solid white; box-shadow: 0 2px 4px rgba(0,0,0,0.3);"></div>`,
                    iconSize: [20, 20],
                    iconAnchor: [10, 10]
                });
                
                const marker = L.marker([loc.lat, loc.lng], { icon: icon }).addTo(map);
                
                const popupContent = `
                    <div class="map-popup-title">${escapeHtml(loc.location)}</div>
                    <div class="map-popup-cases">${loc.cases} случаев</div>
                    <div class="map-popup-info">Даты: ${loc.dates.slice(0, 3).join(', ')}${loc.dates.length > 3 ? '...' : ''}</div>
                    <div class="map-popup-info">Источников: ${new Set(loc.sources).size}</div>
                `;
                
                marker.bindPopup(popupContent);
                mapMarkers.push(marker);
            });
            
            // Автоматическое масштабирование карты
            if (mapMarkers.length > 0) {
                const group = new L.featureGroup(mapMarkers);
                map.fitBounds(group.getBounds().pad(0.1));
            }
        } else {
            // Если нет данных, показываем центр области
            map.setView([57.1522, 65.5272], 7);
        }
    } catch (error) {
        console.error('Ошибка загрузки данных карты:', error);
    }
}

// Обновление вида карты
function updateMapView() {
    const view = document.getElementById('mapView').value;
    loadMapData(view);
}

// Получение цвета для количества случаев
function getRiskColorForCases(cases) {
    if (cases === 0) return '#9e9e9e';
    if (cases < 50) return '#00c853';
    if (cases < 100) return '#ffd600';
    if (cases < 150) return '#ff6f00';
    return '#d32f2f';
}

// Загрузка статистики
async function loadStats() {
    try {
        const response = await fetch('/api/stats');
        const data = await response.json();
        
        document.getElementById('currentCases').textContent = data.current_week.cases || 0;
        document.getElementById('currentDate').textContent = data.current_week.date || '-';
        document.getElementById('currentRisk').textContent = `Риск: ${data.current_week.risk_level}`;
        document.getElementById('currentRisk').className = 'stat-risk risk-' + getRiskClass(data.current_week.risk_level);
        
        document.getElementById('previousCases').textContent = data.previous_week.cases || 0;
        document.getElementById('previousDate').textContent = data.previous_week.date || '-';
        document.getElementById('previousRisk').textContent = `Риск: ${data.previous_week.risk_level}`;
        document.getElementById('previousRisk').className = 'stat-risk risk-' + getRiskClass(data.previous_week.risk_level);
    } catch (error) {
        console.error('Ошибка загрузки статистики:', error);
    }
}

// Загрузка графика
async function loadGraph(startDate = null, endDate = null) {
    try {
        let url = '/api/graph';
        if (startDate && endDate) {
            url += `?start_date=${startDate}&end_date=${endDate}`;
        }
        
        const response = await fetch(url);
        const data = await response.json();
        
        const ctx = document.getElementById('activityChart').getContext('2d');
        
        if (activityChart) {
            activityChart.destroy();
        }
        
        activityChart = new Chart(ctx, {
            type: 'bar',
            data: {
                labels: data.weeks || [],
                datasets: [{
                    label: 'Количество обращений',
                    data: data.cases || [],
                    backgroundColor: data.colors || [],
                    borderColor: '#ffffff',
                    borderWidth: 2,
                    borderRadius: 8
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: true,
                plugins: {
                    legend: {
                        display: false
                    },
                    tooltip: {
                        backgroundColor: 'rgba(0, 0, 0, 0.8)',
                        padding: 12,
                        titleFont: {
                            size: 14
                        },
                        bodyFont: {
                            size: 14
                        }
                    }
                },
                scales: {
                    y: {
                        beginAtZero: true,
                        grid: {
                            color: 'rgba(0, 0, 0, 0.05)'
                        },
                        ticks: {
                            font: {
                                size: 12
                            }
                        }
                    },
                    x: {
                        grid: {
                            display: false
                        },
                        ticks: {
                            font: {
                                size: 12
                            },
                            maxRotation: 45,
                            minRotation: 45
                        }
                    }
                }
            }
        });
    } catch (error) {
        console.error('Ошибка загрузки графика:', error);
    }
}

// Загрузка источников с фильтрами
async function loadSources() {
    try {
        // Получаем значения фильтров
        const search = document.getElementById('searchInput')?.value || '';
        const location = document.getElementById('locationFilter')?.value || '';
        const source = document.getElementById('sourceFilter')?.value || '';
        const risk = document.getElementById('riskFilter')?.value || '';
        
        // Формируем URL с параметрами
        let url = '/api/sources?limit=50';
        if (search) url += `&search=${encodeURIComponent(search)}`;
        if (location) url += `&location=${encodeURIComponent(location)}`;
        if (source) url += `&source=${encodeURIComponent(source)}`;
        if (risk) url += `&risk_level=${encodeURIComponent(risk)}`;
        
        const response = await fetch(url);
        const data = await response.json();
        
        const sourcesList = document.getElementById('sourcesList');
        
        if (data.sources && data.sources.length > 0) {
            sourcesList.innerHTML = data.sources.map(source => `
                <div class="source-item">
                    <div class="source-header">
                        <div class="source-title">${escapeHtml(source.title || 'Без заголовка')}</div>
                        <div class="source-date">${source.date || '-'}</div>
                    </div>
                    ${source.content ? `<div class="source-content">${escapeHtml(source.content.substring(0, 150))}${source.content.length > 150 ? '...' : ''}</div>` : ''}
                    <div class="source-meta">
                        ${source.location ? `<span class="source-meta-item"><strong>Локация:</strong> ${escapeHtml(source.location)}</span>` : ''}
                        <span class="source-meta-item">
                            <strong>Случаев:</strong> ${source.cases || 0}
                        </span>
                        <span class="source-meta-item">
                            <strong>Риск:</strong> 
                            <span class="stat-risk risk-${getRiskClass(source.risk_level)}">${source.risk_level || 'Нет данных'}</span>
                        </span>
                        <span class="source-meta-item">
                            <strong>Источник:</strong> ${source.source || 'Неизвестно'}
                        </span>
                        ${source.url ? `<a href="${source.url}" target="_blank" class="source-link">Открыть ссылку →</a>` : ''}
                    </div>
                </div>
            `).join('');
            
            // Обновляем списки фильтров
            updateFilterOptions(data.sources);
        } else {
            sourcesList.innerHTML = '<div class="loading">Нет данных, соответствующих фильтрам</div>';
        }
    } catch (error) {
        console.error('Ошибка загрузки источников:', error);
        document.getElementById('sourcesList').innerHTML = '<div class="loading">Ошибка загрузки данных</div>';
    }
}

// Применение фильтров источников
function applySourceFilters() {
    loadSources();
}

// Обновление опций фильтров
function updateFilterOptions(sources) {
    // Уникальные локации
    const locations = [...new Set(sources.map(s => s.location).filter(Boolean))];
    const locationSelect = document.getElementById('locationFilter');
    if (locationSelect) {
        const currentValue = locationSelect.value;
        locationSelect.innerHTML = '<option value="">Все локации</option>' + 
            locations.map(loc => `<option value="${escapeHtml(loc)}">${escapeHtml(loc)}</option>`).join('');
        if (currentValue) locationSelect.value = currentValue;
    }
    
    // Уникальные источники
    const sourceTypes = [...new Set(sources.map(s => s.source).filter(Boolean))];
    const sourceSelect = document.getElementById('sourceFilter');
    if (sourceSelect) {
        const currentValue = sourceSelect.value;
        sourceSelect.innerHTML = '<option value="">Все источники</option>' + 
            sourceTypes.map(src => `<option value="${escapeHtml(src)}">${escapeHtml(src)}</option>`).join('');
        if (currentValue) sourceSelect.value = currentValue;
    }
}

// Обновление данных
async function updateData() {
    const overlay = document.getElementById('loadingOverlay');
    overlay.style.display = 'flex';
    
    try {
        const response = await fetch('/api/update', {
            method: 'POST'
        });
        
        const data = await response.json();
        
        if (response.ok) {
            // Ждем немного перед обновлением данных
            setTimeout(() => {
                loadStats();
                loadGraph();
                loadSources();
                overlay.style.display = 'none';
                alert('Данные успешно обновлены!');
            }, 3000);
        } else {
            overlay.style.display = 'none';
            alert('Ошибка обновления данных: ' + (data.error || 'Неизвестная ошибка'));
        }
    } catch (error) {
        overlay.style.display = 'none';
        alert('Ошибка обновления данных: ' + error.message);
    }
}

// Применение фильтра
function applyFilter() {
    const startDate = document.getElementById('startDate').value;
    const endDate = document.getElementById('endDate').value;
    
    if (startDate && endDate) {
        loadGraph(startDate, endDate);
    } else {
        loadGraph();
    }
}

// Вспомогательные функции
function getRiskClass(riskLevel) {
    const map = {
        'Низкий': 'low',
        'Умеренный': 'moderate',
        'Высокий': 'high',
        'Очень высокий': 'very-high',
        'Нет данных': 'low'
    };
    return map[riskLevel] || 'low';
}

function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

// Загрузка прогноза
async function loadForecast() {
    try {
        const response = await fetch('/api/forecast');
        const data = await response.json();
        
        if (data.error) {
            document.getElementById('forecastTable').innerHTML = 
                `<p class="loading">${escapeHtml(data.error)}</p>`;
            return;
        }
        
        if (data.forecast && data.forecast.length > 0) {
            // Отображаем график прогноза
            renderForecastChart(data.forecast);
            
            // Отображаем таблицу прогноза
            renderForecastTable(data.forecast);
        } else {
            document.getElementById('forecastTable').innerHTML = 
                '<p class="loading">Недостаточно данных для прогноза</p>';
        }
    } catch (error) {
        console.error('Ошибка загрузки прогноза:', error);
        document.getElementById('forecastTable').innerHTML = 
            '<p class="loading">Ошибка загрузки прогноза</p>';
    }
}

// Отрисовка графика прогноза
function renderForecastChart(forecastData) {
    try {
        const ctx = document.getElementById('forecastChart').getContext('2d');
        
        if (forecastChart) {
            forecastChart.destroy();
        }
        
        const months = forecastData.map(item => item.month);
        const cases = forecastData.map(item => item.total_cases);
        const avgWeekly = forecastData.map(item => item.avg_weekly);
        
        // Определяем цвета в зависимости от уровня риска
        const colors = cases.map(total => {
            if (total < 200) return '#00c853';  // Низкий
            if (total < 400) return '#ffd600';  // Умеренный
            if (total < 600) return '#ff6f00';   // Высокий
            return '#d32f2f';                    // Очень высокий
        });
        
        forecastChart = new Chart(ctx, {
            type: 'bar',
            data: {
                labels: months,
                datasets: [
                    {
                        label: 'Прогноз случаев в месяц',
                        data: cases,
                        backgroundColor: colors,
                        borderColor: '#ffffff',
                        borderWidth: 2,
                        borderRadius: 8
                    },
                    {
                        label: 'Среднее в неделю',
                        data: avgWeekly,
                        type: 'line',
                        borderColor: '#2066B0',
                        backgroundColor: 'rgba(32, 102, 176, 0.1)',
                        borderWidth: 3,
                        pointRadius: 5,
                        pointBackgroundColor: '#2066B0',
                        tension: 0.4
                    }
                ]
            },
            options: {
                responsive: true,
                maintainAspectRatio: true,
                plugins: {
                    legend: {
                        display: true,
                        position: 'top'
                    },
                    tooltip: {
                        backgroundColor: 'rgba(0, 0, 0, 0.8)',
                        padding: 12,
                        callbacks: {
                            label: function(context) {
                                if (context.datasetIndex === 0) {
                                    return `Всего случаев: ${context.parsed.y}`;
                                } else {
                                    return `Среднее в неделю: ${context.parsed.y}`;
                                }
                            }
                        }
                    },
                    title: {
                        display: true,
                        text: 'Прогноз активности клещей на 2026 год (ML модель)',
                        font: {
                            size: 16
                        },
                        color: '#2c2f33'
                    }
                },
                scales: {
                    y: {
                        beginAtZero: true,
                        title: {
                            display: true,
                            text: 'Количество случаев',
                            font: {
                                size: 14
                            }
                        },
                        grid: {
                            color: 'rgba(0, 0, 0, 0.05)'
                        }
                    },
                    x: {
                        title: {
                            display: true,
                            text: 'Месяцы',
                            font: {
                                size: 14
                            }
                        },
                        grid: {
                            display: false
                        },
                        ticks: {
                            maxRotation: 45,
                            minRotation: 45
                        }
                    }
                }
            }
        });
    } catch (error) {
        console.error('Ошибка отрисовки графика прогноза:', error);
    }
}

// Отрисовка таблицы прогноза
function renderForecastTable(forecastData) {
    const tableContainer = document.getElementById('forecastTable');
    
    if (!forecastData || forecastData.length === 0) {
        tableContainer.innerHTML = '<p class="loading">Нет данных для отображения</p>';
        return;
    }
    
    let tableHTML = `
        <table class="forecast-data-table">
            <thead>
                <tr>
                    <th>Месяц</th>
                    <th>Прогноз случаев</th>
                    <th>Среднее в неделю</th>
                    <th>Уровень риска</th>
                </tr>
            </thead>
            <tbody>
    `;
    
    forecastData.forEach(item => {
        const riskLevel = getRiskLevelForCases(item.total_cases);
        const riskClass = getRiskClass(riskLevel);
        
        tableHTML += `
            <tr>
                <td>${escapeHtml(item.month)}</td>
                <td><strong>${item.total_cases}</strong></td>
                <td>${item.avg_weekly}</td>
                <td><span class="stat-risk risk-${riskClass}">${riskLevel}</span></td>
            </tr>
        `;
    });
    
    tableHTML += `
            </tbody>
        </table>
    `;
    
    tableContainer.innerHTML = tableHTML;
}

function getRiskLevelForCases(totalCases) {
    if (totalCases < 200) return 'Низкий';
    if (totalCases < 400) return 'Умеренный';
    if (totalCases < 600) return 'Высокий';
    return 'Очень высокий';
}

// Загрузка ленты новостей
async function loadNewsFeed() {
    try {
        const response = await fetch('/api/news-feed');
        const data = await response.json();
        
        const newsContainer = document.getElementById('newsFeed');
        
        if (data.error) {
            newsContainer.innerHTML = `<p class="loading">${escapeHtml(data.error)}</p>`;
            return;
        }
        
        if (!data.news || data.news.length === 0) {
            newsContainer.innerHTML = '<p class="loading">Новости не найдены</p>';
            return;
        }
        
        let newsHTML = '<div class="news-feed-list">';
        
        data.news.forEach((item, index) => {
            const priorityClass = `priority-${item.priority || 'low'}`;
            const typeIcon = getTypeIcon(item.type);
            
            newsHTML += `
                <div class="news-item ${priorityClass}" data-index="${index}">
                    <div class="news-item-icon">${typeIcon}</div>
                    <div class="news-item-content">
                        <div class="news-item-text">${escapeHtml(item.text)}</div>
                        <div class="news-item-meta">
                            <span class="news-item-date">${escapeHtml(item.date)}</span>
                            ${item.location ? `<span class="news-item-location">${escapeHtml(item.location)}</span>` : ''}
                            ${item.cases > 0 ? `<span class="news-item-cases">${item.cases} случаев</span>` : ''}
                        </div>
                    </div>
                </div>
            `;
        });
        
        newsHTML += '</div>';
        newsContainer.innerHTML = newsHTML;
        
    } catch (error) {
        console.error('Ошибка загрузки ленты новостей:', error);
        document.getElementById('newsFeed').innerHTML = 
            '<p class="loading">Ошибка загрузки новостей</p>';
    }
}

function getTypeIcon(type) {
    const icons = {
        'spike': '📈',
        'daily_spike': '⚡',
        'activity': '📊',
        'trend': '📉',
        'summary': '📋',
        'info': 'ℹ️'
    };
    return icons[type] || '📰';
}

// Экспорт данных
function exportData(format) {
    const startDate = document.getElementById('startDate').value;
    const endDate = document.getElementById('endDate').value;
    
    let url = `/api/export/${format}`;
    if (startDate && endDate) {
        url += `?start_date=${startDate}&end_date=${endDate}`;
    }
    
    window.location.href = url;
    hideExportMenu();
}

function showExportMenu() {
    document.getElementById('exportMenu').style.display = 'block';
}

function hideExportMenu() {
    document.getElementById('exportMenu').style.display = 'none';
}

// Переключение темы
function toggleTheme() {
    isDarkTheme = !isDarkTheme;
    localStorage.setItem('darkTheme', isDarkTheme);
    document.body.classList.toggle('dark-theme', isDarkTheme);
    updateThemeIcon();
}

function updateThemeIcon() {
    const themeBtn = document.getElementById('themeBtn');
    if (themeBtn) {
        themeBtn.querySelector('.btn-icon').textContent = isDarkTheme ? '☀️' : '🌙';
    }
}

// Загрузка сравнения годов
async function loadComparison() {
    try {
        const response = await fetch('/api/analytics/compare');
        const data = await response.json();
        
        if (data.comparison) {
            renderComparisonChart(data.comparison);
        }
    } catch (error) {
        console.error('Ошибка загрузки сравнения:', error);
    }
}

function renderComparisonChart(comparison) {
    const ctx = document.getElementById('comparisonChart');
    if (!ctx) return;
    
    if (comparisonChart) {
        comparisonChart.destroy();
    }
    
    const years = Object.keys(comparison).sort();
    const totals = years.map(year => comparison[year].total_cases);
    const averages = years.map(year => comparison[year].avg_per_month);
    
    comparisonChart = new Chart(ctx, {
        type: 'bar',
        data: {
            labels: years,
            datasets: [
                {
                    label: 'Всего случаев за год',
                    data: totals,
                    backgroundColor: '#2066B0',
                    borderColor: '#185a9a',
                    borderWidth: 2
                },
                {
                    label: 'Среднее в месяц',
                    data: averages,
                    type: 'line',
                    borderColor: '#00c853',
                    backgroundColor: 'rgba(0, 200, 83, 0.1)',
                    borderWidth: 3,
                    pointRadius: 5
                }
            ]
        },
        options: {
            responsive: true,
            plugins: {
                legend: {
                    display: true,
                    position: 'top'
                },
                title: {
                    display: true,
                    text: 'Сравнение активности клещей по годам',
                    font: {
                        size: 16
                    }
                }
            },
            scales: {
                y: {
                    beginAtZero: true
                }
            }
        }
    });
}

function clearFilter() {
    document.getElementById('startDate').value = '';
    document.getElementById('endDate').value = '';
    loadGraph();
}

// Применение темы при загрузке
document.addEventListener('DOMContentLoaded', function() {
    if (isDarkTheme) {
        document.body.classList.add('dark-theme');
    }
    updateThemeIcon();
});

