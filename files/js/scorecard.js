// ==========================================
// scorecard.js - Organizing Scorecard modal
// Extracted from organizer_v5.html lines 8166-8998
// ==========================================

let scorecardResults = [];
let selectedScorecardItem = null;

// Current data source mode
let scorecardDataSource = 'osha';
let currentSectorCities = [];
let scorecardOffset = 0;
let scorecardPageSize = 50;
let scorecardHasMore = false;

function formatNaicsDisplay(naicsCode, naicsDescription, fallbackLabel) {
    const code = naicsCode ? String(naicsCode).trim() : '';
    const description = naicsDescription ? String(naicsDescription).trim() : '';
    if (code && description) return `NAICS ${escapeHtml(code)} - ${escapeHtml(description)}`;
    if (code) return `NAICS ${escapeHtml(code)}`;
    return escapeHtml(String(fallbackLabel || 'N/A'));
}

async function openOrganizingScorecard() {
    document.getElementById('scorecardModal').classList.remove('hidden');
    document.getElementById('scorecardModal').classList.add('flex');
    document.body.classList.add('modal-open');

    // Populate scorecard state filter from scorecard data itself.
    await loadScorecardStates();
    await loadCurrentScorecardVersion();

    const stateSelect = document.getElementById('scorecardState');
    if (stateSelect && !stateSelect.dataset.bound) {
        stateSelect.addEventListener('change', () => {
            if (document.getElementById('scorecardDataSource').value === 'osha') {
                loadScorecardResults();
            }
        });
        stateSelect.dataset.bound = '1';
    }

    // Initialize filter visibility
    updateScorecardFilters();
}

function closeOrganizingScorecard() {
    document.getElementById('scorecardModal').classList.add('hidden');
    document.getElementById('scorecardModal').classList.remove('flex');
    document.body.classList.remove('modal-open');
}

// Union preset configurations
const UNION_PRESETS = {
    'AFSCME_NY': {
        name: 'AFSCME New York',
        sectors: ['social_services', 'education', 'building_services', 'civic_organizations', 'government'],
        description: 'State/county/municipal employees - Social services, education, building services'
    },
    'SEIU_NY': {
        name: 'SEIU New York',
        sectors: ['social_services', 'building_services', 'healthcare_ambulatory', 'healthcare_hospitals', 'healthcare_nursing'],
        description: 'Healthcare workers, building services, public sector'
    },
    'UAW_NY': {
        name: 'UAW New York',
        sectors: ['education', 'information'],
        description: 'Higher education, research, tech workers'
    },
    'CWA_NY': {
        name: 'CWA New York',
        sectors: ['broadcasting', 'information', 'publishing'],
        description: 'Communications, media, tech workers'
    }
};

function loadUnionPreset(presetKey) {
    if (!presetKey || !UNION_PRESETS[presetKey]) {
        // Reset to default
        document.getElementById('scorecardDataSource').value = 'osha';
        updateScorecardFilters();
        return;
    }

    const preset = UNION_PRESETS[presetKey];

    // Set data source to first sector in preset
    document.getElementById('scorecardDataSource').value = 'sector:' + preset.sectors[0];

    // Update filters
    updateScorecardFilters();

    // Show info about the preset
    const statsEl = document.getElementById('sectorStatsDisplay');
    statsEl.classList.remove('hidden');
    statsEl.innerHTML = `
        <div class="font-semibold text-blue-700">${preset.name}</div>
        <div class="text-xs text-warmgray-500">${preset.description}</div>
        <div class="text-xs mt-1">Sectors: ${preset.sectors.map(s => s.replace(/_/g, ' ')).join(', ')}</div>
    `;

    // Load results for first sector
    loadScorecardResults();
}

async function updateScorecardFilters() {
    const dataSource = document.getElementById('scorecardDataSource').value;
    const isOsha = dataSource === 'osha';
    const isSector = dataSource.startsWith('sector:');

    scorecardDataSource = dataSource;

    // Toggle filter visibility based on data source
    document.getElementById('scorecardStateContainer').classList.toggle('hidden', isSector);
    document.getElementById('scorecardIndustryContainer').classList.toggle('hidden', isSector);
    document.getElementById('scorecardTierContainer').classList.toggle('hidden', isOsha);
    document.getElementById('scorecardCityContainer').classList.toggle('hidden', isOsha);

    // Update stats display
    const statsEl = document.getElementById('sectorStatsDisplay');

    if (isSector) {
        scorecardHasMore = false;
        updateScorecardLoadMoreButton();
        const sector = dataSource.replace('sector:', '');
        try {
            // Load sector summary
            const response = await fetch(`${API_BASE}/sectors/${sector}/summary`);
            if (response.ok) {
                const data = await response.json();
                const safeSector = escapeHtml(String(data.sector || ''));
                const targetCount = Number(data.targets?.target_count) || 0;
                const unionizedCount = Number(data.unionized?.unionized_count) || 0;
                const densityPct = Number(data.union_density_pct) || 0;
                statsEl.classList.remove('hidden');
                statsEl.innerHTML = `
                    <span class="font-semibold">${safeSector}</span>:
                    <span class="text-green-600">${targetCount} targets</span> \u00B7
                    <span class="text-blue-600">${unionizedCount} unionized</span> \u00B7
                    <span>${densityPct}% density</span>
                `;
            }

            // Load cities for dropdown
            const citiesResp = await fetch(`${API_BASE}/sectors/${sector}/targets/cities`);
            if (citiesResp.ok) {
                const citiesData = await citiesResp.json();
                const citySelect = document.getElementById('scorecardCity');
                citySelect.innerHTML = '<option value="">All Cities</option>';
                (citiesData.cities || []).slice(0, 50).forEach(c => {
                    citySelect.add(new Option(`${c.city} (${c.target_count})`, c.city));
                });
                currentSectorCities = citiesData.cities || [];
            }
        } catch (e) {
            console.error('Failed to load sector info:', e);
        }
    } else {
        statsEl.classList.add('hidden');
    }
}

