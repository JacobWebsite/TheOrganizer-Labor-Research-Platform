// search.js -- Search mode, typeahead, and results functions

function setSearchMode(mode) {
    currentMode = mode;
    
    // Update tab styles
    document.getElementById('tabEmployers').className = mode === 'employers' 
        ? 'tab-active px-6 py-2 text-sm font-semibold rounded-full transition-all'
        : 'tab-inactive px-6 py-2 text-sm font-semibold rounded-full transition-all hover:text-warmgray-700';
    document.getElementById('tabUnions').className = mode === 'unions'
        ? 'tab-active px-6 py-2 text-sm font-semibold rounded-full transition-all'
        : 'tab-inactive px-6 py-2 text-sm font-semibold rounded-full transition-all hover:text-warmgray-700';
    
    // Update placeholder text
    document.getElementById('mainSearch').placeholder = mode === 'employers' 
        ? 'Search by employer name...'
        : 'Search by union name...';
    
    // Update empty state text
    document.getElementById('emptyStateTitle').textContent = mode === 'employers'
        ? 'Search for employers'
        : 'Search for unions';
    document.getElementById('emptyStateSubtitle').textContent = mode === 'employers'
        ? 'Find organized workplaces by name, industry, or location'
        : 'Find union locals by name, affiliation, or location';
    
    // Update detail empty state
    document.getElementById('detailEmptyText').textContent = mode === 'employers'
        ? 'Select an employer to view details'
        : 'Select a union to view details';
    
    // Clear results
    clearResults();
}


