document.addEventListener('DOMContentLoaded', () => {
    // DOM elements
    const historyContainer = document.getElementById('history-container');
    const emptyHistory = document.getElementById('empty-history');
    const searchInput = document.getElementById('search-input');
    const filterType = document.getElementById('filter-type');
    const filterYear = document.getElementById('filter-year');
    const sortBy = document.getElementById('sort-by');
    const viewToggle = document.getElementById('view-toggle');
    const themeToggle = document.getElementById('theme-toggle');
    const statsToggle = document.getElementById('stats-toggle');
    const dashboard = document.getElementById('dashboard');
    const loadingIndicator = document.getElementById('loading-indicator');
    const pagination = document.getElementById('pagination');
    const prevPageBtn = document.getElementById('prev-page');
    const nextPageBtn = document.getElementById('next-page');
    const pageInfo = document.getElementById('page-info');
    const modalBackdrop = document.getElementById('modal-backdrop');
    const expandedContentTemplate = document.getElementById('expanded-content-template');

    // Stats elements
    const totalCountEl = document.getElementById('total-count');
    const moviesCountEl = document.getElementById('movies-count');
    const showsCountEl = document.getElementById('shows-count');
    const animeCountEl = document.getElementById('anime-count');

    // State
    let historyData = [];
    let activeMediaCard = null;
    let currentView = localStorage.getItem('simkl_history_view') || 'grid';
    let currentTheme = localStorage.getItem('simkl_history_theme') || 'dark'; // Default to dark
    let showStats = localStorage.getItem('simkl_history_stats') === 'true';
    let currentPage = 1;
    let itemsPerPage = 24; // Default for grid view
    let watchChart = null;

    // Apply saved view
    if (currentView === 'list') {
        historyContainer.classList.add('list-view');
        viewToggle.innerHTML = '<i class="ph-duotone ph-grid-four"></i>';
        itemsPerPage = 15; // More items per page in list view
    } else {
        viewToggle.innerHTML = '<i class="ph-duotone ph-list"></i>';
    }

    // Apply saved theme
    if (currentTheme === 'dark') {
        document.body.classList.add('dark-mode');
        themeToggle.innerHTML = '<i class="ph-duotone ph-sun"></i>';
    } else {
        themeToggle.innerHTML = '<i class="ph-duotone ph-moon"></i>';
    }

    // Apply saved stats visibility
    if (showStats) {
        dashboard.style.display = 'block';
    }

    // Apply proxy only to Simkl poster URLs, not to placeholder images
    function getProxiedImageUrl(url) {
        // If no URL is provided, return a default placeholder
        if (!url) {
            console.log('No URL provided to getProxiedImageUrl');
            return `https://via.placeholder.com/150x225.webp?text=No+Poster`;
        }
        

        
        // Check if it's a Simkl poster URL (contains simkl.in/posters)
        if (url.includes('https://simkl.in/posters/')) {
            // Use direct URL without proxy - wsrv.nl is causing issues
           
            return url;
        }

        return url;
    }

    // Load watch history data
    function loadHistory() {
        loadingIndicator.style.display = 'flex';
        historyContainer.style.display = 'none';
        emptyHistory.style.display = 'none';

        try {
            if (typeof HISTORY_DATA !== 'undefined') {
                historyData = HISTORY_DATA;
               
                processHistoryData();
                loadingIndicator.style.display = 'none';
                renderHistory();
            } else {
                console.error('HISTORY_DATA is not defined. Cannot load history.');
                loadingIndicator.style.display = 'none';
                showEmptyState("History data (data.js) not found.");
            }
        } catch (error) {
            console.error('Error loading history data:', error);
            loadingIndicator.style.display = 'none';
            showEmptyState("Failed to load history data.");
        }
    }

    // Process history data
    function processHistoryData() {
        // Populate years filter
        const years = new Set(historyData.map(item => item.year).filter(Boolean));
        const sortedYears = Array.from(years).sort((a, b) => b - a);

        // Clear existing options except "All Years"
        while (filterYear.options.length > 1) filterYear.remove(1);

        sortedYears.forEach(year => {
            const option = document.createElement('option');
            option.value = year;
            option.textContent = year;
            filterYear.appendChild(option);
        });

        updateStatistics();
    }

    // Update statistics panel and chart
    function updateStatistics() {
        // Calculate basic statistics
        const movieCount = historyData.filter(item => item.type === 'movie').length;
        const uniqueShowIds = new Set(historyData.filter(item => item.type === 'show' || item.type === 'tv').map(item => item.simkl_id || `${item.title}-${item.year}`));
        const uniqueAnimeIds = new Set(historyData.filter(item => item.type === 'anime').map(item => item.simkl_id || `${item.title}-${item.year}`));

        // Update count displays
        totalCountEl.textContent = historyData.length;
        moviesCountEl.textContent = movieCount;
        showsCountEl.textContent = uniqueShowIds.size;
        animeCountEl.textContent = uniqueAnimeIds.size;

        // Create statistics visualizations
        createWatchTrendChart();
        // createMediaTypeDistribution();
        createViewingTimesChart();
    }

    // Create or update the watch trend chart with enhanced visuals
    function createWatchTrendChart() {
        if (typeof Chart === 'undefined') return;
        
        // Get the chart canvas
        const chartCanvas = document.getElementById('watch-trend-chart');
        if (!chartCanvas) return;
        
        // Process data for monthly trend
        const watchData = processWatchTrendData();
        const ctx = chartCanvas.getContext('2d');

        // Clean up existing chart
        if (window.watchChart) window.watchChart.destroy();
        
        // Set chart configuration based on theme
        const isDarkMode = document.body.classList.contains('dark-mode');
        const chartConfig = getWatchTrendChartConfig(watchData, isDarkMode);
        
        // Create new chart
        window.watchChart = new Chart(ctx, chartConfig);
        
        // Add title to the chart if needed
        addChartTitle(chartCanvas, 'Viewing Activity (Last 12 Months)', 'watch-trend-title');
    }
    
    // Process data for watch trend chart
    function processWatchTrendData() {
        // Create monthly buckets for the last 12 months
        const watchesByMonth = {};
        const currentDate = new Date();
        
        // Generate data for the last 12 months including current month
        for (let i = 11; i >= 0; i--) {
            const date = new Date(currentDate);  // Create a new date object from current date
            date.setDate(1);  // Set to first day of month to avoid issues with month lengths
            date.setMonth(currentDate.getMonth() - i);
            
            const monthKey = date.toISOString().slice(0, 7); // YYYY-MM format
            const month = date.getMonth();
            const year = date.getFullYear();
            
            // Store with display label for better readability
            watchesByMonth[monthKey] = { 
                month: monthKey, 
                count: 0,
                label: new Date(year, month).toLocaleDateString(undefined, { month: 'short', year: 'numeric' })
            };
        }

        // Count watched items by month
        historyData.forEach(item => {
            if (item.watched_at) {
                try {
                    const watchDate = new Date(item.watched_at);
                    const watchMonth = watchDate.toISOString().slice(0, 7); // YYYY-MM
                    
                    if (watchesByMonth[watchMonth]) {
                        watchesByMonth[watchMonth].count++;
                    }
                } catch (e) {
                    // Silently handle error
                }
            }
        });

        // Sort the chart data chronologically
        return Object.values(watchesByMonth).sort((a, b) => a.month.localeCompare(b.month));
    }
    
    // Get chart configuration for watch trend
    function getWatchTrendChartConfig(chartData, isDarkMode) {
        // Extract labels and data
        const labels = chartData.map(item => item.label);
        const counts = chartData.map(item => item.count);
        
        // Calculate moving average for trend line
        const movingAvg = calculateMovingAverage(counts, 2);
        
        // Define colors based on theme
        const gridColor = isDarkMode ? 'rgba(255, 255, 255, 0.08)' : 'rgba(0, 0, 0, 0.04)';
        const labelColor = isDarkMode ? 'rgba(255, 255, 255, 0.7)' : 'rgba(0, 0, 0, 0.7)';
        const tooltipBgColor = isDarkMode ? 'rgba(22, 28, 36, 0.95)' : 'rgba(255, 255, 255, 0.98)';
        const tooltipBorderColor = isDarkMode ? 'rgba(255, 255, 255, 0.15)' : 'rgba(0, 0, 0, 0.05)';
        
        // Theme-specific colors for primary data
        const primaryColor = 'var(--simkl-red)';
        const primaryColorTransparent = isDarkMode ? 'rgba(230, 50, 50, 0.08)' : 'rgba(230, 50, 50, 0.04)';
        
        // Create gradient for area fill
        const canvas = document.getElementById('watch-trend-chart');
        const ctx = canvas.getContext('2d');
        const gradient = ctx.createLinearGradient(0, 0, 0, canvas.offsetHeight);
        
        if (isDarkMode) {
            gradient.addColorStop(0, 'rgba(230, 50, 50, 0.35)');
            gradient.addColorStop(0.5, 'rgba(230, 50, 50, 0.15)');
            gradient.addColorStop(1, 'rgba(230, 50, 50, 0.02)');
        } else {
            gradient.addColorStop(0, 'rgba(230, 50, 50, 0.25)');
            gradient.addColorStop(0.5, 'rgba(230, 50, 50, 0.1)');
            gradient.addColorStop(1, 'rgba(230, 50, 50, 0.02)');
        }

        return {
            type: 'line',
            data: {
                labels: labels,
                datasets: [
                    {
                        label: 'Watched Items',
                        data: counts,
                        borderColor: primaryColor,
                        backgroundColor: gradient,
                        borderWidth: 2.5,
                        pointBackgroundColor: primaryColor,
                        pointBorderColor: isDarkMode ? '#1f2937' : '#ffffff',
                        pointHoverBackgroundColor: primaryColor,
                        pointHoverBorderColor: isDarkMode ? '#1f2937' : '#ffffff',
                        pointBorderWidth: 2,
                        pointRadius: 4,
                        pointHoverRadius: 6,
                        fill: true,
                        tension: 0.3,
                        order: 1
                    },
                    {
                        label: 'Trend',
                        data: movingAvg,
                        borderColor: isDarkMode ? 'rgba(255, 255, 255, 0.5)' : 'rgba(0, 0, 0, 0.5)',
                        borderWidth: 1.5,
                        borderDash: [5, 5],
                        pointRadius: 0,
                        fill: false,
                        tension: 0.4,
                        order: 0
                    }
                ]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                interaction: {
                    mode: 'index',
                    intersect: false
                },
                plugins: {
                    legend: { 
                        display: false
                    },
                    tooltip: {
                        mode: 'index',
                        intersect: false,
                        backgroundColor: tooltipBgColor,
                        titleColor: isDarkMode ? '#ffffff' : '#000000',
                        bodyColor: isDarkMode ? 'rgba(255, 255, 255, 0.8)' : 'rgba(0, 0, 0, 0.7)',
                        borderColor: tooltipBorderColor,
                        borderWidth: 1,
                        padding: 12,
                        cornerRadius: 8,
                        boxPadding: 6,
                        titleFont: {
                            weight: 'bold',
                            size: 14
                        },
                        bodyFont: {
                            size: 13
                        },
                        callbacks: {
                            title: function(context) {
                                return context[0].label;
                            },
                            label: function(context) {
                                const datasetLabel = context.dataset.label || '';
                                const value = context.parsed.y;
                                if (datasetLabel === 'Trend') {
                                    return `Trend: ${value.toFixed(1)}`;
                                }
                                return `Watched: ${value}`;
                            }
                        },
                        itemSort: function(a, b) {
                            // Show main dataset first
                            return b.datasetIndex - a.datasetIndex;
                        }
                    }
                },
                scales: {
                    y: {
                        beginAtZero: true,
                        ticks: { 
                            precision: 0, 
                            color: labelColor,
                            font: {
                                weight: '500',
                                size: 11
                            }
                        },
                        grid: { 
                            color: gridColor, 
                            drawBorder: false,
                            lineWidth: 0.8
                        },
                        border: {
                            display: false
                        }
                    },
                    x: {
                        ticks: { 
                            color: labelColor,
                            font: {
                                weight: '500',
                                size: 11
                            },
                            maxRotation: 45,
                            minRotation: 0
                        },
                        grid: { 
                            display: false 
                        },
                        border: {
                            display: false
                        }
                    }
                },
                hover: {
                    mode: 'index',
                    intersect: false
                },
                animation: {
                    duration: 1000,
                    easing: 'easeOutQuart'
                }
            }
        };
    }
    
    // Calculate moving average for trend line
    function calculateMovingAverage(data, windowSize) {
        const result = [];
        
        // Fill start with nulls (for proper chart alignment)
        for (let i = 0; i < windowSize; i++) {
            result.push(null);
        }
        
        for (let i = windowSize; i < data.length; i++) {
            let sum = 0;
            for (let j = 0; j < windowSize; j++) {
                sum += data[i - j];
            }
            result.push(sum / windowSize);
        }
        
        return result;
    }
    
    // Create media type distribution chart (pie/doughnut chart)
    function createMediaTypeDistribution() {
        if (typeof Chart === 'undefined') return;
        
        const chartCanvas = document.getElementById('media-type-chart');
        if (!chartCanvas) return;
        
        // Cleanup existing chart
        if (window.mediaTypeChart) window.mediaTypeChart.destroy();
        
        // Calculate counts for each media type
        const movieCount = historyData.filter(item => item.type === 'movie').length;
        const showCount = historyData.filter(item => item.type === 'show' || item.type === 'tv').length;
        const animeCount = historyData.filter(item => item.type === 'anime').length;
        
        // Skip if no data
        if (movieCount + showCount + animeCount === 0) return;
        
        const isDarkMode = document.body.classList.contains('dark-mode');
        const backgroundColor = isDarkMode ? '#1f2937' : '#ffffff';
        const textColor = isDarkMode ? '#ffffff' : '#000000';
        const borderColor = isDarkMode ? '#111827' : '#f3f4f6';
        
        window.mediaTypeChart = new Chart(chartCanvas, {
            type: 'doughnut',
            data: {
                labels: ['Movies', 'TV Shows', 'Anime'],
                datasets: [{
                    data: [movieCount, showCount, animeCount],
                    backgroundColor: [
                        'rgba(59, 130, 246, 0.8)',
                        'rgba(249, 115, 22, 0.8)',
                        'rgba(34, 197, 94, 0.8)'
                    ],
                    borderColor: borderColor,
                    borderWidth: 1,
                    hoverOffset: 10
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                cutout: '65%',
                plugins: {
                    legend: {
                        position: 'right',
                        labels: {
                            color: textColor,
                            padding: 15,
                            usePointStyle: true,
                            pointStyle: 'circle',
                            font: {
                                size: 13
                            }
                        }
                    },
                    tooltip: {
                        backgroundColor: isDarkMode ? 'rgba(22, 28, 36, 0.95)' : 'rgba(255, 255, 255, 0.98)',
                        titleColor: textColor,
                        bodyColor: isDarkMode ? 'rgba(255, 255, 255, 0.8)' : 'rgba(0, 0, 0, 0.7)',
                        borderColor: isDarkMode ? 'rgba(255, 255, 255, 0.15)' : 'rgba(0, 0, 0, 0.05)',
                        borderWidth: 1,
                        padding: 12,
                        cornerRadius: 8,
                        callbacks: {
                            label: function(context) {
                                const value = context.raw;
                                const total = context.chart.data.datasets[0].data.reduce((sum, val) => sum + val, 0);
                                const percentage = ((value / total) * 100).toFixed(1);
                                return `${context.label}: ${value} (${percentage}%)`;
                            }
                        }
                    }
                },
                animation: {
                    animateRotate: true,
                    animateScale: true,
                    duration: 1000,
                    easing: 'easeOutQuart'
                }
            }
        });
        
        addChartTitle(chartCanvas, 'Content Distribution', 'media-type-title');
    }
    
    // Create viewing times chart (by hour of day)
    function createViewingTimesChart() {
        if (typeof Chart === 'undefined') return;
        
        const chartCanvas = document.getElementById('viewing-times-chart');
        if (!chartCanvas) return;
        
        // Cleanup existing chart
        if (window.viewingTimesChart) window.viewingTimesChart.destroy();
        
        // Initialize hours array (0-23)
        const hourCounts = Array(24).fill(0);
        let totalEntries = 0;
        
        // Count entries by hour
        historyData.forEach(item => {
            if (item.watched_at) {
                try {
                    const watchDate = new Date(item.watched_at);
                    const hour = watchDate.getHours();
                    hourCounts[hour]++;
                    totalEntries++;
                } catch (e) {
                    // Skip invalid dates
                }
            }
        });
        
        // Skip if no data
        if (totalEntries === 0) return;
        
        // Format hour labels (12-hour format with AM/PM)
        const hourLabels = Array(24).fill().map((_, i) => {
            const hour12 = i % 12 || 12;
            const ampm = i < 12 ? 'AM' : 'PM';
            return `${hour12}${ampm}`;
        });
        
        const isDarkMode = document.body.classList.contains('dark-mode');
        const colors = getChartColors(isDarkMode);
        
        // Create gradient for bars
        const ctx = chartCanvas.getContext('2d');
        const gradient = ctx.createLinearGradient(0, 0, 0, chartCanvas.offsetHeight);
        gradient.addColorStop(0, isDarkMode ? 'rgba(167, 139, 250, 0.9)' : 'rgba(124, 58, 237, 0.85)');
        gradient.addColorStop(1, isDarkMode ? 'rgba(167, 139, 250, 0.3)' : 'rgba(124, 58, 237, 0.35)');
        
        window.viewingTimesChart = new Chart(chartCanvas, {
            type: 'bar',
            data: {
                labels: hourLabels,
                datasets: [{
                    label: 'Activity',
                    data: hourCounts,
                    backgroundColor: gradient,
                    borderColor: isDarkMode ? 'rgba(167, 139, 250, 1)' : 'rgba(124, 58, 237, 1)',
                    borderWidth: 1,
                    borderRadius: 4,
                    barThickness: 'flex',
                    maxBarThickness: 25
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: {
                        display: false
                    },
                    tooltip: {
                        backgroundColor: colors.tooltipBg,
                        titleColor: colors.tooltipTitle,
                        bodyColor: colors.tooltipBody,
                        borderColor: colors.tooltipBorder,
                        borderWidth: 1,
                        padding: 10,
                        cornerRadius: 8,
                        callbacks: {
                            title: function(context) {
                                const hour = context[0].dataIndex;
                                const hour12 = hour % 12 || 12;
                                const ampm = hour < 12 ? 'AM' : 'PM';
                                return `${hour12}:00 ${ampm}`;
                            },
                            label: function(context) {
                                const value = context.parsed.y;
                                return `${value} items watched`;
                            }
                        }
                    }
                },
                scales: {
                    y: {
                        beginAtZero: true,
                        ticks: {
                            precision: 0,
                            color: colors.label,
                            font: {
                                size: 11
                            }
                        },
                        grid: {
                            color: colors.grid,
                            drawBorder: false
                        },
                        border: {
                            display: false
                        }
                    },
                    x: {
                        ticks: {
                            color: colors.label,
                            font: {
                                size: 10
                            },
                            maxRotation: 0
                        },
                        grid: {
                            display: false
                        },
                        border: {
                            display: false
                        }
                    }
                },
                animation: {
                    duration: 1000,
                    easing: 'easeOutQuart'
                }
            }
        });
        
        addChartTitle(chartCanvas, 'Viewing Times (Hour of Day)', 'viewing-times-title');
    }
    

    
    // Helper function to add chart title
    function addChartTitle(chartCanvas, titleText, titleId) {
        const chartContainer = chartCanvas.parentElement;
        if (!chartContainer) return;
        
        let chartTitle = chartContainer.querySelector(`.chart-title${titleId ? '#' + titleId : ''}`);
        if (!chartTitle) {
            chartTitle = document.createElement('div');
            chartTitle.className = 'chart-title';
            if (titleId) chartTitle.id = titleId;
            chartTitle.textContent = titleText;
            chartContainer.insertBefore(chartTitle, chartCanvas);
        } else {
            chartTitle.textContent = titleText;
        }
    }
    
    // Get consistent chart colors based on theme
    function getChartColors(isDarkMode) {
        return {
            grid: isDarkMode ? 'rgba(255, 255, 255, 0.08)' : 'rgba(0, 0, 0, 0.04)',
            label: isDarkMode ? 'rgba(255, 255, 255, 0.7)' : 'rgba(0, 0, 0, 0.7)',
            tooltipBg: isDarkMode ? 'rgba(22, 28, 36, 0.95)' : 'rgba(255, 255, 255, 0.98)',
            tooltipTitle: isDarkMode ? '#ffffff' : '#000000',
            tooltipBody: isDarkMode ? 'rgba(255, 255, 255, 0.8)' : 'rgba(0, 0, 0, 0.7)',
            tooltipBorder: isDarkMode ? 'rgba(255, 255, 255, 0.15)' : 'rgba(0, 0, 0, 0.05)'
        };
    }
    
    // Generate a gradient of colors between two RGB values
    function generateColorGradient(rgbStart, rgbEnd, steps) {
        const result = [];
        
        for (let i = 0; i < steps; i++) {
            const r = Math.round(rgbStart[0] + (rgbEnd[0] - rgbStart[0]) * i / (steps - 1));
            const g = Math.round(rgbStart[1] + (rgbEnd[1] - rgbStart[1]) * i / (steps - 1));
            const b = Math.round(rgbStart[2] + (rgbEnd[2] - rgbStart[2]) * i / (steps - 1));
            result.push(`rgba(${r}, ${g}, ${b}, 0.8)`);
        }
        
        return result;
    }

    // Format date for display (relative or absolute)
    function formatDate(dateString) {
        if (!dateString) return 'Unknown date';
        try {
            const date = new Date(dateString);
            if (isNaN(date.getTime())) return 'Invalid date';

            const now = new Date();
            const diffSeconds = Math.floor((now - date) / 1000);
            const diffDays = Math.floor(diffSeconds / (60 * 60 * 24));

            if (diffSeconds < 60) return 'Just now';
            if (diffSeconds < 3600) return `${Math.floor(diffSeconds / 60)}m ago`;
            if (diffSeconds < 86400) return `${Math.floor(diffSeconds / 3600)}h ago`;
            if (diffDays === 1) return 'Yesterday';
            if (diffDays < 7) return `${diffDays}d ago`;
            return date.toLocaleDateString(undefined, { year: 'numeric', month: 'short', day: 'numeric' });
        } catch (e) {
            return 'Invalid date';
        }
    }

    // Format timestamp for detailed view
    function formatTimestamp(dateString) {
        if (!dateString) return '-';
        try {
            const date = new Date(dateString);
            if (isNaN(date.getTime())) return '-';
            return date.toLocaleString(undefined, {
                year: 'numeric', month: 'short', day: 'numeric',
                hour: 'numeric', minute: '2-digit', hour12: true
            });
        } catch (e) {
            return '-';
        }
    }

    // Filter history based on current selections
    function filterHistory() {
        const searchTerm = searchInput.value.toLowerCase().trim();
        const typeFilter = filterType.value;
        const yearFilter = filterYear.value;
        const sortOption = sortBy.value;

        let filtered = historyData.filter(item => {
            // Type filter
            if (typeFilter !== 'all' && item.type !== typeFilter) return false;
            // Year filter
            if (yearFilter !== 'all' && item.year !== parseInt(yearFilter)) return false;
            // Search filter (title, year, overview)
            if (searchTerm) {
                const titleMatch = item.title && item.title.toLowerCase().includes(searchTerm);
                const yearMatch = item.year && String(item.year).includes(searchTerm);
                const overviewMatch = item.overview && item.overview.toLowerCase().includes(searchTerm); // Added overview search
                if (!titleMatch && !yearMatch && !overviewMatch) return false; // Include overviewMatch in the check
            }
            return true;
        });

        // Apply sorting
        switch (sortOption) {
            case 'title':
                filtered.sort((a, b) => (a.title || '').localeCompare(b.title || ''));
                break;
            case 'year':
                filtered.sort((a, b) => (b.year || 0) - (a.year || 0) || (a.title || '').localeCompare(b.title || ''));
                break;
            case 'runtime':
                filtered.sort((a, b) => (b.runtime || 0) - (a.runtime || 0) || (a.title || '').localeCompare(b.title || ''));
                break;
            case 'rating':
                // Sort by user_rating (if exists), then rating, then title
                filtered.sort((a, b) => (b.user_rating ?? b.rating ?? 0) - (a.user_rating ?? a.rating ?? 0) || (a.title || '').localeCompare(b.title || ''));
                break;
            default: // watched_at (most recent first)
                filtered.sort((a, b) => new Date(b.watched_at || 0) - new Date(a.watched_at || 0));
        }

        return filtered;
    }

    // Render history items with pagination
    function renderHistory() {
        const filteredHistory = filterHistory();

        if (filteredHistory.length === 0) {
            showEmptyState(searchInput.value ? "No results match your search." : "Your watch history is empty.");
            pagination.style.display = 'none';
            return;
        }

        emptyHistory.style.display = 'none';
        historyContainer.style.display = 'grid';
        historyContainer.innerHTML = ''; // Clear previous items

        // Calculate pagination
        const totalPages = Math.ceil(filteredHistory.length / itemsPerPage);
        currentPage = Math.max(1, Math.min(currentPage, totalPages)); // Ensure currentPage is valid

        const startIndex = (currentPage - 1) * itemsPerPage;
        const endIndex = Math.min(startIndex + itemsPerPage, filteredHistory.length);
        const currentItems = filteredHistory.slice(startIndex, endIndex);

        // Update pagination UI
        pageInfo.textContent = `Page ${currentPage} of ${totalPages}`;
        prevPageBtn.disabled = currentPage === 1;
        nextPageBtn.disabled = currentPage === totalPages;
        pagination.style.display = totalPages > 1 ? 'flex' : 'none';

        // Render current page items
        currentItems.forEach(item => {
            const card = createMediaCardElement(item);
            historyContainer.appendChild(card);
        });
    }

    // Create HTML element for a single media card
    function createMediaCardElement(item) {
        const card = document.createElement('div');
        card.className = 'media-card';
        card.dataset.itemId = item.simkl_id || `${item.title}-${item.year}`; // Unique ID for lookup

        // Determine the base image URL (Simkl or Placeholder)
        let baseImageUrl;
        let posterValue = item.poster || item.poster_url; // Check for both field names
        

        if (posterValue && /^\d+\/\d+[a-f0-9]*$/.test(posterValue)) {
            baseImageUrl = `https://simkl.in/posters/${posterValue}_m.webp`;

        } else {
            // Use placeholder if no valid poster ID
            baseImageUrl = `https://placehold.co/300x450?text=${encodeURIComponent(item.title || 'No Image')}`;
           
        }
        // Apply the proxy to the final base URL
        const proxiedPosterUrl = getProxiedImageUrl(baseImageUrl);

        const mediaType = item.type || 'movie';
        const year = item.year ? `(${item.year})` : '';
        const runtime = item.runtime ? `${item.runtime} min` : '';
        const watchedDate = formatDate(item.watched_at);

        let episodeInfoHtml = '';
        if ((mediaType === 'tv' || mediaType === 'anime') && item.season > 0 && item.episode > 0) {
            episodeInfoHtml = `<span class="episode-info" title="Season ${item.season}, Episode ${item.episode}"><i class="ph-duotone ph-television"></i> S${String(item.season).padStart(2, '0')}E${String(item.episode).padStart(2, '0')}</span>`;
        } else if ((mediaType === 'tv' || mediaType === 'anime') && item.episode > 0) {
            episodeInfoHtml = `<span class="episode-info" title="Episode ${item.episode}"><i class="ph-duotone ph-television"></i> E${item.episode}</span>`;
        }

        let mediaIcon;
        switch(mediaType) {
            case 'tv': mediaIcon = 'ph-duotone ph-television-simple'; break;
            case 'anime': mediaIcon = 'ph-duotone ph-star'; break;
            default: mediaIcon = 'ph-duotone ph-film-strip';
        }

        card.innerHTML = `
            <div class="poster-container">
                <img class="poster-img" src="${proxiedPosterUrl}" alt="${item.title || 'Poster'}" loading="lazy">
                <span class="media-type"><i class="${mediaIcon}"></i> ${mediaType}</span>
            </div>
            <div class="media-info">
                <h3 class="media-title" title="${item.title || ''} ${year}">${item.title || 'No Title'} ${year}</h3>
                <div class="media-meta">
                    ${runtime ? `<span><i class="ph-duotone ph-clock"></i> ${runtime}</span>` : ''}
                    ${episodeInfoHtml}
                    ${item.rating ? `<span><i class="ph-duotone ph-star"></i> ${item.rating.toFixed(1)}</span>` : ''}
                </div>
                <div class="watched-date">
                    <i class="ph-duotone ph-calendar-check"></i> Watched ${watchedDate}
                </div>
                <!-- File Details - Visible only in list view via CSS -->
                <div class="file-details">
                    ${item.resolution ? `<span><i class="ph-duotone ph-monitor"></i> ${item.resolution}</span>` : ''}
                    ${item.formatted_file_size ? `<span><i class="ph-duotone ph-file"></i> ${item.formatted_file_size}</span>` : ''}
                    ${item.file_path ? `<span class="file-path" title="${item.file_path}"><i class="ph-duotone ph-folder"></i> ${item.file_path.length > 40 ? '...' + item.file_path.slice(-37) : item.file_path}</span>` : ''}
                </div>
            </div>
        `;
        return card;
    }

    // Show empty state message
    function showEmptyState(message = "Your watch history is empty.") {
        historyContainer.style.display = 'none';
        emptyHistory.style.display = 'block';
        const emptyText = emptyHistory.querySelector('p');
        if (emptyText) {
            emptyText.textContent = message;
        }
    }

    // Toggle view mode
    viewToggle.addEventListener('click', () => {
        historyContainer.classList.toggle('list-view');
        currentView = historyContainer.classList.contains('list-view') ? 'list' : 'grid';
        localStorage.setItem('simkl_history_view', currentView);
        itemsPerPage = currentView === 'list' ? 15 : 24;
        viewToggle.innerHTML = currentView === 'list' ? '<i class="ph-duotone ph-grid-four"></i>' : '<i class="ph-duotone ph-list"></i>';
        currentPage = 1;
        renderHistory();
    });

    // Toggle theme
    themeToggle.addEventListener('click', () => {
        document.body.classList.toggle('dark-mode');
        currentTheme = document.body.classList.contains('dark-mode') ? 'dark' : 'light';
        localStorage.setItem('simkl_history_theme', currentTheme);
        themeToggle.innerHTML = currentTheme === 'dark' ? '<i class="ph-duotone ph-sun"></i>' : '<i class="ph-duotone ph-moon></i>';
        if (watchChart) createWatchTrendChart(); // Redraw chart with new theme colors
    });

    // Toggle stats dashboard
    statsToggle.addEventListener('click', () => {
        showStats = !showStats;
        dashboard.style.display = showStats ? 'block' : 'none';
        localStorage.setItem('simkl_history_stats', showStats);
        if (showStats && !watchChart) createWatchTrendChart();
    });

    // Pagination event listeners
    prevPageBtn.addEventListener('click', () => {
        if (currentPage > 1) {
            currentPage--;
            renderHistory();
            window.scrollTo({ top: 0, behavior: 'smooth' }); // Scroll to top
        }
    });

    nextPageBtn.addEventListener('click', () => {
        const filteredHistory = filterHistory();
        const totalPages = Math.ceil(filteredHistory.length / itemsPerPage);
        if (currentPage < totalPages) {
            currentPage++;
            renderHistory();
            window.scrollTo({ top: 0, behavior: 'smooth' }); // Scroll to top
        }
    });

    // Event listeners for filtering and searching (debounce search)
    let searchTimeout;
    searchInput.addEventListener('input', () => {
        clearTimeout(searchTimeout);
        searchTimeout = setTimeout(() => {
            currentPage = 1;
            renderHistory();
        }, 300); // Debounce search input
    });

    filterType.addEventListener('change', () => { currentPage = 1; renderHistory(); });
    filterYear.addEventListener('change', () => { currentPage = 1; renderHistory(); });
    sortBy.addEventListener('change', () => { currentPage = 1; renderHistory(); });

    // Keyboard shortcuts for pagination
    document.addEventListener('keydown', (e) => {
        // Ignore if typing in search input or if modal is open
        if (e.target === searchInput || activeMediaCard) return;

        if (e.key === 'ArrowLeft' && !prevPageBtn.disabled) prevPageBtn.click();
        else if (e.key === 'ArrowRight' && !nextPageBtn.disabled) nextPageBtn.click();
    });

    // Handle card clicks to show detailed view
    historyContainer.addEventListener('click', (e) => {
        const card = e.target.closest('.media-card');
        if (!card || card.classList.contains('expanded')) return;

        // Prevent opening if clicking on interactive elements within the card (future-proofing)
        if (e.target.closest('button, a')) return;

        expandMediaCard(card);
    });

    // Close expanded card when clicking backdrop or pressing Escape
    modalBackdrop.addEventListener('click', (e) => { if (e.target === modalBackdrop) closeExpandedCard(); });
    document.addEventListener('keydown', (e) => { if (e.key === 'Escape' && activeMediaCard) closeExpandedCard(); });

    // Expand a media card
    function expandMediaCard(card) {
        if (activeMediaCard) closeExpandedCard(); // Close any existing expanded card

        const itemId = card.dataset.itemId;
        // Find the item data using a more robust method if IDs aren't always present
        const item = historyData.find(i => (i.simkl_id && i.simkl_id == itemId) || (!i.simkl_id && `${i.title}-${i.year}` === itemId));

        if (!item) {
            console.error("Could not find item data for card:", itemId);
            return;
        }

        // Store original position and size for animation
        const rect = card.getBoundingClientRect();
        
        // Set CSS variables for animation origin
        card.style.setProperty('--card-orig-top', `${rect.top}px`);
        card.style.setProperty('--card-orig-left', `${rect.left}px`);
        card.style.setProperty('--card-orig-width', `${rect.width}px`);
        card.style.setProperty('--card-orig-height', `${rect.height}px`);
        
        // Set up the fixed position before starting animation
        card.style.position = 'fixed';
        card.style.top = `${rect.top}px`;
        card.style.left = `${rect.left}px`;
        card.style.width = `${rect.width}px`;
        card.style.height = `${rect.height}px`;
        card.style.margin = '0';
        card.style.zIndex = '1000';

        activeMediaCard = card;
        card.classList.add('expanded');
        
        // Display backdrop with a fade-in effect
        modalBackdrop.style.display = 'block';
        // Short delay to ensure display:block is processed before starting transition
        setTimeout(() => {
            modalBackdrop.classList.add('active');
        }, 10);
        
        document.body.style.overflow = 'hidden'; // Prevent body scroll

        // Add animation class after a small delay to ensure the card is ready
        setTimeout(() => {
            card.classList.add('animating-open');
            
            // Listen for animation end
            card.addEventListener('animationend', function onAnimEnd() {
                card.classList.remove('animating-open');
                card.removeEventListener('animationend', onAnimEnd);
                
                // Reset inline styles once animation is complete
                card.style.position = '';
                card.style.top = '';
                card.style.left = '';
                card.style.width = '';
                card.style.height = '';
                card.style.margin = '';
                
                // Continue with populating the expanded card
                populateExpandedCard(card, item);
            }, { once: true });
        }, 10);
    }

    // Populate the expanded card with content
    function populateExpandedCard(card, item) {
        // Clone template content
        const templateClone = expandedContentTemplate.content.cloneNode(true);
        const expandedHeader = templateClone.querySelector('.expanded-header');
        const expandedContentWrapper = templateClone.querySelector('.expanded-content-wrapper');

        // Populate Header
        const posterBg = expandedHeader.querySelector('.expanded-poster-bg');
        const posterThumbImg = expandedHeader.querySelector('.expanded-poster-thumb img');
        const titleEl = expandedHeader.querySelector('.expanded-title');
        const metaYear = expandedHeader.querySelector('[data-field="release_year"] span');
        const metaRuntime = expandedHeader.querySelector('[data-field="runtime"] span');
        const metaLastWatched = expandedHeader.querySelector('[data-field="last_watched_at"] span'); // Changed from user_rating

        // Determine the base image URLs (Simkl or Placeholder) for large and thumb sizes
        let largeBaseUrl, thumbBaseUrl, baseImageUrl;
        let posterValue = item.poster || item.poster_url; // Check for both field names
        
        if (posterValue && /^\d+\/\d+[a-f0-9]*$/.test(posterValue)) {
            baseImageUrl = `https://simkl.in/posters/${posterValue}`;
            largeBaseUrl = `${baseImageUrl}_c.webp`; // Large poster for background
            thumbBaseUrl = `${baseImageUrl}_m.webp`; // Medium poster for thumb
        } else {
            // Use placeholders if no valid poster ID
            const placeholderText = encodeURIComponent(item.title || 'No Image');
            largeBaseUrl = `https://placehold.co/600x900?text=${placeholderText}`; // Larger placeholder
            thumbBaseUrl = `https://placehold.co/300x450?text=${placeholderText}`;
        }

        // Apply the proxy to the final base URLs
        const largePosterUrl = getProxiedImageUrl(largeBaseUrl);
        const thumbPosterUrl = getProxiedImageUrl(thumbBaseUrl);

        posterBg.style.backgroundImage = `url('${largePosterUrl}')`;
        posterThumbImg.src = thumbPosterUrl;

        titleEl.textContent = item.title || 'No Title';
        metaYear.textContent = item.year || '-';
        metaRuntime.textContent = item.runtime ? `${item.runtime} min` : '-';
        // Populate Last Watched Date
        metaLastWatched.textContent = formatDate(item.watched_at);

        // Populate Content Details
        populateExpandedContentDetails(expandedContentWrapper, item);

        // Add close button listener
        const closeButton = templateClone.querySelector('.close-button');
        closeButton.addEventListener('click', closeExpandedCard);

        // Add action button listeners
        const playMediaBtn = expandedContentWrapper.querySelector('.play-media');
        const openFolderBtn = expandedContentWrapper.querySelector('.open-folder');
        const searchOnlineBtn = expandedContentWrapper.querySelector('#search-online');

        if (item.file_path) {
            playMediaBtn.addEventListener('click', () => window.open(`file:///${item.file_path}`, '_blank'));
            openFolderBtn.addEventListener('click', () => {
                // Attempt to open the folder containing the file
                try {
                    const directory = item.file_path.substring(0, item.file_path.lastIndexOf('\\') || item.file_path.lastIndexOf('/'));
                    window.open(`file:///${directory}`, '_blank');
                } catch (e) {
                    alert('Could not determine folder path.');
                }
            });
        } else {
            playMediaBtn.disabled = true;
            playMediaBtn.title = "File path not available";
            openFolderBtn.disabled = true;
            openFolderBtn.title = "File path not available";
        }
        
        // Update the search online button with the current title
        if (searchOnlineBtn && item.title) {
            const searchQuery = `${item.title} ${item.year || ''} watch online`;
            searchOnlineBtn.href = `https://www.google.com/search?q=${encodeURIComponent(searchQuery)}`;
        }

        // Append the populated template to the card
        card.appendChild(templateClone);
    }

    // Close the expanded card
    function closeExpandedCard() {
        if (!activeMediaCard) return;

        // Get the original position and size from the CSS variables
        const origTop = activeMediaCard.style.getPropertyValue('--card-orig-top');
        const origLeft = activeMediaCard.style.getPropertyValue('--card-orig-left');
        const origWidth = activeMediaCard.style.getPropertyValue('--card-orig-width');
        const origHeight = activeMediaCard.style.getPropertyValue('--card-orig-height');

        // Save references to elements we need to remove after animation
        const header = activeMediaCard.querySelector('.expanded-header');
        const closeBtn = activeMediaCard.querySelector('.close-button');
        const contentWrapper = activeMediaCard.querySelector('.expanded-content-wrapper');

        // Start fade out animation for backdrop
        modalBackdrop.classList.remove('active');

        // Set up fixed position for animation
        activeMediaCard.style.position = 'fixed';
        activeMediaCard.style.top = '50%';
        activeMediaCard.style.left = '50%';
        activeMediaCard.style.width = '90%';
        activeMediaCard.style.maxWidth = '850px';
        activeMediaCard.style.transform = 'translate(-50%, -50%)';
        activeMediaCard.style.zIndex = '1000';

        // Add closing animation class
        activeMediaCard.classList.add('animating-close');
        
        // Listen for animation end
        activeMediaCard.addEventListener('animationend', function onCloseAnimEnd() {
            activeMediaCard.classList.remove('animating-close');
            activeMediaCard.removeEventListener('animationend', onCloseAnimEnd);
            
            // Reset all inline styles
            activeMediaCard.style.position = '';
            activeMediaCard.style.top = '';
            activeMediaCard.style.left = '';
            activeMediaCard.style.width = '';
            activeMediaCard.style.height = '';
            activeMediaCard.style.margin = '';
            activeMediaCard.style.transform = '';
            activeMediaCard.style.zIndex = '';
            
            // Remove elements and cleanup
            if (header) activeMediaCard.removeChild(header);
            if (closeBtn) activeMediaCard.removeChild(closeBtn);
            if (contentWrapper) activeMediaCard.removeChild(contentWrapper);
            
            activeMediaCard.classList.remove('expanded');
            modalBackdrop.style.display = 'none';
            document.body.style.overflow = ''; // Restore body scroll
            activeMediaCard = null;
        }, { once: true });
    }

    // Format file size
    function formatFileSize(bytes) {
        if (bytes === null || bytes === undefined || isNaN(bytes)) return null;
        if (bytes === 0) return '0 Bytes';
        const k = 1024;
        const sizes = ['Bytes', 'KB', 'MB', 'GB', 'TB'];
        const i = Math.floor(Math.log(bytes) / Math.log(k));
        return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
    }

    // Update field helper
    function updateField(container, fieldName, value) {
        const field = container.querySelector(`[data-field="${fieldName}"]`);
        if (field) {
            // If the value is an element (like for genres), append it
            if (value instanceof HTMLElement) {
                 field.innerHTML = ''; // Clear existing
                 field.appendChild(value);
            } else {
                 field.textContent = value || '-'; // Use '-' for null/empty values
            }
            // Hide parent detail-group if value is '-' or empty, unless it's a required field like overview
            const parentGroup = field.closest('.detail-group');
            if (parentGroup && fieldName !== 'overview' && fieldName !== 'file_path') { // Keep overview and file path visible even if '-'
                parentGroup.style.display = (value && value !== '-') ? '' : 'none';
            }
        }
        return field; // Return the element for potential further manipulation
    }

    // Populate the details within the expanded card's scrollable area
    function populateExpandedContentDetails(contentWrapper, item) {
        updateField(contentWrapper, 'overview', item.overview || 'No description available.');
        updateField(contentWrapper, 'language', item.language || '-');

        // Update file details
        const filePathEl = updateField(contentWrapper, 'file_path', item.file_path || '-');
        if (filePathEl && item.file_path) {
            filePathEl.title = `Click to copy: ${item.file_path}`; // Add title for full path
            filePathEl.style.cursor = 'pointer';
            filePathEl.addEventListener('click', () => {
                navigator.clipboard.writeText(item.file_path)
                    .then(() => {
                        const originalText = filePathEl.textContent;
                        filePathEl.textContent = 'Copied!';
                        setTimeout(() => { filePathEl.textContent = originalText; }, 1500);
                    })
                    .catch(err => console.error('Failed to copy file path:', err));
            });
        } else if (filePathEl) {
             filePathEl.style.cursor = 'default';
             filePathEl.title = 'File path not available';
        }

        updateField(contentWrapper, 'file_size', item.formatted_file_size || formatFileSize(item.file_size) || '-');
        updateField(contentWrapper, 'resolution', item.resolution || '-');
        updateField(contentWrapper, 'file_format', item.file_format || '-');
        updateField(contentWrapper, 'last_modified', formatTimestamp(item.last_modified));

        // Populate External Links
        const linksContainer = contentWrapper.querySelector('.external-links');
        linksContainer.innerHTML = '<div class="detail-label">Links</div>'; // Reset and add label
        
        // Fix for TV shows - use 'tv' instead of 'show' in the URL
        const simklUrlType = item.type === 'show' ? 'tv' : item.type;
        
        addExternalLink(linksContainer, item.ids?.simkl || item.simkl_id, 
            `https://simkl.com/${simklUrlType}/${item.ids?.simkl || item.simkl_id}`, 
            'Simkl', 'https://simkl.in/favicon.ico');
        addExternalLink(linksContainer, item.ids?.imdb, `https://www.imdb.com/title/${item.ids.imdb}`, 'IMDb', 'https://www.imdb.com/favicon.ico');
        addExternalLink(linksContainer, item.ids?.tmdb, `https://www.themoviedb.org/${item.type === 'movie' ? 'movie' : 'tv'}/${item.ids.tmdb}`, 'TMDB', 'https://www.themoviedb.org/favicon.ico');
        addExternalLink(linksContainer, item.ids?.tvdb, `https://thetvdb.com/?tab=series&id=${item.ids.tvdb}`, 'TVDB', 'https://thetvdb.com/images/favicon.ico');
        addExternalLink(linksContainer, item.ids?.anilist, `https://anilist.co/${item.type}/${item.ids.anilist}`, 'Anilist', 'https://anilist.co/img/icons/favicon-32x32.png');
        // Add more links as needed (MAL, etc.)

        // Show/hide TV details section
        const tvDetailsSection = contentWrapper.querySelector('.tv-details-section');
        const mediaType = item.type || 'movie';

        if (mediaType === 'tv' || mediaType === 'anime') {
            tvDetailsSection.style.display = 'block';
            
            // Find the latest watched episode info
            let latestEntry;
            let latestEpisodeText = '-';
            
            if (item.episodes && item.episodes.length > 0) {
                // Sort episodes by most recent watch date
                const sortedEpisodes = [...item.episodes].sort((a, b) => 
                    new Date(b.watched_at || 0) - new Date(a.watched_at || 0)
                );
                latestEntry = sortedEpisodes[0];
            } else {
                // Fallback to the item itself if it has episode info
                latestEntry = item;
            }
            
            // Format latest episode text
            if (latestEntry && latestEntry.season > 0 && latestEntry.episode > 0) {
                latestEpisodeText = `S${String(latestEntry.season).padStart(2, '0')}E${String(latestEntry.episode).padStart(2, '0')}`;
            } else if (latestEntry && latestEntry.episode > 0) {
                latestEpisodeText = `E${latestEntry.episode}`;
            }
            updateField(tvDetailsSection, 'latest_watched_episode', latestEpisodeText);
            updateField(tvDetailsSection, 'total_episodes', item.total_episodes || '-'); // Use item's total_episodes if available

            // Calculate Watched Count: Prioritize item.episodes_watched if available
            let watchedCount = '-';
            if (typeof item.episodes_watched === 'number') {
                watchedCount = item.episodes_watched;
            } else if (item.simkl_id) {
                // Fallback: Count unique episodes from history
                const uniqueEpisodes = new Set();
                historyData
                    .filter(entry => entry.simkl_id === item.simkl_id && entry.episode > 0)
                    .forEach(entry => uniqueEpisodes.add(`S${entry.season || 0}E${entry.episode}`));
                watchedCount = uniqueEpisodes.size;
            } else if (item.episodes && item.episodes.length > 0) {
                watchedCount = item.episodes.length;
            }
            updateField(tvDetailsSection, 'episodes_watched_count', watchedCount);

            // Populate Episode List
            const episodeListContainer = tvDetailsSection.querySelector('[data-field="episode_list"]');
            episodeListContainer.innerHTML = ''; // Clear previous list

            // Get all history entries for this specific show/anime ID, sorted by most recent watch (for fallback/metadata)
            const episodesHistory = historyData
                .filter(entry => entry.simkl_id === item.simkl_id && (entry.type === 'tv' || entry.type === 'anime') && entry.episode > 0)
                .sort((a, b) => new Date(b.watched_at || 0) - new Date(a.watched_at || 0));

            let episodesToDisplay = [];
            let sourceIsItemEpisodes = false;

            if (Array.isArray(item.episodes) && item.episodes.length > 0) {
                // Source: item.episodes array (e.g., from watch_history.json)
                episodesToDisplay = item.episodes.map(epData => ({
                    season: epData.season,
                    number: epData.number,
                    title: epData.title || `Episode ${epData.number}`,
                    // Include direct properties from epData and find corresponding history entry for fallback/additional metadata
                    ...epData, // Spread properties like file_path, formatted_file_size, runtime directly
                    historyEntry: episodesHistory.find(hist => hist.season === epData.season && hist.episode === epData.number)
                }));
                sourceIsItemEpisodes = true;
            } else if (episodesHistory.length > 0) {
                // Fallback Source: History entries
                episodesToDisplay = episodesHistory.map(hist => ({
                    season: hist.season,
                    number: hist.episode,
                    title: `Episode ${hist.episode}`, // No title available from history alone
                    watched_at: hist.watched_at,
                    file_path: hist.file_path,
                    file_size: hist.file_size,
                    formatted_file_size: hist.formatted_file_size,
                    runtime: hist.runtime,
                    historyEntry: hist
                }));
            }

            if (episodesToDisplay.length > 0) {
                // Sort episodes by watched date (newest first)
                episodesToDisplay.sort((a, b) => {
                    // Parse dates for comparison
                    const dateA = a.watched_at ? new Date(a.watched_at) : new Date(0);
                    const dateB = b.watched_at ? new Date(b.watched_at) : new Date(0);
                    
                    // Sort by date descending (newest first)
                    return dateB - dateA;
                });

                episodesToDisplay.forEach(ep => {
                    const epElement = document.createElement('div');
                    epElement.className = 'episode-item';
                    const epNumber = ep.number || '?';
                    const seasonNumber = ep.season || 0;
                    const epTitle = ep.title; // Already determined above
                    
                    // Use the direct watched_at from the episode object if available (from item.episodes)
                    // Only fallback to historyEntry if needed
                    const epWatchedDate = ep.watched_at ? formatDate(ep.watched_at) : 
                                        ep.historyEntry ? formatDate(ep.historyEntry.watched_at) : 'N/A';
                    
                    const epFilePath = ep.file_path || ep.historyEntry?.file_path || 'N/A';
                    const epFileSize = ep.formatted_file_size || formatFileSize(ep.file_size) || ep.historyEntry?.formatted_file_size || formatFileSize(ep.historyEntry?.file_size) || 'N/A';
                    const epRuntime = ep.runtime || ep.historyEntry?.runtime; // Get runtime if available

                    const runtimeHtml = epRuntime ? `<span title="Runtime"><i class="ph-duotone ph-clock"></i> ${epRuntime} min</span>` : '';
                    epElement.innerHTML = `
                        <div class="episode-info-main">
                            <span class="episode-number">${seasonNumber > 0 ? `S${String(seasonNumber).padStart(2, '0')}` : ''}E${epNumber}</span>
                            <span class="episode-title" title="${epTitle}">${epTitle}</span>
                        </div>
                        <div class="episode-info-meta">
                            <span title="Watched Date"><i class="ph-duotone ph-calendar-check"></i> ${epWatchedDate}</span>
                            <span title="File Size"><i class="ph-duotone ph-file"></i> ${epFileSize}</span>
                            ${runtimeHtml}
                            <span class="file-path-ep" title="${epFilePath}"><i class="ph-duotone ph-folder"></i> ${epFilePath.length > 25 ? '...' + epFilePath.slice(-22) : epFilePath}</span>
                        </div>
                    `;
                    episodeListContainer.appendChild(epElement);
                });
            } else {
                episodeListContainer.innerHTML = '<div class="no-episodes">No episode watch history found.</div>';
            }
        } else {
            tvDetailsSection.style.display = 'none';
        }
    }

    // Helper to add an external link button if the ID exists
    function addExternalLink(container, id, url, text, iconSrc) {
        if (!id || !url) return;
        
        const link = document.createElement('a');
        link.href = url;
        link.target = '_blank';
        link.rel = 'noopener';
        link.className = 'external-link-btn';
        link.title = `View on ${text}`;
        
        if (iconSrc && iconSrc.includes('http')) {
            const icon = document.createElement('img');
            icon.src = iconSrc;
            icon.alt = text;
            icon.className = 'icon';
            link.appendChild(icon);
        } else {
            const icon = document.createElement('i');
            icon.className = 'ph-duotone ph-link icon';
            link.appendChild(icon);
        }
        
        const textSpan = document.createElement('span');
        textSpan.textContent = text;
        link.appendChild(textSpan);
        
        container.appendChild(link);
    }

    // Make these functions globally accessible for data.js
    window.loadHistory = loadHistory;
    window.processHistoryData = processHistoryData;

    // Initial load
    loadHistory();
});