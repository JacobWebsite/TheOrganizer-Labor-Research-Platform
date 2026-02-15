// config.js — Global state variables

const API_BASE = (window.LABOR_API_BASE || window.location.origin) + '/api';

// Canonical scoring system — 9 factors, unified across all views
const SCORE_FACTORS = [
    { key: 'company_unions',   label: 'Existing Unions',   max: 20, color: 'bg-indigo-500', desc: 'Related company locations with union presence' },
    { key: 'industry_density', label: 'Industry Density',  max: 10, color: 'bg-blue-500',   desc: 'Union membership rate in NAICS sector' },
    { key: 'geographic',       label: 'Geographic',        max: 10, color: 'bg-purple-500',  desc: 'State union membership vs national average' },
    { key: 'size',             label: 'Employer Size',     max: 10, color: 'bg-yellow-500',  desc: 'Sweet spot 50-250 employees' },
    { key: 'osha',             label: 'OSHA Violations',   max: 10, color: 'bg-red-500',     desc: 'Workplace safety violations on record' },
    { key: 'nlrb',             label: 'NLRB Patterns',     max: 10, color: 'bg-green-500',   desc: 'Historical election win patterns' },
    { key: 'contracts',        label: 'Govt Contracts',    max: 10, color: 'bg-orange-500',  desc: 'NY State & NYC contract funding' },
    { key: 'projections',      label: 'Industry Growth',   max: 10, color: 'bg-teal-500',    desc: 'BLS industry employment projections' },
    { key: 'similarity',       label: 'Union Similarity',  max: 10, color: 'bg-cyan-500',    desc: 'Gower distance to unionized employers' }
];
const SCORE_MAX = SCORE_FACTORS.reduce((sum, f) => sum + f.max, 0); // 100

let currentMode = 'employers'; // 'employers' or 'unions'
let currentResults = [];
let selectedItem = null;
let currentPage = 1;
let totalPages = 1;
let detailMap = null;
let detailMarker = null;

// Map view state
let currentView = 'list'; // 'list' or 'map'
let fullMap = null;
let markerClusterGroup = null;
let mapMarkers = new Map(); // id -> marker

// Comparison state
let comparisonItems = [null, null]; // [leftItem, rightItem]

// App mode state
let currentAppMode = 'territory'; // 'territory' | 'search' | 'deepdive'
let territoryContext = { union: '', state: '', metro: '' };
let deepDiveReturnMode = 'territory';
let territoryMap = null;
let territoryMarkerCluster = null;
let territoryCharts = {};  // track Chart.js instances for cleanup
let territoryDataCache = {}; // cache fetched territory data