// ==========================================
// TYPEAHEAD DATA
// ==========================================
const typeaheadData = {
    // NAICS 2-digit sectors
    naics_sectors: [
        { code: '11', name: 'Agriculture, Forestry, Fishing and Hunting', keywords: ['farm', 'farming', 'agricultural', 'forestry', 'logging', 'fishing'] },
        { code: '21', name: 'Mining, Quarrying, and Oil and Gas Extraction', keywords: ['mining', 'oil', 'gas', 'petroleum', 'coal', 'quarry'] },
        { code: '22', name: 'Utilities', keywords: ['utility', 'utilities', 'electric', 'power', 'water', 'gas', 'energy'] },
        { code: '23', name: 'Construction', keywords: ['construction', 'building', 'contractor', 'trades', 'carpenter', 'electrician', 'plumber'] },
        { code: '31', name: 'Manufacturing - Food, Beverage, Textiles', keywords: ['food', 'beverage', 'textile', 'apparel', 'clothing', 'meat', 'bakery'] },
        { code: '32', name: 'Manufacturing - Wood, Paper, Chemicals', keywords: ['wood', 'paper', 'chemical', 'plastics', 'rubber', 'petroleum', 'printing'] },
        { code: '33', name: 'Manufacturing - Metals, Machinery, Electronics', keywords: ['metal', 'steel', 'machinery', 'computer', 'electronics', 'automotive', 'aerospace', 'auto'] },
        { code: '42', name: 'Wholesale Trade', keywords: ['wholesale', 'distributor', 'distribution'] },
        { code: '44', name: 'Retail Trade - Motor Vehicles, Home', keywords: ['retail', 'car dealer', 'furniture', 'electronics store', 'hardware'] },
        { code: '45', name: 'Retail Trade - Grocery, General', keywords: ['grocery', 'supermarket', 'pharmacy', 'gas station', 'department store', 'retail'] },
        { code: '48', name: 'Transportation', keywords: ['transportation', 'trucking', 'airline', 'railroad', 'rail', 'transit', 'bus', 'shipping', 'freight'] },
        { code: '49', name: 'Warehousing and Postal', keywords: ['warehouse', 'warehousing', 'postal', 'courier', 'delivery', 'ups', 'fedex', 'amazon'] },
        { code: '51', name: 'Information', keywords: ['media', 'publishing', 'broadcasting', 'telecom', 'telecommunications', 'internet', 'software', 'film', 'movie', 'television', 'tv', 'radio', 'news'] },
        { code: '52', name: 'Finance and Insurance', keywords: ['bank', 'banking', 'insurance', 'credit union', 'financial', 'investment'] },
        { code: '53', name: 'Real Estate and Rental', keywords: ['real estate', 'property', 'rental', 'leasing'] },
        { code: '54', name: 'Professional, Scientific, Technical Services', keywords: ['legal', 'lawyer', 'accounting', 'engineering', 'architect', 'consulting', 'research', 'tech'] },
        { code: '55', name: 'Management of Companies', keywords: ['corporate', 'headquarters', 'holding company'] },
        { code: '56', name: 'Administrative and Waste Services', keywords: ['janitorial', 'janitor', 'custodian', 'security', 'guard', 'staffing', 'temp', 'waste', 'cleaning', 'building services'] },
        { code: '61', name: 'Educational Services', keywords: ['education', 'school', 'college', 'university', 'teacher', 'professor', 'k-12', 'training'] },
        { code: '62', name: 'Health Care and Social Assistance', keywords: ['healthcare', 'health care', 'hospital', 'nurse', 'nursing', 'doctor', 'medical', 'clinic', 'home health', 'social work', 'childcare', 'daycare'] },
        { code: '71', name: 'Arts, Entertainment, and Recreation', keywords: ['entertainment', 'sports', 'casino', 'gambling', 'theater', 'theatre', 'museum', 'amusement', 'recreation'] },
        { code: '72', name: 'Accommodation and Food Services', keywords: ['hotel', 'motel', 'restaurant', 'food service', 'hospitality', 'casino', 'bar', 'catering'] },
        { code: '81', name: 'Other Services', keywords: ['repair', 'automotive repair', 'personal services', 'laundry', 'religious', 'nonprofit'] },
        { code: '92', name: 'Public Administration', keywords: ['government', 'public sector', 'federal', 'state', 'municipal', 'city', 'county'] }
    ],
    
    // Common NAICS 3-4 digit subsectors
    naics_subsectors: [
        { code: '622', name: 'Hospitals', parent: '62', keywords: ['hospital', 'medical center'] },
        { code: '623', name: 'Nursing and Residential Care', parent: '62', keywords: ['nursing home', 'assisted living', 'residential care', 'senior'] },
        { code: '621', name: 'Ambulatory Health Care', parent: '62', keywords: ['clinic', 'physician', 'dentist', 'outpatient', 'home health'] },
        { code: '611', name: 'Elementary and Secondary Schools', parent: '61', keywords: ['k-12', 'school', 'elementary', 'high school', 'middle school'] },
        { code: '6113', name: 'Colleges and Universities', parent: '61', keywords: ['college', 'university', 'higher education', 'higher ed'] },
        { code: '484', name: 'Truck Transportation', parent: '48', keywords: ['trucking', 'truck driver', 'freight', 'hauling'] },
        { code: '493', name: 'Warehousing and Storage', parent: '49', keywords: ['warehouse', 'fulfillment', 'distribution center', 'logistics'] },
        { code: '492', name: 'Couriers and Messengers', parent: '49', keywords: ['courier', 'delivery', 'package', 'ups', 'fedex'] },
        { code: '7211', name: 'Hotels and Motels', parent: '72', keywords: ['hotel', 'motel', 'lodging', 'resort'] },
        { code: '7225', name: 'Restaurants', parent: '72', keywords: ['restaurant', 'fast food', 'dining', 'food service'] },
        { code: '4451', name: 'Grocery Stores', parent: '44', keywords: ['grocery', 'supermarket', 'food store'] },
        { code: '5121', name: 'Motion Picture and Video', parent: '51', keywords: ['film', 'movie', 'video production', 'hollywood', 'studio'] },
        { code: '5152', name: 'Cable and Subscription Programming', parent: '51', keywords: ['cable', 'streaming', 'television', 'tv'] },
        { code: '517', name: 'Telecommunications', parent: '51', keywords: ['telecom', 'phone', 'wireless', 'broadband', 'internet provider'] },
        { code: '238', name: 'Specialty Trade Contractors', parent: '23', keywords: ['electrician', 'plumber', 'hvac', 'roofing', 'painting', 'carpentry'] },
        { code: '3361', name: 'Motor Vehicle Manufacturing', parent: '33', keywords: ['auto', 'automotive', 'car', 'vehicle', 'assembly'] },
        { code: '3364', name: 'Aerospace Product Manufacturing', parent: '33', keywords: ['aerospace', 'aircraft', 'airplane', 'boeing', 'defense'] }
    ],
    
    // Union affiliations with industry associations
    unions: [
        { abbr: 'SEIU', name: 'Service Employees International Union', industries: ['62', '56'], keywords: ['healthcare', 'janitor', 'building services', 'home care'] },
        { abbr: 'UFCW', name: 'United Food and Commercial Workers', industries: ['44', '45', '31'], keywords: ['grocery', 'retail', 'meatpacking', 'food processing'] },
        { abbr: 'IBT', name: 'International Brotherhood of Teamsters', industries: ['48', '49', '42'], keywords: ['trucking', 'warehouse', 'delivery', 'ups', 'freight'] },
        { abbr: 'UAW', name: 'United Auto Workers', industries: ['33'], keywords: ['auto', 'automotive', 'manufacturing', 'assembly'] },
        { abbr: 'USW', name: 'United Steelworkers', industries: ['33', '32', '21'], keywords: ['steel', 'metal', 'manufacturing', 'mining', 'paper'] },
        { abbr: 'CWA', name: 'Communications Workers of America', industries: ['51', '52'], keywords: ['telecom', 'media', 'tech', 'call center', 'airline'] },
        { abbr: 'IBEW', name: 'International Brotherhood of Electrical Workers', industries: ['23', '22'], keywords: ['electrician', 'electrical', 'utility', 'construction'] },
        { abbr: 'AFSCME', name: 'American Federation of State County Municipal Employees', industries: ['92', '62', '61'], keywords: ['government', 'public sector', 'state', 'county', 'municipal'] },
        { abbr: 'AFT', name: 'American Federation of Teachers', industries: ['61', '62'], keywords: ['teacher', 'education', 'school', 'professor', 'healthcare'] },
        { abbr: 'NEA', name: 'National Education Association', industries: ['61'], keywords: ['teacher', 'education', 'school', 'k-12'] },
        { abbr: 'NNU', name: 'National Nurses United', industries: ['62'], keywords: ['nurse', 'nursing', 'rn', 'hospital'] },
        { abbr: 'UNITE HERE', name: 'UNITE HERE', industries: ['72', '71'], keywords: ['hotel', 'restaurant', 'hospitality', 'casino', 'food service'] },
        { abbr: 'LIUNA', name: 'Laborers International Union', industries: ['23'], keywords: ['laborer', 'construction', 'building'] },
        { abbr: 'UA', name: 'United Association (Plumbers & Pipefitters)', industries: ['23'], keywords: ['plumber', 'pipefitter', 'plumbing', 'hvac'] },
        { abbr: 'SMART', name: 'Sheet Metal Air Rail Transportation Workers', industries: ['23', '48'], keywords: ['sheet metal', 'hvac', 'rail', 'transit'] },
        { abbr: 'IAM', name: 'International Association of Machinists', industries: ['33', '48'], keywords: ['machinist', 'aerospace', 'airline', 'manufacturing'] },
        { abbr: 'ATU', name: 'Amalgamated Transit Union', industries: ['48'], keywords: ['transit', 'bus', 'driver', 'public transit'] },
        { abbr: 'TWU', name: 'Transport Workers Union', industries: ['48'], keywords: ['transit', 'airline', 'transportation'] },
        { abbr: 'UBC', name: 'United Brotherhood of Carpenters', industries: ['23'], keywords: ['carpenter', 'carpentry', 'woodwork', 'construction'] },
        { abbr: 'IUOE', name: 'International Union of Operating Engineers', industries: ['23'], keywords: ['crane', 'heavy equipment', 'operator', 'construction'] },
        { abbr: 'NALC', name: 'National Association of Letter Carriers', industries: ['49'], keywords: ['postal', 'mail', 'letter carrier', 'usps'] },
        { abbr: 'APWU', name: 'American Postal Workers Union', industries: ['49'], keywords: ['postal', 'mail', 'post office', 'usps'] },
        { abbr: 'AFGE', name: 'American Federation of Government Employees', industries: ['92'], keywords: ['federal', 'government', 'va', 'tsa', 'dod'] },
        { abbr: 'SAG-AFTRA', name: 'Screen Actors Guild - AFTRA', industries: ['51'], keywords: ['actor', 'film', 'television', 'radio', 'media'] },
        { abbr: 'IATSE', name: 'International Alliance of Theatrical Stage Employees', industries: ['51', '71'], keywords: ['stagehand', 'film', 'television', 'theater', 'production'] },
        { abbr: 'WGA', name: 'Writers Guild of America', industries: ['51'], keywords: ['writer', 'screenwriter', 'film', 'television'] },
        { abbr: 'DGA', name: 'Directors Guild of America', industries: ['51'], keywords: ['director', 'film', 'television'] },
        { abbr: 'ILA', name: 'International Longshoremen\'s Association', industries: ['48'], keywords: ['longshoremen', 'dockworker', 'port', 'shipping'] },
        { abbr: 'ILWU', name: 'International Longshore and Warehouse Union', industries: ['48', '49'], keywords: ['longshoremen', 'dockworker', 'port', 'warehouse'] }
    ],
    
    // Common occupation/role keywords mapped to industries
    occupations: [
        { term: 'nurse', display: 'Nurses / Nursing', naics: '62', union: 'NNU' },
        { term: 'teacher', display: 'Teachers / Education', naics: '61', union: 'AFT' },
        { term: 'truck driver', display: 'Truck Drivers', naics: '48', union: 'IBT' },
        { term: 'warehouse worker', display: 'Warehouse Workers', naics: '49', union: 'IBT' },
        { term: 'janitor', display: 'Janitors / Custodians', naics: '56', union: 'SEIU' },
        { term: 'security guard', display: 'Security Guards', naics: '56', union: 'SEIU' },
        { term: 'hotel worker', display: 'Hotel Workers', naics: '72', union: 'UNITE HERE' },
        { term: 'grocery worker', display: 'Grocery / Retail Workers', naics: '44', union: 'UFCW' },
        { term: 'auto worker', display: 'Auto Workers', naics: '33', union: 'UAW' },
        { term: 'steelworker', display: 'Steelworkers / Metal Workers', naics: '33', union: 'USW' },
        { term: 'electrician', display: 'Electricians', naics: '23', union: 'IBEW' },
        { term: 'plumber', display: 'Plumbers / Pipefitters', naics: '23', union: 'UA' },
        { term: 'carpenter', display: 'Carpenters', naics: '23', union: 'UBC' },
        { term: 'machinist', display: 'Machinists', naics: '33', union: 'IAM' },
        { term: 'flight attendant', display: 'Flight Attendants', naics: '48', union: 'AFA' },
        { term: 'pilot', display: 'Pilots', naics: '48', union: 'ALPA' },
        { term: 'bus driver', display: 'Bus / Transit Drivers', naics: '48', union: 'ATU' },
        { term: 'postal worker', display: 'Postal Workers', naics: '49', union: 'APWU' },
        { term: 'home health aide', display: 'Home Health Aides', naics: '62', union: 'SEIU' },
        { term: 'actor', display: 'Actors / Performers', naics: '51', union: 'SAG-AFTRA' },
        { term: 'stagehand', display: 'Stagehands / Crew', naics: '51', union: 'IATSE' }
    ]
};

