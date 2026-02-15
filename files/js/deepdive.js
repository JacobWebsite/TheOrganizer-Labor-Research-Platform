// deepdive.js — Deep dive mode functions
// Extracted from organizer_v5.html lines 3108-3457

// ==========================================
// DEEP DIVE: EMPLOYER PROFILE
// ==========================================
let deepDiveData = {};

async function loadDeepDiveData(employerId) {
    const content = document.getElementById('deepDiveContent');
    content.innerHTML = `
        <div class="space-y-4">
            <div class="bg-white rounded-xl border border-warmgray-200 p-6"><div class="skeleton h-20"></div></div>
            <div class="grid grid-cols-3 gap-4">
                <div class="bg-white rounded-xl border border-warmgray-200 p-4"><div class="skeleton h-16"></div></div>
                <div class="bg-white rounded-xl border border-warmgray-200 p-4"><div class="skeleton h-16"></div></div>
                <div class="bg-white rounded-xl border border-warmgray-200 p-4"><div class="skeleton h-16"></div></div>
            </div>
            <div class="grid grid-cols-2 gap-4">
                <div class="bg-white rounded-xl border border-warmgray-200 p-4"><div class="skeleton h-48"></div></div>
                <div class="bg-white rounded-xl border border-warmgray-200 p-4"><div class="skeleton h-48"></div></div>
            </div>
        </div>
    `;

    try {
        // Parallel fetches
        const [scorecardResp, siblingsResp, electionsResp] = await Promise.all([
            fetch(`${API_BASE}/organizing/scorecard/${employerId}`)
                .then(r => r.ok ? r.json() : null).catch(() => null),
            fetch(`${API_BASE}/organizing/siblings/${employerId}?limit=10`)
                .then(r => r.ok ? r.json() : null).catch(() => null),
            // We'll search elections by the employer name after we get it
            Promise.resolve(null)
        ]);

        if (!scorecardResp) {
            content.innerHTML = '<div class="text-center py-12 text-warmgray-400">Employer not found or scorecard unavailable.</div>';
            return;
        }

        deepDiveData = { scorecard: scorecardResp, siblings: siblingsResp };

        const est = scorecardResp.establishment || {};
        const score = scorecardResp.organizing_score || 0;
        const breakdown = scorecardResp.score_breakdown || {};
        const osha = scorecardResp.osha_context || {};
        const geo = scorecardResp.geographic_context || {};
        const contracts = scorecardResp.contracts || {};
        const nlrb = scorecardResp.nlrb_context || {};
        const ctx = scorecardResp.context || {};
        const tier = score >= 30 ? 'TOP' : score >= 25 ? 'HIGH' : score >= 20 ? 'MEDIUM' : 'LOW';
        const tierColor = tier === 'TOP' ? 'bg-green-100 text-green-800' : tier === 'HIGH' ? 'bg-blue-100 text-blue-800' : tier === 'MEDIUM' ? 'bg-yellow-100 text-yellow-800' : 'bg-warmgray-100 text-warmgray-600';

        // Fetch elections by name (now that we have the name)
        const elName = (est.estab_name || '').split(/\s+/).slice(0, 3).join(' ');
        let electionsData = null;
        if (elName) {
            try {
                const elResp = await fetch(`${API_BASE}/nlrb/elections/search?employer_name=${encodeURIComponent(elName)}&limit=10`);
                if (elResp.ok) electionsData = await elResp.json();
            } catch(e) {}
        }

        renderDeepDive(est, score, tier, tierColor, breakdown, osha, geo, contracts, nlrb, ctx, siblingsResp, electionsData);

    } catch (e) {
        console.error('Deep dive load failed:', e);
        content.innerHTML = '<div class="text-center py-12 text-red-500">Failed to load employer profile.</div>';
    }
}

