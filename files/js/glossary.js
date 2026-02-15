// glossary.js -- Metrics Glossary modal

function openGlossary() {
    const modal = document.getElementById('glossaryModal');
    modal.classList.remove('hidden');
    modal.classList.add('flex');
    document.body.classList.add('modal-open');
    renderGlossary();
}

function closeGlossary() {
    const modal = document.getElementById('glossaryModal');
    modal.classList.add('hidden');
    modal.classList.remove('flex');
    document.body.classList.remove('modal-open');
}

function renderGlossary() {
    const content = document.getElementById('glossaryContent');

    const factorsHtml = SCORE_FACTORS.map(f => `
        <tr class="border-b border-warmgray-100">
            <td class="py-2 pr-4 font-medium text-warmgray-900">${f.label}</td>
            <td class="py-2 pr-4 text-right font-semibold">${f.max}</td>
            <td class="py-2 text-warmgray-500 text-sm">${getFactorDescription(f.key)}</td>
        </tr>
    `).join('');

    content.innerHTML = `
        <!-- Scoring Factors -->
        <div class="mb-6">
            <h3 class="text-sm font-bold text-warmgray-900 uppercase tracking-wide mb-3">Organizing Score Factors (max ${SCORE_MAX})</h3>
            <table class="w-full text-sm">
                <thead>
                    <tr class="border-b border-warmgray-200 text-xs text-warmgray-500 uppercase">
                        <th class="text-left py-2 pr-4">Factor</th>
                        <th class="text-right py-2 pr-4">Max</th>
                        <th class="text-left py-2">Description</th>
                    </tr>
                </thead>
                <tbody>${factorsHtml}</tbody>
            </table>
        </div>

        <!-- Score Tiers -->
        <div class="mb-6">
            <h3 class="text-sm font-bold text-warmgray-900 uppercase tracking-wide mb-3">Score Tiers</h3>
            <div class="grid grid-cols-4 gap-3">
                <div class="bg-green-50 rounded-lg p-3 text-center">
                    <div class="text-lg font-bold text-green-700">TOP</div>
                    <div class="text-xs text-green-600">Score >= 30</div>
                </div>
                <div class="bg-blue-50 rounded-lg p-3 text-center">
                    <div class="text-lg font-bold text-blue-700">HIGH</div>
                    <div class="text-xs text-blue-600">Score 25-29</div>
                </div>
                <div class="bg-yellow-50 rounded-lg p-3 text-center">
                    <div class="text-lg font-bold text-yellow-700">MEDIUM</div>
                    <div class="text-xs text-yellow-600">Score 20-24</div>
                </div>
                <div class="bg-warmgray-100 rounded-lg p-3 text-center">
                    <div class="text-lg font-bold text-warmgray-600">LOW</div>
                    <div class="text-xs text-warmgray-500">Score < 20</div>
                </div>
            </div>
        </div>

        <!-- Confidence Levels -->
        <div class="mb-6">
            <h3 class="text-sm font-bold text-warmgray-900 uppercase tracking-wide mb-3">Data Confidence</h3>
            <table class="w-full text-sm">
                <tbody>
                    <tr class="border-b border-warmgray-100">
                        <td class="py-2 pr-4"><span class="badge bg-green-50 text-green-700">HIGH</span></td>
                        <td class="py-2 text-warmgray-500">NAICS confidence >= 0.8 or 7+ score factors with data</td>
                    </tr>
                    <tr class="border-b border-warmgray-100">
                        <td class="py-2 pr-4"><span class="badge bg-yellow-50 text-yellow-700">MEDIUM</span></td>
                        <td class="py-2 text-warmgray-500">NAICS confidence 0.5-0.79 or 4-6 score factors with data</td>
                    </tr>
                    <tr class="border-b border-warmgray-100">
                        <td class="py-2 pr-4"><span class="badge bg-warmgray-100 text-warmgray-600">LOW</span></td>
                        <td class="py-2 text-warmgray-500">NAICS confidence < 0.5 or fewer than 4 score factors with data</td>
                    </tr>
                </tbody>
            </table>
        </div>

        <!-- Data Sources -->
        <div class="mb-6">
            <h3 class="text-sm font-bold text-warmgray-900 uppercase tracking-wide mb-3">Data Sources</h3>
            <table class="w-full text-sm">
                <tbody>
                    <tr class="border-b border-warmgray-100">
                        <td class="py-2 pr-4 font-medium text-warmgray-900">OLMS F-7</td>
                        <td class="py-2 text-warmgray-500">DOL employer-union bargaining relationships. Private sector only.</td>
                    </tr>
                    <tr class="border-b border-warmgray-100">
                        <td class="py-2 pr-4 font-medium text-warmgray-900">OSHA</td>
                        <td class="py-2 text-warmgray-500">Workplace safety inspections, violations, and penalties.</td>
                    </tr>
                    <tr class="border-b border-warmgray-100">
                        <td class="py-2 pr-4 font-medium text-warmgray-900">NLRB</td>
                        <td class="py-2 text-warmgray-500">Union elections (RC/RD/RM) and ULP cases (CA/CB).</td>
                    </tr>
                    <tr class="border-b border-warmgray-100">
                        <td class="py-2 pr-4 font-medium text-warmgray-900">WHD</td>
                        <td class="py-2 text-warmgray-500">Wage & Hour Division enforcement actions and back wages.</td>
                    </tr>
                    <tr class="border-b border-warmgray-100">
                        <td class="py-2 pr-4 font-medium text-warmgray-900">BLS</td>
                        <td class="py-2 text-warmgray-500">Bureau of Labor Statistics occupational projections and matrix codes.</td>
                    </tr>
                    <tr class="border-b border-warmgray-100">
                        <td class="py-2 pr-4 font-medium text-warmgray-900">IRS 990</td>
                        <td class="py-2 text-warmgray-500">Nonprofit/union financial disclosures (assets, receipts).</td>
                    </tr>
                    <tr class="border-b border-warmgray-100">
                        <td class="py-2 pr-4 font-medium text-warmgray-900">SAM.gov</td>
                        <td class="py-2 text-warmgray-500">Federal contractor registrations (UEI, CAGE, NAICS).</td>
                    </tr>
                    <tr class="border-b border-warmgray-100">
                        <td class="py-2 pr-4 font-medium text-warmgray-900">SEC EDGAR</td>
                        <td class="py-2 text-warmgray-500">Public company filings (CIK, EIN, state of incorporation).</td>
                    </tr>
                    <tr class="border-b border-warmgray-100">
                        <td class="py-2 pr-4 font-medium text-warmgray-900">GLEIF</td>
                        <td class="py-2 text-warmgray-500">Legal Entity Identifiers for global entity resolution.</td>
                    </tr>
                </tbody>
            </table>
        </div>

        <!-- Match Rate Denominators -->
        <div>
            <h3 class="text-sm font-bold text-warmgray-900 uppercase tracking-wide mb-3">Match Rate Context</h3>
            <p class="text-sm text-warmgray-600 mb-2">
                Match rates are reported from two perspectives:
            </p>
            <ul class="text-sm text-warmgray-600 list-disc list-inside space-y-1">
                <li><strong>F7 employer perspective:</strong> % of F7 employers matched to a given source (e.g., OSHA 47.3%)</li>
                <li><strong>Source perspective:</strong> % of source records matched to F7 employers (e.g., OSHA 13.7%)</li>
                <li>Source-perspective rates are lower because source tables (e.g., OSHA 1M+ establishments) are much larger than F7 (114K employers)</li>
            </ul>
        </div>
    `;
}

function getFactorDescription(key) {
    const descriptions = {
        size: 'Employee count sweet spot: 50-250 employees score highest (organizing-favorable size)',
        osha: 'OSHA violation rate vs industry average, with severity bonus for willful/repeat violations',
        geographic: 'State labor climate: non-RTW states, higher NLRB win rates score better',
        contracts: 'Federal/state/local government contracts (leverage for organizing)',
        labor_history: 'Prior NLRB elections, ULP charges, and WHD violations at employer',
        projections: 'BLS occupational projections: growing industries score higher',
        similarity: 'Similarity to successfully organized employers (Gower distance model)',
        nlrb: 'NLRB predicted election win rate for this employer/industry/state combination',
        sector_density: 'Union density in employer\'s sector/NAICS: higher density = more favorable'
    };
    return descriptions[key] || '';
}
