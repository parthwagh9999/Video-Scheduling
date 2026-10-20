/**
 * Video Scheduling Dashboard — Client Application
 * Handles SPA navigation, real-time polling, and interactions with FastAPI backend.
 */

// ── State ─────────────────────────────────────────────────────────────
const state = {
    currentPage: 'overview',
    videos: [],
    excelRecords: [],
    thumbnails: [],
    queueJobs: [],
    calendarDate: new Date(),
    calendarData: null,
    selectedJobIds: new Set(),
    rescheduleTargetJob: null,
    isBulkReschedule: false,
    processingPollingInterval: null,
    heartbeatInterval: null,
    isProcessingStarting: false,
    isQueuePublishingRunning: false,
};

// ── Helpers & UI Utilities ─────────────────────────────────────────────
function showToast(message, type = 'info', duration = 4000) {
    const container = document.getElementById('toast-container');
    if (!container) return;

    const toast = document.createElement('div');
    toast.className = `toast ${type}`;
    
    const icons = {
        success: '✅',
        error: '❌',
        warning: '⚠️',
        info: 'ℹ️'
    };

    toast.innerHTML = `
        <span style="font-size:1.1rem">${icons[type] || 'ℹ️'}</span>
        <div style="flex:1">
            <div style="font-size:0.85rem;font-weight:600;color:var(--text-primary);margin-bottom:2px;">
                ${type.toUpperCase()}
            </div>
            <div style="font-size:0.8rem;color:var(--text-secondary);word-break:break-word;">
                ${escapeHtml(message)}
            </div>
        </div>
    `;

    container.appendChild(toast);
    setTimeout(() => {
        toast.style.opacity = '0';
        toast.style.transform = 'translateX(100px)';
        toast.style.transition = 'all 300ms ease';
        setTimeout(() => toast.remove(), 300);
    }, duration);
}

function escapeHtml(str) {
    if (str === null || str === undefined) return '';
    return String(str)
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#039;');
}

function formatDuration(seconds) {
    if (!seconds) return '0:00';
    const mins = Math.floor(seconds / 60);
    const secs = Math.floor(seconds % 60);
    return `${mins}:${secs.toString().padStart(2, '0')}`;
}

