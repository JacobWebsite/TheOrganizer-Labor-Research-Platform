// modal-publicsector.js -- Public Sector modal

let publicSectorResults = [];
let selectedPublicSectorItem = null;
let publicSectorView = 'locals';

function openPublicSectorModal() {
    console.log('Opening Public Sector modal...');
    document.getElementById('publicSectorModal').classList.remove('hidden');
    document.getElementById('publicSectorModal').classList.add('flex');
    document.body.classList.add('modal-open');
    initPublicSectorDropdowns();

    // Auto-load results on open
    if (publicSectorView === 'locals') {
        loadPublicSectorLocals();
    } else {
        loadPublicSectorEmployers();
    }
}

function closePublicSectorModal() {
    document.getElementById('publicSectorModal').classList.add('hidden');
    document.getElementById('publicSectorModal').classList.remove('flex');
    document.body.classList.remove('modal-open');
}

async function initPublicSectorDropdowns() {
    // Populate state dropdowns
    const mainStateSelect = document.getElementById('stateFilter');
    ['psLocalsState', 'psEmployersState'].forEach(id => {
        const select = document.getElementById(id);
        if (select.options.length <= 1) {
            for (let i = 1; i < mainStateSelect.options.length; i++) {
                const opt = mainStateSelect.options[i];
                select.add(new Option(opt.text, opt.value));
            }
        }
    });

    // Load parent unions
    const parentSelect = document.getElementById('psLocalsParent');
    if (parentSelect.options.length <= 1) {
        try {
            const response = await fetch(`${API_BASE}/public-sector/parent-unions`);
            const data = await response.json();
            (data.parent_unions || []).forEach(u => {
                parentSelect.add(new Option(u.full_name || u.abbrev, u.abbrev));
            });
        } catch (e) { console.error('Failed to load parent unions:', e); }
    }

    // Load employer types
    const typeSelect = document.getElementById('psEmployersType');
    if (typeSelect.options.length <= 1) {
        try {
            const response = await fetch(`${API_BASE}/public-sector/employer-types`);
            const data = await response.json();
            (data.employer_types || []).forEach(t => {
                const label = (t.employer_type || '').replace(/_/g, ' ');
                typeSelect.add(new Option(`${label} (${t.count})`, t.employer_type));
            });
        } catch (e) { console.error('Failed to load employer types:', e); }
    }
}

function setPublicSectorView(view) {
    publicSectorView = view;

    document.getElementById('psLocalsTab').className = view === 'locals'
        ? 'px-4 py-1.5 text-sm font-semibold rounded-full transition-all bg-warmgray-900 text-white'
        : 'px-4 py-1.5 text-sm font-semibold rounded-full transition-all text-warmgray-600 hover:text-warmgray-800';
    document.getElementById('psEmployersTab').className = view === 'employers'
        ? 'px-4 py-1.5 text-sm font-semibold rounded-full transition-all bg-warmgray-900 text-white'
        : 'px-4 py-1.5 text-sm font-semibold rounded-full transition-all text-warmgray-600 hover:text-warmgray-800';

    document.getElementById('psLocalsFilters').classList.toggle('hidden', view !== 'locals');
    document.getElementById('psEmployersFilters').classList.toggle('hidden', view !== 'employers');

    // Clear results
    publicSectorResults = [];
    document.getElementById('publicSectorResultsInfo').textContent = 'Click "Search" to browse public sector data';
    document.getElementById('publicSectorResults').innerHTML = '';
    document.getElementById('publicSectorDetailEmpty').classList.remove('hidden');
    document.getElementById('publicSectorDetail').classList.add('hidden');
}

async function loadPublicSectorLocals() {
    console.log('loadPublicSectorLocals called');
    const name = document.getElementById('psLocalsNameSearch').value;
    const state = document.getElementById('psLocalsState').value;
    const parent = document.getElementById('psLocalsParent').value;

    document.getElementById('publicSectorLoading').classList.remove('hidden');
    document.getElementById('publicSectorContent').classList.add('hidden');

    const params = new URLSearchParams({ limit: 100 });
    if (name) params.append('name', name);
    if (state) params.append('state', state);
    if (parent) params.append('parent_union', parent);

    const url = `${API_BASE}/public-sector/locals?${params}`;
    console.log('Fetching:', url);

    try {
        const response = await fetch(url);
        console.log('Response status:', response.status);
        const data = await response.json();
        console.log('Data received:', data.total, 'locals');
        publicSectorResults = data.locals || [];
        renderPublicSectorResults();
    } catch (e) {
        console.error('Public sector locals failed:', e);
        document.getElementById('publicSectorResultsInfo').textContent = 'Error: ' + e.message;
    } finally {
        document.getElementById('publicSectorLoading').classList.add('hidden');
        document.getElementById('publicSectorContent').classList.remove('hidden');
    }
}

