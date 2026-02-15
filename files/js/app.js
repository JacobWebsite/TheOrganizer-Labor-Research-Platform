// app.js -- App initialization, mode switching, exports, URL state, keyboard shortcuts

// ==========================================
// APP MODE SWITCHING
// ==========================================
function setAppMode(mode) {
    currentAppMode = mode;

    const modes = ['territory', 'search', 'deepdive', 'uniondive', 'admin'];
    const containers = {
        territory: document.getElementById('territoryMode'),
        search: document.getElementById('searchMode'),
        deepdive: document.getElementById('deepDiveMode'),
        uniondive: document.getElementById('unionDiveMode'),
        admin: document.getElementById('adminMode')
    };

    // Hide inactive, show + animate active
    modes.forEach(m => {
        const el = containers[m];
        if (m === mode) {
            el.classList.remove('hidden');
            el.classList.remove('mode-enter');
            void el.offsetWidth; // reflow
            el.classList.add('mode-enter');
        } else {
            el.classList.add('hidden');
            el.classList.remove('mode-enter');
        }
    });

    // Update header toggle
    const activeClass = 'app-mode-active px-4 py-1.5 text-sm font-semibold rounded-full transition-all';
    const inactiveClass = 'app-mode-inactive px-4 py-1.5 text-sm font-semibold rounded-full transition-all';
    document.getElementById('modeTerritory').className = mode === 'territory' ? activeClass : inactiveClass;
    document.getElementById('modeSearch').className = (mode === 'search' || mode === 'deepdive' || mode === 'uniondive') ? activeClass : inactiveClass;

    // Invalidate maps when switching to avoid stale tiles
    if (mode === 'search' && fullMap) {
        setTimeout(() => fullMap.invalidateSize(), 200);
    }
    if (mode === 'territory' && territoryMap) {
        setTimeout(() => territoryMap.invalidateSize(), 200);
    }
}

function openDeepDive(employerId, returnTo) {
    deepDiveReturnMode = returnTo || currentAppMode;
    const labels = { territory: 'Back to Territory', uniondive: 'Back to Union Profile' };
    document.getElementById('deepDiveBackLabel').textContent = labels[deepDiveReturnMode] || 'Back to Search';
    setAppMode('deepdive');
    loadDeepDiveData(employerId);
}

function returnFromDeepDive() {
    setAppMode(deepDiveReturnMode);
}


