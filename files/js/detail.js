// ==========================================
// detail.js - Employer and Union detail panel
// Extracted from organizer_v5.html lines 5967-7391
// ==========================================

function selectItem(id) {
    const idStr = String(id);
    const item = currentResults.find(r => {
        const itemId = currentMode === 'employers'
            ? String(r.canonical_id || r.employer_id)
            : String(r.f_num);
        return itemId === idStr;
    });
    if (!item) return;

    selectedItem = item;

    // Update list selection
    document.querySelectorAll('.list-item').forEach(el => {
        el.classList.toggle('selected', el.dataset.id === idStr);
    });

    // Show detail content
    document.getElementById('detailEmpty').classList.add('hidden');
    document.getElementById('detailContent').classList.remove('hidden');

    if (currentMode === 'employers') {
        renderEmployerDetail(item);
    } else {
        renderUnionDetail(item);
    }
}

function renderEmployerDetail(item) {
    // Adapt field names for unified vs legacy data
    const empName = item.employer_name || 'Unknown';
    const unionName = item.union_name || item.latest_union_name || item.union_display_name || '';
    const unionFnum = item.union_fnum || item.latest_union_fnum;
    const affAbbr = item.aff_abbr || '';
    const workers = item.unit_size || item.latest_unit_size || 0;
    const canonicalId = item.canonical_id || item.employer_id;
    const srcType = item.source_type || 'F7';

    // Populate detail fields for employer
    document.getElementById('detailName').textContent = empName;
    document.getElementById('detailLocation').textContent = `${item.city || 'Unknown'}, ${item.state || ''} ${item.zip || ''}`.trim();

    // Badges - source type + sector
    const sectorClass = getSectorBadgeClass(item.union_sector);
    const badgesHtml = `
        ${getSourceBadge(srcType)}
        ${item.union_sector ? `<span class="badge ${sectorClass}">${formatSectorName(item.union_sector)}</span>` : ''}
        ${item.naics_sector_name ? `<span class="badge badge-industry">${escapeHtml(item.naics_sector_name)}</span>` : ''}
        ${item.has_union ? '<span class="inline-block px-1.5 py-0.5 text-xs font-semibold bg-green-100 text-green-700 rounded">Union</span>' : ''}
    `;
    document.getElementById('detailBadges').innerHTML = badgesHtml;

    // Key metrics - Employer view
    document.getElementById('detailMetrics').innerHTML = `
        <div class="bg-warmgray-100 rounded-lg p-4">
            <div class="text-xs font-semibold text-warmgray-500 uppercase tracking-wide mb-1">Union</div>
            <div class="font-semibold text-warmgray-900 ${unionFnum ? 'entity-link' : ''}"
                 ${unionFnum ? `onclick="loadUnionDetail('${escapeHtml(String(unionFnum))}')"` : ''}>${escapeHtml(unionName || 'Unknown')}</div>
            <div class="text-sm text-warmgray-500">
                ${affAbbr ? `<span class="entity-link" onclick="openNationalDashboard('${escapeHtml(affAbbr)}')">${escapeHtml(affAbbr)} affiliate</span>` : ''}
            </div>
        </div>
        <div class="bg-warmgray-100 rounded-lg p-4">
            <div class="text-xs font-semibold text-warmgray-500 uppercase tracking-wide mb-1">Workers</div>
            <div class="text-3xl font-bold text-accent-red">${workers > 0 ? formatNumber(workers) : '--'}</div>
        </div>
        <div class="bg-warmgray-100 rounded-lg p-4">
            <div class="text-xs font-semibold text-warmgray-500 uppercase tracking-wide mb-1">Source</div>
            <div class="font-semibold text-warmgray-900">${getSourceLabel(srcType)}</div>
            <div class="text-sm text-warmgray-500">${item.naics ? `NAICS ${escapeHtml(item.naics)}` : ''}</div>
        </div>
    `;

    // Filing history - show only for F7
    if (srcType === 'F7') {
        document.getElementById('detailFilingSection').innerHTML = `
            <div class="text-xs font-semibold text-warmgray-500 uppercase tracking-wide mb-3">Filing Details</div>
            <div class="grid grid-cols-2 gap-4 text-sm">
                <div class="flex justify-between">
                    <span class="text-warmgray-500">Latest F-7 Filing</span>
                    <span class="font-medium">${item.latest_notice_date || '---'}</span>
                </div>
                <div class="flex justify-between">
                    <span class="text-warmgray-500">Union File #</span>
                    <span class="font-medium font-mono text-xs">${unionFnum || '---'}</span>
                </div>
                <div class="flex justify-between">
                    <span class="text-warmgray-500">Healthcare Related</span>
                    <span class="font-medium">${item.healthcare_related ? 'Yes' : 'No'}</span>
                </div>
                <div class="flex justify-between">
                    <span class="text-warmgray-500">Status</span>
                    <span class="font-medium ${item.potentially_defunct ? 'text-orange-600' : 'text-green-600'}">${item.potentially_defunct ? 'Potentially Defunct' : 'Active'}</span>
                </div>
            </div>
        `;
    } else {
        document.getElementById('detailFilingSection').innerHTML = `
            <div class="text-xs font-semibold text-warmgray-500 uppercase tracking-wide mb-3">Record Details</div>
            <div class="grid grid-cols-2 gap-4 text-sm">
                <div class="flex justify-between">
                    <span class="text-warmgray-500">Source</span>
                    <span class="font-medium">${getSourceLabel(srcType)}</span>
                </div>
                <div class="flex justify-between">
                    <span class="text-warmgray-500">ID</span>
                    <span class="font-medium font-mono text-xs">${escapeHtml(canonicalId)}</span>
                </div>
            </div>
        `;
    }

    // BLS Projections - show loading then fetch data
    const naics2 = item.naics ? item.naics.substring(0, 2) : null;
    const naicsDetailed = item.naics_detailed || (item.naics && item.naics.length >= 4 ? item.naics : null);
    document.getElementById('detailProjections').innerHTML = `
        <div class="text-xs font-semibold text-warmgray-500 uppercase tracking-wide mb-3">Industry Outlook</div>
        <div class="bg-warmgray-100 rounded-lg p-4 text-sm">
            <div id="projectionsHeader" class="text-warmgray-600">
                <span>${escapeHtml(item.naics_sector_name || 'Industry')}</span>
                ${item.naics ? `<span class="text-warmgray-400">(NAICS ${item.naics.substring(0,2)})</span>` : ''}
            </div>
            <div id="projectionsData" class="mt-2 text-warmgray-400">Loading projections...</div>
            <div id="occupationsToggle" class="hidden mt-3"></div>
            <div id="occupationsData" class="hidden mt-3"></div>
        </div>
    `;

    // Fetch and display BLS projections
    if (naics2 || naicsDetailed) {
        loadIndustryProjections(naics2, naicsDetailed);
    } else {
        document.getElementById('projectionsData').innerHTML = '<span class="text-warmgray-400">No industry data available</span>';
    }

    // Show employer-specific sections, hide union-specific
    document.getElementById('detailCorporateSection').classList.remove('hidden');
    document.getElementById('detailNewsSection').classList.remove('hidden');
    document.getElementById('detailOshaSection').classList.remove('hidden');
    document.getElementById('detailNlrbSection').classList.remove('hidden');
    document.getElementById('detailEmployersSection').classList.add('hidden');
    document.getElementById('detailFinancialsSection').classList.add('hidden');

    // Source records and flag sections - always show
    document.getElementById('detailSourceSection').classList.remove('hidden');
    document.getElementById('detailFlagSection').classList.remove('hidden');

    // Find Similar button
    const inComparison = isInComparison(item.employer_id || item.canonical_id);
    document.getElementById('detailActionSection').innerHTML = `
        <div class="flex gap-2 mb-2">
            <button onclick="openFindSimilar(selectedItem)"
                class="flex-1 py-3 bg-warmgray-900 text-white font-semibold rounded-lg hover:bg-warmgray-800 transition-colors">
                Find Similar Employers ->
            </button>
            <button onclick="addToComparison(selectedItem)"
                class="px-4 py-3 border-2 ${inComparison ? 'border-accent-red bg-accent-red/10 text-accent-red' : 'border-warmgray-300 text-warmgray-600 hover:border-warmgray-400'} font-semibold rounded-lg transition-colors"
                title="${inComparison ? 'Already in comparison' : 'Add to comparison'}">
                <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z"/>
                </svg>
            </button>
        </div>
        <p class="text-xs text-warmgray-400 text-center">Discover non-union employers in the same industry and geography</p>
    `;

    // Update map
    updateDetailMap(item);

    // Load OSHA, NLRB, and corporate family data
    if (srcType === 'F7') {
        loadEmployerOsha(canonicalId);
        loadEmployerNlrb(canonicalId);
        loadCorporateFamily(canonicalId);
    } else {
        document.getElementById('oshaContent').innerHTML = '<div class="text-sm text-warmgray-400">OSHA data only available for F7 employers</div>';
        document.getElementById('nlrbContent').innerHTML = '<div class="text-sm text-warmgray-400">NLRB data loaded via cross-references below</div>';
        document.getElementById('corporateContent').innerHTML = '<div class="text-sm text-warmgray-400">Corporate family data only available for F7 employers</div>';
    }
    // Load corporate family for Mergent sector targets too
    if (srcType === 'MERGENT' && item.duns) {
        loadCorporateFamily(item.duns);
    }

    // Load unified detail (cross-references + flags)
    loadUnifiedDetail(canonicalId);
}