async function loadPublicSectorEmployers() {
    const name = document.getElementById('psEmployersNameSearch').value;
    const state = document.getElementById('psEmployersState').value;
    const type = document.getElementById('psEmployersType').value;

    document.getElementById('publicSectorLoading').classList.remove('hidden');
    document.getElementById('publicSectorContent').classList.add('hidden');

    const params = new URLSearchParams({ limit: 100 });
    if (name) params.append('name', name);
    if (state) params.append('state', state);
    if (type) params.append('employer_type', type);

    try {
        const response = await fetch(`${API_BASE}/public-sector/employers?${params}`);
        const data = await response.json();
        publicSectorResults = data.employers || data.results || [];
        renderPublicSectorResults();
    } catch (e) {
        console.error('Public sector employers failed:', e);
        document.getElementById('publicSectorResultsInfo').textContent = 'Error loading results.';
    } finally {
        document.getElementById('publicSectorLoading').classList.add('hidden');
        document.getElementById('publicSectorContent').classList.remove('hidden');
    }
}

function renderPublicSectorResults() {
    const infoEl = document.getElementById('publicSectorResultsInfo');
    const resultsEl = document.getElementById('publicSectorResults');

    infoEl.textContent = `${formatNumber(publicSectorResults.length)} ${publicSectorView} found`;

    if (publicSectorResults.length === 0) {
        resultsEl.innerHTML = '<div class="p-8 text-center text-warmgray-400">No results found.</div>';
        return;
    }

    if (publicSectorView === 'locals') {
        resultsEl.innerHTML = publicSectorResults.map(item => `
            <div class="p-4 cursor-pointer hover:bg-warmgray-50 transition-colors ${selectedPublicSectorItem?.id === item.id ? 'bg-orange-50 border-l-4 border-orange-500' : ''}"
                 onclick="selectPublicSectorItem('${item.id}', 'local')">
                <div class="flex justify-between items-start mb-1">
                    <div class="font-semibold text-warmgray-900 truncate flex-1">${escapeHtml(item.local_name || 'Unknown')}</div>
                    ${item.parent_abbrev ? `<span class="px-2 py-0.5 rounded text-xs font-semibold bg-orange-100 text-orange-700">${item.parent_abbrev}</span>` : ''}
                </div>
                ${item.local_designation ? `<div class="text-xs text-warmgray-400">${item.local_designation}</div>` : ''}
                <div class="text-sm text-warmgray-500">${escapeHtml(item.city || '')}, ${item.state || ''}</div>
                ${item.members ? `<div class="text-xs text-warmgray-400 mt-1">${formatNumber(item.members)} members</div>` : ''}
            </div>
        `).join('');
    } else {
        resultsEl.innerHTML = publicSectorResults.map(item => `
            <div class="p-4 cursor-pointer hover:bg-warmgray-50 transition-colors ${selectedPublicSectorItem?.id === item.id ? 'bg-orange-50 border-l-4 border-orange-500' : ''}"
                 onclick="selectPublicSectorItem('${item.id}', 'employer')">
                <div class="flex justify-between items-start mb-1">
                    <div class="font-semibold text-warmgray-900 truncate flex-1">${escapeHtml(item.employer_name || 'Unknown')}</div>
                    ${getEmployerTypeBadge(item.employer_type)}
                </div>
                <div class="text-sm text-warmgray-500">${item.state || ''} ${item.county ? `· ${item.county} County` : ''}</div>
                ${item.total_employees ? `<div class="text-xs text-warmgray-400 mt-1">${formatNumber(item.total_employees)} employees</div>` : ''}
            </div>
        `).join('');
    }
}

