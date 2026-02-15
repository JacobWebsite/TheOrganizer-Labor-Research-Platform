// uniondive.js -- Union Profile (full-page deep dive for a union)

let unionDiveData = {};
let unionDiveReturnMode = 'search';

async function loadUnionDiveData(fNum) {
    const content = document.getElementById('unionDiveContent');
    content.innerHTML = `
        <div class="space-y-4">
            <div class="bg-white rounded-xl border border-warmgray-200 p-6"><div class="skeleton h-20"></div></div>
            <div class="grid grid-cols-4 gap-4">
                <div class="bg-white rounded-xl border border-warmgray-200 p-4"><div class="skeleton h-16"></div></div>
                <div class="bg-white rounded-xl border border-warmgray-200 p-4"><div class="skeleton h-16"></div></div>
                <div class="bg-white rounded-xl border border-warmgray-200 p-4"><div class="skeleton h-16"></div></div>
                <div class="bg-white rounded-xl border border-warmgray-200 p-4"><div class="skeleton h-16"></div></div>
            </div>
        </div>
    `;

    try {
        const resp = await fetch(`${API_BASE}/unions/${fNum}`);
        if (!resp.ok) {
            content.innerHTML = '<div class="text-center py-12 text-warmgray-400">Union not found.</div>';
            return;
        }
        unionDiveData = await resp.json();
        renderUnionDive(unionDiveData);
    } catch (e) {
        console.error('Union dive load failed:', e);
        content.innerHTML = '<div class="text-center py-12 text-red-500">Failed to load union profile.</div>';
    }
}

function renderUnionDive(data) {
    const content = document.getElementById('unionDiveContent');
    const u = data.union || {};
    const employers = data.top_employers || [];
    const elections = data.nlrb_elections || [];
    const nlrb = data.nlrb_summary || {};

    const sectorLabel = formatSectorName ? formatSectorName(u.sector) : (u.sector || 'N/A');

    content.innerHTML = `
        <!-- Header -->
        <div class="bg-white rounded-xl border border-warmgray-200 p-6 mb-4">
            <div class="flex justify-between items-start">
                <div>
                    <h2 class="headline text-2xl font-bold text-warmgray-900">${escapeHtml(u.union_name || 'Unknown Union')}</h2>
                    <p class="text-warmgray-500 mt-1">
                        ${u.aff_abbr ? escapeHtml(u.aff_abbr) + ' &middot; ' : ''}${escapeHtml(u.city || '')}, ${escapeHtml(u.state || '')}
                    </p>
                    <div class="flex gap-2 mt-3">
                        <span class="badge bg-warmgray-100 text-warmgray-700">F-${u.f_num || 'N/A'}</span>
                        <span class="badge bg-blue-50 text-blue-700">${escapeHtml(sectorLabel)}</span>
                        ${u.local_number ? `<span class="badge bg-purple-50 text-purple-700">Local ${escapeHtml(String(u.local_number))}</span>` : ''}
                    </div>
                </div>
                <div class="text-right">
                    <div class="text-sm text-warmgray-500 uppercase font-semibold">Members</div>
                    <div class="text-4xl font-bold text-warmgray-900 mt-1">${formatNumber(u.members || 0)}</div>
                </div>
            </div>
        </div>

        <!-- KPI Row -->
        <div class="grid grid-cols-4 gap-4 mb-4">
            <div class="territory-kpi text-center">
                <div class="text-xs font-semibold text-warmgray-500 uppercase">Members</div>
                <div class="text-2xl font-bold text-warmgray-900 mt-1">${formatNumber(u.members || 0)}</div>
            </div>
            <div class="territory-kpi text-center">
                <div class="text-xs font-semibold text-warmgray-500 uppercase">Employers</div>
                <div class="text-2xl font-bold text-warmgray-900 mt-1">${formatNumber(u.f7_employer_count || 0)}</div>
            </div>
            <div class="territory-kpi text-center">
                <div class="text-xs font-semibold text-warmgray-500 uppercase">Workers Covered</div>
                <div class="text-2xl font-bold text-warmgray-900 mt-1">${formatNumber(u.f7_total_workers || 0)}</div>
            </div>
            <div class="territory-kpi text-center">
                <div class="text-xs font-semibold text-warmgray-500 uppercase">NLRB Win Rate</div>
                <div class="text-2xl font-bold ${(nlrb.win_rate || 0) >= 50 ? 'text-green-600' : 'text-warmgray-900'} mt-1">
                    ${nlrb.total_elections ? (nlrb.win_rate || 0).toFixed(0) + '%' : 'N/A'}
                </div>
                <div class="text-xs text-warmgray-400">${nlrb.total_elections ? nlrb.total_elections + ' elections' : ''}</div>
            </div>
        </div>

        <!-- Employers + Elections -->
        <div class="grid grid-cols-2 gap-4 mb-4">
            <!-- Top Employers -->
            <div class="bg-white rounded-xl border border-warmgray-200 p-5">
                <div class="text-xs font-semibold text-warmgray-500 uppercase tracking-wide mb-3">Top Employers (F-7)</div>
                ${renderUnionEmployers(employers)}
            </div>

            <!-- NLRB Elections -->
            <div class="bg-white rounded-xl border border-warmgray-200 p-5">
                <div class="text-xs font-semibold text-warmgray-500 uppercase tracking-wide mb-3">NLRB Election History</div>
                ${renderUnionElections(elections, nlrb)}
            </div>
        </div>
    `;
}