function formatBytes(bytes) {
    if (!bytes) return '0 B';
    const k = 1024;
    const sizes = ['B', 'KB', 'MB', 'GB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return parseFloat((bytes / Math.pow(k, i)).toFixed(1)) + ' ' + sizes[i];
}

// ── Navigation ────────────────────────────────────────────────────────
function navigateTo(pageId) {
    state.currentPage = pageId;

    // Update nav items
    document.querySelectorAll('.sidebar-nav .nav-item').forEach(item => {
        if (item.getAttribute('data-page') === pageId) {
            item.classList.add('active');
        } else {
            item.classList.remove('active');
        }
    });

    // Update pages
    document.querySelectorAll('.main-content .page').forEach(page => {
        if (page.id === `page-${pageId}`) {
            page.style.display = 'block';
        } else {
            page.style.display = 'none';
        }
    });

    // Load data for active page
    switch (pageId) {
        case 'overview':
            loadOverview();
            break;
        case 'library':
            loadLibrary();
            break;
        case 'excel':
            loadExcel();
            break;
        case 'processing':
            loadProcessingStatus();
            break;
        case 'thumbnails':
            loadThumbnails();
            break;
        case 'calendar':
            loadCalendar();
            break;
        case 'queue':
            loadQueue();
            break;
        case 'settings':
            loadSettings();
            break;
    }
}

// ── 1. Overview ───────────────────────────────────────────────────────
async function loadOverview() {
    try {
        const res = await fetch('/api/overview');
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const data = await res.json();

        // Stats grid
        const statsContainer = document.getElementById('overview-stats');
        statsContainer.innerHTML = `
            <div class="stat-tile">
                <div class="stat-label">Source Videos</div>
                <div class="stat-value">${data.source_videos || 0}</div>
            </div>
            <div class="stat-tile success">
                <div class="stat-label">Ready to Publish</div>
                <div class="stat-value">${data.ready_to_publish || 0}</div>
            </div>
            <div class="stat-tile info">
                <div class="stat-label">Thumbnails Ready</div>
                <div class="stat-value">${data.total_thumbnails || 0}</div>
            </div>
            <div class="stat-tile info">
                <div class="stat-label">Published</div>
                <div class="stat-value">${data.published || 0}</div>
            </div>
            <div class="stat-tile warning">
                <div class="stat-label">Queue Size</div>
                <div class="stat-value">${data.scheduled || 0}</div>
            </div>
            <div class="stat-tile">
                <div class="stat-label">Uploaded Today</div>
                <div class="stat-value">${data.uploaded_today || 0}</div>
            </div>
        `;

        // Platform stats
        const platformContainer = document.getElementById('platform-stats');
        const platforms = [
            { name: 'YouTube Shorts', key: 'youtube', icon: '▶️', class: 'youtube' },
            { name: 'Instagram Reels', key: 'instagram', icon: '📸', class: 'instagram' },
            { name: 'Facebook Reels', key: 'facebook', icon: '👥', class: 'facebook' },
        ];

        let platHtml = '';
        for (const p of platforms) {
            const pStat = (data.platforms && data.platforms[p.key]) || { published: 0, scheduled: 0, failed: 0 };
            platHtml += `
                <div class="card">
                    <div class="card-header">
                        <div class="flex items-center gap-2">
                            <span>${p.icon}</span>
                            <span class="platform-badge ${p.class}">${p.name}</span>
                        </div>
                    </div>
                    <div class="card-body">
                        <div class="flex justify-between items-center mb-2">
                            <span class="text-xs text-muted">Published</span>
                            <span class="text-sm font-semibold" style="color:var(--success)">${pStat.published || 0}</span>
                        </div>
                        <div class="flex justify-between items-center mb-2">
                            <span class="text-xs text-muted">Scheduled</span>
                            <span class="text-sm font-semibold" style="color:var(--info)">${pStat.scheduled || 0}</span>
                        </div>
                        <div class="flex justify-between items-center">
                            <span class="text-xs text-muted">Failed / Errors</span>
                            <span class="text-sm font-semibold" style="color:${pStat.failed ? 'var(--error)' : 'var(--text-muted)'}">${pStat.failed || 0}</span>
                        </div>
                    </div>
                </div>
            `;
        }
        platformContainer.innerHTML = platHtml;

    } catch (e) {
        showToast(`Failed to load overview: ${e.message}`, 'error');
    }
}

async function scanVideos() {
    showToast('Scanning video directories, thumbnails, and Excel records...', 'info');
    try {
        const res = await fetch('/api/scan', { method: 'POST' });
        const data = await res.json();
        if (data.errors && data.errors.length > 0) {
            showToast(`Scan complete with ${data.errors.length} warnings. Discovered ${data.start_videos} videos, ${data.thumbnails_valid || 0} thumbnails.`, 'warning');
        } else {
            showToast(`Scan complete! Found ${data.start_videos} videos & validated ${data.thumbnails_valid || 0} thumbnails.`, 'success');
        }
        loadOverview();
    } catch (e) {
        showToast(`Scan failed: ${e.message}`, 'error');
    }
}

async function scanThumbnails() {
    const btn = document.getElementById('btn-scan-thumbnails');
    if (btn) {
        btn.disabled = true;
        btn.innerHTML = '<span class="spinner" style="width:12px;height:12px;display:inline-block;"></span> Scanning...';
    }
    showToast('Scanning and verifying opening-frame thumbnails...', 'info');
    try {
        const res = await fetch('/api/thumbnails/scan', { method: 'POST' });
        const data = await res.json();
        showToast(`Thumbnails Verified! Total: ${data.total_videos}, Valid: ${data.existing_valid}, Extracted: ${data.extracted}, Failed: ${data.failed}`, data.failed > 0 ? 'warning' : 'success');
        if (state.currentPage === 'overview') await loadOverview();
        if (state.currentPage === 'thumbnails') await loadThumbnails();
        if (state.currentPage === 'processing') await loadProcessingStatus();
    } catch (e) {
        showToast(`Thumbnail scan error: ${e.message}`, 'error');
    } finally {
        if (btn) {
            btn.disabled = false;
            btn.innerHTML = '🖼️ Scan Thumbnails';
        }
    }
}

let pipelineEventSource = null;

function closeTerminal() {
    const card = document.getElementById('pipeline-terminal-card');
    if (card) card.style.display = 'none';
}

async function runAllPipeline() {
    const btn = document.getElementById('btn-run-all-pipeline');
    const card = document.getElementById('pipeline-terminal-card');
    const output = document.getElementById('terminal-output');
    const badge = document.getElementById('terminal-step-badge');
    const terminalBody = document.getElementById('terminal-body');

    if (btn && btn.disabled) return;
    if (!confirm('Execute all pipeline steps sequentially?\n\n1. Preflight & Auth Check\n2. Media & Excel Discovery\n3. Thumbnail Scan & Validation\n4. Outro Concatenation & Video Processing\n5. Schedule Generation & Queue Commitment\n6. Final Readiness Report\n\nFull output will stream live to this terminal and your system console.')) {
        return;
    }

    if (card) card.style.display = 'block';
    if (output) output.textContent = '';
    if (badge) {
        badge.style.background = 'var(--accent-primary)';
        badge.textContent = '🚀 Initializing...';
    }

    if (btn) {
        btn.disabled = true;
        btn.innerHTML = '<span class="spinner" style="width:14px;height:14px;display:inline-block;"></span> Running Pipeline...';
    }

    showToast('Full Pipeline execution started! Watch terminal output below.', 'info');

    if (pipelineEventSource) {
        pipelineEventSource.close();
        pipelineEventSource = null;
    }

    try {
        pipelineEventSource = new EventSource('/api/pipeline/run-all');

        pipelineEventSource.onmessage = function(event) {
            try {
                const data = JSON.parse(event.data);
                if (output) {
                    output.textContent += data.line + '\n';
                    if (terminalBody) terminalBody.scrollTop = terminalBody.scrollHeight;
                }
                if (badge) {
                    badge.textContent = `Step ${data.step}/6 (${data.progress}%)`;
                    if (data.step === 6 && data.done) {
                        badge.style.background = 'var(--success)';
                        badge.textContent = '✅ All Complete!';
                    }
                }
                if (btn && data.step) {
                    btn.innerHTML = `<span class="spinner" style="width:14px;height:14px;display:inline-block;"></span> Step ${data.step}/6...`;
                }

                if (data.done) {
                    if (pipelineEventSource) {
                        pipelineEventSource.close();
                        pipelineEventSource = null;
                    }
                    if (btn) {
                        btn.disabled = false;
                        btn.className = 'btn btn-success btn-sm';
                        btn.innerHTML = '✅ All Steps Complete';
                    }
                    showToast('🎉 All pipeline steps executed successfully!', 'success');
                    loadOverview();
                }
            } catch (err) {
                console.error('Error parsing SSE data:', err);
            }
        };

        pipelineEventSource.onerror = function(err) {
            console.warn('Pipeline event source closed:', err);
            if (pipelineEventSource) {
                pipelineEventSource.close();
                pipelineEventSource = null;
            }
            if (btn) {
                btn.disabled = false;
                btn.innerHTML = '⚡ Run All Steps (Full Pipeline)';
            }
            loadOverview();
        };

    } catch (e) {
        showToast(`Pipeline start failed: ${e.message}`, 'error');
        if (btn) {
            btn.disabled = false;
            btn.innerHTML = '⚡ Run All Steps (Full Pipeline)';
        }
    }
}

// ── 2. Video Library ──────────────────────────────────────────────────
async function loadLibrary() {
    const tbody = document.getElementById('library-tbody');
    tbody.innerHTML = `<tr><td colspan="7" class="loading-overlay"><span class="spinner"></span> Loading library...</td></tr>`;

    try {
        const res = await fetch('/api/videos');
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        state.videos = await res.json();
        renderLibrary();
    } catch (e) {
        tbody.innerHTML = `<tr><td colspan="7" class="text-muted" style="text-align:center;padding:24px;">Failed to load library: ${escapeHtml(e.message)}</td></tr>`;
        showToast(`Library load error: ${e.message}`, 'error');
    }
}

function filterLibrary() {
    renderLibrary();
}

function renderLibrary() {
    const tbody = document.getElementById('library-tbody');
    const search = (document.getElementById('library-search')?.value || '').toLowerCase();
    const filterStatus = document.getElementById('library-filter')?.value || '';

    const filtered = state.videos.filter(v => {
        const matchSearch = (v.filename || '').toLowerCase().includes(search) ||
                            (v.seo_title || '').toLowerCase().includes(search);
        
        let status = 'Pending';
        if (v.excel_status) status = v.excel_status;
        else if (v.validation_passed) status = 'Ready';

        const matchStatus = !filterStatus || status.toLowerCase() === filterStatus.toLowerCase();
        return matchSearch && matchStatus;
    });

    if (filtered.length === 0) {
        tbody.innerHTML = `<tr><td colspan="7" class="text-muted" style="text-align:center;padding:32px;">No videos found matching filters.</td></tr>`;
        return;
    }

    tbody.innerHTML = filtered.map(v => {
        const status = v.excel_status || (v.validation_passed ? 'Ready' : 'Pending');
        const statusClass = status.toLowerCase().replace(/\s+/g, '-');
        const outroBadge = v.outro_appended 
            ? `<span class="badge" style="background:var(--success-bg);color:var(--success);padding:2px 6px;border-radius:4px;font-size:0.7rem;">+ Outro</span>`
            : `<span class="text-muted text-xs">Original</span>`;

        const thumbBadge = v.thumbnail_path
            ? `<span title="Valid opening frame thumbnail" style="color:var(--success);font-size:1rem;">🖼️</span>`
            : `<span class="text-muted text-xs">—</span>`;

        return `
            <tr>
                <td class="filename" title="${escapeHtml(v.filename)}">${escapeHtml(v.filename)}</td>
                <td style="max-width:240px;" class="truncate" title="${escapeHtml(v.seo_title || 'No Title')}">
                    ${escapeHtml(v.seo_title || '—')}
                </td>
                <td>${formatDuration(v.output_duration_seconds || v.duration_seconds)}</td>
                <td>${outroBadge}</td>
                <td style="text-align:center">${thumbBadge}</td>
                <td><span class="status-pill ${statusClass}">${escapeHtml(status)}</span></td>
                <td>
                    <div class="flex gap-2 items-center">
                        <span class="platform-badge youtube" title="YouTube Shorts">YT</span>
                        <span class="platform-badge instagram" title="Instagram Reels">IG</span>
                        <span class="platform-badge facebook" title="Facebook Reels">FB</span>
                    </div>
                </td>
            </tr>
        `;
    }).join('');
}

// ── 3. Excel Sync ─────────────────────────────────────────────────────
async function loadExcel() {
    const statsContainer = document.getElementById('excel-stats');
    const tbody = document.getElementById('excel-tbody');

    try {
        const summaryRes = await fetch('/api/excel/summary');
        const summary = await summaryRes.json();

        statsContainer.innerHTML = `
            <div class="stat-tile">
                <div class="stat-label">Total Rows</div>
                <div class="stat-value">${summary.total_records || 0}</div>
            </div>
            <div class="stat-tile success">
                <div class="stat-label">Matched to Files</div>
                <div class="stat-value">${summary.matched_count || 0}</div>
            </div>
            <div class="stat-tile warning">
                <div class="stat-label">Unmatched Videos</div>
                <div class="stat-value">${summary.missing_count || 0}</div>
            </div>
            <div class="stat-tile info">
                <div class="stat-label">Avg Word Count</div>
                <div class="stat-value">${summary.avg_words || 0}</div>
            </div>
        `;

        const recordsRes = await fetch('/api/excel/records');
        state.excelRecords = await recordsRes.json();

        tbody.innerHTML = state.excelRecords.map(r => `
            <tr>
                <td class="filename" title="${escapeHtml(r.filename)}">${escapeHtml(r.filename)}</td>
                <td style="max-width:220px;" class="truncate" title="${escapeHtml(r.seo_title)}">${escapeHtml(r.seo_title || '—')}</td>
                <td>${r.word_count || 0} w</td>
                <td><span class="status-pill ${(r.status || 'pending').toLowerCase()}">${escapeHtml(r.status || 'Pending')}</span></td>
                <td>${escapeHtml(r.scheduled_date || '—')} ${escapeHtml(r.scheduled_time || '')}</td>
                <td>
                    ${r.youtube_url ? `<a href="${escapeHtml(r.youtube_url)}" target="_blank" style="color:var(--accent-primary);text-decoration:none;">🔗 Link</a>` : '<span class="text-muted">—</span>'}
                </td>
            </tr>
        `).join('');

    } catch (e) {
        showToast(`Failed to load Excel data: ${e.message}`, 'error');
    }
}

async function previewExcelSync() {
    const card = document.getElementById('excel-preview-card');
    const body = document.getElementById('excel-preview-body');
    card.style.display = 'block';
    body.innerHTML = `<div class="loading-overlay"><span class="spinner"></span> Checking workbook...</div>`;

    try {
        const res = await fetch('/api/excel/preview-sync');
        const data = await res.json();

        if (data.new_records && data.new_records.length > 0) {
            body.innerHTML = `
                <p class="text-sm text-secondary mb-3">Found <strong>${data.new_records.length}</strong> videos without rows in Excel. These will be added safely preserving all workbook formatting:</p>
                <ul style="padding-left: 20px; font-size:0.82rem; color:var(--text-primary); max-height:200px; overflow-y:auto;">
                    ${data.new_records.map(r => `<li>${escapeHtml(r.filename)} (Auto SEO title will be generated)</li>`).join('')}
                </ul>
            `;
        } else {
            body.innerHTML = `<p class="text-sm" style="color:var(--success);">✅ All video files are already recorded in Excel! No new rows needed.</p>`;
        }
    } catch (e) {
        body.innerHTML = `<p class="text-sm" style="color:var(--error);">Failed preview: ${escapeHtml(e.message)}</p>`;
    }
}

async function runExcelSync() {
    if (!confirm('Sync Excel workbook now? A dated backup will be created automatically in output/excel_backups/.')) return;
    showToast('Syncing Excel workbook...', 'info');

    try {
        const res = await fetch('/api/excel/sync', { method: 'POST' });
        if (!res.ok) {
            const err = await res.json();
            throw new Error(err.detail || 'Sync failed');
        }
        const data = await res.json();
        showToast(`Sync complete! Added: ${data.added_count || 0}, Backup saved: ${data.backup_path || 'Yes'}`, 'success');
        loadExcel();
    } catch (e) {
        showToast(`Sync error: ${e.message}`, 'error');
    }
}

// ── 4. Video Processing ───────────────────────────────────────────────
async function loadProcessingStatus() {
    const statsContainer = document.getElementById('processing-stats');
    const btnStart = document.getElementById('btn-start-processing');
    const btnDryRun = document.getElementById('btn-dry-run-processing');
    const btnPreview = document.getElementById('btn-preview-processing');
    const statusBadge = document.getElementById('processing-status-badge');
    const progressCard = document.getElementById('processing-progress-card');
    const progressBar = document.getElementById('processing-progress-bar');
    const progressText = document.getElementById('processing-progress-text');
    const progressPercent = document.getElementById('processing-progress-percent');
    const progressFilename = document.getElementById('processing-progress-filename');

    try {
        const res = await fetch('/api/processing/status');
        const data = await res.json();

        if (statsContainer) {
            statsContainer.innerHTML = `
                <div class="stat-tile">
                    <div class="stat-label">Total Videos</div>
                    <div class="stat-value">${data.total_source || 0}</div>
                </div>
                <div class="stat-tile success">
                    <div class="stat-label">Processed</div>
                    <div class="stat-value">${data.processed || 0}</div>
                </div>
                <div class="stat-tile info">
                    <div class="stat-label">Valid Thumbnails</div>
                    <div class="stat-value">${data.thumbnails_valid || 0}</div>
                </div>
                <div class="stat-tile ${data.remaining === 0 ? 'success' : 'warning'}">
                    <div class="stat-label">Remaining</div>
                    <div class="stat-value">${data.remaining || 0}</div>
                </div>
            `;
        }

        // 1. ACTIVE RUNNING STATE
        if (data.is_running) {
            if (btnStart) {
                btnStart.disabled = true;
                btnStart.className = 'btn btn-primary';
                btnStart.innerHTML = `<span class="spinner" style="width:14px;height:14px;display:inline-block;margin-right:6px;"></span> Processing (${data.progress || 0}/${data.total || data.total_source || 0})...`;
            }
            if (btnDryRun) btnDryRun.disabled = true;
            if (btnPreview) btnPreview.disabled = true;

            const total = data.total || data.total_source || 1;
            const current = data.progress || 0;
            const pct = Math.min(100, Math.round((current / total) * 100));

            if (progressCard) progressCard.style.display = 'block';
            if (progressBar) progressBar.style.width = `${pct}%`;
            if (progressPercent) progressPercent.innerText = `${pct}%`;
            if (progressText) {
                progressText.innerHTML = `<span class="spinner" style="width:14px;height:14px;display:inline-block;"></span> Processing video ${current} of ${total}...`;
            }
            if (progressFilename) {
                progressFilename.innerText = data.current_file ? `Current file: ${data.current_file}` : (data.message || '');
            }

            if (statusBadge) {
                statusBadge.style.display = 'inline-flex';
                statusBadge.className = 'status-pill scheduled';
                statusBadge.innerHTML = `⏳ In Progress: ${current}/${total}`;
            }

            // Ensure polling is active
            if (!state.processingPollingInterval) {
                state.processingPollingInterval = setInterval(loadProcessingStatus, 1500);
            }
        }
        // 2. COMPLETED STATE (Done - All videos ready and validated)
        else if (data.is_complete || (data.total_source > 0 && data.remaining === 0 && (data.thumbnails_valid || 0) >= data.total_source)) {
            // Stop polling once complete
            if (state.processingPollingInterval) {
                clearInterval(state.processingPollingInterval);
                state.processingPollingInterval = null;
            }

            if (btnStart) {
                btnStart.disabled = true;
                btnStart.className = 'btn btn-success';
                btnStart.innerHTML = '✅ Done (All Videos Ready)';
                btnStart.title = 'All videos and thumbnails are already processed and validated. Redundant processing is locked.';
            }
            if (btnDryRun) btnDryRun.disabled = false;
            if (btnPreview) btnPreview.disabled = false;

            if (progressCard) {
                if (progressBar) progressBar.style.width = '100%';
                if (progressPercent) progressPercent.innerText = '100%';
                if (progressText) progressText.innerHTML = '✅ All processing completed successfully!';
                setTimeout(() => {
                    if (progressCard && !state.processingPollingInterval) {
                        progressCard.style.display = 'none';
                    }
                }, 2500);
            }

            if (statusBadge) {
                statusBadge.style.display = 'inline-flex';
                statusBadge.className = 'status-pill published';
                statusBadge.innerHTML = `✅ Complete: All ${data.total_source} Ready (${data.thumbnails_valid} Thumbnails)`;
            }
        }
        // 3. IDLE WITH REMAINING VIDEOS
        else {
            if (state.processingPollingInterval) {
                clearInterval(state.processingPollingInterval);
                state.processingPollingInterval = null;
            }

            if (btnStart) {
                btnStart.disabled = false;
                btnStart.className = 'btn btn-primary';
                btnStart.innerHTML = data.remaining > 0 ? `🚀 Start Processing (${data.remaining} remaining)` : '🚀 Start Processing';
                btnStart.title = 'Render concatenated videos and extract opening frame thumbnails';
            }
            if (btnDryRun) btnDryRun.disabled = false;
            if (btnPreview) btnPreview.disabled = false;
            if (progressCard) progressCard.style.display = 'none';
            if (statusBadge) statusBadge.style.display = 'none';
        }

    } catch (e) {
        console.error('Failed to load processing status:', e);
    }
}

async function previewProcessing() {
    const rule = document.getElementById('outro-rule').value;
    const tbody = document.getElementById('processing-tbody');
    tbody.innerHTML = `<tr><td colspan="4" class="loading-overlay"><span class="spinner"></span> Computing outro assignments...</td></tr>`;

    try {
        const res = await fetch(`/api/processing/preview?outro_rule=${rule}&start_index=0`);
        const data = await res.json();

        tbody.innerHTML = data.sequence.map(item => `
            <tr>
                <td style="font-weight:600;color:var(--text-muted)">#${item.position}</td>
                <td class="filename">${escapeHtml(item.filename)}</td>
                <td>
                    ${item.gets_outro 
                        ? `<span class="badge" style="background:var(--success-bg);color:var(--success);padding:3px 8px;border-radius:4px;font-size:0.75rem;">YES (+ Outro)</span>` 
                        : `<span class="text-muted text-xs">No Outro</span>`}
                </td>
                <td class="text-sm">${item.end_video ? escapeHtml(item.end_video) : '—'}</td>
            </tr>
        `).join('');

        showToast(`Preview generated: ${data.with_outro} videos get outro, ${data.without_outro} remain standalone.`, 'info');
    } catch (e) {
        tbody.innerHTML = `<tr><td colspan="4" style="text-align:center;color:var(--error);padding:20px;">Preview failed: ${escapeHtml(e.message)}</td></tr>`;
    }
}

async function startProcessing(dryRun) {
    const btnStart = document.getElementById('btn-start-processing');
    const btnDryRun = document.getElementById('btn-dry-run-processing');
    const btnPreview = document.getElementById('btn-preview-processing');
    const rule = document.getElementById('outro-rule').value;
    const actionName = dryRun ? 'Dry Run' : 'Video Processing';

    // Guard: Prevent double clicking or clicking when already disabled/done
    if (state.isProcessingStarting) return;
    if (!dryRun && btnStart && btnStart.disabled) {
        showToast('Processing is already running or already completed.', 'info');
        return;
    }

    if (!dryRun && !confirm('Start video processing now? FFmpeg will render concatenated videos and extract opening frame thumbnails (existing valid files are automatically reused).')) {
        return;
    }

    state.isProcessingStarting = true;

    // Immediately lock UI buttons to prevent rapid multiple clicks
    if (!dryRun) {
        if (btnStart) {
            btnStart.disabled = true;
            btnStart.innerHTML = `<span class="spinner" style="width:14px;height:14px;display:inline-block;margin-right:6px;"></span> Starting...`;
        }
        if (btnDryRun) btnDryRun.disabled = true;
        if (btnPreview) btnPreview.disabled = true;
    }

    showToast(`Starting ${actionName}...`, 'info');

    try {
        const res = await fetch(`/api/processing/start?outro_rule=${rule}&dry_run=${dryRun}`, { method: 'POST' });
        const data = await res.json();

        if (dryRun) {
            showToast(`Dry run complete! Simulated ${data.total} videos.`, 'success');
            if (btnDryRun) btnDryRun.disabled = false;
            if (btnPreview) btnPreview.disabled = false;
        } else if (data.status === 'already_complete') {
            showToast(data.message, 'success');
            await loadProcessingStatus();
        } else if (data.status === 'already_running') {
            showToast(data.message, 'warning');
            if (state.processingPollingInterval) clearInterval(state.processingPollingInterval);
            state.processingPollingInterval = setInterval(loadProcessingStatus, 1500);
            await loadProcessingStatus();
        } else {
            showToast('Processing started in background! Live progress active.', 'success');
            if (state.processingPollingInterval) clearInterval(state.processingPollingInterval);
            state.processingPollingInterval = setInterval(loadProcessingStatus, 1500);
            await loadProcessingStatus();
        }
    } catch (e) {
        showToast(`Processing start failed: ${e.message}`, 'error');
        await loadProcessingStatus();
    } finally {
        state.isProcessingStarting = false;
    }
}

// ── 5. Thumbnails ─────────────────────────────────────────────────────
async function loadThumbnails() {
    const grid = document.getElementById('thumb-grid');
    grid.innerHTML = `<div class="loading-overlay" style="grid-column:1/-1"><span class="spinner"></span> Loading extracted thumbnails...</div>`;

    try {
        const res = await fetch('/api/thumbnails');
        state.thumbnails = await res.json();

        if (state.thumbnails.length === 0) {
            grid.innerHTML = `<div class="text-muted" style="grid-column:1/-1;text-align:center;padding:40px;">No thumbnails extracted yet. Run Video Processing first.</div>`;
            return;
        }

        grid.innerHTML = state.thumbnails.map(t => `
            <div class="thumb-card">
                <img src="/api/thumbnails/image/${t.source_video_id}" alt="Thumbnail" loading="lazy" onerror="this.src='data:image/svg+xml,<svg xmlns=\\'http://www.w3.org/2000/svg\\' viewBox=\\'0 0 100 100\\'><text y=\\'.9em\\' font-size=\\'30\\'>🖼️</text></svg>'">
                <div class="thumb-info">
                    <div class="thumb-filename" title="${escapeHtml(t.video_filename)}">${escapeHtml(t.video_filename)}</div>
                    <div class="flex justify-between items-center mt-2">
                        <span class="text-xs text-muted">${t.width}x${t.height}</span>
                        <span class="status-pill ${t.is_valid ? 'scheduled' : 'failed'}" style="font-size:0.65rem;">
                            ${t.is_valid ? 'Valid Frame' : 'Needs Review'}
                        </span>
                    </div>
                </div>
            </div>
        `).join('');

    } catch (e) {
        grid.innerHTML = `<div style="grid-column:1/-1;text-align:center;color:var(--error);padding:40px;">Failed to load thumbnails: ${escapeHtml(e.message)}</div>`;
    }
}

// ── 6. Calendar ───────────────────────────────────────────────────────
function calendarNav(offset) {
    state.calendarDate.setMonth(state.calendarDate.getMonth() + offset);
    loadCalendar();
}

async function loadCalendar() {
    const monthEl = document.getElementById('calendar-month');
    const grid = document.getElementById('calendar-grid');
    const platform = document.getElementById('calendar-platform-filter')?.value || '';

    const year = state.calendarDate.getFullYear();
    const month = state.calendarDate.getMonth();
    const monthStr = `${year}-${String(month + 1).padStart(2, '0')}`;

    try {
        let url = `/api/schedule/calendar?month=${monthStr}`;
        if (platform) url += `&platform=${encodeURIComponent(platform)}`;

        const res = await fetch(url);
        state.calendarData = await res.json();
        renderCalendar();
    } catch (e) {
        console.error('Failed to load calendar events:', e);
        showToast(`Failed to load calendar: ${e.message}`, 'error');
    }
}

function renderCalendar() {
    const monthEl = document.getElementById('calendar-month');
    const grid = document.getElementById('calendar-grid');
    if (!monthEl || !grid) return;

    const year = state.calendarDate.getFullYear();
    const month = state.calendarDate.getMonth();
    const monthNames = ["January", "February", "March", "April", "May", "June",
                        "July", "August", "September", "October", "November", "December"];

    monthEl.textContent = `${monthNames[month]} ${year}`;

    const daysInMonth = new Date(year, month + 1, 0).getDate();
    const firstDayIndex = new Date(year, month, 1).getDay();

    const dayHeaders = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'];
    let html = dayHeaders.map(d => `<div class="calendar-day-header">${d}</div>`).join('');

    // Blank cells before first day
    for (let i = 0; i < firstDayIndex; i++) {
        html += `<div class="calendar-day" style="opacity:0.25;background:transparent;border:none;"></div>`;
    }

    const todayStr = new Date().toISOString().split('T')[0];

    for (let day = 1; day <= daysInMonth; day++) {
        const dateStr = `${year}-${String(month + 1).padStart(2, '0')}-${String(day).padStart(2, '0')}`;
        const isToday = dateStr === todayStr;

        // Check if we have slots scheduled for this day from DB
        const daySlots = (state.calendarData && state.calendarData.calendar && state.calendarData.calendar[dateStr]) || [];

        let slotsHtml = '';
        for (const slot of daySlots) {
            const timeClass = (slot.time || '').replace(':', '');
            const plat = (slot.platform || 'youtube').toLowerCase();
            const platShort = plat === 'youtube' ? 'YT' : plat === 'instagram' ? 'IG' : 'FB';
            const status = (slot.status || 'pending').toLowerCase();
            const title = slot.title || slot.filename || '—';

            slotsHtml += `
                <div class="calendar-slot slot-${timeClass}" onclick="openRescheduleModalFromCalendar(${slot.id})" title="Click to reschedule: ${escapeHtml(title)} [${plat.toUpperCase()} - ${status}]">
                    <span class="slot-time">${escapeHtml(slot.time)}</span>
                    <span class="platform-mini ${plat}">${platShort}</span>
                    <span class="slot-status-dot ${status}"></span>
                    <span class="slot-title">${escapeHtml(title)}</span>
                </div>
            `;
        }

        html += `
            <div class="calendar-day ${isToday ? 'today' : ''}">
                <div class="day-number">
                    <span>${day}</span>
                    ${daySlots.length > 0 ? `<span class="text-xs text-muted" style="font-weight:400;">(${daySlots.length})</span>` : ''}
                </div>
                ${slotsHtml}
            </div>
        `;
    }

    grid.innerHTML = html;
}

function openRescheduleModalFromCalendar(jobId) {
    let foundJob = null;
    if (state.calendarData && state.calendarData.calendar) {
        for (const date in state.calendarData.calendar) {
            const match = state.calendarData.calendar[date].find(j => j.id === jobId);
            if (match) {
                foundJob = match;
                break;
            }
        }
    }
    if (!foundJob && state.queueJobs) {
        foundJob = state.queueJobs.find(j => j.id === jobId);
    }
    if (foundJob) {
        openRescheduleModal(foundJob);
    } else {
        showToast(`Job #${jobId} details not found.`, 'warning');
    }
}

function openRescheduleModalFromQueue(jobId) {
    let foundJob = null;
    if (state.queueJobs) {
        foundJob = state.queueJobs.find(j => j.id === jobId);
    }
    if (!foundJob && state.calendarData && state.calendarData.calendar) {
        for (const date in state.calendarData.calendar) {
            const match = state.calendarData.calendar[date].find(j => j.id === jobId);
            if (match) {
                foundJob = match;
                break;
            }
        }
    }
    if (foundJob) {
        openRescheduleModal(foundJob);
    } else {
        showToast(`Job #${jobId} details not found.`, 'warning');
    }
}

function openRescheduleModal(job) {
    state.rescheduleTargetJob = job;
    state.isBulkReschedule = false;

    const modal = document.getElementById('modal-reschedule');
    const heading = document.getElementById('modal-reschedule-heading');
    const singleCard = document.getElementById('modal-job-info-card');
    const bulkCard = document.getElementById('modal-bulk-info-card');
    const platBadge = document.getElementById('modal-job-platform-badge');
    const statusPill = document.getElementById('modal-job-status-pill');
    const filenameEl = document.getElementById('modal-job-filename');
    const schedEl = document.getElementById('modal-job-current-schedule');
    const syncGroup = document.getElementById('modal-sync-platforms-group');
    const quickPendingBtn = document.getElementById('modal-btn-quick-pending');

    const dateInput = document.getElementById('modal-reschedule-date');
    const timeInput = document.getElementById('modal-reschedule-time');
    const statusSelect = document.getElementById('modal-reschedule-status');
    const allPlatCheckbox = document.getElementById('modal-reschedule-all-platforms');
    const jobIdInput = document.getElementById('modal-reschedule-job-id');

    if (!modal) return;

    // Show single card, hide bulk card
    if (singleCard) singleCard.style.display = 'block';
    if (bulkCard) bulkCard.style.display = 'none';
    if (syncGroup) syncGroup.style.display = 'block';
    if (quickPendingBtn) quickPendingBtn.style.display = 'inline-block';

    const fname = job.source_filename || job.filename || '—';
    const plat = (job.platform || 'youtube').toLowerCase();
    const curStatus = (job.status || 'pending').toLowerCase();
    const curDate = job.scheduled_date || job.date || '';
    const curTime = job.scheduled_time || job.time || '08:30';

    if (heading) heading.textContent = `🗓️ Reschedule Video Slot`;
    if (jobIdInput) jobIdInput.value = job.id;
    if (platBadge) {
        platBadge.className = `platform-badge ${plat}`;
        platBadge.textContent = plat.toUpperCase();
    }
    if (statusPill) {
        statusPill.className = `status-pill ${curStatus}`;
        statusPill.textContent = curStatus;
    }
    if (filenameEl) filenameEl.textContent = fname;
    if (schedEl) schedEl.textContent = `Current Slot: ${curDate || '—'} @ ${curTime} IST`;

    if (dateInput) dateInput.value = curDate;
    if (timeInput) timeInput.value = curTime;
    if (statusSelect) statusSelect.value = '';
    if (allPlatCheckbox) allPlatCheckbox.checked = true;

    modal.style.display = 'flex';
}

function openBulkRescheduleModal() {
    if (!state.selectedJobIds || state.selectedJobIds.size === 0) {
        showToast('Please select at least one video in the queue first.', 'warning');
        return;
    }

    state.isBulkReschedule = true;
    state.rescheduleTargetJob = null;

    const modal = document.getElementById('modal-reschedule');
    const heading = document.getElementById('modal-reschedule-heading');
    const singleCard = document.getElementById('modal-job-info-card');
    const bulkCard = document.getElementById('modal-bulk-info-card');
    const bulkCountText = document.getElementById('modal-bulk-count-text');
    const syncGroup = document.getElementById('modal-sync-platforms-group');
    const quickPendingBtn = document.getElementById('modal-btn-quick-pending');

    const dateInput = document.getElementById('modal-reschedule-date');
    const timeInput = document.getElementById('modal-reschedule-time');
    const statusSelect = document.getElementById('modal-reschedule-status');

    if (!modal) return;

    if (singleCard) singleCard.style.display = 'none';
    if (bulkCard) bulkCard.style.display = 'block';
    if (bulkCountText) bulkCountText.textContent = `Bulk Rescheduling ${state.selectedJobIds.size} Selected Job(s)`;
    if (syncGroup) syncGroup.style.display = 'none';
    if (quickPendingBtn) quickPendingBtn.style.display = 'none';

    if (heading) heading.textContent = `🗓️ Bulk Reschedule (${state.selectedJobIds.size} Videos)`;

    // Default to tomorrow or today
    const tomorrow = new Date();
    tomorrow.setDate(tomorrow.getDate() + 1);
    const tomStr = tomorrow.toISOString().split('T')[0];

    if (dateInput) dateInput.value = tomStr;
    if (timeInput) timeInput.value = '08:30';
    if (statusSelect) statusSelect.value = 'pending';

    modal.style.display = 'flex';
}

function closeRescheduleModal() {
    const modal = document.getElementById('modal-reschedule');
    if (modal) modal.style.display = 'none';
    state.rescheduleTargetJob = null;
    state.isBulkReschedule = false;
}

function setModalTime(timeStr) {
    const timeInput = document.getElementById('modal-reschedule-time');
    if (timeInput) timeInput.value = timeStr;
}

async function submitReschedule() {
    const dateInput = document.getElementById('modal-reschedule-date');
    const timeInput = document.getElementById('modal-reschedule-time');
    const statusSelect = document.getElementById('modal-reschedule-status');
    const allPlatCheckbox = document.getElementById('modal-reschedule-all-platforms');

    const newDate = (dateInput?.value || '').trim();
    const newTime = (timeInput?.value || '').trim();
    const newStatus = (statusSelect?.value || '').trim();

    if (!newDate || !newTime) {
        showToast('Please specify both Scheduled Date and Scheduled Time.', 'warning');
        return;
    }

    const saveBtn = document.getElementById('modal-btn-save');
    if (saveBtn) {
        saveBtn.disabled = true;
        saveBtn.innerHTML = '<span class="spinner" style="width:12px;height:12px;display:inline-block;margin-right:4px;"></span> Saving...';
    }

    try {
        if (state.isBulkReschedule) {
            // Bulk reschedule
            const jobIds = Array.from(state.selectedJobIds);
            const payload = {
                job_ids: jobIds,
                scheduled_date: newDate,
                scheduled_time: newTime,
            };
            if (newStatus) payload.status = newStatus;

            const res = await fetch('/api/schedule/jobs/bulk-reschedule', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload)
            });
            const data = await res.json();
            if (!res.ok) throw new Error(data.detail || 'Bulk reschedule failed');

            showToast(data.message || `Bulk rescheduled ${data.updated_count} jobs.`, 'success');
            clearQueueSelection();
        } else {
            // Single job reschedule (with optional all-platform sync)
            if (!state.rescheduleTargetJob) throw new Error('No target job selected');

            const payload = {
                job_id: state.rescheduleTargetJob.id,
                scheduled_date: newDate,
                scheduled_time: newTime,
                update_all_platforms: allPlatCheckbox ? allPlatCheckbox.checked : true,
            };
            if (newStatus) payload.status = newStatus;

            const res = await fetch('/api/schedule/jobs/reschedule', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload)
            });
            const data = await res.json();
            if (!res.ok) throw new Error(data.detail || 'Reschedule failed');

            showToast(data.message || `Job rescheduled to ${newDate} @ ${newTime} IST.`, 'success');
        }

        closeRescheduleModal();
        loadCalendar();
        loadQueue();
        loadOverview();
        loadExcel();
    } catch (err) {
        console.error('Error submitting reschedule:', err);
        showToast(`Failed to reschedule: ${err.message}`, 'error');
    } finally {
        if (saveBtn) {
            saveBtn.disabled = false;
            saveBtn.innerHTML = '💾 Save & Reschedule';
        }
    }
}

