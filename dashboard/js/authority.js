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

        const resCameras = await fetch(`${API_BASE}/cameras`);
        const cameras = await resCameras.json();
        
        // Initialize Map
        if (!map) {
            map = L.map('map').setView([26.16, 91.76], 12);
            L.tileLayer('https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png', {
                attribution: '&copy; OpenStreetMap',
                subdomains: 'abcd',
                maxZoom: 19
            }).addTo(map);
        }

        // Add markers
        cameras.forEach(c => {
            const color = c.status === 'HEALTHY' ? '#00e676' : '#ff1744';
            const markerHtml = `
                <div style="background-color: ${color}; width: 15px; height: 15px; border-radius: 50%; border: 2px solid white; box-shadow: 0 0 10px ${color};"></div>
            `;
            const icon = L.divIcon({ html: markerHtml, className: 'custom-icon' });
            L.marker([c.latitude, c.longitude], { icon }).addTo(map)
                .bindPopup(`<b>${c.location_name}</b><br/>ID: ${c.external_id}<br/>Status: ${c.status}`);
        });

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
