// modals.js -- All modal dialog functions

// ==========================================
// MODAL STATE VARIABLES
// ==========================================
let dashboardChart = null;
let currentDashboardAffiliation = null;
let corporateFamilyMap = null;
let corporateFamilyMarkers = null;
let analyticsCharts = {};

function openFindSimilar(employer) {
    selectedItem = employer;
    
    // Populate source info
    document.getElementById('similarSourceName').textContent = employer.employer_name || 'Unknown';
    const naicsLabel = employer.naics_sector_name || `NAICS ${employer.naics?.substring(0,2) || 'N/A'}`;
    const location = [employer.city, employer.state].filter(Boolean).join(', ') || 'Unknown Location';
    const workers = employer.latest_unit_size ? formatNumber(employer.latest_unit_size) + ' workers' : '';
    document.getElementById('similarSourceDetails').textContent = [naicsLabel, location, workers].filter(Boolean).join(' · ');
    document.getElementById('matchIndustryLabel').textContent = naicsLabel;
    
    // Reset to form view
    showFindSimilarForm();
    
    // Show modal
    document.getElementById('findSimilarModal').classList.remove('hidden');
    document.getElementById('findSimilarModal').classList.add('flex');
}

function closeFindSimilar() {
    document.getElementById('findSimilarModal').classList.add('hidden');
    document.getElementById('findSimilarModal').classList.remove('flex');
}

// ==========================================
// NATIONAL UNION DASHBOARD
// ==========================================

async function openNationalDashboard(affAbbr) {
    currentDashboardAffiliation = affAbbr;
    document.getElementById('nationalDashboardModal').classList.remove('hidden');
    document.getElementById('nationalDashboardModal').classList.add('flex');
    document.body.classList.add('modal-open');
    document.getElementById('dashboardTitle').textContent = affAbbr;
    document.getElementById('dashboardLoading').classList.remove('hidden');
    document.getElementById('dashboardContent').classList.add('hidden');
    
    try {
        const response = await fetch(`${API_BASE}/unions/national/${encodeURIComponent(affAbbr)}`);
        if (!response.ok) throw new Error('Failed to load');
        
        const data = await response.json();
        renderNationalDashboard(data);
    } catch (e) {
        console.error('Failed to load national dashboard:', e);
        document.getElementById('dashboardLoading').innerHTML = `
            <div class="text-red-600">Failed to load dashboard data</div>
        `;
    }
}

function closeNationalDashboard() {
    document.getElementById('nationalDashboardModal').classList.add('hidden');
    document.getElementById('nationalDashboardModal').classList.remove('flex');
    document.body.classList.remove('modal-open');

    // Destroy chart
    if (dashboardChart) {
        dashboardChart.destroy();
        dashboardChart = null;
    }
}

function renderNationalDashboard(data) {
    document.getElementById('dashboardLoading').classList.add('hidden');
    document.getElementById('dashboardContent').classList.remove('hidden');
    
    const s = data.summary;
    
    // Summary cards
    document.getElementById('dashLocalCount').textContent = formatNumber(s.local_count || 0);
    document.getElementById('dashMemberCount').textContent = formatNumber(s.total_members || 0);
    document.getElementById('dashEmployerCount').textContent = formatNumber(s.total_employers || 0);
    document.getElementById('dashWorkerCount').textContent = formatNumber(s.covered_workers || 0);
    document.getElementById('dashStateCount').textContent = (s.states || []).length;
    
    // Trends
    const trends = data.trends || {};
    if (trends.member_change_pct !== undefined || trends.asset_change_pct !== undefined) {
        document.getElementById('dashTrends').classList.remove('hidden');
        
        if (trends.member_change_pct !== undefined) {
            const el = document.getElementById('dashMemberTrend');
            const isPos = trends.member_change_pct >= 0;
            el.textContent = `${isPos ? '↑' : '↓'} ${Math.abs(trends.member_change_pct)}% members (${trends.years_of_data}yr)`;
            el.className = `px-3 py-1 rounded-full text-sm font-medium ${isPos ? 'bg-green-100 text-green-700' : 'bg-red-100 text-red-700'}`;
        }
        
        if (trends.asset_change_pct !== undefined) {
            const el = document.getElementById('dashAssetTrend');
            const isPos = trends.asset_change_pct >= 0;
            el.textContent = `${isPos ? '↑' : '↓'} ${Math.abs(trends.asset_change_pct)}% assets`;
            el.className = `px-3 py-1 rounded-full text-sm font-medium ${isPos ? 'bg-green-100 text-green-700' : 'bg-red-100 text-red-700'}`;
        }
    } else {
        document.getElementById('dashTrends').classList.add('hidden');
    }
    
    // Sector badges
    const sectors = s.sectors || [];
    document.getElementById('dashSectors').innerHTML = sectors.map(sector => {
        const sectorClass = getSectorBadgeClass(sector);
        return `<span class="badge ${sectorClass}">${formatSectorName(sector)}</span>`;
    }).join('');
    
    // Financial trends chart
    renderDashboardChart(data.financial_trends || []);
    
    // Top locals
    const locals = data.top_locals || [];
    document.getElementById('dashTopLocals').innerHTML = locals.length > 0 
        ? locals.map(local => `
            <div class="flex justify-between items-center p-2 bg-warmgray-50 rounded hover:bg-warmgray-100 cursor-pointer"
                 onclick="selectLocalFromDashboard('${local.f_num}')">
                <div>
                    <div class="font-medium text-sm text-warmgray-900">
                        ${local.local_number ? `Local ${local.local_number}` : escapeHtml(local.union_name || 'Unknown')}
                        ${local.desig_name ? `<span class="text-warmgray-500">${escapeHtml(local.desig_name)}</span>` : ''}
                    </div>
                    <div class="text-xs text-warmgray-500">${escapeHtml(local.city || '')}, ${local.state || ''}</div>
                </div>
                <div class="text-right">
                    <div class="font-semibold text-warmgray-900">${formatNumber(local.members || 0)}</div>
                    <div class="text-xs text-warmgray-400">${formatNumber(local.f7_employer_count || 0)} employers</div>
                </div>
            </div>
        `).join('')
        : '<div class="text-warmgray-400 text-sm">No local data available</div>';
    
    // Geographic distribution - use by_state (filtered to current affiliation)
    const geo = data.by_state || [];
    const totalMembers = geo.reduce((sum, g) => sum + (g.total_members || 0), 0);
    document.getElementById('dashGeoDistribution').innerHTML = geo.length > 0
        ? geo.slice(0, 15).map(g => {
            const pct = totalMembers > 0 ? Math.round((g.total_members || 0) / totalMembers * 100) : 0;
            return `
                <div class="flex items-center gap-3">
                    <div class="w-8 text-xs font-medium text-warmgray-700">${g.state}</div>
                    <div class="flex-1 bg-warmgray-200 rounded-full h-2">
                        <div class="bg-accent-red rounded-full h-2" style="width: ${pct}%"></div>
                    </div>
                    <div class="w-24 text-right text-xs">
                        <span class="text-warmgray-700">${formatNumber(g.total_members || 0)}</span>
                        <span class="text-warmgray-400">(${g.local_count})</span>
                    </div>
                </div>
            `;
        }).join('')
        : '<div class="text-warmgray-400 text-sm">No geographic data available</div>';
    
    // Industries
    const industries = data.industry_distribution || [];
    document.getElementById('dashIndustries').innerHTML = industries.length > 0
        ? industries.map(ind => `
            <span class="px-3 py-1 bg-warmgray-100 text-warmgray-700 text-sm rounded-full">
                ${escapeHtml(ind.naics_sector_name || 'NAICS ' + ind.naics_2digit)}
                <span class="text-warmgray-400">(${formatNumber(ind.total_workers || 0)})</span>
            </span>
        `).join('')
        : '<div class="text-warmgray-400 text-sm">No industry data available</div>';
    
    // Top employers
    const employers = data.top_employers || [];
    document.getElementById('dashTopEmployers').innerHTML = employers.length > 0
        ? employers.slice(0, 10).map(emp => `
            <div class="flex justify-between items-center p-2 bg-warmgray-50 rounded hover:bg-warmgray-100 cursor-pointer"
                 onclick="selectEmployerFromDashboard('${emp.employer_id}')">
                <div>
                    <div class="font-medium text-sm text-warmgray-900">${escapeHtml(emp.employer_name)}</div>
                    <div class="text-xs text-warmgray-500">
                        ${escapeHtml(emp.city || '')}, ${emp.state || ''}
                        ${emp.local_number ? ` · Local ${emp.local_number}` : ''}
                    </div>
                </div>
                <div class="text-right">
                    <div class="font-semibold text-warmgray-900">${formatNumber(emp.latest_unit_size || 0)}</div>
                    <div class="text-xs text-warmgray-400">workers</div>
                </div>
            </div>
        `).join('')
        : '<div class="text-warmgray-400 text-sm">No employer data available</div>';
}