function renderDeepDive(est, score, tier, tierColor, breakdown, osha, geo, contracts, nlrb, ctx, siblings, elections) {
    const content = document.getElementById('deepDiveContent');

    // Use canonical scoring factors from config.js
    const scoreFactors = SCORE_FACTORS;

    content.innerHTML = `
        <!-- Header -->
        <div class="bg-white rounded-xl border border-warmgray-200 p-6 mb-4">
            <div class="flex justify-between items-start">
                <div>
                    <h2 class="headline text-2xl font-bold text-warmgray-900">${escapeHtml(est.estab_name || 'Unknown')}</h2>
                    <p class="text-warmgray-500 mt-1">
                        ${escapeHtml(est.site_address || '')}${est.site_address ? ', ' : ''}${escapeHtml(est.site_city || '')}, ${escapeHtml(est.site_state || '')} ${escapeHtml(est.site_zip || '')}
                    </p>
                    <div class="flex gap-2 mt-3">
                        ${est.naics_code ? `<span class="badge badge-industry">NAICS ${est.naics_code}</span>` : ''}
                        <span class="badge ${est.risk_level === 'HIGH' ? 'bg-red-100 text-red-700' : est.risk_level === 'MODERATE' ? 'bg-yellow-100 text-yellow-700' : 'bg-green-100 text-green-700'}">${est.risk_level || 'N/A'} Risk</span>
                        ${geo.is_rtw_state ? '<span class="badge bg-orange-100 text-orange-700">Right-to-Work State</span>' : ''}
                        ${ctx.has_related_union ? '<span class="badge bg-purple-100 text-purple-700">Has Related Unions</span>' : ''}
                    </div>
                </div>
                <div class="text-right">
                    <div class="text-sm text-warmgray-500 uppercase font-semibold">Organizing Score</div>
                    <div class="text-4xl font-bold mt-1" style="color: ${score >= 30 ? '#16a34a' : score >= 25 ? '#2563eb' : score >= 20 ? '#ca8a04' : '#7d7770'}">${score}</div>
                    <span class="badge ${tierColor} mt-1 inline-block">${tier}</span>
                    <div class="mt-3">
                        <button onclick="exportEmployerReport()" class="px-3 py-1.5 bg-warmgray-100 hover:bg-warmgray-200 text-warmgray-700 text-xs font-medium rounded-lg transition-colors inline-flex items-center gap-1">
                            <svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M17 17h2a2 2 0 002-2v-4a2 2 0 00-2-2H5a2 2 0 00-2 2v4a2 2 0 002 2h2m2 4h6a2 2 0 002-2v-4a2 2 0 00-2-2H9a2 2 0 00-2 2v4a2 2 0 002 2zm8-12V5a2 2 0 00-2-2H9a2 2 0 00-2 2v4h10z"/></svg>
                            Print Report
                        </button>
                    </div>
                </div>
            </div>
        </div>

        <!-- KPI Row -->
        <div class="grid grid-cols-5 gap-4 mb-4">
            <div class="territory-kpi text-center">
                <div class="text-xs font-semibold text-warmgray-500 uppercase">Employees</div>
                <div class="text-2xl font-bold text-warmgray-900 mt-1">${formatNumber(est.employee_count || 0)}</div>
            </div>
            <div class="territory-kpi text-center">
                <div class="text-xs font-semibold text-warmgray-500 uppercase">OSHA Violations</div>
                <div class="text-2xl font-bold text-accent-red mt-1">${formatNumber(est.total_violations || 0)}</div>
                <div class="text-xs text-warmgray-400">${osha.industry_ratio ? osha.industry_ratio.toFixed(1) + 'x industry avg' : ''}</div>
            </div>
            <div class="territory-kpi text-center">
                <div class="text-xs font-semibold text-warmgray-500 uppercase">Total Penalties</div>
                <div class="text-2xl font-bold text-warmgray-900 mt-1">$${formatNumber(Math.round(est.total_penalties || 0))}</div>
            </div>
            <div class="territory-kpi text-center">
                <div class="text-xs font-semibold text-warmgray-500 uppercase">Govt Contracts</div>
                <div class="text-2xl font-bold text-warmgray-900 mt-1">${contracts.total_funding ? '$' + formatCompact(contracts.total_funding) : 'None'}</div>
                <div class="text-xs text-warmgray-400">${contracts.federal_contract_count ? contracts.federal_contract_count + ' contracts' : ''}</div>
            </div>
            ${renderDeepDiveDataQuality(breakdown)}
        </div>

        <!-- Score Breakdown + OSHA Detail -->
        <div class="grid grid-cols-2 gap-4 mb-4">
            <!-- Score Breakdown -->
            <div class="bg-white rounded-xl border border-warmgray-200 p-5">
                <div class="text-xs font-semibold text-warmgray-500 uppercase tracking-wide mb-4">Score Breakdown</div>
                <div class="space-y-2.5">
                    ${scoreFactors.map(f => {
                        const val = breakdown[f.key] || 0;
                        const pct = Math.round((val / f.max) * 100);
                        const barColor = pct >= 80 ? '#16a34a' : pct >= 50 ? '#2563eb' : pct >= 25 ? '#ca8a04' : '#d4d0c8';
                        return `
                            <div class="flex items-center gap-3">
                                <div class="w-32 text-sm text-warmgray-600">${f.label}</div>
                                <div class="flex-1 bg-warmgray-100 rounded-full h-2.5">
                                    <div class="score-bar-fill h-2.5 rounded-full" style="width:${pct}%; background:${barColor}"></div>
                                </div>
                                <div class="w-12 text-right text-sm font-semibold">${val}/${f.max}</div>
                            </div>
                        `;
                    }).join('')}
                </div>
            </div>

            <!-- OSHA + Safety Detail -->
            <div class="bg-white rounded-xl border border-warmgray-200 p-5">
                <div class="text-xs font-semibold text-warmgray-500 uppercase tracking-wide mb-4">Safety Record (OSHA)</div>
                <div class="grid grid-cols-2 gap-4 mb-4">
                    <div class="bg-warmgray-50 rounded-lg p-3 text-center">
                        <div class="text-xs text-warmgray-500">Inspections</div>
                        <div class="text-xl font-bold">${est.total_inspections || 0}</div>
                    </div>
                    <div class="bg-warmgray-50 rounded-lg p-3 text-center">
                        <div class="text-xs text-warmgray-500">Last Inspection</div>
                        <div class="text-sm font-semibold mt-1">${est.last_inspection_date || 'N/A'}</div>
                    </div>
                    <div class="bg-warmgray-50 rounded-lg p-3 text-center">
                        <div class="text-xs text-warmgray-500">Serious</div>
                        <div class="text-xl font-bold text-orange-600">${est.serious_count || 0}</div>
                    </div>
                    <div class="bg-warmgray-50 rounded-lg p-3 text-center">
                        <div class="text-xs text-warmgray-500">Willful/Repeat</div>
                        <div class="text-xl font-bold text-red-600">${(est.willful_count || 0) + (est.repeat_count || 0)}</div>
                    </div>
                </div>
                ${est.accident_count || est.fatality_count ? `
                    <div class="border-t border-warmgray-200 pt-3 flex gap-6">
                        <div class="text-sm"><span class="text-warmgray-500">Accidents:</span> <strong>${est.accident_count || 0}</strong></div>
                        <div class="text-sm"><span class="text-warmgray-500">Fatalities:</span> <strong class="text-red-600">${est.fatality_count || 0}</strong></div>
                    </div>
                ` : ''}
                ${osha.industry_ratio ? `
                    <div class="border-t border-warmgray-200 pt-3 mt-3">
                        <div class="text-sm text-warmgray-600">
                            Violation rate is <strong class="${osha.industry_ratio > 2 ? 'text-red-600' : osha.industry_ratio > 1 ? 'text-orange-600' : 'text-green-600'}">${osha.industry_ratio.toFixed(1)}x</strong> the industry average
                        </div>
                    </div>
                ` : ''}
            </div>
        </div>

        <!-- Geographic + NLRB Context -->
        <div class="grid grid-cols-2 gap-4 mb-4">
            <!-- Geographic & Contract Context -->
            <div class="bg-white rounded-xl border border-warmgray-200 p-5">
                <div class="text-xs font-semibold text-warmgray-500 uppercase tracking-wide mb-4">Geographic & Contract Context</div>
                <div class="space-y-3 text-sm">
                    <div class="flex justify-between">
                        <span class="text-warmgray-500">State</span>
                        <span class="font-semibold">${est.site_state || 'N/A'}</span>
                    </div>
                    <div class="flex justify-between">
                        <span class="text-warmgray-500">Right-to-Work</span>
                        <span class="font-semibold ${geo.is_rtw_state ? 'text-orange-600' : 'text-green-600'}">${geo.is_rtw_state ? 'Yes' : 'No'}</span>
                    </div>
                    <div class="flex justify-between">
                        <span class="text-warmgray-500">State NLRB Win Rate</span>
                        <span class="font-semibold">${geo.nlrb_win_rate ? geo.nlrb_win_rate.toFixed(1) + '%' : 'N/A'}</span>
                    </div>
                    ${contracts.federal_funding ? `
                        <div class="border-t border-warmgray-200 pt-3 mt-2">
                            <div class="text-xs font-semibold text-warmgray-500 uppercase mb-2">Federal Contracts</div>
                            <div class="flex justify-between">
                                <span class="text-warmgray-500">Total Obligations</span>
                                <span class="font-semibold">$${formatCompact(contracts.federal_funding)}</span>
                            </div>
                            <div class="flex justify-between mt-1">
                                <span class="text-warmgray-500">Contract Count</span>
                                <span class="font-semibold">${contracts.federal_contract_count || 0}</span>
                            </div>
                        </div>
                    ` : ''}
                    ${contracts.ny_state_funding || contracts.nyc_funding ? `
                        <div class="border-t border-warmgray-200 pt-3 mt-2">
                            <div class="text-xs font-semibold text-warmgray-500 uppercase mb-2">State/Local</div>
                            ${contracts.ny_state_funding ? `<div class="flex justify-between"><span class="text-warmgray-500">NY State</span><span class="font-semibold">$${formatCompact(contracts.ny_state_funding)}</span></div>` : ''}
                            ${contracts.nyc_funding ? `<div class="flex justify-between mt-1"><span class="text-warmgray-500">NYC</span><span class="font-semibold">$${formatCompact(contracts.nyc_funding)}</span></div>` : ''}
                        </div>
                    ` : ''}
                </div>
            </div>

            <!-- NLRB Patterns -->
            <div class="bg-white rounded-xl border border-warmgray-200 p-5">
                <div class="text-xs font-semibold text-warmgray-500 uppercase tracking-wide mb-4">NLRB Success Prediction</div>
                ${nlrb.predicted_win_pct ? `
                    <div class="text-center mb-4">
                        <div class="text-3xl font-bold ${nlrb.predicted_win_pct >= 75 ? 'text-green-600' : nlrb.predicted_win_pct >= 65 ? 'text-blue-600' : 'text-yellow-600'}">${nlrb.predicted_win_pct.toFixed(1)}%</div>
                        <div class="text-xs text-warmgray-500 mt-1">Predicted Election Win Rate</div>
                    </div>
                    <div class="space-y-2 text-sm">
                        <div class="flex justify-between">
                            <span class="text-warmgray-500">State Win Rate</span>
                            <span class="font-semibold">${nlrb.state_win_rate ? nlrb.state_win_rate.toFixed(1) + '%' : 'N/A'}</span>
                        </div>
                        <div class="flex justify-between">
                            <span class="text-warmgray-500">Industry Win Rate</span>
                            <span class="font-semibold">${nlrb.industry_win_rate ? nlrb.industry_win_rate.toFixed(1) + '%' : 'N/A'}</span>
                        </div>
                        <div class="flex justify-between">
                            <span class="text-warmgray-500">Past Elections</span>
                            <span class="font-semibold">${nlrb.direct_case_count || ctx.nlrb_count || 0}</span>
                        </div>
                    </div>
                ` : `
                    <div class="text-sm text-warmgray-400 text-center py-4">
                        ${ctx.nlrb_count ? ctx.nlrb_count + ' past election(s) found' : 'No NLRB prediction data available'}
                    </div>
                `}
            </div>
        </div>

        <!-- Elections History + Sibling Employers -->
        <div class="grid grid-cols-2 gap-4 mb-4">
            <!-- Recent Elections -->
            <div class="bg-white rounded-xl border border-warmgray-200 p-5">
                <div class="text-xs font-semibold text-warmgray-500 uppercase tracking-wide mb-3">NLRB Election History</div>
                <div id="deepDiveElections">${renderDeepDiveElections(elections)}</div>
            </div>

            <!-- Sibling / Similar Unionized Employers -->
            <div class="bg-white rounded-xl border border-warmgray-200 p-5">
                <div class="text-xs font-semibold text-warmgray-500 uppercase tracking-wide mb-3">Similar Unionized Employers</div>
                <div id="deepDiveSiblings">${renderDeepDiveSiblings(siblings)}</div>
            </div>
        </div>
    `;
}

