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
    let currentTheme = localStorage.getItem('simkl_history_theme') || 'dark';
    let showStats = localStorage.getItem('simkl_history_stats') === 'true';
    let currentPage = 1;
    let itemsPerPage = 24;
    let watchChart = null;
    
    // Image cache in IndexedDB
    let imageCache;
    const IMAGE_CACHE_NAME = 'simkl-images-cache';
    const CACHE_VERSION = 1;
    
    // Initialize image cache
    initImageCache();
    
    // Apply saved view
    if (currentView === 'list') {
        historyContainer.classList.add('list-view');
        viewToggle.innerHTML = '<i class="ph ph-grid-four"></i>';
        itemsPerPage = 12; // Fewer items per page in list view
    }
    
    // Apply saved theme
    if (currentTheme === 'dark') {
        document.body.classList.add('dark-mode');
        themeToggle.innerHTML = '<i class="ph ph-sun"></i>';
    }
    
    // Apply saved stats visibility
    if (showStats) {
        dashboard.style.display = 'block';
    }
    
    // Initialize IndexedDB cache for images
    function initImageCache() {
        const request = indexedDB.open(IMAGE_CACHE_NAME, CACHE_VERSION);
        
        request.onupgradeneeded = (event) => {
            const db = event.target.result;
            if (!db.objectStoreNames.contains('images')) {
                const store = db.createObjectStore('images', { keyPath: 'url' });
                store.createIndex('timestamp', 'timestamp', { unique: false });
                console.log('Image cache store created');
            }
        };
        
        request.onsuccess = (event) => {
            imageCache = event.target.result;
            console.log('Image cache initialized');
        };
        
        request.onerror = (event) => {
            console.error('Error initializing image cache:', event.target.error);
            // Continue without caching if there's an error
            imageCache = null;
        };
    }
    
    // Get image URL with WSRV proxy for SIMKL images
    function getProxiedImageUrl(originalUrl, size = '_m') {
        // First check if it's already a wsrv.nl URL
        if (originalUrl.includes('wsrv.nl')) {
            return originalUrl;
        }
        
        // Build the wsrv.nl URL with optimization parameters
        const buildWsrvUrl = (url) => {
            // Highest quality settings with good performance:
            // No width restriction (original image size)
            // q=100 - maximum quality
            // output=webp - still use WebP for better compression
            // n=-1 - disable caching on wsrv.nl's side
            // sharp=20 - apply slight sharpening for better detail
            return `https://wsrv.nl/?url=${encodeURIComponent(url)}&q=100&output=webp&sharp=20&n=-1`;
        };
        
        // Special case: If the URL already has a directory format like "17/172580032b3d125198"
        if (/^\d+\/\d+[a-f0-9]*$/.test(originalUrl)) {
            return buildWsrvUrl(`https://simkl.in/posters/${originalUrl}${size}.jpg`);
        }
        
        // Handle SIMKL poster URL patterns
        
        // Pattern 1: Full SIMKL URL (e.g. https://simkl.in/posters/74/74415673dcdc9cdd_m.webp)
        if (originalUrl.includes('simkl.in/posters/')) {
            return buildWsrvUrl(originalUrl);
        }
        
        // Pattern 2: Just the ID with or without file extension (e.g. 74415673dcdc9cdd or 74415673dcdc9cdd_m.webp)
        const idPattern = /^([a-f0-9]+)(?:_[cm])?(?:\.(jpg|webp))?$/i;
        const idMatch = originalUrl.match(idPattern);
        if (idMatch) {
            const id = idMatch[1];
            const firstTwo = id.substring(0, 2);
            return buildWsrvUrl(`https://simkl.in/posters/${firstTwo}/${id}${size}.jpg`);
        }
        
        // Pattern 3: Just a numeric SIMKL ID (e.g. 12345)
        if (/^\d+$/.test(originalUrl)) {
            return buildWsrvUrl(`https://simkl.in/posters/${originalUrl}${size}.jpg`);
        }
        
        // Log URLs that don't match any patterns for debugging
        console.log(`Unrecognized poster URL format: ${originalUrl}`);
        
        // Fallback - if we can't determine the format, return the original URL
        return originalUrl;
    }
    
    // Get image from cache or fetch
    async function getImageWithCache(url) {
        const cacheKey = url;
        
        // If no cache available, return the URL directly
        if (!imageCache) {
            return url;
        }
        
        // Check if we're running from a file:// URL, in which case
        // direct fetch won't work due to CORS restrictions
        const isFileProtocol = window.location.protocol === 'file:';
        
        return new Promise((resolve) => {
            const transaction = imageCache.transaction(['images'], 'readonly');
            const store = transaction.objectStore('images');
            const request = store.get(cacheKey);
            
            request.onsuccess = (event) => {
                const result = event.target.result;
                // *** Check for file protocol BEFORE using cached blob ***
                if (isFileProtocol) {
                    // Always use the original proxied URL when running locally
                    console.log(`File protocol: Using original URL for ${cacheKey}`);
                    resolve(url);
                } else if (result && result.data) {
                    // Image exists in cache and not file protocol, use blob URL
                    console.log(`Using cached image for ${cacheKey}`);
                    resolve(result.data);
                } else {
                    // Not in cache (or file protocol), use the original URL directly
                    console.log(`No cache or file protocol: Using original URL for ${cacheKey}`);
                    resolve(url);
                    
                    // Only try to fetch and cache if we're not using file:// protocol
                    // or if it's an external URL (https://)
                    if (!isFileProtocol || url.startsWith('https://')) {
                        // Fetch the image and store in cache for next time
                        fetch(url, { mode: 'cors', credentials: 'omit' })
                            .then(response => {
                                if (!response.ok) {
                                    throw new Error('Network response was not ok');
                                }
                                return response.blob();
                            })
                            .then(blob => {
                                // Create an object URL for the blob
                                const objectURL = URL.createObjectURL(blob);
                                
                                // Store in cache
                                const transaction = imageCache.transaction(['images'], 'readwrite');
                                const store = transaction.objectStore('images');
                                store.put({
                                    url: cacheKey,
                                    data: objectURL,
                                    timestamp: Date.now()
                                });
                            })
                            .catch(error => {
                                console.error('Error caching image:', error);
                            });
                    }
                }
            };
            
            request.onerror = () => {
                // Error accessing cache, just use the URL
                console.error('Error accessing image cache');
                resolve(url);
            };
        });
    }
    
    // Load watch history data
    function loadHistory() {
        // Show loading indicator
        loadingIndicator.style.display = 'flex';
        historyContainer.style.display = 'none';
        emptyHistory.style.display = 'none';
        
        try {
            // Check if the HISTORY_DATA variable exists (should be defined in data.js)
            if (typeof HISTORY_DATA !== 'undefined') {
                historyData = HISTORY_DATA;
                console.log(`Loaded ${historyData.length} watch history entries from data.js`);
                
                // Process data
                processHistoryData();
                
                // Hide loading indicator
                loadingIndicator.style.display = 'none';
                
                // Render history data
                renderHistory();
                return;
            }
            
            // Fallback method - try to load from the JSON file directly
            console.log("No HISTORY_DATA found in data.js, falling back to fetch method");
            
            // Try to load from the local watch_history.json file
            fetch('watch_history.json')
                .then(response => {
                    if (!response.ok) {
                        throw new Error('History file not found');
                    }
                    return response.json();
                })
                .then(data => {
                    historyData = data;
                    processHistoryData();
                    loadingIndicator.style.display = 'none';
                    renderHistory();
                })
                .catch(error => {
                    console.error('Error loading history:', error);
                    loadingIndicator.style.display = 'none';
                    showEmptyState();
                });
        } catch (error) {
            console.error('Error loading history data:', error);
            loadingIndicator.style.display = 'none';
            showEmptyState();
        }
    }
    
    // Process history data, additional meta processing
    function processHistoryData() {
        // Populate years filter
        const years = new Set();
        historyData.forEach(item => {
            if (item.year) {
                years.add(item.year);
            }
        });
        
        // Sort years in descending order
        const sortedYears = Array.from(years).sort((a, b) => b - a);
        
        // Clear existing options except the first one
        while (filterYear.options.length > 1) {
            filterYear.remove(1);
        }
        
        // Add year options
        sortedYears.forEach(year => {
            const option = document.createElement('option');
            option.value = year;
            option.textContent = year;
            filterYear.appendChild(option);
        });
        
        // Update stats
        updateStatistics();
        
        // Preload and cache poster images for visible items
        preloadImages();
    }
    
    // Preload common poster images
    function preloadImages() {
        if (!imageCache) return;
        
        console.log('Preloading poster images...');
        
        // Get first batch of items to preload
        const preloadCount = Math.min(itemsPerPage * 2, historyData.length);
        const itemsToPreload = historyData.slice(0, preloadCount);
        
        // Preload each poster image
        itemsToPreload.forEach(item => {
            const posterUrl = item.poster_url || item.poster || `https://simkl.in/posters/${item.simkl_id}_m.jpg`;
            const proxiedUrl = getProxiedImageUrl(posterUrl);
            
            // Start caching the image
            getImageWithCache(proxiedUrl);
        });
    }
    
    // Update statistics
    function updateStatistics() {
        const movieCount = historyData.filter(item => item.type === 'movie').length;
        // Count unique TV shows based on simkl_id (or title/year as fallback)
        const uniqueShowIds = new Set();
        historyData.forEach(item => {
            if (item.type === 'show' || item.type === 'tv') { // Include 'show' type
                // Prefer simkl_id, fallback to title+year combination
                const uniqueId = item.simkl_id || `${item.title}-${item.year}`;
                uniqueShowIds.add(uniqueId);
            }
        });
        const showCount = uniqueShowIds.size; // Count of unique TV shows

        // Count unique Anime based on simkl_id (or title/year as fallback)
        const uniqueAnimeIds = new Set();
        historyData.forEach(item => {
            if (item.type === 'anime') {
                const uniqueId = item.simkl_id || `${item.title}-${item.year}`;
                uniqueAnimeIds.add(uniqueId);
            }
        });
        const animeCount = uniqueAnimeIds.size; // Count of unique Anime

        totalCountEl.textContent = historyData.length;
        moviesCountEl.textContent = movieCount;
        showsCountEl.textContent = showCount; // Display unique TV show count
        animeCountEl.textContent = animeCount; // Display unique Anime count here

        // Create watch trend chart
        createWatchTrendChart();
    }
    
    // Create watch trend chart
    function createWatchTrendChart() {
        // If Chart.js is not available, skip chart creation
        if (typeof Chart === 'undefined') return;
        
        // Group watch history by month
        const watchesByMonth = {};
        const currentDate = new Date();
        
        // Start 12 months ago from current date
        for (let i = 11; i >= 0; i--) {
            const date = new Date(currentDate);
            date.setMonth(currentDate.getMonth() - i);
            const monthKey = date.toISOString().slice(0, 7); // YYYY-MM format
            watchesByMonth[monthKey] = { month: monthKey, count: 0 };
        }
        
        // Count watches by month
        historyData.forEach(item => {
            if (item.watched_at) {
                const watchMonth = item.watched_at.slice(0, 7); // YYYY-MM
                if (watchesByMonth[watchMonth]) {
                    watchesByMonth[watchMonth].count++;
                }
            }
        });
        
        // Convert to array and prepare for chart
        const chartData = Object.values(watchesByMonth);
        
        // Format month labels
        const labels = chartData.map(item => {
            const [year, month] = item.month.split('-');
            return new Date(year, month - 1).toLocaleDateString(undefined, { month: 'short', year: 'numeric' });
        });
        
        // Get counts
        const counts = chartData.map(item => item.count);
        
        // Canvas element
        const chartCanvas = document.getElementById('watch-trend-chart');
        if (!chartCanvas) return;
        
        // Destroy previous chart if it exists
        if (watchChart) {
            watchChart.destroy();
        }
        
        // Create new chart
        watchChart = new Chart(chartCanvas, {
            type: 'line',
            data: {
                labels: labels,
                datasets: [{
                    label: 'Watched Content',
                    data: counts,
                    borderColor: '#e63232',
                    backgroundColor: 'rgba(230, 50, 50, 0.1)',
                    borderWidth: 2,
                    pointBackgroundColor: '#e63232',
                    fill: true,
                    tension: 0.3
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
                        mode: 'index',
                        intersect: false
                    }
                },
                scales: {
                    y: {
                        beginAtZero: true,
                        ticks: {
                            precision: 0
                        }
                    }
                }
            }
        });
    }
    
    // Format date for display
    function formatDate(dateString) {
        if (!dateString) return 'Unknown date';
        
        const date = new Date(dateString);
        const now = new Date();
        const diffDays = Math.floor((now - date) / (1000 * 60 * 60 * 24));
        
        if (isNaN(date.getTime())) return 'Unknown date';
        
        if (diffDays === 0) {
            return 'Today';
        } else if (diffDays === 1) {
            return 'Yesterday';
        } else if (diffDays < 7) {
            return `${diffDays} days ago`;
        } else {
            return date.toLocaleDateString(undefined, { year: 'numeric', month: 'short', day: 'numeric' });
        }
    }
    
    // Filter history based on current filters
    function filterHistory() {
        const searchTerm = searchInput.value.toLowerCase();
        const typeFilter = filterType.value;
        const yearFilter = filterYear.value;
        const sortOption = sortBy.value;
        
        let filtered = [...historyData];
        
        // Apply type filter
        if (typeFilter !== 'all') {
            filtered = filtered.filter(item => item.type === typeFilter);
        }
        
        // Apply year filter
        if (yearFilter !== 'all') {
            filtered = filtered.filter(item => item.year === parseInt(yearFilter));
        }
        
        // Apply search filter
        if (searchTerm) {
            filtered = filtered.filter(item => 
                (item.title && item.title.toLowerCase().includes(searchTerm)) ||
                (item.overview && item.overview.toLowerCase().includes(searchTerm)) ||
                (item.genres && item.genres.some(genre => genre.toLowerCase().includes(searchTerm))) ||
                (item.cast && item.cast.some(actor => actor.toLowerCase().includes(searchTerm)))
            );
        }
        
        // Apply sorting
        switch (sortOption) {
            case 'title':
                filtered.sort((a, b) => a.title.localeCompare(b.title));
                break;
            case 'year':
                filtered.sort((a, b) => {
                    // Sort by year, then by title for items with the same year
                    if (a.year === b.year) {
                        return a.title.localeCompare(b.title);
                    }
                    return (b.year || 0) - (a.year || 0);
                });
                break;
            case 'runtime':
                filtered.sort((a, b) => {
                    // Sort by runtime, then by title for items with the same runtime
                    if (a.runtime === b.runtime) {
                        return a.title.localeCompare(b.title);
                    }
                    return (b.runtime || 0) - (a.runtime || 0);
                });
                break;
            case 'rating':
                filtered.sort((a, b) => {
                    // Sort by user rating if available, otherwise by rating, then by title
                    const aRating = a.user_rating || a.rating || 0;
                    const bRating = b.user_rating || b.rating || 0;
                    
                    if (aRating === bRating) {
                        return a.title.localeCompare(b.title);
                    }
                    return bRating - aRating;
                });
                break;
            default: // watched_at
                filtered.sort((a, b) => new Date(b.watched_at || 0) - new Date(a.watched_at || 0));
        }
        
        return filtered;
    }
    
    // Render history items with pagination
    async function renderHistory() {
        const filteredHistory = filterHistory();
        
        if (filteredHistory.length === 0) {
            showEmptyState();
            pagination.style.display = 'none';
            return;
        }
        
        emptyHistory.style.display = 'none';
        historyContainer.style.display = 'grid';
        historyContainer.innerHTML = '';
        
        // Calculate pagination
        const totalPages = Math.ceil(filteredHistory.length / itemsPerPage);
        if (currentPage > totalPages) {
            currentPage = 1;
        }
        
        const startIndex = (currentPage - 1) * itemsPerPage;
        const endIndex = Math.min(startIndex + itemsPerPage, filteredHistory.length);
        const currentItems = filteredHistory.slice(startIndex, endIndex);
        
        // Update pagination UI
        pageInfo.textContent = `Page ${currentPage} of ${totalPages}`;
        prevPageBtn.disabled = currentPage === 1;
        nextPageBtn.disabled = currentPage === totalPages;
        pagination.style.display = totalPages > 1 ? 'flex' : 'none';
        
        // Render current page items
        for (const item of currentItems) {
            const card = document.createElement('div');
            card.className = 'media-card';
            
            // Better poster URL handling
            let posterUrl;
            if (item.poster_url) {
                posterUrl = item.poster_url;
            } else if (item.poster) {
                posterUrl = item.poster;
            } else if (item.simkl_id) {
                // Format: directly use SIMKL ID with proper suffix
                posterUrl = `${item.simkl_id}`;
            } else {
                posterUrl = 'no-image';
            }
            
            // Use wsrv.nl proxy for the poster
            const proxiedPosterUrl = getProxiedImageUrl(posterUrl);
            console.log(`Loading image for ${item.title}: ${proxiedPosterUrl}`);
            
            const mediaType = item.type || 'movie'; // Ensure type exists
            const year = item.year ? `(${item.year})` : '';
            const runtime = item.runtime ? `${item.runtime} min` : '';
            const watchedDate = formatDate(item.watched_at);

            // --- Season/Episode Info (Task 3) ---
            let episodeInfoHtml = '';
            const seasonNum = item.season; // Use variables for clarity
            const episodeNum = item.episode;

            // Display SxxEyy if both season and episode are present and > 0
            if ((mediaType === 'show' || mediaType === 'tv' || mediaType === 'anime') && seasonNum > 0 && episodeNum > 0) { // Added 'show'
                episodeInfoHtml = `<span class="episode-info"><i class="ph ph-play-circle"></i> S${String(seasonNum).padStart(2, '0')}E${String(episodeNum).padStart(2, '0')}</span>`;
            }
            // Display Exx if only episode is present and > 0 (useful for Anime, maybe some TV specials)
            else if ((mediaType === 'show' || mediaType === 'tv' || mediaType === 'anime') && episodeNum > 0) { // Added 'show'
                 episodeInfoHtml = `<span class="episode-info"><i class="ph ph-play-circle"></i> E${episodeNum}</span>`;
            }
            // --- End Season/Episode Info ---

            // Define icons based on media type
            let mediaIcon;
            switch(mediaType) {
                case 'tv':
                    mediaIcon = 'ph ph-television';
                    break;
                case 'anime':
                    mediaIcon = 'ph ph-star';
                    break;
                default:
                    mediaIcon = 'ph ph-film-strip';
            }
            
            card.innerHTML = `
                <div class="poster-container">
                    <img class="poster-img" src="${proxiedPosterUrl}" alt="${item.title}" 
                        onerror="this.onerror=null; this.src='https://placehold.co/300x450?text=${encodeURIComponent(item.title || 'No Image')}'" 
                        loading="lazy">
                    <span class="media-type"><i class="${mediaIcon}"></i> ${mediaType}</span>
                </div>
                <div class="media-info">
                    <h3 class="media-title">${item.title} ${year}</h3>
                    <div class="media-meta">
                        ${runtime ? `<span><i class="ph ph-clock"></i> ${runtime}</span>` : ''}
                        ${episodeInfoHtml}
                    </div>
                    <div class="watched-date">
                        <i class="ph ph-clock-counter-clockwise"></i> Watched ${watchedDate}
                    </div>
                    <!-- Add File Details - Visible only in list view via CSS -->
                    <div class="file-details">
                        ${item.resolution ? `<span><i class="ph ph-monitor"></i> ${item.resolution}</span>` : ''}
                        ${item.formatted_file_size ? `<span><i class="ph ph-file"></i> ${item.formatted_file_size}</span>` : ''}
                        ${item.file_path ? `<span class="file-path" title="${item.file_path}"><i class="ph ph-folder"></i> ${item.file_path.length > 50 ? '...' + item.file_path.slice(-47) : item.file_path}</span>` : ''}
                    </div>
                    <!-- Removed media-actions div from small card -->
                </div>
            `;

            historyContainer.appendChild(card);
        }
        
        // Preload images for the next page
        if (currentPage < totalPages) {
            const nextPageItems = filteredHistory.slice(endIndex, endIndex + itemsPerPage);
            nextPageItems.forEach(item => {
                const posterUrl = item.poster_url || item.poster || `https://simkl.in/posters/${item.simkl_id}_m.jpg`;
                const proxiedUrl = getProxiedImageUrl(posterUrl);
                getImageWithCache(proxiedUrl);
            });
        }
    }
    
    // Show empty state
    function showEmptyState() {
        historyContainer.style.display = 'none';
        emptyHistory.style.display = 'block';
    }
    
    // Toggle view mode
    viewToggle.addEventListener('click', () => {
        historyContainer.classList.toggle('list-view');
        currentView = historyContainer.classList.contains('list-view') ? 'list' : 'grid';
        localStorage.setItem('simkl_history_view', currentView);
        
        // Update items per page based on view
        itemsPerPage = currentView === 'list' ? 12 : 24;
        
        // Update button icon
        viewToggle.innerHTML = currentView === 'list' 
            ? '<i class="ph ph-grid-four"></i>' 
            : '<i class="ph ph-list"></i>';
            
        // Re-render with new settings
        currentPage = 1;
        renderHistory();
    });
    
    // Toggle theme
    themeToggle.addEventListener('click', () => {
        document.body.classList.toggle('dark-mode');
        currentTheme = document.body.classList.contains('dark-mode') ? 'dark' : 'light';
        localStorage.setItem('simkl_history_theme', currentTheme);
        
        // Update button icon
        themeToggle.innerHTML = currentTheme === 'dark' 
            ? '<i class="ph ph-sun"></i>' 
            : '<i class="ph ph-moon"></i>';
            
        // Update chart if it exists
        if (watchChart) {
            createWatchTrendChart();
        }
    });
    
    // Toggle stats dashboard
    statsToggle.addEventListener('click', () => {
        showStats = dashboard.style.display !== 'block';
        dashboard.style.display = showStats ? 'block' : 'none';
        localStorage.setItem('simkl_history_stats', showStats);
        
        // Update chart if showing stats
        if (showStats && !watchChart) {
            createWatchTrendChart();
        }
    });
    
    // Pagination event listeners
    prevPageBtn.addEventListener('click', () => {
        if (currentPage > 1) {
            currentPage--;
            renderHistory();
            // Scroll to top of container
            historyContainer.scrollIntoView({ behavior: 'smooth' });
        }
    });
    
    nextPageBtn.addEventListener('click', () => {
        const filteredHistory = filterHistory();
        const totalPages = Math.ceil(filteredHistory.length / itemsPerPage);
        
        if (currentPage < totalPages) {
            currentPage++;
            renderHistory();
            // Scroll to top of container
            historyContainer.scrollIntoView({ behavior: 'smooth' });
        }
    });
    
    // Event listeners for filtering and searching
    searchInput.addEventListener('input', () => {
        currentPage = 1; // Reset to first page on search
        renderHistory();
    });
    
    filterType.addEventListener('change', () => {
        currentPage = 1; // Reset to first page on filter change
        renderHistory();
    });
    
    filterYear.addEventListener('change', () => {
        currentPage = 1; // Reset to first page on year filter change
        renderHistory();
    });
    
    sortBy.addEventListener('change', () => {
        currentPage = 1; // Reset to first page on sort change
        renderHistory();
    });
    
    // Keyboard shortcuts
    document.addEventListener('keydown', (e) => {
        if (e.key === 'ArrowLeft' && !prevPageBtn.disabled) {
            prevPageBtn.click();
        } else if (e.key === 'ArrowRight' && !nextPageBtn.disabled) {
            nextPageBtn.click();
        }
    });
    
    // Handle card clicks to show detailed view
    historyContainer.addEventListener('click', (e) => {
        // Find the clicked card
        const card = e.target.closest('.media-card');
        if (!card) return;

        // *** Add check: If the card is already expanded, do nothing ***
        if (card.classList.contains('expanded')) {
            return;
        }
        
        // Prevent opening if the click is on a button or a link
        if (e.target.tagName === 'BUTTON' || e.target.tagName === 'A' || 
            e.target.closest('button') || e.target.closest('a')) {
            return;
        }
        
        expandMediaCard(card);
    });
    
    // Close expanded card when clicking outside
    modalBackdrop.addEventListener('click', (e) => {
        if (e.target === modalBackdrop) {
            closeExpandedCard();
        }
    });
    
    // Close expanded card when Escape key is pressed
    document.addEventListener('keydown', (e) => {
        if (e.key === 'Escape' && activeMediaCard) {
            closeExpandedCard();
        }
    });
    
    // Expand a media card to show detailed information
    function expandMediaCard(card) {
        // If a card is already expanded, close it first
        if (activeMediaCard) {
            closeExpandedCard();
        }
        
        // Get the item data for this card
        const index = Array.from(historyContainer.children).indexOf(card);
        const filteredItems = filterHistory();
        const startIndex = (currentPage - 1) * itemsPerPage;
        const item = filteredItems[startIndex + index];
        
        if (!item) return;
        
        // Set active card
        activeMediaCard = card;
        
        // Clone template content
        const templateClone = expandedContentTemplate.content.cloneNode(true);
        const posterBanner = templateClone.querySelector('.poster-banner');
        const posterImage = templateClone.querySelector('.poster-image');
        const movieTitle = templateClone.querySelector('.movie-title');
        const expandedContent = templateClone.querySelector('.expanded-content');
 
        // --- Set poster banner and title ---
        // Set the movie title text
        if (movieTitle) {
            movieTitle.textContent = item.title + (item.year ? ` (${item.year})` : '');
        }
        
        if (posterImage) {
            if (item.simkl_id) {
                // Fallback to regular landscape poster if fanart fails
                const posterUrl = item.poster_url || item.poster || `${item.simkl_id}`;
                const landscapePosterUrl = getProxiedImageUrl(posterUrl, '_w');
                
                posterImage.style.backgroundImage = `url('${landscapePosterUrl}')`;
                card.style.backgroundImage = `url('${landscapePosterUrl}')`;
            } else {
                // Fallback if no SIMKL ID - use regular poster
                const posterUrl = item.poster_url || item.poster || 'no-image';
                const landscapePosterUrl = getProxiedImageUrl(posterUrl, '_w');
                
                if (landscapePosterUrl !== 'no-image') {
                    posterImage.style.backgroundImage = `url('${landscapePosterUrl}')`;
                    card.style.backgroundImage = `url('${landscapePosterUrl}')`;
                } else {
                    // No image available
                    posterImage.style.backgroundColor = 'var(--border-color)';
                    card.style.backgroundImage = 'none';
                }
            }
        }
        
        // Apply expanded card styles
        card.classList.add('expanded');
        
        // Show modal backdrop
        modalBackdrop.style.display = 'block';
        
        // Fill in details from the item data
        populateExpandedContent(expandedContent, item);
        
        // Add close button event listener
        const closeButton = templateClone.querySelector('.close-button');
        if (closeButton) {
            closeButton.addEventListener('click', closeExpandedCard);
        } else {
            console.error("Could not find close button in template clone.");
        }
        
        // Add action buttons event listeners
        const playMediaBtn = expandedContent.querySelector('.play-media');
        playMediaBtn.addEventListener('click', () => {
            // Open media with default player if file path exists
            if (item.file_path) {
                window.open(`file:///${item.file_path}`, '_blank');
            } else {
                alert('Media file path not available.');
            }
        });
        
        const openFolderBtn = expandedContent.querySelector('.open-folder');
        openFolderBtn.addEventListener('click', () => {
            // Open folder containing the media file
            if (item.file_path) {
                // Extract directory from file path
                const directory = item.file_path.substring(0, item.file_path.lastIndexOf('\\'));
                window.open(`file:///${directory}`, '_blank');
            } else {
                alert('Media folder path not available.');
            }
        });
        
        const openSimklBtn = expandedContent.querySelector('.open-simkl');
        openSimklBtn.addEventListener('click', () => {
            // Open SIMKL page for this item
            const url = item.imdb_id 
                ? `https://api.simkl.com/redirect?to=Simkl&imdb=${item.imdb_id}`
                : `https://api.simkl.com/redirect?to=Simkl&simkl=${item.simkl_id}&title=${encodeURIComponent(item.title)}`;
            window.open(url, '_blank');
        });
        
        // Append the cloned template
        card.appendChild(templateClone);
    }
    
    // Close the expanded card
    function closeExpandedCard() {
        if (!activeMediaCard) return;
        
        // Find all elements added from the template
        const posterBanner = activeMediaCard.querySelector('.poster-banner');
        const closeBtn = activeMediaCard.querySelector('.close-button');
        const expandedContent = activeMediaCard.querySelector('.expanded-content');
        
        // Remove each element if it exists
        if (posterBanner) activeMediaCard.removeChild(posterBanner);
        if (closeBtn) activeMediaCard.removeChild(closeBtn);
        if (expandedContent) activeMediaCard.removeChild(expandedContent);
        
        // Remove any other potential elements that might have been added
        // (including any left from previous implementations)
        const oldElements = activeMediaCard.querySelectorAll('.expanded-background, .movie-title-overlay');
        oldElements.forEach(el => {
            if (activeMediaCard.contains(el)) {
                activeMediaCard.removeChild(el);
            }
        });
        
        // Remove expanded class
        activeMediaCard.classList.remove('expanded');
        
        // Clear the card's background image style
        activeMediaCard.style.backgroundImage = 'none';
        
        // Hide modal backdrop
        modalBackdrop.style.display = 'none';
        
        // Clear active card reference
        activeMediaCard = null;
    }
    
    // Populate expanded content with item data
    function populateExpandedContent(contentElement, item) {
        // --- Find the latest watch entry for this show/anime ---
        let latestEntry = item; // Default to the clicked item
        if ((item.type === 'show' || item.type === 'tv' || item.type === 'anime') && item.simkl_id) {
            const allEntriesForShow = historyData
                .filter(entry => entry.simkl_id === item.simkl_id && (entry.type === 'show' || entry.type === 'tv' || entry.type === 'anime'))
                .sort((a, b) => new Date(b.watched_at || 0) - new Date(a.watched_at || 0));
            
            if (allEntriesForShow.length > 0) {
                latestEntry = allEntriesForShow[0]; // Get the most recent one
            }
        }
        // --- End Find Latest Entry ---

        // Update basic fields with available data (using the original item for general info)
        updateField(contentElement, 'release_date', formatReleaseDate(item.release_date || item.year));
        updateField(contentElement, 'runtime', item.runtime ? `${item.runtime} minutes` : 'Unknown');
        updateField(contentElement, 'overview', item.overview || 'No description available.');
        
        // Add file information if available (using the original item)
        updateField(contentElement, 'file_path', item.file_path || 'Not available');
        updateField(contentElement, 'resolution', item.resolution || 'Unknown');
        updateField(contentElement, 'file_size', formatFileSize(item.file_size) || 'Unknown');
        
        // Show/hide TV details section based on media type
        const tvDetailsSection = contentElement.querySelector('.tv-details');
        const mediaType = item.type || 'movie';
        
        if (mediaType === 'show' || mediaType === 'tv' || mediaType === 'anime') {
            tvDetailsSection.style.display = 'block';

            // --- Display Latest Watched Episode Info (using latestEntry) ---
            let latestEpisodeText = '-'; // Default text
            const latestSeason = latestEntry.season;
            const latestEpisode = latestEntry.episode;

            if (latestSeason > 0 && latestEpisode > 0) {
                latestEpisodeText = `S${String(latestSeason).padStart(2, '0')}E${String(latestEpisode).padStart(2, '0')}`;
            } else if (latestEpisode > 0) { // Handle cases like Anime with only episode number
                 latestEpisodeText = `E${latestEpisode}`;
            }
            updateField(contentElement, 'latest_watched_episode', latestEpisodeText);
            // --- End Latest Watched ---

            // REMOVED: Update TV/Anime specific fields (Status, Watched x of ?)
            // REMOVED: Episode list population
        } else {
            // Hide TV details section if it's a movie
            if (tvDetailsSection) {
                tvDetailsSection.style.display = 'none';
            }
        }
    }
    
    // Format release date
    function formatReleaseDate(dateStr) {
        if (!dateStr) return 'Unknown';
        
        // If it's just a year (4 digits)
        if (/^\d{4}$/.test(dateStr)) {
            return dateStr;
        }
        
        // Try to parse the date
        try {
            const date = new Date(dateStr);
            return date.toLocaleDateString(undefined, { year: 'numeric', month: 'long', day: 'numeric' });
        } catch (e) {
            return dateStr;
        }
    }
    
    // Genres removed, function no longer needed
    // function formatGenres(genres) { ... }
    
    // Format file size
    function formatFileSize(bytes) {
        if (!bytes) return 'Unknown';
        
        // Check if the bytes value already includes a formatted string
        if (typeof bytes === 'string' && bytes.includes(' ')) {
            // Likely already formatted (e.g., "3.5 GB")
            return bytes;
        }
        
        const sizes = ['Bytes', 'KB', 'MB', 'GB', 'TB'];
        if (bytes === 0) return '0 Bytes';
        const i = parseInt(Math.floor(Math.log(bytes) / Math.log(1024)), 10);
        if (i === 0) return `${bytes} ${sizes[i]}`;
        return `${(bytes / (1024 ** i)).toFixed(2)} ${sizes[i]}`;
    }
    
    // Update field in expanded content
    function updateField(contentElement, fieldName, value) {
        const field = contentElement.querySelector(`[data-field="${fieldName}"]`);
        if (field) {
            field.textContent = value;
        }
    }
    
    // REMOVED: populateEpisodeList function as it's no longer used.
    
    // Initial load
    loadHistory();
});