// ==========================================
// UNIFIED SEARCH HELPERS
// ==========================================
async function loadUnifiedDetail(canonicalId) {
    const srcContent = document.getElementById('sourceRecordsContent');
    const flagsContent = document.getElementById('existingFlags');
    srcContent.innerHTML = '<div class="text-sm text-warmgray-400">Loading cross-references...</div>';
    flagsContent.innerHTML = '';

    try {
        const resp = await fetch(`${API_BASE}/employers/unified-detail/${encodeURIComponent(canonicalId)}`);
        if (!resp.ok) {
            srcContent.innerHTML = '<div class="text-sm text-warmgray-400">No cross-reference data available</div>';
            return;
        }
        const data = await resp.json();

        // Render cross-references
        const xrefs = data.cross_references || [];
        if (xrefs.length === 0) {
            srcContent.innerHTML = '<div class="text-sm text-warmgray-400">No additional source records found</div>';
        } else {
            srcContent.innerHTML = `
                <div class="space-y-2">
                    ${xrefs.map(ref => `
                        <div class="bg-warmgray-50 rounded p-3 text-sm">
                            <div class="flex items-center gap-2 mb-1">
                                ${getSourceBadge(ref.source_type)}
                                <span class="font-medium">${escapeHtml(ref.employer_name || '')}</span>
                                ${ref.election_result ? `<span class="text-xs px-1.5 py-0.5 rounded ${ref.election_result === 'Won' ? 'bg-green-100 text-green-700' : 'bg-red-100 text-red-700'}">${ref.election_result}</span>` : ''}
                            </div>
                            <div class="text-warmgray-500 text-xs flex gap-3">
                                ${ref.case_number ? `<span>Case: ${escapeHtml(ref.case_number)}</span>` : ''}
                                ${ref.election_date ? `<span>Date: ${escapeHtml(ref.election_date)}</span>` : ''}
                                ${ref.unit_size ? `<span>Workers: ${formatNumber(ref.unit_size)}</span>` : ''}
                                ${ref.union_name ? `<span>Union: ${escapeHtml(ref.union_name)}</span>` : ''}
                            </div>
                        </div>
                    `).join('')}
                </div>
            `;
        }

        // Render flags
        renderFlags(data.flags || []);
    } catch (e) {
        console.error('Failed to load unified detail:', e);
        srcContent.innerHTML = '<div class="text-sm text-warmgray-400">Failed to load cross-references</div>';
    }
}

function renderFlags(flags) {
    const container = document.getElementById('existingFlags');
    if (!flags || flags.length === 0) {
        container.innerHTML = '<div class="text-sm text-warmgray-400 mb-2">No flags</div>';
        return;
    }
    container.innerHTML = flags.map(f => `
        <div class="flex items-center justify-between bg-warmgray-50 rounded px-3 py-2 mb-1 text-sm">
            <div>
                <span class="font-medium text-warmgray-700">${escapeHtml(f.flag_type.replace(/_/g, ' '))}</span>
                ${f.notes ? `<span class="text-warmgray-500 ml-2">${escapeHtml(f.notes)}</span>` : ''}
            </div>
            <button onclick="deleteFlag(${f.id})" class="text-warmgray-400 hover:text-red-600 text-lg leading-none" title="Remove flag">&times;</button>
        </div>
    `).join('');
}

async function submitFlag() {
    if (!selectedItem) return;
    const flagType = document.getElementById('flagTypeSelect').value;
    if (!flagType) return;
    const notes = document.getElementById('flagNotesInput').value.trim();
    const canonicalId = selectedItem.canonical_id || selectedItem.employer_id;
    const srcType = selectedItem.source_type || 'F7';

    // Extract source_id from canonical_id
    let sourceId = canonicalId;
    if (canonicalId.startsWith('NLRB-')) sourceId = canonicalId.substring(5);
    else if (canonicalId.startsWith('VR-')) sourceId = canonicalId.substring(3);
    else if (canonicalId.startsWith('MANUAL-')) sourceId = canonicalId.substring(7);

    try {
        const resp = await fetch(`${API_BASE}/employers/flags`, {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({source_type: srcType, source_id: sourceId, flag_type: flagType, notes: notes || null})
        });
        if (resp.ok) {
            document.getElementById('flagTypeSelect').value = '';
            document.getElementById('flagNotesInput').value = '';
            // Reload flags
            loadUnifiedDetail(canonicalId);
        } else {
            const err = await resp.json();
            alert(err.detail || 'Failed to add flag');
        }
    } catch (e) {
        console.error('Flag creation failed:', e);
    }
}