async function modalResetToPending() {
    if (!state.rescheduleTargetJob) return;
    const jobId = state.rescheduleTargetJob.id;
    const fname = state.rescheduleTargetJob.source_filename || state.rescheduleTargetJob.filename || 'video';

    if (!confirm(`Reset status of "${fname}" back to PENDING?\n\nThis will clear any draft errors, reset attempt counts, and re-arm the job for automated publishing.`)) {
        return;
    }

    try {
        const res = await fetch('/api/schedule/jobs/update-status', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ job_id: jobId, status: 'pending' })
        });
        const data = await res.json();
        if (!res.ok) throw new Error(data.detail || 'Reset to pending failed');

        showToast(`✅ Reset to Pending: "${fname}" will be published on next run.`, 'success');
        closeRescheduleModal();
        loadCalendar();
        loadQueue();
        loadOverview();
        loadExcel();
    } catch (err) {
        showToast(`Error resetting status: ${err.message}`, 'error');
    }
}

// ── 7. Publishing Queue ───────────────────────────────────────────────
async function loadQueue() {
    const platform = document.getElementById('queue-platform-filter')?.value || '';
    const status = document.getElementById('queue-status-filter')?.value || '';
    const tbody = document.getElementById('queue-tbody');
    const pipeline = document.getElementById('queue-pipeline');

    tbody.innerHTML = `<tr><td colspan="9" class="loading-overlay"><span class="spinner"></span> Loading queue...</td></tr>`;

    try {
        let url = '/api/schedule/jobs?';
        if (platform) url += `platform=${platform}&`;
        if (status) url += `status=${status}&`;

        const res = await fetch(url);
        state.queueJobs = await res.json();

        // Update pipeline summary counts
        const stages = [
            { key: 'all', label: 'Total Jobs' },
            { key: 'pending', label: 'Pending' },
            { key: 'uploading', label: 'Uploading' },
            { key: 'scheduled', label: 'Scheduled' },
            { key: 'published', label: 'Published' },
            { key: 'failed', label: 'Failed' },
        ];

        const counts = {
            all: state.queueJobs.length,
            pending: state.queueJobs.filter(j => j.status === 'pending').length,
            uploading: state.queueJobs.filter(j => j.status === 'uploading').length,
            scheduled: state.queueJobs.filter(j => j.status === 'scheduled').length,
            published: state.queueJobs.filter(j => j.status === 'published').length,
            failed: state.queueJobs.filter(j => j.status === 'failed').length,
        };

        pipeline.innerHTML = stages.map(s => `
            <div class="pipeline-stage ${status === s.key ? 'active' : ''}" onclick="setQueueFilter('${s.key}')">
                <div class="stage-count">${counts[s.key] || 0}</div>
                <div class="stage-label">${s.label}</div>
            </div>
        `).join('');

        // Badge in sidebar
        const badge = document.getElementById('queue-badge');
        if (badge) {
            if (counts.pending > 0) {
                badge.style.display = 'inline-block';
                badge.textContent = counts.pending;
            } else {
                badge.style.display = 'none';
            }
        }

        renderQueueTable();
        updateBulkBar();

    } catch (e) {
        tbody.innerHTML = `<tr><td colspan="9" class="text-muted" style="text-align:center;padding:24px;">Failed to load queue: ${escapeHtml(e.message)}</td></tr>`;
    }
}