// Currently selected industry filter
let selectedIndustry = null;

// ==========================================
// TYPEAHEAD IMPLEMENTATION
// ==========================================
function setupTypeahead() {
    const industryInput = document.getElementById('industrySearch');
    const industryDropdown = document.getElementById('industryTypeahead');
    
    // Show dropdown on focus with popular options
    industryInput.addEventListener('focus', () => {
        if (industryInput.value.trim() === '') {
            showPopularIndustries();
        } else {
            filterTypeahead(industryInput.value);
        }
        industryDropdown.classList.add('open');
    });
    
    // Hide dropdown on blur (with delay for click handling)
    industryInput.addEventListener('blur', () => {
        setTimeout(() => industryDropdown.classList.remove('open'), 200);
    });
    
    // Filter on input
    industryInput.addEventListener('input', (e) => {
        const query = e.target.value.trim();
        if (query === '') {
            showPopularIndustries();
        } else {
            filterTypeahead(query);
        }
        industryDropdown.classList.add('open');
    });
    
    // Handle keyboard navigation
    industryInput.addEventListener('keydown', (e) => {
        handleTypeaheadKeyboard(e);
    });
}

function showPopularIndustries() {
    const dropdown = document.getElementById('industryTypeahead');
    
    // Show popular sectors
    const popularSectors = ['62', '61', '48', '72', '23', '33']; // Healthcare, Education, Transportation, Hospitality, Construction, Manufacturing
    const popularItems = typeaheadData.naics_sectors
        .filter(s => popularSectors.includes(s.code))
        .map(s => ({
            type: 'naics',
            code: s.code,
            name: s.name,
            category: 'Popular Industries'
        }));
    
    // Add popular unions
    const popularUnions = ['SEIU', 'IBT', 'UFCW', 'UAW', 'AFSCME'];
    const popularUnionItems = typeaheadData.unions
        .filter(u => popularUnions.includes(u.abbr))
        .map(u => ({
            type: 'union',
            abbr: u.abbr,
            name: u.name,
            category: 'Popular Unions'
        }));
    
    renderTypeaheadResults([...popularItems, ...popularUnionItems]);
}