function getEmployerTypeBadge(type) {
    const colors = {
        'FEDERAL': 'bg-blue-100 text-blue-700',
        'STATE': 'bg-purple-100 text-purple-700',
        'STATE_AGENCY': 'bg-purple-100 text-purple-700',
        'COUNTY': 'bg-orange-100 text-orange-700',
        'CITY': 'bg-green-100 text-green-700',
        'SCHOOL_DISTRICT': 'bg-yellow-100 text-yellow-700',
        'UNIVERSITY': 'bg-indigo-100 text-indigo-700',
        'TRANSIT_AUTHORITY': 'bg-cyan-100 text-cyan-700',
        'UTILITY': 'bg-teal-100 text-teal-700',
        'SPECIAL_DISTRICT': 'bg-pink-100 text-pink-700'
    };
    const label = (type || '').replace(/_/g, ' ');
    return `<span class="px-2 py-0.5 rounded text-xs font-semibold ${colors[type] || 'bg-gray-100 text-gray-700'}">${label}</span>`;
}

function selectPublicSectorItem(id, type) {
    selectedPublicSectorItem = publicSectorResults.find(r => r.id == id);
    renderPublicSectorResults();

    document.getElementById('publicSectorDetailEmpty').classList.add('hidden');
    document.getElementById('publicSectorDetail').classList.remove('hidden');
    renderPublicSectorDetail(selectedPublicSectorItem, type);
}

function renderPublicSectorDetail(item, type) {
    if (!item) return;
    const el = document.getElementById('publicSectorDetail');

    if (type === 'local') {
        el.innerHTML = `
            <div class="mb-6">
                <h3 class="text-xl font-bold text-warmgray-900">${escapeHtml(item.local_name || 'Unknown')}</h3>
                ${item.local_designation ? `<p class="text-warmgray-500">${item.local_designation}</p>` : ''}
                <p class="text-warmgray-500">${escapeHtml(item.city || '')}, ${item.state || ''}</p>
                <div class="flex gap-2 mt-2 flex-wrap">
                    ${item.parent_abbrev ? `<span class="badge bg-orange-100 text-orange-700">${item.parent_abbrev}</span>` : ''}
                    ${item.parent_name ? `<span class="text-xs text-warmgray-500">${item.parent_name}</span>` : ''}
                </div>
                ${item.members ? `<div class="text-sm text-warmgray-600 mt-2">${formatNumber(item.members)} members</div>` : ''}
            </div>

            <div class="space-y-4">
                ${item.contact_info ? `
                    <div class="bg-warmgray-50 rounded-lg p-4">
                        <h4 class="text-xs font-semibold text-warmgray-500 uppercase mb-2">Contact</h4>
                        <div class="text-sm">${escapeHtml(item.contact_info)}</div>
                    </div>
                ` : ''}
                ${item.website ? `
                    <div class="bg-blue-50 rounded-lg p-4">
                        <h4 class="text-xs font-semibold text-blue-700 uppercase mb-2">Website</h4>
                        <a href="${item.website}" target="_blank" class="text-sm text-blue-600 hover:underline">${item.website}</a>
                    </div>
                ` : ''}
            </div>
        `;
    } else {
        el.innerHTML = `
            <div class="mb-6">
                <h3 class="text-xl font-bold text-warmgray-900">${escapeHtml(item.employer_name || 'Unknown')}</h3>
                <p class="text-warmgray-500">${item.city ? item.city + ', ' : ''}${item.state || ''}</p>
                <div class="flex gap-2 mt-2 flex-wrap">
                    ${getEmployerTypeBadge(item.employer_type)}
                    ${item.total_employees ? `<span class="badge badge-industry">${formatNumber(item.total_employees)} employees</span>` : ''}
                </div>
            </div>

            <div class="space-y-4">
                <div class="bg-warmgray-50 rounded-lg p-4">
                    <h4 class="text-xs font-semibold text-warmgray-500 uppercase mb-2">Details</h4>
                    <div class="text-sm space-y-1">
                        <div><span class="text-warmgray-500">Type:</span> ${(item.employer_type || 'N/A').replace(/_/g, ' ')}</div>
                        <div><span class="text-warmgray-500">State:</span> ${item.state || 'N/A'}</div>
                        ${item.county ? `<div><span class="text-warmgray-500">County:</span> ${item.county}</div>` : ''}
                        ${item.naics_code ? `<div><span class="text-warmgray-500">NAICS:</span> ${item.naics_code}</div>` : ''}
                    </div>
                </div>
            </div>
        `;
    }
}