async function loadScorecardResults() {
    const dataSource = document.getElementById('scorecardDataSource').value;
    scorecardOffset = 0;
    selectedScorecardItem = null;

    // Show loading
    document.getElementById('scorecardLoading').classList.remove('hidden');
    document.getElementById('scorecardContent').classList.add('hidden');

    try {
        if (dataSource.startsWith('sector:')) {
            await loadSectorResults(dataSource.replace('sector:', ''));
        } else {
            await loadOshaResults();
        }
    } catch (e) {
        console.error('Scorecard failed:', e);
        document.getElementById('scorecardResultsInfo').textContent = 'Error loading results. Check that the API is running.';
    } finally {
        document.getElementById('scorecardLoading').classList.add('hidden');
        document.getElementById('scorecardContent').classList.remove('hidden');
    }
}

async function loadOshaResults() {
    const state = document.getElementById('scorecardState').value;
    const industry = document.getElementById('scorecardIndustry').value;
    const minEmp = document.getElementById('scorecardMinEmp').value || 25;
    const maxEmp = document.getElementById('scorecardMaxEmp').value || 5000;
    const minScore = document.getElementById('scorecardMinScore').value || 0;
    const hasContracts = document.getElementById('scorecardContracts').value;

    const params = new URLSearchParams({
        min_employees: minEmp,
        max_employees: maxEmp,
        min_score: minScore,
        offset: String(scorecardOffset),
        page_size: String(scorecardPageSize)
    });

    if (state) params.append('state', state);
    if (industry) params.append('naics_2digit', industry);
    if (hasContracts) params.append('has_contracts', hasContracts);

    const response = await fetch(`${API_BASE}/scorecard/?${params}`);
    if (!response.ok) throw new Error('API error');

    const data = await response.json();
    const rows = data.data || [];
    if (scorecardOffset === 0) {
        scorecardResults = rows;
    } else {
        scorecardResults = scorecardResults.concat(rows);
    }
    scorecardHasMore = Boolean(data.has_more);
    updateScorecardLoadMoreButton();

    renderScorecardResults({
        results: scorecardResults,
        scored_count: data.total || scorecardResults.length,
        shown_count: scorecardResults.length,
    }, 'osha');
}

async function loadSectorResults(sector) {
    const tier = document.getElementById('scorecardTier').value;
    const city = document.getElementById('scorecardCity').value;
    const minEmp = document.getElementById('scorecardMinEmp').value || 25;
    const maxEmp = document.getElementById('scorecardMaxEmp').value || 5000;
    const minScore = document.getElementById('scorecardMinScore').value || 0;
    const hasContracts = document.getElementById('scorecardContracts').value;

    const params = new URLSearchParams({
        limit: 100
    });

    if (tier) params.append('tier', tier);
    if (city) params.append('city', city);
    if (minEmp) params.append('min_employees', minEmp);
    if (maxEmp) params.append('max_employees', maxEmp);
    if (minScore) params.append('min_score', minScore);
    if (hasContracts === 'true') params.append('has_govt_contracts', 'true');
    if (hasContracts === 'false') params.append('has_govt_contracts', 'false');

    const response = await fetch(`${API_BASE}/sectors/${sector}/targets?${params}`);
    if (!response.ok) throw new Error('API error');

    const data = await response.json();
    scorecardResults = (data.targets || []).map(t => ({
        ...t,
        establishment_id: t.id,
        estab_name: t.employer_name,
        site_city: t.city,
        site_state: t.state,
        employee_count: t.best_employee_count || t.employee_count,
        organizing_score: t.total_score,
        naics_code: t.naics_primary,
        naics_description: t.naics_description || t.naics_primary_description || null,
        total_violations: t.osha_violation_count,
        contract_info: {
            contract_count: (t.ny_state_contracts || 0) + (t.nyc_contracts || 0),
            total_funding: t.total_contract_value
        },
        labor_violations: {
            wage_theft_cases: t.nyc_wage_theft_cases || 0,
            wage_theft_amount: t.nyc_wage_theft_amount || 0,
            ulp_cases: t.nyc_ulp_cases || 0,
            local_law_cases: t.nyc_local_law_cases || 0,
            local_law_amount: t.nyc_local_law_amount || 0,
            debarred: t.nyc_debarred || false
        },
        score_breakdown: {
            company_unions: t.score_company_unions || 0,
            industry_density: t.score_industry_density || 0,
            geographic: t.score_geographic || 0,
            size: t.score_size || 0,
            osha: t.score_osha_violations || 0,
            nlrb: t.score_nlrb_momentum || 0,
            contracts: t.score_govt_contracts || 0,
            projections: t.score_projections || 0,
            similarity: t.score_similarity || 0
        },
        _source: 'sector',
        _sector: sector
    }));

    renderScorecardResults({
        results: scorecardResults,
        scored_count: data.total,
        shown_count: scorecardResults.length,
        sector: data.sector
    }, 'sector');
    scorecardHasMore = false;
    updateScorecardLoadMoreButton();
}

