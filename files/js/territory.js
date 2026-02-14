// territory.js — Territory mode functions
// Extracted from organizer_v5.html lines 2441-3105

// ==========================================
// TERRITORY: UNION SELECTOR & QUICK START
// ==========================================
async function loadTerritoryDropdowns() {
    try {
        // Load affiliations for union dropdown
        const resp = await fetch(`${API_BASE}/lookups/affiliations`);
        if (!resp.ok) throw new Error('Failed to load affiliations');
        const data = await resp.json();
        const select = document.getElementById('territoryUnion');
        (data.affiliations || []).forEach(a => {
            const opt = document.createElement('option');
            opt.value = a.aff_abbr;
            opt.textContent = `${a.aff_abbr} (${formatNumber(a.total_members || 0)} members)`;
            select.appendChild(opt);
        });

        // Load states for territory state dropdown
        const stateResp = await fetch(`${API_BASE}/lookups/states`);
        if (stateResp.ok) {
            const stateData = await stateResp.json();
            const stateSelect = document.getElementById('territoryState');
            (stateData.states || []).forEach(s => {
                const opt = document.createElement('option');
                opt.value = s.state || s;
                opt.textContent = s.state || s;
                stateSelect.appendChild(opt);
            });
        }
    } catch (e) {
        console.error('Failed to load territory dropdowns:', e);
    }
}

async function loadQuickStartUnions() {
    try {
        // Fetch unions + total target count in parallel
        const [resp, targetResp] = await Promise.all([
            fetch(`${API_BASE}/unions/national?limit=100`),
            fetch(`${API_BASE}/organizing/scorecard?limit=1&min_score=20`).catch(() => null)
        ]);
        if (!resp.ok) throw new Error('Failed');

        // Show targets count on welcome screen
        if (targetResp && targetResp.ok) {
            const td = await targetResp.json();
            const wt = document.getElementById('welcomeTargets');
            if (wt) wt.textContent = formatNumber(td.total || 0);
        }

        const data = await resp.json();
        const unions = (data.national_unions || [])
            .sort((a, b) => (b.total_members || 0) - (a.total_members || 0))
            .slice(0, 8);

        const grid = document.getElementById('quickStartGrid');
        grid.innerHTML = unions.map(u => `
            <div class="territory-card" onclick="selectQuickStartUnion('${escapeHtml(u.aff_abbr)}')">
                <div class="text-2xl font-bold text-warmgray-900 headline mb-1">${escapeHtml(u.aff_abbr)}</div>
                <div class="text-accent-red font-semibold text-lg">${formatNumber(u.total_members || 0)}</div>
                <div class="text-warmgray-400 text-xs mt-1">members</div>
                <div class="flex justify-between mt-3 text-xs text-warmgray-500">
                    <span>${u.local_count || 0} locals</span>
                    <span>${u.state_count || 0} states</span>
                </div>
            </div>
        `).join('');
    } catch (e) {
        console.error('Failed to load quick start unions:', e);
        document.getElementById('quickStartGrid').innerHTML =
            '<div class="col-span-4 text-center text-warmgray-400 py-8">Failed to load unions. Is the API running?</div>';
    }
}

function selectQuickStartUnion(abbr) {
    document.getElementById('territoryUnion').value = abbr;
    territoryContext.union = abbr;
    loadTerritoryDashboard();
}

function onTerritoryUnionChange() {
    territoryContext.union = document.getElementById('territoryUnion').value;
}

async function onTerritoryStateChange() {
    const state = document.getElementById('territoryState').value;
    territoryContext.state = state;
    territoryContext.metro = '';

    const metroSelect = document.getElementById('territoryMetro');
    metroSelect.innerHTML = '<option value="">All Metros</option>';

    if (!state) {
        metroSelect.disabled = true;
        return;
    }

    metroSelect.disabled = false;
    try {
        const resp = await fetch(`${API_BASE}/lookups/metros?state=${state}`);
        if (resp.ok) {
            const data = await resp.json();
            (data.metros || []).forEach(m => {
                const opt = document.createElement('option');
                opt.value = m.cbsa_code || m;
                opt.textContent = m.cbsa_title || m;
                metroSelect.appendChild(opt);
            });
        }
    } catch (e) {
        console.error('Failed to load metros:', e);
    }
}