// ==========================================
// EXPORTS: TERRITORY + EMPLOYER
// ==========================================
function exportTerritoryReport() {
    const ctx = territoryContext;
    const cache = territoryDataCache;
    const title = (ctx.union || 'All Unions') + (ctx.state ? ' — ' + ctx.state : '') + (ctx.metro ? ' / ' + ctx.metro : '');
    const date = new Date().toLocaleDateString();

    // Gather KPIs
    const s = cache.unionData?.summary || cache.unionData || {};
    const members = s.total_members || s.members || 0;
    const locals = s.local_count || s.locals || 0;
    const workers = s.covered_workers || s.workers || 0;

    // Targets table
    const targets = cache.targetsData?.results || [];
    let targetsHtml = '';
    if (targets.length) {
        targetsHtml = `
            <h2 style="font-size:16px; margin:24px 0 8px;">Top Organizing Targets</h2>
            <table style="width:100%; border-collapse:collapse; font-size:13px;">
                <tr style="background:#f5f3f0;">
                    <th style="text-align:left; padding:6px 8px; border:1px solid #ddd;">Employer</th>
                    <th style="text-align:left; padding:6px 8px; border:1px solid #ddd;">Location</th>
                    <th style="text-align:right; padding:6px 8px; border:1px solid #ddd;">Score</th>
                    <th style="text-align:right; padding:6px 8px; border:1px solid #ddd;">Tier</th>
                </tr>
                ${targets.slice(0, 20).map(t => {
                    const score = t.organizing_score || 0;
                    const tier = score >= 30 ? 'TOP' : score >= 25 ? 'HIGH' : score >= 20 ? 'MEDIUM' : 'LOW';
                    return `<tr>
                        <td style="padding:5px 8px; border:1px solid #ddd;">${escapeHtml(t.estab_name || '')}</td>
                        <td style="padding:5px 8px; border:1px solid #ddd;">${escapeHtml((t.site_city || '') + ', ' + (t.site_state || ''))}</td>
                        <td style="padding:5px 8px; border:1px solid #ddd; text-align:right; font-weight:bold;">${score}</td>
                        <td style="padding:5px 8px; border:1px solid #ddd; text-align:right;">${tier}</td>
                    </tr>`;
                }).join('')}
            </table>
        `;
    }

    // Elections table
    const elections = cache.electionsData?.elections || [];
    let electionsHtml = '';
    if (elections.length) {
        electionsHtml = `
            <h2 style="font-size:16px; margin:24px 0 8px;">Recent NLRB Elections</h2>
            <table style="width:100%; border-collapse:collapse; font-size:13px;">
                <tr style="background:#f5f3f0;">
                    <th style="text-align:left; padding:6px 8px; border:1px solid #ddd;">Date</th>
                    <th style="text-align:left; padding:6px 8px; border:1px solid #ddd;">Employer</th>
                    <th style="text-align:center; padding:6px 8px; border:1px solid #ddd;">Voters</th>
                    <th style="text-align:right; padding:6px 8px; border:1px solid #ddd;">Result</th>
                </tr>
                ${elections.slice(0, 15).map(e => `<tr>
                    <td style="padding:5px 8px; border:1px solid #ddd;">${e.election_date || '--'}</td>
                    <td style="padding:5px 8px; border:1px solid #ddd;">${escapeHtml(e.employer_name || '')}</td>
                    <td style="padding:5px 8px; border:1px solid #ddd; text-align:center;">${e.eligible_voters || '--'}</td>
                    <td style="padding:5px 8px; border:1px solid #ddd; text-align:right; color:${e.union_won ? '#16a34a' : '#dc2626'};">${e.union_won ? 'Won' : 'Lost'}</td>
                </tr>`).join('')}
            </table>
        `;
    }

    // WHD violators
    const violators = cache.whdData?.results || [];
    let violatorsHtml = '';
    if (violators.length) {
        violatorsHtml = `
            <h2 style="font-size:16px; margin:24px 0 8px;">Top Wage & Safety Violators</h2>
            <table style="width:100%; border-collapse:collapse; font-size:13px;">
                <tr style="background:#f5f3f0;">
                    <th style="text-align:left; padding:6px 8px; border:1px solid #ddd;">Employer</th>
                    <th style="text-align:right; padding:6px 8px; border:1px solid #ddd;">Back Wages</th>
                    <th style="text-align:right; padding:6px 8px; border:1px solid #ddd;">Violations</th>
                </tr>
                ${violators.slice(0, 10).map(v => `<tr>
                    <td style="padding:5px 8px; border:1px solid #ddd;">${escapeHtml(v.name_normalized || '')}</td>
                    <td style="padding:5px 8px; border:1px solid #ddd; text-align:right; color:#dc2626;">$${formatNumber(Math.round(v.total_backwages || 0))}</td>
                    <td style="padding:5px 8px; border:1px solid #ddd; text-align:right;">${formatNumber(v.total_violations || 0)}</td>
                </tr>`).join('')}
            </table>
        `;
    }

    const pw = window.open('', '_blank');
    pw.document.write(`<!DOCTYPE html><html><head>
        <title>Territory Report — ${escapeHtml(title)}</title>
        <link href="https://fonts.googleapis.com/css2?family=Playfair+Display:wght@600;700&family=Source+Sans+Pro:wght@400;600;700&display=swap" rel="stylesheet">
        <style>
            body { font-family: 'Source Sans Pro', sans-serif; padding: 40px; max-width: 900px; margin: 0 auto; color: #1a1a1a; }
            h1 { font-family: 'Playfair Display', serif; margin: 0; }
            .kpi-row { display: flex; gap: 16px; margin: 20px 0; }
            .kpi { flex: 1; background: #f5f3f0; border-radius: 8px; padding: 16px; text-align: center; }
            .kpi-value { font-size: 22px; font-weight: 700; }
            .kpi-label { font-size: 11px; text-transform: uppercase; color: #7d7770; letter-spacing: 0.05em; }
            .footer { margin-top: 40px; padding-top: 16px; border-top: 1px solid #ddd; font-size: 12px; color: #999; }
            @media print { body { padding: 20px; } }
        </style>
    </head><body>
        <h1>${escapeHtml(title)}</h1>
        <p style="color:#7d7770; margin:4px 0 0;">Territory Report &mdash; Generated ${date}</p>

        <div class="kpi-row">
            <div class="kpi"><div class="kpi-label">Members</div><div class="kpi-value">${formatNumber(members)}</div></div>
            <div class="kpi"><div class="kpi-label">Locals</div><div class="kpi-value">${formatNumber(locals)}</div></div>
            <div class="kpi"><div class="kpi-label">Covered Workers</div><div class="kpi-value">${formatNumber(workers)}</div></div>
            <div class="kpi"><div class="kpi-label">Organizing Targets</div><div class="kpi-value">${formatNumber(cache.targetsData?.total || targets.length)}</div></div>
        </div>

        ${targetsHtml}
        ${electionsHtml}
        ${violatorsHtml}

        <div class="footer">
            <p>Data sources: DOL OLMS, OSHA, NLRB, WHD, BLS</p>
            <p>Generated from The Organizer &mdash; Labor Research Platform</p>
        </div>
    </body></html>`);
    pw.document.close();
    pw.focus();
    setTimeout(() => pw.print(), 300);
}