function renderScorecardResults(data, source = 'osha') {
    const infoEl = document.getElementById('scorecardResultsInfo');
    const resultsEl = document.getElementById('scorecardResults');

    const sourceLabel = source === 'sector' ? `${data.sector || 'Sector'} targets` : 'establishments';
    const totalCount = data.scored_count || data.total || data.results?.length || 0;
    const shownCount = data.shown_count || data.results?.length || 0;
    infoEl.textContent = `${formatNumber(totalCount)} ${sourceLabel} scored (showing ${shownCount})`;

    if (!data.results || data.results.length === 0) {
        resultsEl.innerHTML = '<div class="p-8 text-center text-warmgray-400">No results found. Try adjusting filters.</div>';
        if (source !== 'sector') {
            scorecardHasMore = false;
            updateScorecardLoadMoreButton();
        }
        return;
    }

    resultsEl.innerHTML = data.results.map((item, idx) => {
        const tierBadge = item.priority_tier ?
            `<span class="badge ${getTierBadgeClass(item.priority_tier)}">${item.priority_tier}</span>` : '';

        return `
        <div class="p-4 cursor-pointer hover:bg-warmgray-50 transition-colors ${selectedScorecardItem?.establishment_id === item.establishment_id ? 'bg-green-50 border-l-4 border-green-500' : ''}"
             onclick="selectScorecardItem('${item.establishment_id}', '${source}')">
            <div class="flex justify-between items-start mb-2">
                <div class="flex-1 min-w-0">
                    <div class="flex items-center gap-2">
                        <span class="text-xs text-warmgray-400">#${idx + 1}</span>
                        <div class="font-semibold text-warmgray-900 truncate">${escapeHtml(item.estab_name || 'Unknown')}</div>
                        ${tierBadge}
                        ${item.ulp_case_count > 0 ? `<span class="badge bg-yellow-100 text-yellow-800">ULP (${item.ulp_case_count})</span>` : ''}
                        ${item.contract_info?.contract_count > 0 ? '<span class="badge bg-orange-100 text-orange-700">Contracts</span>' : ''}
                        ${item.labor_violations?.wage_theft_cases > 0 ? '<span class="badge bg-pink-100 text-pink-700">Labor Viol</span>' : ''}
                    </div>
                    <div class="text-sm text-warmgray-500 truncate">
                        ${escapeHtml(item.site_city || '')}, ${item.site_state || ''} \u00B7 ${formatNaicsDisplay(item.naics_code, item.naics_description, item.industry)}
                    </div>
                </div>
                <div class="text-right ml-3">
                    <div class="text-2xl font-bold ${getScoreColor(item.organizing_score)}">${item.organizing_score || 0}</div>
                    <div class="text-xs text-warmgray-400">score</div>
                </div>
            </div>
            <div class="flex gap-1">
                ${renderMiniScoreBar(item.score_breakdown)}
            </div>
            <div class="flex justify-between text-xs text-warmgray-400 mt-2">
                <span>${formatNumber(item.employee_count || 0)} employees</span>
                <span>${item.total_violations || 0} OSHA viol</span>
                ${item.contract_info?.total_funding > 0 ? `<span class="text-orange-600">$${formatNumber(Math.round(item.contract_info.total_funding))} funding</span>` : ''}
                ${item.labor_violations?.wage_theft_amount > 0 ? `<span class="text-pink-600">$${formatNumber(Math.round(item.labor_violations.wage_theft_amount))} wage theft</span>` : ''}
            </div>
        </div>
    `}).join('');
    updateScorecardLoadMoreButton();
}

function renderMiniScoreBar(breakdown) {
    if (!breakdown) return '';
    return `<div class="flex-1 h-2 bg-warmgray-200 rounded-full overflow-hidden flex">
        ${SCORE_FACTORS.map(f => {
            const val = breakdown[f.key] || 0;
            return `<div class="${f.color}" style="width: ${(val / SCORE_MAX * 100).toFixed(1)}%" title="${f.label}: ${val}/${f.max}"></div>`;
        }).join('')}
    </div>`;
}

async function selectScorecardItem(estabId, source = 'osha') {
    const item = scorecardResults.find(r => String(r.establishment_id) === String(estabId));
    if (!item) return;

    selectedScorecardItem = item;

    // Re-render list to show selection
    const dataSource = document.getElementById('scorecardDataSource').value;
    const isSector = dataSource.startsWith('sector:');
    renderScorecardResults({ results: scorecardResults, scored_count: scorecardResults.length, sector: item._sector }, isSector ? 'sector' : 'osha');

    // Show detail panel
    document.getElementById('scorecardDetailEmpty').classList.add('hidden');
    document.getElementById('scorecardDetail').classList.remove('hidden');

    if (item._source === 'sector') {
        // Render sector detail directly from item data
        renderSectorDetail(item);
    } else {
        // Load detailed scorecard from OSHA API
        try {
            const response = await fetch(`${API_BASE}/scorecard/${estabId}`);
            if (!response.ok) throw new Error('API error');

            const detail = await response.json();
            renderScorecardDetail(detail);
        } catch (e) {
            console.error('Scorecard detail failed:', e);
            renderScorecardDetail({ establishment: item, organizing_score: item.organizing_score, score_breakdown: item.score_breakdown });
        }
    }
}

function updateScorecardLoadMoreButton() {
    const btn = document.getElementById('scorecardLoadMoreBtn');
    if (!btn) return;
    btn.classList.toggle('hidden', !scorecardHasMore || scorecardDataSource !== 'osha');
}

async function loadMoreScorecardResults() {
    if (!scorecardHasMore || scorecardDataSource !== 'osha') return;
    scorecardOffset += scorecardPageSize;
    await loadOshaResults();
}