function renderDashboardChart(financials) {
    // Destroy existing chart
    if (dashboardChart) {
        dashboardChart.destroy();
        dashboardChart = null;
    }
    
    if (!financials || financials.length < 2) {
        document.getElementById('dashTrendsChart').parentElement.innerHTML = `
            <h3 class="text-sm font-semibold text-warmgray-700 uppercase tracking-wide mb-3">Membership Trend</h3>
            <div class="text-warmgray-400 text-sm py-8 text-center">Insufficient historical data</div>
        `;
        return;
    }
    
    // Reverse for chronological order
    const sorted = [...financials].reverse();
    const labels = sorted.map(f => f.yr_covered);
    const memberData = sorted.map(f => (f.total_members || 0) / 1000); // In thousands
    const assetData = sorted.map(f => (f.total_assets || 0) / 1000000); // In millions
    
    const ctx = document.getElementById('dashTrendsChart').getContext('2d');
    
    dashboardChart = new Chart(ctx, {
        type: 'line',
        data: {
            labels: labels,
            datasets: [
                {
                    label: 'Members (K)',
                    data: memberData,
                    borderColor: '#8B4513',
                    backgroundColor: 'rgba(139, 69, 19, 0.1)',
                    yAxisID: 'y',
                    tension: 0.3,
                    fill: true
                },
                {
                    label: 'Assets ($M)',
                    data: assetData,
                    borderColor: '#6B7280',
                    backgroundColor: 'transparent',
                    yAxisID: 'y1',
                    tension: 0.3,
                    borderDash: [5, 5]
                }
            ]
        },
        options: {
            responsive: true,
            maintainAspectRatio: true,
            interaction: {
                mode: 'index',
                intersect: false,
            },
            plugins: {
                legend: {
                    position: 'top',
                    labels: { boxWidth: 12, font: { size: 11 } }
                }
            },
            scales: {
                x: { grid: { display: false } },
                y: {
                    type: 'linear',
                    display: true,
                    position: 'left',
                    title: { display: true, text: 'Members (K)', font: { size: 10 } }
                },
                y1: {
                    type: 'linear',
                    display: true,
                    position: 'right',
                    title: { display: true, text: 'Assets ($M)', font: { size: 10 } },
                    grid: { drawOnChartArea: false }
                }
            }
        }
    });
}

// Track current affiliation for linking

function selectLocalFromDashboard(fNum) {
    closeNationalDashboard();
    setSearchMode('unions');
    // Search for this specific union
    document.getElementById('mainSearch').value = fNum;
    executeSearch();
}

async function selectEmployerFromDashboard(employerId) {
    closeNationalDashboard();
    setSearchMode('employers');
    // Fetch the employer and add to results before selecting
    try {
        const response = await fetch(`${API_BASE}/employers/${employerId}`);
        if (response.ok) {
            const data = await response.json();
            if (data.employer) {
                currentResults = [data.employer];
                selectItem(employerId);
            }
        }
    } catch (e) {
        console.error('Failed to load employer:', e);
    }
}

function searchLocalsForCurrentAffiliation() {
    if (!currentDashboardAffiliation) return;
    searchLocalsForAffiliation(currentDashboardAffiliation);
}

function searchLocalsForAffiliation(affAbbr) {
    closeNationalDashboard();
    setSearchMode('unions');
    // Clear main search, set affiliation filter via selectedIndustry
    document.getElementById('mainSearch').value = '';
    // Set the industry filter to be a union affiliation
    selectedIndustry = { type: 'union', abbr: affAbbr, name: affAbbr };
    showSelectedIndustryTag();
    executeSearch();
}

// ==========================================
// NATIONAL UNIONS BROWSER
// ==========================================
async function openNationalUnionsBrowser() {
    document.getElementById('nationalBrowserModal').classList.remove('hidden');
    document.getElementById('nationalBrowserModal').classList.add('flex');
    document.getElementById('browserLoading').classList.remove('hidden');
    document.getElementById('browserContent').classList.add('hidden');
    
    try {
        const response = await fetch(`${API_BASE}/unions/national?limit=100`);
        if (!response.ok) throw new Error('Failed to load');
        
        const data = await response.json();
        renderNationalUnionsList(data.national_unions || []);
    } catch (e) {
        console.error('Failed to load national unions:', e);
        document.getElementById('browserLoading').innerHTML = `
            <div class="text-red-600">Failed to load national unions</div>
        `;
    }
}

function closeNationalBrowser() {
    document.getElementById('nationalBrowserModal').classList.add('hidden');
    document.getElementById('nationalBrowserModal').classList.remove('flex');
}

function renderNationalUnionsList(unions) {
    document.getElementById('browserLoading').classList.add('hidden');
    document.getElementById('browserContent').classList.remove('hidden');
    
    const container = document.getElementById('browserList');
    
    if (unions.length === 0) {
        container.innerHTML = '<div class="col-span-2 text-center text-warmgray-400 py-8">No national unions found</div>';
        return;
    }
    
    container.innerHTML = unions.map(u => `
        <div class="bg-warmgray-50 rounded-lg p-4 hover:bg-warmgray-100 cursor-pointer transition-colors"
             onclick="selectNationalUnion('${escapeHtml(u.aff_abbr)}')">
            <div class="flex justify-between items-start mb-2">
                <div class="font-bold text-lg text-warmgray-900">${escapeHtml(u.aff_abbr)}</div>
                <div class="text-xs text-warmgray-400">${u.local_count} locals</div>
            </div>
            <div class="grid grid-cols-2 gap-2 text-sm">
                <div>
                    <span class="text-warmgray-500">Members:</span>
                    <span class="font-semibold text-accent-red">${formatNumber(u.total_members || 0)}</span>
                </div>
                <div>
                    <span class="text-warmgray-500">Employers:</span>
                    <span class="font-semibold">${formatNumber(u.employer_count || 0)}</span>
                </div>
            </div>
            <div class="text-xs text-warmgray-400 mt-2">
                ${u.state_count || 0} states · ${formatNumber(u.covered_workers || 0)} workers covered
            </div>
        </div>
    `).join('');
}

function selectNationalUnion(affAbbr) {
    closeNationalBrowser();
    openNationalDashboard(affAbbr);
}