function filterTypeahead(query) {
    const q = query.toLowerCase();
    const results = [];
    
    // Search NAICS sectors
    typeaheadData.naics_sectors.forEach(sector => {
        const nameMatch = sector.name.toLowerCase().includes(q);
        const codeMatch = sector.code.startsWith(q);
        const keywordMatch = sector.keywords.some(kw => kw.includes(q));
        
        if (nameMatch || codeMatch || keywordMatch) {
            results.push({
                type: 'naics',
                code: sector.code,
                name: sector.name,
                category: 'Industry (NAICS)',
                score: nameMatch ? 3 : (codeMatch ? 2 : 1)
            });
        }
    });
    
    // Search NAICS subsectors
    typeaheadData.naics_subsectors.forEach(sub => {
        const nameMatch = sub.name.toLowerCase().includes(q);
        const codeMatch = sub.code.startsWith(q);
        const keywordMatch = sub.keywords.some(kw => kw.includes(q));
        
        if (nameMatch || codeMatch || keywordMatch) {
            results.push({
                type: 'naics',
                code: sub.code,
                name: sub.name,
                parent: sub.parent,
                category: 'Industry (NAICS)',
                score: nameMatch ? 3 : (codeMatch ? 2 : 1)
            });
        }
    });
    
    // Search unions
    typeaheadData.unions.forEach(union => {
        const abbrMatch = union.abbr.toLowerCase().includes(q);
        const nameMatch = union.name.toLowerCase().includes(q);
        const keywordMatch = union.keywords.some(kw => kw.includes(q));
        
        if (abbrMatch || nameMatch || keywordMatch) {
            results.push({
                type: 'union',
                abbr: union.abbr,
                name: union.name,
                industries: union.industries,
                category: 'Union',
                score: abbrMatch ? 4 : (nameMatch ? 3 : 1)
            });
        }
    });
    
    // Search occupations
    typeaheadData.occupations.forEach(occ => {
        if (occ.term.includes(q) || occ.display.toLowerCase().includes(q)) {
            results.push({
                type: 'occupation',
                term: occ.term,
                display: occ.display,
                naics: occ.naics,
                union: occ.union,
                category: 'Occupation',
                score: occ.term.includes(q) ? 3 : 2
            });
        }
    });
    
    // Sort by score and limit results
    results.sort((a, b) => b.score - a.score);
    renderTypeaheadResults(results.slice(0, 12));
}

function renderTypeaheadResults(results) {
    const dropdown = document.getElementById('industryTypeahead');
    
    if (results.length === 0) {
        dropdown.innerHTML = `
            <div class="p-4 text-center text-warmgray-400 text-sm">
                No matching industries found
            </div>
        `;
        return;
    }
    
    // Group by category
    const grouped = {};
    results.forEach(r => {
        if (!grouped[r.category]) grouped[r.category] = [];
        grouped[r.category].push(r);
    });
    
    let html = '';
    
    for (const [category, items] of Object.entries(grouped)) {
        html += `<div class="typeahead-category px-3 py-2 text-xs font-semibold text-warmgray-400 uppercase tracking-wide bg-warmgray-50">${category}</div>`;
        
        items.forEach((item, idx) => {
            const dataAttrs = `data-type="${item.type}" data-code="${item.code || item.abbr || item.term}" data-name="${item.name || item.display}"`;
            
            if (item.type === 'naics') {
                html += `
                    <div class="typeahead-item" ${dataAttrs} onclick="selectTypeaheadItem(this)">
                        <div class="flex justify-between items-center">
                            <span>${item.name}</span>
                            <span class="text-xs text-warmgray-400 font-mono">NAICS ${item.code}</span>
                        </div>
                    </div>
                `;
            } else if (item.type === 'union') {
                html += `
                    <div class="typeahead-item" ${dataAttrs} data-industries="${(item.industries || []).join(',')}" onclick="selectTypeaheadItem(this)">
                        <div class="flex justify-between items-center">
                            <span><strong>${item.abbr}</strong> — ${item.name}</span>
                        </div>
                    </div>
                `;
            } else if (item.type === 'occupation') {
                html += `
                    <div class="typeahead-item" ${dataAttrs} data-naics="${item.naics}" data-union="${item.union}" onclick="selectTypeaheadItem(this)">
                        <div class="flex justify-between items-center">
                            <span>${item.display}</span>
                            <span class="text-xs text-warmgray-400">${item.union} · NAICS ${item.naics}</span>
                        </div>
                    </div>
                `;
            }
        });
    }
    
    dropdown.innerHTML = html;
}

function selectTypeaheadItem(element) {
    const type = element.dataset.type;
    const code = element.dataset.code;
    const name = element.dataset.name;
    
    const input = document.getElementById('industrySearch');
    
    if (type === 'naics') {
        input.value = name;
        selectedIndustry = { type: 'naics', code, name };
    } else if (type === 'union') {
        input.value = `${code} — ${name}`;
        selectedIndustry = { type: 'union', abbr: code, name, industries: element.dataset.industries?.split(',') };
    } else if (type === 'occupation') {
        input.value = name;
        selectedIndustry = { 
            type: 'occupation', 
            term: code, 
            display: name, 
            naics: element.dataset.naics,
            union: element.dataset.union
        };
    }
    
    // Close dropdown
    document.getElementById('industryTypeahead').classList.remove('open');
    
    // Show selected indicator
    showSelectedIndustryTag();
}