async function loadScorecardStates() {
    const stateSelect = document.getElementById('scorecardState');
    if (!stateSelect) return;
    stateSelect.innerHTML = '<option value="">All States</option>';
    try {
        const resp = await fetch(`${API_BASE}/scorecard/states`);
        if (!resp.ok) return;
        const rows = await resp.json();
        (rows || []).forEach(r => {
            const state = String(r.state || '').trim();
            if (!state) return;
            const count = Number(r.count || 0);
            stateSelect.add(new Option(`${state} (${formatNumber(count)})`, state));
        });
    } catch (e) {
        console.error('Failed to load scorecard states:', e);
    }
}

async function loadCurrentScorecardVersion() {
    const el = document.getElementById('scorecardVersionText');
    if (!el) return;
    try {
        const resp = await fetch(`${API_BASE}/scorecard/versions/current`);
        if (!resp.ok) {
            el.textContent = 'Score version: unavailable';
            return;
        }
        const payload = await resp.json();
        const current = payload.current || {};
        const v = current.version_name || current.version || current.id || 'N/A';
        const tsRaw = current.created_at || current.refreshed_at || null;
        const ts = tsRaw ? new Date(tsRaw).toLocaleString() : 'unknown';
        el.textContent = `Score ${v} - last refreshed ${ts}`;
    } catch (e) {
        console.error('Failed to load scorecard version:', e);
        el.textContent = 'Score version: unavailable';
    }
}

function renderSectorDetail(item) {
    const el = document.getElementById('scorecardDetail');
    const breakdown = item.score_breakdown || {};

    el.innerHTML = `
        <!-- Header -->
        <div class="mb-6">
            <h3 class="text-xl font-bold text-warmgray-900">${escapeHtml(item.estab_name || 'Unknown')}</h3>
            <p class="text-warmgray-500">${escapeHtml(item.site_city || '')}, ${escapeHtml(item.site_state || '')}</p>
            <div class="flex gap-2 mt-2 flex-wrap">
                ${item.priority_tier ? `<span class="badge ${getTierBadgeClass(item.priority_tier)}">${escapeHtml(item.priority_tier)} Priority</span>` : ''}
                <span class="badge badge-industry">${formatNaicsDisplay(item.naics_code, item.naics_description, item.industry)}</span>
                <span class="badge badge-private">${formatNumber(item.employee_count || 0)} employees</span>
                ${item.contract_info?.contract_count > 0 ? '<span class="badge bg-orange-100 text-orange-700">Has Govt Contracts</span>' : ''}
            </div>
        </div>

        ${getScorecardFlagHTML()}

        <!-- Score breakdown -->
        <div class="bg-gradient-to-r from-green-50 to-warmgray-50 rounded-lg p-4 mb-6">
            <div class="flex items-center justify-between mb-4">
                <span class="text-sm font-semibold text-warmgray-700">Organizing Score</span>
                <span class="text-4xl font-bold ${getScoreColor(item.organizing_score)}">${item.organizing_score || 0}</span>
            </div>

            <div class="space-y-3">
                ${SCORE_FACTORS.map(f => renderScoreRow(f.label, breakdown[f.key], f.max, f.color, f.desc, getScoreReason(f.key, item))).join('\n                ')}
            </div>
        </div>

        <!-- Contract Details -->
        ${item.contract_info?.total_funding > 0 ? `
        <div class="bg-orange-50 rounded-lg p-4 mb-6">
            <h4 class="font-semibold text-orange-800 mb-2">Government Contracts</h4>
            <div class="grid grid-cols-2 gap-4 text-sm">
                <div>
                    <div class="text-orange-600 font-semibold">$${formatNumber(Math.round(item.contract_info.total_funding))}</div>
                    <div class="text-warmgray-500">Total Contract Value</div>
                </div>
                <div>
                    <div class="text-orange-600 font-semibold">${item.contract_info.contract_count}</div>
                    <div class="text-warmgray-500">Contracts</div>
                </div>
            </div>
        </div>
        ` : ''}

        <!-- OSHA Details -->
        ${item.total_violations > 0 ? `
        <div class="bg-red-50 rounded-lg p-4 mb-6">
            <h4 class="font-semibold text-red-800 mb-2">OSHA Violations</h4>
            <div class="grid grid-cols-2 gap-4 text-sm">
                <div>
                    <div class="text-red-600 font-semibold">${item.total_violations}</div>
                    <div class="text-warmgray-500">Violations</div>
                </div>
                <div>
                    <div class="text-red-600 font-semibold">$${formatNumber(Math.round(item.osha_total_penalties || 0))}</div>
                    <div class="text-warmgray-500">Total Penalties</div>
                </div>
            </div>
        </div>
        ` : ''}

        <!-- Labor Violations (NYC Comptroller) -->
        ${(item.labor_violations?.wage_theft_cases > 0 || item.labor_violations?.ulp_cases > 0 || item.labor_violations?.local_law_cases > 0) ? `
        <div class="bg-pink-50 rounded-lg p-4 mb-6">
            <h4 class="font-semibold text-pink-800 mb-2">Labor Violations (NYC Comptroller)</h4>
            <div class="grid grid-cols-2 gap-4 text-sm">
                ${item.labor_violations.wage_theft_cases > 0 ? `
                <div>
                    <div class="text-pink-600 font-semibold">${item.labor_violations.wage_theft_cases} cases</div>
                    <div class="text-warmgray-500">Wage Theft ($${formatNumber(Math.round(item.labor_violations.wage_theft_amount))})</div>
                </div>
                ` : ''}
                ${item.labor_violations.ulp_cases > 0 ? `
                <div>
                    <div class="text-pink-600 font-semibold">${item.labor_violations.ulp_cases} cases</div>
                    <div class="text-warmgray-500">NLRB ULP Cases</div>
                </div>
                ` : ''}
                ${item.labor_violations.local_law_cases > 0 ? `
                <div>
                    <div class="text-pink-600 font-semibold">${item.labor_violations.local_law_cases} cases</div>
                    <div class="text-warmgray-500">PSSL/Fair Workweek ($${formatNumber(Math.round(item.labor_violations.local_law_amount))})</div>
                </div>
                ` : ''}
                ${item.labor_violations.debarred ? `
                <div>
                    <div class="text-pink-600 font-semibold">DEBARRED</div>
                    <div class="text-warmgray-500">NYS Debarment List</div>
                </div>
                ` : ''}
            </div>
        </div>
        ` : ''}

        <!-- Additional Info -->
        <div class="border-t border-warmgray-200 pt-4">
            <h4 class="font-semibold text-warmgray-700 mb-2">Data Sources</h4>
            <div class="text-sm text-warmgray-500 space-y-1">
                <div>\u2022 Employer data from Mergent Intellect</div>
                ${item.ny990_id ? '<div>\u2022 IRS Form 990 data matched</div>' : ''}
                ${item.matched_f7_employer_id ? '<div>\u2022 F-7 union contract matched (UNIONIZED)</div>' : ''}
                ${item.nlrb_case_number ? '<div>\u2022 NLRB election on record</div>' : ''}
                ${item.osha_establishment_id ? '<div>\u2022 OSHA establishment matched</div>' : ''}
            </div>
        </div>

        <!-- EIN for verification -->
        ${item.ein ? `
        <div class="mt-4 text-xs text-warmgray-400">
            EIN: ${item.ein} \u00B7 DUNS: ${item.duns || 'N/A'}
        </div>
        ` : ''}
    `;

    // Load flags for this sector target (use MERGENT source type with duns as ID)
    const sectorSourceId = item.duns || item.establishment_id || item.id;
    if (sectorSourceId) {
        loadScorecardFlags('MERGENT', sectorSourceId);
    }
}