function renderDeepDiveDataQuality(breakdown) {
    const factorCount = SCORE_FACTORS.filter(f => (breakdown[f.key] || 0) > 0).length;
    const total = SCORE_FACTORS.length;
    const level = factorCount >= 7 ? 'HIGH' : factorCount >= 4 ? 'MEDIUM' : 'LOW';
    const levelColor = level === 'HIGH' ? 'text-green-600' : level === 'MEDIUM' ? 'text-yellow-600' : 'text-warmgray-400';
    const badgeColor = level === 'HIGH' ? 'bg-green-50 text-green-700' : level === 'MEDIUM' ? 'bg-yellow-50 text-yellow-700' : 'bg-warmgray-100 text-warmgray-600';
    // OSHA freshness from global freshnessData
    let oshaAge = '';
    if (typeof freshnessData !== 'undefined' && freshnessData?.sources) {
        const osha = freshnessData.sources.find(s => s.source_name === 'osha_inspections');
        if (osha && osha.last_updated) {
            const days = Math.floor((Date.now() - new Date(osha.last_updated).getTime()) / 86400000);
            oshaAge = days <= 30 ? 'Current' : days <= 90 ? days + 'd old' : Math.floor(days / 30) + 'mo old';
        }
    }
    return `
        <div class="territory-kpi text-center">
            <div class="text-xs font-semibold text-warmgray-500 uppercase">Data Quality</div>
            <div class="text-2xl font-bold ${levelColor} mt-1">${factorCount}/${total}</div>
            <div class="text-xs text-warmgray-400">factors with data${oshaAge ? ' &middot; OSHA ' + oshaAge : ''}</div>
        </div>
    `;
}