function renderQueueTable() {
    const tbody = document.getElementById('queue-tbody');
    const searchVal = (document.getElementById('queue-search-input')?.value || '').toLowerCase().trim();

    let jobs = state.queueJobs || [];
    if (searchVal) {
        jobs = jobs.filter(j => {
            const fname = (j.source_filename || j.filename || '').toLowerCase();
            const title = (j.seo_title || '').toLowerCase();
            return fname.includes(searchVal) || title.includes(searchVal);
        });
    }

    if (jobs.length === 0) {
        tbody.innerHTML = `<tr><td colspan="9" class="text-muted" style="text-align:center;padding:32px;">No matching jobs found in queue.</td></tr>`;
        return;
    }

    tbody.innerHTML = jobs.map(j => {
        const platClass = (j.platform || 'youtube').toLowerCase();
        const statusClass = (j.status || 'pending').toLowerCase().replace(/\s+/g, '-');
        const fname = j.source_filename || j.filename || '—';
        const attempts = j.attempt_count ?? j.retry_count ?? 0;
        const url = j.remote_url || j.platform_url || '';
        const errorHtml = j.error_message ? `<div style="font-size:0.75rem; color:#f87171; margin-top:3px; word-break:break-word;">⚠️ ${escapeHtml(j.error_message)}</div>` : '';
        const isChecked = state.selectedJobIds.has(j.id);

        const statusOptions = ['pending', 'scheduled', 'uploading', 'uploaded', 'published', 'failed', 'needs_attention'];
        const selectOptionsHtml = statusOptions.map(st => `
            <option value="${st}" ${j.status === st ? 'selected' : ''}>${st}</option>
        `).join('');

        return `
            <tr id="queue-row-${j.id}">
                <td style="text-align:center;">
                    <input type="checkbox" class="queue-row-checkbox" data-id="${j.id}" ${isChecked ? 'checked' : ''} onchange="onQueueRowCheck(${j.id}, this.checked)">
                </td>
                <td class="filename" title="${escapeHtml(fname)}">
                    <div style="font-weight:600; color:var(--text-primary); cursor:pointer;" onclick="openRescheduleModalFromQueue(${j.id})">${escapeHtml(fname)}</div>
                    ${errorHtml}
                </td>
                <td><span class="platform-badge ${platClass}">${escapeHtml(j.platform)}</span></td>
                <td><span style="font-family:monospace; font-size:0.82rem; cursor:pointer;" onclick="openRescheduleModalFromQueue(${j.id})" title="Click to edit date">${escapeHtml(j.scheduled_date || '—')}</span></td>
                <td><span style="font-family:monospace; font-size:0.82rem; cursor:pointer;" onclick="openRescheduleModalFromQueue(${j.id})" title="Click to edit time">${escapeHtml(j.scheduled_time || '—')}</span></td>
                <td>
                    <select class="status-select-badge ${statusClass}" onchange="changeJobStatus(${j.id}, this.value)" title="Change job status directly">
                        ${selectOptionsHtml}
                    </select>
                </td>
                <td style="text-align:center">${attempts}</td>
                <td>
                    ${url ? `<a href="${escapeHtml(url)}" target="_blank" style="color:var(--accent-primary);text-decoration:none;font-weight:600;">View</a>` : '—'}
                </td>
                <td style="text-align:right; white-space:nowrap;">
                    <div class="flex items-center gap-1 justify-end">
                        ${j.status !== 'pending' ? `
                            <button class="btn btn-secondary btn-sm" onclick="quickSetPending(${j.id}, '${escapeHtml(fname)}')" title="Mark Draft Deleted & Reset to Pending" style="padding:3px 8px; font-size:0.75rem; border-color:#f59e0b; color:#fbbf24;">
                                ↺ Pending
                            </button>
                        ` : ''}
                        <button class="btn btn-secondary btn-sm" onclick="openRescheduleModalFromQueue(${j.id})" title="Reschedule Date & Time" style="padding:3px 8px; font-size:0.75rem;">
                            ✏️ Edit
                        </button>
                    </div>
                </td>
            </tr>
        `;
    }).join('');

    // Update select all checkbox state
    const selectAllCheckbox = document.getElementById('queue-select-all');
    if (selectAllCheckbox && jobs.length > 0) {
        const allChecked = jobs.every(j => state.selectedJobIds.has(j.id));
        selectAllCheckbox.checked = allChecked;
    }
}