async function deleteFlag(flagId) {
    try {
        const resp = await fetch(`${API_BASE}/employers/flags/${flagId}`, {method: 'DELETE'});
        if (resp.ok && selectedItem) {
            const canonicalId = selectedItem.canonical_id || selectedItem.employer_id;
            loadUnifiedDetail(canonicalId);
        }
    } catch (e) {
        console.error('Flag deletion failed:', e);
    }
}

// ---- Scorecard Flag Functions ----
let currentScorecardFlagSource = null; // {source_type, source_id}

function getScorecardFlagHTML() {
    return `
        <div class="border-t border-warmgray-200 pt-4 mt-6">
            <h4 class="text-sm font-semibold text-warmgray-700 uppercase tracking-wide mb-3">Review Flags</h4>
            <div id="scorecardExistingFlags" class="mb-3"></div>
            <div class="flex gap-2 items-end">
                <select id="scorecardFlagTypeSelect" class="text-sm border border-warmgray-300 rounded px-2 py-1.5 flex-1">
                    <option value="">Flag for review...</option>
                    <option value="ALREADY_UNION">Already Union</option>
                    <option value="DUPLICATE">Duplicate</option>
                    <option value="LABOR_ORG_NOT_EMPLOYER">Labor Org Not Employer</option>
                    <option value="DEFUNCT">Defunct</option>
                    <option value="DATA_QUALITY">Data Quality</option>
                    <option value="NEEDS_REVIEW">Needs Review</option>
                    <option value="VERIFIED_OK">Verified OK</option>
                </select>
                <input id="scorecardFlagNotesInput" type="text" placeholder="Notes (optional)" class="text-sm border border-warmgray-300 rounded px-2 py-1.5 flex-1">
                <button onclick="submitScorecardFlag()" class="px-3 py-1.5 bg-warmgray-700 text-white text-sm rounded hover:bg-warmgray-800">Flag</button>
            </div>
        </div>
    `;
}

function renderScorecardFlags(flags) {
    const container = document.getElementById('scorecardExistingFlags');
    if (!container) return;
    if (!flags || flags.length === 0) {
        container.innerHTML = '<div class="text-sm text-warmgray-400 mb-2">No flags</div>';
        return;
    }
    container.innerHTML = flags.map(f => `
        <div class="flex items-center justify-between bg-warmgray-50 rounded px-3 py-2 mb-1 text-sm">
            <div>
                <span class="font-medium text-warmgray-700">${escapeHtml(f.flag_type.replace(/_/g, ' '))}</span>
                ${f.notes ? `<span class="text-warmgray-500 ml-2">${escapeHtml(f.notes)}</span>` : ''}
            </div>
            <button onclick="deleteScorecardFlag(${f.id})" class="text-warmgray-400 hover:text-red-600 text-lg leading-none" title="Remove flag">&times;</button>
        </div>
    `).join('');
}

async function loadScorecardFlags(sourceType, sourceId) {
    currentScorecardFlagSource = {source_type: sourceType, source_id: String(sourceId)};
    try {
        const resp = await fetch(`${API_BASE}/employers/flags/by-source?source_type=${encodeURIComponent(sourceType)}&source_id=${encodeURIComponent(sourceId)}`);
        if (resp.ok) {
            const data = await resp.json();
            renderScorecardFlags(data.flags || []);
        }
    } catch (e) {
        console.error('Failed to load scorecard flags:', e);
    }
}

async function submitScorecardFlag() {
    if (!currentScorecardFlagSource) return;
    const flagType = document.getElementById('scorecardFlagTypeSelect').value;
    if (!flagType) return;
    const notes = document.getElementById('scorecardFlagNotesInput').value.trim();

    try {
        const resp = await fetch(`${API_BASE}/employers/flags`, {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({
                source_type: currentScorecardFlagSource.source_type,
                source_id: currentScorecardFlagSource.source_id,
                flag_type: flagType,
                notes: notes || null
            })
        });
        if (resp.ok) {
            document.getElementById('scorecardFlagTypeSelect').value = '';
            document.getElementById('scorecardFlagNotesInput').value = '';
            loadScorecardFlags(currentScorecardFlagSource.source_type, currentScorecardFlagSource.source_id);
        } else {
            const err = await resp.json();
            alert(err.detail || 'Failed to add flag');
        }
    } catch (e) {
        console.error('Scorecard flag creation failed:', e);
    }
}

async function deleteScorecardFlag(flagId) {
    try {
        const resp = await fetch(`${API_BASE}/employers/flags/${flagId}`, {method: 'DELETE'});
        if (resp.ok && currentScorecardFlagSource) {
            loadScorecardFlags(currentScorecardFlagSource.source_type, currentScorecardFlagSource.source_id);
        }
    } catch (e) {
        console.error('Scorecard flag deletion failed:', e);
    }
}

// Navigate to union detail from employer view
async function loadUnionDetail(fNum) {
    setSearchMode('unions');
    document.getElementById('mainSearch').value = fNum;
    await executeSearch();
    // Try to select the union from results
    if (currentResults.length > 0) {
        const union = currentResults.find(u => u.f_num === fNum);
        if (union) {
            selectItem(union.f_num);
        }
    }
}

// Store current matrix code for occupation loading
let currentProjectionMatrixCode = null;