function renderDeepDiveElections(data) {
    const elections = data?.elections || [];
    if (elections.length === 0) {
        return '<div class="text-warmgray-400 text-sm text-center py-4">No NLRB elections found for this employer</div>';
    }
    return `
        <table class="w-full text-sm">
            <thead>
                <tr class="text-warmgray-500 text-xs uppercase border-b border-warmgray-100">
                    <th class="text-left py-2 font-semibold">Date</th>
                    <th class="text-left py-2 font-semibold">Union</th>
                    <th class="text-center py-2 font-semibold">Voters</th>
                    <th class="text-right py-2 font-semibold">Result</th>
                </tr>
            </thead>
            <tbody>
                ${elections.slice(0, 8).map(e => {
                    const won = e.union_won === true;
                    return `
                        <tr class="border-b border-warmgray-50">
                            <td class="py-2 text-warmgray-500">${e.election_date || '--'}</td>
                            <td class="py-2 text-warmgray-700">${escapeHtml((e.aff_abbr || e.union_name || '').substring(0, 20))}</td>
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

function renderDeepDiveSiblings(data) {
    const siblings = data?.siblings || [];
    if (siblings.length === 0) {
        return '<div class="text-warmgray-400 text-sm text-center py-4">No similar unionized employers found</div>';
    }
    return `
        <table class="w-full text-sm">
            <thead>
                <tr class="text-warmgray-500 text-xs uppercase border-b border-warmgray-100">
                    <th class="text-left py-2 font-semibold">Employer</th>
                    <th class="text-left py-2 font-semibold">Location</th>
                    <th class="text-right py-2 font-semibold">Match</th>
                </tr>
            </thead>
            <tbody>
                ${siblings.slice(0, 8).map(s => `
                    <tr class="border-b border-warmgray-50">
                        <td class="py-2 font-medium text-warmgray-900">${escapeHtml(s.employer_name || '')}</td>
                        <td class="py-2 text-warmgray-500">${escapeHtml((s.city || '') + (s.state ? ', ' + s.state : ''))}</td>
                        <td class="py-2 text-right">
                            <span class="badge ${s.match_score >= 80 ? 'bg-green-50 text-green-700' : 'bg-warmgray-50 text-warmgray-600'}">${s.match_score || 0}%</span>
                        </td>
                    </tr>
                `).join('')}
            </tbody>
        </table>
        ${siblings.length > 0 && siblings[0].match_reasons ? `
            <div class="mt-3 text-xs text-warmgray-400">
                Top match reasons: ${siblings[0].match_reasons.join(', ')}
            </div>
        ` : ''}
    `;
}