function exportEmployerReport() {
    const sc = deepDiveData.scorecard;
    if (!sc) { alert('No employer data loaded'); return; }

    const est = sc.establishment || {};
    const score = sc.organizing_score || 0;
    const breakdown = sc.score_breakdown || {};
    const osha = sc.osha_context || {};
    const geo = sc.geographic_context || {};
    const contracts = sc.contracts || {};
    const nlrb = sc.nlrb_context || {};
    const ctx = sc.context || {};
    const tier = score >= 30 ? 'TOP' : score >= 25 ? 'HIGH' : score >= 20 ? 'MEDIUM' : 'LOW';
    const date = new Date().toLocaleDateString();

    const factors = SCORE_FACTORS.map(f => [f.label, breakdown[f.key], f.max]);

    const siblings = deepDiveData.siblings?.siblings || [];

    const pw = window.open('', '_blank');
    pw.document.write(`<!DOCTYPE html><html><head>
        <title>${escapeHtml(est.estab_name || 'Employer')} — Report</title>
        <link href="https://fonts.googleapis.com/css2?family=Playfair+Display:wght@600;700&family=Source+Sans+Pro:wght@400;600;700&display=swap" rel="stylesheet">
        <style>
            body { font-family: 'Source Sans Pro', sans-serif; padding: 40px; max-width: 900px; margin: 0 auto; color: #1a1a1a; }
            h1 { font-family: 'Playfair Display', serif; margin: 0; }
            h2 { font-size: 16px; margin: 24px 0 8px; }
            .score-badge { display: inline-block; padding: 4px 12px; border-radius: 4px; font-weight: 700; font-size: 14px; }
            .kpi-row { display: flex; gap: 16px; margin: 20px 0; }
            .kpi { flex: 1; background: #f5f3f0; border-radius: 8px; padding: 16px; text-align: center; }
            .kpi-value { font-size: 22px; font-weight: 700; }
            .kpi-label { font-size: 11px; text-transform: uppercase; color: #7d7770; letter-spacing: 0.05em; }
            table { width: 100%; border-collapse: collapse; font-size: 13px; }
            th { background: #f5f3f0; text-align: left; padding: 6px 8px; border: 1px solid #ddd; }
            td { padding: 5px 8px; border: 1px solid #ddd; }
            .bar { height: 10px; border-radius: 5px; background: #e8e5e0; }
            .bar-fill { height: 10px; border-radius: 5px; }
            .footer { margin-top: 40px; padding-top: 16px; border-top: 1px solid #ddd; font-size: 12px; color: #999; }
            @media print { body { padding: 20px; } }
        </style>
    </head><body>
        <div style="display:flex; justify-content:space-between; align-items:flex-start;">
            <div>
                <h1>${escapeHtml(est.estab_name || 'Unknown')}</h1>
                <p style="color:#7d7770; margin:4px 0;">
                    ${escapeHtml(est.site_address || '')}${est.site_address ? ', ' : ''}${escapeHtml(est.site_city || '')}, ${escapeHtml(est.site_state || '')} ${escapeHtml(est.site_zip || '')}
                </p>
                <p style="color:#7d7770; font-size:12px;">NAICS: ${est.naics_code || 'N/A'} | Risk: ${est.risk_level || 'N/A'} | ${geo.is_rtw_state ? 'Right-to-Work State' : 'Non-RTW State'}</p>
            </div>
            <div style="text-align:right;">
                <div style="font-size:36px; font-weight:700; color:${score >= 30 ? '#16a34a' : score >= 25 ? '#2563eb' : '#ca8a04'};">${score}</div>
                <span class="score-badge" style="background:${tier === 'TOP' ? '#dcfce7' : tier === 'HIGH' ? '#dbeafe' : '#fef9c3'}; color:${tier === 'TOP' ? '#166534' : tier === 'HIGH' ? '#1e40af' : '#854d0e'};">${tier}</span>
            </div>
        </div>

        <div class="kpi-row">
            <div class="kpi"><div class="kpi-label">Employees</div><div class="kpi-value">${formatNumber(est.employee_count || 0)}</div></div>
            <div class="kpi"><div class="kpi-label">OSHA Violations</div><div class="kpi-value" style="color:#dc2626;">${formatNumber(est.total_violations || 0)}</div></div>
            <div class="kpi"><div class="kpi-label">Penalties</div><div class="kpi-value">$${formatNumber(Math.round(est.total_penalties || 0))}</div></div>
            <div class="kpi"><div class="kpi-label">Govt Contracts</div><div class="kpi-value">${contracts.total_funding ? '$' + formatCompact(contracts.total_funding) : 'None'}</div></div>
        </div>

        <h2>Score Breakdown</h2>
        <table>
            <tr><th>Factor</th><th style="text-align:right;">Score</th><th style="text-align:right;">Max</th><th style="width:40%;">Bar</th></tr>
            ${factors.map(([label, val, max]) => {
                const v = val || 0;
                const pct = Math.round((v / max) * 100);
                return `<tr>
                    <td>${label}</td>
                    <td style="text-align:right; font-weight:700;">${v}</td>
                    <td style="text-align:right; color:#999;">${max}</td>
                    <td><div class="bar"><div class="bar-fill" style="width:${pct}%; background:${pct >= 80 ? '#16a34a' : pct >= 50 ? '#2563eb' : '#ca8a04'};"></div></div></td>
                </tr>`;
            }).join('')}
        </table>

        <h2>Context</h2>
        <table>
            <tr><td>OSHA Industry Ratio</td><td style="text-align:right;">${osha.industry_ratio ? osha.industry_ratio.toFixed(1) + 'x average' : 'N/A'}</td></tr>
            <tr><td>NLRB Win Prediction</td><td style="text-align:right;">${nlrb.predicted_win_pct ? nlrb.predicted_win_pct.toFixed(1) + '%' : 'N/A'}</td></tr>
            <tr><td>State NLRB Win Rate</td><td style="text-align:right;">${geo.nlrb_win_rate ? geo.nlrb_win_rate.toFixed(1) + '%' : 'N/A'}</td></tr>
            <tr><td>Past Elections at Employer</td><td style="text-align:right;">${nlrb.direct_case_count || ctx.nlrb_count || 0}</td></tr>
            <tr><td>Federal Contract Obligations</td><td style="text-align:right;">${contracts.federal_funding ? '$' + formatCompact(contracts.federal_funding) : 'None'}</td></tr>
        </table>

        ${siblings.length ? `
            <h2>Similar Unionized Employers</h2>
            <table>
                <tr><th>Employer</th><th>Location</th><th style="text-align:right;">Match</th></tr>
                ${siblings.slice(0, 8).map(s => `<tr>
                    <td>${escapeHtml(s.employer_name || '')}</td>
                    <td>${escapeHtml((s.city || '') + ', ' + (s.state || ''))}</td>
                    <td style="text-align:right;">${s.match_score || 0}%</td>
                </tr>`).join('')}
            </table>
        ` : ''}

        <div class="footer">
            <p>Employer Profile Report &mdash; Generated ${date}</p>
            <p>Data sources: DOL OLMS, OSHA, NLRB, WHD, BLS, USASpending</p>
            <p>Generated from The Organizer &mdash; Labor Research Platform</p>
        </div>
    </body></html>`);
    pw.document.close();
    pw.focus();
    setTimeout(() => pw.print(), 300);
}