function showSelectedIndustryTag() {
    if (!selectedIndustry) return;
    
    const tagContainer = document.getElementById('industryTagContainer');
    
    let tagText = '';
    
    if (selectedIndustry.type === 'naics') {
        tagText = `NAICS ${selectedIndustry.code}: ${selectedIndustry.name}`;
    } else if (selectedIndustry.type === 'union') {
        tagText = `Union: ${selectedIndustry.abbr}`;
    } else if (selectedIndustry.type === 'occupation') {
        tagText = `${selectedIndustry.display} (${selectedIndustry.union} · NAICS ${selectedIndustry.naics})`;
    }
    
    tagContainer.innerHTML = `
        <span class="inline-flex items-center gap-2 px-3 py-1.5 bg-warmgray-900 text-white text-xs rounded-full">
            <span>${tagText}</span>
            <button onclick="clearIndustrySelection()" class="hover:text-warmgray-300 transition-colors">
                <svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12"/>
                </svg>
            </button>
        </span>
    `;
}

function clearIndustrySelection() {
    selectedIndustry = null;
    document.getElementById('industrySearch').value = '';
    const tagContainer = document.getElementById('industryTagContainer');
    if (tagContainer) tagContainer.innerHTML = '';
}

// Keyboard navigation for typeahead
let typeaheadFocusIndex = -1;

function handleTypeaheadKeyboard(e) {
    const dropdown = document.getElementById('industryTypeahead');
    const items = dropdown.querySelectorAll('.typeahead-item');
    
    if (!dropdown.classList.contains('open') || items.length === 0) return;
    
    if (e.key === 'ArrowDown') {
        e.preventDefault();
        typeaheadFocusIndex = Math.min(typeaheadFocusIndex + 1, items.length - 1);
        updateTypeaheadFocus(items);
    } else if (e.key === 'ArrowUp') {
        e.preventDefault();
        typeaheadFocusIndex = Math.max(typeaheadFocusIndex - 1, 0);
        updateTypeaheadFocus(items);
    } else if (e.key === 'Enter') {
        e.preventDefault();
        if (typeaheadFocusIndex >= 0 && items[typeaheadFocusIndex]) {
            selectTypeaheadItem(items[typeaheadFocusIndex]);
        }
    } else if (e.key === 'Escape') {
        dropdown.classList.remove('open');
        typeaheadFocusIndex = -1;
    }
}

function updateTypeaheadFocus(items) {
    items.forEach((item, idx) => {
        if (idx === typeaheadFocusIndex) {
            item.classList.add('bg-warmgray-100');
            item.scrollIntoView({ block: 'nearest' });
        } else {
            item.classList.remove('bg-warmgray-100');
        }
    });
}

// ==========================================
// SEARCH EXECUTION
// ==========================================
async function executeSearch() {
    // Show loading state
    showLoading(true);

    const params = new URLSearchParams();

    const mainSearch = document.getElementById('mainSearch').value.trim();
    const state = document.getElementById('stateFilter').value;
    const metro = document.getElementById('metroFilter').value;
    const city = document.getElementById('cityFilter').value;
    const sector = document.getElementById('sectorFilter').value;
    const sourceFilter = document.getElementById('sourceFilter') ? document.getElementById('sourceFilter').value : '';

    // Name search
    if (mainSearch) params.append('name', mainSearch);

    // Geography
    if (state) params.append('state', state);
    if (metro) params.append('metro', metro);
    if (city) params.append('city', city);

    // Sector filter - supported for both modes (PUBLIC_SECTOR queries ps_employers)
    if (sector) {
        params.append('sector', sector);
    }

    // Source filter (employer mode only, unified search)
    if (sourceFilter && currentMode === 'employers') {
        params.append('source_type', sourceFilter);
    }

    // Handle industry filter based on selection type
    if (selectedIndustry) {
        if (selectedIndustry.type === 'naics') {
            params.append('naics', selectedIndustry.code.substring(0, 2));
        } else if (selectedIndustry.type === 'union') {
            params.append('aff_abbr', selectedIndustry.abbr);
        } else if (selectedIndustry.type === 'occupation') {
            params.append('naics', selectedIndustry.naics);
        }
    }

    // Pagination
    params.append('limit', '15');
    params.append('offset', String((currentPage - 1) * 15));

    // Use unified search for employers, standard for unions
    const endpoint = currentMode === 'employers' ? 'employers/unified-search' : 'unions/search';

    try {
        const response = await fetch(`${API_BASE}/${endpoint}?${params}`);

        if (!response.ok) {
            throw new Error(`HTTP ${response.status}`);
        }

        const rawData = await response.json();

        // Transform API response to expected format
        const data = {
            total_count: rawData.total || 0,
            results: currentMode === 'employers' ? (rawData.employers || []) : (rawData.unions || [])
        };

        // Calculate aggregate stats from results
        if (currentMode === 'employers') {
            data.total_workers = data.results.reduce((sum, r) => sum + (r.unit_size || r.latest_unit_size || 0), 0);
            data.total_locals = new Set(data.results.map(r => r.union_fnum || r.latest_union_fnum).filter(Boolean)).size;
        } else {
            data.total_members = data.results.reduce((sum, r) => sum + (r.members || 0), 0);
            data.total_employers = data.results.reduce((sum, r) => sum + (r.f7_employer_count || 0), 0);
        }

        displayResults(data);
        updateUrl();

        // Load stats breakdown for employer searches
        if (currentMode === 'employers') {
            loadStatsBreakdown(params);
        }
    } catch (e) {
        console.error('Search failed:', e);
        showError('Search failed. Please check that the API server is running.');
    } finally {
        showLoading(false);
    }
}

