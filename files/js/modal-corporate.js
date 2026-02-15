// modal-corporate.js -- Corporate Family tree + map

let corporateFamilyMap = null;
let corporateFamilyMarkers = null;

async function loadCorporateFamily(employerId) {
    // Show loading in the detail section
    document.getElementById('corporateLoadingBadge').classList.remove('hidden');
    document.getElementById('corporateContent').innerHTML = `
        <div class="bg-warmgray-50 border border-dashed border-warmgray-300 rounded-lg p-4 text-center text-sm text-warmgray-400">
            Searching for related employers...
        </div>
    `;

    try {
        const response = await fetch(`${API_BASE}/corporate/family/${employerId}`);
        const data = await response.json();

        document.getElementById('corporateLoadingBadge').classList.add('hidden');

        if (!data.family_members || data.family_members.length === 0) {
            document.getElementById('corporateContent').innerHTML = `
                <div class="bg-warmgray-50 border border-warmgray-200 rounded-lg p-4 text-sm text-warmgray-500">
                    <div class="flex items-center gap-2">
                        <svg class="w-5 h-5 text-warmgray-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"/>
                        </svg>
                        <span>No related employers found in our database.</span>
                    </div>
                </div>
            `;
            return;
        }

        // Build state summary from family_members
        const stateMap = {};
        data.family_members.forEach(m => {
            const st = m.state || 'Unknown';
            if (!stateMap[st]) stateMap[st] = { state: st, count: 0, workers: 0 };
            stateMap[st].count++;
            stateMap[st].workers += (m.latest_unit_size || 0);
        });
        const stateSummary = Object.values(stateMap).sort((a, b) => b.workers - a.workers);
        const maxWorkers = stateSummary.length > 0 ? Math.max(...stateSummary.map(s => s.workers)) : 1;

        // Source badge
        const sourceBadge = data.hierarchy_source === 'CORPORATE_HIERARCHY'
            ? '<span class="text-xs px-2 py-0.5 bg-green-100 text-green-700 rounded-full font-medium">Ownership</span>'
            : '<span class="text-xs px-2 py-0.5 bg-warmgray-200 text-warmgray-600 rounded-full font-medium">Name Match</span>';

        // SEC badge
        const secBadge = data.sec_info && data.sec_info.ticker
            ? `<span class="text-xs px-2 py-0.5 bg-blue-100 text-blue-700 rounded-full font-medium">${escapeHtml(data.sec_info.ticker)}</span>`
            : '';

        // Union penetration
        const unionizedCount = data.unionized_count || 0;
        const totalFamily = data.total_family || 0;
        const unionPct = totalFamily > 0 ? Math.round(100 * unionizedCount / totalFamily) : 0;
        const totalFamilyDisplay = Number(data.total_family) || 0;
        const totalWorkersDisplay = formatNumber(Number(data.total_workers) || 0);
        const statesCountDisplay = Array.isArray(data.states) ? data.states.length : 0;

        document.getElementById('corporateContent').innerHTML = `
            <div class="bg-gradient-to-r from-warmgray-100 to-warmgray-50 rounded-lg p-4 border border-warmgray-200">
                <div class="flex items-center justify-between mb-3">
                    <div>
                        <div class="flex items-center gap-2 mb-1">
                            <div class="text-xs text-warmgray-500 uppercase font-semibold">Corporate Family</div>
                            ${sourceBadge} ${secBadge}
                        </div>
                        <div class="text-lg font-bold text-warmgray-900">${escapeHtml(data.root_name || data.employer.employer_name)}</div>
                    </div>
                    <button onclick="openCorporateFamily('${employerId}')"
                        class="px-4 py-2 bg-warmgray-900 text-white text-sm font-semibold rounded-lg hover:bg-warmgray-800 transition-colors">
                        View All ->
                    </button>
                </div>
                <div class="grid grid-cols-4 gap-2 text-center">
                    <div class="bg-white rounded-lg p-2">
                        <div class="text-xl font-bold text-warmgray-900">${totalFamilyDisplay}</div>
                        <div class="text-xs text-warmgray-500">Related</div>
                    </div>
                    <div class="bg-white rounded-lg p-2">
                        <div class="text-xl font-bold text-accent-red">${totalWorkersDisplay}</div>
                        <div class="text-xs text-warmgray-500">Workers</div>
                    </div>
                    <div class="bg-white rounded-lg p-2">
                        <div class="text-xl font-bold text-warmgray-900">${statesCountDisplay}</div>
                        <div class="text-xs text-warmgray-500">States</div>
                    </div>
                    <div class="bg-white rounded-lg p-2">
                        <div class="text-xl font-bold ${unionPct > 0 ? 'text-green-700' : 'text-warmgray-400'}">${unionPct}%</div>
                        <div class="text-xs text-warmgray-500">Union</div>
                    </div>
                </div>
                ${stateSummary.slice(0, 3).map(s => `
                    <div class="mt-2 flex items-center gap-2">
                        <span class="text-xs font-medium w-8">${s.state}</span>
                        <div class="flex-1 h-2 bg-warmgray-200 rounded-full">
                            <div class="h-full bg-warmgray-600 rounded-full" style="width: ${(s.workers / maxWorkers) * 100}%"></div>
                        </div>
                        <span class="text-xs text-warmgray-500">${formatNumber(s.workers)}</span>
                    </div>
                `).join('')}
            </div>
        `;
    } catch (e) {
        console.error('Corporate family load error:', e);
        document.getElementById('corporateLoadingBadge').classList.add('hidden');
        document.getElementById('corporateContent').innerHTML = `
            <div class="bg-warmgray-50 border border-warmgray-200 rounded-lg p-4 text-sm text-warmgray-500">
                Unable to load corporate family data.
            </div>
        `;
    }
}