function onTerritoryMetroChange() {
    territoryContext.metro = document.getElementById('territoryMetro').value;
}

async function loadTerritoryDashboard() {
    const union = territoryContext.union || document.getElementById('territoryUnion').value;
    const state = territoryContext.state || document.getElementById('territoryState').value;

    if (!union && !state) {
        // Nothing selected, show welcome
        document.getElementById('territoryWelcome').classList.remove('hidden');
        document.getElementById('territoryDashboard').classList.add('hidden');
        return;
    }

    territoryContext.union = union;
    territoryContext.state = state;
    territoryContext.metro = document.getElementById('territoryMetro').value || '';

    // Switch to dashboard view
    document.getElementById('territoryWelcome').classList.add('hidden');
    document.getElementById('territoryDashboard').classList.remove('hidden');

    // Show loading state
    renderTerritoryLoading();

    // Sprint 2 will populate the actual dashboard content
    await fetchTerritoryData();
}

function renderTerritoryLoading() {
    const dash = document.getElementById('territoryDashboard');
    dash.innerHTML = `
        <div class="flex items-center justify-between mb-6">
            <div>
                <h2 class="headline text-2xl font-bold text-warmgray-900">
                    ${territoryContext.union ? escapeHtml(territoryContext.union) : 'All Unions'}
                    ${territoryContext.state ? ' — ' + escapeHtml(territoryContext.state) : ''}
                    ${territoryContext.metro ? ' / ' + escapeHtml(territoryContext.metro) : ''}
                </h2>
                <p class="text-warmgray-500 text-sm mt-0.5">Territory Overview</p>
            </div>
            <div class="flex gap-2">
                <button onclick="exportTerritoryReport()" class="px-4 py-2 bg-warmgray-100 hover:bg-warmgray-200 text-warmgray-700 text-sm font-medium rounded-lg transition-colors flex items-center gap-1">
                    <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M17 17h2a2 2 0 002-2v-4a2 2 0 00-2-2H5a2 2 0 00-2 2v4a2 2 0 002 2h2m2 4h6a2 2 0 002-2v-4a2 2 0 00-2-2H9a2 2 0 00-2 2v4a2 2 0 002 2zm8-12V5a2 2 0 00-2-2H9a2 2 0 00-2 2v4h10z"/></svg>
                    Print Report
                </button>
                <button onclick="exportTerritoryTargetsCSV()" class="px-4 py-2 bg-warmgray-100 hover:bg-warmgray-200 text-warmgray-700 text-sm font-medium rounded-lg transition-colors">
                    Targets CSV
                </button>
                <button onclick="exportTerritoryElectionsCSV()" class="px-4 py-2 bg-warmgray-100 hover:bg-warmgray-200 text-warmgray-700 text-sm font-medium rounded-lg transition-colors">
                    Elections CSV
                </button>
            </div>
        </div>

        <!-- KPI Row -->
        <div id="territoryKPIs" class="grid grid-cols-5 gap-4 mb-6">
            ${[1,2,3,4,5].map(() => '<div class="territory-kpi"><div class="skeleton h-16"></div></div>').join('')}
        </div>

        <!-- Map + Industry Row -->
        <div class="grid grid-cols-5 gap-4 mb-6">
            <div class="col-span-3 bg-white rounded-xl border border-warmgray-200 p-4">
                <div class="section-header">
                    <svg fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M17.657 16.657L13.414 20.9a1.998 1.998 0 01-2.827 0l-4.244-4.243a8 8 0 1111.314 0z"/><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15 11a3 3 0 11-6 0 3 3 0 016 0z"/></svg>
                    Territory Map
                </div>
                <div id="territoryMapContainer" class="skeleton" style="height: 350px; border-radius: 8px;"></div>
            </div>
            <div class="col-span-2 bg-white rounded-xl border border-warmgray-200 p-4">
                <div class="section-header">
                    <svg fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 21V5a2 2 0 00-2-2H7a2 2 0 00-2 2v16m14 0h2m-2 0h-5m-9 0H3m2 0h5M9 7h1m-1 4h1m4-4h1m-1 4h1m-5 10v-5a1 1 0 011-1h2a1 1 0 011 1v5m-4 0h4"/></svg>
                    Industry Union Density
                </div>
                <div id="territoryIndustry" class="skeleton" style="height: 350px;"></div>
            </div>
        </div>

        <!-- Targets + Trends Row -->
        <div class="grid grid-cols-2 gap-4 mb-6">
            <div class="bg-white rounded-xl border border-warmgray-200 p-4">
                <div class="flex justify-between items-center mb-3">
                    <div class="section-header" style="margin-bottom:0">
                        <svg fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z"/></svg>
                        Top Organizing Targets
                    </div>
                    <button onclick="openOrganizingScorecard()" class="text-xs text-accent-red hover:text-accent-redDark font-medium">View All</button>
                </div>
                <div id="territoryTargets"><div class="skeleton h-64"></div></div>
            </div>
            <div class="bg-white rounded-xl border border-warmgray-200 p-4">
                <div class="section-header">
                    <svg fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M7 12l3-3 3 3 4-4M8 21l4-4 4 4M3 4h18M4 4h16v12a1 1 0 01-1 1H5a1 1 0 01-1-1V4z"/></svg>
                    Membership Trends
                </div>
                <div id="territoryTrends"><div class="skeleton h-64"></div></div>
            </div>
        </div>

        <!-- Elections + Hotspots Row -->
        <div class="grid grid-cols-2 gap-4 mb-6">
            <div class="bg-white rounded-xl border border-warmgray-200 p-4">
                <div class="section-header">
                    <svg fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2m-6 9l2 2 4-4"/></svg>
                    Recent NLRB Elections
                </div>
                <div id="territoryElections"><div class="skeleton h-48"></div></div>
            </div>
            <div class="bg-white rounded-xl border border-warmgray-200 p-4">
                <div class="section-header">
                    <svg fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z"/></svg>
                    Top Wage &amp; Safety Violators
                </div>
                <div id="territoryHotspots"><div class="skeleton h-48"></div></div>
            </div>
        </div>
    `;
}