function exportTerritoryTargetsCSV() {
    const targets = territoryDataCache.targetsData?.results || [];
    if (!targets.length) { alert('No targets data to export'); return; }

    const header = 'Employer,Address,City,State,ZIP,NAICS,Employees,Score,Tier,Violations,Penalties';
    const rows = targets.map(t => {
        const score = t.organizing_score || 0;
        const tier = score >= 30 ? 'TOP' : score >= 25 ? 'HIGH' : score >= 20 ? 'MEDIUM' : 'LOW';
        return [
            csvEscape(t.estab_name || ''),
            csvEscape(t.site_address || ''),
            csvEscape(t.site_city || ''),
            csvEscape(t.site_state || ''),
            csvEscape(t.site_zip || ''),
            t.naics_code || '',
            t.employee_count || 0,
            score,
            tier,
            t.total_violations || 0,
            t.total_penalties || 0
        ].join(',');
    });

    const ctx = territoryContext;
    const filename = `organizing_targets_${ctx.union || 'all'}_${ctx.state || 'national'}_${new Date().toISOString().slice(0,10)}.csv`;
    downloadCSV(header + '\n' + rows.join('\n'), filename);
}

function exportTerritoryElectionsCSV() {
    const elections = territoryDataCache.electionsData?.elections || [];
    if (!elections.length) { alert('No elections data to export'); return; }

    const header = 'Date,Employer,City,State,Union,Eligible Voters,Vote Margin,Result';
    const rows = elections.map(e => [
        csvEscape(e.election_date || ''),
        csvEscape(e.employer_name || ''),
        csvEscape(e.employer_city || ''),
        csvEscape(e.employer_state || ''),
        csvEscape(e.aff_abbr || ''),
        e.eligible_voters || 0,
        e.vote_margin || 0,
        e.union_won ? 'Won' : 'Lost'
    ].join(','));

    const ctx = territoryContext;
    const filename = `nlrb_elections_${ctx.state || 'national'}_${new Date().toISOString().slice(0,10)}.csv`;
    downloadCSV(header + '\n' + rows.join('\n'), filename);
}

// ==========================================
// INITIALIZATION
// ==========================================
function initEventListeners() {
    // Delegated click handler for data-action attributes
    document.addEventListener('click', function(e) {
        const target = e.target.closest('[data-action]');
        if (!target) return;
        // data-action-self: only fire if clicked element IS the target (backdrop clicks)
        if (target.dataset.actionSelf && e.target !== target) return;
        const action = target.dataset.action;
        const arg = target.dataset.actionArg;
        const fn = window[action];
        if (typeof fn === 'function') {
            arg !== undefined ? fn(arg) : fn();
        }
    });

    // Delegated change handler for data-change attributes
    document.addEventListener('change', function(e) {
        const target = e.target.closest('[data-change]');
        if (!target) return;
        const action = target.dataset.change;
        const fn = window[action];
        if (typeof fn === 'function') {
            target.dataset.changeValue ? fn(target.value) : fn();
        }
    });
}

document.addEventListener('DOMContentLoaded', async () => {
    initEventListeners();
    initMap();
    setupTypeahead();
    setupGeoChangeListeners();
    setupKeyboardShortcuts();

    // Sort dropdown triggers search
    document.getElementById('sortBy').addEventListener('change', () => executeSearch());

    // Check for URL params before loading
    const hasUrlParams = parseUrlAndSearch();

    // Load initial data + territory dropdowns in parallel
    await Promise.all([
        loadStates(),
        loadHeaderStats(),
        loadTerritoryDropdowns(),
        loadQuickStartUnions()
    ]);

    // Default to territory mode unless URL has search params
    if (hasUrlParams) {
        setAppMode('search');
        await applyPendingUrlParams();
    } else {
        setAppMode('territory');
    }

    // Load data freshness footer
    loadFreshnessFooter();

    console.log('=== INIT COMPLETE ===');
    console.log('App mode:', currentAppMode);
    console.log('API_BASE:', API_BASE);
});


async function runDebugCheck() {
    const output = document.getElementById('debugOutput');
    output.classList.remove('hidden');

    let html = '<h3 class="font-bold mb-2">Debug Check</h3>';

    // Check functions
    html += '<div class="mb-2"><strong>Modal Functions:</strong></div>';
    html += `<div>openUnifiedEmployersModal: ${typeof openUnifiedEmployersModal}</div>`;
    html += `<div>openElectionsModal: ${typeof openElectionsModal}</div>`;
    html += `<div>openPublicSectorModal: ${typeof openPublicSectorModal}</div>`;
    html += `<div>openTrendsModal: ${typeof openTrendsModal}</div>`;

    // Check API_BASE
    html += `<div class="mt-2"><strong>API_BASE:</strong> ${API_BASE}</div>`;

    // Check main state filter
    const stateFilter = document.getElementById('stateFilter');
    html += `<div><strong>State Filter Options:</strong> ${stateFilter ? stateFilter.options.length : 'NOT FOUND'}</div>`;

    // Test API
    html += '<div class="mt-2"><strong>API Tests:</strong></div>';
    try {
        const r1 = await fetch(`${API_BASE}/health`);
        const d1 = await r1.json();
        html += `<div style="color:green">✓ Health: ${d1.status}</div>`;
    } catch(e) {
        html += `<div style="color:red">✗ Health: ${e.message}</div>`;
    }

    try {
        const r2 = await fetch(`${API_BASE}/employers/unified/search?limit=2`);
        const d2 = await r2.json();
        html += `<div style="color:green">✓ Unified: ${d2.total} total</div>`;
    } catch(e) {
        html += `<div style="color:red">✗ Unified: ${e.message}</div>`;
    }

    try {
        const r3 = await fetch(`${API_BASE}/nlrb/elections/search?limit=2`);
        const d3 = await r3.json();
        html += `<div style="color:green">✓ Elections: ${d3.total} total</div>`;
    } catch(e) {
        html += `<div style="color:red">✗ Elections: ${e.message}</div>`;
    }

    // Check modal elements
    html += '<div class="mt-2"><strong>Modal Elements:</strong></div>';
    html += `<div>unifiedEmployersModal: ${document.getElementById('unifiedEmployersModal') ? 'EXISTS' : 'MISSING'}</div>`;
    html += `<div>electionsModal: ${document.getElementById('electionsModal') ? 'EXISTS' : 'MISSING'}</div>`;
    html += `<div>publicSectorModal: ${document.getElementById('publicSectorModal') ? 'EXISTS' : 'MISSING'}</div>`;
    html += `<div>trendsModal: ${document.getElementById('trendsModal') ? 'EXISTS' : 'MISSING'}</div>`;

    output.innerHTML = html;
}


