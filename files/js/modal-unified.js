// modal-unified.js -- Unified Employers modal

let unifiedEmployersResults = [];
let selectedUnifiedItem = null;

function openUnifiedEmployersModal() {
    console.log('Opening Unified Employers modal...');
    document.getElementById('unifiedEmployersModal').classList.remove('hidden');
    document.getElementById('unifiedEmployersModal').classList.add('flex');
    document.body.classList.add('modal-open');

    // Populate state dropdown
    const stateSelect = document.getElementById('unifiedState');
    if (stateSelect.options.length <= 1) {
        const mainStateSelect = document.getElementById('stateFilter');
        console.log('Main state options:', mainStateSelect.options.length);
        for (let i = 1; i < mainStateSelect.options.length; i++) {
            const opt = mainStateSelect.options[i];
            stateSelect.add(new Option(opt.text, opt.value));
        }
    }

    // Auto-load results on open
    loadUnifiedEmployers();
}

function closeUnifiedEmployersModal() {
    document.getElementById('unifiedEmployersModal').classList.add('hidden');
    document.getElementById('unifiedEmployersModal').classList.remove('flex');
    document.body.classList.remove('modal-open');
}

async function loadUnifiedEmployers() {
    console.log('loadUnifiedEmployers called');
    const name = document.getElementById('unifiedNameSearch').value;
    const state = document.getElementById('unifiedState').value;
    const source = document.getElementById('unifiedSource').value;
    const hasUnion = document.getElementById('unifiedHasUnion').value;
    const hasOsha = document.getElementById('unifiedHasOsha').value;

    document.getElementById('unifiedLoading').classList.remove('hidden');
    document.getElementById('unifiedContent').classList.add('hidden');

    const params = new URLSearchParams({ limit: 100 });
    if (name) params.append('name', name);
    if (state) params.append('state', state);
    if (source) params.append('source_type', source);
    if (hasUnion) params.append('has_union', hasUnion);
    if (hasOsha) params.append('has_osha', hasOsha);

    const url = `${API_BASE}/employers/unified/search?${params}`;
    console.log('Fetching:', url);

    try {
        const response = await fetch(url);
        console.log('Response status:', response.status);
        if (!response.ok) throw new Error('API error: ' + response.status);

        const data = await response.json();
        console.log('Data received:', data.total, 'employers');
        unifiedEmployersResults = data.employers || [];
        renderUnifiedResults(data);
    } catch (e) {
        console.error('Unified employers failed:', e);
        document.getElementById('unifiedResultsInfo').textContent = 'Error: ' + e.message;
    } finally {
        document.getElementById('unifiedLoading').classList.add('hidden');
        document.getElementById('unifiedContent').classList.remove('hidden');
    }
}

function renderUnifiedResults(data) {
    const infoEl = document.getElementById('unifiedResultsInfo');
    const resultsEl = document.getElementById('unifiedResults');
    const employers = data.employers || [];

    infoEl.textContent = `${formatNumber(data.total || employers.length)} employers found`;

    if (employers.length === 0) {
        resultsEl.innerHTML = '<div class="p-8 text-center text-warmgray-400">No results found. Try adjusting filters.</div>';
        return;
    }

    resultsEl.innerHTML = employers.map(item => `
        <div class="p-4 cursor-pointer hover:bg-warmgray-50 transition-colors ${selectedUnifiedItem?.unified_id === item.unified_id ? 'bg-purple-50 border-l-4 border-purple-500' : ''}"
             onclick="selectUnifiedItem('${item.unified_id}')">
            <div class="flex justify-between items-start mb-1">
                <div class="font-semibold text-warmgray-900 truncate flex-1">${escapeHtml(item.employer_name || 'Unknown')}</div>
                ${getSourceBadge(item.source_type)}
            </div>
            <div class="text-sm text-warmgray-500">
                ${escapeHtml(item.city || '')}, ${item.state || ''}
            </div>
            <div class="flex gap-2 mt-2 flex-wrap">
                ${item.osha_match_count ? `<span class="text-xs px-2 py-0.5 rounded bg-red-50 text-red-600">${item.osha_match_count} OSHA matches</span>` : ''}
                ${item.union_name ? `<span class="text-xs px-2 py-0.5 rounded bg-green-50 text-green-600">${escapeHtml(item.union_name)}</span>` : ''}
                ${item.employee_count ? `<span class="text-xs text-warmgray-400">${formatNumber(item.employee_count)} employees</span>` : ''}
            </div>
        </div>
    `).join('');
}

