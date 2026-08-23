document.addEventListener('DOMContentLoaded', () => {
    // ========== CONFIG ==========
    const API_BASE = window.location.origin;
    
    // Firebase Configuration
    const firebaseConfig = {
        apiKey: "AIzaSyA-ozJSi8oGUBiaDaHvKnrD8xdQjspyWaI",
        authDomain: "perplexity-8cd7e.firebaseapp.com",
        projectId: "perplexity-8cd7e",
        storageBucket: "perplexity-8cd7e.firebasestorage.app",
        messagingSenderId: "382933324502",
        appId: "1:382933324502:web:6ab36a80255489b4e92f77",
        measurementId: "G-GCEKS40QNE"
    };

    // Initialize Firebase
    firebase.initializeApp(firebaseConfig);
    const auth = firebase.auth();
    const googleProvider = new firebase.auth.GoogleAuthProvider();

    let SESSION_ID = 'guest_' + Date.now();
    let currentUser = null;

    // ========== DOM REFS ==========
    const homeView = document.getElementById('home-view');
    const chatView = document.getElementById('chat-view');
    const discoverView = document.getElementById('discover-view');
    const spacesView = document.getElementById('spaces-view');
    const computerView = document.getElementById('computer-view');
    const homeInput = document.getElementById('home-search-input');
    const chatInput = document.getElementById('chat-search-input');
    const homeSubmitBtn = document.getElementById('home-submit-btn');
    const chatSubmitBtn = document.getElementById('chat-submit-btn');
    const chatMessages = document.getElementById('chat-messages');
    const chatTitle = document.getElementById('chat-title');
    const backBtn = document.getElementById('back-to-home');
    const newThreadBtn = document.getElementById('chat-new-thread');
    const navNewThread = document.getElementById('nav-new-thread');
    const tabButtons = document.querySelectorAll('.tab-btn');
    const suggestionContainer = document.getElementById('suggestion-content');
    const historyList = document.getElementById('history-list');
    const navItems = document.querySelectorAll('.nav-item:not(#nav-new-thread)');
    const signInArea = document.getElementById('sign-in-btn');
    const userProfileArea = document.getElementById('user-profile-btn');
    const userAvatar = document.getElementById('user-avatar');
    const userName = document.getElementById('user-name');
    const logoutBtn = document.getElementById('logout-btn');

    // ========== TAB DATA ==========
    const tabData = {
        taxes: [
            "Prepare my 2025 taxes for my review",
            "I got married this year — should we file jointly or separately?",
            "How should I report my stock compensation when filing my taxes?",
            "Do I qualify for the new no-tax-on-tips deduction?",
            "Maximize my 2025 tax deductions as a small business owner"
        ],
        business: [
            "How to start a SaaS business in 2025?",
            "What are the best industries for a startup right now?",
            "Write a business plan for an AI-powered travel agency",
            "Tips for scaling a small team efficiently"
        ],
        learn: [
            "Explain Quantum Entanglement like I'm five",
            "What is the best way to learn Python for data science?",
            "How does photosynthesis work in deep sea plants?",
            "The history of modern architecture in 5 minutes"
        ],
        monitor: [
            "Monitor the latest tech news from today",
            "Track the status of the upcoming rocket launch",
            "What is the current stock price of major tech firms?",
            "Recent updates in global environmental policies"
        ]
    };

    let isStreaming = false;

    // ========== AUTH LOGIC ==========
    function updateAuthUI(user) {
        if (user) {
            currentUser = user;
            SESSION_ID = user.uid; // Use UID as session ID for persistent cloud history
            signInArea.classList.add('hidden');
            userProfileArea.classList.remove('hidden');
            userAvatar.src = user.photoURL || '';
            userName.textContent = user.displayName || 'User';
            console.log("[Auth] Logged in as:", user.displayName);
        } else {
            currentUser = null;
            SESSION_ID = 'guest_' + Date.now();
            signInArea.classList.remove('hidden');
            userProfileArea.classList.add('hidden');
            console.log("[Auth] Switched to guest mode.");
        }
        lucide.createIcons();
    }

    auth.onAuthStateChanged(updateAuthUI);

    let loginInProgress = false;
    async function handleLogin() {
        if (loginInProgress) return;
        loginInProgress = true;
        signInArea.style.opacity = '0.5';
        signInArea.style.pointerEvents = 'none';

        try {
            await auth.signInWithPopup(googleProvider);
        } catch (error) {
            // Suppress "cancelled" error which happens if user clicks again or closes popup manually
            if (error.code !== 'auth/cancelled-popup-request' && error.code !== 'auth/popup-closed-by-user') {
                console.error("[Auth] Login failed:", error);
                alert("Login failed: " + error.message);
            }
        } finally {
            loginInProgress = false;
            signInArea.style.opacity = '1';
            signInArea.style.pointerEvents = 'auto';
        }
    }

    async function handleLogout() {
        try {
            await auth.signOut();
            window.location.reload(); // Refresh to clear local state safely
        } catch (error) {
            console.error("[Auth] Logout failed:", error);
        }
    }

    if (signInArea) signInArea.addEventListener('click', handleLogin);
    if (userProfileArea) {
        userProfileArea.addEventListener('click', (e) => {
            if (e.target.closest('#logout-btn')) {
                e.stopPropagation();
                handleLogout();
            }
        });
    }

    // ========== VIEW SWITCHING ==========
    const allViews = [homeView, chatView, discoverView, spacesView, computerView];

    function hideAllViews() {
        allViews.forEach(v => {
            if (v) v.classList.add('hidden');
        });
    }

    function showChat() {
        hideAllViews();
        if (chatView) chatView.classList.remove('hidden');
        if (chatInput) chatInput.focus();
    }

    function showHome() {
        hideAllViews();
        if (homeView) homeView.classList.remove('hidden');
        if (homeInput) homeInput.focus();
    }

    function showDiscover() {
        hideAllViews();
        if (discoverView) discoverView.classList.remove('hidden');
    }

    function showSpaces() {
        hideAllViews();
        if (spacesView) spacesView.classList.remove('hidden');
    }

    function showComputer() {
        hideAllViews();
        if (computerView) computerView.classList.remove('hidden');
    }

    function resetNavigation() {
        navItems.forEach(n => n.classList.remove('active'));
    }

    document.getElementById('nav-search')?.addEventListener('click', () => {
        resetNavigation();
        document.getElementById('nav-search').classList.add('active');
        showHome();
    });

    document.getElementById('nav-discover')?.addEventListener('click', () => {
        resetNavigation();
        document.getElementById('nav-discover').classList.add('active');
        showDiscover();
    });

    document.getElementById('nav-spaces')?.addEventListener('click', () => {
        resetNavigation();
        document.getElementById('nav-spaces').classList.add('active');
        showSpaces();
    });

    document.getElementById('nav-computer')?.addEventListener('click', () => {
        resetNavigation();
        document.getElementById('nav-computer').classList.add('active');
        showComputer();
    });

    function resetChat() {
        chatMessages.innerHTML = '';
        chatTitle.textContent = 'New Thread';
        currentThreadTitle = null;
    }

    // ========== HISTORY ==========
    const threadHistory = [];
    const threadsHTML = {};
    let currentThreadTitle = null;

    function addToHistory(title) {
        if (threadHistory.length === 0) {
            historyList.innerHTML = '';
        }
        // Remove duplicate if exists
        const idx = threadHistory.indexOf(title);
        if (idx > -1) threadHistory.splice(idx, 1);
        threadHistory.unshift(title);
        renderHistory();
    }

    function renderHistory() {
        historyList.innerHTML = '';
        if (threadHistory.length === 0) {
            historyList.innerHTML = '<p>Your threads will appear here.</p>';
            return;
        }
        threadHistory.forEach(title => {
            const item = document.createElement('div');
            item.className = 'history-item';
            Object.assign(item.style, {
                padding: '0.4rem 0.5rem',
                color: '#9B9CA0',
                cursor: 'pointer',
                fontSize: '0.82rem',
                whiteSpace: 'nowrap',
                overflow: 'hidden',
                textOverflow: 'ellipsis',
                borderRadius: '6px',
                marginBottom: '1px',
                transition: 'background 150ms ease, color 150ms ease'
            });

            item.addEventListener('mouseenter', () => {
                item.style.background = 'rgba(255,255,255,0.06)';
                item.style.color = '#E8E8E8';
            });
            item.addEventListener('mouseleave', () => {
                item.style.background = 'transparent';
                item.style.color = '#9B9CA0';
            });

            item.innerHTML = `<span style="vertical-align:middle">${escapeHTML(title)}</span>`;

            item.addEventListener('click', () => {
                if (threadsHTML[title]) {
                    showChat();
                    chatTitle.textContent = title;
                    currentThreadTitle = title;
                    chatMessages.innerHTML = threadsHTML[title];
                    scrollToBottom();
                    navItems.forEach(n => n.classList.remove('active'));
                    document.getElementById('nav-search')?.classList.add('active');
                }
            });
            historyList.appendChild(item);
        });
    }

    // ========== MESSAGE CREATION ==========
    function addUserMessage(text, files = []) {
        const msg = document.createElement('div');
        msg.className = 'message user-message';
        
        let attachmentHTML = '';
        if (files && files.length > 0) {
            attachmentHTML = `<div class="user-message-attachments">` + 
                files.map(f => {
                    if (f.isImage && f.base64) {
                        return `<div class="user-attachment-img"><img src="data:${f.mimeType};base64,${f.base64}" alt="${escapeHTML(f.name)}"></div>`;
                    } else {
                        return `<div class="user-attachment-file"><i data-lucide="file-text"></i><span>${escapeHTML(f.name)}</span></div>`;
                    }
                }).join('') + `</div>`;
        }

        msg.innerHTML = `
            <div class="message-content">
                ${attachmentHTML}
                <div class="message-text">${escapeHTML(text)}</div>
            </div>
        `;
        chatMessages.appendChild(msg);
        if (window.lucide) window.lucide.createIcons();
        scrollToBottom();
    }

    function addAIMessage() {
        const msg = document.createElement('div');
        msg.className = 'message ai-message';
        msg.innerHTML = `
            <div class="message-label">
                <svg class="ai-icon spinning" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="#20B8CD" stroke-width="2" stroke-linecap="round">
                    <path d="M12 3v4m0 14v-4M5.636 5.636l2.828 2.828m7.072 7.072l2.828 2.828M3 12h4m14 0h-4M5.636 18.364l2.828-2.828m7.072-7.072l2.828-2.828"/>
                </svg>
                <span class="ai-label-text">Thinking...</span>
            </div>
            <div class="search-status-container">
                <div class="search-status-steps">
                    <div class="status-step active" id="step-search">
                        <div class="status-dot"></div>
                        <span>Searching the web</span>
                    </div>
                    <div class="status-step" id="step-read">
                        <div class="status-dot"></div>
                        <span>Reading sources</span>
                    </div>
                    <div class="status-step" id="step-write">
                        <div class="status-dot"></div>
                        <span>Writing answer</span>
                    </div>
                </div>
            </div>
            <div class="message-content">
                <div class="typing-indicator">
                    <span></span><span></span><span></span>
                </div>
            </div>
            <div class="sources-section">
                <div class="sources-section-header">
                    <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M10 13a5 5 0 007.54.54l3-3a5 5 0 00-7.07-7.07l-1.72 1.71"/><path d="M14 11a5 5 0 00-7.54-.54l-3 3a5 5 0 007.07 7.07l1.71-1.71"/></svg>
                    <span>Sources</span>
                </div>
                <div class="source-cards-container"></div>
            </div>
            <div class="related-section" style="display:none">
                <div class="related-section-header">
                    <i data-lucide="layers-3"></i>
                    <span>Related</span>
                </div>
                <div class="related-queries-container"></div>
            </div>
            <div class="message-actions" style="display:none">
            </div>
        `;
        chatMessages.appendChild(msg);
        scrollToBottom();
        return {
            msgEl: msg,
            contentEl: msg.querySelector('.message-content'),
            labelEl: msg.querySelector('.ai-label-text'),
            actionsEl: msg.querySelector('.message-actions'),
            statusContainer: msg.querySelector('.search-status-container'),
            sourceCardsContainer: msg.querySelector('.source-cards-container'),
            sourcesSection: msg.querySelector('.sources-section'),
            relatedSection: msg.querySelector('.related-section'),
            relatedContainer: msg.querySelector('.related-queries-container'),
            stepSearch: msg.querySelector('#step-search'),
            stepRead: msg.querySelector('#step-read'),
            stepWrite: msg.querySelector('#step-write'),
        };
    }

    // ========== SOURCE CARDS ==========
    function renderSourceCards(container, sources, sourcesSection) {
        if (!sources || sources.length === 0) return;
        // Show the whole sources section
        if (sourcesSection) sourcesSection.style.display = 'block';
        container.innerHTML = sources.map((s, i) => {
            const domain = extractDomain(s.url);
            const favicon = `https://www.google.com/s2/favicons?domain=${domain}&sz=32`;
            return `
                <a href="${escapeHTML(s.url)}" target="_blank" rel="noopener noreferrer" class="source-card" title="${escapeHTML(s.title)}">
                    <div class="source-card-number">${i + 1}</div>
                    <div class="source-card-body">
                        <div class="source-card-title">${escapeHTML(s.title)}</div>
                        <div class="source-card-domain">
                            <img src="${favicon}" alt="" width="14" height="14" onerror="this.style.display='none'">
                            <span>${escapeHTML(domain)}</span>
                        </div>
                    </div>
                </a>
            `;
        }).join('');
    }

    function extractDomain(url) {
        try {
            return new URL(url).hostname.replace('www.', '');
        } catch {
            return url;
        }
    }

    // ========== STATUS STEP UPDATES ==========
    function setStepActive(stepEl) {
        stepEl.classList.add('active');
        stepEl.classList.remove('done');
    }

    function setStepDone(stepEl) {
        stepEl.classList.remove('active');
        stepEl.classList.add('done');
    }

    // ========== POST-PROCESS AI RESPONSE ==========
    function postProcessAIMessage(aiMessage) {
        const { msgEl, contentEl, relatedSection, relatedContainer } = aiMessage;

        // Add copy buttons to all code blocks
        msgEl.querySelectorAll('pre').forEach(pre => {
            if (pre.querySelector('.code-copy-btn')) return;
            const btn = document.createElement('button');
            btn.className = 'code-copy-btn';
            btn.innerHTML = `<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="9" y="9" width="13" height="13" rx="2"/><path d="M5 15H4a2 2 0 01-2-2V4a2 2 0 012-2h9a2 2 0 012 2v1"/></svg>`;
            btn.title = 'Copy code';
            pre.style.position = 'relative';
            btn.addEventListener('click', () => {
                const code = pre.querySelector('code');
                navigator.clipboard.writeText(code ? code.textContent : pre.textContent);
                btn.innerHTML = `<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="#4ade80" stroke-width="2"><polyline points="20 6 9 17 4 12"/></svg>`;
                setTimeout(() => {
                    btn.innerHTML = `<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="9" y="9" width="13" height="13" rx="2"/><path d="M5 15H4a2 2 0 01-2-2V4a2 2 0 012-2h9a2 2 0 012 2v1"/></svg>`;
                }, 2000);
            });
            pre.appendChild(btn);
        });

        // Parse Related Queries
        const html = contentEl.innerHTML;
        const markers = [
            '<strong>Related Queries:</strong>',
            '<strong>Related questions:</strong>',
            'Related Queries:',
            'Related questions:'
        ];

        let foundMarker = null;
        let markerIndex = -1;

        for (const m of markers) {
            const idx = html.lastIndexOf(m);
            if (idx !== -1 && idx > markerIndex) {
                markerIndex = idx;
                foundMarker = m;
            }
        }

        if (foundMarker) {
            const afterMarker = html.substring(markerIndex + foundMarker.length);
            // Extract list items <li>...</li>
            const tempDiv = document.createElement('div');
            tempDiv.innerHTML = afterMarker;
            const items = tempDiv.querySelectorAll('li');
            
            if (items.length > 0) {
                const queries = Array.from(items).map(li => li.textContent.trim());
                
                // Remove the related queries from the main content
                // More robust stripping: find the starting tag of the paragraph/header containing the marker
                const beforeMarker = html.substring(0, markerIndex);
                const lastTagMatch = beforeMarker.match(/<[a-z0-9]+(?:\s+[^>]*?)?>\s*$/i);
                
                if (lastTagMatch) {
                    contentEl.innerHTML = beforeMarker.substring(0, lastTagMatch.index).trim();
                } else {
                    contentEl.innerHTML = beforeMarker.trim();
                }
                
                // Final cleanup of trailing empty tags
                contentEl.innerHTML = contentEl.innerHTML.replace(/<(p|h[1-6]|strong|em|div|span|ul|ol|li)>\s*<\/\1>\s*$/i, '').trim();

                // Render as buttons
                relatedContainer.innerHTML = '';
                queries.forEach(q => {
                    if (!q) return;
                    const btn = document.createElement('div');
                    btn.className = 'related-query-item';
                    btn.innerHTML = `<span>${escapeHTML(q)}</span> <i data-lucide="plus"></i>`;
                    btn.onclick = () => {
                        const chatInput = document.getElementById('chat-search-input');
                        if (chatInput) {
                            chatInput.value = q;
                            document.getElementById('chat-submit-btn')?.click();
                        }
                    };
                    relatedContainer.appendChild(btn);
                });
                
                relatedSection.style.display = 'block';
                if (window.lucide) window.lucide.createIcons();
            }
        }

        // Show action bar
        const actionsEl = msgEl.querySelector('.message-actions');
        if (actionsEl) {
            actionsEl.style.display = 'none';
        }
    }

    function scrollToBottom() {
        requestAnimationFrame(() => {
            chatMessages.scrollTop = chatMessages.scrollHeight;
        });
    }

    function escapeHTML(str) {
        const div = document.createElement('div');
        div.textContent = str;
        return div.innerHTML;
    }

    // ========== FALLBACK LOGIC ==========
    function fallbackAnswer(sources) {
        if (!sources || sources.length === 0) {
            return "I searched the web but couldn't find definitive information on that right now. Please try a different query.";
        }
        return `
Here’s what I found based on recent sources:

Multiple reports indicate recent information is available on official and sports news platforms. You can check detailed records from the sources below.

**Sources:**
${sources.map((s, i) => `${i + 1}. [${s.title}](${s.url})`).join("\n")}
`;
    }

    async function callLLMWithRetry(query, sessionId, images = null, retries = 2) {
        try {
            const body = { query: query, session_id: sessionId };
            if (images && images.length > 0) body.images = images;

            const response = await fetch(`${API_BASE}/ask/stream`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(body)
            });

            if (!response.ok) {
                const errData = await response.json().catch(() => ({ detail: 'Server error' }));
                throw new Error(errData.detail || `HTTP ${response.status}`);
            }
            return response;
        } catch (e) {
            if (retries > 0) {
                console.warn(`Retrying chat... (${2 - retries + 1}/2)`);
                await new Promise(r => setTimeout(r, 1000));
                return await callLLMWithRetry(query, sessionId, retries - 1);
            }
            throw e;
        }
    }

    // ========== AI QUERY (STREAMING) ==========
    async function sendQuery(query) {
        if (isStreaming || !query.trim()) return;
        isStreaming = true;

        if (chatMessages.children.length === 0) {
            chatTitle.textContent = query.length > 50 ? query.substring(0, 50) + '...' : query;
            currentThreadTitle = chatTitle.textContent;
            addToHistory(chatTitle.textContent);
        }

        // Capture attachments for chat message and API call
        const currentAttachments = [...attachedFiles];
        
        addUserMessage(query, currentAttachments);
        
        // Clear attachments from search bar immediately
        attachedFiles.length = 0;
        renderAttachedFiles();

        const aiMessage = addAIMessage();
        const {
            msgEl, contentEl, labelEl, statusContainer,
            sourceCardsContainer, sourcesSection, stepSearch, stepRead, stepWrite
        } = aiMessage;

        let sources = [];
        try {
            // Collect images from the captured attachments
            const activeImages = currentAttachments
                .filter(f => f.isImage && f.base64)
                .map(f => ({ data: f.base64, mime_type: f.mimeType }));

            const response = await callLLMWithRetry(query, SESSION_ID, activeImages);
            const reader = response.body.getReader();
            const decoder = new TextDecoder();
            let fullText = '';
            let sourcesParsed = false;
            let buffer = '';

            setStepDone(stepSearch);
            setStepActive(stepRead);
            labelEl.textContent = 'Thinking...';

            while (true) {
                const { done, value } = await reader.read();
                if (done) break;

                const chunk = decoder.decode(value, { stream: true });
                buffer += chunk;

                if (!sourcesParsed && buffer.includes('__END_SOURCES__')) {
                    const startMarker = '__SOURCES__';
                    const endMarker = '__END_SOURCES__';
                    const startIdx = buffer.indexOf(startMarker);
                    const endIdx = buffer.indexOf(endMarker);

                    if (startIdx !== -1 && endIdx !== -1) {
                        const jsonStr = buffer.substring(startIdx + startMarker.length, endIdx);
                        try {
                            sources = JSON.parse(jsonStr);
                            // Store sources but don't render yet - wait for text to finish
                        } catch (e) {
                            console.warn('Failed to parse sources:', e);
                        }

                        buffer = buffer.substring(endIdx + endMarker.length);
                        if (buffer.startsWith('\n')) buffer = buffer.substring(1);
                        sourcesParsed = true;

                        setStepDone(stepRead);
                        setStepActive(stepWrite);
                        labelEl.textContent = 'Answer';
                        const aiIcon = msgEl.querySelector('.ai-icon');
                        if (aiIcon) aiIcon.classList.remove('spinning');

                        setTimeout(() => {
                            statusContainer.classList.add('fade-out');
                            setTimeout(() => {
                                statusContainer.style.display = 'none';
                            }, 400);
                        }, 600);
                        contentEl.innerHTML = '';
                    }
                }

                if (sourcesParsed) {
                    if (fullText === '') {
                        fullText = buffer;
                        buffer = '';
                    } else {
                        fullText += chunk;
                    }
                    contentEl.innerHTML = marked.parse(fullText);
                    scrollToBottom();
                } else if (buffer.length > 0 && !'__SOURCES__'.startsWith(buffer) && !buffer.startsWith('__SOURCES__')) {
                    // Direct response / conversational response
                    sourcesParsed = true;
                    setStepDone(stepSearch);
                    setStepDone(stepRead);
                    setStepActive(stepWrite);
                    labelEl.textContent = 'Answer';
                    const aiIcon = msgEl.querySelector('.ai-icon');
                    if (aiIcon) aiIcon.classList.remove('spinning');
                    statusContainer.style.display = 'none';
                    contentEl.innerHTML = marked.parse(buffer);
                    scrollToBottom();
                }
            }

            if (!sourcesParsed) {
                contentEl.innerHTML = marked.parse(buffer);
            }
            // Render sources at the very end so information appears first
            if (sourcesParsed && sources.length > 0) {
                renderSourceCards(sourceCardsContainer, sources, sourcesSection);
            }
            postProcessAIMessage(aiMessage);

        } catch (error) {
            console.error('Final failure:', error);
            labelEl.textContent = 'Information';
            statusContainer.style.display = 'none';
            const aiIcon = msgEl.querySelector('.ai-icon');
            if (aiIcon) aiIcon.classList.remove('spinning');
            
            let finalFallbackText = fallbackAnswer(sources);
            
            // ✅ Check for Rate Limit to provide specific feedback
            if (error && error.message && error.message.includes('Rate limit exceeded')) {
                finalFallbackText = `**Rate Limit Exceeded**\n\nYou have reached the maximum allowed limit of 20 requests per minute. Please wait for a moment and try again.`;
                labelEl.textContent = 'Limit Exceeded';
                if (aiIcon) {
                    aiIcon.innerHTML = `<path d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" stroke="#FF4B4B" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>`;
                }
            }

            contentEl.innerHTML = marked.parse(finalFallbackText);
            postProcessAIMessage(aiMessage);
        } finally {
            isStreaming = false;
            if (currentThreadTitle) {
                threadsHTML[currentThreadTitle] = chatMessages.innerHTML;
            }
        }
    }

    // ========== SUBMIT HANDLERS ==========
    function handleHomeSubmit() {
        const query = homeInput.value.trim();
        if (!query) return;
        homeInput.value = '';
        homeInput.style.height = 'auto';
        showChat();
        sendQuery(query);
    }

    function handleChatSubmit() {
        const query = chatInput.value.trim();
        if (!query) return;
        chatInput.value = '';
        chatInput.style.height = 'auto';
        sendQuery(query);
    }

    homeInput.addEventListener('keydown', (e) => {
        if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault();
            handleHomeSubmit();
        }
    });

    chatInput.addEventListener('keydown', (e) => {
        if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault();
            handleChatSubmit();
        }
    });

    homeSubmitBtn.addEventListener('click', handleHomeSubmit);
    chatSubmitBtn.addEventListener('click', handleChatSubmit);

    // ========== NAVIGATION ==========
    backBtn.addEventListener('click', showHome);

    newThreadBtn.addEventListener('click', () => {
        resetChat();
        chatInput.focus();
    });

    navNewThread.addEventListener('click', () => {
        resetChat();
        showHome();
    });

    document.getElementById('logo')?.addEventListener('click', () => {
        resetChat();
        showHome();
    });

    // Sidebar nav active states
    navItems.forEach(item => {
        item.addEventListener('click', () => {
            navItems.forEach(n => n.classList.remove('active'));
            item.classList.add('active');

            if (item.id === 'nav-history') {
                const sidebarBottom = document.querySelector('.sidebar-bottom');
                if (sidebarBottom) sidebarBottom.scrollIntoView({ behavior: 'smooth' });
                if (currentThreadTitle) {
                    showChat();
                } else {
                    showHome();
                }
                return;
            }

            if (item.id === 'nav-search') {
                showHome();
                return;
            }

            if (item.id === 'nav-discover') {
                showDiscover();
                return;
            }

            if (item.id === 'nav-spaces') {
                showSpaces();
                return;
            }

            if (item.id === 'nav-computer') {
                showComputer();
                return;
            }

            // Other nav items (fallback)
            resetChat();
            showHome();
        });
    });

    // ========== NEW VIEW INTERACTIONS ==========
    // Discover Card clicks
    document.querySelectorAll('.discover-card').forEach(card => {
        card.addEventListener('click', () => {
            const topic = card.getAttribute('data-topic');
            if (topic && homeInput) {
                homeInput.value = topic;
                document.getElementById('nav-search')?.click(); // Switch to home nav state
                homeSubmitBtn.click(); // Submit the query
            }
        });
    });

    // Computer Upload Dropzone Trigger
    const computerFileInput = document.getElementById('computer-file-input');
    const computerDropzone = document.getElementById('computer-dropzone');
    
    document.querySelectorAll('.upload-btn-trigger').forEach(btn => {
        btn.addEventListener('click', () => computerFileInput?.click());
    });
    
    if (computerDropzone && computerFileInput) {
        computerDropzone.addEventListener('click', (e) => {
            if (e.target.tagName !== 'BUTTON') {
                computerFileInput.click();
            }
        });
        
        computerDropzone.addEventListener('dragover', (e) => {
            e.preventDefault();
            computerDropzone.style.borderColor = 'var(--text-secondary)';
            computerDropzone.style.background = 'rgba(255, 255, 255, 0.04)';
        });
        
        computerDropzone.addEventListener('dragleave', (e) => {
            e.preventDefault();
            computerDropzone.style.borderColor = 'var(--border-primary)';
            computerDropzone.style.background = 'rgba(255, 255, 255, 0.02)';
        });
        
        computerDropzone.addEventListener('drop', (e) => {
            e.preventDefault();
            computerDropzone.style.borderColor = 'var(--border-primary)';
            computerDropzone.style.background = 'rgba(255, 255, 255, 0.02)';
            
            if (e.dataTransfer.files && e.dataTransfer.files.length > 0) {
                Array.from(e.dataTransfer.files).forEach(f => handleFileUpload(f));
                document.getElementById('nav-search')?.click(); // Switch to home to see attachments
            }
        });

        computerFileInput.addEventListener('change', (e) => {
            if (e.target.files && e.target.files.length > 0) {
                Array.from(e.target.files).forEach(f => handleFileUpload(f));
                document.getElementById('nav-search')?.click(); // Switch to home to see attachments
            }
        });
    }


    // ========== HELPERS ==========
    function escapeHTML(str) {
        const div = document.createElement('div');
        div.textContent = str;
        return div.innerHTML;
    }

    // ========== FILE ATTACHMENT ==========
    const attachedFiles = [];
    const homeFilesContainer = document.getElementById('home-attached-files');
    const chatFilesContainer = document.getElementById('chat-attached-files');

    const fileInput = document.createElement('input');
    fileInput.type = 'file';
    fileInput.accept = '.pdf,.txt,.md,.png,.jpg,.jpeg,.webp';
    fileInput.style.display = 'none';
    document.body.appendChild(fileInput);

    async function handleFileUpload(file) {
        const formData = new FormData();
        // Fallback for blobs from clipboard which might not have names
        if (!file.name) {
            const ext = file.type.split('/')[1] || 'png';
            file = new File([file], `screenshot-${Date.now()}.${ext}`, { type: file.type });
        }
        
        formData.append('file', file);
        formData.append('session_id', SESSION_ID);

        console.log(`[Upload] Starting upload for ${file.name} (${file.type})`);

        // Show uploading state
        const originalText = "Attach file";
        const paperclipBtns = document.querySelectorAll('.icon-btn-text');
        paperclipBtns.forEach(btn => {
            btn.style.opacity = '0.5';
            btn.style.pointerEvents = 'none';
        });

        try {
            const response = await fetch(`${API_BASE}/upload`, {
                method: 'POST',
                body: formData
            });

            if (!response.ok) throw new Error('Upload failed');

            const result = await response.json();
            
            // Check if it's an image to store for vision
            let base64 = null;
            let mimeType = file.type;
            const isImage = mimeType.startsWith('image/');
            
            if (isImage) {
                base64 = await new Promise((resolve) => {
                    const reader = new FileReader();
                    reader.onload = () => resolve(reader.result.split(',')[1]);
                    reader.readAsDataURL(file);
                });
            }

            attachedFiles.push({
                name: file.name,
                id: Date.now(),
                isImage: isImage,
                mimeType: mimeType,
                base64: base64
            });
            renderAttachedFiles();
        } catch (error) {
            console.error('Upload error:', error);
            alert(`Failed to upload file: ${error.message}. Please try again.`);
        } finally {
            paperclipBtns.forEach(btn => {
                btn.style.opacity = '1';
                btn.style.pointerEvents = 'auto';
            });
        }
    }

    // ========== CLIPBOARD PASTE SUPPORT ==========
    async function handlePaste(e) {
        const items = e.clipboardData.items;
        for (let i = 0; i < items.length; i++) {
            if (items[i].type.indexOf('image') !== -1) {
                const blob = items[i].getAsFile();
                if (blob) {
                    e.preventDefault();
                    console.log('[Paste] Image detected in clipboard');
                    await handleFileUpload(blob);
                }
            }
        }
    }

    function renderAttachedFiles() {
        const containers = [homeFilesContainer, chatFilesContainer];
        containers.forEach(container => {
            if (!container) return;
            container.innerHTML = attachedFiles.map(file => `
                <div class="attached-file-tag" data-id="${file.id}">
                    <i data-lucide="${file.isImage ? 'image' : 'file-text'}"></i>
                    <span>${escapeHTML(file.name)}</span>
                    <button class="remove-file-btn" onclick="removeFile(${file.id})">
                        <i data-lucide="x"></i>
                    </button>
                </div>
            `).join('');
        });
        if (window.lucide) window.lucide.createIcons();
    }

    window.removeFile = (id) => {
        const index = attachedFiles.findIndex(f => f.id === id);
        if (index > -1) {
            attachedFiles.splice(index, 1);
            renderAttachedFiles();
        }
    };

    fileInput.addEventListener('change', (e) => {
        if (e.target.files.length > 0) {
            handleFileUpload(e.target.files[0]);
            e.target.value = ''; // Reset for same file re-upload
        }
    });

    document.querySelectorAll('.icon-btn-text').forEach(btn => {
        btn.addEventListener('click', (e) => {
            e.preventDefault();
            fileInput.click();
        });
    });

    // Attach paste listeners
    homeInput.addEventListener('paste', handlePaste);
    chatInput.addEventListener('paste', handlePaste);

    // ========== FOCUS / MODEL PICKER ==========
    const focusModes = ['All', 'Academic', 'Writing', 'Wolfram', 'YouTube', 'Reddit'];
    let focusIndex = 0;

    document.querySelectorAll('.model-picker').forEach(picker => {
        picker.addEventListener('click', (e) => {
            e.preventDefault();
            focusIndex = (focusIndex + 1) % focusModes.length;
            const span = picker.querySelector('span');
            span.textContent = focusModes[focusIndex];
        });
    });

    // ========== VOICE INPUT ==========
    const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
    document.querySelectorAll('.icon-btn').forEach(btn => {
        btn.addEventListener('click', (e) => {
            e.preventDefault();
            if (!SpeechRecognition) {
                alert('Speech recognition is not supported in your browser.');
                return;
            }

            const recognition = new SpeechRecognition();
            recognition.lang = 'en-US';
            const originalColor = btn.style.color;
            btn.style.color = '#F87171';
            recognition.start();

            recognition.onresult = function(event) {
                const speechResult = event.results[0][0].transcript;
                if (!homeView.classList.contains('hidden')) {
                    homeInput.value += (homeInput.value.length > 0 ? ' ' : '') + speechResult;
                    homeInput.focus();
                } else {
                    chatInput.value += (chatInput.value.length > 0 ? ' ' : '') + speechResult;
                    chatInput.focus();
                }
            };

            recognition.onspeechend = function() {
                recognition.stop();
                btn.style.color = originalColor;
            };

            recognition.onerror = function(event) {
                btn.style.color = originalColor;
                console.error('Speech Recognition Error: ', event.error);
            };
        });
    });

    // ========== PRO TAG TOGGLE ==========
    document.querySelectorAll('.computer-tag').forEach(tag => {
        tag.addEventListener('click', () => {
            const isActive = tag.classList.toggle('active');
            if (isActive) {
                tag.style.background = 'rgba(32, 184, 205, 0.15)';
                tag.style.borderColor = 'rgba(32, 184, 205, 0.3)';
                tag.style.color = '#20B8CD';
            } else {
                tag.style.background = '';
                tag.style.borderColor = '';
                tag.style.color = '';
            }
        });
    });

    // ========== SUGGESTION ITEMS ==========
    function bindSuggestionClicks() {
        document.querySelectorAll('.suggestion-item').forEach(item => {
            item.addEventListener('click', () => {
                const query = item.textContent.trim();
                homeInput.value = '';
                showChat();
                sendQuery(query);
            });
        });
    }
    bindSuggestionClicks();

    // ========== TAB SWITCHING ==========
    function updateSuggestions(tabKey) {
        if (!tabData[tabKey]) return;
        suggestionContainer.innerHTML = '';
        tabData[tabKey].forEach(text => {
            const item = document.createElement('div');
            item.className = 'suggestion-item';
            item.textContent = text;
            suggestionContainer.appendChild(item);
        });
        bindSuggestionClicks();
    }

    tabButtons.forEach(button => {
        button.addEventListener('click', () => {
            tabButtons.forEach(btn => btn.classList.remove('active'));
            button.classList.add('active');
            updateSuggestions(button.getAttribute('data-tab'));
        });
    });

    // ========== AUTO-RESIZE TEXTAREAS ==========
    [homeInput, chatInput].forEach(textarea => {
        textarea.addEventListener('input', function () {
            this.style.height = 'auto';
            this.style.height = Math.min(this.scrollHeight, 200) + 'px';
            this.style.overflowY = this.scrollHeight > 200 ? 'auto' : 'hidden';
        });
    });

    // ========== THEME LOGIC ==========
    const themeBtn = document.getElementById('theme-toggle-btn');
    const themeIcon = document.getElementById('theme-icon');
    const themeText = document.getElementById('theme-text');

    function applyTheme(isLight) {
        if (isLight) {
            document.documentElement.classList.add('light-mode');
            if (themeIcon) themeIcon.setAttribute('data-lucide', 'moon');
            if (themeText) themeText.textContent = 'Dark Mode';
        } else {
            document.documentElement.classList.remove('light-mode');
            if (themeIcon) themeIcon.setAttribute('data-lucide', 'sun');
            if (themeText) themeText.textContent = 'Light Mode';
        }
        if (window.lucide) window.lucide.createIcons();
    }

    const savedTheme = localStorage.getItem('theme');
    const isLightMode = savedTheme === 'light' || (!savedTheme && window.matchMedia('(prefers-color-scheme: light)').matches);
    applyTheme(isLightMode);

    if (themeBtn) {
        themeBtn.addEventListener('click', () => {
            const willBeLight = !document.documentElement.classList.contains('light-mode');
            localStorage.setItem('theme', willBeLight ? 'light' : 'dark');
            applyTheme(willBeLight);
        });
    }
});