function filterQueueRows() {
    renderQueueTable();
}

async function changeJobStatus(jobId, newStatus) {
    try {
        const res = await fetch('/api/schedule/jobs/update-status', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ job_id: jobId, status: newStatus })
        });
        const data = await res.json();
        if (!res.ok) throw new Error(data.detail || 'Failed to update status');

        showToast(`Job #${jobId} status updated to '${newStatus}'.`, 'success');
        loadQueue();
        loadOverview();
        loadCalendar();
    } catch (err) {
        showToast(`Status update failed: ${err.message}`, 'error');
        loadQueue();
    }
}

async function quickSetPending(jobId, filename) {
    try {
        const res = await fetch('/api/schedule/jobs/update-status', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ job_id: jobId, status: 'pending' })
        });
        const data = await res.json();
        if (!res.ok) throw new Error(data.detail || 'Reset failed');

        showToast(`↺ Reset to Pending: Ready for automated publishing!`, 'success');
        loadQueue();
        loadOverview();
        loadCalendar();
    } catch (err) {
        showToast(`Failed to reset job: ${err.message}`, 'error');
    }
}

function toggleSelectAllQueue(checked) {
    const searchVal = (document.getElementById('queue-search-input')?.value || '').toLowerCase().trim();
    let jobs = state.queueJobs || [];
    if (searchVal) {
        jobs = jobs.filter(j => {
            const fname = (j.source_filename || j.filename || '').toLowerCase();
            const title = (j.seo_title || '').toLowerCase();
            return fname.includes(searchVal) || title.includes(searchVal);
        });
    }

    jobs.forEach(j => {
        if (checked) {
            state.selectedJobIds.add(j.id);
        } else {
            state.selectedJobIds.delete(j.id);
        }
    });

    renderQueueTable();
    updateBulkBar();
}