async function adminRefreshScorecard() {
    const btn = document.getElementById('adminRefreshBtn');
    const status = document.getElementById('adminRefreshStatus');
    if (btn) btn.disabled = true;
    if (status) status.textContent = 'Refreshing...';
    try {
        const resp = await fetch(`${API_BASE}/admin/refresh-scorecard`, { method: 'POST' });
        if (resp.ok) {
            const data = await resp.json();
            if (status) status.textContent = 'Done! ' + (data.message || '');
        } else {
            if (status) status.textContent = 'Error: ' + resp.status;
        }
    } catch (e) {
        if (status) status.textContent = 'Failed: ' + e.message;
    }
    if (btn) btn.disabled = false;
}

function setupKeyboardShortcuts() {
    // Enter to search in main input
    document.getElementById('mainSearch').addEventListener('keydown', (e) => {
        if (e.key === 'Enter') {
            e.preventDefault();
            currentPage = 1;
            executeSearch();
        }
    });
    
    // Enter to search in industry input (when dropdown closed)
    document.getElementById('industrySearch').addEventListener('keydown', (e) => {
        if (e.key === 'Enter' && !document.getElementById('industryTypeahead').classList.contains('open')) {
            e.preventDefault();
            currentPage = 1;
            executeSearch();
        }
    });
}

// ==========================================
// LOAD INITIAL DATA
// ==========================================
async function loadStates() {
    try {
        const response = await fetch(`${API_BASE}/lookups/states`);
        const data = await response.json();
        const stateSelect = document.getElementById('stateFilter');
        
        // Clear existing options except "All States"
        stateSelect.innerHTML = '<option value="">All States</option>';
        
        // Sort by state abbreviation
        const states = data.states.sort((a, b) => a.state.localeCompare(b.state));
        
        states.forEach(s => {
            const option = document.createElement('option');
            option.value = s.state;
            option.textContent = `${s.state} (${formatNumber(s.employer_count)})`;
            stateSelect.appendChild(option);
        });
    } catch (e) {
        console.error('Failed to load states:', e);
    }
}

async function loadHeaderStats() {
    try {
        const response = await fetch(`${API_BASE}/summary`);
        const data = await response.json();

        const workers = data.employers?.covered_workers || 0;
        const employers = data.employers?.total_employers || 0;
        const unions = data.unions?.total_unions || 0;

        document.getElementById('headerWorkers').textContent = formatNumber(workers);
        document.getElementById('headerEmployers').textContent = formatNumber(employers);
        document.getElementById('headerUnions').textContent = formatNumber(unions);

        // Welcome screen stats
        const ww = document.getElementById('welcomeWorkers');
        if (ww) ww.textContent = formatNumber(workers);
        const we = document.getElementById('welcomeEmployers');
        if (we) we.textContent = formatNumber(employers);
        const wu = document.getElementById('welcomeUnions');
        if (wu) wu.textContent = formatNumber(unions);
    } catch (e) {
        console.error('Failed to load header stats:', e);
    }
}

// ==========================================
// GEOGRAPHIC CASCADE
// ==========================================
function setupGeoChangeListeners() {
    document.getElementById('similarGeoLevel').addEventListener('change', (e) => {
        const radiusInput = document.getElementById('similarRadius');
        const radiusLabel = document.getElementById('similarRadiusLabel');
        if (e.target.value === 'radius') {
            radiusInput.classList.remove('hidden');
            radiusInput.disabled = false;
            radiusLabel.classList.remove('hidden');
        } else {
            radiusInput.classList.add('hidden');
            radiusInput.disabled = true;
            radiusLabel.classList.add('hidden');
        }
    });
}

async function onStateChange() {
    const state = document.getElementById('stateFilter').value;
    const metroSelect = document.getElementById('metroFilter');
    const citySelect = document.getElementById('cityFilter');
    
    // Reset dependent dropdowns
    metroSelect.innerHTML = '<option value="">All Metros</option>';
    citySelect.innerHTML = '<option value="">All Cities</option>';
    
    if (!state) {
        metroSelect.disabled = true;
        citySelect.disabled = true;
        return;
    }
    
    // Load metros for state
    metroSelect.disabled = false;
    citySelect.disabled = false;
    
    try {
        const response = await fetch(`${API_BASE}/lookups/metros?state=${state}`);
        const data = await response.json();
        
        if (data.metros && data.metros.length > 0) {
            data.metros.forEach(metro => {
                const option = document.createElement('option');
                option.value = metro.cbsa_code;
                option.textContent = `${metro.cbsa_title} (${formatNumber(metro.employer_count)})`;
                metroSelect.appendChild(option);
            });
        }
    } catch (e) {
        console.log('Metro loading failed:', e);
    }
    
    // Also load cities for state
    try {
        const response = await fetch(`${API_BASE}/lookups/cities?state=${state}`);
        const data = await response.json();
        
        if (data.cities && data.cities.length > 0) {
            data.cities.forEach(c => {
                const option = document.createElement('option');
                option.value = c.city;
                option.textContent = `${c.city} (${formatNumber(c.employer_count)})`;
                citySelect.appendChild(option);
            });
        }
    } catch (e) {
        console.log('City loading failed:', e);
    }
}