async function loadStatsBreakdown(searchParams) {
    try {
        const response = await fetch(`${API_BASE}/stats/breakdown?${searchParams}`);
        if (!response.ok) return;
        
        const data = await response.json();
        populateStatsBreakdown(data);
    } catch (e) {
        console.log('Stats breakdown load failed:', e);
    }
}

function populateStatsBreakdown(data) {
    // Update totals in header
    if (data.totals) {
        document.getElementById('resultCount').textContent = formatNumber(data.totals.total_employers || 0);
        document.getElementById('resultWorkers').textContent = formatNumber(data.totals.total_workers || 0);
        document.getElementById('resultLocals').textContent = formatNumber(data.totals.total_locals || 0);
    }
    
    // By Sector
    const sectorEl = document.getElementById('statsBySector');
    if (data.by_sector && data.by_sector.length > 0) {
        const sectorNames = {
            'PRIVATE': 'Private',
            'PUBLIC_SECTOR': 'Public',
            'FEDERAL': 'Federal',
            'RLA': 'RLA',
            'UNKNOWN': 'Other'
        };
        sectorEl.innerHTML = data.by_sector.map(s => `
            <div class="flex justify-between">
                <span>${sectorNames[s.sector] || s.sector}</span>
                <span class="font-semibold">${formatNumber(s.worker_count)}</span>
            </div>
        `).join('');
    } else {
        sectorEl.innerHTML = '<div class="text-warmgray-400 text-sm">No data</div>';
    }
    
    // By Industry
    const industryEl = document.getElementById('statsByIndustry');
    if (data.by_industry && data.by_industry.length > 0) {
        industryEl.innerHTML = data.by_industry.map(i => `
            <div class="flex justify-between gap-2">
                <span class="truncate" title="${escapeHtml(i.industry_name || 'NAICS ' + i.naics_code)}">${escapeHtml(truncateText(i.industry_name || 'NAICS ' + i.naics_code, 20))}</span>
                <span class="font-semibold whitespace-nowrap">${formatNumber(i.worker_count)}</span>
            </div>
        `).join('');
    } else {
        industryEl.innerHTML = '<div class="text-warmgray-400 text-sm">No data</div>';
    }
    
    // By Metro
    const metroEl = document.getElementById('statsByMetro');
    if (data.by_metro && data.by_metro.length > 0) {
        metroEl.innerHTML = data.by_metro.map(m => `
            <div class="flex justify-between gap-2">
                <span class="truncate" title="${escapeHtml(m.city)}, ${m.state}">${escapeHtml(truncateText(m.city, 15))}, ${m.state}</span>
                <span class="font-semibold whitespace-nowrap">${formatNumber(m.worker_count)}</span>
            </div>
        `).join('');
    } else {
        metroEl.innerHTML = '<div class="text-warmgray-400 text-sm">No data</div>';
    }
    
    // By Union
    const unionEl = document.getElementById('statsByUnion');
    if (data.by_union && data.by_union.length > 0) {
        unionEl.innerHTML = data.by_union.map(u => `
            <div class="flex justify-between gap-2">
                <span class="truncate" title="${escapeHtml(u.aff_abbr)}">${escapeHtml(u.aff_abbr)}</span>
                <span class="font-semibold whitespace-nowrap">${formatNumber(u.worker_count)}</span>
            </div>
        `).join('');
    } else {
        unionEl.innerHTML = '<div class="text-warmgray-400 text-sm">No data</div>';
    }
}

