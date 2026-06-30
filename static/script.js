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
            <td class="ip-location">${getFlagEmoji(data.ip_location)} ${getCountryName(data.ip_location)}</td>
            <td>${data.ping}</td>
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
        
        const checkboxes = document.querySelectorAll('.country-cb:checked');
        let selectedArr = [];
        checkboxes.forEach(cb => selectedArr.push(cb.value));
        const setCountries = selectedArr.join(",");

        const payload = {
            max_instances: parseInt(maxCountries),
            ping_interval: parseInt(setPing),
            ram_limit_mb: parseInt(setRam),
            bandwidth_limit_kb: parseInt(setBw),
            worker_count: parseInt(setWorkers),
            selected_countries: setCountries
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
    showToast("Settings saved. Press Start to apply (Live Reload supported).");
}

window.onclick = function(event) {
    if (event.target == modal) {
        modal.classList.remove('show');
    }
}

function getFlagEmoji(countryCode) {
    if(!countryCode || countryCode.length !== 2) return '🏳️';
    const codePoints = countryCode.toUpperCase().split('').map(char => 127397 + char.charCodeAt(0));
    return String.fromCodePoint(...codePoints);
}

const btnScan = document.getElementById('btn-scan-countries');
const listContainer = document.getElementById('countries-list');

let savedCountries = [];

btnScan.addEventListener('click', async () => {
    btnScan.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> Scanning (15s)...';
    btnScan.disabled = true;
    listContainer.innerHTML = '<span style="color: var(--text-muted); font-size: 0.8rem; grid-column: span 2;">Downloading live Tor network consensus... please wait.</span>';
    
    try {
        const res = await fetch('/api/scan_countries');
        const data = await res.json();
        
        if(data.status === 'success') {
            listContainer.innerHTML = '';
            data.countries.forEach(code => {
                const isChecked = savedCountries.includes(code.toLowerCase()) ? 'checked' : '';
                const flag = getFlagEmoji(code);
                const html = `
                    <label style="display: flex; align-items: center; gap: 8px; font-size: 0.9rem; cursor: pointer; padding: 4px; border-radius: 4px; transition: background 0.2s;" onmouseover="this.style.background='rgba(255,255,255,0.1)'" onmouseout="this.style.background='transparent'">
                        <input type="checkbox" class="country-cb" value="${code}" ${isChecked}>
                        <span>${flag} ${code.toUpperCase()}</span>
                    </label>
                `;
                listContainer.insertAdjacentHTML('beforeend', html);
            });
        } else {
            listContainer.innerHTML = `<span style="color: var(--danger); grid-column: span 2;">Scan failed: ${data.message}</span>`;
        }
    } catch(e) {
        listContainer.innerHTML = `<span style="color: var(--danger); grid-column: span 2;">Network error during scan.</span>`;
    }
    
    btnScan.innerHTML = '<i class="fa-solid fa-satellite-dish"></i> Live Scan';
    btnScan.disabled = false;
});

async function loadSettings() {
    try {
        const res = await fetch('/api/settings');
        if (res.ok) {
            const data = await res.json();
            document.getElementById('max-countries').value = data.max_instances || 20;
            document.getElementById('set-ping').value = data.ping_interval || 60;
            document.getElementById('set-ram').value = data.ram_limit_mb || 15;
            document.getElementById('set-bw').value = data.bandwidth_limit_kb || 0;
            document.getElementById('set-workers').value = data.worker_count || 0;
            if (data.selected_countries) {
                savedCountries = data.selected_countries.split(',').map(c => c.trim().toLowerCase());
                if(savedCountries.length > 0) {
                    listContainer.innerHTML = `<span style="color: var(--primary); font-size: 0.8rem; grid-column: span 2;">${savedCountries.length} countries saved. Click Scan to load full list.</span>`;
                }
            }
        }
    } catch (e) {
        console.error("Failed to load settings");
    }
}

// Poll every 1.5 seconds
loadSettings();
statusInterval = setInterval(fetchStatus, 1500);
fetchStatus();