function renderScorecardDetail(detail) {
    const el = document.getElementById('scorecardDetail');
    const estab = detail.establishment || {};
    const breakdown = detail.score_breakdown || {};
    const violations = detail.violations || {};
    const contracts = detail.contracts || {};
    const context = detail.context || {};
    const organizingScoreValue = Number(detail.organizing_score) || 0;
    const organizingScoreColor = getScoreColor(organizingScoreValue);
    const predictedWinPct = Number(detail.nlrb_context?.predicted_win_pct);
    const nlrbDescription = Number.isFinite(predictedWinPct)
        ? `Predicted ${predictedWinPct.toFixed(0)}% win probability`
        : 'Past election activity for this employer';

    el.innerHTML = `
        <!-- Header -->
        <div class="mb-6">
            <h3 class="text-xl font-bold text-warmgray-900">${escapeHtml(estab.estab_name || 'Unknown')}</h3>
            <p class="text-warmgray-500">${escapeHtml(estab.site_city || '')}, ${escapeHtml(estab.site_state || '')} ${escapeHtml(estab.site_zip || '')}</p>
            <div class="flex gap-2 mt-2 flex-wrap">
                <span class="badge badge-industry">${formatNaicsDisplay(estab.naics_code, estab.naics_description, 'N/A')}</span>
                <span class="badge badge-private">${formatNumber(estab.employee_count || 0)} employees</span>
                ${contracts.federal_contract_count > 0 ? '<span class="badge bg-orange-100 text-orange-700">Has Govt Contracts</span>' : ''}
            </div>
        </div>

        ${getScorecardFlagHTML()}

        <!-- Data Quality -->
        ${renderScorecardDataQuality(detail)}

        <!-- Score breakdown -->
        <div class="bg-gradient-to-r from-green-50 to-warmgray-50 rounded-lg p-4 mb-6">
            <div class="flex items-center justify-between mb-4">
                <span class="text-sm font-semibold text-warmgray-700">Organizing Potential Score</span>
                <span class="text-4xl font-bold ${organizingScoreColor}">${organizingScoreValue}</span>
            </div>

            <div class="space-y-3">
                ${renderScoreRow('Company Union Shops', breakdown.company_unions, 20, 'bg-indigo-500', 'Related company locations with union presence')}
                ${renderScoreRow('Industry Density', breakdown.industry_density, 10, 'bg-blue-500', 'Union membership rate in NAICS sector')}
                ${renderScoreRow('Geographic', breakdown.geographic, 10, 'bg-purple-500', 'State union membership vs national average')}
                ${renderScoreRow('Establishment Size', breakdown.size, 10, 'bg-yellow-500', 'Sweet spot 50-250 employees')}
                ${renderScoreRow('OSHA Violations', breakdown.osha, 10, 'bg-red-500', 'Workplace safety violations on record')}
                ${renderScoreRow('NLRB Patterns', breakdown.nlrb, 10, 'bg-green-500', nlrbDescription)}
                ${renderScoreRow('Govt Contracts', breakdown.contracts, 10, 'bg-orange-500', 'NY State & NYC contract funding')}
                ${renderScoreRow('Industry Growth', breakdown.projections, 10, 'bg-teal-500', 'BLS industry employment projections')}
                ${renderScoreRow('Union Similarity', breakdown.similarity, 10, 'bg-cyan-500', 'Gower distance to unionized employers')}
            </div>
        </div>

        <!-- Similarity Context -->
        ${detail.similarity_context?.similarity_score ? `
        <div class="mb-6">
            <h4 class="text-sm font-semibold text-warmgray-700 uppercase tracking-wide mb-3">Union Similarity</h4>
            <div class="bg-cyan-50 rounded-lg p-3">
                <div class="flex justify-between items-center">
                    <span class="text-sm text-cyan-700">Similarity to unionized employers</span>
                    <span class="text-lg font-bold text-cyan-700">${(detail.similarity_context.similarity_score * 100).toFixed(0)}%</span>
                </div>
                <div class="w-full bg-cyan-200 rounded-full h-2 mt-2">
                    <div class="bg-cyan-500 h-2 rounded-full" style="width: ${(detail.similarity_context.similarity_score * 100).toFixed(0)}%"></div>
                </div>
                <p class="text-xs text-warmgray-500 mt-2">Based on Gower distance across 14 features (industry, size, geography, violations, contracts)</p>
            </div>
        </div>
        ` : ''}

        <!-- NLRB Success Patterns -->
        ${detail.nlrb_context?.predicted_win_pct ? `
        <div class="mb-6">
            <h4 class="text-sm font-semibold text-warmgray-700 uppercase tracking-wide mb-3">NLRB Success Prediction</h4>
            <div class="bg-green-50 rounded-lg p-3">
                <div class="flex justify-between items-center">
                    <span class="text-sm text-green-700">Predicted election win probability</span>
                    <span class="text-lg font-bold text-green-700">${detail.nlrb_context.predicted_win_pct.toFixed(1)}%</span>
                </div>
                <div class="w-full bg-green-200 rounded-full h-2 mt-2">
                    <div class="bg-green-500 h-2 rounded-full" style="width: ${Math.min(100, detail.nlrb_context.predicted_win_pct).toFixed(0)}%"></div>
                </div>
                <div class="grid grid-cols-3 gap-2 mt-3 text-xs">
                    <div class="text-center">
                        <div class="font-semibold text-green-700">${detail.nlrb_context.state_win_rate ? detail.nlrb_context.state_win_rate.toFixed(0) + '%' : 'N/A'}</div>
                        <div class="text-warmgray-500">State rate</div>
                    </div>
                    <div class="text-center">
                        <div class="font-semibold text-green-700">${detail.nlrb_context.industry_win_rate ? detail.nlrb_context.industry_win_rate.toFixed(0) + '%' : 'N/A'}</div>
                        <div class="text-warmgray-500">Industry rate</div>
                    </div>
                    <div class="text-center">
                        <div class="font-semibold text-green-700">${detail.nlrb_context.direct_case_count || 0}</div>
                        <div class="text-warmgray-500">Past cases</div>
                    </div>
                </div>
                <p class="text-xs text-warmgray-500 mt-2">Based on 33K NLRB elections: state win rate, industry patterns, and unit size</p>
            </div>
        </div>
        ` : ''}

        <!-- ULP History -->
        ${detail.ulp_context ? `
        <div class="mb-6">
            <h4 class="text-sm font-semibold text-warmgray-700 uppercase tracking-wide mb-3">Unfair Labor Practice History</h4>
            <div class="bg-yellow-50 rounded-lg p-3 mb-3">
                <div class="flex justify-between items-center">
                    <span class="text-sm text-yellow-800">${detail.ulp_context.total_cases} ULP case${detail.ulp_context.total_cases !== 1 ? 's' : ''}</span>
                    <span class="text-sm font-semibold text-yellow-800">${detail.ulp_context.employer_ulp_cases} employer-charged (CA)</span>
                </div>
                ${detail.ulp_context.date_range?.earliest ? `
                <div class="text-xs text-warmgray-500 mt-1">
                    Date range: ${detail.ulp_context.date_range.earliest} to ${detail.ulp_context.date_range.latest || 'present'}
                </div>
                ` : ''}
            </div>
            ${detail.ulp_context.section_breakdown?.length > 0 ? `
            <div class="mb-3">
                <div class="text-xs font-semibold text-warmgray-600 mb-1">Top Allegation Sections</div>
                <div class="space-y-1">
                    ${detail.ulp_context.section_breakdown.map(s => `
                        <div class="flex justify-between text-xs">
                            <span class="text-warmgray-700">${escapeHtml(s.section)}</span>
                            <span class="text-yellow-700 font-semibold">${s.count} allegation${s.count !== 1 ? 's' : ''}</span>
                        </div>
                    `).join('')}
                </div>
            </div>
            ` : ''}
            ${detail.ulp_context.recent_cases?.length > 0 ? `
            <div class="space-y-2 max-h-40 overflow-y-auto">
                ${detail.ulp_context.recent_cases.map(c => `
                    <div class="text-sm border-l-2 border-yellow-400 pl-2">
                        <div class="font-medium text-warmgray-700">${escapeHtml(c.case_number)}</div>
                        <div class="text-xs text-warmgray-500">Type: ${c.case_type} | ${c.latest_date || c.earliest_date || 'Date unknown'}</div>
                    </div>
                `).join('')}
            </div>
            ` : ''}
        </div>
        ` : ''}

        <!-- Government Contracts -->
        ${contracts.contract_count > 0 ? `
        <div class="mb-6">
            <h4 class="text-sm font-semibold text-warmgray-700 uppercase tracking-wide mb-3">Government Contracts</h4>
            <div class="bg-orange-50 rounded-lg p-3 mb-3">
                <div class="flex justify-between">
                    <span class="text-sm text-orange-700">${contracts.contract_count} contract(s)</span>
                    <span class="text-sm font-semibold text-orange-700">$${formatNumber(contracts.total_funding || 0)} total</span>
                </div>
            </div>
            ${contracts.records && contracts.records.length > 0 ? `
                <div class="space-y-2 max-h-40 overflow-y-auto">
                    ${contracts.records.slice(0, 5).map(c => `
                        <div class="text-sm border-l-2 border-orange-300 pl-2">
                            <div class="font-medium text-warmgray-700">${escapeHtml(c.title || 'Contract')}</div>
                            <div class="text-xs text-warmgray-500">${c.source || ''} \u00B7 ${c.agency_name || ''} \u00B7 $${formatNumber(c.amount || 0)}</div>
                        </div>
                    `).join('')}
                </div>
            ` : ''}
        </div>
        ` : ''}

        <!-- Violations detail -->
        <div class="mb-6">
            <h4 class="text-sm font-semibold text-warmgray-700 uppercase tracking-wide mb-3">Safety Violations</h4>
            ${violations.count > 0 ? `
                <div class="bg-red-50 rounded-lg p-3 mb-3">
                    <div class="flex justify-between">
                        <span class="text-sm text-red-700">${violations.count} total violations</span>
                        <span class="text-sm text-red-700">Severity: ${violations.severity_score || 0}</span>
                    </div>
                </div>
                ${violations.recent && violations.recent.length > 0 ? `
                    <div class="space-y-2 max-h-40 overflow-y-auto">
                        ${violations.recent.slice(0, 5).map(v => `
                            <div class="text-sm border-l-2 border-red-300 pl-2">
                                <div class="font-medium text-warmgray-700">${escapeHtml(v.standard || 'Unknown standard')}</div>
                                <div class="text-xs text-warmgray-500">${v.violation_type || ''} \u00B7 ${v.issuance_date || ''} \u00B7 $${formatNumber(v.current_penalty || 0)}</div>
                            </div>
                        `).join('')}
                    </div>
                ` : ''}
            ` : '<div class="text-warmgray-400 text-sm">No OSHA violations on record</div>'}
        </div>

        <!-- Context -->
        <div class="mb-6">
            <h4 class="text-sm font-semibold text-warmgray-700 uppercase tracking-wide mb-3">Organizing Context</h4>
            <div class="grid grid-cols-2 gap-3 text-sm">
                <div class="bg-warmgray-100 rounded p-3">
                    <div class="text-warmgray-500">Unions in ${estab.site_state || 'state'}</div>
                    <div class="font-semibold text-warmgray-900">${formatNumber(context.state_union_presence?.union_count || 0)} locals</div>
                </div>
                <div class="bg-warmgray-100 rounded p-3">
                    <div class="text-warmgray-500">Industry union employers</div>
                    <div class="font-semibold text-warmgray-900">${formatNumber(context.industry_union_presence?.union_employers || 0)}</div>
                </div>
                <div class="bg-warmgray-100 rounded p-3">
                    <div class="text-warmgray-500">Recent NLRB cases</div>
                    <div class="font-semibold text-warmgray-900">${formatNumber(context.nlrb_activity?.case_count || 0)} (3 yr)</div>
                </div>
            </div>
        </div>

        <!-- Nearby unions -->
        ${detail.nearby_unions && detail.nearby_unions.length > 0 ? `
            <div class="mb-6">
                <h4 class="text-sm font-semibold text-warmgray-700 uppercase tracking-wide mb-3">Active Unions in ${estab.site_state || 'State'}</h4>
                <div class="flex flex-wrap gap-2">
                    ${detail.nearby_unions.map(u => `
                        <span class="px-2 py-1 bg-warmgray-100 rounded text-sm">
                            ${escapeHtml(u.aff_abbr)} <span class="text-warmgray-400">(${u.local_count})</span>
                        </span>
                    `).join('')}
                </div>
            </div>
        ` : ''}

        <!-- Similar union employers -->
        ${detail.similar_union_employers && detail.similar_union_employers.length > 0 ? `
            <div>
                <h4 class="text-sm font-semibold text-warmgray-700 uppercase tracking-wide mb-3">Similar Unionized Employers</h4>
                <div class="space-y-2 max-h-48 overflow-y-auto">
                    ${detail.similar_union_employers.map(e => `
                        <div class="text-sm border-l-2 border-green-300 pl-2">
                            <div class="font-medium text-warmgray-700">${escapeHtml(e.employer_name)}</div>
                            <div class="text-xs text-warmgray-500">
                                ${escapeHtml(e.city || '')}, ${e.state || ''} \u00B7
                                ${formatNumber(e.latest_unit_size || 0)} workers \u00B7
                                <span class="text-green-600">${escapeHtml(e.aff_abbr || e.union_name || 'Union')}</span>
                            </div>
                        </div>
                    `).join('')}
                </div>
            </div>
        ` : ''}
    `;

    // Load flags for this OSHA establishment
    const oshaSourceId = estab.establishment_id || estab.id;
    if (oshaSourceId) {
        loadScorecardFlags('OSHA', oshaSourceId);
    }
}