async function loadIndustryProjections(naics2digit, naicsDetailed) {
    const el = document.getElementById('projectionsData');
    const headerEl = document.getElementById('projectionsHeader');
    const toggleEl = document.getElementById('occupationsToggle');
    const occupationsEl = document.getElementById('occupationsData');

    currentProjectionMatrixCode = null;
    toggleEl.classList.add('hidden');
    occupationsEl.classList.add('hidden');

    try {
        // Try detailed NAICS first if available
        let data = null;
        let isDetailedProjection = false;

        if (naicsDetailed && naicsDetailed.length >= 4) {
            try {
                const detailedResponse = await fetch(`${API_BASE}/projections/matrix/${naicsDetailed}`);
                if (detailedResponse.ok) {
                    data = await detailedResponse.json();
                    isDetailedProjection = true;
                    currentProjectionMatrixCode = naicsDetailed;
                }
            } catch (e) {
                console.log('Detailed projection not found, falling back to sector');
            }
        }

        // Fall back to sector-level if detailed not available
        if (!data && naics2digit) {
            const response = await fetch(`${API_BASE}/projections/naics/${naics2digit}`);
            if (!response.ok) throw new Error('Failed to load');
            data = await response.json();
        }

        if (!data) throw new Error('No projection data');

        if (isDetailedProjection) {
            // Detailed industry projection - data is nested in projection object
            const proj = data.projection || data;
            const changePct = proj.employment_change_pct || 0;
            const category = proj.growth_category || 'unknown';
            const emp2024 = proj.employment_2024 || 0;
            const emp2034 = proj.employment_2034 || 0;
            const industryTitle = proj.industry_title || data.industry_title || 'Industry';
            const matrixCode = escapeHtml(String(data.matrix_code || ''));

            // Update header with specific industry name
            headerEl.innerHTML = `
                <span class="font-medium">${escapeHtml(industryTitle)}</span>
                <span class="text-warmgray-400">(${matrixCode})</span>
            `;

            // Determine color based on growth category
            let colorClass = 'text-warmgray-600';
            let icon = '';
            if (category === 'fast_growing' || category === 'growing') {
                colorClass = 'text-green-600';
                icon = '\u2191';
            } else if (category === 'declining' || category === 'fast_declining') {
                colorClass = 'text-red-600';
                icon = '\u2193';
            } else {
                icon = '\u2192';
            }

            el.innerHTML = `
                <div class="flex items-center gap-2">
                    <span class="text-lg font-bold ${colorClass}">${icon} ${changePct > 0 ? '+' : ''}${changePct.toFixed(1)}%</span>
                    <span class="text-warmgray-500">projected growth (2024-2034)</span>
                </div>
                <div class="text-xs text-warmgray-400 mt-1">
                    ${formatNumber(emp2024)}K \u2192 ${formatNumber(emp2034)}K jobs nationwide
                </div>
            `;

            // Show occupation toggle if we have a matrix code
            if (currentProjectionMatrixCode && data.occupation_count > 0) {
                const occupationCount = Number(data.occupation_count) || 0;
                toggleEl.classList.remove('hidden');
                toggleEl.innerHTML = `
                    <button onclick="toggleOccupations()" class="flex items-center gap-1 text-xs text-accent-blue hover:text-accent-blue/80 transition-colors">
                        <span id="occupationsToggleIcon">\u25BC</span>
                        <span id="occupationsToggleText">Show Top Occupations</span>
                        <span class="text-warmgray-400">(${occupationCount} jobs)</span>
                    </button>
                `;
            }
        } else {
            // Sector-level projection (fallback)
            const summary = data.summary || {};
            const changePct = summary.avg_change_pct || 0;
            const category = summary.growth_category || 'unknown';

            // Determine color based on growth category
            let colorClass = 'text-warmgray-600';
            let icon = '';
            if (category === 'fast_growing' || category === 'growing') {
                colorClass = 'text-green-600';
                icon = '\u2191';
            } else if (category === 'declining' || category === 'fast_declining') {
                colorClass = 'text-red-600';
                icon = '\u2193';
            } else {
                icon = '\u2192';
            }

            el.innerHTML = `
                <div class="flex items-center gap-2">
                    <span class="text-lg font-bold ${colorClass}">${icon} ${changePct > 0 ? '+' : ''}${changePct.toFixed(1)}%</span>
                    <span class="text-warmgray-500">projected growth (2024-2034)</span>
                </div>
                <div class="text-xs text-warmgray-400 mt-1">
                    ${formatNumber(summary.total_2024 || 0)}K \u2192 ${formatNumber(summary.total_2034 || 0)}K jobs nationwide
                </div>
                <div class="text-xs text-warmgray-400 mt-1 italic">
                    Sector-level estimate (detailed NAICS unavailable)
                </div>
            `;
        }
    } catch (e) {
        console.log('Projections load failed:', e);
        el.innerHTML = '<span class="text-warmgray-400">Projections unavailable</span>';
    }
}

async function toggleOccupations() {
    const occupationsEl = document.getElementById('occupationsData');
    const toggleIcon = document.getElementById('occupationsToggleIcon');
    const toggleText = document.getElementById('occupationsToggleText');

    if (occupationsEl.classList.contains('hidden')) {
        // Show occupations
        occupationsEl.classList.remove('hidden');
        toggleIcon.textContent = '\u25B2';
        toggleText.textContent = 'Hide Occupations';

        // Load if not already loaded
        if (occupationsEl.innerHTML === '' || occupationsEl.innerHTML.includes('Loading')) {
            await loadOccupationBreakdown(currentProjectionMatrixCode);
        }
    } else {
        // Hide occupations
        occupationsEl.classList.add('hidden');
        toggleIcon.textContent = '\u25BC';
        toggleText.textContent = 'Show Top Occupations';
    }
}

async function loadOccupationBreakdown(matrixCode) {
    const el = document.getElementById('occupationsData');
    el.innerHTML = '<div class="text-warmgray-400 text-xs">Loading occupations...</div>';

    try {
        const response = await fetch(`${API_BASE}/projections/matrix/${matrixCode}/occupations?occupation_type=Line+Item&limit=8&sort_by=employment`);
        if (!response.ok) throw new Error('Failed to load');

        const data = await response.json();
        const occupations = data.occupations || [];

        if (occupations.length === 0) {
            el.innerHTML = '<div class="text-warmgray-400 text-xs">No occupation data available</div>';
            return;
        }

        let html = `
            <div class="border-t border-warmgray-200 pt-3">
                <div class="text-xs font-semibold text-warmgray-500 mb-2">Top Occupations in This Industry</div>
                <div class="space-y-1">
        `;

        for (const occ of occupations) {
            const changePct = occ.emp_change_pct || 0;
            let growthColor = 'text-warmgray-500';
            let growthIcon = '\u2192';

            if (changePct >= 5) {
                growthColor = 'text-green-600';
                growthIcon = '\u2191';
            } else if (changePct >= 0) {
                growthColor = 'text-green-500';
                growthIcon = '\u2197';
            } else if (changePct >= -5) {
                growthColor = 'text-orange-500';
                growthIcon = '\u2198';
            } else {
                growthColor = 'text-red-600';
                growthIcon = '\u2193';
            }

            // Truncate long titles
            const title = occ.occupation_title.length > 30
                ? occ.occupation_title.substring(0, 28) + '...'
                : occ.occupation_title;

            html += `
                <div class="flex items-center justify-between text-xs py-1 border-b border-warmgray-100 last:border-0">
                    <span class="text-warmgray-700 truncate flex-1" title="${escapeHtml(occ.occupation_title)}">${escapeHtml(title)}</span>
                    <span class="text-warmgray-500 mx-2">${formatNumber(occ.emp_2024 || 0)}K</span>
                    <span class="font-medium ${growthColor} w-14 text-right">${growthIcon} ${changePct > 0 ? '+' : ''}${changePct.toFixed(1)}%</span>
                </div>
            `;
        }

        html += `
                </div>
                <div class="text-xs text-warmgray-400 mt-2 text-right">
                    Source: BLS Employment Projections 2024-2034
                </div>
            </div>
        `;

        el.innerHTML = html;
    } catch (e) {
        console.log('Occupations load failed:', e);
        el.innerHTML = '<div class="text-warmgray-400 text-xs">Could not load occupation data</div>';
    }
}

async function loadEmployerOsha(employerId) {
    const contentEl = document.getElementById('oshaContent');
    const loadingEl = document.getElementById('oshaLoadingBadge');

    loadingEl.classList.remove('hidden');

    try {
        const response = await fetch(`${API_BASE}/employers/${employerId}/osha`);
        if (!response.ok) throw new Error('Failed to load');

        const data = await response.json();
        renderOshaContent(data);
    } catch (e) {
        console.log('OSHA load failed:', e);
        contentEl.innerHTML = `
            <div class="bg-warmgray-50 border border-dashed border-warmgray-300 rounded-lg p-4 text-center text-sm text-warmgray-400">
                No OSHA data available
            </div>
        `;
    } finally {
        loadingEl.classList.add('hidden');
    }
}

