// modal-analytics.js -- Analytics Dashboard + charts

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
