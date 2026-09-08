import { muapi } from '../lib/muapi.js';
import { i2vModels, getAspectRatiosForI2VModel, getDurationsForI2VModel, getResolutionsForI2VModel } from '../lib/models.js';
import { AuthModal } from './AuthModal.js';

const DEFAULT_PROMPTS = [
    'Elegant slow walk, fabric flowing gently in sea breeze, cinematic golden hour light, luxury fashion editorial',
    'Relaxed turn with soft smile, hair moves in warm breeze, dreamy bokeh beach background, slow motion',
    'Gentle sway walking along shoreline, waves crashing softly, fabric catching sunlight, cinematic wide shot',
    'Confident pose, subtle fabric movement, Mediterranean coast backdrop, editorial fashion film',
    'Serene stillness, golden sunset reflections, slow zoom out, atmospheric luxury brand film',
];

export function PromoVideoStudio() {
    const container = document.createElement('div');
    container.className = 'w-full h-full flex flex-col bg-app-bg overflow-y-auto custom-scrollbar';

    // --- State ---
    let scenes = [];
    let selectedModel = i2vModels[0].id;
    let selectedModelName = i2vModels[0].name;
    let selectedAr = '9:16';
    let selectedDuration = 5;
    let selectedResolution = '720p';
    let dropdownOpen = null;
    let sceneIdCounter = 0;

    // ==========================================
    // HERO
    // ==========================================
    const hero = document.createElement('div');
    hero.className = 'flex flex-col items-center pt-10 pb-8 px-4 animate-fade-in-up';
    hero.innerHTML = `
        <div class="mb-6 relative group">
            <div class="absolute inset-0 bg-primary/20 blur-[80px] rounded-full opacity-40 group-hover:opacity-60 transition-opacity duration-1000"></div>
            <div class="relative w-20 h-20 bg-teal-900/40 rounded-3xl flex items-center justify-center border border-white/5">
                <div class="w-14 h-14 bg-primary/10 rounded-2xl flex items-center justify-center border border-primary/20 shadow-glow">
                    <svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" class="text-primary">
                        <rect x="2" y="3" width="20" height="14" rx="2"/>
                        <path d="M8 21h8M12 17v4"/>
                        <circle cx="9" cy="8" r="1.5" fill="currentColor" stroke="none"/>
                        <path d="M21 8l-4 4-4-4"/>
                    </svg>
                </div>
            </div>
        </div>
        <h1 class="text-3xl sm:text-5xl md:text-6xl font-black text-white tracking-widest uppercase mb-3 text-center">Promo Studio</h1>
        <p class="text-secondary text-sm font-medium tracking-wide opacity-60 text-center max-w-md">Animate your product images into stunning video clips for your brand</p>
    `;
    container.appendChild(hero);

    // ==========================================
    // GLOBAL SETTINGS BAR
    // ==========================================
    const settingsBar = document.createElement('div');
    settingsBar.className = 'w-full max-w-5xl mx-auto px-4 pb-6 z-40';

    const settingsInner = document.createElement('div');
    settingsInner.className = 'bg-[#111]/90 backdrop-blur-xl border border-white/10 rounded-2xl p-3 flex flex-wrap items-center gap-2';

    const createDropdown = (id, icon, label, options, currentVal, onChange) => {
        const wrapper = document.createElement('div');
        wrapper.className = 'relative';

        const btn = document.createElement('button');
        btn.id = id;
        btn.className = 'flex items-center gap-2 px-3 py-2 bg-white/5 hover:bg-white/10 rounded-xl border border-white/5 transition-all group';
        btn.innerHTML = `
            ${icon}
            <span id="${id}-label" class="text-xs font-bold text-white">${currentVal || label}</span>
            <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="4" class="opacity-30"><path d="M6 9l6 6 6-6"/></svg>
        `;

        const menu = document.createElement('div');
        menu.className = 'absolute top-full left-0 mt-1 bg-[#1a1a1a] border border-white/10 rounded-xl shadow-2xl overflow-hidden z-50 hidden min-w-[160px]';

        options.forEach(opt => {
            const item = document.createElement('button');
            item.className = 'w-full text-left px-4 py-2.5 text-xs text-secondary hover:text-white hover:bg-white/5 transition-colors';
            item.textContent = opt;
            item.onclick = () => {
                document.getElementById(`${id}-label`).textContent = opt;
                menu.classList.add('hidden');
                dropdownOpen = null;
                onChange(opt);
            };
            menu.appendChild(item);
        });

        btn.onclick = (e) => {
            e.stopPropagation();
            const isOpen = !menu.classList.contains('hidden');
            document.querySelectorAll('.promo-dropdown-menu').forEach(m => m.classList.add('hidden'));
            dropdownOpen = null;
            if (!isOpen) {
                menu.classList.remove('hidden');
                dropdownOpen = id;
            }
        };

        wrapper.appendChild(btn);
        menu.classList.add('promo-dropdown-menu');
        wrapper.appendChild(menu);
        return wrapper;
    };

    const modelDropdown = createDropdown(
        'promo-model',
        `<div class="w-4 h-4 bg-primary rounded flex items-center justify-center"><span class="text-[8px] font-black text-black">V</span></div>`,
        'Model',
        i2vModels.map(m => m.name),
        selectedModelName,
        (val) => {
            const m = i2vModels.find(m => m.name === val);
            if (m) {
                selectedModel = m.id;
                selectedModelName = m.name;
                updateDynamicControls();
            }
        }
    );

    const arOptions = ['9:16', '16:9', '1:1', '4:3'];
    const arDropdown = createDropdown(
        'promo-ar',
        `<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" class="opacity-60"><rect x="3" y="3" width="18" height="18" rx="2"/></svg>`,
        'Ratio',
        arOptions,
        selectedAr,
        (val) => { selectedAr = val; }
    );

    const durationOptions = ['5', '10'];
    const durationDropdown = createDropdown(
        'promo-dur',
        `<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" class="opacity-60"><circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/></svg>`,
        'Duration',
        durationOptions,
        `${selectedDuration}s`,
        (val) => { selectedDuration = parseInt(val); }
    );

    const resOptions = ['480p', '720p', '1080p'];
    const resDropdown = createDropdown(
        'promo-res',
        `<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" class="opacity-60"><path d="M2 12s3-7 10-7 10 7 10 7-3 7-10 7-10-7-10-7z"/><circle cx="12" cy="12" r="3"/></svg>`,
        'Res',
        resOptions,
        selectedResolution,
        (val) => { selectedResolution = val; }
    );

    function updateDynamicControls() {
        // Could update dropdowns based on model capabilities
    }

    const labelEl = document.createElement('span');
    labelEl.className = 'text-xs text-muted ml-1';
    labelEl.textContent = 'Global settings applied to all scenes';

    settingsInner.appendChild(modelDropdown);
    settingsInner.appendChild(arDropdown);
    settingsInner.appendChild(durationDropdown);
    settingsInner.appendChild(resDropdown);
    settingsInner.appendChild(labelEl);
    settingsBar.appendChild(settingsInner);
    container.appendChild(settingsBar);

    // Close dropdowns on outside click
    document.addEventListener('click', () => {
        document.querySelectorAll('.promo-dropdown-menu').forEach(m => m.classList.add('hidden'));
        dropdownOpen = null;
    });

    // ==========================================
    // UPLOAD ZONE
    // ==========================================
    const uploadSection = document.createElement('div');
    uploadSection.className = 'w-full max-w-5xl mx-auto px-4 pb-6';

    const dropZone = document.createElement('div');
    dropZone.className = 'border-2 border-dashed border-white/10 hover:border-primary/40 rounded-2xl p-8 text-center transition-all cursor-pointer group';
    dropZone.innerHTML = `
        <div class="flex flex-col items-center gap-3">
            <div class="w-12 h-12 bg-white/5 rounded-2xl flex items-center justify-center group-hover:bg-primary/10 transition-colors">
                <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" class="text-secondary group-hover:text-primary transition-colors">
                    <path d="M21 15v4a2 2 0 01-2 2H5a2 2 0 01-2-2v-4"/>
                    <polyline points="17 8 12 3 7 8"/>
                    <line x1="12" y1="3" x2="12" y2="15"/>
                </svg>
            </div>
            <div>
                <p class="text-white font-semibold text-sm">Drop images here or click to upload</p>
                <p class="text-muted text-xs mt-1">JPG, PNG, WebP · Up to 8 images · Max 10MB each</p>
            </div>
            <p class="text-xs text-secondary/50">Or paste a hosted image URL below each scene</p>
        </div>
    `;

    const fileInput = document.createElement('input');
    fileInput.type = 'file';
    fileInput.accept = 'image/jpeg,image/png,image/webp';
    fileInput.multiple = true;
    fileInput.className = 'hidden';

    dropZone.onclick = () => fileInput.click();

    dropZone.addEventListener('dragover', (e) => {
        e.preventDefault();
        dropZone.classList.add('border-primary/40', 'bg-primary/5');
    });
    dropZone.addEventListener('dragleave', () => {
        dropZone.classList.remove('border-primary/40', 'bg-primary/5');
    });
    dropZone.addEventListener('drop', (e) => {
        e.preventDefault();
        dropZone.classList.remove('border-primary/40', 'bg-primary/5');
        const files = Array.from(e.dataTransfer.files).filter(f => f.type.startsWith('image/'));
        handleFiles(files);
    });

    fileInput.onchange = () => {
        const files = Array.from(fileInput.files);
        handleFiles(files);
        fileInput.value = '';
    };

    uploadSection.appendChild(dropZone);
    uploadSection.appendChild(fileInput);
    container.appendChild(uploadSection);

    // ==========================================
    // SCENES GRID
    // ==========================================
    const scenesSection = document.createElement('div');
    scenesSection.className = 'w-full max-w-5xl mx-auto px-4 pb-10';

    const scenesHeader = document.createElement('div');
    scenesHeader.className = 'flex items-center justify-between mb-4 hidden';
    scenesHeader.id = 'scenes-header';
    scenesHeader.innerHTML = `
        <h2 class="text-white font-bold text-lg">Scenes <span id="scene-count" class="text-primary text-sm ml-1">0</span></h2>
        <div class="flex items-center gap-2">
            <button id="generate-all-btn" class="flex items-center gap-2 px-5 py-2.5 bg-primary text-black text-sm font-bold rounded-xl hover:bg-primary/90 transition-all shadow-glow-sm disabled:opacity-40">
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><polygon points="5 3 19 12 5 21 5 3"/></svg>
                Generate All Clips
            </button>
        </div>
    `;
    scenesSection.appendChild(scenesHeader);

    const scenesGrid = document.createElement('div');
    scenesGrid.className = 'grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4';
    scenesSection.appendChild(scenesGrid);
    container.appendChild(scenesSection);

    // ==========================================
    // REEL PREVIEW SECTION
    // ==========================================
    const reelSection = document.createElement('div');
    reelSection.className = 'w-full max-w-5xl mx-auto px-4 pb-16 hidden';
    reelSection.id = 'reel-section';
    reelSection.innerHTML = `
        <div class="border-t border-white/5 pt-8">
            <h2 class="text-white font-bold text-xl mb-6 flex items-center gap-2">
                <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" class="text-primary"><polygon points="23 7 16 12 23 17 23 7"/><rect x="1" y="5" width="15" height="14" rx="2"/></svg>
                Generated Reel
            </h2>
            <div id="reel-grid" class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4"></div>
        </div>
    `;
    container.appendChild(reelSection);

    // ==========================================
    // CORE LOGIC
    // ==========================================

    function fileToDataUrl(file) {
        return new Promise((resolve, reject) => {
            const reader = new FileReader();
            reader.onload = e => resolve(e.target.result);
            reader.onerror = reject;
            reader.readAsDataURL(file);
        });
    }

    async function handleFiles(files) {
        if (!localStorage.getItem('muapi_key')) {
            const modal = AuthModal();
            document.body.appendChild(modal);
            return;
        }
        const remaining = Math.max(0, 8 - scenes.length);
        const toAdd = files.slice(0, remaining);
        for (const file of toAdd) {
            const dataUrl = await fileToDataUrl(file);
            addScene({ imageUrl: dataUrl, name: file.name });
        }
    }

    function addScene({ imageUrl, name }) {
        const id = ++sceneIdCounter;
        const promptIndex = (scenes.length) % DEFAULT_PROMPTS.length;
        const scene = {
            id,
            imageUrl,
            name: name || `Scene ${id}`,
            prompt: DEFAULT_PROMPTS[promptIndex],
            status: 'idle',
            videoUrl: null,
        };
        scenes.push(scene);
        renderScene(scene);
        updateScenesHeader();
    }

    function updateScenesHeader() {
        const header = document.getElementById('scenes-header');
        const count = document.getElementById('scene-count');
        if (scenes.length > 0) {
            header.classList.remove('hidden');
            count.textContent = scenes.length;
        } else {
            header.classList.add('hidden');
        }
    }

    function renderScene(scene) {
        const card = document.createElement('div');
        card.id = `scene-card-${scene.id}`;
        card.className = 'bg-[#111]/80 border border-white/5 rounded-2xl overflow-hidden flex flex-col';

        // Image / Video preview
        const previewArea = document.createElement('div');
        previewArea.className = 'relative aspect-[9/16] bg-black overflow-hidden';
        previewArea.id = `scene-preview-${scene.id}`;

        if (scene.imageUrl) {
            const img = document.createElement('img');
            img.src = scene.imageUrl;
            img.className = 'w-full h-full object-cover';
            previewArea.appendChild(img);
        } else {
            // URL input placeholder
            previewArea.innerHTML = `
                <div class="flex flex-col items-center justify-center h-full gap-2 p-4">
                    <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" class="text-muted"><rect x="3" y="3" width="18" height="18" rx="2"/><circle cx="8.5" cy="8.5" r="1.5"/><polyline points="21 15 16 10 5 21"/></svg>
                    <p class="text-muted text-xs text-center">Paste image URL below</p>
                </div>
            `;
        }

        // Status overlay
        const statusOverlay = document.createElement('div');
        statusOverlay.id = `scene-status-${scene.id}`;
        statusOverlay.className = 'absolute inset-0 hidden items-center justify-center bg-black/70 backdrop-blur-sm';
        statusOverlay.innerHTML = `
            <div class="flex flex-col items-center gap-3">
                <div class="w-8 h-8 border-2 border-primary border-t-transparent rounded-full animate-spin"></div>
                <span class="text-white text-xs font-medium">Generating...</span>
            </div>
        `;
        previewArea.appendChild(statusOverlay);

        card.appendChild(previewArea);

        // Controls
        const controls = document.createElement('div');
        controls.className = 'p-3 flex flex-col gap-2 flex-1';

        // Image URL input (for URL-based images)
        if (!scene.imageUrl) {
            const urlInput = document.createElement('input');
            urlInput.type = 'url';
            urlInput.placeholder = 'Paste image URL...';
            urlInput.className = 'w-full bg-white/5 border border-white/10 rounded-lg px-3 py-2 text-white text-xs placeholder:text-muted focus:outline-none focus:border-primary/40 transition-colors';
            urlInput.onchange = () => {
                scene.imageUrl = urlInput.value;
                const preview = document.getElementById(`scene-preview-${scene.id}`);
                const img = document.createElement('img');
                img.src = scene.imageUrl;
                img.className = 'w-full h-full object-cover absolute inset-0';
                preview.insertBefore(img, preview.firstChild);
            };
            controls.appendChild(urlInput);
        }

        // Prompt textarea
        const promptLabel = document.createElement('label');
        promptLabel.className = 'text-xs text-muted font-medium';
        promptLabel.textContent = 'Animation prompt';
        controls.appendChild(promptLabel);

        const promptArea = document.createElement('textarea');
        promptArea.className = 'w-full bg-white/5 border border-white/10 rounded-lg px-3 py-2 text-white text-xs placeholder:text-muted focus:outline-none focus:border-primary/40 transition-colors resize-none leading-relaxed';
        promptArea.rows = 3;
        promptArea.value = scene.prompt;
        promptArea.oninput = () => { scene.prompt = promptArea.value; };
        controls.appendChild(promptArea);

        // Actions row
        const actionsRow = document.createElement('div');
        actionsRow.className = 'flex items-center gap-2 mt-1';

        const genBtn = document.createElement('button');
        genBtn.id = `scene-gen-btn-${scene.id}`;
        genBtn.className = 'flex-1 flex items-center justify-center gap-2 py-2 bg-primary/10 hover:bg-primary/20 border border-primary/20 hover:border-primary/40 rounded-xl text-primary text-xs font-bold transition-all';
        genBtn.innerHTML = `
            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><polygon points="5 3 19 12 5 21 5 3"/></svg>
            Generate Clip
        `;
        genBtn.onclick = () => generateSceneClip(scene.id);
        actionsRow.appendChild(genBtn);

        const removeBtn = document.createElement('button');
        removeBtn.className = 'p-2 text-muted hover:text-red-400 transition-colors rounded-lg hover:bg-red-400/10';
        removeBtn.title = 'Remove scene';
        removeBtn.innerHTML = `<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="3 6 5 6 21 6"/><path d="M19 6l-1 14a2 2 0 01-2 2H8a2 2 0 01-2-2L5 6"/><path d="M10 11v6M14 11v6"/></svg>`;
        removeBtn.onclick = () => removeScene(scene.id);
        actionsRow.appendChild(removeBtn);

        controls.appendChild(actionsRow);
        card.appendChild(controls);
        scenesGrid.appendChild(card);
    }

    function removeScene(id) {
        scenes = scenes.filter(s => s.id !== id);
        const card = document.getElementById(`scene-card-${id}`);
        if (card) card.remove();
        updateScenesHeader();
        if (scenes.length === 0) {
            document.getElementById('reel-section').classList.add('hidden');
        }
    }

    async function generateSceneClip(id) {
        const scene = scenes.find(s => s.id === id);
        if (!scene) return;

        if (!scene.imageUrl) {
            alert('Please provide an image URL or upload an image for this scene.');
            return;
        }

        if (!scene.prompt.trim()) {
            alert('Please enter an animation prompt for this scene.');
            return;
        }

        if (!localStorage.getItem('muapi_key')) {
            const modal = AuthModal();
            document.body.appendChild(modal);
            return;
        }

        scene.status = 'generating';

        const overlay = document.getElementById(`scene-status-${id}`);
        overlay.classList.remove('hidden');
        overlay.classList.add('flex');

        const btn = document.getElementById(`scene-gen-btn-${id}`);
        if (btn) btn.disabled = true;

        try {
            const result = await muapi.generateVideoFromImage({
                model: selectedModel,
                prompt: scene.prompt,
                image_url: scene.imageUrl,
                aspect_ratio: selectedAr,
                duration: selectedDuration,
                resolution: selectedResolution,
            });

            scene.status = 'done';
            scene.videoUrl = result.url;

            overlay.classList.add('hidden');
            overlay.classList.remove('flex');

            // Replace preview with video
            const previewArea = document.getElementById(`scene-preview-${id}`);
            previewArea.innerHTML = '';
            const video = document.createElement('video');
            video.src = result.url;
            video.controls = false;
            video.autoplay = true;
            video.loop = true;
            video.muted = true;
            video.playsInline = true;
            video.className = 'w-full h-full object-cover';
            previewArea.appendChild(video);

            // Add download overlay
            const dlOverlay = document.createElement('div');
            dlOverlay.className = 'absolute inset-0 bg-black/0 hover:bg-black/40 transition-all flex items-end justify-center pb-3 opacity-0 hover:opacity-100 group';
            const dlBtn = document.createElement('a');
            dlBtn.href = result.url;
            dlBtn.download = `promo-clip-${id}.mp4`;
            dlBtn.className = 'flex items-center gap-1.5 px-3 py-1.5 bg-black/70 text-white text-xs font-medium rounded-lg backdrop-blur-sm';
            dlBtn.innerHTML = `<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><path d="M21 15v4a2 2 0 01-2 2H5a2 2 0 01-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/></svg> Download`;
            dlOverlay.appendChild(dlBtn);
            previewArea.appendChild(dlOverlay);

            // Update gen button
            if (btn) {
                btn.innerHTML = `<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><polyline points="20 6 9 17 4 12"/></svg> Done — Regenerate`;
                btn.disabled = false;
                btn.className = btn.className.replace('bg-primary/10', 'bg-green-900/20').replace('text-primary', 'text-green-400').replace('border-primary/20', 'border-green-400/20');
            }

            addToReel(scene);

        } catch (err) {
            scene.status = 'error';
            overlay.innerHTML = `
                <div class="flex flex-col items-center gap-2 p-4">
                    <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" class="text-red-400"><circle cx="12" cy="12" r="10"/><line x1="15" y1="9" x2="9" y2="15"/><line x1="9" y1="9" x2="15" y2="15"/></svg>
                    <p class="text-red-400 text-xs text-center font-medium">${err.message.slice(0, 120)}</p>
                    <button class="text-xs text-white underline" onclick="this.closest('[id^=scene-status]').classList.add('hidden')">Dismiss</button>
                </div>
            `;
            if (btn) btn.disabled = false;
        }
    }

    function addToReel(scene) {
        if (!scene.videoUrl) return;
        const reel = document.getElementById('reel-section');
        reel.classList.remove('hidden');

        const reelGrid = document.getElementById('reel-grid');
        const existing = document.getElementById(`reel-clip-${scene.id}`);
        if (existing) existing.remove();

        const clip = document.createElement('div');
        clip.id = `reel-clip-${scene.id}`;
        clip.className = 'relative rounded-2xl overflow-hidden bg-black group aspect-[9/16]';

        const video = document.createElement('video');
        video.src = scene.videoUrl;
        video.controls = false;
        video.autoplay = true;
        video.loop = true;
        video.muted = true;
        video.playsInline = true;
        video.className = 'w-full h-full object-cover';
        clip.appendChild(video);

        const info = document.createElement('div');
        info.className = 'absolute bottom-0 left-0 right-0 p-3 bg-gradient-to-t from-black/80 to-transparent translate-y-full group-hover:translate-y-0 transition-transform';
        info.innerHTML = `
            <p class="text-white text-xs font-medium mb-2 truncate">${scene.name}</p>
            <a href="${scene.videoUrl}" download="promo-clip-${scene.id}.mp4" class="inline-flex items-center gap-1.5 px-3 py-1.5 bg-primary text-black text-xs font-bold rounded-lg">
                <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3"><path d="M21 15v4a2 2 0 01-2 2H5a2 2 0 01-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/></svg>
                Download
            </a>
        `;
        clip.appendChild(info);
        reelGrid.appendChild(clip);
    }

    // Generate All button handler (wired after render)
    container.addEventListener('click', async (e) => {
        if (e.target.closest('#generate-all-btn')) {
            const pendingScenes = scenes.filter(s => s.status !== 'generating');
            for (const scene of pendingScenes) {
                await generateSceneClip(scene.id);
            }
        }
    });

    return container;
}
