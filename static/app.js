// JavaScript для веб-приложения
let activityChart = null;
let map = null;
let mapMarkers = [];

// Загрузка данных при старте
document.addEventListener('DOMContentLoaded', function() {
    loadStats();
    loadGraph();
    loadSources();
    initMap();
    loadMapData();
    
    // Устанавливаем даты по умолчанию (последние 2 месяца)
    const endDate = new Date();
    const startDate = new Date();
    startDate.setMonth(startDate.getMonth() - 2);
    
    document.getElementById('endDate').value = endDate.toISOString().split('T')[0];
    document.getElementById('startDate').value = startDate.toISOString().split('T')[0];
});

// Инициализация карты
function initMap() {
    // Центр карты - Тюменская область
    map = L.map('map').setView([57.1522, 65.5272], 7);
    
    // Добавляем слой карты OpenStreetMap
    L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
        attribution: '© OpenStreetMap contributors',
        maxZoom: 18
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

// Загрузка источников
async function loadSources() {
    try {
        const response = await fetch('/api/sources?limit=20');
        const data = await response.json();
        
        const sourcesList = document.getElementById('sourcesList');
        
        if (data.sources && data.sources.length > 0) {
            sourcesList.innerHTML = data.sources.map(source => `
                <div class="source-item">
                    <div class="source-header">
                        <div class="source-title">${escapeHtml(source.title || 'Без заголовка')}</div>
                        <div class="source-date">${source.date || '-'}</div>
                    </div>
                    <div class="source-meta">
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
        } else {
            sourcesList.innerHTML = '<div class="loading">Нет данных</div>';
        }
    } catch (error) {
        console.error('Ошибка загрузки источников:', error);
        document.getElementById('sourcesList').innerHTML = '<div class="loading">Ошибка загрузки данных</div>';
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