async function openCorporateFamily(employerId) {
    document.getElementById('corporateFamilyModal').classList.remove('hidden');
    document.getElementById('corporateFamilyModal').classList.add('flex');
    document.getElementById('corporateFamilyLoading').classList.remove('hidden');
    document.getElementById('corporateFamilyContent').classList.add('hidden');

    try {
        const response = await fetch(`${API_BASE}/corporate/family/${employerId}`);
        const data = await response.json();

        renderCorporateFamilyModal(data);
    } catch (e) {
        console.error('Corporate family modal error:', e);
        document.getElementById('corporateFamilyLoading').innerHTML = `
            <div class="text-red-600">Failed to load corporate family data.</div>
        `;
    }
}

function closeCorporateFamily() {
    document.getElementById('corporateFamilyModal').classList.add('hidden');
    document.getElementById('corporateFamilyModal').classList.remove('flex');

    // Clean up map
    if (corporateFamilyMap) {
        corporateFamilyMap.remove();
        corporateFamilyMap = null;
    }
}

function renderCorporateFamilyModal(data) {
    document.getElementById('corporateFamilyLoading').classList.add('hidden');
    document.getElementById('corporateFamilyContent').classList.remove('hidden');

    const rootName = data.root_name || data.employer.employer_name || 'Corporate Family';
    const empName = data.employer ? (data.employer.employer_name || '') : '';

    // Header with source badge
    const srcLabel = data.hierarchy_source === 'CORPORATE_HIERARCHY' ? 'Ownership-based' : 'Name similarity';
    document.getElementById('corporateFamilyTitle').textContent = rootName;
    document.getElementById('corporateFamilySubtitle').innerHTML =
        `Based on "${escapeHtml(empName)}" <span class="ml-2 text-xs px-2 py-0.5 rounded-full ${data.hierarchy_source === 'CORPORATE_HIERARCHY' ? 'bg-green-100 text-green-700' : 'bg-warmgray-200 text-warmgray-600'}">${srcLabel}</span>`
        + (data.sec_info && data.sec_info.ticker ? ` <span class="ml-1 text-xs px-2 py-0.5 bg-blue-100 text-blue-700 rounded-full">${escapeHtml(data.sec_info.ticker)}</span>` : '');

    // Summary cards
    document.getElementById('cfLocations').textContent = formatNumber(data.total_family || 0);
    document.getElementById('cfWorkers').textContent = formatNumber(data.total_workers || 0);
    document.getElementById('cfStates').textContent = (data.states || []).length;
    document.getElementById('cfUnions').textContent = (data.unions || []).length;

    // Root name
    document.getElementById('cfRootName').textContent = rootName;

    // Location count
    const members = data.family_members || [];
    document.getElementById('cfLocationCount').textContent = `${members.length} employers`;

    // Location list with relationship badges
    document.getElementById('cfLocationList').innerHTML = members.slice(0, 100).map(m => {
        const relBadge = m.relationship === 'CORPORATE_FAMILY'
            ? '<span class="text-xs px-1.5 py-0.5 bg-green-50 text-green-600 rounded">Family</span>'
            : m.relationship === 'MERGENT_FAMILY'
            ? '<span class="text-xs px-1.5 py-0.5 bg-purple-50 text-purple-600 rounded">Subsidiary</span>'
            : m.relationship === 'MULTI_EMPLOYER_GROUP'
            ? '<span class="text-xs px-1.5 py-0.5 bg-blue-50 text-blue-600 rounded">Agreement</span>'
            : '<span class="text-xs px-1.5 py-0.5 bg-warmgray-100 text-warmgray-500 rounded">Similar</span>';
        const unionBadge = m.latest_union_name
            ? `<span class="text-xs px-1.5 py-0.5 bg-red-50 text-red-600 rounded ml-1">Union</span>`
            : '';
        const tickerBadge = m.sec_ticker
            ? `<span class="text-xs px-1.5 py-0.5 bg-blue-50 text-blue-600 rounded ml-1">${escapeHtml(m.sec_ticker)}</span>`
            : '';
        return `
        <div class="px-4 py-3 hover:bg-warmgray-50 cursor-pointer" onclick="selectCorporateLocation('${m.employer_id}')">
            <div class="flex justify-between items-start">
                <div>
                    <div class="font-medium text-warmgray-900">${escapeHtml(m.employer_name)}</div>
                    <div class="text-sm text-warmgray-500">${m.city || '-'}, ${m.state || '-'}</div>
                    <div class="mt-1">${relBadge}${unionBadge}${tickerBadge}</div>
                </div>
                <div class="text-right">
                    <div class="font-semibold text-warmgray-900">${formatNumber(m.latest_unit_size || 0)}</div>
                    <div class="text-xs text-warmgray-400">workers</div>
                </div>
            </div>
        </div>`;
    }).join('');

    // By State breakdown (computed from family_members)
    const stateMap = {};
    members.forEach(m => {
        const st = m.state || 'Unknown';
        if (!stateMap[st]) stateMap[st] = { state: st, count: 0, workers: 0 };
        stateMap[st].count++;
        stateMap[st].workers += (m.latest_unit_size || 0);
    });
    const stateSummary = Object.values(stateMap).sort((a, b) => b.workers - a.workers);

    if (stateSummary.length > 0) {
        const maxW = Math.max(...stateSummary.map(s => s.workers));
        document.getElementById('cfByState').innerHTML = stateSummary.map(s => `
            <div class="flex items-center gap-2">
                <span class="text-xs font-semibold w-6">${s.state}</span>
                <div class="flex-1 h-2 bg-warmgray-200 rounded-full">
                    <div class="h-full bg-accent-red rounded-full" style="width: ${(s.workers / maxW) * 100}%"></div>
                </div>
                <span class="text-xs text-warmgray-500 w-16 text-right">${formatNumber(s.workers)}</span>
                <span class="text-xs text-warmgray-400 w-8">(${s.count})</span>
            </div>
        `).join('');
    } else {
        document.getElementById('cfByState').innerHTML = '<div class="text-sm text-warmgray-400">No state data</div>';
    }

    // By Union breakdown (computed from family_members)
    const unionMap = {};
    members.forEach(m => {
        if (m.latest_union_name) {
            const u = m.latest_union_name;
            if (!unionMap[u]) unionMap[u] = { union: u, count: 0, workers: 0 };
            unionMap[u].count++;
            unionMap[u].workers += (m.latest_unit_size || 0);
        }
    });
    const unionSummary = Object.values(unionMap).sort((a, b) => b.workers - a.workers);

    if (unionSummary.length > 0) {
        const maxW = Math.max(...unionSummary.map(u => u.workers));
        document.getElementById('cfByUnion').innerHTML = unionSummary.map(u => `
            <div class="flex items-center gap-2">
                <span class="text-xs font-semibold flex-1 truncate">${escapeHtml(u.union)}</span>
                <div class="w-20 h-2 bg-warmgray-200 rounded-full">
                    <div class="h-full bg-blue-500 rounded-full" style="width: ${(u.workers / maxW) * 100}%"></div>
                </div>
                <span class="text-xs text-warmgray-500 w-16 text-right">${formatNumber(u.workers)}</span>
            </div>
        `).join('');
    } else {
        document.getElementById('cfByUnion').innerHTML = '<div class="text-sm text-warmgray-400">No union data</div>';
    }

    // Initialize map
    setTimeout(() => initCorporateFamilyMap(members), 100);
}