async function onMetroChange() {
    const metro = document.getElementById('metroFilter').value;
    const citySelect = document.getElementById('cityFilter');
    
    citySelect.innerHTML = '<option value="">All Cities</option>';
    
    if (!metro) {
        // Metro cleared, reload all cities for state
        const state = document.getElementById('stateFilter').value;
        if (state) {
            await loadCitiesForState(state);
        }
        return;
    }
    
    // Load cities for this metro
    try {
        const response = await fetch(`${API_BASE}/lookups/cities?cbsa=${metro}`);
        const data = await response.json();
        
        if (data.cities && data.cities.length > 0) {
            data.cities.forEach(c => {
                const option = document.createElement('option');
                option.value = c.city;
                option.textContent = `${c.city} (${formatNumber(c.employer_count)})`;
                citySelect.appendChild(option);
            });
        }
    } catch (e) {
        console.log('City loading for metro failed:', e);
    }
}

async function loadCitiesForState(state) {
    const citySelect = document.getElementById('cityFilter');
    try {
        const response = await fetch(`${API_BASE}/lookups/cities?state=${state}`);
        const data = await response.json();
        
        citySelect.innerHTML = '<option value="">All Cities</option>';
        if (data.cities && data.cities.length > 0) {
            data.cities.forEach(c => {
                const option = document.createElement('option');
                option.value = c.city;
                option.textContent = `${c.city} (${formatNumber(c.employer_count)})`;
                citySelect.appendChild(option);
            });
        }
    } catch (e) {
        console.log('City loading failed:', e);
    }
}

function copyShareLink() {
    const url = getShareableUrl();
    navigator.clipboard.writeText(url).then(() => {
        const btn = document.getElementById('shareBtnText');
        const original = btn.textContent;
        btn.textContent = 'Copied!';
        setTimeout(() => { btn.textContent = original; }, 2000);
    }).catch(() => {
        // Fallback for browsers that don't support clipboard API
        prompt('Copy this link:', url);
    });
}

function exportResults() {
    if (!currentResults || currentResults.length === 0) {
        alert('No results to export');
        return;
    }
    
    let csv = '';
    let filename = '';
    
    if (currentMode === 'employers') {
        // Employer columns
        const headers = [
            'Employer ID', 'Employer Name', 'City', 'State', 'NAICS', 'Industry',
            'Workers', 'Union', 'Local Number', 'Latitude', 'Longitude',
            'Latest Notice Date', 'OSHA Establishment ID'
        ];
        csv = headers.join(',') + '\n';
        
        currentResults.forEach(r => {
            const row = [
                r.employer_id || '',
                csvEscape(r.employer_name || ''),
                csvEscape(r.city || ''),
                r.state || '',
                r.naics || '',
                csvEscape(r.naics_sector_name || ''),
                r.latest_unit_size || '',
                csvEscape(r.latest_union_name || ''),
                r.local_number || '',
                r.latitude || '',
                r.longitude || '',
                r.latest_notice_date || '',
                r.osha_estab_id || ''
            ];
            csv += row.join(',') + '\n';
        });
        
        filename = `employers_export_${new Date().toISOString().slice(0,10)}.csv`;
    } else {
        // Union columns
        const headers = [
            'F-Number', 'Union Name', 'Affiliation', 'Local Number', 'Designation',
            'City', 'State', 'Sector', 'Members', 'Employer Count', 'Workers Covered',
            'Latitude', 'Longitude'
        ];
        csv = headers.join(',') + '\n';
        
        currentResults.forEach(r => {
            const row = [
                r.f_num || '',
                csvEscape(r.union_name || ''),
                r.aff_abbr || '',
                r.local_number || '',
                csvEscape(r.desig_name || ''),
                csvEscape(r.city || ''),
                r.state || '',
                r.sector || '',
                r.members || '',
                r.f7_employer_count || '',
                r.f7_total_workers || '',
                r.latitude || '',
                r.longitude || ''
            ];
            csv += row.join(',') + '\n';
        });
        
        filename = `unions_export_${new Date().toISOString().slice(0,10)}.csv`;
    }
    
    // Download
    downloadCSV(csv, filename);
}