function onQueueRowCheck(jobId, checked) {
    if (checked) {
        state.selectedJobIds.add(jobId);
    } else {
        state.selectedJobIds.delete(jobId);
    }

    const selectAllCheckbox = document.getElementById('queue-select-all');
    if (selectAllCheckbox && state.queueJobs && state.queueJobs.length > 0) {
        selectAllCheckbox.checked = state.queueJobs.every(j => state.selectedJobIds.has(j.id));
    }

    updateBulkBar();
}

function updateBulkBar() {
    const bar = document.getElementById('queue-bulk-bar');
    const countBadge = document.getElementById('queue-selected-count');
    if (!bar) return;

    const count = state.selectedJobIds ? state.selectedJobIds.size : 0;
    if (count > 0) {
        bar.style.display = 'flex';
        if (countBadge) countBadge.textContent = `${count} Selected`;
    } else {
        bar.style.display = 'none';
    }
}

function clearQueueSelection() {
    if (state.selectedJobIds) state.selectedJobIds.clear();
    const selectAllCheckbox = document.getElementById('queue-select-all');
    if (selectAllCheckbox) selectAllCheckbox.checked = false;
    renderQueueTable();
    updateBulkBar();
}

async function applyBulkStatus() {
    const select = document.getElementById('queue-bulk-status-select');
    const newStatus = (select?.value || 'pending').trim();

    if (!state.selectedJobIds || state.selectedJobIds.size === 0) {
        showToast('Please select at least one video first.', 'warning');
        return;
    }

    const count = state.selectedJobIds.size;
    if (!confirm(`Update status of ${count} selected video(s) to '${newStatus.toUpperCase()}'?`)) {
        return;
    }

    try {
        const res = await fetch('/api/schedule/jobs/update-status', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                job_ids: Array.from(state.selectedJobIds),
                status: newStatus
            })
        });
        const data = await res.json();
        if (!res.ok) throw new Error(data.detail || 'Bulk status update failed');

        showToast(data.message || `Updated ${count} jobs to '${newStatus}'.`, 'success');
        clearQueueSelection();
        loadQueue();
        loadOverview();
        loadCalendar();
    } catch (err) {
        showToast(`Bulk update error: ${err.message}`, 'error');
    }
}

