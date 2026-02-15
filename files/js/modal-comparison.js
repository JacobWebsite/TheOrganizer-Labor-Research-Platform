// modal-comparison.js -- Comparison view + Saved Searches

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
