/* Traffic Image Upload & Client-Side Validation Logic */

const ALLOWED_EXTENSIONS = ['jpg', 'jpeg', 'png'];
const MAX_FILE_SIZE = 10 * 1024 * 1024; // 10 MB

document.addEventListener('DOMContentLoaded', () => {
    const dropZone = document.getElementById('dropZone');
    const fileInput = document.getElementById('trafficImageInput');

    if (dropZone && fileInput) {
        // Drag Over
        dropZone.addEventListener('dragover', (e) => {
            e.preventDefault();
            e.stopPropagation();
            dropZone.classList.add('border-cyan', 'bg-opacity-60');
        });

        // Drag Leave
        dropZone.addEventListener('dragleave', (e) => {
            e.preventDefault();
            e.stopPropagation();
            dropZone.classList.remove('border-cyan', 'bg-opacity-60');
        });

        // Drop
        dropZone.addEventListener('drop', (e) => {
            e.preventDefault();
            e.stopPropagation();
            dropZone.classList.remove('border-cyan', 'bg-opacity-60');

            if (e.dataTransfer.files && e.dataTransfer.files.length > 0) {
                const file = e.dataTransfer.files[0];
                fileInput.files = e.dataTransfer.files;
                validateAndDisplayFile(file);
            }
        });
    }
});

function handleFileSelect(event) {
    if (event.target.files && event.target.files.length > 0) {
        validateAndDisplayFile(event.target.files[0]);
    }
}

function validateAndDisplayFile(file) {
    const errorAlert = document.getElementById('clientErrorAlert');
    const errorMessage = document.getElementById('clientErrorMessage');
    const fileInfo = document.getElementById('fileSelectedInfo');
    const fileNameDisplay = document.getElementById('fileNameDisplay');
    const fileSizeDisplay = document.getElementById('fileSizeDisplay');
    const btnSubmit = document.getElementById('btnSubmitUpload');

    // Reset state
    if (errorAlert) errorAlert.classList.add('d-none');
    if (fileInfo) fileInfo.classList.add('d-none');
    if (btnSubmit) btnSubmit.disabled = true;

    if (!file) return;

    // Check extension
    const ext = file.name.split('.').pop().toLowerCase();
    if (!ALLOWED_EXTENSIONS.includes(ext)) {
        showError(`Invalid file extension '.${ext}'. Only JPG, JPEG, and PNG images are allowed.`);
        return;
    }

    // Check file size
    if (file.size > MAX_FILE_SIZE) {
        const sizeMB = (file.size / (1024 * 1024)).toFixed(2);
        showError(`File size (${sizeMB} MB) exceeds maximum allowed limit of 10 MB.`);
        return;
    }

    if (file.size === 0) {
        showError('Selected file is empty. Please select a valid traffic image.');
        return;
    }

    // Valid file selected
    if (fileNameDisplay) fileNameDisplay.innerText = file.name;
    if (fileSizeDisplay) fileSizeDisplay.innerText = `${(file.size / (1024 * 1024)).toFixed(2)} MB`;
    if (fileInfo) fileInfo.classList.remove('d-none');
    if (btnSubmit) btnSubmit.disabled = false;
}

function showError(msg) {
    const errorAlert = document.getElementById('clientErrorAlert');
    const errorMessage = document.getElementById('clientErrorMessage');
    const btnSubmit = document.getElementById('btnSubmitUpload');

    if (errorMessage) errorMessage.innerText = msg;
    if (errorAlert) errorAlert.classList.remove('d-none');
    if (btnSubmit) btnSubmit.disabled = true;
}

// Disable Detect button while inference runs and prevent duplicate requests
document.addEventListener('DOMContentLoaded', () => {
    const uploadForm = document.getElementById('imageUploadForm');
    if (uploadForm) {
        uploadForm.addEventListener('submit', (e) => {
            const btnSubmit = document.getElementById('btnSubmitUpload');
            if (btnSubmit) {
                btnSubmit.disabled = true;
                btnSubmit.innerHTML = '<span class="spinner-border spinner-border-sm me-2" role="status" aria-hidden="true"></span> Analyzing Frame (YOLOv11)...';
            }
        });
    }

    function applyTelemetryToDOM(data) {
        const liveCount = document.getElementById('liveCountVal');
        const liveCars = document.getElementById('liveCarsVal');
        const liveBuses = document.getElementById('liveBusesVal');
        const liveTrucks = document.getElementById('liveTrucksVal');
        const liveMotorcycles = document.getElementById('liveMotorcyclesVal');
        const liveBicycles = document.getElementById('liveBicyclesVal');
        const liveVans = document.getElementById('liveVansVal');
        const liveCongestion = document.getElementById('liveCongestionVal');
        const liveOccupancy = document.getElementById('liveOccupancyVal');
        const congestionBar = document.getElementById('congestionProgressBar');
        const occupancyBar = document.getElementById('occupancyProgressBar');
        const densityBadge = document.getElementById('densityBadgeVal');

        const cnt = data.vehicle_count !== undefined ? data.vehicle_count : data.count;
        const bdown = data.breakdown || data;
        const occ = data.occupancy_pct !== undefined ? data.occupancy_pct : data.occupancy;
        const cong = data.congestion_pct;

        if (liveCount && cnt !== undefined) liveCount.innerText = cnt;
        if (liveCars && bdown.cars !== undefined) liveCars.innerText = bdown.cars;
        if (liveBuses && bdown.buses !== undefined) liveBuses.innerText = bdown.buses;
        if (liveTrucks && bdown.trucks !== undefined) liveTrucks.innerText = bdown.trucks;
        if (liveMotorcycles && bdown.motorcycles !== undefined) liveMotorcycles.innerText = bdown.motorcycles;
        if (liveBicycles && bdown.bicycles !== undefined) liveBicycles.innerText = bdown.bicycles;
        if (liveVans && bdown.vans !== undefined) liveVans.innerText = bdown.vans;
        if (liveCongestion && cong !== undefined) liveCongestion.innerText = cong + '%';
        if (liveOccupancy && occ !== undefined) liveOccupancy.innerText = occ + '%';
        if (congestionBar && cong !== undefined) congestionBar.style.width = cong + '%';
        if (occupancyBar && occ !== undefined) occupancyBar.style.width = occ + '%';
        if (densityBadge && data.density) densityBadge.innerText = data.density.toUpperCase();
    }

    // Connect to Socket.IO for instant live monitoring updates
    if (typeof io !== 'undefined') {
        const socket = io({
            transports: ['websocket', 'polling'],
            reconnection: true
        });
        socket.on('traffic_update', (data) => {
            if (data) applyTelemetryToDOM(data);
        });
    }

    // Auto update dashboard telemetry periodically without manual refresh as fallback
    setInterval(async () => {
        try {
            const resp = await fetch('/api/telemetry/1', {
                headers: { 'Accept': 'application/json' }
            });
            if (resp.ok) {
                const data = await resp.json();
                applyTelemetryToDOM(data);
            }
        } catch (_) {}
    }, 4000);
});
