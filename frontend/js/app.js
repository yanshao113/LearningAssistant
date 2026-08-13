/**
 * Learning Assistant - SPA Client Application Logic
 */

document.addEventListener('DOMContentLoaded', () => {
    // --- Application State ---
    const state = {
        activeTab: 'chat',
        apiKey: localStorage.getItem('gemini_api_key') || '',
        hasApiKey: false,
        chatHistory: [],
        documents: [],
        stats: { total_files: 0, total_chunks: 0 }
    };

    // --- DOM Elements ---
    const elements = {
        // Nav & Tabs
        navItems: document.querySelectorAll('.nav-item'),
        tabPanes: document.querySelectorAll('.tab-pane'),
        pageTitle: document.getElementById('page-title'),
        pageDesc: document.getElementById('page-desc'),

        // Header & Status
        btnApiKey: document.getElementById('btn-api-key'),
        apiKeyBtnText: document.getElementById('api-key-btn-text'),
        statusDot: document.getElementById('status-dot'),
        statusText: document.getElementById('status-text'),
        miniStatFiles: document.getElementById('mini-stat-files'),
        miniStatChunks: document.getElementById('mini-stat-chunks'),
        btnReindexTop: document.getElementById('btn-reindex-top'),

        // Chat
        chatForm: document.getElementById('chat-form'),
        chatInput: document.getElementById('chat-input'),
        chatMessages: document.getElementById('chat-messages'),
        btnSend: document.getElementById('btn-send'),
        suggestionsRow: document.getElementById('suggestions-row'),

        // Upload & Documents
        dropZone: document.getElementById('drop-zone'),
        fileInput: document.getElementById('file-input'),
        folderInput: document.getElementById('folder-input'),
        courseSelect: document.getElementById('course-select'),
        btnBrowseFiles: document.getElementById('btn-browse-files'),
        btnBrowseFolder: document.getElementById('btn-browse-folder'),
        uploadProgressContainer: document.getElementById('upload-progress-container'),
        uploadProgressBar: document.getElementById('upload-progress-bar'),
        uploadProgressText: document.getElementById('upload-progress-text'),
        docsList: document.getElementById('docs-list'),
        btnRefreshDocs: document.getElementById('btn-refresh-docs'),

        // Settings & API Key
        settingsApiForm: document.getElementById('settings-api-form'),
        inputGeminiKey: document.getElementById('input-gemini-key'),
        btnToggleKey: document.getElementById('btn-toggle-key'),
        settingsKeyBadge: document.getElementById('settings-key-badge'),
        btnClearSettingsKey: document.getElementById('btn-clear-settings-key'),
        btnForceReindex: document.getElementById('btn-force-reindex'),
        reindexProgressContainer: document.getElementById('reindex-progress-container'),
        reindexProgressBar: document.getElementById('reindex-progress-bar'),
        reindexStatusText: document.getElementById('reindex-status-text'),
        reindexPercentText: document.getElementById('reindex-percent-text'),

        // Modals
        modalApiKey: document.getElementById('modal-api-key'),
        modalApiClose: document.getElementById('modal-api-close'),
        modalApiCancel: document.getElementById('modal-api-cancel'),
        modalApiSave: document.getElementById('modal-api-save'),
        modalApiClear: document.getElementById('modal-api-clear'),
        modalInputKey: document.getElementById('modal-input-key'),
        modalKeyStatusBox: document.getElementById('modal-key-status-box'),
        modalKeyStatusText: document.getElementById('modal-key-status-text'),

        modalDocPreview: document.getElementById('modal-doc-preview'),
        modalPreviewClose: document.getElementById('modal-preview-close'),
        previewModalTitle: document.getElementById('preview-modal-title'),
        previewModalContent: document.getElementById('preview-modal-content')
    };

    // Initialize Markdown Parser
    if (window.marked) {
        marked.setOptions({
            highlight: function(code, lang) {
                if (window.hljs) {
                    const language = hljs.getLanguage(lang) ? lang : 'plaintext';
                    return hljs.highlight(code, { language }).value;
                }
                return code;
            },
            breaks: true
        });
    }

    // --- Core Functions ---

    async function init() {
        setupEventListeners();
        if (state.apiKey) {
            await syncApiKey(state.apiKey);
        }
        await fetchStats();
        await fetchDocuments();
    }

    // Fetch system & database stats
    async function fetchStats() {
        try {
            const res = await fetch('/api/stats');
            if (res.ok) {
                const data = await res.json();
                state.stats = data;
                state.hasApiKey = data.has_api_key;
                updateStatusUI();
            }
        } catch (err) {
            console.error('Failed to fetch stats:', err);
        }
    }

    // Update status indicators & features across UI (Loaded vs Not Loaded)
    function updateStatusUI() {
        elements.miniStatFiles.textContent = state.stats.total_files || 0;
        elements.miniStatChunks.textContent = state.stats.total_chunks || 0;

        if (state.hasApiKey) {
            // Active / Configured State
            elements.statusDot.className = 'status-dot green';
            elements.statusText.textContent = 'Vector DB Ready';
            elements.apiKeyBtnText.textContent = 'API Key Active ✓';
            elements.btnApiKey.className = 'btn btn-secondary';

            // Settings tab badge
            if (elements.settingsKeyBadge) {
                elements.settingsKeyBadge.className = 'badge-status active';
                elements.settingsKeyBadge.innerHTML = '<i class="fa-solid fa-circle-check"></i> API Key Configured';
            }
            if (elements.btnClearSettingsKey) {
                elements.btnClearSettingsKey.style.display = 'inline-flex';
            }

            // Modal Status Box
            if (elements.modalKeyStatusBox) {
                elements.modalKeyStatusBox.className = 'key-status-box active mb-3';
                elements.modalKeyStatusText.innerHTML = '<i class="fa-solid fa-circle-check"></i> API Key is active & stored in session';
            }
            if (elements.modalApiClear) {
                elements.modalApiClear.style.display = 'inline-flex';
            }

        } else {
            // Missing Key State
            elements.statusDot.className = 'status-dot';
            elements.statusText.textContent = 'Missing API Key';
            elements.apiKeyBtnText.textContent = 'Configure API Key';
            elements.btnApiKey.className = 'btn btn-outline';

            // Settings tab badge
            if (elements.settingsKeyBadge) {
                elements.settingsKeyBadge.className = 'badge-status missing';
                elements.settingsKeyBadge.innerHTML = '<i class="fa-solid fa-triangle-exclamation"></i> Key Missing';
            }
            if (elements.btnClearSettingsKey) {
                elements.btnClearSettingsKey.style.display = 'none';
            }

            // Modal Status Box
            if (elements.modalKeyStatusBox) {
                elements.modalKeyStatusBox.className = 'key-status-box missing mb-3';
                elements.modalKeyStatusText.innerHTML = '<i class="fa-solid fa-triangle-exclamation"></i> No Gemini API key configured';
            }
            if (elements.modalApiClear) {
                elements.modalApiClear.style.display = 'none';
            }
        }
    }

    // Sync API key with backend server
    async function syncApiKey(key) {
        try {
            const res = await fetch('/api/config/api-key', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ api_key: key })
            });

            if (res.ok) {
                state.apiKey = key;
                localStorage.setItem('gemini_api_key', key);
                state.hasApiKey = true;
                updateStatusUI();
                return true;
            }
        } catch (err) {
            console.error('API key sync error:', err);
        }
        return false;
    }

    // Clear API key
    async function clearApiKey() {
        try {
            await fetch('/api/config/api-key', { method: 'DELETE' });
            state.apiKey = '';
            localStorage.removeItem('gemini_api_key');
            state.hasApiKey = false;
            elements.inputGeminiKey.value = '';
            elements.modalInputKey.value = '';
            updateStatusUI();
            alert('API key cleared successfully.');
        } catch (err) {
            console.error('Error clearing API key:', err);
        }
    }

    // Fetch workspace documents
    async function fetchDocuments() {
        try {
            const res = await fetch('/api/documents');
            if (res.ok) {
                const data = await res.json();
                state.documents = data.documents;
                renderDocumentsTable(data.documents);
            }
        } catch (err) {
            console.error('Failed to fetch documents:', err);
        }
    }

    // Render documents table (default empty guidance)
    function renderDocumentsTable(docs) {
        if (!docs || docs.length === 0) {
            elements.docsList.innerHTML = `
                <tr>
                    <td colspan="5" style="text-align: center; color: var(--text-muted); padding: 36px 20px;">
                        <i class="fa-solid fa-folder-open" style="font-size: 2rem; color: var(--text-dim); margin-bottom: 10px; display: block;"></i>
                        <strong>Your Knowledge Base is currently empty</strong>
                        <p style="font-size: 0.85rem; margin-top: 4px;">Drag & drop course notes, code files, or entire folders above to start asking questions!</p>
                    </td>
                </tr>`;
            return;
        }

        elements.docsList.innerHTML = docs.map(doc => `
            <tr>
                <td>
                    <i class="fa-regular fa-file-code text-accent" style="margin-right: 8px;"></i>
                    <strong>${escapeHtml(doc.filename)}</strong>
                </td>
                <td><span class="badge-type">${escapeHtml(doc.course)}</span></td>
                <td>${escapeHtml(doc.file_type)}</td>
                <td>${doc.size_formatted}</td>
                <td>
                    <button class="btn btn-secondary btn-sm btn-preview-doc" data-path="${escapeHtml(doc.full_path)}">
                        <i class="fa-solid fa-eye"></i> Preview
                    </button>
                    <button class="btn btn-secondary btn-sm text-danger btn-delete-doc" data-path="${escapeHtml(doc.full_path)}">
                        <i class="fa-solid fa-trash"></i>
                    </button>
                </td>
            </tr>
        `).join('');

        // Attach event handlers for dynamic buttons
        document.querySelectorAll('.btn-preview-doc').forEach(btn => {
            btn.addEventListener('click', () => openDocPreview(btn.dataset.path));
        });

        document.querySelectorAll('.btn-delete-doc').forEach(btn => {
            btn.addEventListener('click', () => deleteDoc(btn.dataset.path));
        });
    }

    // Preview document content modal
    async function openDocPreview(filepath) {
        elements.previewModalTitle.innerHTML = `<i class="fa-solid fa-file-lines text-accent"></i> ${filepath.split('/').pop()}`;
        elements.previewModalContent.textContent = 'Loading content...';
        elements.modalDocPreview.classList.add('active');

        try {
            const res = await fetch(`/api/documents/preview?filepath=${encodeURIComponent(filepath)}`);
            if (res.ok) {
                const data = await res.json();
                elements.previewModalContent.textContent = data.content;
                if (window.hljs) {
                    hljs.highlightElement(elements.previewModalContent);
                }
            } else {
                elements.previewModalContent.textContent = 'Failed to load preview for this file.';
            }
        } catch (err) {
            elements.previewModalContent.textContent = 'Error reading document preview.';
        }
    }

    // Delete document
    async function deleteDoc(filepath) {
        if (!confirm(`Are you sure you want to delete ${filepath.split('/').pop()}?`)) return;

        try {
            const res = await fetch('/api/documents/delete', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ filepath })
            });

            if (res.ok) {
                await fetchDocuments();
                await fetchStats();
            }
        } catch (err) {
            alert('Failed to delete file.');
        }
    }

    // --- Thinking Steps & Interactive Chat ---

    async function sendChatMessage(promptText) {
        const text = promptText || elements.chatInput.value.trim();
        if (!text) return;

        if (!state.hasApiKey && !state.apiKey) {
            openApiKeyModal();
            return;
        }

        // Add user message to UI
        appendMessage('user', text);
        elements.chatInput.value = '';

        // Create Thinking Box container in Chat
        const thinkingId = appendThinkingStepsBox();

        try {
            const res = await fetch('/api/chat', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    message: text,
                    history: state.chatHistory,
                    api_key: state.apiKey
                })
            });

            removeMessage(thinkingId);

            if (!res.ok) {
                const errData = await res.json();
                appendMessage('assistant', `⚠️ **Error:** ${errData.detail || 'Failed to process request.'}`);
                return;
            }

            const data = await res.json();
            
            // Save context into history only if response is non-empty
            if (data.response && data.response.trim()) {
                state.chatHistory.push({ role: 'user', content: text });
                state.chatHistory.push({ role: 'assistant', content: data.response });
            }

            // Append assistant response with citations and thinking step recap
            appendMessage('assistant', data.response || 'No response generated.', data.citations, data.tool_calls);

        } catch (err) {
            removeMessage(thinkingId);
            appendMessage('assistant', `⚠️ **Network Error:** Could not reach AI server.`);
        }
    }

    // Thinking Steps Box with Step-by-Step animation
    function appendThinkingStepsBox() {
        const id = 'thinking-' + Date.now();
        const thinkingEl = document.createElement('div');
        thinkingEl.className = 'message assistant-message';
        thinkingEl.id = id;
        thinkingEl.innerHTML = `
            <div class="msg-avatar"><i class="fa-solid fa-robot"></i></div>
            <div class="msg-body" style="width: 100%;">
                <div class="msg-author">Learning Assistant AI</div>
                <div class="msg-content" style="width: 100%;">
                    <div class="thinking-box">
                        <div class="thinking-header">
                            <i class="fa-solid fa-brain fa-spin"></i> Reasoning & Retrieval Steps...
                        </div>
                        <div class="thinking-steps-list">
                            <div class="thinking-step active" id="${id}-step1">
                                <i class="fa-solid fa-spinner fa-spin"></i> <span>Step 1: Analyzing user query & course context...</span>
                            </div>
                            <div class="thinking-step" id="${id}-step2">
                                <i class="fa-regular fa-circle"></i> <span>Step 2: Searching ChromaDB vector database for course notes...</span>
                            </div>
                            <div class="thinking-step" id="${id}-step3">
                                <i class="fa-regular fa-circle"></i> <span>Step 3: Extracting relevant document passages & citations...</span>
                            </div>
                            <div class="thinking-step" id="${id}-step4">
                                <i class="fa-regular fa-circle"></i> <span>Step 4: Synthesizing AI study response...</span>
                            </div>
                        </div>
                    </div>
                </div>
            </div>
        `;
        elements.chatMessages.appendChild(thinkingEl);
        elements.chatMessages.scrollTop = elements.chatMessages.scrollHeight;

        // Step-by-step animation sequence
        setTimeout(() => updateStepState(id, 'step1', 'step2'), 600);
        setTimeout(() => updateStepState(id, 'step2', 'step3'), 1200);
        setTimeout(() => updateStepState(id, 'step3', 'step4'), 1800);

        return id;
    }

    function updateStepState(boxId, doneStep, activeStep) {
        const doneEl = document.getElementById(`${boxId}-${doneStep}`);
        const activeEl = document.getElementById(`${boxId}-${activeStep}`);
        if (doneEl) {
            doneEl.className = 'thinking-step done';
            doneEl.innerHTML = `<i class="fa-solid fa-circle-check text-accent"></i> <span>${doneEl.querySelector('span').textContent}</span>`;
        }
        if (activeEl) {
            activeEl.className = 'thinking-step active';
            activeEl.innerHTML = `<i class="fa-solid fa-spinner fa-spin"></i> <span>${activeEl.querySelector('span').textContent}</span>`;
        }
    }

    // Append message element to chat window
    function appendMessage(role, text, citations = [], toolCalls = []) {
        const msgId = 'msg-' + Date.now();
        const isUser = role === 'user';
        const avatarIcon = isUser ? 'fa-user' : 'fa-robot';
        const authorName = isUser ? 'You' : 'Learning Assistant AI';

        let formattedHtml = escapeHtml(text);
        if (window.marked && !isUser) {
            formattedHtml = marked.parse(text);
        }

        // Render Citations
        let citationsHtml = '';
        if (citations && citations.length > 0) {
            citationsHtml = `
                <div class="citations-list">
                    <span style="font-size: 0.78rem; font-weight: 600; color: var(--text-muted); display: block; width: 100%; margin-bottom: 6px;">
                        <i class="fa-solid fa-folder-tree text-accent"></i> Referenced Original Source Files:
                    </span>
                    ${citations.map(c => `
                        <span class="citation-pill btn-preview-doc" data-path="${escapeHtml(c.file_path)}" title="Click to view ${escapeHtml(c.original_path || c.file_path)}">
                            <i class="fa-solid fa-file-contract text-accent"></i> ${escapeHtml(c.original_path || c.filename)}
                        </span>
                    `).join('')}
                </div>
            `;
        }

        // Render Tool Calls & Thinking Summary
        let toolHtml = '';
        if (toolCalls && toolCalls.length > 0) {
            toolHtml = toolCalls.map(tc => `
                <div class="tool-call-box">
                    <i class="fa-solid fa-circle-check text-accent"></i> <strong>Retriever Executed:</strong> Searched vector database for <em>"${escapeHtml(tc.query)}"</em>
                </div>
            `).join('');
        }

        const msgElement = document.createElement('div');
        msgElement.className = `message ${isUser ? 'user-message' : 'assistant-message'}`;
        msgElement.id = msgId;
        msgElement.innerHTML = `
            <div class="msg-avatar">
                <i class="fa-solid ${avatarIcon}"></i>
            </div>
            <div class="msg-body">
                <div class="msg-author">${authorName}</div>
                <div class="msg-content">
                    ${toolHtml}
                    ${formattedHtml}
                    ${citationsHtml}
                </div>
            </div>
        `;

        elements.chatMessages.appendChild(msgElement);
        elements.chatMessages.scrollTop = elements.chatMessages.scrollHeight;

        // Attach event listeners for citation pills
        msgElement.querySelectorAll('.citation-pill').forEach(pill => {
            pill.addEventListener('click', () => openDocPreview(pill.dataset.path));
        });

        return msgId;
    }

    function removeMessage(id) {
        const el = document.getElementById(id);
        if (el) el.remove();
    }

    // --- File & Folder Upload Handlers ---

    // Handle File & Large Folder Uploads in Batches
    async function handleFilesUpload(filesList, relativePaths = []) {
        if (!filesList || filesList.length === 0) return;

        const totalFiles = filesList.length;
        const BATCH_SIZE = 250; // Upload in safe batches to avoid FastAPI 1000 file form limits
        const defaultCourse = elements.courseSelect.value.trim() || 'General';

        elements.uploadProgressContainer.style.display = 'block';
        elements.uploadProgressBar.style.width = '2%';
        elements.uploadProgressText.textContent = `Preparing to upload ${totalFiles} file(s)...`;

        let uploadedCount = 0;

        for (let i = 0; i < totalFiles; i += BATCH_SIZE) {
            const batchFiles = Array.from(filesList).slice(i, i + BATCH_SIZE);
            const batchPaths = relativePaths.slice(i, i + BATCH_SIZE);

            const formData = new FormData();
            for (let j = 0; j < batchFiles.length; j++) {
                formData.append('files', batchFiles[j]);
                const relPath = batchPaths[j] || batchFiles[j].webkitRelativePath || batchFiles[j].name;
                formData.append('relative_paths', relPath);
            }
            formData.append('course', defaultCourse);

            const currentTotal = Math.min(i + batchFiles.length, totalFiles);
            const pct = Math.round((currentTotal / totalFiles) * 100);
            const batchNum = Math.floor(i / BATCH_SIZE) + 1;
            const totalBatches = Math.ceil(totalFiles / BATCH_SIZE);

            elements.uploadProgressText.textContent = `Uploading batch ${batchNum}/${totalBatches} (${currentTotal}/${totalFiles} files, ${pct}%)...`;
            elements.uploadProgressBar.style.width = `${pct}%`;

            try {
                const res = await fetch('/api/documents/upload', {
                    method: 'POST',
                    body: formData
                });

                if (!res.ok) {
                    const errData = await res.json();
                    elements.uploadProgressText.textContent = `Upload batch error: ${errData.detail}`;
                    return;
                }
                uploadedCount += batchFiles.length;
            } catch (err) {
                elements.uploadProgressText.textContent = `Network error during batch upload.`;
                return;
            }
        }

        elements.uploadProgressBar.style.width = '100%';
        elements.uploadProgressText.textContent = `Successfully uploaded & indexed ${uploadedCount} file(s) across folders!`;
        
        setTimeout(() => {
            elements.uploadProgressContainer.style.display = 'none';
            elements.uploadProgressBar.style.width = '0%';
        }, 3000);

        await fetchDocuments();
        await fetchStats();
    }

    // Traverse directory tree for Drag & Drop folders
    async function handleDropItems(items) {
        const files = [];
        const relativePaths = [];

        async function traverseEntry(entry, path = '') {
            if (entry.isFile) {
                await new Promise((resolve) => {
                    entry.file((file) => {
                        files.push(file);
                        relativePaths.push(path + file.name);
                        resolve();
                    });
                });
            } else if (entry.isDirectory) {
                const dirReader = entry.createReader();
                const entries = await new Promise((resolve) => {
                    dirReader.readEntries((results) => resolve(results));
                });
                for (const childEntry of entries) {
                    await traverseEntry(childEntry, path + entry.name + '/');
                }
            }
        }

        for (let i = 0; i < items.length; i++) {
            const item = items[i];
            if (item.webkitGetAsEntry) {
                const entry = item.webkitGetAsEntry();
                if (entry) {
                    await traverseEntry(entry);
                }
            } else if (item.getAsFile) {
                const file = item.getAsFile();
                if (file) {
                    files.push(file);
                    relativePaths.push(file.name);
                }
            }
        }

        if (files.length > 0) {
            await handleFilesUpload(files, relativePaths);
        }
    }

    // Re-indexing Progress Polling with Percentage %
    async function triggerReindex() {
        if (!confirm('Rebuild the vector database from all workspace files?')) return;

        elements.reindexProgressContainer.style.display = 'block';
        elements.reindexProgressBar.style.width = '5%';
        elements.reindexPercentText.textContent = '5%';
        elements.reindexStatusText.textContent = 'Starting indexing process...';

        // Start progress polling loop
        const pollInterval = setInterval(async () => {
            try {
                const progressRes = await fetch('/api/documents/reindex/progress');
                if (progressRes.ok) {
                    const p = await progressRes.json();
                    const percent = Math.min(100, Math.max(0, p.percent || 0));
                    elements.reindexProgressBar.style.width = percent + '%';
                    elements.reindexPercentText.textContent = percent + '%';
                    if (p.message) elements.reindexStatusText.textContent = p.message;

                    if (p.status === 'completed' && percent >= 100) {
                        clearInterval(pollInterval);
                    }
                }
            } catch (e) {
                // Ignore polling glitches
            }
        }, 400);

        try {
            const res = await fetch('/api/documents/reindex', { method: 'POST' });
            clearInterval(pollInterval);
            elements.reindexProgressBar.style.width = '100%';
            elements.reindexPercentText.textContent = '100%';

            if (res.ok) {
                const data = await res.json();
                elements.reindexStatusText.textContent = data.message;
                await fetchStats();
            } else {
                const err = await res.json();
                elements.reindexStatusText.textContent = `Re-indexing error: ${err.detail}`;
            }
        } catch (err) {
            clearInterval(pollInterval);
            elements.reindexStatusText.textContent = 'Re-indexing request failed.';
        }
    }

    function openApiKeyModal() {
        elements.modalInputKey.value = state.apiKey;
        elements.modalApiKey.classList.add('active');
    }

    function closeApiKeyModal() {
        elements.modalApiKey.classList.remove('active');
    }

    // Event Listeners Setup
    function setupEventListeners() {
        // Navigation Tabs
        elements.navItems.forEach(item => {
            item.addEventListener('click', () => {
                const targetTab = item.dataset.tab;
                elements.navItems.forEach(n => n.classList.remove('active'));
                elements.tabPanes.forEach(p => p.classList.remove('active'));

                item.classList.add('active');
                document.getElementById(`pane-${targetTab}`).classList.add('active');

                if (targetTab === 'chat') {
                    elements.pageTitle.textContent = 'AI Study Assistant';
                    elements.pageDesc.textContent = 'Ask questions about your uploaded lecture notes, code, and documents.';
                } else if (targetTab === 'knowledge') {
                    elements.pageTitle.textContent = 'Knowledge Base & Files';
                    elements.pageDesc.textContent = 'Upload and manage course documents indexed in ChromaDB.';
                } else if (targetTab === 'settings') {
                    elements.pageTitle.textContent = 'Settings & API';
                    elements.pageDesc.textContent = 'Configure Google Gemini API Key and system preferences.';
                }
            });
        });

        // Header Actions
        elements.btnApiKey.addEventListener('click', openApiKeyModal);
        elements.modalApiClose.addEventListener('click', closeApiKeyModal);
        elements.modalApiCancel.addEventListener('click', closeApiKeyModal);
        
        elements.modalApiSave.addEventListener('click', async () => {
            const key = elements.modalInputKey.value.trim();
            if (key) {
                await syncApiKey(key);
                closeApiKeyModal();
            }
        });

        if (elements.modalApiClear) {
            elements.modalApiClear.addEventListener('click', async () => {
                await clearApiKey();
                closeApiKeyModal();
            });
        }

        if (elements.btnClearSettingsKey) {
            elements.btnClearSettingsKey.addEventListener('click', clearApiKey);
        }

        elements.btnReindexTop.addEventListener('click', triggerReindex);
        elements.btnForceReindex.addEventListener('click', triggerReindex);

        // Chat Form
        elements.chatForm.addEventListener('submit', (e) => {
            e.preventDefault();
            sendChatMessage();
        });

        // Chat Textarea Enter key submit
        elements.chatInput.addEventListener('keydown', (e) => {
            if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault();
                sendChatMessage();
            }
        });

        // Suggestion Chips
        elements.suggestionsRow.querySelectorAll('.suggestion-chip').forEach(chip => {
            chip.addEventListener('click', () => {
                sendChatMessage(chip.dataset.prompt);
            });
        });

        // File & Folder Browsing Buttons
        if (elements.btnBrowseFiles) {
            elements.btnBrowseFiles.addEventListener('click', (e) => {
                e.stopPropagation();
                elements.fileInput.click();
            });
        }

        if (elements.btnBrowseFolder) {
            elements.btnBrowseFolder.addEventListener('click', (e) => {
                e.stopPropagation();
                elements.folderInput.click();
            });
        }

        elements.dropZone.addEventListener('click', () => elements.folderInput.click());

        // File Input Change
        elements.fileInput.addEventListener('change', (e) => {
            const files = e.target.files;
            const relPaths = Array.from(files).map(f => f.name);
            handleFilesUpload(files, relPaths);
        });

        // Native Folder Input Change
        if (elements.folderInput) {
            elements.folderInput.addEventListener('change', (e) => {
                const files = e.target.files;
                const relPaths = Array.from(files).map(f => f.webkitRelativePath || f.name);
                handleFilesUpload(files, relPaths);
            });
        }

        // Drag & Drop Folder and File Traversal
        elements.dropZone.addEventListener('dragover', (e) => {
            e.preventDefault();
            elements.dropZone.classList.add('dragover');
        });

        elements.dropZone.addEventListener('dragleave', () => {
            elements.dropZone.classList.remove('dragover');
        });

        elements.dropZone.addEventListener('drop', async (e) => {
            e.preventDefault();
            elements.dropZone.classList.remove('dragover');
            if (e.dataTransfer.items) {
                await handleDropItems(e.dataTransfer.items);
            } else if (e.dataTransfer.files) {
                handleFilesUpload(e.dataTransfer.files);
            }
        });

        elements.btnRefreshDocs.addEventListener('click', fetchDocuments);

        // Settings API Form
        elements.settingsApiForm.addEventListener('submit', async (e) => {
            e.preventDefault();
            const key = elements.inputGeminiKey.value.trim();
            if (key) {
                const ok = await syncApiKey(key);
                if (ok) alert('API key saved successfully!');
            }
        });

        elements.btnToggleKey.addEventListener('click', () => {
            const input = elements.inputGeminiKey;
            const icon = elements.btnToggleKey.querySelector('i');
            if (input.type === 'password') {
                input.type = 'text';
                icon.className = 'fa-solid fa-eye-slash';
            } else {
                input.type = 'password';
                icon.className = 'fa-solid fa-eye';
            }
        });

        // Document Preview Modal Close
        elements.modalPreviewClose.addEventListener('click', () => {
            elements.modalDocPreview.classList.remove('active');
        });

        // Backdrop click to close modals
        window.addEventListener('click', (e) => {
            if (e.target === elements.modalApiKey) closeApiKeyModal();
            if (e.target === elements.modalDocPreview) elements.modalDocPreview.classList.remove('active');
        });
    }

    function escapeHtml(str) {
        if (!str) return '';
        return String(str)
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;')
            .replace(/'/g, '&#039;');
    }

    // Boot App
    init();
});
