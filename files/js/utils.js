// utils.js — Shared utility functions

function formatNumber(num) {
    if (num === null || num === undefined) return '0';
    return num.toLocaleString();
}

function formatCompact(num) {
    if (num === null || num === undefined) return '0';
    if (num >= 1000000000) return (num / 1000000000).toFixed(1) + 'B';
    if (num >= 1000000) return (num / 1000000).toFixed(1) + 'M';
    if (num >= 1000) return (num / 1000).toFixed(0) + 'K';
    return formatNumber(Math.round(num));
}

function truncateText(text, maxLen) {
    if (!text) return '';
    return text.length > maxLen ? text.substring(0, maxLen) + '\u2026' : text;
}

function showLoading(isLoading) {
    const listContainer = document.getElementById('listItems');
    const emptyState = document.getElementById('emptyState');

    if (isLoading) {
        emptyState.classList.add('hidden');
        listContainer.classList.remove('hidden');
        listContainer.innerHTML = `
            <div class="p-8 text-center">
                <div class="animate-spin w-8 h-8 border-2 border-warmgray-300 border-t-warmgray-600 rounded-full mx-auto mb-3"></div>
                <div class="text-warmgray-500">Searching...</div>
            </div>
        `;
    }
}

function showError(message) {
    const listContainer = document.getElementById('listItems');
    listContainer.innerHTML = `
        <div class="p-8 text-center">
            <div class="text-red-500 mb-2">
                <svg class="w-10 h-10 mx-auto" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"/>
                </svg>
            </div>
            <div class="text-warmgray-700 font-medium">${message}</div>
            <button onclick="executeSearch()" class="mt-3 text-sm text-accent-red hover:underline">Try again</button>
        </div>
    `;
}

// Escape HTML to prevent XSS
function escapeHtml(str) {
    if (str === null || str === undefined) return '';
    if (typeof str !== 'string') str = String(str);
    return str.replace(/&/g, '&amp;')
              .replace(/</g, '&lt;')
              .replace(/>/g, '&gt;')
              .replace(/"/g, '&quot;')
              .replace(/'/g, '&#39;');
}

// Format union name for display: "SEIU Local 2015 (Los Angeles, CA)"
function formatUnionName(union) {
    const abbr = union.aff_abbr || '';
    let localPart = '';

    // Try to extract local number from union_name or unit_name
    const nameToCheck = union.union_name || union.unit_name || '';
    const localMatch = nameToCheck.match(/Local\s*(\d+[A-Z]*)/i);

    if (localMatch) {
        localPart = `Local ${localMatch[1]}`;
    } else if (union.desig_num) {
        localPart = `Local ${union.desig_num}`;
    } else if (union.unit_name && union.unit_name !== union.union_name) {
        // Use unit name if different
        localPart = union.unit_name;
    }

    // Build display name
    if (abbr && localPart) {
        return `${abbr} ${localPart}`;
    } else if (abbr) {
        return union.union_name || abbr;
    } else {
        return union.union_name || 'Unknown Union';
    }
}

function csvEscape(str) {
    if (str == null) return '';
    str = String(str);
    // Escape quotes and wrap in quotes if contains comma, quote, or newline
    if (str.includes(',') || str.includes('"') || str.includes('\n')) {
        return '"' + str.replace(/"/g, '""') + '"';
    }
    return str;
}

function downloadCSV(csv, filename) {
    const blob = new Blob([csv], { type: 'text/csv;charset=utf-8;' });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.setAttribute('href', url);
    link.setAttribute('download', filename);
    link.style.visibility = 'hidden';
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    URL.revokeObjectURL(url);
}

function getSourceBadge(sourceType) {
    const badges = {
        'F7': '<span class="inline-block px-1.5 py-0.5 text-xs font-semibold bg-blue-100 text-blue-700 rounded">F7</span>',
        'NLRB': '<span class="inline-block px-1.5 py-0.5 text-xs font-semibold bg-green-100 text-green-700 rounded">NLRB</span>',
        'VR': '<span class="inline-block px-1.5 py-0.5 text-xs font-semibold bg-orange-100 text-orange-700 rounded">VR</span>',
        'MANUAL': '<span class="inline-block px-1.5 py-0.5 text-xs font-semibold bg-purple-100 text-purple-700 rounded">Manual</span>',
        'PUBLIC': '<span class="inline-block px-1.5 py-0.5 text-xs font-semibold bg-teal-100 text-teal-700 rounded">Public</span>'
    };
    return badges[sourceType] || '';
}

function getSourceLabel(sourceType) {
    const labels = {
        'F7': 'F-7 Contract Filing',
        'NLRB': 'NLRB Election Record',
        'VR': 'Voluntary Recognition',
        'MANUAL': 'Research Discovery',
        'PUBLIC': 'Public Sector'
    };
    return labels[sourceType] || sourceType;
}

function getSectorBadgeClass(sector) {
    const sectorMap = {
        'PRIVATE': 'badge-private',
        'PRIVATE_MIXED': 'badge-private',
        'PUBLIC_SECTOR': 'badge-public',
        'PUBLIC_EDUCATION': 'badge-public',
        'FEDERAL': 'badge-federal',
        'RLA': 'badge-rla',
        'RAILROAD_AIRLINE_RLA': 'badge-rla'
    };
    return sectorMap[sector] || 'badge-private';
}

function formatSectorName(sector) {
    const sectorNames = {
        'PRIVATE': 'Private',
        'PRIVATE_MIXED': 'Private',
        'PUBLIC_SECTOR': 'Public',
        'PUBLIC_EDUCATION': 'Education',
        'FEDERAL': 'Federal',
        'RLA': 'RLA',
        'RAILROAD_AIRLINE_RLA': 'RLA'
    };
    return sectorNames[sector] || 'Private';
}

function formatCurrency(num) {
    if (!num) return '\u2014';
    if (num >= 1000000000) {
        return '$' + (num / 1000000000).toFixed(1) + 'B';
    } else if (num >= 1000000) {
        return '$' + (num / 1000000).toFixed(1) + 'M';
    } else if (num >= 1000) {
        return '$' + (num / 1000).toFixed(0) + 'K';
    }
    return '$' + num.toLocaleString();
}

function getTierBadgeClass(tier) {
    switch (tier) {
        case 'TOP': return 'bg-red-100 text-red-700';
        case 'HIGH': return 'bg-orange-100 text-orange-700';
        case 'MEDIUM': return 'bg-yellow-100 text-yellow-700';
        case 'LOW': return 'bg-warmgray-100 text-warmgray-600';
        default: return 'bg-warmgray-100 text-warmgray-600';
    }
}

function getScoreColor(score) {
    if (score >= 30) return 'text-green-600';   // TOP
    if (score >= 25) return 'text-blue-600';    // HIGH
    if (score >= 20) return 'text-yellow-600';  // MEDIUM
    return 'text-warmgray-400';                 // LOW
}

function getUnifiedScoreColor(score) {
    if (score >= 7) return 'text-green-600';     // TOP
    if (score >= 5) return 'text-blue-600';      // HIGH
    if (score >= 3.5) return 'text-yellow-600';  // MEDIUM
    return 'text-warmgray-400';                  // LOW
}