function showFindSimilarForm() {
    document.getElementById('findSimilarForm').classList.remove('hidden');
    document.getElementById('findSimilarResults').classList.add('hidden');
    document.getElementById('findSimilarLoading').classList.add('hidden');
}

function showFindSimilarLoading() {
    document.getElementById('findSimilarForm').classList.add('hidden');
    document.getElementById('findSimilarResults').classList.add('hidden');
    document.getElementById('findSimilarLoading').classList.remove('hidden');
}

function showFindSimilarResults() {
    document.getElementById('findSimilarForm').classList.add('hidden');
    document.getElementById('findSimilarResults').classList.remove('hidden');
    document.getElementById('findSimilarLoading').classList.add('hidden');
}

async function executeFindSimilar() {
    if (!selectedItem || !selectedItem.employer_id) {
        alert('No employer selected');
        return;
    }
    
    showFindSimilarLoading();
    
    const geoLevel = document.getElementById('similarGeoLevel').value;
    const radiusMiles = document.getElementById('similarRadius').value || 50;
    const includeUnion = !document.getElementById('matchNonUnion').checked;
    
    const params = new URLSearchParams({
        geo_level: geoLevel,
        include_union: includeUnion,
        limit: 50
    });
    
    if (geoLevel === 'radius') {
        params.append('radius_miles', radiusMiles);
    }
    
    try {
        const response = await fetch(`${API_BASE}/employers/${selectedItem.employer_id}/similar?${params}`);
        
        if (!response.ok) {
            throw new Error(`HTTP ${response.status}`);
        }
        
        const data = await response.json();
        displaySimilarResults(data);
    } catch (e) {
        console.error('Find Similar failed:', e);
        showFindSimilarForm();
        alert('Search failed. Make sure the API is running and OSHA data is loaded.');
    }
}

function displaySimilarResults(data) {
    const listEl = document.getElementById('similarResultsList');
    const results = data.similar_employers || [];
    
    // Update header
    document.getElementById('similarResultsCount').textContent = 
        `${results.length} potential target${results.length !== 1 ? 's' : ''} found`;
    document.getElementById('similarResultsSource').textContent = 
        data.data_source === 'osha' ? 'from OSHA enforcement data' : 'from F-7 employer data';
    
    if (results.length === 0) {
        listEl.innerHTML = `
            <div class="text-center py-12 text-warmgray-500">
                <svg class="w-12 h-12 mx-auto mb-4 text-warmgray-300" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" 
                        d="M9.172 16.172a4 4 0 015.656 0M9 10h.01M15 10h.01M12 20a8 8 0 100-16 8 8 0 000 16z"/>
                </svg>
                <p class="font-medium">No similar employers found</p>
                <p class="text-sm mt-1">Try expanding your geography or adjusting filters</p>
            </div>
        `;
    } else {
        listEl.innerHTML = results.map(emp => renderSimilarCard(emp, data.data_source)).join('');
    }
    
    showFindSimilarResults();
}

function renderSimilarCard(emp, dataSource) {
    const riskColors = {
        'HIGH': 'bg-red-100 text-red-800 border-red-200',
        'MEDIUM': 'bg-yellow-100 text-yellow-800 border-yellow-200',
        'LOW': 'bg-green-100 text-green-800 border-green-200',
        'UNKNOWN': 'bg-warmgray-100 text-warmgray-600 border-warmgray-200'
    };
    
    const riskClass = riskColors[emp.risk_level] || riskColors['UNKNOWN'];
    const location = [emp.city, emp.state].filter(Boolean).join(', ');
    const employees = emp.employee_count ? formatNumber(emp.employee_count) + ' employees' : '';
    
    // OSHA-specific fields
    const violations = emp.total_violations || 0;
    const serious = emp.serious_violations || 0;
    const willful = emp.willful_violations || 0;
    const penalty = emp.total_penalty ? '$' + formatNumber(emp.total_penalty) : '';
    
    let violationBadges = '';
    if (dataSource === 'osha' && violations > 0) {
        violationBadges = `
            <div class="flex gap-2 mt-2 flex-wrap">
                <span class="text-xs px-2 py-0.5 rounded bg-warmgray-100 text-warmgray-700">
                    ${violations} violation${violations !== 1 ? 's' : ''}
                </span>
                ${serious > 0 ? `<span class="text-xs px-2 py-0.5 rounded bg-orange-100 text-orange-700">${serious} serious</span>` : ''}
                ${willful > 0 ? `<span class="text-xs px-2 py-0.5 rounded bg-red-100 text-red-700">${willful} willful</span>` : ''}
                ${penalty ? `<span class="text-xs px-2 py-0.5 rounded bg-warmgray-100 text-warmgray-700">${penalty} penalties</span>` : ''}
            </div>
        `;
    }
    
    const nlrbBadge = emp.has_nlrb_history ? 
        '<span class="text-xs px-2 py-0.5 rounded bg-blue-100 text-blue-700">NLRB history</span>' : '';
    
    return `
        <div class="border border-warmgray-200 rounded-lg p-4 mb-3 hover:border-warmgray-400 transition-colors">
            <div class="flex justify-between items-start">
                <div class="flex-1">
                    <h4 class="font-semibold text-warmgray-900">${escapeHtml(emp.employer_name)}</h4>
                    <p class="text-sm text-warmgray-500">${escapeHtml(location)} ${employees ? '· ' + employees : ''}</p>
                    ${violationBadges}
                    ${nlrbBadge ? `<div class="mt-2">${nlrbBadge}</div>` : ''}
                </div>
                <div class="flex flex-col items-end gap-2">
                    <span class="text-xs px-2 py-1 rounded border ${riskClass} font-medium">
                        ${emp.risk_level || 'N/A'} risk
                    </span>
                    ${emp.naics ? `<span class="text-xs text-warmgray-400">NAICS ${emp.naics}</span>` : ''}
                </div>
            </div>
        </div>
    `;
}


// ==========================================
// CORPORATE FAMILY
// ==========================================

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


// ==========================================
// ANALYTICS DASHBOARD
// ==========================================
let dashboardCharts = {};

async function openAnalyticsDashboard() {
    document.getElementById('analyticsDashboardModal').classList.remove('hidden');
    document.getElementById('analyticsDashboardModal').classList.add('flex');
    document.body.classList.add('modal-open');
    document.getElementById('analyticsDashboardLoading').classList.remove('hidden');
    document.getElementById('analyticsDashboardContent').classList.add('hidden');

    try {
        // Load data using existing endpoints
        const [summaryData, nationalTrends, electionTrends, recentElections] = await Promise.all([
            fetch(`${API_BASE}/summary`).then(r => r.json()),
            fetch(`${API_BASE}/trends/national?start_year=2010&end_year=2024`).then(r => r.json()),
            fetch(`${API_BASE}/trends/elections`).then(r => r.json()),
            fetch(`${API_BASE}/nlrb/elections/search?limit=10`).then(r => r.json())
        ]);

        // Transform data to expected format
        const summary = {
            total_unions: summaryData.unions?.total_unions || 0,
            total_members: summaryData.unions?.total_members || 0,
            total_employers: summaryData.employers?.total_employers || 0,
            covered_workers: summaryData.employers?.covered_workers || 0,
            osha_establishments: 0,
            nlrb_cases_1yr: summaryData.nlrb?.elections?.total_elections || 0,
            nlrb_wins_1yr: summaryData.nlrb?.elections?.union_wins || 0,
            nlrb_losses_1yr: (summaryData.nlrb?.elections?.total_elections || 0) - (summaryData.nlrb?.elections?.union_wins || 0),
            top_affiliations: [],
            top_industries: []
        };

        const trends = {
            membership_by_year: (nationalTrends.trends || []).map(t => ({
                year: t.year,
                total_members: t.total_members_raw || t.total_members
            })),
            nlrb_by_year: (electionTrends.election_trends || []).map(e => ({
                year: e.year,
                wins: e.union_wins,
                losses: e.union_losses
            })),
            f7_filings_by_year: [],
            osha_by_year: []
        };

        const nlrbRecent = {
            recent_elections: (recentElections.elections || []).slice(0, 10)
        };

        const growth = {};
        const geographic = { unions_by_state: [] };

        renderDashboard(summary, trends, nlrbRecent, growth, geographic);
    } catch (e) {
        console.error('Dashboard load failed:', e);
        document.getElementById('analyticsDashboardLoading').innerHTML = `
            <div class="text-red-600">Failed to load dashboard. Check that the API is running.</div>
        `;
    }
}