function displaySampleResults() {
    if (currentMode === 'employers') {
        // Demo data for employer layout testing
        const sampleData = {
            total_count: 142,
            total_workers: 234567,
            total_locals: 38,
            results: [
                { employer_id: 1, employer_name: 'Kaiser Permanente', city: 'Oakland', state: 'CA', zip: '94612', latest_unit_size: 58420, union_name: 'SEIU-UHW Local 2005', aff_abbr: 'SEIU', sector: 'PRIVATE', naics: '622110', naics_sector_name: 'Hospitals', latitude: 37.8044, longitude: -122.2712, latest_notice_date: '2024-03-15' },
                { employer_id: 2, employer_name: 'Dignity Health', city: 'San Francisco', state: 'CA', zip: '94102', latest_unit_size: 12350, union_name: 'SEIU Local 121RN', aff_abbr: 'SEIU', sector: 'PRIVATE', naics: '622110', naics_sector_name: 'Hospitals', latitude: 37.7749, longitude: -122.4194, latest_notice_date: '2024-02-20' },
                { employer_id: 3, employer_name: 'Sutter Health', city: 'Sacramento', state: 'CA', zip: '95814', latest_unit_size: 8200, union_name: 'CNA/NNU', aff_abbr: 'NNU', sector: 'PRIVATE', naics: '622110', naics_sector_name: 'Hospitals', latitude: 38.5816, longitude: -121.4944, latest_notice_date: '2024-01-10' },
                { employer_id: 4, employer_name: 'UCLA Medical Center', city: 'Los Angeles', state: 'CA', zip: '90095', latest_unit_size: 6890, union_name: 'AFSCME Local 3299', aff_abbr: 'AFSCME', sector: 'PUBLIC_SECTOR', naics: '622110', naics_sector_name: 'Hospitals', latitude: 34.0667, longitude: -118.4452, latest_notice_date: '2023-12-05' },
                { employer_id: 5, employer_name: 'Stanford Health Care', city: 'Palo Alto', state: 'CA', zip: '94304', latest_unit_size: 5430, union_name: 'SEIU Local 2007', aff_abbr: 'SEIU', sector: 'PRIVATE', naics: '622110', naics_sector_name: 'Hospitals', latitude: 37.4419, longitude: -122.1430, latest_notice_date: '2024-04-01' },
            ]
        };
        displayResults(sampleData);
    } else {
        // Demo data for union layout testing
        const sampleUnionData = {
            total_count: 38,
            total_members: 892450,
            total_employers: 142,
            results: [
                { 
                    f_num: '545348', 
                    union_name: 'SEIU Local 2015', 
                    unit_name: 'SEIU Local 2015',
                    aff_abbr: 'SEIU', 
                    affiliation: 'Service Employees International Union',
                    city: 'Los Angeles', 
                    state: 'CA', 
                    members: 246113, 
                    employer_count: 847,
                    total_covered_workers: 312500,
                    sector: 'PRIVATE_MIXED',
                    receipts: 148372941,
                    assets: 168442757,
                    disbursements: 135107824,
                    top_industries: ['Healthcare', 'Home Care', 'Nursing Facilities'],
                    latitude: 34.0522,
                    longitude: -118.2437
                },
                { 
                    f_num: '31847', 
                    union_name: 'SEIU Local 1199', 
                    unit_name: 'SEIU United Healthcare Workers East',
                    aff_abbr: 'SEIU', 
                    affiliation: 'Service Employees International Union',
                    city: 'New York', 
                    state: 'NY', 
                    members: 324595, 
                    employer_count: 412,
                    total_covered_workers: 298000,
                    sector: 'PRIVATE_MIXED',
                    receipts: 224284814,
                    assets: 485717385,
                    disbursements: 220291696,
                    top_industries: ['Hospitals', 'Nursing Homes', 'Home Care'],
                    latitude: 40.7128,
                    longitude: -74.0060
                },
                { 
                    f_num: '15724', 
                    union_name: 'California Nurses Association', 
                    unit_name: 'California Nurses Association',
                    aff_abbr: 'NNU', 
                    affiliation: 'National Nurses United',
                    city: 'Oakland', 
                    state: 'CA', 
                    members: 133446, 
                    employer_count: 215,
                    total_covered_workers: 145000,
                    sector: 'PRIVATE',
                    receipts: 238604317,
                    assets: 513002801,
                    disbursements: 219526564,
                    top_industries: ['Hospitals', 'Medical Centers'],
                    latitude: 37.8044,
                    longitude: -122.2712
                },
                { 
                    f_num: '5568', 
                    union_name: 'Teamsters Joint Council 42', 
                    unit_name: 'Joint Council 42',
                    aff_abbr: 'IBT', 
                    affiliation: 'International Brotherhood of Teamsters',
                    city: 'Pomona', 
                    state: 'CA', 
                    members: 180006, 
                    employer_count: 1250,
                    total_covered_workers: 195000,
                    sector: 'PRIVATE',
                    receipts: 4485720,
                    assets: 3573068,
                    disbursements: 3784596,
                    top_industries: ['Trucking', 'Warehousing', 'Package Delivery'],
                    latitude: 34.0551,
                    longitude: -117.7500
                },
                { 
                    f_num: '25027', 
                    union_name: 'Carpenters Local 405', 
                    unit_name: 'Western States Regional Council of Carpenters',
                    aff_abbr: 'UBC', 
                    affiliation: 'United Brotherhood of Carpenters',
                    city: 'Los Angeles', 
                    state: 'CA', 
                    members: 88963, 
                    employer_count: 2100,
                    total_covered_workers: 92000,
                    sector: 'PRIVATE',
                    receipts: 386151115,
                    assets: 531402942,
                    disbursements: 458160991,
                    top_industries: ['Construction', 'Building Trades'],
                    latitude: 34.0522,
                    longitude: -118.2437
                },
            ]
        };
        displayResults(sampleUnionData);
    }
}

