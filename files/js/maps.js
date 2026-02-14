// maps.js — Leaflet map initialization and interaction

function initMap() {
    detailMap = L.map('detailMap').setView([39.8283, -98.5795], 4);
    L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
        attribution: '© OpenStreetMap'
    }).addTo(detailMap);
}

function initFullMap() {
    if (fullMap) return; // Already initialized

    fullMap = L.map('fullMapContainer').setView([39.8283, -98.5795], 4);
    L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
        attribution: '© OpenStreetMap'
    }).addTo(fullMap);

    // Initialize marker cluster group
    markerClusterGroup = L.markerClusterGroup({
        chunkedLoading: true,
        spiderfyOnMaxZoom: true,
        showCoverageOnHover: false,
        maxClusterRadius: 50,
        iconCreateFunction: function(cluster) {
            const count = cluster.getChildCount();
            let size = 'small';
            if (count > 100) size = 'large';
            else if (count > 10) size = 'medium';

            return L.divIcon({
                html: `<div><span>${count}</span></div>`,
                className: `marker-cluster marker-cluster-${size}`,
                iconSize: L.point(40, 40)
            });
        }
    });

    fullMap.addLayer(markerClusterGroup);
}

function setView(view) {
    currentView = view;

    // Update toggle buttons
    document.getElementById('listViewBtn').classList.toggle('active', view === 'list');
    document.getElementById('mapViewBtn').classList.toggle('active', view === 'map');

    // Show/hide containers
    document.getElementById('listViewContainer').classList.toggle('hidden', view === 'map');
    document.getElementById('mapViewContainer').classList.toggle('hidden', view === 'list');

    if (view === 'map') {
        initFullMap();
        // Need to invalidate size after container becomes visible
        // Using 250ms delay for modal transitions
        setTimeout(() => {
            fullMap.invalidateSize();
            updateMapMarkers();
        }, 250);
    }
}

function updateMapMarkers() {
    if (!fullMap || !markerClusterGroup) return;

    // Clear existing markers
    markerClusterGroup.clearLayers();
    mapMarkers.clear();

    // Count mappable items
    let mappable = 0;

    // Add markers for all results with coordinates
    currentResults.forEach(item => {
        if (!item.latitude || !item.longitude) return;
        mappable++;

        const id = currentMode === 'employers' ? item.employer_id : item.f_num;
        const name = currentMode === 'employers' ? item.employer_name : formatUnionName(item);
        const workers = currentMode === 'employers'
            ? (item.latest_unit_size || 0)
            : (item.members || 0);

        // Create custom icon based on size
        const iconSize = workers > 1000 ? 12 : (workers > 100 ? 10 : 8);
        const icon = L.divIcon({
            className: 'custom-marker',
            html: `<div style="
                width: ${iconSize}px;
                height: ${iconSize}px;
                background: #8B4513;
                border: 2px solid white;
                border-radius: 50%;
                box-shadow: 0 2px 4px rgba(0,0,0,0.3);
            "></div>`,
            iconSize: [iconSize, iconSize],
            iconAnchor: [iconSize/2, iconSize/2]
        });

        const marker = L.marker([item.latitude, item.longitude], { icon });

        // Popup content
        const popupContent = `
            <div style="min-width: 180px;">
                <div style="font-weight: 600; margin-bottom: 4px;">${escapeHtml(name)}</div>
                <div style="color: #666; font-size: 12px;">${item.city || ''}, ${item.state || ''}</div>
                <div style="margin-top: 6px; font-size: 13px;">
                    <strong>${formatNumber(workers)}</strong> ${currentMode === 'employers' ? 'workers' : 'members'}
                </div>
                <button onclick="selectFromMap('${id}')" style="
                    margin-top: 8px;
                    color: #8B4513;
                    font-size: 12px;
                    font-weight: 500;
                    cursor: pointer;
                    background: none;
                    border: none;
                    padding: 0;
                ">View details -></button>
            </div>
        `;
        marker.bindPopup(popupContent);

        // Click handler
        marker.on('click', () => {
            showMapSelection(item);
        });

        markerClusterGroup.addLayer(marker);
        mapMarkers.set(String(id), marker);
    });

    // Update mappable count display
    const countEl = document.getElementById('mappableCount');
    if (mappable < currentResults.length) {
        countEl.textContent = `(${mappable} with coordinates)`;
    } else {
        countEl.textContent = '';
    }

    // Fit bounds if we have markers
    if (mappable > 0) {
        const bounds = markerClusterGroup.getBounds();
        fullMap.fitBounds(bounds, { padding: [50, 50], maxZoom: 12 });
    }
}

function showMapSelection(item) {
    const panel = document.getElementById('mapSelectionPanel');
    panel.classList.remove('hidden');

    const id = currentMode === 'employers' ? item.employer_id : item.f_num;
    const name = currentMode === 'employers' ? item.employer_name : formatUnionName(item);

    document.getElementById('mapSelectedName').textContent = name;
    document.getElementById('mapSelectedLocation').textContent =
        `${item.city || 'Unknown'}, ${item.state || ''}`;

    // Badges
    const sector = item.union_sector || item.sector;
    const sectorClass = getSectorBadgeClass(sector);
    document.getElementById('mapSelectedBadges').innerHTML = `
        <span class="badge ${sectorClass}">${formatSectorName(sector)}</span>
    `;

    // Stats
    if (currentMode === 'employers') {
        document.getElementById('mapSelectedStats').innerHTML = `
            <span class="text-warmgray-600"><strong>${formatNumber(item.latest_unit_size || 0)}</strong> workers</span>
            <span class="text-warmgray-400 mx-2">•</span>
            <span class="text-warmgray-600">${escapeHtml(item.aff_abbr || item.latest_union_name || 'Unknown union')}</span>
        `;
    } else {
        document.getElementById('mapSelectedStats').innerHTML = `
            <span class="text-warmgray-600"><strong>${formatNumber(item.members || 0)}</strong> members</span>
            <span class="text-warmgray-400 mx-2">•</span>
            <span class="text-warmgray-600">${formatNumber(item.f7_employer_count || 0)} employers</span>
        `;
    }

    // View detail button
    document.getElementById('mapViewDetailBtn').onclick = () => {
        setView('list');
        selectItem(id);
    };
}

function selectFromMap(id) {
    // Switch to list view and select item
    setView('list');
    selectItem(id);
}

function updateDetailMap(item) {
    if (item.latitude && item.longitude) {
        detailMap.setView([item.latitude, item.longitude], 12);
        if (detailMarker) {
            detailMarker.setLatLng([item.latitude, item.longitude]);
        } else {
            detailMarker = L.marker([item.latitude, item.longitude]).addTo(detailMap);
        }
        const popupContent = currentMode === 'employers'
            ? `<strong>${item.employer_name}</strong><br>${item.city}, ${item.state}`
            : `<strong>${formatUnionName(item)}</strong><br>${item.city}, ${item.state}`;
        detailMarker.bindPopup(popupContent);
    }

    // Invalidate map size (fixes rendering issues)
    // Using 250ms delay for modal transitions
    setTimeout(() => detailMap.invalidateSize(), 250);
}