function renderUnionEmployers(employers) {
    if (!employers || employers.length === 0) {
        return '<div class="text-warmgray-400 text-sm text-center py-4">No F-7 employers found</div>';
    }
    return `
        <table class="w-full text-sm">
            <thead>
                <tr class="text-warmgray-500 text-xs uppercase border-b border-warmgray-100">
                    <th class="text-left py-2 font-semibold">Employer</th>
                    <th class="text-left py-2 font-semibold">Location</th>
                    <th class="text-right py-2 font-semibold">Workers</th>
                </tr>
            </thead>
            <tbody>
                ${employers.slice(0, 15).map(e => `
                    <tr class="border-b border-warmgray-50 cursor-pointer hover:bg-warmgray-50"
                        onclick="openDeepDive('${escapeHtml(e.employer_id || '')}', 'uniondive')">
                        <td class="py-2 font-medium text-warmgray-900">${escapeHtml(e.employer_name || '')}</td>
                        <td class="py-2 text-warmgray-500">${escapeHtml((e.city || '') + (e.state ? ', ' + e.state : ''))}</td>
                        <td class="py-2 text-right font-semibold">${formatNumber(e.latest_unit_size || 0)}</td>
                    </tr>
                `).join('')}
            </tbody>
        </table>
    `;
}

function renderUnionElections(elections, nlrb) {
    if (!elections || elections.length === 0) {
        return '<div class="text-warmgray-400 text-sm text-center py-4">No NLRB elections found</div>';
    }

    const summaryHtml = nlrb.total_elections ? `
        <div class="flex gap-4 mb-3 text-sm">
            <span class="text-green-600 font-semibold">${nlrb.wins || 0} wins</span>
            <span class="text-red-600 font-semibold">${nlrb.losses || 0} losses</span>
            <span class="text-warmgray-500">${(nlrb.win_rate || 0).toFixed(0)}% win rate</span>
        </div>
    ` : '';

    return `
        ${summaryHtml}
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
                            <td class="py-2 text-warmgray-700">${escapeHtml((e.employer_name || '').substring(0, 25))}</td>
                            <td class="py-2 text-center">${e.eligible_voters || '--'}</td>
                            <td class="py-2 text-right">
                                ${e.union_won !== null ? `<span class="badge ${won ? 'bg-green-50 text-green-700' : 'bg-red-50 text-red-700'}">${won ? 'Won' : 'Lost'}</span>` : '<span class="text-warmgray-400">Pending</span>'}
                            </td>
                        </tr>
                    `;
                }).join('')}
            </tbody>
        </table>
    `;
}

function openUnionDive(fNum, returnTo) {
    unionDiveReturnMode = returnTo || currentAppMode;
    document.getElementById('unionDiveBackLabel').textContent =
        unionDiveReturnMode === 'territory' ? 'Back to Territory' : 'Back to Search';
    setAppMode('uniondive');
    loadUnionDiveData(fNum);
}

function returnFromUnionDive() {
    setAppMode(unionDiveReturnMode);
}