function renderOshaContent(data) {
    const contentEl = document.getElementById('oshaContent');

    if (!data.osha_summary || data.osha_summary.total_establishments === 0) {
        contentEl.innerHTML = `
            <div class="bg-green-50 border border-green-200 rounded-lg p-4 text-center text-sm text-green-700">
                <span class="font-medium">\u2713 No OSHA violations found</span>
                <p class="text-green-600 text-xs mt-1">No matched OSHA inspection records</p>
            </div>
        `;
        return;
    }

    const s = data.osha_summary;
    const riskColors = {
        'HIGH': 'bg-red-100 text-red-800 border-red-200',
        'MEDIUM': 'bg-yellow-100 text-yellow-800 border-yellow-200',
        'LOW': 'bg-green-100 text-green-700 border-green-200',
        'NONE': 'bg-warmgray-100 text-warmgray-600 border-warmgray-200'
    };
    // Compute risk level from violation data since API doesn't return it
    const riskLevel = s.willful_violations > 0 ? 'HIGH' : s.serious_violations > 2 ? 'MEDIUM' : s.total_violations > 0 ? 'LOW' : 'NONE';
    const riskClass = riskColors[riskLevel] || riskColors['NONE'];

    let html = `
        <div class="space-y-3">
            <!-- Summary -->
            <div class="flex items-center justify-between">
                <span class="px-2 py-1 text-xs font-semibold rounded border ${riskClass}">
                    ${riskLevel} RISK
                </span>
                <span class="text-xs text-warmgray-500">${s.total_establishments} establishment${s.total_establishments !== 1 ? 's' : ''} matched</span>
            </div>

            <!-- Violation stats -->
            <div class="grid grid-cols-4 gap-2 text-center">
                <div class="bg-warmgray-100 rounded p-2">
                    <div class="text-lg font-bold text-warmgray-900">${formatNumber(s.total_violations)}</div>
                    <div class="text-xs text-warmgray-500">Total</div>
                </div>
                <div class="bg-orange-50 rounded p-2">
                    <div class="text-lg font-bold text-orange-700">${formatNumber(s.serious_violations)}</div>
                    <div class="text-xs text-orange-600">Serious</div>
                </div>
                <div class="bg-red-50 rounded p-2">
                    <div class="text-lg font-bold text-red-700">${formatNumber(s.willful_violations)}</div>
                    <div class="text-xs text-red-600">Willful</div>
                </div>
                <div class="bg-warmgray-100 rounded p-2">
                    <div class="text-lg font-bold text-warmgray-900">${formatNumber(s.total_inspections || 0)}</div>
                    <div class="text-xs text-warmgray-500">Inspections</div>
                </div>
            </div>

            <!-- Penalties -->
            ${s.total_penalties > 0 ? `
                <div class="bg-red-50 border border-red-100 rounded-lg p-3 text-center">
                    <div class="text-xl font-bold text-red-700">$${formatNumber(s.total_penalties)}</div>
                    <div class="text-xs text-red-600">Total Penalties</div>
                </div>
            ` : ''}
    `;

    // Show recent establishments
    if (data.establishments && data.establishments.length > 0) {
        html += `
            <div class="mt-3">
                <div class="text-xs font-semibold text-warmgray-500 mb-2">Recent Inspections</div>
                <div class="space-y-2 max-h-40 overflow-y-auto">
        `;
        data.establishments.slice(0, 5).forEach(est => {
            html += `
                <div class="text-sm p-2 bg-warmgray-50 rounded flex justify-between items-center">
                    <div>
                        <div class="font-medium text-warmgray-900">${escapeHtml(est.estab_name || 'Unknown')}</div>
                        <div class="text-xs text-warmgray-500">${escapeHtml(est.site_city || '')}, ${est.site_state || ''}</div>
                    </div>
                    <div class="text-right">
                        <div class="text-xs font-medium ${est.total_violations > 0 ? 'text-red-600' : 'text-green-600'}">
                            ${est.total_violations} violations
                        </div>
                        ${est.last_inspection_date ? `<div class="text-xs text-warmgray-400">${est.last_inspection_date}</div>` : ''}
                    </div>
                </div>
            `;
        });
        html += '</div></div>';
    }

    html += '</div>';
    contentEl.innerHTML = html;
}

async function loadEmployerNlrb(employerId) {
    const contentEl = document.getElementById('nlrbContent');
    const loadingEl = document.getElementById('nlrbLoadingBadge');

    loadingEl.classList.remove('hidden');

    try {
        const response = await fetch(`${API_BASE}/employers/${employerId}/nlrb`);
        if (!response.ok) throw new Error('Failed to load');

        const data = await response.json();
        renderNlrbContent(data);
    } catch (e) {
        console.log('NLRB load failed:', e);
        contentEl.innerHTML = `
            <div class="bg-warmgray-50 border border-dashed border-warmgray-300 rounded-lg p-4 text-center text-sm text-warmgray-400">
                No NLRB data available
            </div>
        `;
    } finally {
        loadingEl.classList.add('hidden');
    }
}