function renderScorecardDataQuality(detail) {
    const estab = detail.establishment || {};
    const osha = detail.osha_context || {};
    const geo = detail.geographic_context || {};

    // Count how many non-zero score factors exist
    const breakdown = detail.score_breakdown || {};
    const factorsWithData = SCORE_FACTORS.filter(f => (breakdown[f.key] || 0) > 0).length;
    const coverageLabel = factorsWithData >= 7 ? 'HIGH' : factorsWithData >= 4 ? 'MEDIUM' : 'LOW';
    const coverageColor = factorsWithData >= 7 ? 'bg-green-100 text-green-700'
        : factorsWithData >= 4 ? 'bg-yellow-100 text-yellow-700'
        : 'bg-orange-100 text-orange-700';

    // Source freshness
    let freshnessInfo = '';
    if (typeof freshnessData !== 'undefined' && freshnessData && freshnessData.sources) {
        const oshaSrc = freshnessData.sources.find(s => s.source_name === 'osha_inspections');
        if (oshaSrc && oshaSrc.last_updated) {
            const updated = new Date(oshaSrc.last_updated);
            const daysSince = Math.floor((Date.now() - updated.getTime()) / 86400000);
            freshnessInfo = `<span class="text-xs text-warmgray-400">OSHA data: ${daysSince}d old</span>`;
        }
    }

    return `
        <div class="flex items-center gap-2 mb-4 flex-wrap">
            <span class="text-xs px-2 py-0.5 rounded font-medium ${coverageColor}">${coverageLabel} coverage</span>
            <span class="text-xs text-warmgray-400">${factorsWithData}/${SCORE_FACTORS.length} factors with data</span>
            ${freshnessInfo}
        </div>
    `;
}

