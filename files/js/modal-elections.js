// modal-elections.js -- NLRB Elections modal

let electionsResults = [];
let selectedElectionItem = null;

function openElectionsModal() {
    console.log('Opening Elections modal...');
    document.getElementById('electionsModal').classList.remove('hidden');
    document.getElementById('electionsModal').classList.add('flex');
    document.body.classList.add('modal-open');

    const stateSelect = document.getElementById('electionsState');
    if (stateSelect.options.length <= 1) {
        const mainStateSelect = document.getElementById('stateFilter');
        for (let i = 1; i < mainStateSelect.options.length; i++) {
            const opt = mainStateSelect.options[i];
            stateSelect.add(new Option(opt.text, opt.value));
        }
    }

    // Auto-load results on open
    loadElections();
}

function closeElectionsModal() {
    document.getElementById('electionsModal').classList.add('hidden');
    document.getElementById('electionsModal').classList.remove('flex');
    document.body.classList.remove('modal-open');
}

async function loadElections() {
    console.log('loadElections called');
    const employer = document.getElementById('electionsEmployerSearch').value;
    const state = document.getElementById('electionsState').value;
    const year = document.getElementById('electionsYear').value;
    const result = document.getElementById('electionsResult').value;
    const minVoters = document.getElementById('electionsMinVoters').value;

    document.getElementById('electionsLoading').classList.remove('hidden');
    document.getElementById('electionsContent').classList.add('hidden');

    const params = new URLSearchParams({ limit: 100 });
    if (employer) params.append('employer_name', employer);
    if (state) params.append('state', state);
    if (year) {
        params.append('year_from', year);
        params.append('year_to', year);
    }
    if (result === 'won') params.append('union_won', 'true');
    if (result === 'lost') params.append('union_won', 'false');
    if (minVoters) params.append('min_voters', minVoters);

    const url = `${API_BASE}/nlrb/elections/search?${params}`;
    console.log('Fetching:', url);

    try {
        const response = await fetch(url);
        console.log('Response status:', response.status);
        if (!response.ok) throw new Error('API error: ' + response.status);

        const data = await response.json();
        console.log('Data received:', data.total, 'elections');
        electionsResults = data.elections || [];

        // Filter out law firms if checkbox is checked
        const excludeLawFirms = document.getElementById('electionsExcludeLawFirms').checked;
        if (excludeLawFirms) {
            electionsResults = electionsResults.filter(e => !e.is_law_firm);
        }
        renderElectionsResults({ ...data, elections: electionsResults, total: electionsResults.length });
    } catch (e) {
        console.error('Elections failed:', e);
        document.getElementById('electionsResultsInfo').textContent = 'Error: ' + e.message;
    } finally {
        document.getElementById('electionsLoading').classList.add('hidden');
        document.getElementById('electionsContent').classList.remove('hidden');
    }
}

function renderElectionsResults(data) {
    const infoEl = document.getElementById('electionsResultsInfo');
    const resultsEl = document.getElementById('electionsResults');

    const results = data.results || data.elections || [];
    infoEl.textContent = `${formatNumber(data.total || results.length)} elections found`;

    if (results.length === 0) {
        resultsEl.innerHTML = '<div class="p-8 text-center text-warmgray-400">No elections found. Try adjusting filters.</div>';
        return;
    }

    resultsEl.innerHTML = results.map(item => {
        const isWon = item.union_won || item.result === 'won' || item.votes_for > item.votes_against;
        const isLost = item.result === 'lost' || (!item.union_won && item.votes_against > item.votes_for);
        const resultBadge = isWon
            ? '<span class="px-2 py-0.5 rounded text-xs font-semibold bg-green-100 text-green-700">WON</span>'
            : isLost
                ? '<span class="px-2 py-0.5 rounded text-xs font-semibold bg-red-100 text-red-700">LOST</span>'
                : '<span class="px-2 py-0.5 rounded text-xs font-semibold bg-yellow-100 text-yellow-700">PENDING</span>';
        const lawFirmBadge = item.is_law_firm
            ? '<span class="badge badge-law-firm ml-1" title="Employer name pattern suggests a law firm - verify employer">Verify</span>'
            : '';

        return `
            <div class="p-4 cursor-pointer hover:bg-warmgray-50 transition-colors ${selectedElectionItem?.case_number === item.case_number ? 'bg-blue-50 border-l-4 border-blue-500' : ''}"
                 onclick="selectElectionItem('${item.case_number}')">
                <div class="flex justify-between items-start mb-1">
                    <div class="text-xs text-warmgray-400">${item.case_number || 'N/A'}</div>
                    <div class="flex items-center gap-1">${resultBadge}${lawFirmBadge}</div>
                </div>
                <div class="font-semibold text-warmgray-900 truncate">${escapeHtml(item.employer_name || item.employer || 'Unknown')}</div>
                <div class="text-sm text-warmgray-500 truncate">
                    ${escapeHtml(item.union_name || item.labor_org || 'Unknown Union')}
                </div>
                <div class="text-sm text-warmgray-500">
                    ${escapeHtml(item.employer_city || item.city || '')}, ${item.employer_state || item.state || ''}
                </div>
                <div class="flex justify-between text-xs text-warmgray-400 mt-2">
                    <span>${item.eligible_voters || 0} eligible</span>
                    <span class="text-green-600">${item.vote_margin > 0 ? '+' + item.vote_margin : ''}</span>
                    <span>${item.election_date || ''}</span>
                </div>
            </div>
        `;
    }).join('');
}

