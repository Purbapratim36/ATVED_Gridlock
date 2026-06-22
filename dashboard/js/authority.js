const API_BASE = "http://localhost:8000/api/v1";
let map;

async function loadData() {
    try {
        const resStats = await fetch(`${API_BASE}/stats`);
        const stats = await resStats.json();

        // Update KPIs with simple count-up animation
        animateValue('statFines', 0, stats.total_fines_issued || 0, 1000, '');
        animateValue('statRevenue', 0, stats.total_revenue || 0, 1000, '₹');
        animateValue('statPending', 0, stats.pending_collection || 0, 1000, '₹');
        animateValue('statDrivers', 0, stats.registered_drivers || 0, 1000, '');

        // Render Chart Curve instead of Map
        if (!map) {
            const ctx = document.getElementById('violationsChart').getContext('2d');
            
            // Create a nice curvy demo graph representing 7-day historical trend
            const labels = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Today"];
            // Base historical data + real time stats from today
            const baseData = [45, 52, 38, 65, 48, 55];
            const todayCount = stats.total_fines_issued || 14;
            const data = [...baseData, todayCount];

            // Create beautiful gradient fill
            const gradient = ctx.createLinearGradient(0, 0, 0, 400);
            gradient.addColorStop(0, 'rgba(0, 240, 255, 0.4)');
            gradient.addColorStop(1, 'rgba(0, 240, 255, 0.0)');

            map = new Chart(ctx, {
                type: 'line',
                data: {
                    labels: labels,
                    datasets: [{
                        label: 'Total Violations',
                        data: data,
                        borderColor: '#00f0ff',
                        backgroundColor: gradient,
                        borderWidth: 3,
                        pointBackgroundColor: '#00f0ff',
                        pointBorderColor: '#fff',
                        pointHoverBackgroundColor: '#fff',
                        pointHoverBorderColor: '#00f0ff',
                        pointRadius: 6,
                        pointHoverRadius: 8,
                        fill: true,
                        tension: 0.4 // Makes the line a beautiful smooth curve
                    }]
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    plugins: {
                        legend: { display: false },
                        tooltip: {
                            backgroundColor: 'rgba(10, 11, 26, 0.9)',
                            titleColor: '#00f0ff',
                            bodyColor: '#fff',
                            borderColor: 'rgba(0, 240, 255, 0.3)',
                            borderWidth: 1,
                            padding: 10,
                            displayColors: false
                        }
                    },
                    scales: {
                        y: {
                            beginAtZero: true,
                            grid: { color: 'rgba(255, 255, 255, 0.05)' },
                            ticks: { color: '#aaa', stepSize: 10 }
                        },
                        x: {
                            grid: { display: false },
                            ticks: { color: '#aaa', font: { size: 12 } }
                        }
                    }
                }
            });
        } else {
            // Update existing chart with new today count
            const todayCount = stats.total_fines_issued || 14;
            map.data.datasets[0].data[6] = todayCount;
            map.update();
        }

        const resFines = await fetch(`${API_BASE}/fines`);
        const fines = await resFines.json();

        const tbody = document.querySelector('#violationsTable tbody');
        tbody.innerHTML = "";

        fines.slice(0, 15).forEach(f => {
            const tr = document.createElement('tr');
            const d = new Date(f.created_at);
            const dName = f.driver ? f.driver.name : "Unknown/Unregistered";
            const score = f.driver ? f.driver.traffic_score : "---";
            const vType = f.violation ? f.violation.violation_type.replace('_', ' ') : "MANUAL";
            
            tr.innerHTML = `
                <td>${d.toLocaleTimeString([], {hour: '2-digit', minute:'2-digit'})}</td>
                <td>${dName}</td>
                <td style="font-family: monospace;">${score}</td>
                <td><span class="tag" style="background: rgba(255,23,68,0.2); color: var(--danger); border: 1px solid var(--danger);">${vType}</span></td>
                <td><a href="http://localhost:8000/pdf/${f.violation_record_id}.pdf" target="_blank" style="padding: 4px 8px; background: var(--accent-primary); color: white; border-radius: 4px; text-decoration: none; font-size: 0.8rem;">View PDF</a></td>
            `;
            tbody.appendChild(tr);
        });

    } catch (e) {
        console.error("Control Room Fetch Error:", e);
    }
}

// Simple counter animation
function animateValue(id, start, end, duration, prefix) {
    if (start === end) {
        document.getElementById(id).innerText = prefix + end.toLocaleString('en-IN');
        return;
    }
    let range = end - start;
    let current = start;
    let increment = end > start ? Math.ceil(range / 20) : -1;
    let stepTime = Math.abs(Math.floor(duration / (range / increment)));
    if(stepTime < 20) stepTime = 20; // limit framerate
    
    let obj = document.getElementById(id);
    let timer = setInterval(function() {
        current += increment;
        if (current >= end) {
            current = end;
            clearInterval(timer);
        }
        obj.innerText = prefix + current.toLocaleString('en-IN');
    }, stepTime);
}

window.onload = () => {
    loadData();
    // Auto refresh every 10 seconds
    setInterval(loadData, 10000);
};