function renderNlrbContent(data) {
    const contentEl = document.getElementById('nlrbContent');

    const hasElections = data.elections && data.elections.length > 0;
    const hasUlp = data.ulp_cases && data.ulp_cases.length > 0;

    if (!hasElections && !hasUlp) {
        contentEl.innerHTML = `
            <div class="bg-warmgray-50 border border-dashed border-warmgray-300 rounded-lg p-4 text-center text-sm text-warmgray-400">
                No NLRB election or ULP records found for this employer
            </div>
        `;
        return;
    }

    const es = data.elections_summary || {};
    const us = data.ulp_summary || {};

    let html = '<div class="space-y-3">';

    // Summary stats
    if ((es.total || 0) > 0 || (us.total || 0) > 0) {
        html += `
            <div class="grid grid-cols-4 gap-2 text-center">
                <div class="bg-warmgray-100 rounded p-2">
                    <div class="text-lg font-bold text-warmgray-900">${es.total || 0}</div>
                    <div class="text-xs text-warmgray-500">Elections</div>
                </div>
                <div class="bg-green-50 rounded p-2">
                    <div class="text-lg font-bold text-green-700">${es.union_wins || 0}</div>
                    <div class="text-xs text-green-600">Union Wins</div>
                </div>
                <div class="bg-red-50 rounded p-2">
                    <div class="text-lg font-bold text-red-700">${es.union_losses || 0}</div>
                    <div class="text-xs text-red-600">Losses</div>
                </div>
                <div class="bg-yellow-50 rounded p-2">
                    <div class="text-lg font-bold text-yellow-700">${us.total || 0}</div>
                    <div class="text-xs text-yellow-600">ULP Cases</div>
                </div>
            </div>
        `;
    }

    // Elections list
    if (hasElections) {
        html += `
            <div>
                <div class="text-xs font-semibold text-warmgray-500 mb-2">Election History</div>
                <div class="space-y-2 max-h-48 overflow-y-auto">
        `;
        data.elections.slice(0, 8).forEach(el => {
            const isWin = el.union_won === true;
            const isLoss = el.union_won === false;
            const resultClass = isWin ? 'text-green-600' : (isLoss ? 'text-red-600' : 'text-warmgray-500');
            const resultText = isWin ? 'Union Won' : (isLoss ? 'Employer Won' : 'Pending');

            html += `
                <div class="text-sm p-2 bg-warmgray-50 rounded">
                    <div class="flex justify-between items-start">
                        <div>
                            <div class="font-medium text-warmgray-900">${escapeHtml(el.case_number || '')}</div>
                            <div class="text-xs text-warmgray-500">${el.election_date || el.date_filed || '\u2014'}</div>
                        </div>
                        <span class="text-xs font-medium ${resultClass}">${resultText}</span>
                    </div>
                    ${el.eligible_voters != null ? `
                        <div class="mt-1 text-xs text-warmgray-500">
                            ${el.eligible_voters} eligible voters${el.vote_margin != null ? `, margin: ${el.vote_margin}` : ''}
                        </div>
                    ` : ''}
                    ${el.union_name ? `<div class="text-xs text-warmgray-400 mt-1">${escapeHtml(el.union_name)}</div>` : ''}
                </div>
            `;
        });
        html += '</div></div>';
    }

    // ULP cases
    if (hasUlp) {
        html += `
            <div>
                <div class="text-xs font-semibold text-warmgray-500 mb-2">Unfair Labor Practice Cases</div>
                <div class="space-y-2 max-h-32 overflow-y-auto">
        `;
        data.ulp_cases.slice(0, 5).forEach(ulp => {
            const caseTypes = {
                'CA': 'Employer ULP',
                'CB': 'Union ULP',
                'CC': 'Union ULP',
                'CD': 'Jurisdictional',
                'CE': 'Employer ULP',
                'CG': 'Employer ULP',
                'CP': 'Picketing'
            };
            const typeLabel = caseTypes[ulp.case_type] || ulp.case_type;

            html += `
                <div class="text-sm p-2 bg-yellow-50 rounded flex justify-between items-center">
                    <div>
                        <div class="font-medium text-warmgray-900">${escapeHtml(ulp.case_number)}</div>
                        <div class="text-xs text-warmgray-500">${ulp.date_filed || '\u2014'} \u00B7 ${typeLabel}</div>
                    </div>
                    <div class="text-right">
                        <span class="text-xs px-1.5 py-0.5 rounded ${ulp.status === 'Closed' ? 'bg-warmgray-200 text-warmgray-600' : 'bg-yellow-200 text-yellow-800'}">
                            ${escapeHtml(ulp.status || 'Unknown')}
                        </span>
                        ${ulp.allegation_count > 0 ? `<div class="text-xs text-warmgray-400 mt-1">${ulp.allegation_count} allegations</div>` : ''}
                    </div>
                </div>
            `;
        });
        html += '</div></div>';
    }

    html += '</div>';
    contentEl.innerHTML = html;
}

let trendsChart = null;

async function renderUnionDetail(item) {
    // Populate detail fields for union
    document.getElementById('detailName').textContent = formatUnionName(item);
    document.getElementById('detailLocation').textContent = `${item.city || 'Unknown'}, ${item.state || ''}`;

    // Badges
    const sectorClass = getSectorBadgeClass(item.sector);
    const badgesHtml = `
        <span class="badge ${sectorClass}">${formatSectorName(item.sector)}</span>
        ${item.aff_abbr ? `<span class="badge badge-industry cursor-pointer hover:opacity-80" onclick="openNationalDashboard('${escapeHtml(item.aff_abbr)}')" title="View ${escapeHtml(item.aff_abbr)} National Dashboard">${escapeHtml(item.aff_abbr)}</span>` : ''}
    `;
    document.getElementById('detailBadges').innerHTML = badgesHtml;

    // Key metrics - Union view
    document.getElementById('detailMetrics').innerHTML = `
        <div class="bg-warmgray-100 rounded-lg p-4">
            <div class="text-xs font-semibold text-warmgray-500 uppercase tracking-wide mb-1">Affiliation</div>
            ${item.aff_abbr ? `
                <div class="font-semibold text-warmgray-900 cursor-pointer hover:text-accent-red" onclick="openNationalDashboard('${escapeHtml(item.aff_abbr)}')">${escapeHtml(item.aff_abbr)}</div>
                <div class="text-xs text-accent-red cursor-pointer hover:underline mt-1" onclick="openNationalDashboard('${escapeHtml(item.aff_abbr)}')">View national \u2192</div>
            ` : `
                <div class="font-semibold text-warmgray-900">Independent</div>
            `}
        </div>
        <div class="bg-warmgray-100 rounded-lg p-4">
            <div class="text-xs font-semibold text-warmgray-500 uppercase tracking-wide mb-1">Members</div>
            <div class="text-3xl font-bold text-accent-red">${formatNumber(item.members || 0)}</div>
        </div>
        <div class="bg-warmgray-100 rounded-lg p-4">
            <div class="text-xs font-semibold text-warmgray-500 uppercase tracking-wide mb-1">Employers</div>
            <div class="text-2xl font-bold text-warmgray-900">${formatNumber(item.f7_employer_count || 0)}</div>
            <div class="text-sm text-warmgray-500">${formatNumber(item.f7_total_workers || 0)} workers</div>
        </div>
    `;

    // Show loading states
    document.getElementById('detailFilingSection').innerHTML = `
        <div class="text-xs font-semibold text-warmgray-500 uppercase tracking-wide mb-3">LM Filing Summary</div>
        <div class="text-warmgray-400 text-sm">Loading financial data...</div>
    `;
    document.getElementById('detailProjections').innerHTML = `
        <div class="text-xs font-semibold text-warmgray-500 uppercase tracking-wide mb-3">Top Industries</div>
        <div class="text-warmgray-400 text-sm">Loading...</div>
    `;

    // Show union-specific sections, hide employer-specific
    document.getElementById('detailCorporateSection').classList.add('hidden');
    document.getElementById('detailOshaSection').classList.add('hidden');
    document.getElementById('detailNlrbSection').classList.add('hidden');
    document.getElementById('detailNewsSection').classList.add('hidden');
    document.getElementById('detailSourceSection').classList.add('hidden');
    document.getElementById('detailFlagSection').classList.add('hidden');
    document.getElementById('detailEmployersSection').classList.remove('hidden');
    document.getElementById('detailFinancialsSection').classList.remove('hidden');
    document.getElementById('detailTrendsSection').classList.remove('hidden');
    document.getElementById('detailSisterLocalsSection').classList.remove('hidden');
    document.getElementById('detailGeoSection').classList.remove('hidden');

    // Employers covered section (placeholder while loading)
    document.getElementById('detailEmployersSection').innerHTML = `
        <div class="text-xs font-semibold text-warmgray-500 uppercase tracking-wide mb-3">Top Employers</div>
        <div class="text-warmgray-400 text-sm">Loading...</div>
    `;

    // Sister locals placeholder
    document.getElementById('detailSisterLocalsSection').innerHTML = `
        <div class="text-xs font-semibold text-warmgray-500 uppercase tracking-wide mb-3">Sister Locals</div>
        <div class="text-warmgray-400 text-sm">Loading...</div>
    `;

    // Geo distribution placeholder
    document.getElementById('detailGeoSection').innerHTML = `
        <div class="text-xs font-semibold text-warmgray-500 uppercase tracking-wide mb-3">Geographic Coverage</div>
        <div class="text-warmgray-400 text-sm">Loading...</div>
    `;

    // Action button for unions
    const inComparison = isInComparison(item.f_num);
    document.getElementById('detailActionSection').innerHTML = `
        <div class="flex gap-2 mb-2">
            ${item.f7_employer_count > 0 ? `
                <button onclick="viewUnionEmployers('${item.f_num}')"
                    class="flex-1 py-3 bg-warmgray-900 text-white font-semibold rounded-lg hover:bg-warmgray-800 transition-colors">
                    View All ${formatNumber(item.f7_employer_count)} Employers \u2192
                </button>
            ` : `
                <div class="flex-1 text-center text-warmgray-400 text-sm py-3 border-2 border-warmgray-200 rounded-lg">
                    No F-7 employer filings
                </div>
            `}
            <button onclick="addToComparison(selectedItem)"
                class="px-4 py-3 border-2 ${inComparison ? 'border-accent-red bg-accent-red/10 text-accent-red' : 'border-warmgray-300 text-warmgray-600 hover:border-warmgray-400'} font-semibold rounded-lg transition-colors"
                title="${inComparison ? 'Already in comparison' : 'Add to comparison'}">
                <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z"/>
                </svg>
            </button>
        </div>
        ${item.f7_employer_count > 0 ? `<p class="text-xs text-warmgray-400 text-center">See complete employer list with bargaining agreements</p>` : ''}
    `;

    // Update map
    updateDetailMap(item);

    // Fetch detailed union info
    try {
        const response = await fetch(`${API_BASE}/unions/${item.f_num}`);
        if (response.ok) {
            const detail = await response.json();
            renderUnionDetailData(detail, item);
        }
    } catch (e) {
        console.error('Failed to load union detail:', e);
    }
}