async function fetchTerritoryData() {
    // Sprint 2 implementation - for now just show the skeleton layout
    // This will be replaced with 6 parallel fetches
    const ctx = territoryContext;
    const params = new URLSearchParams();
    if (ctx.state) params.set('state', ctx.state);

    try {
        // Parallel fetches for all sections
        const fetches = [];

        // 1. Union detail (KPIs + industry)
        if (ctx.union) {
            fetches.push(
                fetch(`${API_BASE}/unions/national/${encodeURIComponent(ctx.union)}`)
                    .then(r => r.ok ? r.json() : null)
                    .catch(() => null)
            );
        } else {
            fetches.push(Promise.resolve(null));
        }

        // 2. Organizing targets
        const scorecardParams = new URLSearchParams({ limit: '10', min_score: '20' });
        if (ctx.state) scorecardParams.set('state', ctx.state);
        fetches.push(
            fetch(`${API_BASE}/organizing/scorecard?${scorecardParams}`)
                .then(r => r.ok ? r.json() : null)
                .catch(() => null)
        );

        // 3. Trends
        if (ctx.state) {
            fetches.push(
                fetch(`${API_BASE}/trends/by-state/${ctx.state}`)
                    .then(r => r.ok ? r.json() : null)
                    .catch(() => null)
            );
        } else {
            fetches.push(
                fetch(`${API_BASE}/trends/national`)
                    .then(r => r.ok ? r.json() : null)
                    .catch(() => null)
            );
        }

        // 4. Elections
        const electionParams = new URLSearchParams({ limit: '10' });
        if (ctx.state) electionParams.set('state', ctx.state);
        fetches.push(
            fetch(`${API_BASE}/nlrb/elections/search?${electionParams}`)
                .then(r => r.ok ? r.json() : null)
                .catch(() => null)
        );

        // 5. Density
        fetches.push(
            fetch(`${API_BASE}/density/by-state`)
                .then(r => r.ok ? r.json() : null)
                .catch(() => null)
        );

        // 6. WHD hotspots
        const whdParams = new URLSearchParams({ limit: '10' });
        if (ctx.state) whdParams.set('state', ctx.state);
        fetches.push(
            fetch(`${API_BASE}/whd/top-violators?${whdParams}`)
                .then(r => r.ok ? r.json() : null)
                .catch(() => null)
        );

        // 7. Industry density rates
        fetches.push(
            fetch(`${API_BASE}/density/industry-rates`)
                .then(r => r.ok ? r.json() : null)
                .catch(() => null)
        );

        const [unionData, targetsData, trendsData, electionsData, densityData, whdData, industryData] = await Promise.all(fetches);
        territoryDataCache = { unionData, targetsData, trendsData, electionsData, densityData, whdData, industryData };

        // Render each section
        renderTerritoryKPIs(unionData, densityData);
        renderTerritoryTargets(targetsData);
        renderTerritoryTrends(trendsData);
        renderTerritoryElections(electionsData);
        renderTerritoryHotspots(whdData);
        renderTerritoryIndustry(industryData);
        renderTerritoryMap(targetsData);

    } catch (e) {
        console.error('Failed to load territory data:', e);
        const dash = document.getElementById('territoryDashboard');
        if (dash) {
            dash.innerHTML = `
                <div class="bg-red-50 border border-red-200 rounded-xl p-8 text-center">
                    <div class="text-red-600 font-semibold mb-2">Failed to load territory data</div>
                    <div class="text-red-500 text-sm mb-4">${escapeHtml(e.message || 'Check that the API is running on port 8001')}</div>
                    <button onclick="loadTerritoryDashboard()" class="px-4 py-2 bg-red-600 text-white text-sm font-medium rounded-lg hover:bg-red-700 transition-colors">
                        Retry
                    </button>
                </div>
            `;
        }
    }
}

