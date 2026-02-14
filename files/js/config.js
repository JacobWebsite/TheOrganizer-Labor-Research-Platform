// config.js — Global state variables

const API_BASE = (window.LABOR_API_BASE || window.location.origin) + '/api';

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