function renderUnionDetailData(detail, item) {
    // API returns {union, top_employers, nlrb_elections, nlrb_summary}
    const u = detail.union || {};
    const hasFinancials = u.ttl_receipts || u.ttl_assets;

    // Financial summary
    if (hasFinancials) {
        const netAssets = (u.ttl_assets || 0) - (u.ttl_liabilities || 0);
        document.getElementById('detailFilingSection').innerHTML = `
            <div class="text-xs font-semibold text-warmgray-500 uppercase tracking-wide mb-3">LM Filing${u.yr_covered ? ` (${u.yr_covered})` : ''}</div>
            <div class="grid grid-cols-2 gap-3 text-sm">
                <div class="bg-warmgray-50 rounded p-3">
                    <div class="text-warmgray-500 text-xs mb-1">Total Receipts</div>
                    <div class="font-semibold text-warmgray-900">${formatCurrency(u.ttl_receipts)}</div>
                </div>
                <div class="bg-warmgray-50 rounded p-3">
                    <div class="text-warmgray-500 text-xs mb-1">Members</div>
                    <div class="font-semibold text-warmgray-900">${formatNumber(u.members || 0)}</div>
                </div>
                <div class="bg-warmgray-50 rounded p-3">
                    <div class="text-warmgray-500 text-xs mb-1">Total Assets</div>
                    <div class="font-semibold text-warmgray-900">${formatCurrency(u.ttl_assets)}</div>
                </div>
                <div class="bg-warmgray-50 rounded p-3">
                    <div class="text-warmgray-500 text-xs mb-1">Net Assets</div>
                    <div class="font-semibold ${netAssets >= 0 ? 'text-green-700' : 'text-red-700'}">${formatCurrency(netAssets)}</div>
                </div>
            </div>
        `;
    } else {
        document.getElementById('detailFilingSection').innerHTML = `
            <div class="text-xs font-semibold text-warmgray-500 uppercase tracking-wide mb-3">LM Filing Summary</div>
            <div class="text-warmgray-400 text-sm">No LM filings found</div>
        `;
    }

    // Render trends chart
    renderTrendsChart(detail.financial_trends);

    // Render industries
    const industries = detail.industry_distribution || [];
    if (industries.length > 0) {
        document.getElementById('detailProjections').innerHTML = `
            <div class="text-xs font-semibold text-warmgray-500 uppercase tracking-wide mb-3">Top Industries</div>
            <div class="flex flex-wrap gap-2">
                ${industries.slice(0, 5).map(ind =>
                    `<span class="px-3 py-1 bg-warmgray-100 text-warmgray-700 text-sm rounded-full">
                        ${escapeHtml(ind.sector_name || 'NAICS ' + ind.naics_2digit)}
                        <span class="text-warmgray-400">(${formatNumber(ind.workers || 0)})</span>
                    </span>`
                ).join('')}
            </div>
        `;
    } else {
        document.getElementById('detailProjections').innerHTML = `
            <div class="text-xs font-semibold text-warmgray-500 uppercase tracking-wide mb-3">Top Industries</div>
            <div class="text-warmgray-400 text-sm">No industry data available</div>
        `;
    }

    // Render top employers
    const employers = detail.top_employers || [];
    if (employers.length > 0) {
        document.getElementById('detailEmployersSection').innerHTML = `
            <div class="flex justify-between items-center mb-3">
                <div class="text-xs font-semibold text-warmgray-500 uppercase tracking-wide">Top Employers</div>
                ${item.f7_employer_count > 10 ? `
                    <button onclick="viewUnionEmployers('${item.f_num}')" class="text-xs text-accent-red hover:underline">
                        View all ${formatNumber(item.f7_employer_count)} \u2192
                    </button>
                ` : ''}
            </div>
            <div class="space-y-2 max-h-48 overflow-y-auto">
                ${employers.map(emp => `
                    <div class="flex justify-between items-center p-2 bg-warmgray-50 rounded hover:bg-warmgray-100 cursor-pointer"
                         onclick="switchToEmployerAndSelect('${emp.employer_id}')">
                        <div>
                            <div class="font-medium text-sm text-warmgray-900 entity-link">${escapeHtml(emp.employer_name)}</div>
                            <div class="text-xs text-warmgray-500">${escapeHtml(emp.city || '')}, ${emp.state || ''}</div>
                        </div>
                        <div class="text-right">
                            <div class="font-semibold text-warmgray-900">${formatNumber(emp.latest_unit_size || 0)}</div>
                            <div class="text-xs text-warmgray-400">workers</div>
                        </div>
                    </div>
                `).join('')}
            </div>
        `;
    } else {
        document.getElementById('detailEmployersSection').innerHTML = `
            <div class="text-xs font-semibold text-warmgray-500 uppercase tracking-wide mb-3">Top Employers</div>
            <div class="text-warmgray-400 text-sm">No employer data available</div>
        `;
    }

    // Render sister locals
    const sisterLocals = detail.sister_locals || [];
    if (sisterLocals.length > 0) {
        document.getElementById('detailSisterLocalsSection').innerHTML = `
            <div class="text-xs font-semibold text-warmgray-500 uppercase tracking-wide mb-3">
                Sister Locals (${item.aff_abbr})
            </div>
            <div class="space-y-2 max-h-40 overflow-y-auto">
                ${sisterLocals.map(local => `
                    <div class="flex justify-between items-center p-2 bg-warmgray-50 rounded hover:bg-warmgray-100 cursor-pointer"
                         onclick="selectUnionByFnum('${local.f_num}')">
                        <div>
                            <div class="font-medium text-sm text-warmgray-900">
                                ${local.local_number ? `Local ${local.local_number}${local.desig_name || ''}` : escapeHtml(local.union_name || 'Unknown')}
                            </div>
                            <div class="text-xs text-warmgray-500">${escapeHtml(local.city || '')}, ${local.state || ''}</div>
                        </div>
                        <div class="text-right">
                            <div class="font-semibold text-warmgray-900">${formatNumber(local.members || 0)}</div>
                            <div class="text-xs text-warmgray-400">${local.employer_count || 0} employers</div>
                        </div>
                    </div>
                `).join('')}
            </div>
        `;
    } else {
        document.getElementById('detailSisterLocalsSection').classList.add('hidden');
    }

    // Render geographic distribution
    const geoDist = detail.geo_distribution || [];
    if (geoDist.length > 0) {
        const totalWorkers = geoDist.reduce((sum, g) => sum + (g.workers || 0), 0);
        document.getElementById('detailGeoSection').innerHTML = `
            <div class="text-xs font-semibold text-warmgray-500 uppercase tracking-wide mb-3">Geographic Coverage</div>
            <div class="space-y-2">
                ${geoDist.slice(0, 6).map(geo => {
                    const pct = totalWorkers > 0 ? Math.round((geo.workers || 0) / totalWorkers * 100) : 0;
                    return `
                        <div class="flex items-center gap-3">
                            <div class="w-8 text-xs font-medium text-warmgray-700">${geo.state}</div>
                            <div class="flex-1 bg-warmgray-200 rounded-full h-2">
                                <div class="bg-accent-red rounded-full h-2" style="width: ${pct}%"></div>
                            </div>
                            <div class="w-20 text-right text-xs text-warmgray-600">
                                ${formatNumber(geo.workers || 0)} <span class="text-warmgray-400">(${pct}%)</span>
                            </div>
                        </div>
                    `;
                }).join('')}
            </div>
        `;
    } else {
        document.getElementById('detailGeoSection').classList.add('hidden');
    }
}