function setQueueFilter(statusKey) {
    const filter = document.getElementById('queue-status-filter');
    if (filter) {
        filter.value = statusKey === 'all' ? '' : statusKey;
        loadQueue();
    }
}

let queuePublishingEventSource = null;

function toggleQueueConsole() {
    const card = document.getElementById('queue-publishing-card');
    if (!card) return;
    if (card.style.display === 'none' || card.style.display === '') {
        card.style.display = 'block';
        card.scrollIntoView({ behavior: 'smooth', block: 'start' });
    } else {
        card.style.display = 'none';
    }
}

function closeQueueConsole() {
    const card = document.getElementById('queue-publishing-card');
    if (card) card.style.display = 'none';
}

async function resetFailedQueueJobs() {
    try {
        const res = await fetch('/api/queue/reset-failed?reset_all=true', { method: 'POST' });
        const data = await res.json();
        showToast(data.message, 'success');
        resetQueuePublishButtons(false);
        loadQueue();
        loadOverview();
    } catch (err) {
        showToast(`Reset failed: ${err.message}`, 'error');
    }
}


function resetQueuePublishButtons(isCompleted = false, isStopped = false) {
    const btnLive = document.getElementById('btn-queue-publish-live');
    const btnDryRun = document.getElementById('btn-queue-publish-dryrun');
    const btnStop = document.getElementById('btn-queue-publish-stop');
    const btnConsoleStop = document.getElementById('btn-queue-console-stop');

    if (btnStop) {
        btnStop.style.display = 'none';
        btnStop.disabled = false;
        btnStop.innerHTML = '⏹️ Stop Uploading';
    }
    if (btnConsoleStop) {
        btnConsoleStop.style.display = 'none';
        btnConsoleStop.disabled = false;
        btnConsoleStop.innerHTML = '⏹️ Stop Engine';
    }
    if (btnDryRun) {
        btnDryRun.disabled = false;
    }
    if (btnLive) {
        btnLive.disabled = false;
        if (isCompleted) {
            btnLive.className = 'btn btn-success btn-sm';
            btnLive.style.background = '';
            btnLive.innerHTML = '✅ Upload Complete';
        } else {
            btnLive.className = 'btn btn-primary btn-sm';
            btnLive.style.background = 'linear-gradient(135deg, #10b981, #059669)';
            btnLive.innerHTML = '🚀 Start Uploading & Scheduling';
        }
    }
}

async function stopQueuePublishing() {
    const btnStop = document.getElementById('btn-queue-publish-stop');
    const btnConsoleStop = document.getElementById('btn-queue-console-stop');
    const badge = document.getElementById('queue-exec-badge');
    const output = document.getElementById('queue-console-output');

    if (btnStop) {
        btnStop.disabled = true;
        btnStop.innerHTML = '<span class="spinner" style="width:12px;height:12px;display:inline-block;margin-right:4px;"></span> Stopping...';
    }
    if (btnConsoleStop) {
        btnConsoleStop.disabled = true;
        btnConsoleStop.innerHTML = '⏹️ Stopping...';
    }
    if (badge) {
        badge.style.background = 'var(--danger)';
        badge.textContent = '⏹️ Stopping Engine...';
    }

    try {
        const res = await fetch('/api/queue/publish/stop', { method: 'POST' });
        const data = await res.json();
        if (output) {
            output.textContent += '\n🛑 [USER REQUEST] Stop command issued. Engine halting...\n';
        }
        showToast('🛑 Publishing stopped by user.', 'warning');
    } catch (err) {
        console.error('Failed to request publishing stop:', err);
        showToast(`Stop request failed: ${err.message}`, 'error');
    } finally {
        if (queuePublishingEventSource) {
            queuePublishingEventSource.close();
            queuePublishingEventSource = null;
        }
        state.isQueuePublishingRunning = false;
        resetQueuePublishButtons(false, true);
        if (badge) {
            badge.style.background = 'var(--text-muted)';
            badge.textContent = '⏹️ Stopped';
        }
        loadQueue();
        loadOverview();
    }
}

