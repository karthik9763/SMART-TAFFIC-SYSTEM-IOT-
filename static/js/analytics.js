/* Chart.js Analytics Visualizations */

let countTrendChart = null;
let densityPieChart = null;
let vehicleBarChart = null;

document.addEventListener('DOMContentLoaded', () => {
    initCharts();
    loadAnalyticsData();
});

async function loadAnalyticsData() {
    try {
        const resp = await fetch('/api/traffic_data');
        if (resp.ok) {
            const data = await resp.json();
            renderTrendChart(data.labels, data.counts, data.speeds);
            renderDensityPieChart(data.densities);
        }
    } catch (err) {
        console.error("Failed to load analytics data:", err);
    }
}

function initCharts() {
    // Defaults for Chart.js Dark Mode Styling
    Chart.defaults.color = '#94a3b8';
    Chart.defaults.borderColor = 'rgba(255, 255, 255, 0.08)';
    Chart.defaults.font.family = "'Inter', sans-serif";
}

function renderTrendChart(labels, counts, speeds) {
    const ctx = document.getElementById('countTrendChart');
    if (!ctx) return;

    if (countTrendChart) countTrendChart.destroy();

    countTrendChart = new Chart(ctx, {
        type: 'line',
        data: {
            labels: labels,
            datasets: [
                {
                    label: 'Vehicle Count',
                    data: counts,
                    borderColor: '#00f2fe',
                    backgroundColor: 'rgba(0, 242, 254, 0.15)',
                    fill: true,
                    tension: 0.4,
                    borderWidth: 2,
                    yAxisID: 'y'
                },
                {
                    label: 'Avg Speed (km/h)',
                    data: speeds,
                    borderColor: '#10b981',
                    borderDash: [5, 5],
                    fill: false,
                    tension: 0.3,
                    borderWidth: 2,
                    yAxisID: 'y1'
                }
            ]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            interaction: { mode: 'index', intersect: false },
            scales: {
                y: {
                    type: 'linear',
                    display: true,
                    position: 'left',
                    title: { display: true, text: 'Vehicle Count' },
                    grid: { color: 'rgba(255,255,255,0.05)' }
                },
                y1: {
                    type: 'linear',
                    display: true,
                    position: 'right',
                    title: { display: true, text: 'Speed (km/h)' },
                    grid: { drawOnChartArea: false }
                }
            }
        }
    });
}

function renderDensityPieChart(densities) {
    const ctx = document.getElementById('densityPieChart');
    if (!ctx) return;

    let low = 0, med = 0, high = 0;
    densities.forEach(d => {
        if (d === 'Low') low++;
        else if (d === 'Medium') med++;
        else if (d === 'High') high++;
    });

    if (densityPieChart) densityPieChart.destroy();

    densityPieChart = new Chart(ctx, {
        type: 'doughnut',
        data: {
            labels: ['Low Density', 'Medium Density', 'High Density'],
            datasets: [{
                data: [low, med, high],
                backgroundColor: ['#10b981', '#f59e0b', '#ef4444'],
                borderWidth: 0
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: { position: 'bottom' }
            }
        }
    });
}
