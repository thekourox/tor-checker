const btnStart = document.getElementById('btn-start');
const btnStop = document.getElementById('btn-stop');
const btnXray = document.getElementById('btn-xray');
const badgeStatus = document.getElementById('badge-status');
const discoveryMsg = document.getElementById('discovery-msg');
const discoveryProgress = document.getElementById('discovery-progress');
const instancesBody = document.getElementById('instances-body');
const instanceCount = document.getElementById('instance-count');
const toast = document.getElementById('toast');
const toastMsg = document.getElementById('toast-msg');

let statusInterval;

const regionNames = new Intl.DisplayNames(['en'], { type: 'region' });

function getCountryName(code) {
    try {
        if (!code) return '...';
        if (code === '...' || code === 'UNKNOWN') return code;
        return regionNames.of(code.toUpperCase()) || code.toUpperCase();
    } catch (e) {
        return (code || '...').toString().toUpperCase();
    }
}

function showToast(msg) {
    toastMsg.textContent = msg;
    toast.classList.remove('hidden');
    toast.classList.add('show');
    setTimeout(() => {
        toast.classList.remove('show');
    }, 3000);
}

function updateTable(instances) {
    instancesBody.innerHTML = '';
    const entries = Object.entries(instances);
    instanceCount.textContent = `${entries.length} / 190`;

    entries.forEach(([country, data]) => {
        const tr = document.createElement('tr');
        
        let statusDot = 'status-yellow';
        let statusText = data.status;
        if (statusText.includes('🟢')) {
            statusDot = 'status-green';
            statusText = statusText.replace('🟢 ', '');
        } else if (statusText.includes('🔴')) {
            statusDot = 'status-red';
            statusText = statusText.replace('🔴 ', '');
        } else if (statusText.includes('🟡')) {
            statusDot = 'status-yellow';
            statusText = statusText.replace('🟡 ', '');
        }

        tr.innerHTML = `
            <td class="country-code" title="${country.toUpperCase()}">${getCountryName(country)}</td>
            <td>${data.port}</td>
            <td>${data.ip}</td>
            <td class="ip-location">${getCountryName(data.ip_location)}</td>
            <td>${data.ping}</td>
            <td>${data.speed}</td>
            <td><span class="status-dot ${statusDot}"></span> ${statusText}</td>
        `;
        instancesBody.appendChild(tr);
    });
}

async function fetchStatus() {
    try {
        const res = await fetch('/api/status');
        const data = await res.json();

        // Update Header Status
        if (data.status === 'running') {
            badgeStatus.textContent = 'RUNNING';
            badgeStatus.className = 'badge badge-running';
        } else {
            badgeStatus.textContent = 'IDLE';
            badgeStatus.className = 'badge badge-idle';
        }

        // Update Discovery Phase
        discoveryMsg.textContent = data.discovery_msg;
        if (data.phase === 'discovery') {
            discoveryProgress.style.width = `${data.discovery_progress}%`;
        } else if (data.phase === 'monitoring') {
            discoveryProgress.style.width = `100%`;
        } else {
            discoveryProgress.style.width = `0%`;
        }

        // Update Table
        updateTable(data.instances);

    } catch (e) {
        console.error("Error fetching status:", e);
    }
}

btnStart.addEventListener('click', async () => {
    try {
        const maxCountries = document.getElementById('max-countries').value || 20;
        const setPing = document.getElementById('set-ping').value || 60;
        const setRam = document.getElementById('set-ram').value || 15;
        const setBw = document.getElementById('set-bw').value || 0;
        const setWorkers = document.getElementById('set-workers').value || 0;

        const payload = {
            max_instances: parseInt(maxCountries),
            ping_interval: parseInt(setPing),
            ram_limit_mb: parseInt(setRam),
            bandwidth_limit_kb: parseInt(setBw),
            worker_count: parseInt(setWorkers)
        };

        const res = await fetch('/api/start', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify(payload)
        });
        const data = await res.json();
        showToast(data.message);
    } catch (e) {
        showToast("Error starting network");
    }
});

btnStop.addEventListener('click', async () => {
    try {
        const res = await fetch('/api/stop', { method: 'POST' });
        const data = await res.json();
        showToast(data.message);
    } catch (e) {
        showToast("Error stopping network");
    }
});

btnXray.addEventListener('click', async () => {
    try {
        const res = await fetch('/api/generate_xray', { method: 'POST' });
        if (res.ok) {
            window.location.href = '/api/download_config';
            showToast("Config ready for 3x-ui!");
        } else {
            const data = await res.json();
            showToast(data.message || "Failed to generate");
        }
    } catch (e) {
        showToast("Error generating config");
    }
});

// Modal Logic
const modal = document.getElementById('settings-modal');
const btnSettings = document.getElementById('btn-settings');
const spanClose = document.getElementsByClassName('close-btn')[0];
const btnSaveSettings = document.getElementById('btn-save-settings');

btnSettings.onclick = function() {
    modal.classList.add('show');
}

spanClose.onclick = function() {
    modal.classList.remove('show');
}

btnSaveSettings.onclick = function() {
    modal.classList.remove('show');
    showToast("Settings saved. Press Start to apply.");
}

window.onclick = function(event) {
    if (event.target == modal) {
        modal.classList.remove('show');
    }
}

// Poll every 1.5 seconds
statusInterval = setInterval(fetchStatus, 1500);
fetchStatus();