// ==========================================
// TERRITORY: RENDER FUNCTIONS
// ==========================================
function renderTerritoryKPIs(unionData, densityData) {
    const el = document.getElementById('territoryKPIs');
    if (!el) return;

    let members = 0, locals = 0, workers = 0, targets = 0, density = 0;

    if (unionData) {
        const s = unionData.summary || unionData;
        members = s.total_members || s.members || 0;
        locals = s.local_count || s.locals || 0;
        workers = s.covered_workers || s.workers || 0;
    }

    if (densityData && territoryContext.state) {
        const stateRow = (densityData.states || []).find(s => s.state === territoryContext.state);
        if (stateRow) density = stateRow.total_density_pct || 0;
    } else if (densityData && densityData.states) {
        // Compute average national density
        const allStates = densityData.states;
        const sum = allStates.reduce((acc, s) => acc + (s.total_density_pct || 0), 0);
        density = allStates.length > 0 ? sum / allStates.length : 0;
    }

    el.innerHTML = `
        <div class="territory-kpi text-center">
            <div class="text-xs font-semibold text-warmgray-500 uppercase tracking-wide">Members</div>
            <div class="text-2xl font-bold text-warmgray-900 mt-1">${formatNumber(members)}</div>
        </div>
        <div class="territory-kpi text-center">
            <div class="text-xs font-semibold text-warmgray-500 uppercase tracking-wide">Locals</div>
            <div class="text-2xl font-bold text-warmgray-900 mt-1">${formatNumber(locals)}</div>
        </div>
        <div class="territory-kpi text-center">
            <div class="text-xs font-semibold text-warmgray-500 uppercase tracking-wide">Covered Workers</div>
            <div class="text-2xl font-bold text-warmgray-900 mt-1">${formatNumber(workers)}</div>
        </div>
        <div class="territory-kpi text-center">
            <div class="text-xs font-semibold text-warmgray-500 uppercase tracking-wide">Organizing Targets</div>
            <div class="text-2xl font-bold text-accent-red mt-1">${formatNumber(targets)}</div>
        </div>
        <div class="territory-kpi text-center">
            <div class="text-xs font-semibold text-warmgray-500 uppercase tracking-wide">Union Density</div>
            <div class="text-2xl font-bold text-warmgray-900 mt-1">${typeof density === 'number' ? density.toFixed(1) + '%' : '--'}</div>
        </div>
    `;
}