// getSourceBadge() defined in utils.js

async function selectUnifiedItem(unifiedId) {
    selectedUnifiedItem = unifiedEmployersResults.find(r => r.unified_id == unifiedId);
    renderUnifiedResults({ employers: unifiedEmployersResults, total: unifiedEmployersResults.length });

    document.getElementById('unifiedDetailEmpty').classList.add('hidden');
    document.getElementById('unifiedDetail').classList.remove('hidden');

    try {
        const response = await fetch(`${API_BASE}/employers/unified/${unifiedId}`);
        if (!response.ok) throw new Error('API error');

        const detail = await response.json();
        renderUnifiedDetail(detail);
    } catch (e) {
        console.error('Unified detail failed:', e);
        renderUnifiedDetail(selectedUnifiedItem);
    }
}

function renderUnifiedDetail(detail) {
    const el = document.getElementById('unifiedDetail');
    const oshaMatches = detail.osha_matches || [];
    const sourceTypeRaw = String(detail.source_type || '');
    const sourceBadge = getSourceBadge(sourceTypeRaw);
    const hasEmployeeCount = Number(detail.employee_count) > 0;
    const employeeCountDisplay = formatNumber(Number(detail.employee_count) || 0);
    const hasNaicsCode = Boolean(detail.naics_code);
    const safeState = escapeHtml(String(detail.state || ''));
    const safeSourceType = escapeHtml(String(detail.source_type || 'N/A'));
    const safeSourceId = escapeHtml(String(detail.source_id || 'N/A'));
    const safeNaicsCode = escapeHtml(String(detail.naics_code || ''));

    el.innerHTML = `
        <div class="mb-6">
            <h3 class="text-xl font-bold text-warmgray-900">${escapeHtml(detail.employer_name || 'Unknown')}</h3>
            <p class="text-warmgray-500">${escapeHtml(detail.city || '')}, ${safeState}</p>
            <div class="flex gap-2 mt-2 flex-wrap">
                ${sourceBadge}
                ${hasEmployeeCount ? `<span class="badge badge-industry">${employeeCountDisplay} employees</span>` : ''}
                ${detail.union_name ? `<span class="badge badge-public">${escapeHtml(detail.union_name)}</span>` : ''}
            </div>
        </div>

        <div class="space-y-4">
            <div class="bg-warmgray-50 rounded-lg p-4">
                <h4 class="text-xs font-semibold text-warmgray-500 uppercase mb-2">Source Information</h4>
                <div class="text-sm space-y-1">
                    <div><span class="text-warmgray-500">Source:</span> ${safeSourceType}</div>
                    <div><span class="text-warmgray-500">Source ID:</span> ${safeSourceId}</div>
                    ${hasNaicsCode ? `<div><span class="text-warmgray-500">NAICS:</span> ${safeNaicsCode}</div>` : ''}
                </div>
            </div>

            ${oshaMatches.length > 0 ? `
                <div class="bg-red-50 rounded-lg p-4">
                    <h4 class="text-xs font-semibold text-red-700 uppercase mb-2">OSHA Matches (${oshaMatches.length})</h4>
                    <div class="space-y-2 max-h-48 overflow-y-auto">
                        ${oshaMatches.slice(0, 10).map(m => `
                            <div class="text-sm border-l-2 border-red-300 pl-2">
                                <div class="font-medium text-warmgray-700">${escapeHtml(m.estab_name || m.establishment_name || 'Establishment')}</div>
                                <div class="text-xs text-warmgray-500">
                                    ${escapeHtml(m.site_city || m.city || '')}, ${m.site_state || m.state || ''} ·
                                    ${m.total_violations || 0} violations ·
                                    $${formatNumber(m.total_penalties || 0)} penalties
                                </div>
                            </div>
                        `).join('')}
                        ${oshaMatches.length > 10 ? `<div class="text-xs text-warmgray-400">... and ${oshaMatches.length - 10} more</div>` : ''}
                    </div>
                </div>
            ` : ''}

            ${detail.union_fnum ? `
                <div class="bg-green-50 rounded-lg p-4">
                    <h4 class="text-xs font-semibold text-green-700 uppercase mb-2">Union Connection</h4>
                    <div class="text-sm">
                        <div>${escapeHtml(detail.union_name || 'Unknown Union')}</div>
                        <div class="text-xs text-warmgray-500">F-Num: ${detail.union_fnum}</div>
                    </div>
                </div>
            ` : ''}
        </div>
    `;
}
