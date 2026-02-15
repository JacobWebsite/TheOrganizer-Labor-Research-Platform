// modal-trends.js -- Trends modal + charts

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
            ? `${Math.round(totalWins / totalElections * 100)}%` : '--';
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