function renderScoreRow(label, score, max, colorClass, description, reason) {
    const pct = Math.round((score / max) * 100);
    return `
        <div>
            <div class="flex justify-between text-xs mb-1">
                <span class="text-warmgray-600" title="${description}">${label}</span>
                <span class="font-semibold">${score || 0}/${max}</span>
            </div>
            <div class="h-2 bg-warmgray-200 rounded-full overflow-hidden">
                <div class="${colorClass} h-full rounded-full transition-all" style="width: ${pct}%"></div>
            </div>
            ${reason ? `<div class="text-xs text-warmgray-500 mt-1 italic">${reason}</div>` : ''}
        </div>
    `;
}

// Generate human-readable reason text for score components
// Prefers server-provided explanations when available, falls back to client-side logic
function getScoreReason(type, item) {
    // Use server-provided explanation if available
    const explanations = item.score_explanations || {};
    if (explanations[type]) return explanations[type];

    const emp = item.employee_count || item.best_employee_count || 0;
    const breakdown = item.score_breakdown || {};
    const contractInfo = item.contract_info || {};
    const laborViol = item.labor_violations || {};

    switch(type) {
        case 'size':
            if (emp >= 50 && emp <= 250) return `${formatNumber(emp)} employees (50-250 organizing sweet spot)`;
            if (emp > 250 && emp <= 500) return `${formatNumber(emp)} employees (mid-size, feasible target)`;
            if (emp >= 25 && emp < 50) return `${formatNumber(emp)} employees (small but organizable)`;
            if (emp > 500 && emp <= 1000) return `${formatNumber(emp)} employees (large, requires more resources)`;
            if (emp > 1000) return `${formatNumber(emp)} employees (very large unit)`;
            if (emp > 0) return `${formatNumber(emp)} employees (very small unit)`;
            return 'No employee data';

        case 'industry_density': {
            const score = breakdown.industry_density || 0;
            if (score >= 10) return '15%+ union density in sector (very high)';
            if (score >= 8) return '10-15% union density in sector (high)';
            if (score >= 6) return '5-10% union density in sector (moderate)';
            if (score >= 4) return '2-5% union density in sector (low)';
            if (score >= 2) return 'Under 2% union density (very low)';
            return 'Density data unavailable';
        }

        case 'nlrb': {
            const score = breakdown.nlrb || 0;
            if (score >= 10) return 'High predicted win probability';
            if (score >= 7) return 'Above-average predicted win probability';
            if (score >= 4) return 'Moderate predicted win probability';
            if (score > 0) return 'Below-average predicted win probability';
            return 'No NLRB prediction available';
        }

        case 'osha': {
            const violations = item.total_violations || item.osha_violation_count || 0;
            if (violations === 0) return 'No OSHA violations on record';
            const ratio = item.osha_industry_ratio;
            if (ratio && ratio > 1) return `${violations} violations (${ratio.toFixed(1)}x industry average)`;
            return `${violations} violations`;
        }

        case 'contracts': {
            const total = contractInfo.total_funding || item.total_contract_value || 0;
            const count = contractInfo.federal_contract_count || 0;
            if (total >= 1000000) return `$${(total / 1000000).toFixed(1)}M across ${count} federal contract${count !== 1 ? 's' : ''}`;
            if (total >= 1000) return `$${(total / 1000).toFixed(0)}K across ${count} federal contract${count !== 1 ? 's' : ''}`;
            if (total > 0) return `$${formatNumber(Math.round(total))} in ${count} federal contract${count !== 1 ? 's' : ''}`;
            return 'No federal contracts on record';
        }

        case 'geographic': {
            const score = breakdown.geographic || 0;
            if (score >= 8) return 'Favorable organizing geography (non-RTW, high win rate)';
            if (score >= 5) return 'Moderate organizing geography';
            if (score >= 2) return 'Challenging organizing geography';
            return 'Geographic data unavailable';
        }

        case 'company_unions': {
            const score = breakdown.company_unions || 0;
            if (score >= 15) return 'Multiple related locations with union presence';
            if (score >= 10) return 'Related location has union representation';
            if (score >= 5) return 'Same-sector employer has nearby union';
            return 'No related union presence detected';
        }

        case 'projections': {
            const score = breakdown.projections || 0;
            if (score >= 8) return 'Industry projected for strong growth (BLS)';
            if (score >= 5) return 'Industry projected for moderate growth (BLS)';
            if (score >= 3) return 'Industry projected for slow growth (BLS)';
            return 'Industry growth data unavailable';
        }

        case 'similarity': {
            const score = breakdown.similarity || 0;
            if (score >= 8) return 'Very similar to successfully organized employers';
            if (score >= 5) return 'Moderately similar to organized employers';
            if (score >= 3) return 'Some similarity to organized employers';
            return 'Low similarity to organized employers';
        }

        default:
            return '';
    }
}