function closeAnalyticsDashboard() {
    document.getElementById('analyticsDashboardModal').classList.add('hidden');
    document.getElementById('analyticsDashboardModal').classList.remove('flex');
    document.body.classList.remove('modal-open');

    // Destroy charts to prevent memory leaks
    Object.values(dashboardCharts).forEach(chart => {
        if (chart) chart.destroy();
    });
    dashboardCharts = {};
}

function renderDashboard(summary, trends, nlrbRecent, growth, geographic) {
    // Hide loading, show content
    document.getElementById('analyticsDashboardLoading').classList.add('hidden');
    document.getElementById('analyticsDashboardContent').classList.remove('hidden');
    
    // Summary cards
    document.getElementById('dashUnions').textContent = formatNumber(summary.total_unions || 0);
    document.getElementById('dashMembers').textContent = formatNumber(summary.total_members || 0);
    document.getElementById('dashEmployers').textContent = formatNumber(summary.total_employers || 0);
    document.getElementById('dashWorkers').textContent = formatNumber(summary.covered_workers || 0);
    document.getElementById('dashOsha').textContent = formatNumber(summary.osha_establishments || 0);
    document.getElementById('dashNlrb').textContent = formatNumber(summary.nlrb_cases_1yr || 0);
    
    const wins = summary.nlrb_wins_1yr || 0;
    const losses = summary.nlrb_losses_1yr || 0;
    if (wins || losses) {
        document.getElementById('dashNlrbWins').textContent = `${wins} wins / ${losses} losses`;
    }
    
    // Render charts
    renderMembershipChart(trends.membership_by_year || []);
    renderNlrbChart(trends.nlrb_by_year || []);
    renderF7Chart(trends.f7_filings_by_year || []);
    renderOshaChart(trends.osha_by_year || []);
    
    // Render tables
    renderRecentNlrb(nlrbRecent.recent_elections || []);
    renderGrowthTables(growth);
    renderTopStates(geographic.unions_by_state || []);
    renderTopAffiliations(summary.top_affiliations || []);
    renderTopIndustries(summary.top_industries || []);
}