function renderTerritoryTargets(data) {
    const el = document.getElementById('territoryTargets');
    if (!el) return;

    const targets = data?.results || data?.targets || data?.employers || [];
    if (targets.length === 0) {
        el.innerHTML = '<div class="text-warmgray-400 text-sm text-center py-8">No organizing targets found for this territory</div>';
        return;
    }

    // Update KPI count
    const kpiEl = document.querySelector('#territoryKPIs .territory-kpi:nth-child(4) .text-2xl');
    if (kpiEl) kpiEl.textContent = formatNumber(data?.total || targets.length);

    el.innerHTML = `
        <table class="w-full text-sm">
            <thead>
                <tr class="text-warmgray-500 text-xs uppercase border-b border-warmgray-100">
                    <th class="text-left py-2 font-semibold">Employer</th>
                    <th class="text-left py-2 font-semibold">Location</th>
                    <th class="text-right py-2 font-semibold">Emp</th>
                    <th class="text-right py-2 font-semibold">Score</th>
                    <th class="text-right py-2 font-semibold">Tier</th>
                </tr>
            </thead>
            <tbody>
                ${targets.slice(0, 10).map(t => {
                    const score = t.organizing_score || t.total_score || 0;
                    const tier = t.tier || (score >= 30 ? 'TOP' : score >= 25 ? 'HIGH' : score >= 20 ? 'MEDIUM' : 'LOW');
                    const tierColor = tier === 'TOP' ? 'text-green-700 bg-green-50' : tier === 'HIGH' ? 'text-blue-700 bg-blue-50' : tier === 'MEDIUM' ? 'text-yellow-700 bg-yellow-50' : 'text-warmgray-500 bg-warmgray-50';
                    const eid = t.establishment_id || t.employer_id || t.id;
                    return `
                        <tr class="border-b border-warmgray-50 hover:bg-warmgray-50 cursor-pointer" onclick="openDeepDive('${eid}', 'territory')">
                            <td class="py-2.5 font-medium text-warmgray-900">${escapeHtml(t.estab_name || t.company_name || t.employer_name || '')}</td>
                            <td class="py-2.5 text-warmgray-500">${escapeHtml((t.site_city || t.city || '') + (t.site_state || t.state ? ', ' + (t.site_state || t.state) : ''))}</td>
                            <td class="py-2.5 text-right text-warmgray-500">${t.employee_count ? formatNumber(t.employee_count) : '--'}</td>
                            <td class="py-2.5 text-right font-semibold">${score}</td>
                            <td class="py-2.5 text-right"><span class="badge ${tierColor}">${tier}</span></td>
                        </tr>
                    `;
                }).join('')}
            </tbody>
        </table>
    `;
}