function printReport() {
    if (!selectedItem) {
        alert('No item selected');
        return;
    }
    
    // Create a print-friendly version
    const printWindow = window.open('', '_blank');
    const name = currentMode === 'employers' 
        ? selectedItem.employer_name 
        : selectedItem.union_name;
    const location = `${selectedItem.city || ''}, ${selectedItem.state || ''}`;
    const date = new Date().toLocaleDateString();
    
    let content = '';
    
    if (currentMode === 'employers') {
        content = `
            <h1 style="margin:0; font-size: 24px;">${escapeHtml(name)}</h1>
            <p style="color: #666; margin: 5px 0 20px;">${escapeHtml(location)}</p>
            
            <table style="width: 100%; border-collapse: collapse; margin-bottom: 20px;">
                <tr>
                    <td style="padding: 10px; border: 1px solid #ddd; width: 33%;"><strong>Workers</strong><br>${formatNumber(selectedItem.latest_unit_size || 0)}</td>
                    <td style="padding: 10px; border: 1px solid #ddd; width: 33%;"><strong>Industry</strong><br>${escapeHtml(selectedItem.naics_sector_name || 'N/A')}</td>
                    <td style="padding: 10px; border: 1px solid #ddd; width: 33%;"><strong>NAICS</strong><br>${selectedItem.naics || 'N/A'}</td>
                </tr>
                <tr>
                    <td style="padding: 10px; border: 1px solid #ddd;"><strong>Union</strong><br>${escapeHtml(selectedItem.latest_union_name || 'N/A')}</td>
                    <td style="padding: 10px; border: 1px solid #ddd;"><strong>Latest Notice</strong><br>${selectedItem.latest_notice_date || 'N/A'}</td>
                    <td style="padding: 10px; border: 1px solid #ddd;"><strong>F-7 ID</strong><br>${selectedItem.employer_id || 'N/A'}</td>
                </tr>
            </table>
        `;
    } else {
        content = `
            <h1 style="margin:0; font-size: 24px;">${escapeHtml(name)}</h1>
            <p style="color: #666; margin: 5px 0;">${selectedItem.local_number ? 'Local ' + selectedItem.local_number : ''}</p>
            <p style="color: #666; margin: 5px 0 20px;">${escapeHtml(location)}</p>
            
            <table style="width: 100%; border-collapse: collapse; margin-bottom: 20px;">
                <tr>
                    <td style="padding: 10px; border: 1px solid #ddd; width: 33%;"><strong>Members</strong><br>${formatNumber(selectedItem.members || 0)}</td>
                    <td style="padding: 10px; border: 1px solid #ddd; width: 33%;"><strong>Affiliation</strong><br>${selectedItem.aff_abbr || 'Independent'}</td>
                    <td style="padding: 10px; border: 1px solid #ddd; width: 33%;"><strong>Sector</strong><br>${formatSectorName(selectedItem.sector)}</td>
                </tr>
                <tr>
                    <td style="padding: 10px; border: 1px solid #ddd;"><strong>Employers</strong><br>${formatNumber(selectedItem.f7_employer_count || 0)}</td>
                    <td style="padding: 10px; border: 1px solid #ddd;"><strong>Workers Covered</strong><br>${formatNumber(selectedItem.f7_total_workers || 0)}</td>
                    <td style="padding: 10px; border: 1px solid #ddd;"><strong>F-Number</strong><br>${selectedItem.f_num || 'N/A'}</td>
                </tr>
            </table>
        `;
    }
    
    printWindow.document.write(`
        <!DOCTYPE html>
        <html>
        <head>
            <title>${escapeHtml(name)} - Labor Relations Report</title>
            <style>
                body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; padding: 40px; max-width: 800px; margin: 0 auto; }
                h1 { color: #1a1a1a; }
                table { font-size: 14px; }
                .footer { margin-top: 40px; padding-top: 20px; border-top: 1px solid #ddd; font-size: 12px; color: #666; }
            </style>
        </head>
        <body>
            ${content}
            <div class="footer">
                <p>Generated from Labor Relations Research Platform on ${date}</p>
                <p>Data sources: DOL OLMS, OSHA, NLRB, BLS</p>
            </div>
        </body>
        </html>
    `);
    
    printWindow.document.close();
    printWindow.focus();
    setTimeout(() => printWindow.print(), 250);
}

function toggleStats() {
    const expanded = document.getElementById('statsExpanded');
    const toggleText = document.getElementById('statsToggleText');
    const toggleIcon = document.getElementById('statsToggleIcon');
    
    expanded.classList.toggle('open');
    
    if (expanded.classList.contains('open')) {
        toggleText.textContent = 'Hide breakdown';
        toggleIcon.style.transform = 'rotate(180deg)';
    } else {
        toggleText.textContent = 'Show breakdown';
        toggleIcon.style.transform = 'rotate(0deg)';
    }
}

// Close modal on backdrop click
document.getElementById('findSimilarModal').addEventListener('click', (e) => {
    if (e.target.id === 'findSimilarModal') closeFindSimilar();
});