function renderMembershipChart(data) {
    const ctx = document.getElementById('membershipChart').getContext('2d');
    if (dashboardCharts.membership) dashboardCharts.membership.destroy();
    
    dashboardCharts.membership = new Chart(ctx, {
        type: 'line',
        data: {
            labels: data.map(d => d.year),
            datasets: [{
                label: 'Total Members',
                data: data.map(d => (d.total_members || 0) / 1000000),
                borderColor: '#c73e1d',
                backgroundColor: 'rgba(199, 62, 29, 0.1)',
                fill: true,
                tension: 0.3
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: { display: false },
                tooltip: {
                    callbacks: {
                        label: ctx => `${ctx.parsed.y.toFixed(1)}M members`
                    }
                }
            },
            scales: {
                y: {
                    beginAtZero: false,
                    title: { display: true, text: 'Members (millions)' }
                }
            }
        }
    });
}

function renderNlrbChart(data) {
    const ctx = document.getElementById('nlrbChart').getContext('2d');
    if (dashboardCharts.nlrb) dashboardCharts.nlrb.destroy();
    
    dashboardCharts.nlrb = new Chart(ctx, {
        type: 'bar',
        data: {
            labels: data.map(d => d.year),
            datasets: [{
                label: 'Union Wins',
                data: data.map(d => d.union_wins || 0),
                backgroundColor: '#22c55e'
            }, {
                label: 'Union Losses',
                data: data.map(d => d.union_losses || 0),
                backgroundColor: '#ef4444'
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: { position: 'top' }
            },
            scales: {
                x: { stacked: true },
                y: { stacked: true, beginAtZero: true }
            }
        }
    });
}

function renderF7Chart(data) {
    const ctx = document.getElementById('f7Chart').getContext('2d');
    if (dashboardCharts.f7) dashboardCharts.f7.destroy();
    
    dashboardCharts.f7 = new Chart(ctx, {
        type: 'line',
        data: {
            labels: data.map(d => d.year),
            datasets: [{
                label: 'Filings',
                data: data.map(d => d.filings || 0),
                borderColor: '#3b82f6',
                backgroundColor: 'rgba(59, 130, 246, 0.1)',
                fill: true,
                tension: 0.3,
                yAxisID: 'y'
            }, {
                label: 'Workers Covered',
                data: data.map(d => (d.workers_covered || 0) / 1000),
                borderColor: '#8b5cf6',
                borderDash: [5, 5],
                tension: 0.3,
                yAxisID: 'y1'
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: { position: 'top' }
            },
            scales: {
                y: {
                    type: 'linear',
                    position: 'left',
                    title: { display: true, text: 'Filings' }
                },
                y1: {
                    type: 'linear',
                    position: 'right',
                    title: { display: true, text: 'Workers (thousands)' },
                    grid: { drawOnChartArea: false }
                }
            }
        }
    });
}

function renderOshaChart(data) {
    const ctx = document.getElementById('oshaChart').getContext('2d');
    if (dashboardCharts.osha) dashboardCharts.osha.destroy();
    
    dashboardCharts.osha = new Chart(ctx, {
        type: 'bar',
        data: {
            labels: data.map(d => d.year),
            datasets: [{
                label: 'Total Violations',
                data: data.map(d => d.violations || 0),
                backgroundColor: '#f59e0b'
            }, {
                label: 'Serious',
                data: data.map(d => d.serious_violations || 0),
                backgroundColor: '#dc2626'
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: { position: 'top' }
            },
            scales: {
                y: { beginAtZero: true }
            }
        }
    });
}

function renderRecentNlrb(elections) {
    const el = document.getElementById('recentNlrb');
    if (!elections.length) {
        el.innerHTML = '<div class="text-warmgray-400 text-sm">No recent elections</div>';
        return;
    }
    
    el.innerHTML = elections.slice(0, 15).map(e => {
        const statusClass = (e.status || '').toLowerCase().includes('certif') || (e.status || '').toLowerCase().includes('won')
            ? 'text-green-600' 
            : (e.status || '').toLowerCase().includes('dismiss') || (e.status || '').toLowerCase().includes('withdraw')
                ? 'text-red-600'
                : 'text-warmgray-500';
        return `
            <div class="text-sm border-l-2 border-warmgray-200 pl-2 py-1">
                <div class="font-medium text-warmgray-900 truncate">${escapeHtml(e.case_name || 'Unknown')}</div>
                <div class="text-xs text-warmgray-500">${e.city || ''}, ${e.state || ''} · ${e.date_filed || ''}</div>
                <div class="text-xs ${statusClass}">${escapeHtml(e.status || 'Unknown')}</div>
            </div>
        `;
    }).join('');
}

function renderGrowthTables(growth) {
    const growingEl = document.getElementById('growingUnions');
    const decliningEl = document.getElementById('decliningUnions');
    
    if (growth.growing && growth.growing.length > 0) {
        growingEl.innerHTML = growth.growing.map(u => `
            <div class="flex justify-between items-center text-sm py-1 border-b border-warmgray-100">
                <span class="font-medium">${escapeHtml(u.affiliation)}</span>
                <span class="text-green-600 font-semibold">+${u.pct_change}%</span>
            </div>
        `).join('');
    } else {
        growingEl.innerHTML = '<div class="text-warmgray-400 text-sm">No growth data available</div>';
    }
    
    if (growth.declining && growth.declining.length > 0) {
        decliningEl.innerHTML = growth.declining.map(u => `
            <div class="flex justify-between items-center text-sm py-1 border-b border-warmgray-100">
                <span class="font-medium">${escapeHtml(u.affiliation)}</span>
                <span class="text-red-600 font-semibold">${u.pct_change}%</span>
            </div>
        `).join('');
    } else {
        decliningEl.innerHTML = '<div class="text-warmgray-400 text-sm">No decline data available</div>';
    }
}

function renderTopStates(states) {
    const el = document.getElementById('topStates');
    const maxMembers = Math.max(...states.map(s => s.total_members || 0));
    
    el.innerHTML = states.slice(0, 15).map(s => {
        const pct = maxMembers > 0 ? ((s.total_members || 0) / maxMembers) * 100 : 0;
        return `
            <div class="text-sm">
                <div class="flex justify-between mb-1">
                    <span class="font-medium">${s.state}</span>
                    <span class="text-warmgray-500">${formatNumber(s.total_members || 0)}</span>
                </div>
                <div class="h-1.5 bg-warmgray-200 rounded-full">
                    <div class="h-full bg-accent-red rounded-full" style="width: ${pct}%"></div>
                </div>
            </div>
        `;
    }).join('');
}

function renderTopAffiliations(affiliations) {
    const el = document.getElementById('topAffiliations');
    
    el.innerHTML = affiliations.map(a => `
        <div class="flex justify-between items-center text-sm py-1 border-b border-warmgray-100 cursor-pointer hover:bg-warmgray-50"
             onclick="closeAnalyticsDashboard(); openNationalDashboard('${escapeHtml(a.aff_abbr)}')">
            <div>
                <span class="font-semibold text-warmgray-900">${escapeHtml(a.aff_abbr)}</span>
                <span class="text-warmgray-400 ml-2">${formatNumber(a.locals)} locals</span>
            </div>
            <span class="text-accent-red font-medium">${formatNumber(a.members || 0)}</span>
        </div>
    `).join('');
}

function renderTopIndustries(industries) {
    const el = document.getElementById('topIndustries');
    
    el.innerHTML = industries.map(i => `
        <div class="flex justify-between items-center text-sm py-1 border-b border-warmgray-100">
            <span class="truncate flex-1 mr-2">${escapeHtml(i.sector_name || 'Unknown')}</span>
            <span class="text-warmgray-500 whitespace-nowrap">${formatNumber(i.workers || 0)} workers</span>
        </div>
    `).join('');
}

// ==========================================
// COMPARISON VIEW
// ==========================================
function openComparison() {
    document.getElementById('comparisonModal').classList.remove('hidden');
    document.getElementById('comparisonModal').classList.add('flex');
    renderComparison();
}

function closeComparison() {
    document.getElementById('comparisonModal').classList.add('hidden');
    document.getElementById('comparisonModal').classList.remove('flex');
}

function addToComparison(item) {
    // Find first empty slot
    if (!comparisonItems[0]) {
        comparisonItems[0] = item;
    } else if (!comparisonItems[1]) {
        comparisonItems[1] = item;
    } else {
        // Both full - replace second
        comparisonItems[1] = item;
    }
    
    updateComparisonBadge();
    renderComparison();
    
    // Auto-open if we have 2 items
    if (comparisonItems[0] && comparisonItems[1]) {
        openComparison();
    }
}

function removeFromComparison(index) {
    comparisonItems[index] = null;
    updateComparisonBadge();
    renderComparison();
}

function clearComparison() {
    comparisonItems = [null, null];
    updateComparisonBadge();
    renderComparison();
}

function updateComparisonBadge() {
    const count = comparisonItems.filter(Boolean).length;
    const badge = document.getElementById('comparisonBadge');
    if (badge) {
        badge.textContent = count;
        badge.classList.toggle('hidden', count === 0);
    }
}

function renderComparison() {
    const subtitle = currentMode === 'employers' ? 'Employer comparison' : 'Union comparison';
    document.getElementById('comparisonSubtitle').textContent = subtitle;
    
    // Render left
    document.getElementById('compareLeft').innerHTML = comparisonItems[0] 
        ? renderComparisonCard(comparisonItems[0], 0)
        : '<div class="text-center text-warmgray-400 py-8"><p>Select first item to compare</p></div>';
    
    // Render right
    document.getElementById('compareRight').innerHTML = comparisonItems[1]
        ? renderComparisonCard(comparisonItems[1], 1)
        : '<div class="text-center text-warmgray-400 py-8"><p>Select second item to compare</p></div>';
}

function renderComparisonCard(item, index) {
    if (currentMode === 'employers') {
        return `
            <div class="relative">
                <button onclick="removeFromComparison(${index})" 
                    class="absolute top-0 right-0 p-1 text-warmgray-400 hover:text-red-500">
                    <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12"/>
                    </svg>
                </button>
                <h3 class="font-bold text-lg text-warmgray-900 pr-6">${escapeHtml(item.employer_name)}</h3>
                <p class="text-sm text-warmgray-500 mb-4">${escapeHtml(item.city || '')}, ${item.state || ''}</p>
                
                <div class="space-y-3">
                    <div class="flex justify-between py-2 border-b border-warmgray-100">
                        <span class="text-warmgray-500">Workers</span>
                        <span class="font-semibold">${formatNumber(item.latest_unit_size || 0)}</span>
                    </div>
                    <div class="flex justify-between py-2 border-b border-warmgray-100">
                        <span class="text-warmgray-500">Industry</span>
                        <span class="font-medium text-sm">${escapeHtml(item.naics_sector_name || 'N/A')}</span>
                    </div>
                    <div class="flex justify-between py-2 border-b border-warmgray-100">
                        <span class="text-warmgray-500">NAICS</span>
                        <span class="font-medium">${item.naics || 'N/A'}</span>
                    </div>
                    <div class="flex justify-between py-2 border-b border-warmgray-100">
                        <span class="text-warmgray-500">Union</span>
                        <span class="font-medium text-sm">${escapeHtml(item.latest_union_name || 'N/A')}</span>
                    </div>
                    <div class="flex justify-between py-2">
                        <span class="text-warmgray-500">Latest Notice</span>
                        <span class="font-medium">${item.latest_notice_date || 'N/A'}</span>
                    </div>
                </div>
            </div>
        `;
    } else {
        return `
            <div class="relative">
                <button onclick="removeFromComparison(${index})" 
                    class="absolute top-0 right-0 p-1 text-warmgray-400 hover:text-red-500">
                    <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12"/>
                    </svg>
                </button>
                <h3 class="font-bold text-lg text-warmgray-900 pr-6">${escapeHtml(item.union_name)}</h3>
                <p class="text-sm text-warmgray-500 mb-1">${item.local_number ? `Local ${item.local_number}` : ''}</p>
                <p class="text-sm text-warmgray-500 mb-4">${escapeHtml(item.city || '')}, ${item.state || ''}</p>
                
                <div class="space-y-3">
                    <div class="flex justify-between py-2 border-b border-warmgray-100">
                        <span class="text-warmgray-500">Members</span>
                        <span class="font-semibold text-accent-red">${formatNumber(item.members || 0)}</span>
                    </div>
                    <div class="flex justify-between py-2 border-b border-warmgray-100">
                        <span class="text-warmgray-500">Affiliation</span>
                        <span class="font-medium">${item.aff_abbr || 'Independent'}</span>
                    </div>
                    <div class="flex justify-between py-2 border-b border-warmgray-100">
                        <span class="text-warmgray-500">Sector</span>
                        <span class="font-medium">${formatSectorName(item.sector)}</span>
                    </div>
                    <div class="flex justify-between py-2 border-b border-warmgray-100">
                        <span class="text-warmgray-500">Employers</span>
                        <span class="font-medium">${formatNumber(item.f7_employer_count || 0)}</span>
                    </div>
                    <div class="flex justify-between py-2">
                        <span class="text-warmgray-500">Workers Covered</span>
                        <span class="font-medium">${formatNumber(item.f7_total_workers || 0)}</span>
                    </div>
                </div>
            </div>
        `;
    }
}

function isInComparison(itemId) {
    return comparisonItems.some(item => {
        if (!item) return false;
        const id = currentMode === 'employers' ? item.employer_id : item.f_num;
        return String(id) === String(itemId);
    });
}

// ==========================================
// SAVED SEARCHES
// ==========================================
const SAVED_SEARCHES_KEY = 'laborPlatform_savedSearches';

function toggleSavedSearches() {
    const dropdown = document.getElementById('savedSearchesDropdown');
    const isHidden = dropdown.classList.contains('hidden');
    
    // Close dropdown when clicking outside
    if (isHidden) {
        dropdown.classList.remove('hidden');
        renderSavedSearches();
        setTimeout(() => {
            document.addEventListener('click', closeSavedSearchesOnClickOutside);
        }, 0);
    } else {
        dropdown.classList.add('hidden');
        document.removeEventListener('click', closeSavedSearchesOnClickOutside);
    }
}

function closeSavedSearchesOnClickOutside(e) {
    const dropdown = document.getElementById('savedSearchesDropdown');
    if (!dropdown.contains(e.target) && !e.target.closest('[onclick*="toggleSavedSearches"]')) {
        dropdown.classList.add('hidden');
        document.removeEventListener('click', closeSavedSearchesOnClickOutside);
    }
}

function getSavedSearches() {
    try {
        return JSON.parse(localStorage.getItem(SAVED_SEARCHES_KEY)) || [];
    } catch {
        return [];
    }
}

function saveSavedSearches(searches) {
    localStorage.setItem(SAVED_SEARCHES_KEY, JSON.stringify(searches));
}

function saveCurrentSearch() {
    const name = prompt('Name this search:');
    if (!name || !name.trim()) return;
    
    const search = {
        id: Date.now(),
        name: name.trim(),
        mode: currentMode,
        query: document.getElementById('mainSearch').value,
        industry: document.getElementById('industrySearch').value,
        state: document.getElementById('stateFilter').value,
        metro: document.getElementById('metroFilter')?.value || '',
        city: document.getElementById('cityFilter')?.value || '',
        sector: document.getElementById('sectorFilter')?.value || '',
        createdAt: new Date().toISOString()
    };
    
    const searches = getSavedSearches();
    searches.unshift(search);
    
    // Keep only last 20 searches
    if (searches.length > 20) searches.pop();
    
    saveSavedSearches(searches);
    renderSavedSearches();
}

function renderSavedSearches() {
    const searches = getSavedSearches();
    const container = document.getElementById('savedSearchesList');
    
    if (searches.length === 0) {
        container.innerHTML = '<div class="p-3 text-sm text-warmgray-400 text-center">No saved searches</div>';
        return;
    }
    
    container.innerHTML = searches.map(s => `
        <div class="flex items-center justify-between px-3 py-2 hover:bg-warmgray-50 group">
            <button onclick="loadSavedSearch(${s.id})" class="flex-1 text-left">
                <div class="text-sm font-medium text-warmgray-900">${escapeHtml(s.name)}</div>
                <div class="text-xs text-warmgray-400">
                    ${s.mode === 'employers' ? 'Employers' : 'Unions'}
                    ${s.state ? ` · ${s.state}` : ''}
                    ${s.query ? ` · "${escapeHtml(s.query)}"` : ''}
                </div>
            </button>
            <button onclick="deleteSavedSearch(${s.id})" 
                class="opacity-0 group-hover:opacity-100 p-1 text-warmgray-400 hover:text-red-500 transition-opacity">
                <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12"/>
                </svg>
            </button>
        </div>
    `).join('');
}

function loadSavedSearch(id) {
    const searches = getSavedSearches();
    const search = searches.find(s => s.id === id);
    if (!search) return;
    
    // Set mode
    setSearchMode(search.mode);
    
    // Set filters
    document.getElementById('mainSearch').value = search.query || '';
    document.getElementById('industrySearch').value = search.industry || '';
    
    // Load state and dependent filters
    if (search.state) {
        document.getElementById('stateFilter').value = search.state;
        onStateChange().then(() => {
            if (search.metro) document.getElementById('metroFilter').value = search.metro;
            if (search.city) document.getElementById('cityFilter').value = search.city;
        });
    }
    
    if (search.sector && document.getElementById('sectorFilter')) {
        document.getElementById('sectorFilter').value = search.sector;
    }
    
    // Close dropdown and execute search
    document.getElementById('savedSearchesDropdown').classList.add('hidden');
    
    // Small delay to let filters settle
    setTimeout(() => executeSearch(), 100);
}

function deleteSavedSearch(id) {
    if (!confirm('Delete this saved search?')) return;
    
    const searches = getSavedSearches().filter(s => s.id !== id);
    saveSavedSearches(searches);
    renderSavedSearches();
}


// ==========================================
// UNIFIED EMPLOYERS MODAL
// ==========================================
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

// getSourceBadge() defined in utils.js — removed duplicate (Sprint 6.1 review fix)

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

// ==========================================

// ==========================================
// NLRB ELECTIONS MODAL
// ==========================================
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

// ==========================================

// ==========================================
// PUBLIC SECTOR MODAL
// ==========================================
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

// ==========================================

// ==========================================
// TRENDS MODAL
// ==========================================
let trendsData = {};
let trendsCharts = {};
let currentTrendsTab = 'overview';

function openTrendsModal() {
    document.getElementById('trendsModal').classList.remove('hidden');
    document.getElementById('trendsModal').classList.add('flex');
    document.body.classList.add('modal-open');
    loadTrendsData();
}

function closeTrendsModal() {
    document.getElementById('trendsModal').classList.add('hidden');
    document.getElementById('trendsModal').classList.remove('flex');
    document.body.classList.remove('modal-open');

    // Destroy charts to prevent memory leaks
    Object.values(trendsCharts).forEach(chart => {
        if (chart) chart.destroy();
    });
    trendsCharts = {};
}

async function loadTrendsData() {
    document.getElementById('trendsLoading').classList.remove('hidden');
    document.getElementById('trendsContent').classList.add('hidden');

    try {
        const [national, elections, affiliations, states, sectors] = await Promise.all([
            fetch(`${API_BASE}/trends/national?start_year=2010&end_year=2024`).then(r => r.json()),
            fetch(`${API_BASE}/trends/elections`).then(r => r.json()),
            fetch(`${API_BASE}/trends/affiliations/summary`).then(r => r.json()),
            fetch(`${API_BASE}/trends/states/summary`).then(r => r.json()),
            fetch(`${API_BASE}/trends/sectors`).then(r => r.json())
        ]);

        trendsData = { national, elections, affiliations, states, sectors };
        renderTrendsOverview();

        // Populate dropdowns
        populateTrendsDropdowns();

    } catch (e) {
        console.error('Trends data failed:', e);
    } finally {
        document.getElementById('trendsLoading').classList.add('hidden');
        document.getElementById('trendsContent').classList.remove('hidden');
    }
}

function populateTrendsDropdowns() {
    // State dropdown
    const stateSelect = document.getElementById('trendsStateSelect');
    if (stateSelect.options.length <= 1) {
        const mainStateSelect = document.getElementById('stateFilter');
        for (let i = 1; i < mainStateSelect.options.length; i++) {
            const opt = mainStateSelect.options[i];
            stateSelect.add(new Option(opt.text, opt.value));
        }
    }

    // Affiliation dropdown
    const affSelect = document.getElementById('trendsAffiliationSelect');
    if (affSelect.options.length <= 1 && trendsData.affiliations?.affiliations) {
        trendsData.affiliations.affiliations.slice(0, 30).forEach(a => {
            affSelect.add(new Option(a.aff_abbr || a.abbreviation, a.aff_abbr || a.abbreviation));
        });
    }
}

function setTrendsTab(tab) {
    currentTrendsTab = tab;

    ['overview', 'membership', 'elections', 'byState', 'byAffiliation'].forEach(t => {
        const btn = document.getElementById(`trendsTab${t.charAt(0).toUpperCase() + t.slice(1)}`);
        const panel = document.getElementById(`trendsPanel${t.charAt(0).toUpperCase() + t.slice(1)}`);

        if (t === tab) {
            btn.className = 'px-4 py-2 text-sm font-semibold rounded-lg bg-emerald-100 text-emerald-700';
            panel.classList.remove('hidden');
        } else {
            btn.className = 'px-4 py-2 text-sm font-semibold rounded-lg text-warmgray-600 hover:bg-warmgray-100';
            panel.classList.add('hidden');
        }
    });

    // Render the selected tab
    switch (tab) {
        case 'overview': renderTrendsOverview(); break;
        case 'membership': renderTrendsMembership(); break;
        case 'elections': renderTrendsElections(); break;
    }
}

function renderTrendsOverview() {
    const data = trendsData.national?.trends || [];
    const elections = trendsData.elections?.election_trends || [];

    // Find latest year data
    const latest = data[data.length - 1];
    const first = data[0];

    if (latest) {
        // Use deduplicated data if available, otherwise fall back to raw
        const latestMembers = latest.total_members_dedup || latest.total_members_raw || 0;
        const firstMembers = first?.total_members_dedup || first?.total_members_raw || 0;
        document.getElementById('trendsMembers2024').textContent = formatNumber(latestMembers);
        if (first && latestMembers && firstMembers) {
            const change = ((latestMembers - firstMembers) / firstMembers * 100).toFixed(1);
            document.getElementById('trendsMembersChange').textContent = `${change > 0 ? '+' : ''}${change}% since ${first.year}`;
        }
    }

    // Calculate averages using deduplicated data
    if (data.length > 1) {
        let totalChange = 0;
        for (let i = 1; i < data.length; i++) {
            const curr = data[i].total_members_dedup || data[i].total_members_raw;
            const prev = data[i-1].total_members_dedup || data[i-1].total_members_raw;
            if (curr && prev) {
                totalChange += (curr - prev) / prev * 100;
            }
        }
        document.getElementById('trendsAvgChange').textContent = `${(totalChange / (data.length - 1)).toFixed(2)}%`;
    }

    // Elections stats
    if (elections.length > 0) {
        const latestElection = elections[elections.length - 1];
        const totalWins = elections.reduce((sum, y) => sum + (y.union_wins || 0), 0);
        const totalElections = elections.reduce((sum, y) => sum + (y.total_elections || 0), 0);
        document.getElementById('trendsWinRate').textContent = totalElections > 0
            ? `${Math.round(totalWins / totalElections * 100)}%` : '—';
        document.getElementById('trendsElections2024').textContent = formatNumber(latestElection?.total_elections || 0);
    }

    // Overview charts
    renderOverviewCharts();
}

function renderOverviewCharts() {
    const data = trendsData.national?.trends || [];
    const elections = trendsData.elections?.election_trends || [];

    // Membership chart
    const ctx1 = document.getElementById('trendsOverviewChart');
    if (ctx1 && data.length > 0) {
        if (trendsCharts.overview) trendsCharts.overview.destroy();
        trendsCharts.overview = new Chart(ctx1, {
            type: 'line',
            data: {
                labels: data.map(d => d.year),
                datasets: [{
                    label: 'Total Members (Deduplicated)',
                    data: data.map(d => d.total_members_dedup || d.total_members_raw),
                    borderColor: '#059669',
                    backgroundColor: 'rgba(5, 150, 105, 0.1)',
                    fill: true,
                    tension: 0.3
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: { legend: { display: false } },
                scales: {
                    y: { beginAtZero: false, ticks: { callback: v => (v/1000000).toFixed(1) + 'M' } }
                }
            }
        });
    }

    // Elections chart
    const ctx2 = document.getElementById('trendsElectionsChart');
    if (ctx2 && elections.length > 0) {
        if (trendsCharts.electionsOverview) trendsCharts.electionsOverview.destroy();
        trendsCharts.electionsOverview = new Chart(ctx2, {
            type: 'bar',
            data: {
                labels: elections.map(d => d.year),
                datasets: [
                    {
                        label: 'Won',
                        data: elections.map(d => d.union_wins || 0),
                        backgroundColor: '#22c55e'
                    },
                    {
                        label: 'Lost',
                        data: elections.map(d => d.union_losses || 0),
                        backgroundColor: '#ef4444'
                    }
                ]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: { legend: { position: 'bottom' } },
                scales: { x: { stacked: true }, y: { stacked: true } }
            }
        });
    }
}

function renderTrendsMembership() {
    const data = trendsData.national?.trends || [];
    const affiliations = trendsData.affiliations?.affiliations || [];
    const sectors = trendsData.sectors?.sectors || [];

    // Main membership chart
    const ctx = document.getElementById('trendsMembershipChart');
    if (ctx && data.length > 0) {
        if (trendsCharts.membership) trendsCharts.membership.destroy();
        trendsCharts.membership = new Chart(ctx, {
            type: 'line',
            data: {
                labels: data.map(d => d.year),
                datasets: [{
                    label: 'Total Members (Deduplicated)',
                    data: data.map(d => d.total_members_dedup || d.total_members_raw),
                    borderColor: '#059669',
                    backgroundColor: 'rgba(5, 150, 105, 0.1)',
                    fill: true,
                    tension: 0.3,
                    pointRadius: 4
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: { legend: { display: false } },
                scales: {
                    y: { beginAtZero: false, ticks: { callback: v => (v/1000000).toFixed(1) + 'M' } }
                }
            }
        });
    }

    // Top growing/declining (sort by pct_change)
    const sortedAffs = [...affiliations].sort((a, b) => (b.pct_change || 0) - (a.pct_change || 0));
    const growing = sortedAffs.filter(a => (a.pct_change || 0) > 0).slice(0, 5);
    const declining = sortedAffs.filter(a => (a.pct_change || 0) < 0).slice(-5).reverse();

    document.getElementById('trendsTopGrowing').innerHTML = growing.map(a => `
        <div class="flex justify-between">
            <span>${a.aff_abbr}</span>
            <span class="text-green-600">+${(a.pct_change || 0).toFixed(1)}%</span>
        </div>
    `).join('') || '<div class="text-warmgray-400">No data</div>';

    document.getElementById('trendsDeclining').innerHTML = declining.map(a => `
        <div class="flex justify-between">
            <span>${a.aff_abbr}</span>
            <span class="text-red-600">${(a.pct_change || 0).toFixed(1)}%</span>
        </div>
    `).join('') || '<div class="text-warmgray-400">No data</div>';

    // Sectors
    document.getElementById('trendsSectors').innerHTML = sectors.slice(0, 5).map(s => `
        <div class="flex justify-between">
            <span>${s.sector || s.name}</span>
            <span class="font-semibold">${formatNumber(s.members || s.total_members || 0)}</span>
        </div>
    `).join('') || '<div class="text-warmgray-400">No data</div>';
}

function renderTrendsElections() {
    const elections = trendsData.elections?.election_trends || [];
    const byState = trendsData.elections?.by_state || [];

    // Elections by year chart
    const ctx = document.getElementById('trendsElectionsByYearChart');
    if (ctx && elections.length > 0) {
        if (trendsCharts.electionsByYear) trendsCharts.electionsByYear.destroy();
        trendsCharts.electionsByYear = new Chart(ctx, {
            type: 'bar',
            data: {
                labels: elections.map(d => d.year),
                datasets: [
                    {
                        label: 'Won',
                        data: elections.map(d => d.union_wins || 0),
                        backgroundColor: '#22c55e'
                    },
                    {
                        label: 'Lost',
                        data: elections.map(d => d.union_losses || 0),
                        backgroundColor: '#ef4444'
                    }
                ]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: { legend: { position: 'bottom' } },
                scales: { y: { beginAtZero: true } }
            }
        });
    }

    // Win rate by year
    document.getElementById('trendsWinRateByYear').innerHTML = elections.slice().reverse().map(y => {
        const rate = y.win_rate || 0;
        return `
            <div class="flex justify-between">
                <span>${y.year}</span>
                <span class="font-semibold ${rate >= 50 ? 'text-green-600' : 'text-red-600'}">${rate.toFixed(1)}%</span>
            </div>
        `;
    }).join('') || '<div class="text-warmgray-400">No data</div>';

    // By state - Note: API may not return by_state, show message if empty
    document.getElementById('trendsElectionsByState').innerHTML = byState.length > 0
        ? byState.slice(0, 10).map(s => `
            <div class="flex justify-between">
                <span>${s.state}</span>
                <span class="font-semibold">${formatNumber(s.total_elections || s.total || 0)}</span>
            </div>
        `).join('')
        : '<div class="text-warmgray-400">State breakdown not available</div>';
}

async function loadStateTrends() {
    const state = document.getElementById('trendsStateSelect').value;
    if (!state) return;

    try {
        const response = await fetch(`${API_BASE}/trends/by-state/${state}`);
        const data = await response.json();

        const trends = data.trends || [];
        const ctx = document.getElementById('trendsStateChart');

        if (ctx && trends.length > 0) {
            if (trendsCharts.state) trendsCharts.state.destroy();
            trendsCharts.state = new Chart(ctx, {
                type: 'line',
                data: {
                    labels: trends.map(d => d.year),
                    datasets: [{
                        label: `${state} Members`,
                        data: trends.map(d => d.total_members || d.members),
                        borderColor: '#059669',
                        backgroundColor: 'rgba(5, 150, 105, 0.1)',
                        fill: true,
                        tension: 0.3
                    }]
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    plugins: { legend: { display: false } },
                    scales: { y: { beginAtZero: false } }
                }
            });
        }

        // State info cards
        const latest = trends[trends.length - 1];
        const first = trends[0];
        document.getElementById('trendsStateInfo').innerHTML = `
            <div class="bg-white rounded-lg p-4 shadow-sm border border-warmgray-200">
                <div class="text-xs font-semibold text-warmgray-500 uppercase">Latest Members</div>
                <div class="text-2xl font-bold text-warmgray-900 mt-1">${formatNumber(latest?.total_members || latest?.members || 0)}</div>
            </div>
            <div class="bg-white rounded-lg p-4 shadow-sm border border-warmgray-200">
                <div class="text-xs font-semibold text-warmgray-500 uppercase">Change</div>
                <div class="text-2xl font-bold ${first && latest && latest.total_members > first.total_members ? 'text-green-600' : 'text-red-600'} mt-1">
                    ${first && latest ? ((latest.total_members - first.total_members) / first.total_members * 100).toFixed(1) : 0}%
                </div>
            </div>
            <div class="bg-white rounded-lg p-4 shadow-sm border border-warmgray-200">
                <div class="text-xs font-semibold text-warmgray-500 uppercase">Years of Data</div>
                <div class="text-2xl font-bold text-warmgray-900 mt-1">${trends.length}</div>
            </div>
        `;
    } catch (e) {
        console.error('State trends failed:', e);
    }
}

async function loadAffiliationTrends() {
    const aff = document.getElementById('trendsAffiliationSelect').value;
    if (!aff) return;

    try {
        const response = await fetch(`${API_BASE}/trends/by-affiliation/${encodeURIComponent(aff)}`);
        const data = await response.json();

        const trends = data.trends || [];
        const ctx = document.getElementById('trendsAffiliationChart');

        if (ctx && trends.length > 0) {
            if (trendsCharts.affiliation) trendsCharts.affiliation.destroy();
            trendsCharts.affiliation = new Chart(ctx, {
                type: 'line',
                data: {
                    labels: trends.map(d => d.year),
                    datasets: [{
                        label: `${aff} Members`,
                        data: trends.map(d => d.total_members || d.members),
                        borderColor: '#8b5cf6',
                        backgroundColor: 'rgba(139, 92, 246, 0.1)',
                        fill: true,
                        tension: 0.3
                    }]
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    plugins: { legend: { display: false } },
                    scales: { y: { beginAtZero: false } }
                }
            });
        }

        // Affiliation info cards
        const latest = trends[trends.length - 1];
        const first = trends[0];
        document.getElementById('trendsAffiliationInfo').innerHTML = `
            <div class="bg-white rounded-lg p-4 shadow-sm border border-warmgray-200">
                <div class="text-xs font-semibold text-warmgray-500 uppercase">Latest Members</div>
                <div class="text-2xl font-bold text-warmgray-900 mt-1">${formatNumber(latest?.total_members || latest?.members || 0)}</div>
            </div>
            <div class="bg-white rounded-lg p-4 shadow-sm border border-warmgray-200">
                <div class="text-xs font-semibold text-warmgray-500 uppercase">Change</div>
                <div class="text-2xl font-bold ${first && latest && latest.total_members > first.total_members ? 'text-green-600' : 'text-red-600'} mt-1">
                    ${first && latest ? ((latest.total_members - first.total_members) / first.total_members * 100).toFixed(1) : 0}%
                </div>
            </div>
            <div class="bg-white rounded-lg p-4 shadow-sm border border-warmgray-200">
                <div class="text-xs font-semibold text-warmgray-500 uppercase">Years of Data</div>
                <div class="text-2xl font-bold text-warmgray-900 mt-1">${trends.length}</div>
            </div>
        `;
    } catch (e) {
        console.error('Affiliation trends failed:', e);
    }
}