async function startQueuePublishing(dryRun = false) {
    const btnLive = document.getElementById('btn-queue-publish-live');
    const btnDryRun = document.getElementById('btn-queue-publish-dryrun');
    const btnStop = document.getElementById('btn-queue-publish-stop');
    const btnConsoleStop = document.getElementById('btn-queue-console-stop');
    const platform = document.getElementById('queue-exec-platform')?.value || '';
    const limit = document.getElementById('queue-exec-limit')?.value || '0';
    const isVisible = document.getElementById('queue-exec-visible')?.checked !== false;
    const headless = !isVisible;
    const card = document.getElementById('queue-publishing-card');
    const output = document.getElementById('queue-console-output');
    const badge = document.getElementById('queue-exec-badge');
    const body = document.getElementById('queue-console-body');

    if (state.isQueuePublishingRunning) {
        showToast('Queue publishing is already running.', 'info');
        return;
    }

    const actionTitle = dryRun ? 'Dry Run Upload' : 'Live Browser Upload & Scheduling';
    const targetDesc = platform ? platform.toUpperCase() : 'All Platforms (YouTube, Instagram, Facebook)';
    const limitDesc = limit === '0' ? 'all pending jobs' : `${limit} job(s)`;

    if (!dryRun) {
        const confirmed = confirm(
            `Start ${actionTitle} now?\n\n` +
            `• Target: ${targetDesc}\n` +
            `• Batch: ${limitDesc}\n` +
            `• Browser: ${isVisible ? 'Visible Chrome Window' : 'Background Headless'}\n` +
            `• Mechanism: Pure Playwright browser automation with persistent session profile.\n\n` +
            `Click OK to begin uploading and scheduling.`
        );
        if (!confirmed) return;
    }

    state.isQueuePublishingRunning = true;

    // Show console & stop buttons and scroll console into view
    if (card) {
        card.style.display = 'block';
        card.scrollIntoView({ behavior: 'smooth', block: 'start' });
    }
    if (output) output.textContent = '';
    if (badge) {
        badge.style.background = 'var(--accent-primary)';
        badge.textContent = '🚀 Initializing Engine...';
    }

    // Lock start buttons & show stop buttons
    if (btnLive) {
        btnLive.disabled = true;
        btnLive.innerHTML = `<span class="spinner" style="width:14px;height:14px;display:inline-block;margin-right:6px;"></span> ${dryRun ? 'Simulating...' : 'Uploading & Scheduling...'}`;
    }
    if (btnDryRun) btnDryRun.disabled = true;

    if (btnStop) {
        btnStop.style.display = 'inline-flex';
        btnStop.disabled = false;
        btnStop.innerHTML = '⏹️ Stop Uploading';
    }
    if (btnConsoleStop) {
        btnConsoleStop.style.display = 'inline-block';
        btnConsoleStop.disabled = false;
        btnConsoleStop.innerHTML = '⏹️ Stop Engine';
    }

    showToast(`Starting ${actionTitle}... Watch progress below.`, 'info');

    if (queuePublishingEventSource) {
        queuePublishingEventSource.close();
        queuePublishingEventSource = null;
    }

    try {
        let streamUrl = `/api/queue/publish/stream?dry_run=${dryRun}&limit=${limit}&headless=${headless}`;
        if (platform) streamUrl += `&platform=${encodeURIComponent(platform)}`;

        queuePublishingEventSource = new EventSource(streamUrl);

        queuePublishingEventSource.onmessage = function(event) {
            try {
                const data = JSON.parse(event.data);
                if (output) {
                    output.textContent += data.line + '\n';
                    if (body) body.scrollTop = body.scrollHeight;
                }

                if (badge && data.total > 0) {
                    badge.textContent = `Job ${data.current}/${data.total} (${data.status})`;
                }

                // Refresh queue table periodically on job progress
                if (data.line && (data.line.includes('SUCCESS') || data.line.includes('FAILED') || data.line.includes('Processing:'))) {
                    loadQueue();
                }

                if (data.done) {
                    if (queuePublishingEventSource) {
                        queuePublishingEventSource.close();
                        queuePublishingEventSource = null;
                    }
                    state.isQueuePublishingRunning = false;

                    const wasStopped = data.status === 'stopped';
                    if (badge) {
                        badge.style.background = wasStopped ? 'var(--danger)' : 'var(--success)';
                        badge.textContent = wasStopped ? '⏹️ Queue Stopped' : '✅ Queue Complete!';
                    }

                    resetQueuePublishButtons(!wasStopped, wasStopped);

                    if (wasStopped) {
                        showToast('⏹️ Queue publishing stopped.', 'warning');
                    } else {
                        showToast('🎉 Queue publishing batch completed successfully!', 'success');
                    }
                    loadQueue();
                    loadOverview();
                }
            } catch (err) {
                console.error('Error parsing queue stream data:', err);
            }
        };

        queuePublishingEventSource.onerror = function(err) {
            console.warn('Queue publishing stream closed:', err);
            if (queuePublishingEventSource) {
                queuePublishingEventSource.close();
                queuePublishingEventSource = null;
            }
            state.isQueuePublishingRunning = false;
            resetQueuePublishButtons(false, false);
            loadQueue();
        };

    } catch (e) {
        state.isQueuePublishingRunning = false;
        showToast(`Publishing start failed: ${e.message}`, 'error');
        resetQueuePublishButtons(false, false);
    }
}

// ── 8. Settings & Browser Login ───────────────────────────────────────
async function loadSettings() {
    const body = document.getElementById('settings-body');
    try {
        const res = await fetch('/api/settings');
        const s = await res.json();

        body.innerHTML = `
            <div class="settings-group">
                <h4>📁 Workspace & Storage Paths</h4>
                <div class="form-row"><label>Start Video Dir</label><input type="text" readonly value="${escapeHtml(s.start_video_dir)}"></div>
                <div class="form-row"><label>End Video Dir</label><input type="text" readonly value="${escapeHtml(s.end_video_dir)}"></div>
                <div class="form-row"><label>Excel Workbook</label><input type="text" readonly value="${escapeHtml(s.excel_path)}"></div>
                <div class="form-row"><label>Processed Output</label><input type="text" readonly value="${escapeHtml(s.processed_dir)}"></div>
                <div class="form-row"><label>Thumbnails</label><input type="text" readonly value="${escapeHtml(s.thumbnail_dir)}"></div>
                <div class="form-row"><label>Browser Profile</label><input type="text" readonly value="${escapeHtml(s.browser_profile_dir)}"></div>
            </div>

            <div class="settings-group">
                <h4>⏰ Scheduling Engine & Caps</h4>
                <div class="form-row"><label>Timezone</label><input type="text" readonly value="${escapeHtml(s.timezone)}"></div>
                <div class="form-row"><label>Daily Upload Cap</label><input type="text" readonly value="${s.daily_upload_cap} videos/day"></div>
                <div class="form-row"><label>Daily Target</label><input type="text" readonly value="${s.daily_publication_count} videos/day"></div>
                <div class="form-row"><label>Time Slots</label><input type="text" readonly value="${(s.publishing_slots || []).join(', ')}"></div>
            </div>
        `;
    } catch (e) {
        body.innerHTML = `<p style="color:var(--error);">Failed to load settings: ${escapeHtml(e.message)}</p>`;
    }
}

async function openBrowserLogin() {
    showToast('Opening Chrome with your persistent profile...', 'info');
    try {
        const res = await fetch('/api/browser/open-login', { method: 'POST' });
        const data = await res.json();
        showToast(data.message || 'Browser opened! Sign into your accounts.', 'success', 8000);
    } catch (e) {
        showToast(`Failed to launch browser: ${e.message}`, 'error');
    }
}

async function closeBrowser() {
    showToast('Closing browser...', 'info');
    try {
        const res = await fetch('/api/browser/close', { method: 'POST' });
        const data = await res.json();
        showToast(data.message || 'Browser closed.', 'info');
    } catch (e) {
        showToast(`Failed to close browser: ${e.message}`, 'error');
    }
}

async function checkAuth() {
    const statusDiv = document.getElementById('auth-status');
    statusDiv.innerHTML = `<span class="spinner"></span> Checking account sessions...`;

    try {
        const res = await fetch('/api/browser/check-auth', { method: 'POST' });
        const data = await res.json();

        statusDiv.innerHTML = `
            <div class="flex gap-4 items-center">
                <div class="flex items-center gap-2">
                    <span class="platform-badge youtube">YouTube</span>
                    <span class="status-pill ${data.youtube ? 'uploaded' : 'failed'}">${data.youtube ? 'Authenticated' : 'Logged Out'}</span>
                </div>
                <div class="flex items-center gap-2">
                    <span class="platform-badge instagram">Instagram</span>
                    <span class="status-pill ${data.instagram ? 'uploaded' : 'failed'}">${data.instagram ? 'Authenticated' : 'Logged Out'}</span>
                </div>
                <div class="flex items-center gap-2">
                    <span class="platform-badge facebook">Facebook</span>
                    <span class="status-pill ${data.facebook ? 'uploaded' : 'failed'}">${data.facebook ? 'Authenticated' : 'Logged Out'}</span>
                </div>
            </div>
            ${data.error ? `<div class="text-xs mt-2" style="color:var(--error)">Notice: ${escapeHtml(data.error)}</div>` : ''}
        `;
    } catch (e) {
        statusDiv.innerHTML = `<span style="color:var(--error)">Error checking auth: ${escapeHtml(e.message)}</span>`;
    }
}

// ── Heartbeat ─────────────────────────────────────────────────────────
async function checkHeartbeat() {
    const dot = document.getElementById('heartbeat-dot');
    try {
        const res = await fetch('/api/scheduler/heartbeat');
        const data = await res.json();
        if (data.running) {
            dot.style.background = 'var(--success)';
            dot.title = 'Scheduler active and running';
        } else {
            dot.style.background = 'var(--warning)';
            dot.title = 'Scheduler stopped or idle';
        }
    } catch (e) {
        if (dot) dot.style.background = 'var(--error)';
    }
}

// ── Initialization ────────────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', () => {
    // Initial page load
    navigateTo('overview');

    // Start heartbeat polling
    checkHeartbeat();
    state.heartbeatInterval = setInterval(checkHeartbeat, 15000);
});