function displayResults(data) {
    currentResults = data.results || [];
    totalPages = Math.ceil((data.total_count || 0) / 50);
    resetKeyboardFocus();
    
    // Update counts based on mode
    if (currentMode === 'employers') {
        document.getElementById('resultCount').textContent = formatNumber(data.total_count || 0);
        document.getElementById('resultWorkers').textContent = formatNumber(data.total_workers || 0);
        document.getElementById('resultLocals').textContent = formatNumber(data.total_locals || 0);
        document.getElementById('resultCountLabel').textContent = 'employers';
        document.getElementById('resultWorkersLabel').textContent = 'workers';
        document.getElementById('resultLocalsLabel').textContent = 'locals';
    } else {
        document.getElementById('resultCount').textContent = formatNumber(data.total_count || 0);
        document.getElementById('resultWorkers').textContent = formatNumber(data.total_members || 0);
        document.getElementById('resultLocals').textContent = formatNumber(data.total_employers || 0);
        document.getElementById('resultCountLabel').textContent = 'unions';
        document.getElementById('resultWorkersLabel').textContent = 'members';
        document.getElementById('resultLocalsLabel').textContent = 'employers';
    }
    
    // Handle empty results
    if (currentResults.length === 0) {
        document.getElementById('emptyState').classList.remove('hidden');
        document.getElementById('listItems').classList.add('hidden');
        document.getElementById('emptyStateTitle').textContent = 'No results found';
        document.getElementById('emptyStateSubtitle').textContent = 'Try adjusting your search criteria';
        document.getElementById('exportBtn').disabled = true;
        document.getElementById('shareBtn').disabled = true;
        return;
    }
    
    // Enable export and share buttons
    document.getElementById('exportBtn').disabled = false;
    document.getElementById('shareBtn').disabled = false;
    
    // Hide empty state, show list
    document.getElementById('emptyState').classList.add('hidden');
    document.getElementById('listItems').classList.remove('hidden');
    
    // Render list items based on mode
    const listContainer = document.getElementById('listItems');
    
    if (currentMode === 'employers') {
        listContainer.innerHTML = currentResults.map((item, index) => {
            const itemId = item.canonical_id || item.employer_id;
            const workers = item.unit_size || item.latest_unit_size || 0;
            const unionInfo = item.union_name || item.latest_union_name || item.aff_abbr || '';
            const srcBadge = getSourceBadge(item.source_type);
            const flagIcon = item.flag_count > 0 ? '<span class="ml-1 text-orange-500" title="Has review flags">&#9873;</span>' : '';
            return `
            <div class="list-item p-4 cursor-pointer border-b border-warmgray-100 ${index === 0 ? 'selected' : ''}"
                 onclick="selectItem('${escapeHtml(itemId)}')"
                 data-id="${escapeHtml(itemId)}">
                <div class="flex justify-between items-start">
                    <div class="flex-1 min-w-0">
                        <div class="flex items-center gap-1.5">
                            ${srcBadge}${flagIcon}
                            <span class="font-semibold text-warmgray-900 truncate">${escapeHtml(item.employer_name || 'Unknown')}</span>
                        </div>
                        <div class="text-sm text-warmgray-500 mt-1 truncate">
                            ${unionInfo ? escapeHtml(unionInfo) + ' · ' : ''}${escapeHtml(item.city || '')}, ${escapeHtml(item.state || '')}
                        </div>
                    </div>
                    <div class="text-right ml-3">
                        <div class="text-lg font-bold text-accent-red">${workers > 0 ? formatNumber(workers) : '--'}</div>
                        <div class="text-xs text-warmgray-400">workers</div>
                    </div>
                </div>
            </div>`;
        }).join('');
    } else {
        listContainer.innerHTML = currentResults.map((item, index) => `
            <div class="list-item p-4 cursor-pointer border-b border-warmgray-100 ${index === 0 ? 'selected' : ''}" 
                 onclick="selectItem('${item.f_num}')" 
                 data-id="${item.f_num}">
                <div class="flex justify-between items-start">
                    <div class="flex-1 min-w-0">
                        <div class="font-semibold text-warmgray-900 truncate">${escapeHtml(formatUnionName(item))}</div>
                        <div class="text-sm text-warmgray-500 mt-1">
                            <span class="font-medium">${escapeHtml(item.aff_abbr || 'IND')}</span> · ${escapeHtml(item.city || '')}, ${escapeHtml(item.state || '')}
                        </div>
                        <div class="text-xs text-warmgray-400 mt-1">${formatNumber(item.f7_employer_count || 0)} employers covered</div>
                    </div>
                    <div class="text-right ml-3">
                        <div class="text-lg font-bold text-accent-red">${formatNumber(item.members || 0)}</div>
                        <div class="text-xs text-warmgray-400">members</div>
                    </div>
                </div>
            </div>
        `).join('');
    }
    
    // Show/hide pagination
    updatePagination();
    
    // Update results count
    document.getElementById('resultsCount').textContent = formatNumber(data.total_count || currentResults.length);
    
    // Update map if in map view
    if (currentView === 'map') {
        updateMapMarkers();
    }
    
    // Auto-select first item
    if (currentResults.length > 0) {
        const firstId = currentMode === 'employers'
            ? (currentResults[0].canonical_id || currentResults[0].employer_id)
            : currentResults[0].f_num;
        selectItem(firstId);
    }
}

function updatePagination() {
    const paginationEl = document.getElementById('pagination');
    const pageInfoEl = document.getElementById('pageInfo');
    const prevBtn = document.getElementById('prevPage');
    const nextBtn = document.getElementById('nextPage');
    
    if (totalPages <= 1) {
        paginationEl.classList.add('hidden');
        return;
    }
    
    paginationEl.classList.remove('hidden');
    pageInfoEl.textContent = `Page ${currentPage} of ${totalPages}`;
    
    prevBtn.disabled = currentPage <= 1;
    nextBtn.disabled = currentPage >= totalPages;
    
    prevBtn.onclick = () => { if (currentPage > 1) { currentPage--; executeSearch(); } };
    nextBtn.onclick = () => { if (currentPage < totalPages) { currentPage++; executeSearch(); } };
}

function clearResults() {
    currentResults = [];
    selectedItem = null;

    // Reset counts
    document.getElementById('resultCount').textContent = '0';
    document.getElementById('resultWorkers').textContent = '0';
    document.getElementById('resultLocals').textContent = '0';

    // Reset labels based on mode
    if (currentMode === 'employers') {
        document.getElementById('resultCountLabel').textContent = 'employers';
        document.getElementById('resultWorkersLabel').textContent = 'workers';
        document.getElementById('resultLocalsLabel').textContent = 'locals';
    } else {
        document.getElementById('resultCountLabel').textContent = 'unions';
        document.getElementById('resultWorkersLabel').textContent = 'members';
        document.getElementById('resultLocalsLabel').textContent = 'employers';
    }

    // Show empty states
    document.getElementById('emptyState').classList.remove('hidden');
    document.getElementById('listItems').classList.add('hidden');
    document.getElementById('listItems').innerHTML = '';
    document.getElementById('detailEmpty').classList.remove('hidden');
    document.getElementById('detailContent').classList.add('hidden');

    // Clear map marker
    if (detailMarker) {
        detailMap.removeLayer(detailMarker);
        detailMarker = null;
    }
    detailMap.setView([39.8283, -98.5795], 4);

    // Clear full map
    if (markerClusterGroup) {
        markerClusterGroup.clearLayers();
        mapMarkers.clear();
    }
    document.getElementById('mapSelectionPanel').classList.add('hidden');
    document.getElementById('resultsCount').textContent = '0';
    document.getElementById('mappableCount').textContent = '';
    document.getElementById('exportBtn').disabled = true;
    document.getElementById('shareBtn').disabled = true;
}
