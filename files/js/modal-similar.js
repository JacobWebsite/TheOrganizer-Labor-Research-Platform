// modal-similar.js -- Find Similar, National Dashboard, National Browser

let dashboardChart = null;
let currentDashboardAffiliation = null;

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