function renderTerritoryTrends(data) {
    const el = document.getElementById('territoryTrends');
    if (!el) return;

    const trends = data?.trends || data?.years || [];
    if (trends.length === 0) {
        el.innerHTML = '<div class="text-warmgray-400 text-sm text-center py-8">No trend data available</div>';
        return;
    }

    // Create canvas for chart
    el.innerHTML = '<canvas id="territoryTrendsChart" height="260"></canvas>';

    // Destroy previous chart if exists
    if (territoryCharts.trends) territoryCharts.trends.destroy();

    const ctx = document.getElementById('territoryTrendsChart').getContext('2d');
    const labels = trends.map(t => t.year);
    const memberData = trends.map(t => (t.total_members_dedup || t.total_members || t.members || 0) / 1000);

    territoryCharts.trends = new Chart(ctx, {
        type: 'line',
        data: {
            labels,
            datasets: [{
                label: 'Members (K)',
                data: memberData,
                borderColor: '#c41e3a',
                backgroundColor: 'rgba(196, 30, 58, 0.1)',
                fill: true,
                tension: 0.3,
                pointRadius: 3,
                pointBackgroundColor: '#c41e3a'
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: { legend: { display: false } },
            scales: {
                x: { grid: { display: false } },
                y: { title: { display: true, text: 'Members (K)', font: { size: 10 } } }
            }
        }
    });
}

function renderTerritoryElections(data) {
    const el = document.getElementById('territoryElections');
    if (!el) return;

    const elections = data?.elections || [];
    if (elections.length === 0) {
        el.innerHTML = '<div class="text-warmgray-400 text-sm text-center py-8">No recent elections found</div>';
        return;
    }

    el.innerHTML = `
        <table class="w-full text-sm">
            <thead>
                <tr class="text-warmgray-500 text-xs uppercase border-b border-warmgray-100">
                    <th class="text-left py-2 font-semibold">Date</th>
                    <th class="text-left py-2 font-semibold">Employer</th>
                    <th class="text-center py-2 font-semibold">Voters</th>
                    <th class="text-right py-2 font-semibold">Result</th>
                </tr>
            </thead>
            <tbody>
                ${elections.slice(0, 10).map(e => {
                    const won = e.union_won === true;
                    return `
                        <tr class="border-b border-warmgray-50">
                            <td class="py-2 text-warmgray-500">${e.election_date || '--'}</td>
                            <td class="py-2 font-medium text-warmgray-900">${escapeHtml(e.employer_name || '')}</td>
                            <td class="py-2 text-center">${e.eligible_voters || '--'}</td>
                            <td class="py-2 text-right">
                                <span class="badge ${won ? 'bg-green-50 text-green-700' : 'bg-red-50 text-red-700'}">${won ? 'Won' : 'Lost'}</span>
                            </td>
                        </tr>
                    `;
                }).join('')}
            </tbody>
        </table>
    `;
}

function renderTerritoryHotspots(data) {
    const el = document.getElementById('territoryHotspots');
    if (!el) return;

    const violators = data?.results || data?.violators || data?.top_violators || [];
    if (violators.length === 0) {
        el.innerHTML = '<div class="text-warmgray-400 text-sm text-center py-8">No violation data found</div>';
        return;
    }

    el.innerHTML = `
        <table class="w-full text-sm">
            <thead>
                <tr class="text-warmgray-500 text-xs uppercase border-b border-warmgray-100">
                    <th class="text-left py-2 font-semibold">Employer</th>
                    <th class="text-right py-2 font-semibold">Back Wages</th>
                    <th class="text-right py-2 font-semibold">Violations</th>
                </tr>
            </thead>
            <tbody>
                ${violators.slice(0, 10).map(v => `
                    <tr class="border-b border-warmgray-50">
                        <td class="py-2 font-medium text-warmgray-900">${escapeHtml(v.name_normalized || v.trade_name || v.legal_name || '')}</td>
                        <td class="py-2 text-right text-accent-red font-semibold">$${formatNumber(Math.round(v.total_backwages || v.civil_penalties || 0))}</td>
                        <td class="py-2 text-right">${formatNumber(v.total_violations || 0)}</td>
                    </tr>
                `).join('')}
            </tbody>
        </table>
    `;
}

function renderTerritoryIndustry(industryData) {
    const el = document.getElementById('territoryIndustry');
    if (!el) return;

    const industries = industryData?.industry_rates || [];
    if (industries.length === 0) {
        el.innerHTML = '<div class="text-warmgray-400 text-sm text-center py-8">No industry data available</div>';
        return;
    }

    el.innerHTML = '<canvas id="territoryIndustryChart" height="350"></canvas>';
    if (territoryCharts.industry) territoryCharts.industry.destroy();

    const ctx = document.getElementById('territoryIndustryChart').getContext('2d');
    const sorted = [...industries].sort((a, b) => b.union_density_pct - a.union_density_pct);

    territoryCharts.industry = new Chart(ctx, {
        type: 'bar',
        data: {
            labels: sorted.map(i => (i.industry_name || '').replace(/ and /g, ' & ').substring(0, 30)),
            datasets: [{
                label: 'Union Density %',
                data: sorted.map(i => i.union_density_pct),
                backgroundColor: sorted.map(i => i.union_density_pct >= 10 ? 'rgba(196, 30, 58, 0.8)' : i.union_density_pct >= 5 ? 'rgba(196, 30, 58, 0.5)' : 'rgba(196, 30, 58, 0.25)'),
                borderRadius: 4
            }]
        },
        options: {
            indexAxis: 'y',
            responsive: true,
            maintainAspectRatio: false,
            plugins: { legend: { display: false } },
            scales: {
                x: {
                    grid: { display: false },
                    title: { display: true, text: 'Union Density %', font: { size: 10 } }
                },
                y: { ticks: { font: { size: 11 } } }
            }
        }
    });
}

// State center coordinates for territory map
const STATE_CENTERS = {
    'AL': [32.8, -86.8], 'AK': [64.2, -152.5], 'AZ': [34.0, -111.1], 'AR': [34.8, -92.2],
    'CA': [36.8, -119.4], 'CO': [39.1, -105.4], 'CT': [41.6, -72.7], 'DE': [39.0, -75.5],
    'DC': [38.9, -77.0], 'FL': [27.6, -81.5], 'GA': [32.2, -83.7], 'HI': [19.9, -155.6],
    'ID': [44.1, -114.7], 'IL': [40.6, -89.3], 'IN': [40.3, -86.1], 'IA': [42.0, -93.2],
    'KS': [38.5, -98.8], 'KY': [37.8, -84.3], 'LA': [30.5, -91.2], 'ME': [45.3, -69.4],
    'MD': [39.0, -76.6], 'MA': [42.4, -71.4], 'MI': [44.3, -84.5], 'MN': [46.7, -94.7],
    'MS': [32.7, -89.5], 'MO': [38.5, -92.3], 'MT': [46.8, -110.4], 'NE': [41.1, -98.3],
    'NV': [38.8, -116.4], 'NH': [43.2, -71.6], 'NJ': [40.1, -74.4], 'NM': [34.5, -106.0],
    'NY': [43.0, -75.0], 'NC': [35.8, -80.0], 'ND': [47.5, -100.5], 'OH': [40.4, -82.9],
    'OK': [35.0, -97.1], 'OR': [43.8, -120.6], 'PA': [41.2, -77.2], 'PR': [18.2, -66.6],
    'RI': [41.6, -71.5], 'SC': [33.8, -81.2], 'SD': [43.9, -99.9], 'TN': [35.5, -86.6],
    'TX': [31.1, -97.6], 'UT': [39.3, -111.1], 'VT': [44.6, -72.6], 'VA': [37.4, -78.7],
    'WA': [47.7, -120.7], 'WV': [38.6, -80.6], 'WI': [43.8, -88.8], 'WY': [43.1, -107.6]
};

function renderTerritoryMap(targetsData) {
    const container = document.getElementById('territoryMapContainer');
    if (!container) return;

    container.classList.remove('skeleton');
    container.innerHTML = '';
    container.style.height = '350px';

    if (territoryMap) {
        territoryMap.remove();
        territoryMap = null;
    }

    // Determine center & zoom from context
    const stateCenter = STATE_CENTERS[territoryContext.state];
    const center = stateCenter || [39.8283, -98.5795];
    const zoom = stateCenter ? 6 : 4;

    territoryMap = L.map(container).setView(center, zoom);
    L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
        attribution: '&copy; OpenStreetMap'
    }).addTo(territoryMap);

    // Add target markers (for those with coordinates)
    const targets = targetsData?.results || targetsData?.targets || [];
    const markers = [];
    targets.forEach(t => {
        if (!t.latitude || !t.longitude) return;
        const score = t.organizing_score || t.total_score || 0;
        const tier = score >= 30 ? 'TOP' : score >= 25 ? 'HIGH' : 'MEDIUM';
        const color = tier === 'TOP' ? '#16a34a' : tier === 'HIGH' ? '#2563eb' : '#ca8a04';
        const marker = L.circleMarker([t.latitude, t.longitude], {
            radius: 6, fillColor: color, color: '#fff', weight: 2, fillOpacity: 0.8
        });
        marker.bindPopup(`
            <div style="min-width:150px">
                <div style="font-weight:600">${escapeHtml(t.estab_name || t.company_name || '')}</div>
                <div style="color:#666;font-size:12px">${t.site_city || t.city || ''}, ${t.site_state || t.state || ''}</div>
                <div style="margin-top:4px;font-size:13px">Score: <strong>${score}</strong> (${tier})</div>
            </div>
        `);
        markers.push(marker);
        marker.addTo(territoryMap);
    });

    if (markers.length > 0) {
        const group = L.featureGroup(markers);
        territoryMap.fitBounds(group.getBounds().pad(0.1));
    }

    setTimeout(() => territoryMap.invalidateSize(), 200);
}