function selectElectionItem(caseNumber) {
    selectedElectionItem = electionsResults.find(r => r.case_number === caseNumber);
    renderElectionsResults({ elections: electionsResults, total: electionsResults.length });

    document.getElementById('electionsDetailEmpty').classList.add('hidden');
    document.getElementById('electionsDetail').classList.remove('hidden');
    renderElectionDetail(selectedElectionItem);
}

function renderElectionDetail(item) {
    if (!item) return;
    const el = document.getElementById('electionsDetail');
    const isWon = item.union_won === true;
    const isLost = item.union_won === false;
    const isPending = item.union_won === null;

    el.innerHTML = `
        <div class="mb-6">
            <div class="text-xs text-warmgray-400 mb-1">${item.case_number || 'N/A'}</div>
            <h3 class="text-xl font-bold text-warmgray-900">${escapeHtml(item.employer_name || 'Unknown')}</h3>
            <p class="text-warmgray-500">${escapeHtml(item.employer_city || '')}, ${item.employer_state || ''}</p>
            <div class="mt-2">
                <span class="badge ${isWon ? 'bg-green-100 text-green-700' : isPending ? 'bg-yellow-100 text-yellow-700' : 'bg-red-100 text-red-700'}">
                    ${isWon ? 'UNION WON' : isPending ? 'PENDING' : 'UNION LOST'}
                </span>
            </div>
        </div>

        <div class="bg-warmgray-50 rounded-lg p-4 mb-4">
            <h4 class="text-xs font-semibold text-warmgray-500 uppercase mb-3">Election Results</h4>
            <div class="grid grid-cols-2 gap-4 text-sm">
                <div>
                    <span class="text-warmgray-500">Eligible Voters:</span>
                    <span class="font-semibold">${item.eligible_voters || 0}</span>
                </div>
                <div>
                    <span class="text-warmgray-500">Vote Margin:</span>
                    <span class="font-semibold ${item.vote_margin > 0 ? 'text-green-600' : item.vote_margin < 0 ? 'text-red-600' : ''}">${item.vote_margin > 0 ? '+' : ''}${item.vote_margin || 0}</span>
                </div>
                <div>
                    <span class="text-warmgray-500">Election Type:</span>
                    <span class="font-semibold">${item.election_type || 'N/A'}</span>
                </div>
                <div>
                    <span class="text-warmgray-500">Election Date:</span>
                    <span class="font-semibold">${item.election_date || 'N/A'}</span>
                </div>
            </div>
        </div>

        <div class="space-y-4">
            <div class="bg-blue-50 rounded-lg p-4">
                <h4 class="text-xs font-semibold text-blue-700 uppercase mb-2">Union</h4>
                <div class="text-sm font-medium">${escapeHtml(item.union_name || item.labor_org || 'Unknown')}</div>
                ${item.aff_abbr ? `<div class="text-xs text-warmgray-500">${item.aff_abbr}</div>` : ''}
            </div>

            <div class="bg-warmgray-50 rounded-lg p-4">
                <h4 class="text-xs font-semibold text-warmgray-500 uppercase mb-2">Case Details</h4>
                <div class="text-sm space-y-1">
                    <div><span class="text-warmgray-500">Filed:</span> ${item.date_filed || 'N/A'}</div>
                    <div><span class="text-warmgray-500">Closed:</span> ${item.date_closed || item.tally_date || 'N/A'}</div>
                    <div><span class="text-warmgray-500">Unit Type:</span> ${item.unit_type || 'N/A'}</div>
                    ${item.naics_code ? `<div><span class="text-warmgray-500">NAICS:</span> ${item.naics_code}</div>` : ''}
                </div>
            </div>
        </div>
    `;
}