// Close modal on Escape
document.addEventListener('keydown', (e) => {
    // Escape closes modals
    if (e.key === 'Escape') {
        closeFindSimilar();
        closeNationalDashboard();
        closeNationalBrowser();
        closeOrganizingScorecard();
        closeComparison();
        closeAnalyticsDashboard();
        closeCorporateFamily();
        closeFreshnessModal();
        if (typeof closeGlossary === 'function') closeGlossary();
        return;
    }
    
    // Don't handle if typing in input
    if (e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA') return;
    
    // Arrow keys for list navigation
    if (e.key === 'ArrowDown' || e.key === 'ArrowUp') {
        e.preventDefault();
        navigateList(e.key === 'ArrowDown' ? 1 : -1);
    }
    
    // Enter to select focused item
    if (e.key === 'Enter' && currentResults.length > 0) {
        const focused = document.querySelector('.list-item.keyboard-focus');
        if (focused) {
            focused.click();
        }
    }
    
    // Slash to focus search
    if (e.key === '/' && !e.ctrlKey && !e.metaKey) {
        e.preventDefault();
        document.getElementById('mainSearch').focus();
    }
});

let keyboardFocusIndex = -1;

function navigateList(direction) {
    if (currentResults.length === 0) return;
    
    // Remove previous focus
    document.querySelectorAll('.list-item.keyboard-focus').forEach(el => {
        el.classList.remove('keyboard-focus');
    });
    
    // Calculate new index
    keyboardFocusIndex += direction;
    if (keyboardFocusIndex < 0) keyboardFocusIndex = 0;
    if (keyboardFocusIndex >= currentResults.length) keyboardFocusIndex = currentResults.length - 1;
    
    // Apply focus
    const items = document.querySelectorAll('.list-item');
    if (items[keyboardFocusIndex]) {
        items[keyboardFocusIndex].classList.add('keyboard-focus');
        items[keyboardFocusIndex].scrollIntoView({ block: 'nearest', behavior: 'smooth' });
    }
}

// Reset keyboard focus when results change
function resetKeyboardFocus() {
    keyboardFocusIndex = -1;
    document.querySelectorAll('.list-item.keyboard-focus').forEach(el => {
        el.classList.remove('keyboard-focus');
    });
}

// ==========================================
// URL DEEP LINKING
// ==========================================
function updateUrl() {
    const params = new URLSearchParams();
    
    // Mode
    params.set('mode', currentMode);
    
    // Search query
    const q = document.getElementById('mainSearch').value.trim();
    if (q) params.set('q', q);
    
    // Industry
    const industry = document.getElementById('industrySearch').value.trim();
    if (industry) params.set('industry', industry);
    
    // Geography
    const state = document.getElementById('stateFilter').value;
    if (state) params.set('state', state);
    
    const metro = document.getElementById('metroFilter')?.value;
    if (metro) params.set('cbsa', metro);

    const city = document.getElementById('cityFilter')?.value;
    if (city) params.set('city', city);
    
    // Sector filter (for unions)
    const sector = document.getElementById('sectorFilter')?.value;
    if (sector) params.set('sector', sector);
    
    // Affiliation filter (for unions)
    const aff = document.getElementById('affiliationFilter')?.value;
    if (aff) params.set('aff', aff);
    
    // Update URL without reload
    const newUrl = params.toString() ? `?${params.toString()}` : window.location.pathname;
    history.replaceState(null, '', newUrl);
}

function parseUrlAndSearch() {
    const params = new URLSearchParams(window.location.search);
    
    if (params.size === 0) return false;
    
    // Mode
    const mode = params.get('mode');
    if (mode === 'unions' || mode === 'employers') {
        setSearchMode(mode);
    }
    
    // Search query
    const q = params.get('q');
    if (q) document.getElementById('mainSearch').value = q;
    
    // Industry
    const industry = params.get('industry');
    if (industry) document.getElementById('industrySearch').value = industry;
    
    // State - need to wait for states to load
    const state = params.get('state');
    const cbsa = params.get('cbsa');
    const city = params.get('city');
    const sector = params.get('sector');
    const aff = params.get('aff');

    // Store for later application after data loads
    window.pendingUrlParams = { state, cbsa, city, sector, aff };
    
    return true;
}

async function applyPendingUrlParams() {
    const p = window.pendingUrlParams;
    if (!p) return;
    
    if (p.state) {
        document.getElementById('stateFilter').value = p.state;
        await onStateChange();  // This loads metros and cities for the state
    }

    if (p.cbsa) document.getElementById('metroFilter').value = p.cbsa;
    if (p.city) document.getElementById('cityFilter').value = p.city;
    if (p.sector && document.getElementById('sectorFilter')) {
        document.getElementById('sectorFilter').value = p.sector;
    }
    if (p.aff && document.getElementById('affiliationFilter')) {
        document.getElementById('affiliationFilter').value = p.aff;
    }
    
    window.pendingUrlParams = null;
    
    // Execute search if we have any filters
    if (document.getElementById('mainSearch').value || 
        document.getElementById('industrySearch').value ||
        p.state) {
        executeSearch();
    }
}

function getShareableUrl() {
    updateUrl();
    return window.location.href;
}


// ==========================================
// DATA FRESHNESS
// ==========================================
let freshnessData = null;

async function loadFreshnessFooter() {
    try {
        const response = await fetch(`${API_BASE}/admin/data-freshness`);
        if (!response.ok) return;
        freshnessData = await response.json();

        const footer = document.getElementById('freshnessFooter');
        const text = document.getElementById('freshnessFooterText');

        if (freshnessData.sources && freshnessData.sources.length > 0) {
            const totalFormatted = formatNumber(freshnessData.total_records);
            const oldestDate = freshnessData.oldest_update
                ? new Date(freshnessData.oldest_update).toLocaleDateString()
                : 'unknown';
            text.textContent = `${freshnessData.source_count} data sources | ${totalFormatted} total records | Last refresh: ${oldestDate}`;
            footer.classList.remove('hidden');
        }
    } catch (e) {
        // Silently fail -- freshness is informational
        console.log('Freshness footer not available:', e.message);
    }
}

function openFreshnessModal() {
    const modal = document.getElementById('freshnessModal');
    modal.classList.remove('hidden');
    modal.classList.add('flex');
    document.body.classList.add('modal-open');

    const content = document.getElementById('freshnessModalContent');
    if (!freshnessData || !freshnessData.sources) {
        content.innerHTML = '<p class="text-warmgray-500">No freshness data available. Run the freshness script first.</p>';
        return;
    }

    content.innerHTML = `
        <div class="mb-4 flex gap-4 text-sm">
            <div class="bg-warmgray-100 rounded-lg px-4 py-2">
                <div class="text-warmgray-500">Sources</div>
                <div class="font-bold text-warmgray-900">${freshnessData.source_count}</div>
            </div>
            <div class="bg-warmgray-100 rounded-lg px-4 py-2">
                <div class="text-warmgray-500">Total Records</div>
                <div class="font-bold text-warmgray-900">${formatNumber(freshnessData.total_records)}</div>
            </div>
        </div>
        <table class="w-full text-sm border-collapse">
            <thead>
                <tr class="border-b border-warmgray-200 text-left text-xs text-warmgray-500 uppercase">
                    <th class="py-2 pr-4">Source</th>
                    <th class="py-2 pr-4 text-right">Records</th>
                    <th class="py-2 pr-4">Date Range</th>
                    <th class="py-2">Last Updated</th>
                </tr>
            </thead>
            <tbody>
                ${freshnessData.sources.map(s => {
                    const dateRange = s.date_range_start
                        ? `${s.date_range_start} to ${s.date_range_end}`
                        : '--';
                    const updated = s.last_updated
                        ? new Date(s.last_updated).toLocaleDateString()
                        : '--';
                    return `
                        <tr class="border-b border-warmgray-100 hover:bg-warmgray-50">
                            <td class="py-2 pr-4">
                                <div class="font-medium text-warmgray-800">${escapeHtml(s.display_name)}</div>
                                <div class="text-xs text-warmgray-400">${escapeHtml(s.notes || '')}</div>
                            </td>
                            <td class="py-2 pr-4 text-right font-semibold text-warmgray-700">${formatNumber(s.record_count || 0)}</td>
                            <td class="py-2 pr-4 text-warmgray-500">${dateRange}</td>
                            <td class="py-2 text-warmgray-500">${updated}</td>
                        </tr>
                    `;
                }).join('')}
            </tbody>
        </table>
    `;
}

function closeFreshnessModal() {
    const modal = document.getElementById('freshnessModal');
    modal.classList.add('hidden');
    modal.classList.remove('flex');
    document.body.classList.remove('modal-open');
}