function initCorporateFamilyMap(locations) {
    // Clean up existing map
    if (corporateFamilyMap) {
        corporateFamilyMap.remove();
    }

    // Create map
    corporateFamilyMap = L.map('corporateFamilyMap').setView([39.8283, -98.5795], 4);

    L.tileLayer('https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png', {
        attribution: '&copy; OpenStreetMap &copy; CARTO',
        subdomains: 'abcd',
        maxZoom: 19
    }).addTo(corporateFamilyMap);

    // Add markers
    corporateFamilyMarkers = L.markerClusterGroup({
        maxClusterRadius: 50,
        spiderfyOnMaxZoom: true,
        showCoverageOnHover: false,
        iconCreateFunction: function(cluster) {
            const count = cluster.getChildCount();
            return L.divIcon({
                html: `<div class="corporate-cluster">${count}</div>`,
                className: 'corporate-cluster-icon',
                iconSize: L.point(40, 40)
            });
        }
    });

    const validLocations = locations.filter(loc => loc.latitude && loc.longitude);

    validLocations.forEach(loc => {
        const marker = L.marker([loc.latitude, loc.longitude]);
        marker.bindPopup(`
            <div class="text-sm">
                <div class="font-semibold">${escapeHtml(loc.employer_name)}</div>
                <div class="text-warmgray-500">${loc.city}, ${loc.state}</div>
                <div class="mt-1">${formatNumber(loc.latest_unit_size || 0)} workers</div>
                ${loc.aff_abbr ? `<div class="text-xs text-blue-600">${escapeHtml(loc.aff_abbr)}</div>` : ''}
            </div>
        `);
        corporateFamilyMarkers.addLayer(marker);
    });

    corporateFamilyMap.addLayer(corporateFamilyMarkers);

    // Fit bounds if we have valid locations
    if (validLocations.length > 0) {
        const bounds = L.latLngBounds(validLocations.map(l => [l.latitude, l.longitude]));
        corporateFamilyMap.fitBounds(bounds, { padding: [30, 30] });
    }
}

function selectCorporateLocation(employerId) {
    // Close modal and load employer in main view
    closeCorporateFamily();

    // Search for this employer by ID
    document.getElementById('mainSearch').value = employerId;
    currentMode = 'employers';
    executeSearch();
}