function renderTrendsChart(financials) {
    // Destroy existing chart
    if (trendsChart) {
        trendsChart.destroy();
        trendsChart = null;
    }

    if (!financials || financials.length < 2) {
        document.getElementById('detailTrendsSection').classList.add('hidden');
        return;
    }

    // Reverse to show chronological order
    const sorted = [...financials].reverse();
    const labels = sorted.map(f => f.yr_covered);
    const memberData = sorted.map(f => f.members || 0);
    const assetData = sorted.map(f => (f.ttl_assets || 0) / 1000); // Convert to thousands

    const ctx = document.getElementById('trendsChart').getContext('2d');

    trendsChart = new Chart(ctx, {
        type: 'line',
        data: {
            labels: labels,
            datasets: [
                {
                    label: 'Members',
                    data: memberData,
                    borderColor: '#8B4513',
                    backgroundColor: 'rgba(139, 69, 19, 0.1)',
                    yAxisID: 'y',
                    tension: 0.3,
                    fill: true
                },
                {
                    label: 'Assets ($K)',
                    data: assetData,
                    borderColor: '#6B7280',
                    backgroundColor: 'rgba(107, 114, 128, 0.1)',
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
                    labels: {
                        boxWidth: 12,
                        font: { size: 11 }
                    }
                }
            },
            scales: {
                x: {
                    grid: { display: false }
                },
                y: {
                    type: 'linear',
                    display: true,
                    position: 'left',
                    title: {
                        display: true,
                        text: 'Members',
                        font: { size: 10 }
                    },
                    ticks: {
                        callback: function(value) {
                            return value >= 1000 ? (value/1000).toFixed(0) + 'K' : value;
                        }
                    }
                },
                y1: {
                    type: 'linear',
                    display: true,
                    position: 'right',
                    title: {
                        display: true,
                        text: 'Assets ($K)',
                        font: { size: 10 }
                    },
                    grid: {
                        drawOnChartArea: false,
                    },
                },
            }
        }
    });
}

async function switchToEmployerAndSelect(employerId) {
    // Switch to employer mode and fetch employer before selecting
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

async function selectUnionByFnum(fNum) {
    // Find the union in current results or fetch it
    const existing = currentResults.find(r => r.f_num === fNum);
    if (existing) {
        selectItem(fNum);
    } else {
        // Fetch and select
        try {
            const response = await fetch(`${API_BASE}/unions/search?f_num=${fNum}&limit=1`);
            if (response.ok) {
                const data = await response.json();
                if (data.unions && data.unions.length > 0) {
                    currentResults.push(data.unions[0]);
                    selectItem(fNum);
                }
            }
        } catch (e) {
            console.error('Failed to load union:', e);
        }
    }
}

// Helper functions
async function viewUnionEmployers(fNum) {
    // Switch to employer mode
    setSearchMode('employers');

    // Clear other filters and search for this union's employers
    document.getElementById('mainSearch').value = '';
    document.getElementById('stateFilter').value = '';
    document.getElementById('cityFilter').value = '';
    document.getElementById('sectorFilter').value = '';
    clearIndustrySelection();

    // Search for employers by union f_num
    currentPage = 1;
    showLoading(true);

    try {
        const response = await fetch(`${API_BASE}/unions/${fNum}/employers?limit=50`);
        if (response.ok) {
            const data = await response.json();

            // Transform data to match expected format
            const transformedData = {
                total_count: data.total_employers,
                total_workers: data.employers.reduce((sum, e) => sum + (e.latest_unit_size || 0), 0),
                total_locals: 1,
                results: data.employers.map(e => ({
                    ...e,
                    union_sector: 'PRIVATE', // May need to lookup
                    latest_union_name: `F-${fNum}`
                }))
            };

            displayResults(transformedData);
        } else {
            showError('Failed to load employers for this union');
        }
    } catch (e) {
        console.error('Failed to load union employers:', e);
        showError('Failed to load employers. Check API connection.');
    } finally {
        showLoading(false);
    }
}
