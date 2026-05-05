(function () {
    'use strict';

    const config = window.DIAGRAM_EDITOR_CONFIG || {};
    const $ = (selector) => document.querySelector(selector);
    const $$ = (selector) => Array.from(document.querySelectorAll(selector));

    const SCHEMES = {
        default: { fill: '#dbeafe', stroke: '#6366f1', font: '#1e293b' },
        ocean: { fill: '#e0f2fe', stroke: '#0284c7', font: '#0c4a6e' },
        forest: { fill: '#dcfce7', stroke: '#16a34a', font: '#14532d' },
        sunset: { fill: '#ffedd5', stroke: '#ea580c', font: '#7c2d12' },
        rose: { fill: '#fce7f3', stroke: '#db2777', font: '#831843' },
        mono: { fill: '#f1f5f9', stroke: '#475569', font: '#0f172a' }
    };

    const CHIP_COLORS = [
        '#2563eb', '#7c3aed', '#db2777', '#dc2626',
        '#ea580c', '#ca8a04', '#16a34a', '#0891b2',
        '#0f766e', '#4f46e5', '#9333ea', '#334155',
        '#22c55e', '#06b6d4', '#f97316', '#64748b'
    ];

    const CANVAS_MIN_WIDTH = 2000;
    const CANVAS_MIN_HEIGHT = 1500;
    const CANVAS_PADDING = 220;

    const state = {
        diagramId: config.diagramId || null,
        xml: config.existingXml || '',
        currentScheme: (config.colorScheme || 'default').startsWith('custom:') ? 'custom' : (config.colorScheme || 'default'),
        colors: parseSavedScheme(config.colorScheme || 'default'),
        layoutDirection: config.layoutDirection || 'TB',
        zoom: 1,
        edgeType: 'orthogonal',
        connectMode: false,
        connectSource: null,
        drag: null,
        aiConfig: null,
        history: {
            undo: [],
            redo: []
        },
        local: {
            nodes: [],
            edges: [],
            backgrounds: [],
            selectedKind: null,
            selectedId: null
        }
    };

    const canvas = $('#localCanvas');
    const stageWrap = $('#stageWrap');
    const nodeLabelInput = $('#nodeLabelInput');
    let labelEditSnapshot = null;
    let colorEditSnapshot = null;

    init();

    function init() {
        initToolbar();
        initPalette();
        initCanvas();
        initImportModal();
        initColorPanel();
        loadAiConfig();

        if (state.xml && loadXmlToState(state.xml)) {
            setStatus('已加载本地流程图，可以继续拖拽编辑', 'ok');
        } else if (config.initialTemplate) {
            applyTemplate(config.initialTemplate, { skipHistory: true, silent: true });
            setStatus('已打开模板，可继续调整、连线和美化', 'ok');
        } else {
            addStarterDiagram();
            setStatus('本地独立编辑器已就绪，从左侧拖拽图形到画布', 'ok');
        }
        applyActiveSchemeMarker();
        render();
        updateHistoryButtons();
    }

    function snapshotState() {
        return {
            layoutDirection: state.layoutDirection,
            currentScheme: state.currentScheme,
            colors: Object.assign({}, state.colors),
            edgeType: state.edgeType,
            local: JSON.parse(JSON.stringify(state.local))
        };
    }

    function restoreSnapshot(snapshot) {
        if (!snapshot) return;
        state.layoutDirection = snapshot.layoutDirection || 'TB';
        state.currentScheme = snapshot.currentScheme || 'default';
        state.colors = Object.assign({}, snapshot.colors || SCHEMES.default);
        state.edgeType = snapshot.edgeType || 'orthogonal';
        state.local = JSON.parse(JSON.stringify(snapshot.local || {
            nodes: [],
            edges: [],
            backgrounds: [],
            selectedKind: null,
            selectedId: null
        }));
        applyActiveSchemeMarker();
        syncColorInputsFromColors(state.colors);
        syncEdgeTypeControl();
        render();
        updateHistoryButtons();
    }

    function pushHistory(label) {
        rememberSnapshot(snapshotState(), label);
    }

    function pushSnapshotIfChanged(snapshot, label) {
        if (!snapshot || snapshotsEqual(snapshot, snapshotState())) return;
        rememberSnapshot(snapshot, label);
    }

    function rememberSnapshot(snapshot, label) {
        const last = state.history.undo[state.history.undo.length - 1];
        if (last && snapshotsEqual(last.snapshot, snapshot)) return;
        state.history.undo.push({ label: label || '操作', snapshot });
        if (state.history.undo.length > 80) state.history.undo.shift();
        state.history.redo = [];
        updateHistoryButtons();
    }

    function snapshotsEqual(a, b) {
        return JSON.stringify(a) === JSON.stringify(b);
    }

    function undoChange() {
        const entry = state.history.undo.pop();
        if (!entry) return;
        state.history.redo.push({ label: entry.label, snapshot: snapshotState() });
        restoreSnapshot(entry.snapshot);
        setStatus('已撤回：' + entry.label, 'ok');
    }

    function redoChange() {
        const entry = state.history.redo.pop();
        if (!entry) return;
        state.history.undo.push({ label: entry.label, snapshot: snapshotState() });
        restoreSnapshot(entry.snapshot);
        setStatus('已恢复：' + entry.label, 'ok');
    }

    function updateHistoryButtons() {
        const undoBtn = $('#undoBtn');
        const redoBtn = $('#redoBtn');
        if (undoBtn) undoBtn.disabled = state.history.undo.length === 0;
        if (redoBtn) redoBtn.disabled = state.history.redo.length === 0;
    }

    function initToolbar() {
        $('#saveBtn').addEventListener('click', doSave);
        $('#layoutTBBtn').addEventListener('click', () => autoLayout('TB'));
        $('#layoutLRBtn').addEventListener('click', () => autoLayout('LR'));
        $('#beautifyBtn').addEventListener('click', beautifyDiagram);
        $('#undoBtn').addEventListener('click', undoChange);
        $('#redoBtn').addEventListener('click', redoChange);
        $('#zoomOutBtn').addEventListener('click', () => setZoom(state.zoom / 1.18));
        $('#zoomFitBtn').addEventListener('click', fitCanvas);
        $('#zoomInBtn').addEventListener('click', () => setZoom(state.zoom * 1.18));
        $('#duplicateBtn').addEventListener('click', duplicateSelected);
        $('#aiGenerateBtn').addEventListener('click', generateDiagramFromAiPrompt);

        $('#edgeTypeSelect').addEventListener('change', () => {
            state.edgeType = $('#edgeTypeSelect').value || 'orthogonal';
            const edge = getSelectedEdge();
            if (edge) {
                pushHistory('修改连线样式');
                edge.type = state.edgeType;
                render();
            } else {
                setStatus('新连线样式已切换为：' + selectedEdgeTypeLabel(), 'ok');
            }
        });

        $$('.export-btn').forEach((btn) => {
            btn.addEventListener('click', (event) => {
                event.preventDefault();
                exportDiagram(btn.dataset.fmt);
            });
        });

        document.addEventListener('keydown', (event) => {
            const tag = document.activeElement ? document.activeElement.tagName : '';
            const isField = ['INPUT', 'TEXTAREA', 'SELECT'].includes(tag);
            if ((event.ctrlKey || event.metaKey) && !isField) {
                const key = event.key.toLowerCase();
                if (key === 'z') {
                    event.preventDefault();
                    if (event.shiftKey) redoChange();
                    else undoChange();
                    return;
                }
                if (key === 'y') {
                    event.preventDefault();
                    redoChange();
                    return;
                }
            }
            if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === 's') {
                event.preventDefault();
                doSave();
            }
            if (event.key === 'Delete' || event.key === 'Backspace') {
                if (!isField) {
                    event.preventDefault();
                    deleteSelected();
                }
            }
            if (event.key === 'Escape') {
                state.connectMode = false;
                state.connectSource = null;
                $('#connectModeBtn').classList.remove('active');
                selectNone();
                render();
            }
        });
    }

    async function loadAiConfig() {
        try {
            const resp = await fetch('/api/admin/ai-config');
            if (!resp.ok) return;
            const data = await resp.json();
            state.aiConfig = (data.configs || []).find((cfg) => cfg.is_enabled) || null;
        } catch (err) {
            state.aiConfig = null;
        }
    }

    function initPalette() {
        const categorySelect = $('#shapeCategorySelect');
        if (categorySelect) {
            categorySelect.addEventListener('change', () => switchShapeCategory(categorySelect.value));
            switchShapeCategory(categorySelect.value || 'basic');
        }

        $$('.shape-tool').forEach((tool) => {
            tool.addEventListener('dragstart', (event) => {
                event.dataTransfer.setData('text/plain', tool.dataset.shape);
                event.dataTransfer.setData('application/x-scifig-shape', tool.dataset.shape);
                event.dataTransfer.effectAllowed = 'copy';
            });
            tool.addEventListener('click', () => {
                const rect = stageWrap.getBoundingClientRect();
                const x = rect.left + rect.width / 2;
                const y = rect.top + rect.height / 2;
                const point = clientToSvg({ clientX: x, clientY: y });
                addNode(tool.dataset.shape, point.x, point.y);
            });
        });

        $$('.template-tool').forEach((tool) => {
            tool.addEventListener('click', () => applyTemplate(tool.dataset.template));
        });

        stageWrap.addEventListener('dragover', (event) => {
            event.preventDefault();
            stageWrap.classList.add('dragover');
        });
        stageWrap.addEventListener('dragleave', () => stageWrap.classList.remove('dragover'));
        stageWrap.addEventListener('drop', (event) => {
            event.preventDefault();
            stageWrap.classList.remove('dragover');
            const shape = event.dataTransfer.getData('application/x-scifig-shape') || event.dataTransfer.getData('text/plain');
            if (!shape) return;
            const point = clientToSvg(event);
            addNode(shape, point.x, point.y);
        });

        $('#connectModeBtn').addEventListener('click', () => {
            state.connectMode = !state.connectMode;
            state.connectSource = null;
            $('#connectModeBtn').classList.toggle('active', state.connectMode);
            setStatus(state.connectMode ? '连线模式：依次点击两个图形创建箭头' : '已退出连线模式', 'ok');
            render();
        });
        $('#deleteSelectedBtn').addEventListener('click', deleteSelected);
        $('#clearCanvasBtn').addEventListener('click', clearCanvas);

        if (nodeLabelInput) {
            nodeLabelInput.addEventListener('focus', () => {
                if (getSelectedNode()) labelEditSnapshot = snapshotState();
            });
            nodeLabelInput.addEventListener('input', () => {
                const node = getSelectedNode();
                if (!node) return;
                node.label = nodeLabelInput.value;
                render(false);
            });
            nodeLabelInput.addEventListener('change', () => {
                pushSnapshotIfChanged(labelEditSnapshot, '编辑文字');
                labelEditSnapshot = null;
                updateXmlSnapshot();
                updateHistoryButtons();
            });
        }
    }

    function switchShapeCategory(name) {
        $$('.shape-group').forEach((item) => item.classList.remove('active'));
        const group = document.querySelector('[data-shape-group="' + name + '"]');
        if (group) group.classList.add('active');
    }

    function initCanvas() {
        setZoom(1, false);
        canvas.addEventListener('pointerdown', (event) => {
            if (event.target === canvas || event.target.classList.contains('canvas-bg')) {
                selectNone();
                render();
            }
        });
        window.addEventListener('pointermove', (event) => {
            if (!state.drag) return;
            const node = getNode(state.drag.id);
            if (!node) return;
            const point = clientToSvg(event);
            state.drag.moved = true;
            node.x = Math.round(point.x - state.drag.offsetX);
            node.y = Math.round(point.y - state.drag.offsetY);
            render(false);
        });
        window.addEventListener('pointerup', () => {
            if (state.drag) {
                const drag = state.drag;
                state.drag = null;
                if (drag.moved) pushSnapshotIfChanged(drag.before, '移动图形');
                updateXmlSnapshot();
                updateHistoryButtons();
            }
        });
        stageWrap.addEventListener('wheel', (event) => {
            if (!event.ctrlKey && !event.metaKey) return;
            event.preventDefault();
            const factor = event.deltaY < 0 ? 1.12 : 1 / 1.12;
            setZoom(state.zoom * factor, true, { clientX: event.clientX, clientY: event.clientY });
        }, { passive: false });
    }

    function initImportModal() {
        const importTabBtns = $$('.import-tab-btn');
        importTabBtns.forEach((btn) => {
            btn.addEventListener('click', () => {
                importTabBtns.forEach((item) => item.classList.remove('active'));
                btn.classList.add('active');
                $('#importTabFile').style.display = btn.dataset.tab === 'file' ? '' : 'none';
                $('#importTabImage').style.display = btn.dataset.tab === 'image' ? '' : 'none';
            });
        });

        initDropZone({
            zone: $('#fileDropZone'),
            input: $('#fileInput'),
            browse: $('#fileBrowseLink'),
            handler: handleFileSelect
        });

        initDropZone({
            zone: $('#imageDropZone'),
            input: $('#imageInput'),
            browse: $('#imageBrowseLink'),
            handler: handleImageSelect
        });

        $('#fileImportConfirm').addEventListener('click', importSelectedFile);
        $('#imageAsBackground').addEventListener('click', importImageAsBackground);
        $('#imageToShapes').addEventListener('click', recognizeImageToShapes);
    }

    function initDropZone(options) {
        options.browse.addEventListener('click', (event) => {
            event.preventDefault();
            options.input.click();
        });
        options.zone.addEventListener('click', (event) => {
            if (event.target.tagName !== 'A') options.input.click();
        });
        options.zone.addEventListener('dragover', (event) => {
            event.preventDefault();
            options.zone.classList.add('dragover');
        });
        options.zone.addEventListener('dragleave', () => options.zone.classList.remove('dragover'));
        options.zone.addEventListener('drop', (event) => {
            event.preventDefault();
            options.zone.classList.remove('dragover');
            if (event.dataTransfer.files.length) options.handler(event.dataTransfer.files[0]);
        });
        options.input.addEventListener('change', () => {
            if (options.input.files.length) options.handler(options.input.files[0]);
        });
    }

    function initColorPanel() {
        const panel = $('#colorPanel');
        const customBtn = $('#customColorBtn');
        customBtn.addEventListener('click', (event) => {
            event.stopPropagation();
            panel.classList.toggle('show');
        });
        panel.addEventListener('click', (event) => event.stopPropagation());
        document.addEventListener('click', () => panel.classList.remove('show'));

        $$('.color-swatch').forEach((swatch) => {
            swatch.addEventListener('click', () => {
                const before = snapshotState();
                state.currentScheme = swatch.dataset.scheme;
                state.colors = Object.assign({}, SCHEMES[state.currentScheme]);
                applyActiveSchemeMarker();
                syncColorInputsFromColors(state.colors);
                applyColorsToAll(state.colors);
                pushSnapshotIfChanged(before, '切换配色');
                setStatus('已应用配色：' + swatch.title, 'ok');
            });
        });

        const chipGrid = $('#colorChipGrid');
        CHIP_COLORS.forEach((color) => {
            const chip = document.createElement('button');
            chip.type = 'button';
            chip.className = 'color-chip';
            chip.style.background = color;
            chip.title = color;
            chip.addEventListener('click', () => {
                const hsl = hexToHsl(color);
                $('#hueRange').value = String(Math.round(hsl.h));
                $('#satRange').value = String(Math.round(hsl.s));
                $('#lightRange').value = String(Math.round(hsl.l));
                updateCustomColorsFromSliders(true);
            });
            chipGrid.appendChild(chip);
        });

        ['hueRange', 'satRange', 'lightRange'].forEach((id) => {
            const range = $('#' + id);
            range.addEventListener('pointerdown', () => {
                colorEditSnapshot = colorEditSnapshot || snapshotState();
            });
            range.addEventListener('focus', () => {
                colorEditSnapshot = colorEditSnapshot || snapshotState();
            });
            range.addEventListener('input', () => updateCustomColorsFromSliders(true));
            range.addEventListener('change', () => {
                pushSnapshotIfChanged(colorEditSnapshot, '滑动调色');
                colorEditSnapshot = null;
            });
        });
        ['fillHex', 'strokeHex', 'fontHex'].forEach((id) => {
            $('#' + id).addEventListener('change', () => {
                const before = snapshotState();
                const fill = normalizeHex($('#fillHex').value) || state.colors.fill;
                const stroke = normalizeHex($('#strokeHex').value) || state.colors.stroke;
                const font = normalizeHex($('#fontHex').value) || state.colors.font;
                state.currentScheme = 'custom';
                state.colors = { fill, stroke, font };
                syncColorInputsFromColors(state.colors);
                applyActiveSchemeMarker();
                applyColorsToAll(state.colors);
                pushSnapshotIfChanged(before, '输入配色编码');
            });
        });
        $('#applyCustomColor').addEventListener('click', () => {
            const before = colorEditSnapshot || snapshotState();
            updateCustomColorsFromSliders(true);
            pushSnapshotIfChanged(before, '应用自定义配色');
            colorEditSnapshot = null;
            panel.classList.remove('show');
        });

        syncColorInputsFromColors(state.colors);
    }

    function addStarterDiagram() {
        const colors = state.colors;
        state.local.nodes = [
            makeNode('terminator', 610, 120, '开始', 160, 50, colors),
            makeNode('process', 590, 220, '处理步骤', 200, 62, colors),
            makeNode('decision', 610, 340, '判断条件', 160, 90, colors),
            makeNode('terminator', 610, 500, '结束', 160, 50, colors)
        ];
        state.local.edges = [
            makeEdge(state.local.nodes[0].id, state.local.nodes[1].id),
            makeEdge(state.local.nodes[1].id, state.local.nodes[2].id),
            makeEdge(state.local.nodes[2].id, state.local.nodes[3].id)
        ];
        state.local.backgrounds = [];
    }

    function render(updateXml) {
        const shouldUpdateXml = updateXml !== false;
        updateCanvasSize();
        const arrowColor = state.colors.stroke || '#475569';
        const defs = [
            '<defs>',
            '<marker id="arrowHead" markerWidth="10" markerHeight="10" refX="9" refY="3" orient="auto" markerUnits="strokeWidth">',
            '<path d="M0,0 L0,6 L9,3 z" fill="' + escapeAttr(arrowColor) + '"></path>',
            '</marker>',
            '<marker id="arrowStart" markerWidth="10" markerHeight="10" refX="1" refY="3" orient="auto" markerUnits="strokeWidth">',
            '<path d="M9,0 L9,6 L0,3 z" fill="' + escapeAttr(arrowColor) + '"></path>',
            '</marker>',
            '</defs>'
        ].join('');
        const backgrounds = state.local.backgrounds.map(backgroundSvg).join('');
        const edges = state.local.edges.map(edgeSvg).join('');
        const nodes = state.local.nodes.map(nodeSvg).join('');
        canvas.innerHTML = defs + backgrounds + edges + nodes;
        bindRenderedElements();
        updateSelectionInspector();
        syncEdgeTypeControl();
        updateHistoryButtons();
        if (shouldUpdateXml) updateXmlSnapshot();
    }

    function bindRenderedElements() {
        canvas.querySelectorAll('.diagram-node').forEach((element) => {
            element.addEventListener('pointerdown', onNodePointerDown);
            element.addEventListener('dblclick', onNodeDoubleClick);
        });
        canvas.querySelectorAll('.diagram-edge').forEach((element) => {
            element.addEventListener('pointerdown', (event) => {
                event.stopPropagation();
                state.local.selectedKind = 'edge';
                state.local.selectedId = element.dataset.edgeId;
                const edge = getSelectedEdge();
                if (edge) state.edgeType = edge.type || 'orthogonal';
                render();
            });
        });
    }

    function backgroundSvg(bg) {
        return [
            '<image class="canvas-bg" href="', escapeAttr(bg.href), '" x="', bg.x, '" y="', bg.y,
            '" width="', bg.width, '" height="', bg.height,
            '" opacity="', bg.opacity, '" preserveAspectRatio="xMidYMid meet"></image>'
        ].join('');
    }

    function nodeSvg(node) {
        const selected = state.local.selectedKind === 'node' && state.local.selectedId === node.id;
        const fill = node.type === 'text' ? 'transparent' : node.fill;
        const stroke = node.type === 'text' ? (selected ? node.stroke : 'transparent') : node.stroke;
        const shape = shapeSvg(node, fill, stroke);
        const text = labelSvg(node);
        return [
            '<g class="diagram-node', selected ? ' selected' : '', '" data-node-id="', node.id, '">',
            shape,
            text,
            '</g>'
        ].join('');
    }

    function shapeSvg(node, fill, stroke) {
        const attrs = ' class="node-shape" fill="' + escapeAttr(fill) + '" stroke="' + escapeAttr(stroke) + '" stroke-width="2"';
        if (node.type === 'decision') {
            const cx = node.x + node.width / 2;
            const cy = node.y + node.height / 2;
            const points = [
                [cx, node.y],
                [node.x + node.width, cy],
                [cx, node.y + node.height],
                [node.x, cy]
            ].map((point) => point.join(',')).join(' ');
            return '<polygon' + attrs + ' points="' + points + '"></polygon>';
        }
        if (node.type === 'preparation') {
            const cut = Math.min(34, node.width * 0.18);
            const points = [
                [node.x + cut, node.y],
                [node.x + node.width - cut, node.y],
                [node.x + node.width, node.y + node.height / 2],
                [node.x + node.width - cut, node.y + node.height],
                [node.x + cut, node.y + node.height],
                [node.x, node.y + node.height / 2]
            ].map((point) => point.join(',')).join(' ');
            return '<polygon' + attrs + ' points="' + points + '"></polygon>';
        }
        if (node.type === 'data') {
            const skew = Math.min(28, node.width * 0.18);
            const points = [
                [node.x + skew, node.y],
                [node.x + node.width, node.y],
                [node.x + node.width - skew, node.y + node.height],
                [node.x, node.y + node.height]
            ].map((point) => point.join(',')).join(' ');
            return '<polygon' + attrs + ' points="' + points + '"></polygon>';
        }
        if (node.type === 'manualInput') {
            const skew = Math.min(26, node.height * 0.32);
            const points = [
                [node.x, node.y + skew],
                [node.x + node.width, node.y],
                [node.x + node.width, node.y + node.height],
                [node.x, node.y + node.height]
            ].map((point) => point.join(',')).join(' ');
            return '<polygon' + attrs + ' points="' + points + '"></polygon>';
        }
        if (node.type === 'document' || node.type === 'paper') {
            const wave = Math.min(18, node.height * 0.24);
            return '<path' + attrs + ' d="M' + node.x + ',' + node.y + ' H' + (node.x + node.width) + ' V' + (node.y + node.height - wave) +
                ' Q' + (node.x + node.width * 0.75) + ',' + (node.y + node.height + wave) + ' ' + (node.x + node.width * 0.5) + ',' + (node.y + node.height - wave / 2) +
                ' Q' + (node.x + node.width * 0.25) + ',' + (node.y + node.height - wave * 2) + ' ' + node.x + ',' + (node.y + node.height - wave / 2) + ' Z"></path>';
        }
        if (node.type === 'multiDocument') {
            return '<rect' + attrs + ' x="' + (node.x + 10) + '" y="' + node.y + '" width="' + (node.width - 10) + '" height="' + (node.height - 10) + '" rx="6"></rect>' +
                '<rect' + attrs + ' x="' + node.x + '" y="' + (node.y + 10) + '" width="' + (node.width - 10) + '" height="' + (node.height - 10) + '" rx="6"></rect>';
        }
        if (node.type === 'dataset') {
            const ry = Math.min(16, node.height * 0.22);
            const rows = 3;
            let marks = '';
            for (let i = 0; i < rows; i++) {
                const y = node.y + 24 + i * 14;
                marks += '<circle cx="' + (node.x + 20) + '" cy="' + y + '" r="3.5" fill="' + escapeAttr(stroke) + '"></circle>' +
                    '<line x1="' + (node.x + 32) + '" y1="' + y + '" x2="' + (node.x + node.width - 18) + '" y2="' + y + '" stroke="' + escapeAttr(stroke) + '" stroke-width="1.5" stroke-linecap="round"></line>';
            }
            return '<path' + attrs + ' d="M' + node.x + ',' + (node.y + ry) + ' C' + node.x + ',' + (node.y - ry / 2) + ' ' + (node.x + node.width) + ',' + (node.y - ry / 2) + ' ' + (node.x + node.width) + ',' + (node.y + ry) +
                ' V' + (node.y + node.height - ry) + ' C' + (node.x + node.width) + ',' + (node.y + node.height + ry / 2) + ' ' + node.x + ',' + (node.y + node.height + ry / 2) + ' ' + node.x + ',' + (node.y + node.height - ry) + ' Z"></path>' +
                '<ellipse cx="' + (node.x + node.width / 2) + '" cy="' + (node.y + ry) + '" rx="' + (node.width / 2) + '" ry="' + ry + '" fill="none" stroke="' + escapeAttr(stroke) + '" stroke-width="2"></ellipse>' + marks;
        }
        if (node.type === 'cache') {
            return '<rect' + attrs + ' x="' + node.x + '" y="' + node.y + '" width="' + node.width + '" height="' + node.height + '" rx="14"></rect>' +
                '<path d="M' + (node.x + node.width * 0.52) + ',' + (node.y + 10) + ' L' + (node.x + node.width * 0.38) + ',' + (node.y + node.height * 0.5) + ' H' + (node.x + node.width * 0.54) + ' L' + (node.x + node.width * 0.44) + ',' + (node.y + node.height - 10) + ' L' + (node.x + node.width * 0.66) + ',' + (node.y + node.height * 0.38) + ' H' + (node.x + node.width * 0.5) + ' Z" fill="' + escapeAttr(stroke) + '"></path>';
        }
        if (node.type === 'database' || node.type === 'storedData') {
            const ry = Math.min(18, node.height * 0.24);
            return '<path' + attrs + ' d="M' + node.x + ',' + (node.y + ry) + ' C' + node.x + ',' + (node.y - ry / 2) + ' ' + (node.x + node.width) + ',' + (node.y - ry / 2) + ' ' + (node.x + node.width) + ',' + (node.y + ry) +
                ' V' + (node.y + node.height - ry) + ' C' + (node.x + node.width) + ',' + (node.y + node.height + ry / 2) + ' ' + node.x + ',' + (node.y + node.height + ry / 2) + ' ' + node.x + ',' + (node.y + node.height - ry) + ' Z"></path>' +
                '<ellipse cx="' + (node.x + node.width / 2) + '" cy="' + (node.y + ry) + '" rx="' + (node.width / 2) + '" ry="' + ry + '" fill="none" stroke="' + escapeAttr(stroke) + '" stroke-width="2"></ellipse>';
        }
        if (node.type === 'queue') {
            return '<rect' + attrs + ' x="' + node.x + '" y="' + node.y + '" width="' + node.width + '" height="' + node.height + '" rx="8"></rect>' +
                '<line x1="' + (node.x + 16) + '" y1="' + (node.y + 18) + '" x2="' + (node.x + node.width - 16) + '" y2="' + (node.y + 18) + '" stroke="' + escapeAttr(stroke) + '" stroke-width="2" stroke-linecap="round"></line>' +
                '<line x1="' + (node.x + 16) + '" y1="' + (node.y + node.height * 0.5) + '" x2="' + (node.x + node.width - 16) + '" y2="' + (node.y + node.height * 0.5) + '" stroke="' + escapeAttr(stroke) + '" stroke-width="2" stroke-linecap="round"></line>' +
                '<line x1="' + (node.x + 16) + '" y1="' + (node.y + node.height - 18) + '" x2="' + (node.x + node.width - 16) + '" y2="' + (node.y + node.height - 18) + '" stroke="' + escapeAttr(stroke) + '" stroke-width="2" stroke-linecap="round"></line>' +
                '<path d="M' + (node.x + node.width - 28) + ',' + (node.y + node.height * 0.35) + ' L' + (node.x + node.width - 16) + ',' + (node.y + node.height * 0.5) + ' L' + (node.x + node.width - 28) + ',' + (node.y + node.height * 0.65) + '" fill="none" stroke="' + escapeAttr(stroke) + '" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"></path>';
        }
        if (node.type === 'internalStorage') {
            return '<rect' + attrs + ' x="' + node.x + '" y="' + node.y + '" width="' + node.width + '" height="' + node.height + '" rx="6"></rect>' +
                '<line x1="' + (node.x + node.width * 0.22) + '" y1="' + node.y + '" x2="' + (node.x + node.width * 0.22) + '" y2="' + (node.y + node.height) + '" stroke="' + escapeAttr(stroke) + '" stroke-width="2"></line>' +
                '<line x1="' + node.x + '" y1="' + (node.y + node.height * 0.28) + '" x2="' + (node.x + node.width) + '" y2="' + (node.y + node.height * 0.28) + '" stroke="' + escapeAttr(stroke) + '" stroke-width="2"></line>';
        }
        if (node.type === 'delay') {
            return '<path' + attrs + ' d="M' + node.x + ',' + node.y + ' H' + (node.x + node.width - node.height / 2) +
                ' A' + (node.height / 2) + ',' + (node.height / 2) + ' 0 0 1 ' + (node.x + node.width - node.height / 2) + ',' + (node.y + node.height) +
                ' H' + node.x + ' Z"></path>';
        }
        if (node.type === 'connector' || node.type === 'metric') {
            return '<ellipse' + attrs + ' cx="' + (node.x + node.width / 2) + '" cy="' + (node.y + node.height / 2) + '" rx="' + (node.width / 2) + '" ry="' + (node.height / 2) + '"></ellipse>';
        }
        if (node.type === 'offpage') {
            const notch = Math.min(28, node.height * 0.35);
            const points = [
                [node.x, node.y],
                [node.x + node.width, node.y],
                [node.x + node.width, node.y + node.height - notch],
                [node.x + node.width / 2, node.y + node.height],
                [node.x, node.y + node.height - notch]
            ].map((point) => point.join(',')).join(' ');
            return '<polygon' + attrs + ' points="' + points + '"></polygon>';
        }
        if (node.type === 'display') {
            return '<path' + attrs + ' d="M' + (node.x + 18) + ',' + node.y + ' H' + (node.x + node.width - 12) +
                ' Q' + (node.x + node.width) + ',' + (node.y + node.height / 2) + ' ' + (node.x + node.width - 12) + ',' + (node.y + node.height) +
                ' H' + (node.x + 18) + ' Q' + node.x + ',' + (node.y + node.height / 2) + ' ' + (node.x + 18) + ',' + node.y + ' Z"></path>';
        }
        if (node.type === 'subroutine') {
            return '<rect' + attrs + ' x="' + node.x + '" y="' + node.y + '" width="' + node.width + '" height="' + node.height + '" rx="8"></rect>' +
                '<line x1="' + (node.x + 18) + '" y1="' + node.y + '" x2="' + (node.x + 18) + '" y2="' + (node.y + node.height) + '" stroke="' + escapeAttr(stroke) + '" stroke-width="2"></line>' +
                '<line x1="' + (node.x + node.width - 18) + '" y1="' + node.y + '" x2="' + (node.x + node.width - 18) + '" y2="' + (node.y + node.height) + '" stroke="' + escapeAttr(stroke) + '" stroke-width="2"></line>';
        }
        if (node.type === 'model') {
            const cx = node.x + node.width - 28;
            const cy = node.y + node.height / 2;
            return '<rect' + attrs + ' x="' + node.x + '" y="' + node.y + '" width="' + node.width + '" height="' + node.height + '" rx="10"></rect>' +
                '<circle cx="' + cx + '" cy="' + cy + '" r="13" fill="none" stroke="' + escapeAttr(stroke) + '" stroke-width="2"></circle>' +
                '<circle cx="' + (cx - 22) + '" cy="' + (cy - 11) + '" r="5" fill="' + escapeAttr(stroke) + '"></circle>' +
                '<circle cx="' + (cx - 22) + '" cy="' + (cy + 11) + '" r="5" fill="' + escapeAttr(stroke) + '"></circle>' +
                '<line x1="' + (cx - 17) + '" y1="' + (cy - 11) + '" x2="' + (cx - 10) + '" y2="' + (cy - 5) + '" stroke="' + escapeAttr(stroke) + '" stroke-width="1.8"></line>' +
                '<line x1="' + (cx - 17) + '" y1="' + (cy + 11) + '" x2="' + (cx - 10) + '" y2="' + (cy + 5) + '" stroke="' + escapeAttr(stroke) + '" stroke-width="1.8"></line>';
        }
        if (node.type === 'code') {
            return '<rect' + attrs + ' x="' + node.x + '" y="' + node.y + '" width="' + node.width + '" height="' + node.height + '" rx="8"></rect>' +
                '<path d="M' + (node.x + 22) + ',' + (node.y + node.height * 0.35) + ' L' + (node.x + 12) + ',' + (node.y + node.height * 0.5) + ' L' + (node.x + 22) + ',' + (node.y + node.height * 0.65) + ' M' + (node.x + node.width - 22) + ',' + (node.y + node.height * 0.35) + ' L' + (node.x + node.width - 12) + ',' + (node.y + node.height * 0.5) + ' L' + (node.x + node.width - 22) + ',' + (node.y + node.height * 0.65) + ' M' + (node.x + node.width - 42) + ',' + (node.y + 14) + ' L' + (node.x + node.width - 58) + ',' + (node.y + node.height - 14) + '" fill="none" stroke="' + escapeAttr(stroke) + '" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"></path>';
        }
        if (node.type === 'api') {
            return '<rect' + attrs + ' x="' + node.x + '" y="' + node.y + '" width="' + node.width + '" height="' + node.height + '" rx="8"></rect>' +
                '<circle cx="' + (node.x + 28) + '" cy="' + (node.y + node.height / 2) + '" r="8" fill="none" stroke="' + escapeAttr(stroke) + '" stroke-width="2"></circle>' +
                '<circle cx="' + (node.x + node.width - 28) + '" cy="' + (node.y + node.height / 2) + '" r="8" fill="none" stroke="' + escapeAttr(stroke) + '" stroke-width="2"></circle>' +
                '<line x1="' + (node.x + 36) + '" y1="' + (node.y + node.height / 2) + '" x2="' + (node.x + node.width - 36) + '" y2="' + (node.y + node.height / 2) + '" stroke="' + escapeAttr(stroke) + '" stroke-width="2" stroke-linecap="round"></line>';
        }
        if (node.type === 'service') {
            const cx = node.x + node.width - 28;
            const cy = node.y + node.height / 2;
            return '<rect' + attrs + ' x="' + node.x + '" y="' + node.y + '" width="' + node.width + '" height="' + node.height + '" rx="10"></rect>' +
                '<circle cx="' + cx + '" cy="' + cy + '" r="13" fill="none" stroke="' + escapeAttr(stroke) + '" stroke-width="2"></circle>' +
                '<circle cx="' + (cx - 16) + '" cy="' + (cy - 14) + '" r="7" fill="none" stroke="' + escapeAttr(stroke) + '" stroke-width="2"></circle>' +
                '<circle cx="' + (cx - 16) + '" cy="' + (cy + 14) + '" r="7" fill="none" stroke="' + escapeAttr(stroke) + '" stroke-width="2"></circle>';
        }
        if (node.type === 'server') {
            return '<rect' + attrs + ' x="' + node.x + '" y="' + node.y + '" width="' + node.width + '" height="' + node.height + '" rx="8"></rect>' +
                '<line x1="' + (node.x + 12) + '" y1="' + (node.y + 22) + '" x2="' + (node.x + node.width - 12) + '" y2="' + (node.y + 22) + '" stroke="' + escapeAttr(stroke) + '" stroke-width="2"></line>' +
                '<circle cx="' + (node.x + node.width - 22) + '" cy="' + (node.y + 11) + '" r="3" fill="' + escapeAttr(stroke) + '"></circle>';
        }
        if (node.type === 'web') {
            return '<rect' + attrs + ' x="' + node.x + '" y="' + node.y + '" width="' + node.width + '" height="' + node.height + '" rx="8"></rect>' +
                '<line x1="' + node.x + '" y1="' + (node.y + 22) + '" x2="' + (node.x + node.width) + '" y2="' + (node.y + 22) + '" stroke="' + escapeAttr(stroke) + '" stroke-width="2"></line>' +
                '<circle cx="' + (node.x + 12) + '" cy="' + (node.y + 11) + '" r="2.6" fill="' + escapeAttr(stroke) + '"></circle>' +
                '<circle cx="' + (node.x + 22) + '" cy="' + (node.y + 11) + '" r="2.6" fill="' + escapeAttr(stroke) + '"></circle>';
        }
        if (node.type === 'mobile') {
            return '<rect' + attrs + ' x="' + node.x + '" y="' + node.y + '" width="' + node.width + '" height="' + node.height + '" rx="16"></rect>' +
                '<line x1="' + (node.x + node.width * 0.36) + '" y1="' + (node.y + 10) + '" x2="' + (node.x + node.width * 0.64) + '" y2="' + (node.y + 10) + '" stroke="' + escapeAttr(stroke) + '" stroke-width="2" stroke-linecap="round"></line>' +
                '<circle cx="' + (node.x + node.width / 2) + '" cy="' + (node.y + node.height - 10) + '" r="3" fill="' + escapeAttr(stroke) + '"></circle>';
        }
        if (node.type === 'message') {
            return '<rect' + attrs + ' x="' + node.x + '" y="' + node.y + '" width="' + node.width + '" height="' + node.height + '" rx="8"></rect>' +
                '<polyline points="' + node.x + ',' + (node.y + 8) + ' ' + (node.x + node.width / 2) + ',' + (node.y + node.height * 0.58) + ' ' + (node.x + node.width) + ',' + (node.y + 8) + '" fill="none" stroke="' + escapeAttr(stroke) + '" stroke-width="2"></polyline>';
        }
        if (node.type === 'note') {
            const fold = Math.min(20, node.width * 0.18, node.height * 0.32);
            const points = [
                [node.x, node.y],
                [node.x + node.width - fold, node.y],
                [node.x + node.width, node.y + fold],
                [node.x + node.width, node.y + node.height],
                [node.x, node.y + node.height]
            ].map((point) => point.join(',')).join(' ');
            return '<polygon' + attrs + ' points="' + points + '"></polygon><polyline points="' +
                (node.x + node.width - fold) + ',' + node.y + ' ' + (node.x + node.width - fold) + ',' + (node.y + fold) + ' ' +
                (node.x + node.width) + ',' + (node.y + fold) + '" fill="none" stroke="' + escapeAttr(stroke) + '" stroke-width="1.5"></polyline>';
        }
        if (node.type === 'callout') {
            const tailX = node.x + node.width * 0.28;
            const tailY = node.y + node.height + 18;
            return '<path' + attrs + ' d="M' + (node.x + 8) + ',' + node.y + ' H' + (node.x + node.width - 8) + ' Q' + (node.x + node.width) + ',' + node.y + ' ' + (node.x + node.width) + ',' + (node.y + 8) +
                ' V' + (node.y + node.height - 8) + ' Q' + (node.x + node.width) + ',' + (node.y + node.height) + ' ' + (node.x + node.width - 8) + ',' + (node.y + node.height) +
                ' H' + (node.x + node.width * 0.42) + ' L' + tailX + ',' + tailY + ' L' + (node.x + node.width * 0.32) + ',' + (node.y + node.height) +
                ' H' + (node.x + 8) + ' Q' + node.x + ',' + (node.y + node.height) + ' ' + node.x + ',' + (node.y + node.height - 8) + ' V' + (node.y + 8) + ' Q' + node.x + ',' + node.y + ' ' + (node.x + 8) + ',' + node.y + ' Z"></path>';
        }
        if (node.type === 'tag') {
            const cut = Math.min(24, node.width * 0.18);
            const cy = node.y + node.height / 2;
            return '<path' + attrs + ' d="M' + node.x + ',' + cy + ' L' + (node.x + cut) + ',' + node.y + ' H' + (node.x + node.width) + ' V' + (node.y + node.height) + ' H' + (node.x + cut) + ' Z"></path>' +
                '<circle cx="' + (node.x + cut) + '" cy="' + cy + '" r="3.5" fill="' + escapeAttr(stroke) + '"></circle>';
        }
        if (node.type === 'cloud') {
            return '<path' + attrs + ' d="M' + (node.x + 34) + ',' + (node.y + node.height * 0.72) +
                ' C' + (node.x + 8) + ',' + (node.y + node.height * 0.72) + ' ' + (node.x + 8) + ',' + (node.y + node.height * 0.42) + ' ' + (node.x + 34) + ',' + (node.y + node.height * 0.42) +
                ' C' + (node.x + 42) + ',' + (node.y + 8) + ' ' + (node.x + 86) + ',' + (node.y + 6) + ' ' + (node.x + 96) + ',' + (node.y + node.height * 0.38) +
                ' C' + (node.x + 132) + ',' + (node.y + node.height * 0.34) + ' ' + (node.x + 144) + ',' + (node.y + node.height * 0.72) + ' ' + (node.x + 110) + ',' + (node.y + node.height * 0.72) + ' Z"></path>';
        }
        if (node.type === 'person') {
            const cx = node.x + node.width / 2;
            return '<circle' + attrs + ' cx="' + cx + '" cy="' + (node.y + 22) + '" r="16"></circle>' +
                '<path' + attrs + ' d="M' + (node.x + 20) + ',' + (node.y + node.height) + ' C' + (node.x + 28) + ',' + (node.y + 50) + ' ' + (node.x + node.width - 28) + ',' + (node.y + 50) + ' ' + (node.x + node.width - 20) + ',' + (node.y + node.height) + ' Z"></path>';
        }
        if (node.type === 'training') {
            const barW = 6;
            return '<rect' + attrs + ' x="' + node.x + '" y="' + node.y + '" width="' + node.width + '" height="' + node.height + '" rx="8"></rect>' +
                '<line x1="' + (node.x + node.width - 18) + '" y1="' + (node.y + 10) + '" x2="' + (node.x + node.width - 18) + '" y2="' + (node.y + node.height - 10) + '" stroke="' + escapeAttr(fill) + '" stroke-width="' + barW + '" stroke-linecap="round"></line>' +
                '<line x1="' + (node.x + node.width - 30) + '" y1="' + (node.y + node.height * 0.4) + '" x2="' + (node.x + node.width - 30) + '" y2="' + (node.y + node.height - 10) + '" stroke="' + escapeAttr(fill) + '" stroke-width="' + barW + '" stroke-linecap="round"></line>';
        }
        if (node.type === 'evaluation') {
            return '<rect' + attrs + ' x="' + node.x + '" y="' + node.y + '" width="' + node.width + '" height="' + node.height + '" rx="8"></rect>' +
                '<rect x="' + (node.x + 10) + '" y="' + (node.y + 6) + '" width="' + (node.width - 20) + '" height="' + (node.height * 0.28) + '" rx="4" fill="' + escapeAttr(fill) + '" stroke="' + escapeAttr(stroke) + '" stroke-width="1.5"></rect>' +
                '<line x1="' + (node.x + 14) + '" y1="' + (node.y + node.height * 0.45) + '" x2="' + (node.x + node.width - 14) + '" y2="' + (node.y + node.height * 0.45) + '" stroke="' + escapeAttr(stroke) + '" stroke-width="1.5"></line>' +
                '<line x1="' + (node.x + 14) + '" y1="' + (node.y + node.height * 0.62) + '" x2="' + (node.x + node.width * 0.6) + '" y2="' + (node.y + node.height * 0.62) + '" stroke="' + escapeAttr(stroke) + '" stroke-width="1.5"></line>';
        }
        if (node.type === 'experiment') {
            return '<rect' + attrs + ' x="' + node.x + '" y="' + node.y + '" width="' + node.width + '" height="' + node.height + '" rx="8"></rect>' +
                '<circle cx="' + (node.x + 14) + '" cy="' + (node.y + node.height - 14) + '" r="5" fill="' + escapeAttr(stroke) + '"></circle>' +
                '<circle cx="' + (node.x + 26) + '" cy="' + (node.y + node.height - 14) + '" r="5" fill="' + escapeAttr(stroke) + '"></circle>' +
                '<circle cx="' + (node.x + 38) + '" cy="' + (node.y + node.height - 14) + '" r="5" fill="' + escapeAttr(stroke) + '"></circle>';
        }
        if (node.type === 'loss') {
            return '<rect' + attrs + ' x="' + node.x + '" y="' + node.y + '" width="' + node.width + '" height="' + node.height + '" rx="8"></rect>' +
                '<polyline points="' + (node.x + 14) + ',' + (node.y + node.height * 0.3) + ' ' + (node.x + node.width * 0.5) + ',' + (node.y + node.height * 0.7) + ' ' + (node.x + node.width - 14) + ',' + (node.y + node.height * 0.35) + '" fill="none" stroke="' + escapeAttr(stroke) + '" stroke-width="2" stroke-linecap="round"></polyline>';
        }
        if (node.type === 'optimizer') {
            return '<rect' + attrs + ' x="' + node.x + '" y="' + node.y + '" width="' + node.width + '" height="' + node.height + '" rx="8"></rect>' +
                '<line x1="' + (node.x + 12) + '" y1="' + (node.y + node.height * 0.35) + '" x2="' + (node.x + node.width - 12) + '" y2="' + (node.y + node.height * 0.35) + '" stroke="' + escapeAttr(stroke) + '" stroke-width="1.5"></line>' +
                '<circle cx="' + (node.x + node.width * 0.5) + '" cy="' + (node.y + node.height * 0.35) + '" r="4" fill="' + escapeAttr(stroke) + '" stroke="' + escapeAttr(stroke) + '" stroke-width="1.5"></circle>' +
                '<line x1="' + (node.x + 12) + '" y1="' + (node.y + node.height * 0.65) + '" x2="' + (node.x + node.width - 12) + '" y2="' + (node.y + node.height * 0.65) + '" stroke="' + escapeAttr(stroke) + '" stroke-width="1.5"></line>' +
                '<circle cx="' + (node.x + node.width * 0.3) + '" cy="' + (node.y + node.height * 0.65) + '" r="4" fill="' + escapeAttr(stroke) + '" stroke="' + escapeAttr(stroke) + '" stroke-width="1.5"></circle>';
        }
        if (node.type === 'augment') {
            return '<rect' + attrs + ' x="' + node.x + '" y="' + node.y + '" width="' + node.width + '" height="' + node.height + '" rx="8"></rect>' +
                '<path d="M' + (node.x + 12) + ',' + (node.y + node.height * 0.45) + ' A8,8 0 1 1 ' + (node.x + 12) + ',' + (node.y + node.height * 0.45 - 0.01) + '" fill="none" stroke="' + escapeAttr(stroke) + '" stroke-width="2" stroke-linecap="round"></path>' +
                '<line x1="' + (node.x + 12) + '" y1="' + (node.y + node.height * 0.3) + '" x2="' + (node.x + 12) + '" y2="' + (node.y + node.height * 0.45) + '" stroke="' + escapeAttr(stroke) + '" stroke-width="2" stroke-linecap="round"></line>';
        }
        if (node.type === 'inference' || node.type === 'prediction') {
            const cx = node.x + node.width - 18;
            const cy = node.y + node.height * 0.5;
            return '<rect' + attrs + ' x="' + node.x + '" y="' + node.y + '" width="' + node.width + '" height="' + node.height + '" rx="8"></rect>' +
                '<ellipse cx="' + cx + '" cy="' + cy + '" rx="8" ry="5" fill="none" stroke="' + escapeAttr(stroke) + '" stroke-width="2"></ellipse>' +
                '<circle cx="' + cx + '" cy="' + cy + '" r="2.5" fill="' + escapeAttr(stroke) + '"></circle>';
        }
        if (node.type === 'deployment') {
            return '<rect' + attrs + ' x="' + node.x + '" y="' + node.y + '" width="' + node.width + '" height="' + node.height + '" rx="8"></rect>' +
                '<path d="M' + (node.x + node.width - 26) + ',' + (node.y + 10) + ' L' + (node.x + node.width - 18) + ',' + (node.y + 4) + ' L' + (node.x + node.width - 10) + ',' + (node.y + 10) + ' M' + (node.x + node.width - 18) + ',' + (node.y + 4) + ' V' + (node.y + 16) + '" fill="none" stroke="' + escapeAttr(stroke) + '" stroke-width="2" stroke-linecap="round"></path>';
        }
        if (node.type === 'embedding') {
            const rows = 3;
            let grid = '';
            for (let r = 0; r < rows; r++) {
                for (let c = 0; c < 4; c++) {
                    grid += '<rect x="' + (node.x + 10 + c * 14) + '" y="' + (node.y + 10 + r * 14) + '" width="10" height="10" rx="2" fill="' + escapeAttr(fill) + '" stroke="' + escapeAttr(stroke) + '" stroke-width="1"></rect>';
                }
            }
            return '<rect' + attrs + ' x="' + node.x + '" y="' + node.y + '" width="' + node.width + '" height="' + node.height + '" rx="8"></rect>' + grid;
        }
        if (node.type === 'backbone') {
            return '<rect' + attrs + ' x="' + node.x + '" y="' + node.y + '" width="' + node.width + '" height="' + node.height + '" rx="8"></rect>' +
                '<line x1="' + (node.x + 14) + '" y1="' + (node.y + node.height * 0.5) + '" x2="' + (node.x + node.width - 14) + '" y2="' + (node.y + node.height * 0.5) + '" stroke="' + escapeAttr(stroke) + '" stroke-width="3" stroke-linecap="round"></line>';
        }
        if (node.type === 'attention') {
            return '<rect' + attrs + ' x="' + node.x + '" y="' + node.y + '" width="' + node.width + '" height="' + node.height + '" rx="8"></rect>' +
                '<path d="M' + (node.x + node.width / 2) + ',' + (node.y + 10) + ' L' + (node.x + node.width / 2 - 10) + ',' + (node.y + 22) + ' M' + (node.x + node.width / 2) + ',' + (node.y + 10) + ' L' + (node.x + node.width / 2 + 10) + ',' + (node.y + 22) + ' M' + (node.x + node.width / 2) + ',' + (node.y + 10) + ' V' + (node.y + node.height - 8) + '" fill="none" stroke="' + escapeAttr(stroke) + '" stroke-width="2" stroke-linecap="round"></path>';
        }
        if (node.type === 'gateway') {
            return '<rect' + attrs + ' x="' + node.x + '" y="' + node.y + '" width="' + node.width + '" height="' + node.height + '" rx="8"></rect>' +
                '<polyline points="' + (node.x + 12) + ',' + (node.y + node.height * 0.35) + ' ' + (node.x + node.width / 2) + ',' + (node.y + node.height * 0.5) + ' ' + (node.x + node.width - 12) + ',' + (node.y + node.height * 0.35) + '" fill="none" stroke="' + escapeAttr(stroke) + '" stroke-width="2" stroke-linecap="round"></polyline>' +
                '<line x1="' + (node.x + node.width / 2) + '" y1="' + (node.y + node.height * 0.5) + '" x2="' + (node.x + node.width / 2) + '" y2="' + (node.y + node.height - 10) + '" stroke="' + escapeAttr(stroke) + '" stroke-width="2" stroke-linecap="round"></line>';
        }
        if (node.type === 'loadBalancer') {
            const cx = node.x + node.width / 2;
            const cy = node.y + node.height / 2;
            return '<rect' + attrs + ' x="' + node.x + '" y="' + node.y + '" width="' + node.width + '" height="' + node.height + '" rx="8"></rect>' +
                '<line x1="' + (node.x + 12) + '" y1="' + cy + '" x2="' + (cx - 12) + '" y2="' + cy + '" stroke="' + escapeAttr(stroke) + '" stroke-width="2"></line>' +
                '<line x1="' + (cx + 12) + '" y1="' + cy + '" x2="' + (node.x + node.width - 12) + '" y2="' + (node.y + 10) + '" stroke="' + escapeAttr(stroke) + '" stroke-width="2"></line>' +
                '<line x1="' + (cx + 12) + '" y1="' + cy + '" x2="' + (node.x + node.width - 12) + '" y2="' + (node.y + node.height - 10) + '" stroke="' + escapeAttr(stroke) + '" stroke-width="2"></line>' +
                '<circle cx="' + (cx - 12) + '" cy="' + cy + '" r="4" fill="' + escapeAttr(stroke) + '"></circle>';
        }
        if (node.type === 'firewall') {
            return '<rect' + attrs + ' x="' + node.x + '" y="' + node.y + '" width="' + node.width + '" height="' + node.height + '" rx="8"></rect>' +
                '<path d="M' + (node.x + node.width / 2) + ',' + (node.y + 8) + ' L' + (node.x + node.width - 14) + ',' + (node.y + node.height / 2) + ' L' + (node.x + node.width / 2) + ',' + (node.y + node.height - 8) + ' L' + (node.x + 14) + ',' + (node.y + node.height / 2) + ' Z" fill="none" stroke="' + escapeAttr(stroke) + '" stroke-width="1.5"></path>';
        }
        if (node.type === 'card') {
            return '<rect' + attrs + ' x="' + node.x + '" y="' + node.y + '" width="' + node.width + '" height="' + node.height + '" rx="12"></rect>' +
                '<line x1="' + node.x + '" y1="' + (node.y + 18) + '" x2="' + (node.x + node.width) + '" y2="' + (node.y + 18) + '" stroke="' + escapeAttr(stroke) + '" stroke-width="1.5"></line>';
        }
        if (node.type === 'tape') {
            return '<rect' + attrs + ' x="' + node.x + '" y="' + node.y + '" width="' + node.width + '" height="' + node.height + '" rx="4"></rect>' +
                '<line x1="' + node.x + '" y1="' + (node.y + node.height / 2) + '" x2="' + (node.x + node.width) + '" y2="' + (node.y + node.height / 2) + '" stroke="' + escapeAttr(stroke) + '" stroke-dasharray="4 3" stroke-width="1.5"></line>';
        }
        if (node.type === 'class') {
            return '<rect' + attrs + ' x="' + node.x + '" y="' + node.y + '" width="' + node.width + '" height="' + node.height + '" rx="0"></rect>' +
                '<line x1="' + node.x + '" y1="' + (node.y + node.height * 0.33) + '" x2="' + (node.x + node.width) + '" y2="' + (node.y + node.height * 0.33) + '" stroke="' + escapeAttr(stroke) + '" stroke-width="1.5"></line>' +
                '<line x1="' + node.x + '" y1="' + (node.y + node.height * 0.66) + '" x2="' + (node.x + node.width) + '" y2="' + (node.y + node.height * 0.66) + '" stroke="' + escapeAttr(stroke) + '" stroke-width="1.5"></line>';
        }
        if (node.type === 'interface') {
            return '<rect' + attrs + ' x="' + node.x + '" y="' + node.y + '" width="' + node.width + '" height="' + node.height + '" rx="0"></rect>' +
                '<line x1="' + node.x + '" y1="' + (node.y + node.height * 0.5) + '" x2="' + (node.x + node.width) + '" y2="' + (node.y + node.height * 0.5) + '" stroke="' + escapeAttr(stroke) + '" stroke-width="1.5"></line>';
        }
        if (node.type === 'component') {
            const tabW = 22;
            const tabH = 10;
            return '<rect' + attrs + ' x="' + node.x + '" y="' + node.y + '" width="' + node.width + '" height="' + node.height + '" rx="6"></rect>' +
                '<rect x="' + (node.x + 10) + '" y="' + (node.y - tabH) + '" width="' + tabW + '" height="' + tabH + '" rx="3" fill="' + escapeAttr(fill) + '" stroke="' + escapeAttr(stroke) + '" stroke-width="1.5"></rect>' +
                '<rect x="' + (node.x + node.width - 10 - tabW) + '" y="' + (node.y - tabH) + '" width="' + tabW + '" height="' + tabH + '" rx="3" fill="' + escapeAttr(fill) + '" stroke="' + escapeAttr(stroke) + '" stroke-width="1.5"></rect>';
        }
        if (node.type === 'actor') {
            const cx = node.x + node.width / 2;
            return '<circle' + attrs + ' cx="' + cx + '" cy="' + (node.y + 16) + '" r="12"></circle>' +
                '<line x1="' + cx + '" y1="' + (node.y + 28) + '" x2="' + cx + '" y2="' + (node.y + 48) + '" stroke="' + escapeAttr(stroke) + '" stroke-width="2"></line>' +
                '<line x1="' + (node.x + 14) + '" y1="' + (node.y + 36) + '" x2="' + (node.x + node.width - 14) + '" y2="' + (node.y + 36) + '" stroke="' + escapeAttr(stroke) + '" stroke-width="2"></line>' +
                '<line x1="' + cx + '" y1="' + (node.y + 48) + '" x2="' + (node.x + 14) + '" y2="' + (node.y + node.height) + '" stroke="' + escapeAttr(stroke) + '" stroke-width="2"></line>' +
                '<line x1="' + cx + '" y1="' + (node.y + 48) + '" x2="' + (node.x + node.width - 14) + '" y2="' + (node.y + node.height) + '" stroke="' + escapeAttr(stroke) + '" stroke-width="2"></line>';
        }
        if (node.type === 'usecase') {
            const rx = node.width / 2;
            const ry = node.height / 2;
            return '<ellipse' + attrs + ' cx="' + (node.x + rx) + '" cy="' + (node.y + ry) + '" rx="' + rx + '" ry="' + ry + '"></ellipse>';
        }
        if (node.type === 'package') {
            const tabH = 18;
            return '<rect' + attrs + ' x="' + node.x + '" y="' + node.y + '" width="' + node.width + '" height="' + node.height + '" rx="4"></rect>' +
                '<rect x="' + node.x + '" y="' + node.y + '" width="' + Math.min(60, node.width * 0.4) + '" height="' + tabH + '" rx="4" fill="' + escapeAttr(fill) + '" stroke="' + escapeAttr(stroke) + '" stroke-width="1.5"></rect>' +
                '<line x1="' + node.x + '" y1="' + (node.y + tabH) + '" x2="' + (node.x + node.width) + '" y2="' + (node.y + tabH) + '" stroke="' + escapeAttr(stroke) + '" stroke-width="1.5"></line>';
        }
        if (node.type === 'pipeline') {
            return '<rect' + attrs + ' x="' + node.x + '" y="' + node.y + '" width="' + node.width + '" height="' + node.height + '" rx="8"></rect>' +
                '<polyline points="' + (node.x + 14) + ',' + (node.y + node.height * 0.35) + ' ' + (node.x + 28) + ',' + (node.y + node.height * 0.65) + ' ' + (node.x + 42) + ',' + (node.y + node.height * 0.35) + '" fill="none" stroke="' + escapeAttr(stroke) + '" stroke-width="2" stroke-linecap="round"></polyline>' +
                '<line x1="' + (node.x + 42) + '" y1="' + (node.y + node.height * 0.5) + '" x2="' + (node.x + node.width - 14) + '" y2="' + (node.y + node.height * 0.5) + '" stroke="' + escapeAttr(stroke) + '" stroke-width="2" stroke-linecap="round"></line>';
        }
        if (node.type === 'container' || node.type === 'docker') {
            return '<rect' + attrs + ' x="' + node.x + '" y="' + node.y + '" width="' + node.width + '" height="' + node.height + '" rx="10"></rect>' +
                '<line x1="' + node.x + '" y1="' + (node.y + 16) + '" x2="' + (node.x + node.width) + '" y2="' + (node.y + 16) + '" stroke="' + escapeAttr(stroke) + '" stroke-width="1.5"></line>';
        }
        if (node.type === 'function') {
            return '<rect' + attrs + ' x="' + node.x + '" y="' + node.y + '" width="' + node.width + '" height="' + node.height + '" rx="8"></rect>' +
                '<path d="M' + (node.x + node.width - 20) + ',' + (node.y + 8) + ' L' + (node.x + node.width - 14) + ',' + (node.y + 16) + ' L' + (node.x + node.width - 8) + ',' + (node.y + 8) + '" fill="' + escapeAttr(stroke) + '" stroke="' + escapeAttr(stroke) + '" stroke-width="1.5"></path>';
        }
        if (node.type === 'warning' || node.type === 'alert') {
            const cx = node.x + node.width / 2;
            const top = node.y + 10;
            const bottom = node.y + node.height - 8;
            return '<path' + attrs + ' d="M' + cx + ',' + top + ' L' + (node.x + node.width - 14) + ',' + bottom + ' L' + (node.x + 14) + ',' + bottom + ' Z" fill="' + escapeAttr(fill) + '" stroke="' + escapeAttr(stroke) + '" stroke-width="2" stroke-linejoin="round"></path>' +
                '<line x1="' + cx + '" y1="' + (node.y + node.height * 0.5) + '" x2="' + cx + '" y2="' + (node.y + node.height * 0.68) + '" stroke="' + escapeAttr(stroke) + '" stroke-width="2.5" stroke-linecap="round"></line>' +
                '<circle cx="' + cx + '" cy="' + (node.y + node.height * 0.76) + '" r="2" fill="' + escapeAttr(stroke) + '"></circle>';
        }
        if (node.type === 'error') {
            const cx = node.x + node.width / 2;
            const cy = node.y + node.height / 2;
            const r = Math.min(node.width, node.height) / 2 - 8;
            return '<circle' + attrs + ' cx="' + cx + '" cy="' + cy + '" r="' + r + '"></circle>' +
                '<line x1="' + (cx - r * 0.5) + '" y1="' + (cy - r * 0.5) + '" x2="' + (cx + r * 0.5) + '" y2="' + (cy + r * 0.5) + '" stroke="' + escapeAttr(stroke) + '" stroke-width="2.5" stroke-linecap="round"></line>' +
                '<line x1="' + (cx + r * 0.5) + '" y1="' + (cy - r * 0.5) + '" x2="' + (cx - r * 0.5) + '" y2="' + (cy + r * 0.5) + '" stroke="' + escapeAttr(stroke) + '" stroke-width="2.5" stroke-linecap="round"></line>';
        }
        if (node.type === 'success') {
            const cx = node.x + node.width / 2;
            const cy = node.y + node.height / 2;
            const r = Math.min(node.width, node.height) / 2 - 8;
            return '<circle' + attrs + ' cx="' + cx + '" cy="' + cy + '" r="' + r + '"></circle>' +
                '<polyline points="' + (cx - r * 0.35) + ',' + cy + ' ' + (cx - r * 0.1) + ',' + (cy + r * 0.35) + ' ' + (cx + r * 0.35) + ',' + (cy - r * 0.3) + '" fill="none" stroke="' + escapeAttr(stroke) + '" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"></polyline>';
        }
        if (node.type === 'info') {
            const cx = node.x + node.width / 2;
            const cy = node.y + node.height / 2;
            const r = Math.min(node.width, node.height) / 2 - 8;
            return '<circle' + attrs + ' cx="' + cx + '" cy="' + cy + '" r="' + r + '"></circle>' +
                '<circle cx="' + cx + '" cy="' + (cy - r * 0.4) + '" r="2.5" fill="' + escapeAttr(stroke) + '"></circle>' +
                '<line x1="' + cx + '" y1="' + (cy - r * 0.15) + '" x2="' + cx + '" y2="' + (cy + r * 0.5) + '" stroke="' + escapeAttr(stroke) + '" stroke-width="2.5" stroke-linecap="round"></line>';
        }
        if (node.type === 'manualOperation') {
            const bot = node.y + node.height;
            const w = node.width;
            return '<path' + attrs + ' d="M' + node.x + ',' + node.y + ' L' + (node.x + w) + ',' + node.y + ' L' + (node.x + w * 0.65) + ',' + bot + ' L' + (node.x + w * 0.35) + ',' + bot + ' Z"></path>';
        }
        if (node.type === 'merge') {
            const top = node.y;
            const bot = node.y + node.height;
            const w = node.width;
            return '<path' + attrs + ' d="M' + (node.x + w * 0.35) + ',' + top + ' L' + (node.x + w * 0.65) + ',' + top + ' L' + (node.x + w) + ',' + bot + ' L' + node.x + ',' + bot + ' Z"></path>';
        }
        if (node.type === 'extract') {
            const top = node.y;
            const bot = node.y + node.height;
            const w = node.width;
            return '<path' + attrs + ' d="M' + node.x + ',' + top + ' L' + (node.x + w) + ',' + top + ' L' + (node.x + w * 0.5) + ',' + bot + ' Z"></path>';
        }
        if (node.type === 'sort') {
            const h = node.height;
            const w = node.width;
            return '<path' + attrs + ' d="M' + (node.x + w * 0.35) + ',' + node.y + ' L' + (node.x + w * 0.65) + ',' + node.y + ' L' + (node.x + w) + ',' + (node.y + h * 0.5) + ' L' + (node.x + w * 0.65) + ',' + (node.y + h) + ' L' + (node.x + w * 0.35) + ',' + (node.y + h) + ' L' + node.x + ',' + (node.y + h * 0.5) + ' Z"></path>';
        }
        if (node.type === 'collate') {
            const w = node.width;
            const h = node.height;
            return '<path' + attrs + ' d="M' + node.x + ',' + node.y + ' H' + (node.x + w) + ' V' + (node.y + h * 0.5) + ' C' + (node.x + w) + ',' + (node.y + h) + ' ' + node.x + ',' + (node.y + h) + ' ' + node.x + ',' + (node.y + h * 0.5) + ' Z"></path>';
        }
        if (node.type === 'fork' || node.type === 'join') {
            const h = node.height;
            const w = node.width;
            const barH = Math.min(12, h * 0.25);
            return '<rect x="' + node.x + '" y="' + (node.y + h / 2 - barH / 2) + '" width="' + w + '" height="' + barH + '" rx="4" fill="' + escapeAttr(fill) + '" stroke="' + escapeAttr(stroke) + '" stroke-width="2"></rect>';
        }
        if (node.type === 'timer') {
            const cx = node.x + node.width / 2;
            const cy = node.y + node.height / 2;
            const r = Math.min(node.width, node.height) / 2 - 6;
            return '<circle' + attrs + ' cx="' + cx + '" cy="' + cy + '" r="' + r + '"></circle>' +
                '<line x1="' + cx + '" y1="' + cy + '" x2="' + cx + '" y2="' + (cy - r * 0.6) + '" stroke="' + escapeAttr(stroke) + '" stroke-width="2" stroke-linecap="round"></line>' +
                '<line x1="' + cx + '" y1="' + cy + '" x2="' + (cx + r * 0.5) + '" y2="' + cy + '" stroke="' + escapeAttr(stroke) + '" stroke-width="2" stroke-linecap="round"></line>';
        }
        if (node.type === 'table') {
            const cols = 3;
            const rows = 2;
            const cw = (node.width - 10) / cols;
            const rh = (node.height - 10) / rows;
            let grid = '<rect' + attrs + ' x="' + node.x + '" y="' + node.y + '" width="' + node.width + '" height="' + node.height + '" rx="4"></rect>';
            for (let r = 1; r < rows; r++) {
                grid += '<line x1="' + node.x + '" y1="' + (node.y + 5 + r * rh) + '" x2="' + (node.x + node.width) + '" y2="' + (node.y + 5 + r * rh) + '" stroke="' + escapeAttr(stroke) + '" stroke-width="1"></line>';
            }
            for (let c = 1; c < cols; c++) {
                grid += '<line x1="' + (node.x + 5 + c * cw) + '" y1="' + node.y + '" x2="' + (node.x + 5 + c * cw) + '" y2="' + (node.y + node.height) + '" stroke="' + escapeAttr(stroke) + '" stroke-width="1"></line>';
            }
            return grid;
        }
        if (node.type === 'image') {
            return '<rect' + attrs + ' x="' + node.x + '" y="' + node.y + '" width="' + node.width + '" height="' + node.height + '" rx="8"></rect>' +
                '<circle cx="' + (node.x + 26) + '" cy="' + (node.y + 22) + '" r="8" fill="none" stroke="' + escapeAttr(stroke) + '" stroke-width="2"></circle>' +
                '<polyline points="' + (node.x + 12) + ',' + (node.y + node.height - 14) + ' ' + (node.x + node.width * 0.42) + ',' + (node.y + node.height * 0.52) + ' ' + (node.x + node.width * 0.58) + ',' + (node.y + node.height * 0.68) + ' ' + (node.x + node.width - 12) + ',' + (node.y + 26) + '" fill="none" stroke="' + escapeAttr(stroke) + '" stroke-width="2" stroke-linejoin="round"></polyline>';
        }
        if (node.type === 'lane') {
            const header = Math.min(42, node.width * 0.22);
            return '<rect' + attrs + ' x="' + node.x + '" y="' + node.y + '" width="' + node.width + '" height="' + node.height + '" rx="4"></rect>' +
                '<line x1="' + (node.x + header) + '" y1="' + node.y + '" x2="' + (node.x + header) + '" y2="' + (node.y + node.height) + '" stroke="' + escapeAttr(stroke) + '" stroke-width="2"></line>';
        }
        if (node.type === 'semaphore') {
            const cx = node.x + node.width / 2;
            const cy = node.y + node.height / 2;
            const r = Math.min(node.width, node.height) / 2 - 8;
            return '<circle' + attrs + ' cx="' + cx + '" cy="' + cy + '" r="' + r + '"></circle>' +
                '<rect x="' + (cx - r * 0.52) + '" y="' + (cy - 4) + '" width="' + (r * 1.04) + '" height="8" rx="4" fill="' + escapeAttr(stroke) + '"></rect>';
        }
        if (node.type === 'event') {
            const cx = node.x + node.width / 2;
            const cy = node.y + node.height / 2;
            const r = Math.min(node.width, node.height) / 2 - 8;
            return '<circle' + attrs + ' cx="' + cx + '" cy="' + cy + '" r="' + r + '"></circle>' +
                '<path d="M' + (cx + 2) + ',' + (cy - r * 0.58) + ' L' + (cx - r * 0.25) + ',' + (cy + 2) + ' H' + (cx + 2) + ' L' + (cx - 2) + ',' + (cy + r * 0.58) + ' L' + (cx + r * 0.28) + ',' + (cy - 2) + ' H' + (cx - 2) + ' Z" fill="' + escapeAttr(stroke) + '"></path>';
        }
        if (node.type === 'stream') {
            return '<path' + attrs + ' d="M' + (node.x + 12) + ',' + node.y + ' H' + (node.x + node.width - 12) + ' C' + (node.x + node.width + 10) + ',' + node.y + ' ' + (node.x + node.width + 10) + ',' + (node.y + node.height) + ' ' + (node.x + node.width - 12) + ',' + (node.y + node.height) + ' H' + (node.x + 12) + ' C' + (node.x - 10) + ',' + (node.y + node.height) + ' ' + (node.x - 10) + ',' + node.y + ' ' + (node.x + 12) + ',' + node.y + ' Z"></path>' +
                '<path d="M' + (node.x + 18) + ',' + (node.y + node.height * 0.5) + ' H' + (node.x + node.width - 26) + ' M' + (node.x + node.width - 36) + ',' + (node.y + node.height * 0.34) + ' L' + (node.x + node.width - 22) + ',' + (node.y + node.height * 0.5) + ' L' + (node.x + node.width - 36) + ',' + (node.y + node.height * 0.66) + '" fill="none" stroke="' + escapeAttr(stroke) + '" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"></path>';
        }
        if (node.type === 'batch') {
            return '<rect' + attrs + ' x="' + (node.x + 12) + '" y="' + node.y + '" width="' + (node.width - 12) + '" height="' + (node.height - 12) + '" rx="6"></rect>' +
                '<rect' + attrs + ' x="' + (node.x + 6) + '" y="' + (node.y + 6) + '" width="' + (node.width - 12) + '" height="' + (node.height - 12) + '" rx="6"></rect>' +
                '<rect' + attrs + ' x="' + node.x + '" y="' + (node.y + 12) + '" width="' + (node.width - 12) + '" height="' + (node.height - 12) + '" rx="6"></rect>';
        }
        if (node.type === 'cron') {
            const cx = node.x + node.width - 24;
            const cy = node.y + 24;
            return '<rect' + attrs + ' x="' + node.x + '" y="' + node.y + '" width="' + node.width + '" height="' + node.height + '" rx="8"></rect>' +
                '<circle cx="' + cx + '" cy="' + cy + '" r="12" fill="none" stroke="' + escapeAttr(stroke) + '" stroke-width="2"></circle>' +
                '<line x1="' + cx + '" y1="' + cy + '" x2="' + cx + '" y2="' + (cy - 7) + '" stroke="' + escapeAttr(stroke) + '" stroke-width="2" stroke-linecap="round"></line>' +
                '<line x1="' + cx + '" y1="' + cy + '" x2="' + (cx + 6) + '" y2="' + cy + '" stroke="' + escapeAttr(stroke) + '" stroke-width="2" stroke-linecap="round"></line>';
        }
        if (node.type === 'gitBranch') {
            const x1 = node.x + 28;
            const x2 = node.x + node.width - 28;
            const y1 = node.y + 18;
            const y2 = node.y + node.height - 18;
            return '<rect' + attrs + ' x="' + node.x + '" y="' + node.y + '" width="' + node.width + '" height="' + node.height + '" rx="8"></rect>' +
                '<circle cx="' + x1 + '" cy="' + y1 + '" r="5" fill="' + escapeAttr(stroke) + '"></circle>' +
                '<circle cx="' + x1 + '" cy="' + y2 + '" r="5" fill="' + escapeAttr(stroke) + '"></circle>' +
                '<circle cx="' + x2 + '" cy="' + y2 + '" r="5" fill="' + escapeAttr(stroke) + '"></circle>' +
                '<path d="M' + x1 + ',' + y1 + ' V' + y2 + ' H' + x2 + '" fill="none" stroke="' + escapeAttr(stroke) + '" stroke-width="2"></path>';
        }
        if (node.type === 'monitor') {
            return '<rect' + attrs + ' x="' + node.x + '" y="' + node.y + '" width="' + node.width + '" height="' + node.height + '" rx="8"></rect>' +
                '<polyline points="' + (node.x + 12) + ',' + (node.y + node.height * 0.58) + ' ' + (node.x + node.width * 0.32) + ',' + (node.y + node.height * 0.58) + ' ' + (node.x + node.width * 0.42) + ',' + (node.y + node.height * 0.36) + ' ' + (node.x + node.width * 0.54) + ',' + (node.y + node.height * 0.72) + ' ' + (node.x + node.width * 0.66) + ',' + (node.y + node.height * 0.46) + ' ' + (node.x + node.width - 12) + ',' + (node.y + node.height * 0.46) + '" fill="none" stroke="' + escapeAttr(stroke) + '" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"></polyline>';
        }
        if (node.type === 'log' || node.type === 'config') {
            const fold = Math.min(18, node.width * 0.14);
            const icon = node.type === 'config'
                ? '<circle cx="' + (node.x + node.width - 24) + '" cy="' + (node.y + 26) + '" r="8" fill="none" stroke="' + escapeAttr(stroke) + '" stroke-width="2"></circle><circle cx="' + (node.x + node.width - 24) + '" cy="' + (node.y + 26) + '" r="2.5" fill="' + escapeAttr(stroke) + '"></circle>'
                : '<line x1="' + (node.x + 14) + '" y1="' + (node.y + 24) + '" x2="' + (node.x + node.width - 18) + '" y2="' + (node.y + 24) + '" stroke="' + escapeAttr(stroke) + '" stroke-width="1.5"></line><line x1="' + (node.x + 14) + '" y1="' + (node.y + 38) + '" x2="' + (node.x + node.width * 0.7) + '" y2="' + (node.y + 38) + '" stroke="' + escapeAttr(stroke) + '" stroke-width="1.5"></line>';
            return '<path' + attrs + ' d="M' + node.x + ',' + node.y + ' H' + (node.x + node.width - fold) + ' L' + (node.x + node.width) + ',' + (node.y + fold) + ' V' + (node.y + node.height) + ' H' + node.x + ' Z"></path>' +
                '<polyline points="' + (node.x + node.width - fold) + ',' + node.y + ' ' + (node.x + node.width - fold) + ',' + (node.y + fold) + ' ' + (node.x + node.width) + ',' + (node.y + fold) + '" fill="none" stroke="' + escapeAttr(stroke) + '" stroke-width="1.5"></polyline>' + icon;
        }
        const rx = node.type === 'terminator' ? Math.min(24, node.height / 2) : 8;
        return '<rect' + attrs + ' x="' + node.x + '" y="' + node.y + '" width="' + node.width + '" height="' + node.height + '" rx="' + rx + '"></rect>';
    }

    function labelSvg(node) {
        const lines = wrapText(node.label || '', Math.max(4, Math.floor(node.width / 13)), 4);
        const lineHeight = 17;
        const startY = node.y + node.height / 2 - ((lines.length - 1) * lineHeight) / 2 + 5;
        return [
            '<text x="', node.x + node.width / 2, '" y="', startY,
            '" text-anchor="middle" dominant-baseline="middle" fill="', escapeAttr(node.font),
            '" font-size="14" font-weight="700" style="pointer-events:none">'
        ].join('') + lines.map((line, index) => {
            return '<tspan x="' + (node.x + node.width / 2) + '" dy="' + (index === 0 ? 0 : lineHeight) + '">' + escapeText(line) + '</tspan>';
        }).join('') + '</text>';
    }

    function edgeSvg(edge) {
        const source = getNode(edge.source);
        const target = getNode(edge.target);
        if (!source || !target) return '';
        const selected = state.local.selectedKind === 'edge' && state.local.selectedId === edge.id;
        const type = edge.type || 'orthogonal';
        const path = edgePath(source, target, type);
        const stroke = selected ? '#4f46e5' : (edge.stroke || state.colors.stroke);
        const strokeWidth = type === 'thick' ? 3.4 : 2.2;
        const dash = type === 'dashed' ? ' stroke-dasharray="8 6"' : (type === 'dotted' ? ' stroke-dasharray="2 6" stroke-linecap="round"' : '');
        const markerStart = type === 'bidirectional' ? ' marker-start="url(#arrowStart)"' : '';
        const markerEnd = type === 'noArrow' ? '' : ' marker-end="url(#arrowHead)"';
        return [
            '<g class="diagram-edge', selected ? ' selected' : '', '" data-edge-id="', edge.id, '">',
            '<path d="', path, '" fill="none" stroke="transparent" stroke-width="14"></path>',
            '<path class="edge-line" d="', path, '" fill="none" stroke="', escapeAttr(stroke),
            '" stroke-width="', strokeWidth, '"', dash, markerStart, markerEnd, '></path>',
            '</g>'
        ].join('');
    }

    function edgePath(source, target, type) {
        const a = anchorPoint(source, target, 12);
        const b = anchorPoint(target, source, 12);
        if (type === 'straight' || type === 'dashed' || type === 'dotted' || type === 'thick' || type === 'noArrow' || type === 'bidirectional') {
            return 'M' + a.x + ',' + a.y + ' L' + b.x + ',' + b.y;
        }
        if (type === 'curve') {
            const dx = Math.max(80, Math.abs(b.x - a.x) * 0.5);
            const dy = Math.max(70, Math.abs(b.y - a.y) * 0.5);
            const c1 = Math.abs(a.x - b.x) > Math.abs(a.y - b.y)
                ? { x: a.x + (b.x > a.x ? dx : -dx), y: a.y }
                : { x: a.x, y: a.y + (b.y > a.y ? dy : -dy) };
            const c2 = Math.abs(a.x - b.x) > Math.abs(a.y - b.y)
                ? { x: b.x - (b.x > a.x ? dx : -dx), y: b.y }
                : { x: b.x, y: b.y - (b.y > a.y ? dy : -dy) };
            return 'M' + a.x + ',' + a.y + ' C' + c1.x + ',' + c1.y + ' ' + c2.x + ',' + c2.y + ' ' + b.x + ',' + b.y;
        }
        if (Math.abs(a.x - b.x) > Math.abs(a.y - b.y)) {
            const midX = (a.x + b.x) / 2;
            return 'M' + a.x + ',' + a.y + ' L' + midX + ',' + a.y + ' L' + midX + ',' + b.y + ' L' + b.x + ',' + b.y;
        }
        const midY = (a.y + b.y) / 2;
        return 'M' + a.x + ',' + a.y + ' L' + a.x + ',' + midY + ' L' + b.x + ',' + midY + ' L' + b.x + ',' + b.y;
    }

    function anchorPoint(node, other) {
        const pad = arguments.length > 2 ? arguments[2] : 0;
        const cx = node.x + node.width / 2;
        const cy = node.y + node.height / 2;
        const ox = other.x + other.width / 2;
        const oy = other.y + other.height / 2;
        if (Math.abs(ox - cx) > Math.abs(oy - cy)) {
            return ox > cx ? { x: node.x + node.width + pad, y: cy } : { x: node.x - pad, y: cy };
        }
        return oy > cy ? { x: cx, y: node.y + node.height + pad } : { x: cx, y: node.y - pad };
    }

    function onNodePointerDown(event) {
        event.stopPropagation();
        const id = event.currentTarget.dataset.nodeId;
        if (event.detail >= 2) {
            focusNodeEditor(id);
            return;
        }
        if (state.connectMode) {
            handleConnectClick(id);
            return;
        }
        const node = getNode(id);
        if (!node) return;
        const point = clientToSvg(event);
        state.local.selectedKind = 'node';
        state.local.selectedId = id;
        state.drag = {
            id,
            offsetX: point.x - node.x,
            offsetY: point.y - node.y,
            before: snapshotState(),
            moved: false
        };
        syncSelectionClass();
        updateSelectionInspector();
    }

    function onNodeDoubleClick(event) {
        event.stopPropagation();
        focusNodeEditor(event.currentTarget.dataset.nodeId);
    }

    function focusNodeEditor(nodeId) {
        const node = getNode(nodeId);
        if (!node) return;
        state.local.selectedKind = 'node';
        state.local.selectedId = node.id;
        syncSelectionClass();
        updateSelectionInspector();
        if (nodeLabelInput) {
            nodeLabelInput.disabled = false;
            nodeLabelInput.focus();
            nodeLabelInput.select();
        }
    }

    function syncSelectionClass() {
        canvas.querySelectorAll('.diagram-node').forEach((element) => {
            element.classList.toggle('selected', state.local.selectedKind === 'node' && state.local.selectedId === element.dataset.nodeId);
        });
        canvas.querySelectorAll('.diagram-edge').forEach((element) => {
            element.classList.toggle('selected', state.local.selectedKind === 'edge' && state.local.selectedId === element.dataset.edgeId);
        });
    }

    function handleConnectClick(nodeId) {
        if (!state.connectSource) {
            state.connectSource = nodeId;
            state.local.selectedKind = 'node';
            state.local.selectedId = nodeId;
            setStatus('请选择连线目标图形', 'ok');
            render();
            return;
        }
        if (state.connectSource !== nodeId) {
            pushHistory('创建连线');
            state.local.edges.push(makeEdge(state.connectSource, nodeId));
            state.connectSource = null;
            setStatus('已创建连线，可继续选择下一组图形', 'ok');
            render();
        }
    }

    function addNode(type, x, y, label) {
        pushHistory('添加图形');
        const size = defaultSize(type);
        const node = makeNode(
            type,
            Math.round(x - size.width / 2),
            Math.round(y - size.height / 2),
            label || defaultLabel(type),
            size.width,
            size.height,
            state.colors
        );
        state.local.nodes.push(node);
        state.local.selectedKind = 'node';
        state.local.selectedId = node.id;
        render();
        setStatus('已添加图形，双击可编辑文字', 'ok');
    }

    function deleteSelected() {
        if (!state.local.selectedId) return;
        pushHistory('删除元素');
        if (state.local.selectedKind === 'node') {
            const nodeId = state.local.selectedId;
            state.local.nodes = state.local.nodes.filter((node) => node.id !== nodeId);
            state.local.edges = state.local.edges.filter((edge) => edge.source !== nodeId && edge.target !== nodeId);
        } else if (state.local.selectedKind === 'edge') {
            state.local.edges = state.local.edges.filter((edge) => edge.id !== state.local.selectedId);
        }
        selectNone();
        render();
    }

    function duplicateSelected() {
        if (state.local.selectedKind !== 'node' || !state.local.selectedId) {
            setStatus('请先选中一个图形再复制', 'busy');
            return;
        }
        const node = getNode(state.local.selectedId);
        if (!node) return;
        pushHistory('复制图形');
        const copy = Object.assign({}, node, {
            id: uniqueId('n'),
            x: Math.round(node.x + 34),
            y: Math.round(node.y + 34),
            label: node.label
        });
        state.local.nodes.push(copy);
        state.local.selectedKind = 'node';
        state.local.selectedId = copy.id;
        render();
        setStatus('已复制选中图形', 'ok');
    }

    function clearCanvas() {
        if (!window.confirm('确定清空当前画布吗？')) return;
        pushHistory('清空画布');
        state.local.nodes = [];
        state.local.edges = [];
        state.local.backgrounds = [];
        selectNone();
        render();
        setStatus('画布已清空', 'ok');
    }

    function applyTemplate(name) {
        const templates = {
            ml: {
                label: '模型训练模板',
                direction: 'TB',
                items: [
                    ['dataset', '数据集'],
                    ['process', '数据清洗'],
                    ['process', '特征工程'],
                    ['training', '模型训练'],
                    ['evaluation', '效果评估'],
                    ['paper', '论文 / 报告输出']
                ]
            },
            deeplearn: {
                label: '深度学习模板',
                direction: 'TB',
                items: [
                    ['dataset', '数据集'],
                    ['augment', '数据增强'],
                    ['embedding', '特征表示'],
                    ['backbone', '骨干网络'],
                    ['attention', '注意力机制'],
                    ['training', '训练'],
                    ['loss', '损失函数'],
                    ['optimizer', '优化器'],
                    ['evaluation', '评估'],
                    ['paper', '结果输出']
                ]
            },
            computer: {
                label: '计算机系统模板',
                direction: 'LR',
                items: [
                    ['person', '用户'],
                    ['web', '前端界面'],
                    ['api', '接口层'],
                    ['service', '业务服务'],
                    ['process', '调度 / 处理'],
                    ['database', '数据库'],
                    ['cache', '缓存'],
                    ['server', '服务器'],
                    ['deployment', '部署']
                ]
            },
            arch: {
                label: '系统架构模板',
                direction: 'LR',
                items: [
                    ['person', '用户'],
                    ['web', '前端页面'],
                    ['gateway', '网关'],
                    ['service', '业务服务'],
                    ['cache', '缓存'],
                    ['database', '数据库'],
                    ['deployment', '部署']
                ]
            },
            ai: {
                label: 'AI 流程模板',
                direction: 'TB',
                items: [
                    ['data', '输入提示词'],
                    ['api', '请求模型'],
                    ['model', '生成内容'],
                    ['evaluation', '结果检查'],
                    ['paper', '输出使用']
                ]
            },
            api: {
                label: 'API 服务模板',
                direction: 'LR',
                items: [
                    ['person', '用户'],
                    ['data', '请求参数'],
                    ['api', 'API 网关'],
                    ['service', '业务服务'],
                    ['model', '模型服务'],
                    ['cache', '缓存'],
                    ['database', '数据库'],
                    ['display', '结果返回']
                ]
            },
            experiment: {
                label: '实验流程模板',
                direction: 'TB',
                items: [
                    ['terminator', '提出问题'],
                    ['preparation', '实验设计'],
                    ['manualInput', '变量设置'],
                    ['experiment', '执行实验'],
                    ['decision', '结果是否有效'],
                    ['metric', '统计指标'],
                    ['document', '实验记录']
                ]
            },
            paper: {
                label: '论文产出模板',
                direction: 'LR',
                items: [
                    ['document', '文献阅读'],
                    ['note', '研究假设'],
                    ['experiment', '实验验证'],
                    ['metric', '图表指标'],
                    ['paper', '论文撰写'],
                    ['terminator', '投稿']
                ]
            },
            flowchart: {
                label: '标准流程图模板',
                direction: 'TB',
                items: [
                    ['terminator', '开始'],
                    ['data', '输入数据'],
                    ['process', '处理步骤'],
                    ['decision', '是否满足条件'],
                    ['process', '执行分支任务'],
                    ['document', '生成结果'],
                    ['terminator', '结束']
                ]
            },
            mindmap: {
                label: '思维导图模板',
                direction: 'LR',
                items: [
                    ['model', '中心主题'],
                    ['process', '研究背景', 0],
                    ['process', '核心问题', 0],
                    ['process', '方法路线', 0],
                    ['process', '实验验证', 0],
                    ['note', '相关工作', 1],
                    ['note', '应用场景', 1],
                    ['note', '指标定义', 2],
                    ['note', '数据来源', 3],
                    ['note', '结果分析', 4]
                ]
            },
            sequence: {
                label: 'UML 时序图模板',
                direction: 'LR',
                items: [
                    ['actor', '用户'],
                    ['web', '前端页面'],
                    ['api', 'API 网关'],
                    ['service', '业务服务'],
                    ['database', '数据库'],
                    ['message', '请求登录'],
                    ['message', '校验参数'],
                    ['message', '查询账号'],
                    ['message', '返回结果']
                ]
            },
            classDiagram: {
                label: 'UML 类图模板',
                direction: 'LR',
                items: [
                    ['class', 'User\n- id\n- email\n+ login()'],
                    ['class', 'Project\n- id\n- title\n+ addMember()'],
                    ['class', 'Diagram\n- id\n- xml\n+ export()'],
                    ['interface', 'AIProvider\n+ generate()'],
                    ['component', 'AuthService'],
                    ['component', 'DiagramService']
                ]
            },
            er: {
                label: 'ER 图模板',
                direction: 'LR',
                items: [
                    ['database', '用户 User'],
                    ['database', '项目 Project', 0],
                    ['database', '图表 Diagram', 1],
                    ['database', 'AI配置 AIConfig', 0],
                    ['tag', '1:N 拥有', 0],
                    ['tag', '1:N 包含', 1]
                ]
            },
            network: {
                label: '网络拓扑模板',
                direction: 'LR',
                items: [
                    ['person', '客户端'],
                    ['firewall', '防火墙', 0],
                    ['loadBalancer', '负载均衡', 1],
                    ['gateway', 'API 网关', 2],
                    ['server', '应用服务器 A', 3],
                    ['server', '应用服务器 B', 3],
                    ['cache', '缓存', 3],
                    ['database', '主数据库', 4],
                    ['database', '备份数据库', 4],
                    ['monitor', '监控告警', 4]
                ]
            }
        };
        const spec = templates[name] || templates.ml;
        replaceDiagramWithItems(spec.items, spec.direction, spec.label);
    }

    function generateDiagramFromAiPrompt() {
        const input = $('#aiPromptInput');
        const typeSelect = $('#aiDiagramType');
        const promptText = input ? input.value.trim() : '';
        if (!promptText) {
            setStatus('请先输入想要的图表描述', 'busy');
            return;
        }
        if (!state.aiConfig) {
            setStatus('未找到可用的 AI 配置，请先到 AI 设置页面配置模型', 'busy');
            return;
        }
        const providerName = state.aiConfig.provider || 'AI';
        const diagramType = typeSelect && typeSelect.value !== 'auto' ? typeSelect.value : 'auto';
        const prompt = diagramType === 'auto' ? promptText : ('图表类型：' + diagramType + '\n' + promptText);
        setStatus('正在请求 ' + providerName + ' 生成图表…', 'busy');
        const generateBtn = $('#aiGenerateBtn');
        if (generateBtn) { generateBtn.disabled = true; generateBtn.textContent = 'AI 绘制中…'; }
        fetch('/api/diagrams/ai-plan', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({ prompt }),
        }).then(async (resp) => {
            const data = await resp.json();
            if (!resp.ok || !data.ok) throw new Error(data.detail || data.msg || 'AI 生成失败');
            const plan = data.plan || {};
            const modal = $('#aiDiagramModal');
            if (modal && window.bootstrap) {
                const instance = window.bootstrap.Modal.getInstance(modal);
                if (instance) instance.hide();
            }
            if (plan.xml) {
                setStatus('AI 已生成图表，正在模拟绘制…', 'ok');
                await animateDrawioXml(plan.xml);
                setStatus('AI 绘图完成，当前使用 ' + providerName + ' / ' + (state.aiConfig.model || '默认模型') + ' 配置。', 'ok');
            } else {
                const items = Array.isArray(plan.items) && plan.items.length ? plan.items : parsePromptSteps(prompt);
                const direction = plan.direction || state.layoutDirection || 'TB';
                replaceDiagramWithItems(items, direction, 'AI 草稿');
                fitCanvas();
                setStatus('已根据描述生成可编辑草稿，当前使用 ' + providerName + ' / ' + (state.aiConfig.model || '默认模型') + ' 配置。', 'ok');
            }
        }).catch((err) => {
            setStatus('AI 生成失败：' + err.message, 'busy');
        }).finally(() => {
            if (generateBtn) { generateBtn.disabled = false; generateBtn.innerHTML = '<i class="bi bi-magic me-1"></i>生成可编辑草稿'; }
        });
    }

    function animateDrawioXml(xml) {
        return new Promise((resolve) => {
            const graphXml = extractGraphXml(xml);
            if (!graphXml) { loadXmlToState(xml); render(); resolve(); return; }
            const doc = new DOMParser().parseFromString(graphXml, 'text/xml');
            if (doc.querySelector('parsererror')) { loadXmlToState(xml); render(); resolve(); return; }
            const model = doc.querySelector('mxGraphModel');
            if (!model) { loadXmlToState(xml); render(); resolve(); return; }
            const cells = Array.from(model.querySelectorAll('mxCell'));
            const parsedNodes = [];
            const parsedEdges = [];
            const nodeIds = new Set();
            cells.forEach((cell) => {
                if (cell.getAttribute('vertex') === '1') {
                    const geo = cell.querySelector('mxGeometry');
                    if (!geo) return;
                    const style = parseStyle(cell.getAttribute('style') || '');
                    const id = cell.getAttribute('id') || uniqueId('n');
                    const x = parseFloat(geo.getAttribute('x') || '0');
                    const y = parseFloat(geo.getAttribute('y') || '0');
                    const w = Math.max(70, parseFloat(geo.getAttribute('width') || '140'));
                    const h = Math.max(34, parseFloat(geo.getAttribute('height') || '60'));
                    parsedNodes.push({ id, type: typeFromStyle(style), label: cell.getAttribute('value') || '', x, y, width: w, height: h, fill: style.fillColor || state.colors.fill, stroke: style.strokeColor || state.colors.stroke, font: style.fontColor || state.colors.font });
                    nodeIds.add(id);
                }
            });
            cells.forEach((cell) => {
                if (cell.getAttribute('edge') === '1') {
                    const src = cell.getAttribute('source');
                    const tgt = cell.getAttribute('target');
                    if (nodeIds.has(src) && nodeIds.has(tgt)) {
                        const style = parseStyle(cell.getAttribute('style') || '');
                        parsedEdges.push({ id: cell.getAttribute('id') || uniqueId('e'), source: src, target: tgt, type: edgeTypeFromStyle(style), stroke: style.strokeColor || state.colors.stroke });
                    }
                }
            });
            if (!parsedNodes.length) { loadXmlToState(xml); render(); resolve(); return; }
            pushHistory('AI 绘图');
            state.local.nodes = [];
            state.local.edges = [];
            state.local.backgrounds = [];
            selectNone();
            const animNodes = [...parsedNodes];
            const animEdges = [...parsedEdges];
            let nodeIndex = 0;
            function addNextNode() {
                if (nodeIndex < animNodes.length) {
                    const n = animNodes[nodeIndex];
                    state.local.nodes.push(n);
                    nodeIndex++;
                    render(false);
                    const wrap = $('#stageWrap');
                    if (wrap) {
                        const cx = n.x + n.width / 2;
                        const cy = n.y + n.height / 2;
                        const zoom = state.zoom || 1;
                        wrap.scrollLeft = Math.max(0, cx * zoom - wrap.clientWidth / 2);
                        wrap.scrollTop = Math.max(0, cy * zoom - wrap.clientHeight / 2);
                    }
                    setTimeout(addNextNode, 200);
                } else {
                    let edgeIndex = 0;
                    function addNextEdge() {
                        if (edgeIndex < animEdges.length) {
                            state.local.edges.push(animEdges[edgeIndex]);
                            edgeIndex++;
                            render(false);
                            setTimeout(addNextEdge, 120);
                        } else {
                            updateCanvasSize();
                            render();
                            fitCanvas();
                            resolve();
                        }
                    }
                    addNextEdge();
                }
            }
            addNextNode();
        });
    }

    function parsePromptSteps(prompt) {
        const arrowMatch = prompt.includes('->') || prompt.includes('→') || prompt.includes('=>');
        let parts = [];
        if (arrowMatch) {
            parts = prompt.split(/(?:->|→|=>)/g);
        } else {
            parts = prompt
                .replace(/画一个|生成|流程图|包含|包括/g, '')
                .split(/[，,。；;\n]/g);
        }
        return parts
            .map((part) => part.trim())
            .filter((part) => part.length >= 2 && part.length <= 28)
            .slice(0, 10)
            .map((label, index) => [guessShapeFromLabel(label, index), label]);
    }

    function guessShapeFromLabel(label, index) {
        if (/开始|结束|完成|投稿/.test(label)) return 'terminator';
        if (/是否|判断|条件|分支|有效/.test(label)) return 'decision';
        if (/数据集|数据采集|采集|样本/.test(label)) return 'dataset';
        if (/数据库|存储/.test(label)) return 'database';
        if (/缓存/.test(label)) return 'cache';
        if (/队列|消息队列/.test(label)) return 'queue';
        if (/API|api|接口|网关/.test(label)) return 'api';
        if (/服务|微服务/.test(label)) return 'service';
        if (/服务器|主机/.test(label)) return 'server';
        if (/网页|页面|Web|web/.test(label)) return 'web';
        if (/移动|手机|App|APP/.test(label)) return 'mobile';
        if (/消息|事件/.test(label)) return 'message';
        if (/输入|输出|请求|返回|参数/.test(label)) return 'data';
        if (/模型|推理|预测/.test(label)) return 'model';
        if (/训练|微调/.test(label)) return 'training';
        if (/评估|指标|统计|效果/.test(label)) return 'evaluation';
        if (/实验|验证|测试/.test(label)) return 'experiment';
        if (/论文|报告|文档/.test(label)) return 'paper';
        if (/用户|角色|人员/.test(label)) return 'person';
        return index === 0 ? 'terminator' : 'process';
    }

    function replaceDiagramWithItems(items, direction, label) {
        pushHistory(label || '套用模板');
        state.layoutDirection = direction || 'TB';
        state.local.nodes = items.map((item) => {
            const size = defaultSize(item[0]);
            const node = makeNode(item[0], 100, 100, item[1], size.width, size.height, state.colors);
            const color = semanticNodeColor(node);
            node.fill = color.fill;
            node.stroke = color.stroke;
            node.font = color.font;
            return node;
        });
        state.local.edges = [];
        const hasExplicitParents = items.some((item) => Number.isInteger(item[2]));
        if (hasExplicitParents) {
            items.forEach((item, index) => {
                if (!Number.isInteger(item[2])) return;
                const source = state.local.nodes[item[2]];
                const target = state.local.nodes[index];
                if (source && target) state.local.edges.push(makeEdge(source.id, target.id));
            });
        } else {
            for (let index = 0; index < state.local.nodes.length - 1; index += 1) {
                state.local.edges.push(makeEdge(state.local.nodes[index].id, state.local.nodes[index + 1].id));
            }
        }
        state.local.backgrounds = [];
        selectNone();
        layoutGraph(state.layoutDirection);
        render();
        fitCanvas();
        setStatus('已套用：' + (label || '模板'), 'ok');
    }

    function canvasBaseSize() {
        const bounds = getDiagramBounds();
        return {
            width: Math.max(CANVAS_MIN_WIDTH, bounds.maxX + CANVAS_PADDING),
            height: Math.max(CANVAS_MIN_HEIGHT, bounds.maxY + CANVAS_PADDING)
        };
    }

    function viewportPointToCanvasPoint(anchor) {
        const rect = canvas.getBoundingClientRect();
        const clientX = anchor && Number.isFinite(anchor.clientX) ? anchor.clientX : (stageWrap.getBoundingClientRect().left + stageWrap.clientWidth / 2);
        const clientY = anchor && Number.isFinite(anchor.clientY) ? anchor.clientY : (stageWrap.getBoundingClientRect().top + stageWrap.clientHeight / 2);
        const x = (clientX - rect.left) / Math.max(0.01, state.zoom || 1);
        const y = (clientY - rect.top) / Math.max(0.01, state.zoom || 1);
        const offsetX = clientX - stageWrap.getBoundingClientRect().left;
        const offsetY = clientY - stageWrap.getBoundingClientRect().top;
        return { x, y, offsetX, offsetY };
    }

    function applyZoomedCanvasSize() {
        const size = canvasBaseSize();
        canvas.setAttribute('width', String(Math.round(size.width)));
        canvas.setAttribute('height', String(Math.round(size.height)));
        canvas.setAttribute('viewBox', '0 0 ' + Math.round(size.width) + ' ' + Math.round(size.height));
        canvas.style.width = Math.round(size.width * state.zoom) + 'px';
        canvas.style.height = Math.round(size.height * state.zoom) + 'px';
    }

    function setZoom(value, showStatus, anchor) {
        const before = viewportPointToCanvasPoint(anchor);
        state.zoom = clamp(Math.round(value * 1000) / 1000, 0.12, 4);
        applyZoomedCanvasSize();
        requestAnimationFrame(() => {
            stageWrap.scrollLeft = Math.max(0, before.x * state.zoom - before.offsetX);
            stageWrap.scrollTop = Math.max(0, before.y * state.zoom - before.offsetY);
            if (showStatus !== false) setStatus('缩放 ' + Math.round(state.zoom * 100) + '%', 'ok');
        });
    }

    function fitCanvas() {
        const bounds = getDiagramBounds();
        if (!state.local.nodes.length && !state.local.backgrounds.length) {
            setZoom(1, false);
            stageWrap.scrollLeft = 0;
            stageWrap.scrollTop = 0;
            setStatus('画布为空，已恢复 100%', 'ok');
            return;
        }
        const margin = 56;
        const contentWidth = Math.max(80, bounds.maxX - bounds.minX);
        const contentHeight = Math.max(60, bounds.maxY - bounds.minY);
        const zoomX = Math.max(0.05, (stageWrap.clientWidth - margin * 2) / contentWidth);
        const zoomY = Math.max(0.05, (stageWrap.clientHeight - margin * 2) / contentHeight);
        state.zoom = clamp(Math.min(zoomX, zoomY), 0.12, 2.2);
        applyZoomedCanvasSize();
        requestAnimationFrame(() => {
            const contentCenterX = (bounds.minX + bounds.maxX) / 2;
            const contentCenterY = (bounds.minY + bounds.maxY) / 2;
            stageWrap.scrollLeft = Math.max(0, contentCenterX * state.zoom - stageWrap.clientWidth / 2);
            stageWrap.scrollTop = Math.max(0, contentCenterY * state.zoom - stageWrap.clientHeight / 2);
            setStatus('已适应画布，缩放 ' + Math.round(state.zoom * 100) + '%', 'ok');
        });
    }

    function selectNone() {
        state.local.selectedKind = null;
        state.local.selectedId = null;
    }

    function getSelectedNode() {
        if (state.local.selectedKind !== 'node' || !state.local.selectedId) return null;
        return getNode(state.local.selectedId);
    }

    function updateSelectionInspector() {
        if (!nodeLabelInput) return;
        const node = getSelectedNode();
        const hint = $('#nodeInspectorHint');
        if (!node) {
            nodeLabelInput.disabled = true;
            if (document.activeElement !== nodeLabelInput) nodeLabelInput.value = '';
            if (hint) hint.textContent = '单击图形选中，也可双击快速编辑。';
            return;
        }
        nodeLabelInput.disabled = false;
        if (document.activeElement !== nodeLabelInput) nodeLabelInput.value = node.label || '';
        if (hint) hint.textContent = '正在编辑：' + defaultLabel(node.type);
    }

    function autoLayout(direction) {
        state.layoutDirection = direction;
        const nodes = state.local.nodes;
        if (!nodes.length) return;
        pushHistory(direction === 'LR' ? '横向布局' : '纵向布局');
        layoutGraph(direction);
        render();
        setStatus(direction === 'LR' ? '已切换为横向布局' : '已切换为纵向布局', 'ok');
    }

    function beautifyDiagram() {
        if (!state.local.nodes.length) return;
        pushHistory('美化流程图');
        layoutGraph(state.layoutDirection || 'TB');
        state.local.nodes.forEach((node) => {
            const color = semanticNodeColor(node);
            node.fill = color.fill;
            node.stroke = color.stroke;
            node.font = color.font;
        });
        state.local.edges.forEach((edge) => {
            edge.stroke = '#475569';
            edge.type = edge.type || state.edgeType || 'orthogonal';
        });
        render();
        setStatus('已按流程层级重新布局，并按图形语义优化颜色', 'ok');
    }

    function layoutGraph(direction) {
        const nodes = state.local.nodes;
        const byId = new Map(nodes.map((node) => [node.id, node]));
        const incoming = new Map(nodes.map((node) => [node.id, 0]));
        const outgoing = new Map(nodes.map((node) => [node.id, []]));
        state.local.edges.forEach((edge) => {
            if (!byId.has(edge.source) || !byId.has(edge.target)) return;
            incoming.set(edge.target, (incoming.get(edge.target) || 0) + 1);
            outgoing.get(edge.source).push(edge.target);
        });

        const roots = nodes.filter((node) => (incoming.get(node.id) || 0) === 0);
        const seed = roots.length ? roots : nodes.slice(0, 1);
        const level = new Map();
        const queue = seed.map((node) => {
            level.set(node.id, 0);
            return node.id;
        });
        while (queue.length) {
            const id = queue.shift();
            const current = level.get(id) || 0;
            (outgoing.get(id) || []).forEach((targetId) => {
                const next = current + 1;
                if (!level.has(targetId) || next > level.get(targetId)) {
                    level.set(targetId, next);
                    queue.push(targetId);
                }
            });
        }

        let fallbackLevel = Math.max(0, ...Array.from(level.values())) + 1;
        nodes
            .slice()
            .sort((a, b) => (a.y - b.y) || (a.x - b.x))
            .forEach((node) => {
                if (!level.has(node.id)) {
                    level.set(node.id, fallbackLevel);
                    fallbackLevel += 1;
                }
            });

        const groups = new Map();
        nodes.forEach((node) => {
            const key = level.get(node.id) || 0;
            if (!groups.has(key)) groups.set(key, []);
            groups.get(key).push(node);
        });

        Array.from(groups.keys()).sort((a, b) => a - b).forEach((key) => {
            const group = groups.get(key).sort((a, b) => (a.y - b.y) || (a.x - b.x));
            if (direction === 'LR') {
                const gap = 34;
                const totalHeight = group.reduce((sum, node) => sum + node.height, 0) + gap * (group.length - 1);
                let y = Math.max(34, (CANVAS_MIN_HEIGHT - totalHeight) / 2);
                group.forEach((node) => {
                    node.x = Math.round(120 + key * 260);
                    node.y = Math.round(y);
                    y += node.height + gap;
                });
            } else {
                const gap = 38;
                const totalWidth = group.reduce((sum, node) => sum + node.width, 0) + gap * (group.length - 1);
                let x = Math.max(34, (CANVAS_MIN_WIDTH - totalWidth) / 2);
                group.forEach((node) => {
                    node.x = Math.round(x);
                    node.y = Math.round(86 + key * 155);
                    x += node.width + gap;
                });
            }
        });
    }

    function getDiagramBounds() {
        const items = [];
        state.local.nodes.forEach((node) => items.push({ x: node.x, y: node.y, w: node.width, h: node.height }));
        state.local.backgrounds.forEach((bg) => items.push({ x: bg.x, y: bg.y, w: bg.width, h: bg.height }));
        if (!items.length) {
            return { minX: 0, minY: 0, maxX: CANVAS_MIN_WIDTH, maxY: CANVAS_MIN_HEIGHT };
        }
        return {
            minX: Math.min(...items.map((item) => item.x)),
            minY: Math.min(...items.map((item) => item.y)),
            maxX: Math.max(...items.map((item) => item.x + item.w)),
            maxY: Math.max(...items.map((item) => item.y + item.h))
        };
    }

    function updateCanvasSize() {
        applyZoomedCanvasSize();
    }

    function semanticNodeColor(node) {
        const map = {
            terminator: { fill: '#ecfdf5', stroke: '#059669', font: '#064e3b' },
            decision: { fill: '#fff7ed', stroke: '#ea580c', font: '#7c2d12' },
            data: { fill: '#e0f2fe', stroke: '#0284c7', font: '#0c4a6e' },
            database: { fill: '#ecfeff', stroke: '#0891b2', font: '#164e63' },
            dataset: { fill: '#ecfeff', stroke: '#0891b2', font: '#164e63' },
            cache: { fill: '#fef9c3', stroke: '#ca8a04', font: '#713f12' },
            document: { fill: '#f8fafc', stroke: '#64748b', font: '#334155' },
            paper: { fill: '#f8fafc', stroke: '#64748b', font: '#334155' },
            model: { fill: '#eef2ff', stroke: '#4f46e5', font: '#312e81' },
            api: { fill: '#eef2ff', stroke: '#4f46e5', font: '#312e81' },
            service: { fill: '#f5f3ff', stroke: '#7c3aed', font: '#4c1d95' },
            server: { fill: '#f8fafc', stroke: '#475569', font: '#0f172a' },
            web: { fill: '#e0f2fe', stroke: '#0284c7', font: '#0c4a6e' },
            mobile: { fill: '#f0fdf4', stroke: '#16a34a', font: '#14532d' },
            message: { fill: '#fff7ed', stroke: '#ea580c', font: '#7c2d12' },
            queue: { fill: '#ecfeff', stroke: '#0891b2', font: '#164e63' },
            training: { fill: '#f5f3ff', stroke: '#7c3aed', font: '#4c1d95' },
            evaluation: { fill: '#fefce8', stroke: '#ca8a04', font: '#713f12' },
            experiment: { fill: '#fdf2f8', stroke: '#db2777', font: '#831843' },
            note: { fill: '#fff7ed', stroke: '#f97316', font: '#7c2d12' },
            callout: { fill: '#fff7ed', stroke: '#f97316', font: '#7c2d12' },
            text: { fill: 'transparent', stroke: state.colors.stroke, font: state.colors.font }
        };
        return map[node.type] || { fill: state.colors.fill, stroke: state.colors.stroke, font: state.colors.font };
    }

    function applyColorsToAll(colors) {
        state.local.nodes.forEach((node) => {
            if (node.type !== 'text') node.fill = colors.fill;
            node.stroke = colors.stroke;
            node.font = colors.font;
        });
        state.local.edges.forEach((edge) => {
            edge.stroke = colors.stroke;
        });
        render();
    }

    function buildPalette(baseHex, count) {
        const base = hexToHsl(baseHex);
        const result = [];
        const total = Math.max(3, count);
        for (let i = 0; i < total; i += 1) {
            const hue = (base.h + i * 28) % 360;
            const stroke = hslToHex(hue, Math.max(55, base.s), Math.max(34, Math.min(58, base.l)));
            const fill = hslToHex(hue, Math.max(45, base.s - 18), 90);
            result.push({ fill, stroke, font: readableTextColor(fill) });
        }
        return result;
    }

    async function doSave() {
        updateXmlSnapshot();
        const title = $('#diagramTitle').value.trim() || '未命名流程图';
        const projectId = parseInt($('#diagramProject').value, 10) || 0;
        const body = {
            title,
            xml_data: state.xml,
            project_id: projectId > 0 ? projectId : null,
            layout_direction: state.layoutDirection || 'TB',
            color_scheme: savedSchemeValue()
        };
        const url = state.diagramId ? '/api/diagrams/' + state.diagramId : '/api/diagrams';
        const method = state.diagramId ? 'PUT' : 'POST';
        try {
            const resp = await fetch(url, {
                method,
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(body)
            });
            const data = await resp.json();
            if (!resp.ok || !data.ok) {
                throw new Error(data.detail || '保存失败');
            }
            if (!state.diagramId && data.diagram_id) {
                state.diagramId = data.diagram_id;
                history.replaceState(null, '', '/diagrams/' + state.diagramId + '/edit');
            }
            showToast();
            setStatus('已保存到本地数据库', 'ok');
        } catch (error) {
            setStatus(error.message || '保存失败', 'error');
            alert(error.message || '保存失败');
        }
    }

    function exportDiagram(format) {
        updateXmlSnapshot();
        const filename = getFileName();
        if (format === 'xml') {
            downloadBlob(new Blob([state.xml], { type: 'application/xml;charset=utf-8' }), filename + '.drawio.xml');
            return;
        }
        if (format === 'json') {
            downloadBlob(new Blob([exportLocalJson()], { type: 'application/json;charset=utf-8' }), filename + '.flow.json');
            return;
        }
        if (format === 'mermaid') {
            downloadBlob(new Blob([exportMermaid()], { type: 'text/markdown;charset=utf-8' }), filename + '.mmd');
            return;
        }
        if (format === 'vdx') {
            downloadBlob(new Blob([exportVdx()], { type: 'application/xml;charset=utf-8' }), filename + '.vdx');
            return;
        }
        if (format === 'vsdx') {
            downloadBlob(exportVsdx(), filename + '.vsdx');
            return;
        }
        if (format === 'svg') {
            downloadBlob(new Blob([serializeSvg()], { type: 'image/svg+xml;charset=utf-8' }), filename + '.svg');
            return;
        }
        if (format === 'eps') {
            downloadBlob(new Blob([exportEps()], { type: 'application/postscript;charset=utf-8' }), filename + '.eps');
            return;
        }
        if (format === 'html') {
            const html = '<!doctype html><html><head><meta charset="utf-8"><title>' + escapeText(filename) + '</title></head><body style="margin:0;background:#f8fafc">' + serializeSvg() + '</body></html>';
            downloadBlob(new Blob([html], { type: 'text/html;charset=utf-8' }), filename + '.html');
            return;
        }
        if (format === 'pdf') {
            const win = window.open('', '_blank');
            if (!win) {
                alert('浏览器阻止了打印窗口，请允许弹窗后重试');
                return;
            }
            win.document.write('<!doctype html><html><head><meta charset="utf-8"><title>' + escapeText(filename) + '</title></head><body style="margin:0">' + serializeSvg() + '<script>window.onload=function(){window.print()};<\/script></body></html>');
            win.document.close();
            return;
        }
        if (format === 'png' || format === 'jpeg') {
            exportRaster(format, filename);
        }
    }

    function serializeSvg() {
        const cloned = canvas.cloneNode(true);
        cloned.setAttribute('xmlns', 'http://www.w3.org/2000/svg');
        const bounds = getDiagramBounds();
        const width = Math.max(CANVAS_MIN_WIDTH, bounds.maxX - bounds.minX + CANVAS_PADDING * 2);
        const height = Math.max(CANVAS_MIN_HEIGHT, bounds.maxY - bounds.minY + CANVAS_PADDING * 2);
        cloned.setAttribute('width', String(Math.round(width)));
        cloned.setAttribute('height', String(Math.round(height)));
        cloned.style.backgroundColor = '#ffffff';
        const metadata = document.createElementNS('http://www.w3.org/2000/svg', 'metadata');
        metadata.setAttribute('id', 'scifiglab-data');
        metadata.textContent = exportLocalJson();
        cloned.insertBefore(metadata, cloned.firstChild);
        return new XMLSerializer().serializeToString(cloned);
    }

    function exportLocalJson() {
        return JSON.stringify({
            format: 'scifiglab-flow',
            version: 1,
            canvas: { width: CANVAS_MIN_WIDTH, height: CANVAS_MIN_HEIGHT },
            layoutDirection: state.layoutDirection || 'TB',
            colorScheme: savedSchemeValue(),
            nodes: state.local.nodes,
            edges: state.local.edges,
            backgrounds: state.local.backgrounds
        }, null, 2);
    }

    function loadJsonToState(content) {
        let data;
        try {
            data = JSON.parse(content);
        } catch (error) {
            return false;
        }
        const nodes = Array.isArray(data.nodes) ? data.nodes : (data.local && Array.isArray(data.local.nodes) ? data.local.nodes : []);
        if (!nodes.length) return false;
        state.local.nodes = nodes.map((node) => normalizeNode(node));
        state.local.edges = (Array.isArray(data.edges) ? data.edges : []).filter((edge) => edge.source && edge.target).map((edge) => ({
            id: edge.id || uniqueId('e'),
            source: edge.source,
            target: edge.target,
            type: edge.type || 'orthogonal',
            stroke: edge.stroke || state.colors.stroke
        }));
        state.local.backgrounds = Array.isArray(data.backgrounds) ? data.backgrounds.map((bg) => ({
            id: bg.id || uniqueId('bg'),
            href: bg.href || '',
            x: Number(bg.x) || 0,
            y: Number(bg.y) || 0,
            width: Number(bg.width) || 300,
            height: Number(bg.height) || 200,
            opacity: Number(bg.opacity) || 0.3,
            name: bg.name || '底图'
        })) : [];
        state.layoutDirection = data.layoutDirection || state.layoutDirection || 'TB';
        selectNone();
        return true;
    }

    function exportMermaid() {
        const dir = state.layoutDirection === 'LR' ? 'LR' : 'TD';
        const idMap = new Map();
        state.local.nodes.forEach((node, index) => idMap.set(node.id, 'N' + (index + 1)));
        const lines = ['flowchart ' + dir];
        state.local.nodes.forEach((node) => {
            lines.push('    ' + idMap.get(node.id) + mermaidShape(node));
        });
        state.local.edges.forEach((edge) => {
            if (idMap.has(edge.source) && idMap.has(edge.target)) {
                lines.push('    ' + idMap.get(edge.source) + ' --> ' + idMap.get(edge.target));
            }
        });
        return lines.join('\n') + '\n';
    }

    function mermaidShape(node) {
        const label = String(node.label || defaultLabel(node.type)).replace(/"/g, '\\"');
        if (node.type === 'terminator') return '(["' + label + '"])';
        if (node.type === 'decision') return '{"' + label + '"}';
        if (node.type === 'data') return '[/"' + label + '"/]';
        if (node.type === 'note' || node.type === 'text') return '["' + label + '"]';
        return '["' + label + '"]';
    }

    function loadMermaidToState(content) {
        if (!/^\s*(flowchart|graph)\s+/m.test(content || '')) return false;
        const lines = content.split(/\r?\n/).map((line) => line.replace(/%%.*$/, '').trim()).filter(Boolean);
        const header = lines.find((line) => /^(flowchart|graph)\s+/i.test(line));
        const direction = header && /\s(LR|RL)\b/i.test(header) ? 'LR' : 'TB';
        const nodeMap = new Map();
        const edges = [];

        lines.forEach((line) => {
            if (/^(flowchart|graph)\s+/i.test(line) || line.startsWith('subgraph') || line === 'end') return;
            const edgeMatch = line.match(/(.+?)\s*(?:-->|---|==>|-.->)\s*(.+)/);
            if (edgeMatch) {
                const left = parseMermaidToken(edgeMatch[1]);
                const right = parseMermaidToken(edgeMatch[2]);
                if (left) ensureMermaidNode(nodeMap, left);
                if (right) ensureMermaidNode(nodeMap, right);
                if (left && right) edges.push({ sourceKey: left.key, targetKey: right.key });
                return;
            }
            const single = parseMermaidToken(line);
            if (single) ensureMermaidNode(nodeMap, single);
        });

        if (!nodeMap.size) return false;
        const nodes = Array.from(nodeMap.values());
        layoutNodes(nodes, direction);
        state.local.nodes = nodes;
        state.local.edges = edges
            .map((edge) => {
                const source = nodeMap.get(edge.sourceKey);
                const target = nodeMap.get(edge.targetKey);
                return source && target ? makeEdge(source.id, target.id) : null;
            })
            .filter(Boolean);
        state.local.backgrounds = [];
        state.layoutDirection = direction;
        selectNone();
        return true;
    }

    function parseMermaidToken(token) {
        const clean = token.replace(/\|.*?\|/g, '').trim().replace(/;$/, '');
        const match = clean.match(/^([A-Za-z][\w-]*)(.*)$/);
        if (!match) return null;
        const key = match[1];
        const rest = match[2].trim();
        let type = 'process';
        let label = key;
        const patterns = [
            { re: /^\(\[\s*"?(.+?)"?\s*\]\)$/, type: 'terminator' },
            { re: /^\(\s*"?(.+?)"?\s*\)$/, type: 'terminator' },
            { re: /^\{\s*"?(.+?)"?\s*\}$/, type: 'decision' },
            { re: /^\[\/\s*"?(.+?)"?\s*\/\]$/, type: 'data' },
            { re: /^\[\s*"?(.+?)"?\s*\]$/, type: 'process' }
        ];
        for (const item of patterns) {
            const m = rest.match(item.re);
            if (m) {
                type = item.type;
                label = m[1];
                break;
            }
        }
        return { key, type, label: label.replace(/\\"/g, '"') };
    }

    function ensureMermaidNode(nodeMap, parsed) {
        if (nodeMap.has(parsed.key)) {
            const existing = nodeMap.get(parsed.key);
            if (parsed.label && parsed.label !== parsed.key) existing.label = parsed.label;
            if (parsed.type) existing.type = parsed.type;
            return existing;
        }
        const size = defaultSize(parsed.type);
        const node = makeNode(parsed.type, 0, 0, parsed.label, size.width, size.height, state.colors);
        nodeMap.set(parsed.key, node);
        return node;
    }

    function loadSvgToState(content) {
        const doc = new DOMParser().parseFromString(content, 'image/svg+xml');
        if (doc.querySelector('parsererror')) return false;
        const metadata = doc.querySelector('#scifiglab-data');
        if (metadata && loadJsonToState(metadata.textContent || '')) return true;

        const textItems = Array.from(doc.getElementsByTagName('text')).map((text) => ({
            x: Number(text.getAttribute('x')) || 0,
            y: Number(text.getAttribute('y')) || 0,
            label: text.textContent.trim()
        })).filter((item) => item.label);
        const nodes = [];

        Array.from(doc.getElementsByTagName('rect')).forEach((rect) => {
            const width = Number(rect.getAttribute('width')) || 0;
            const height = Number(rect.getAttribute('height')) || 0;
            const x = Number(rect.getAttribute('x')) || 0;
            const y = Number(rect.getAttribute('y')) || 0;
            if (width < 30 || height < 24) return;
            const type = Number(rect.getAttribute('rx') || 0) > height * 0.25 ? 'terminator' : 'process';
            nodes.push(nodeFromSvgBox(type, x, y, width, height, rect, textItems));
        });

        Array.from(doc.getElementsByTagName('ellipse')).forEach((ellipse) => {
            const cx = Number(ellipse.getAttribute('cx')) || 0;
            const cy = Number(ellipse.getAttribute('cy')) || 0;
            const rx = Number(ellipse.getAttribute('rx')) || 0;
            const ry = Number(ellipse.getAttribute('ry')) || 0;
            if (rx < 20 || ry < 14) return;
            nodes.push(nodeFromSvgBox('terminator', cx - rx, cy - ry, rx * 2, ry * 2, ellipse, textItems));
        });

        Array.from(doc.getElementsByTagName('polygon')).forEach((poly) => {
            const points = parseSvgPoints(poly.getAttribute('points') || '');
            if (points.length < 3) return;
            const box = pointsBox(points);
            if (box.width < 30 || box.height < 24) return;
            const type = points.length === 4 && Math.abs(points[0].x - points[2].x) < box.width * 0.18 ? 'decision' : 'data';
            nodes.push(nodeFromSvgBox(type, box.x, box.y, box.width, box.height, poly, textItems));
        });

        if (!nodes.length) return false;
        const merged = dedupeNodes(nodes);
        state.local.nodes = merged;
        state.local.edges = inferEdgesFromSvg(doc, merged);
        state.local.backgrounds = [];
        selectNone();
        return true;
    }

    function nodeFromSvgBox(type, x, y, width, height, element, textItems) {
        const labelItem = textItems.find((item) => item.x >= x - 4 && item.x <= x + width + 4 && item.y >= y - 4 && item.y <= y + height + 18);
        return makeNode(type, x, y, labelItem ? labelItem.label : defaultLabel(type), width, height, {
            fill: normalizePaint(element.getAttribute('fill')) || state.colors.fill,
            stroke: normalizePaint(element.getAttribute('stroke')) || state.colors.stroke,
            font: state.colors.font
        });
    }

    function inferEdgesFromSvg(doc, nodes) {
        const edges = [];
        const seen = new Set();
        const addByPoints = (a, b) => {
            const source = nearestNode(nodes, a);
            const target = nearestNode(nodes, b);
            if (!source || !target || source.id === target.id) return;
            const key = source.id + '->' + target.id;
            if (!seen.has(key)) {
                seen.add(key);
                edges.push(makeEdge(source.id, target.id));
            }
        };
        Array.from(doc.getElementsByTagName('line')).forEach((line) => {
            addByPoints(
                { x: Number(line.getAttribute('x1')) || 0, y: Number(line.getAttribute('y1')) || 0 },
                { x: Number(line.getAttribute('x2')) || 0, y: Number(line.getAttribute('y2')) || 0 }
            );
        });
        Array.from(doc.getElementsByTagName('polyline')).forEach((line) => {
            const points = parseSvgPoints(line.getAttribute('points') || '');
            if (points.length >= 2) addByPoints(points[0], points[points.length - 1]);
        });
        Array.from(doc.getElementsByTagName('path')).forEach((path) => {
            const nums = (path.getAttribute('d') || '').match(/-?\d+(?:\.\d+)?/g);
            if (nums && nums.length >= 4) {
                addByPoints({ x: Number(nums[0]), y: Number(nums[1]) }, { x: Number(nums[nums.length - 2]), y: Number(nums[nums.length - 1]) });
            }
        });
        return edges;
    }

    function exportEps() {
        const lines = [
            '%!PS-Adobe-3.0 EPSF-3.0',
            '%%BoundingBox: 0 0 ' + CANVAS_MIN_WIDTH + ' ' + CANVAS_MIN_HEIGHT,
            '/Arial findfont 14 scalefont setfont',
            '1 1 1 setrgbcolor 0 0 ' + CANVAS_MIN_WIDTH + ' ' + CANVAS_MIN_HEIGHT + ' rectfill'
        ];
        state.local.edges.forEach((edge) => {
            const source = getNode(edge.source);
            const target = getNode(edge.target);
            if (!source || !target) return;
            const a = anchorPoint(source, target);
            const b = anchorPoint(target, source);
            const rgb = hexToRgb(edge.stroke || state.colors.stroke) || { r: 71, g: 85, b: 105 };
            lines.push((rgb.r / 255) + ' ' + (rgb.g / 255) + ' ' + (rgb.b / 255) + ' setrgbcolor');
            lines.push('2 setlinewidth newpath ' + a.x + ' ' + (CANVAS_MIN_HEIGHT - a.y) + ' moveto ' + b.x + ' ' + (CANVAS_MIN_HEIGHT - b.y) + ' lineto stroke');
        });
        state.local.nodes.forEach((node) => {
            const fill = hexToRgb(node.fill) || { r: 255, g: 255, b: 255 };
            const stroke = hexToRgb(node.stroke) || { r: 71, g: 85, b: 105 };
            lines.push((fill.r / 255) + ' ' + (fill.g / 255) + ' ' + (fill.b / 255) + ' setrgbcolor');
            lines.push('newpath ' + node.x + ' ' + (CANVAS_MIN_HEIGHT - node.y - node.height) + ' ' + node.width + ' ' + node.height + ' rectfill');
            lines.push((stroke.r / 255) + ' ' + (stroke.g / 255) + ' ' + (stroke.b / 255) + ' setrgbcolor');
            lines.push('2 setlinewidth newpath ' + node.x + ' ' + (CANVAS_MIN_HEIGHT - node.y - node.height) + ' ' + node.width + ' ' + node.height + ' rectstroke');
            lines.push('0 0 0 setrgbcolor ' + (node.x + 10) + ' ' + (CANVAS_MIN_HEIGHT - node.y - node.height / 2) + ' moveto (' + psEscape(node.label || '') + ') show');
        });
        lines.push('showpage', '%%EOF');
        return lines.join('\n');
    }

    function exportRaster(format, filename) {
        const svgText = serializeSvg();
        const blob = new Blob([svgText], { type: 'image/svg+xml;charset=utf-8' });
        const url = URL.createObjectURL(blob);
        const img = new Image();
        img.onload = () => {
            const c = document.createElement('canvas');
            c.width = CANVAS_MIN_WIDTH;
            c.height = CANVAS_MIN_HEIGHT;
            const ctx = c.getContext('2d');
            ctx.fillStyle = '#ffffff';
            ctx.fillRect(0, 0, c.width, c.height);
            ctx.drawImage(img, 0, 0);
            URL.revokeObjectURL(url);
            c.toBlob((out) => {
                downloadBlob(out, filename + (format === 'jpeg' ? '.jpg' : '.png'));
            }, format === 'jpeg' ? 'image/jpeg' : 'image/png', 0.94);
        };
        img.onerror = () => {
            URL.revokeObjectURL(url);
            alert('图片导出失败，请尝试 SVG 格式');
        };
        img.src = url;
    }

    let pendingFile = null;
    let pendingImageDataUrl = null;

    function handleFileSelect(file) {
        pendingFile = file;
        $('#filePreviewName').textContent = '已选择: ' + file.name + ' (' + (file.size / 1024).toFixed(1) + ' KB)';
        $('#filePreview').style.display = '';
    }

    async function importSelectedFile() {
        if (!pendingFile) {
            alert('请先选择文件');
            return;
        }
        const beforeImport = snapshotState();
        const ext = pendingFile.name.split('.').pop().toLowerCase();
        try {
            if (ext === 'vsdx') {
                setStatus('正在读取 VSDX 文件...', 'busy');
                const buffer = await readFileAsArrayBuffer(pendingFile);
                const imported = await loadVsdxToState(buffer);
                if (!imported) throw new Error('没有在 VSDX 中识别到可编辑图形');
                pushSnapshotIfChanged(beforeImport, '导入文件');
                render();
                closeImportModal();
                setStatus('已导入基础 VSDX 图形', 'ok');
                return;
            }

            const content = await readFileAsText(pendingFile);
            const lower = ext === 'drawio' ? 'xml' : ext;
            let imported = false;
            if (lower === 'svg') imported = loadSvgToState(content);
            else if (lower === 'json') imported = loadJsonToState(content);
            else if (lower === 'mmd' || lower === 'mermaid') imported = loadMermaidToState(content);
            else if (lower === 'vdx') imported = loadVdxToState(content);
            else imported = loadXmlToState(content) || loadMermaidToState(content) || loadJsonToState(content) || loadVdxToState(content);
            if (!imported && (ext === 'drawio' || lower === 'xml')) {
                imported = await loadCompressedDrawioToState(content);
            }

            if (imported) {
                pushSnapshotIfChanged(beforeImport, '导入文件');
                render();
                setStatus('已导入并转换为本地可编辑图形', 'ok');
                closeImportModal();
            } else if (lower === 'svg') {
                const dataUrl = 'data:image/svg+xml;charset=utf-8,' + encodeURIComponent(content);
                addBackgroundFromDataUrl(dataUrl, pendingFile.name);
                closeImportModal();
            } else {
                alert('没有识别到可编辑流程图。建议使用本地 XML、未压缩 draw.io XML、Mermaid、JSON、基础 SVG、VDX 或基础 VSDX。');
            }
        } catch (error) {
            setStatus('导入失败', 'error');
            alert('导入失败：' + (error.message || '未知错误'));
        }
    }

    function handleImageSelect(file) {
        const reader = new FileReader();
        reader.onload = (event) => {
            pendingImageDataUrl = event.target.result;
            $('#imagePreviewImg').src = pendingImageDataUrl;
            $('#imagePreview').style.display = '';
        };
        reader.readAsDataURL(file);
    }

    function importImageAsBackground() {
        if (!pendingImageDataUrl) return;
        addBackgroundFromDataUrl(pendingImageDataUrl, '图片底图');
        closeImportModal();
    }

    async function recognizeImageToShapes() {
        if (!pendingImageDataUrl) return;
        setStatus('正在本地识别图片几何结构...', 'busy');
        try {
            const before = snapshotState();
            const result = await recognizeFlowchartImage(pendingImageDataUrl);
            state.local.nodes = result.nodes;
            state.local.edges = result.edges;
            state.local.backgrounds = result.backgrounds;
            selectNone();
            pushSnapshotIfChanged(before, '图片识别');
            render();
            closeImportModal();
            const msg = result.detected
                ? '已识别 ' + result.nodes.length + ' 个可编辑图形、' + result.edges.length + ' 条连线'
                : '未检测到清晰轮廓，已生成可编辑骨架并保留底图';
            setStatus(msg, result.detected ? 'ok' : 'busy');
        } catch (error) {
            setStatus('图片识别失败', 'error');
            alert('图片识别失败：' + (error.message || '未知错误'));
        }
    }

    function addBackgroundFromDataUrl(dataUrl, name) {
        const before = snapshotState();
        loadImage(dataUrl).then((img) => {
            const scale = Math.min(CANVAS_MIN_WIDTH / img.width, CANVAS_MIN_HEIGHT / img.height, 1);
            const width = Math.round(img.width * scale);
            const height = Math.round(img.height * scale);
            state.local.backgrounds.push({
                id: uniqueId('bg'),
                href: dataUrl,
                x: 60,
                y: 50,
                width,
                height,
                opacity: 0.36,
                name: name || '底图'
            });
            pushSnapshotIfChanged(before, '导入图片底图');
            render();
            setStatus('已导入底图，可以在上方拖拽图形描摹', 'ok');
        });
    }

    async function recognizeFlowchartImage(dataUrl) {
        const img = await loadImage(dataUrl);
        const scanScale = Math.min(CANVAS_MIN_WIDTH / img.width, CANVAS_MIN_HEIGHT / img.height, 1);
        const width = Math.max(1, Math.round(img.width * scanScale));
        const height = Math.max(1, Math.round(img.height * scanScale));
        const c = document.createElement('canvas');
        c.width = width;
        c.height = height;
        const ctx = c.getContext('2d', { willReadFrequently: true });
        ctx.drawImage(img, 0, 0, width, height);
        const pixels = ctx.getImageData(0, 0, width, height).data;
        const binary = new Uint8Array(width * height);
        const colorBinary = new Uint8Array(width * height);
        const darkBinary = new Uint8Array(width * height);
        for (let i = 0; i < width * height; i += 1) {
            const r = pixels[i * 4];
            const g = pixels[i * 4 + 1];
            const b = pixels[i * 4 + 2];
            const a = pixels[i * 4 + 3];
            const max = Math.max(r, g, b);
            const min = Math.min(r, g, b);
            const brightness = (r + g + b) / 3;
            const saturation = max === 0 ? 0 : (max - min) / max;
            const isDark = a > 24 && brightness < 205;
            const isColored = a > 24 && brightness < 248 && saturation > 0.12;
            darkBinary[i] = isDark ? 1 : 0;
            colorBinary[i] = isColored ? 1 : 0;
            binary[i] = isDark || isColored ? 1 : 0;
        }

        const colorComps = connectedComponents(colorBinary, width, height);
        const combinedComps = connectedComponents(binary, width, height);
        const pageArea = width * height;
        let binaryForNodes = colorBinary;
        let nodeBoxes = colorComps
            .filter((box) => {
                const w = box.maxX - box.minX + 1;
                const h = box.maxY - box.minY + 1;
                const area = w * h;
                const aspect = w / Math.max(1, h);
                return box.count > 90 && area > 900 && area < pageArea * 0.72 &&
                    w > 34 && h > 24 && aspect < 5.2 && aspect > 0.2;
            })
            .sort((a, b) => (boxArea(b) - boxArea(a)));

        if (nodeBoxes.length < 2) {
            binaryForNodes = binary;
            nodeBoxes = combinedComps
                .filter((box) => {
                    const w = box.maxX - box.minX + 1;
                    const h = box.maxY - box.minY + 1;
                    const area = w * h;
                    const aspect = w / Math.max(1, h);
                    return box.count > 90 && area > 900 && area < pageArea * 0.72 &&
                        w > 34 && h > 24 && aspect < 5.2 && aspect > 0.2;
                })
                .sort((a, b) => (boxArea(b) - boxArea(a)));
        }

        const filtered = [];
        nodeBoxes.forEach((box) => {
            const duplicate = filtered.some((existing) => overlapRatio(box, existing) > 0.58 || containsBox(existing, box, 6));
            if (!duplicate) filtered.push(box);
        });

        const lineBoxes = connectedComponents(darkBinary, width, height).filter((box) => {
            const w = box.maxX - box.minX + 1;
            const h = box.maxY - box.minY + 1;
            const aspect = w / Math.max(1, h);
            const area = w * h;
            return box.count > 45 && area > 220 && (aspect > 4.2 || aspect < 0.24);
        });

        const editorScale = Math.min(CANVAS_MIN_WIDTH / img.width, CANVAS_MIN_HEIGHT / img.height, 1);
        const factor = editorScale / scanScale;
        const offsetX = 70;
        const offsetY = 55;
        const backgrounds = [{
            id: uniqueId('bg'),
            href: dataUrl,
            x: offsetX,
            y: offsetY,
            width: Math.round(img.width * editorScale),
            height: Math.round(img.height * editorScale),
            opacity: 0.16,
            name: '识别参考图'
        }];

        let nodes = filtered
            .slice(0, 24)
            .map((box) => boxToNode(box, binaryForNodes, width, height, factor, offsetX, offsetY))
            .filter(Boolean)
            .sort((a, b) => (a.y - b.y) || (a.x - b.x));

        if (nodes.length < 2) {
            return scaffoldFromImage(dataUrl, img);
        }

        nodes = nodes.map((node, index) => {
            if (index === 0 && node.type === 'process') {
                node.type = 'terminator';
                node.label = '开始';
            } else if (index === nodes.length - 1 && node.type === 'process') {
                node.type = 'terminator';
                node.label = '结束';
            } else if (!node.label) {
                node.label = node.type === 'decision' ? '判断 ' + (index + 1) : '步骤 ' + (index + 1);
            }
            return node;
        });

        let edges = inferEdgesFromLines(nodes, lineBoxes, factor, offsetX, offsetY);
        if (!edges.length) {
            edges = [];
            nodes.forEach((node, index) => {
                if (index < nodes.length - 1) edges.push(makeEdge(node.id, nodes[index + 1].id));
            });
        }

        return { nodes, edges, backgrounds, detected: true };
    }

    function boxToNode(box, binary, width, height, factor, offsetX, offsetY) {
        const w = box.maxX - box.minX + 1;
        const h = box.maxY - box.minY + 1;
        const x = Math.round(offsetX + box.minX * factor);
        const y = Math.round(offsetY + box.minY * factor);
        const nodeW = clamp(Math.round(w * factor), 90, 260);
        const nodeH = clamp(Math.round(h * factor), 44, 150);
        const type = detectShapeType(box, binary, width, height);
        const node = makeNode(type, x, y, '', nodeW, nodeH, state.colors);
        node.label = type === 'decision' ? '判断' : '步骤';
        return node;
    }

    function detectShapeType(box, binary, width, height) {
        const w = box.maxX - box.minX + 1;
        const h = box.maxY - box.minY + 1;
        const aspect = w / Math.max(1, h);
        const padX = Math.max(2, Math.floor(w * 0.16));
        const padY = Math.max(2, Math.floor(h * 0.16));
        const corner = [
            density(binary, width, box.minX, box.minY, box.minX + padX, box.minY + padY),
            density(binary, width, box.maxX - padX, box.minY, box.maxX, box.minY + padY),
            density(binary, width, box.minX, box.maxY - padY, box.minX + padX, box.maxY),
            density(binary, width, box.maxX - padX, box.maxY - padY, box.maxX, box.maxY)
        ].reduce((sum, value) => sum + value, 0) / 4;
        const center = density(binary, width, box.minX + padX, box.minY + padY, box.maxX - padX, box.maxY - padY);
        if (corner < center * 0.48 && aspect > 0.65 && aspect < 1.75) return 'decision';
        if (aspect > 2.15 && corner < center * 0.85) return 'terminator';
        return 'process';
    }

    function inferEdgesFromLines(nodes, lineBoxes, factor, offsetX, offsetY) {
        const edges = [];
        const seen = new Set();
        lineBoxes.slice(0, 40).forEach((box) => {
            const w = box.maxX - box.minX + 1;
            const h = box.maxY - box.minY + 1;
            const horizontal = w >= h;
            const p1 = {
                x: offsetX + (horizontal ? box.minX : (box.minX + box.maxX) / 2) * factor,
                y: offsetY + (horizontal ? (box.minY + box.maxY) / 2 : box.minY) * factor
            };
            const p2 = {
                x: offsetX + (horizontal ? box.maxX : (box.minX + box.maxX) / 2) * factor,
                y: offsetY + (horizontal ? (box.minY + box.maxY) / 2 : box.maxY) * factor
            };
            const a = nearestNode(nodes, p1);
            const b = nearestNode(nodes, p2);
            if (a && b && a.id !== b.id) {
                const source = (a.y + a.height / 2 <= b.y + b.height / 2 || a.x < b.x) ? a : b;
                const target = source === a ? b : a;
                const key = source.id + '->' + target.id;
                if (!seen.has(key)) {
                    seen.add(key);
                    edges.push(makeEdge(source.id, target.id));
                }
            }
        });
        return edges;
    }

    function scaffoldFromImage(dataUrl, img) {
        const scale = Math.min(820 / img.width, 360 / img.height, 1);
        const bg = {
            id: uniqueId('bg'),
            href: dataUrl,
            x: 60,
            y: 45,
            width: Math.round(img.width * scale),
            height: Math.round(img.height * scale),
            opacity: 0.24,
            name: '识别参考图'
        };
        const y = bg.y + bg.height + 70;
        const colors = state.colors;
        const nodes = [
            makeNode('terminator', 610, y, '开始', 160, 50, colors),
            makeNode('process', 590, y + 100, '步骤 1', 200, 62, colors),
            makeNode('decision', 610, y + 220, '判断', 160, 90, colors),
            makeNode('terminator', 610, y + 380, '结束', 160, 50, colors)
        ];
        return {
            nodes,
            edges: [
                makeEdge(nodes[0].id, nodes[1].id),
                makeEdge(nodes[1].id, nodes[2].id),
                makeEdge(nodes[2].id, nodes[3].id)
            ],
            backgrounds: [bg],
            detected: false
        };
    }

    function connectedComponents(binary, width, height) {
        const visited = new Uint8Array(binary.length);
        const comps = [];
        const stack = [];
        const dirs = [1, -1, width, -width];
        for (let index = 0; index < binary.length; index += 1) {
            if (!binary[index] || visited[index]) continue;
            let minX = width;
            let minY = height;
            let maxX = 0;
            let maxY = 0;
            let count = 0;
            visited[index] = 1;
            stack.push(index);
            while (stack.length) {
                const cur = stack.pop();
                const x = cur % width;
                const y = Math.floor(cur / width);
                minX = Math.min(minX, x);
                maxX = Math.max(maxX, x);
                minY = Math.min(minY, y);
                maxY = Math.max(maxY, y);
                count += 1;
                for (let d = 0; d < dirs.length; d += 1) {
                    const next = cur + dirs[d];
                    if (next < 0 || next >= binary.length || visited[next] || !binary[next]) continue;
                    if ((dirs[d] === 1 && x === width - 1) || (dirs[d] === -1 && x === 0)) continue;
                    visited[next] = 1;
                    stack.push(next);
                }
            }
            comps.push({ minX, minY, maxX, maxY, count });
        }
        return comps;
    }

    function loadXmlToState(xml) {
        const graphXml = extractGraphXml(xml);
        if (!graphXml) return false;
        const doc = new DOMParser().parseFromString(graphXml, 'text/xml');
        if (doc.querySelector('parsererror')) return false;
        const model = doc.querySelector('mxGraphModel');
        if (!model) return false;
        const cells = Array.from(model.querySelectorAll('mxCell'));
        const nodes = [];
        const edges = [];
        const backgrounds = [];
        const nodeIds = new Set();

        cells.forEach((cell) => {
            if (cell.getAttribute('vertex') !== '1') return;
            const geo = cell.querySelector('mxGeometry');
            if (!geo) return;
            const style = parseStyle(cell.getAttribute('style') || '');
            const x = parseFloat(geo.getAttribute('x') || '0');
            const y = parseFloat(geo.getAttribute('y') || '0');
            const width = parseFloat(geo.getAttribute('width') || '140');
            const height = parseFloat(geo.getAttribute('height') || '60');
            if (style.shape === 'image' || style.image) {
                backgrounds.push({
                    id: cell.getAttribute('id') || uniqueId('bg'),
                    href: decodeStyleValue(style.image || ''),
                    x,
                    y,
                    width,
                    height,
                    opacity: style.opacity ? parseFloat(style.opacity) / 100 : 0.35,
                    name: cell.getAttribute('value') || '底图'
                });
                return;
            }
            const id = cell.getAttribute('id') || uniqueId('n');
            const node = {
                id,
                type: typeFromStyle(style),
                label: cell.getAttribute('value') || defaultLabel(typeFromStyle(style)),
                x,
                y,
                width: Math.max(70, width),
                height: Math.max(34, height),
                fill: style.fillColor || state.colors.fill,
                stroke: style.strokeColor || state.colors.stroke,
                font: style.fontColor || state.colors.font
            };
            nodes.push(node);
            nodeIds.add(id);
        });

        cells.forEach((cell) => {
            if (cell.getAttribute('edge') !== '1') return;
            const source = cell.getAttribute('source');
            const target = cell.getAttribute('target');
            if (!nodeIds.has(source) || !nodeIds.has(target)) return;
            const style = parseStyle(cell.getAttribute('style') || '');
            edges.push({
                id: cell.getAttribute('id') || uniqueId('e'),
                source,
                target,
                type: edgeTypeFromStyle(style),
                stroke: style.strokeColor || state.colors.stroke
            });
        });

        state.local.nodes = nodes;
        state.local.edges = edges;
        state.local.backgrounds = backgrounds;
        selectNone();
        return nodes.length > 0 || backgrounds.length > 0;
    }

    function extractGraphXml(xml) {
        if (!xml || typeof xml !== 'string') return '';
        const directStart = xml.indexOf('<mxGraphModel');
        if (directStart !== -1) {
            const end = xml.indexOf('</mxGraphModel>', directStart);
            if (end !== -1) return xml.slice(directStart, end + '</mxGraphModel>'.length);
        }
        const doc = new DOMParser().parseFromString(xml, 'text/xml');
        const model = doc.querySelector('mxGraphModel');
        if (model) return new XMLSerializer().serializeToString(model);
        const diagram = doc.querySelector('diagram');
        if (diagram) {
            const text = diagram.textContent || '';
            const textStart = text.indexOf('<mxGraphModel');
            if (textStart !== -1) {
                const textEnd = text.indexOf('</mxGraphModel>', textStart);
                if (textEnd !== -1) return text.slice(textStart, textEnd + '</mxGraphModel>'.length);
            }
        }
        return '';
    }

    async function loadCompressedDrawioToState(content) {
        const doc = new DOMParser().parseFromString(content, 'text/xml');
        if (doc.querySelector('parsererror')) return false;
        const diagrams = Array.from(doc.getElementsByTagName('diagram'));
        for (const diagram of diagrams) {
            const payload = (diagram.textContent || '').trim();
            if (!payload || payload.includes('<mxGraphModel')) continue;
            try {
                const bytes = base64ToBytes(payload);
                let inflated;
                try {
                    inflated = await inflateRaw(bytes);
                } catch (error) {
                    inflated = await inflateDeflate(bytes);
                }
                const text = new TextDecoder('utf-8').decode(inflated);
                let xml = text;
                try {
                    xml = decodeURIComponent(text);
                } catch (error) {
                    xml = text;
                }
                if (loadXmlToState(xml)) return true;
            } catch (error) {
                // Try next diagram payload.
            }
        }
        return false;
    }

    function exportVdx() {
        return [
            '<?xml version="1.0" encoding="UTF-8"?>',
            '<VisioDocument xmlns="urn:schemas-microsoft-com:office:visio">',
            '<DocumentSettings><GlueSettings>9</GlueSettings><SnapSettings>65647</SnapSettings></DocumentSettings>',
            '<Pages><Page ID="0" NameU="Page-1" Name="Page-1">',
            '<PageSheet><Cell N="PageWidth" V="14"/><Cell N="PageHeight" V="9"/></PageSheet>',
            exportVisioShapesXml(),
            '</Page></Pages></VisioDocument>'
        ].join('');
    }

    function exportVsdx() {
        const pageXml = '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>' +
            '<PageContents xmlns="http://schemas.microsoft.com/office/visio/2012/main">' +
            exportVisioShapesXml() + '</PageContents>';
        const files = {
            '[Content_Types].xml': '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>' +
                '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">' +
                '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>' +
                '<Default Extension="xml" ContentType="application/xml"/>' +
                '<Override PartName="/visio/document.xml" ContentType="application/vnd.ms-visio.drawing.main+xml"/>' +
                '<Override PartName="/visio/pages/pages.xml" ContentType="application/vnd.ms-visio.pages+xml"/>' +
                '<Override PartName="/visio/pages/page1.xml" ContentType="application/vnd.ms-visio.page+xml"/>' +
                '</Types>',
            '_rels/.rels': '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>' +
                '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">' +
                '<Relationship Id="rId1" Type="http://schemas.microsoft.com/visio/2010/relationships/document" Target="visio/document.xml"/>' +
                '</Relationships>',
            'visio/document.xml': '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>' +
                '<VisioDocument xmlns="http://schemas.microsoft.com/office/visio/2012/main">' +
                '<DocumentSettings><GlueSettings>9</GlueSettings><SnapSettings>65647</SnapSettings></DocumentSettings>' +
                '<Pages><Page ID="0" NameU="Page-1" Name="Page-1" Rel="rId1"/></Pages></VisioDocument>',
            'visio/_rels/document.xml.rels': '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>' +
                '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">' +
                '<Relationship Id="rId1" Type="http://schemas.microsoft.com/visio/2010/relationships/pages" Target="pages/pages.xml"/>' +
                '</Relationships>',
            'visio/pages/pages.xml': '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>' +
                '<Pages xmlns="http://schemas.microsoft.com/office/visio/2012/main">' +
                '<Page ID="0" NameU="Page-1" Name="Page-1" Rel="rId1"/></Pages>',
            'visio/pages/_rels/pages.xml.rels': '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>' +
                '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">' +
                '<Relationship Id="rId1" Type="http://schemas.microsoft.com/visio/2010/relationships/page" Target="page1.xml"/>' +
                '</Relationships>',
            'visio/pages/page1.xml': pageXml
        };
        return createZip(files);
    }

    function exportVisioShapesXml() {
        const nodeIds = new Map();
        state.local.nodes.forEach((node, index) => nodeIds.set(node.id, index + 1));
        let nextId = state.local.nodes.length + 1;
        const shapes = state.local.nodes.map((node) => visioShapeXml(node, nodeIds.get(node.id))).join('') +
            state.local.edges.map((edge) => {
                const id = nextId;
                nextId += 1;
                return visioConnectorXml(edge, id);
            }).join('');
        const connects = state.local.edges.map((edge, index) => {
            const connectorId = state.local.nodes.length + 1 + index;
            const sourceId = nodeIds.get(edge.source);
            const targetId = nodeIds.get(edge.target);
            if (!sourceId || !targetId) return '';
            return '<Connect FromSheet="' + connectorId + '" FromCell="BeginX" ToSheet="' + sourceId + '"/>' +
                '<Connect FromSheet="' + connectorId + '" FromCell="EndX" ToSheet="' + targetId + '"/>';
        }).join('');
        return '<Shapes>' + shapes + '</Shapes><Connects>' + connects + '</Connects>';
    }

    function visioShapeXml(node, id) {
        const width = Math.max(0.2, node.width / 100);
        const height = Math.max(0.2, node.height / 100);
        const pinX = (node.x + node.width / 2) / 100;
        const pinY = (CANVAS_MIN_HEIGHT - node.y - node.height / 2) / 100;
        const name = visioNameForNode(node);
        return '<Shape ID="' + id + '" NameU="' + name + '" Name="' + name + '" Type="Shape">' +
            '<Cell N="PinX" V="' + round(pinX) + '"/><Cell N="PinY" V="' + round(pinY) + '"/>' +
            '<Cell N="Width" V="' + round(width) + '"/><Cell N="Height" V="' + round(height) + '"/>' +
            '<Cell N="FillForegnd" V="' + escapeAttr(node.fill || state.colors.fill) + '"/>' +
            '<Cell N="LineColor" V="' + escapeAttr(node.stroke || state.colors.stroke) + '"/>' +
            '<Text>' + escapeText(node.label || '') + '</Text>' +
            '<Section N="Geometry" IX="0">' + visioGeometryRows(node.type, width, height) + '</Section>' +
            '</Shape>';
    }

    function visioConnectorXml(edge, id) {
        const source = getNode(edge.source);
        const target = getNode(edge.target);
        if (!source || !target) return '';
        const a = anchorPoint(source, target);
        const b = anchorPoint(target, source);
        return '<Shape ID="' + id + '" NameU="Dynamic connector" Name="Dynamic connector" Type="Shape">' +
            '<Cell N="BeginX" V="' + round(a.x / 100) + '"/><Cell N="BeginY" V="' + round((CANVAS_MIN_HEIGHT - a.y) / 100) + '"/>' +
            '<Cell N="EndX" V="' + round(b.x / 100) + '"/><Cell N="EndY" V="' + round((CANVAS_MIN_HEIGHT - b.y) / 100) + '"/>' +
            '<Cell N="LineColor" V="' + escapeAttr(edge.stroke || state.colors.stroke) + '"/>' +
            '<Section N="Geometry" IX="0"><Row T="MoveTo" IX="1"><Cell N="X" V="0"/><Cell N="Y" V="0"/></Row>' +
            '<Row T="LineTo" IX="2"><Cell N="X" V="1"/><Cell N="Y" V="0"/></Row></Section></Shape>';
    }

    function visioGeometryRows(type, width, height) {
        const w = round(width);
        const h = round(height);
        if (type === 'decision') {
            return '<Row T="MoveTo" IX="1"><Cell N="X" V="' + round(w / 2) + '"/><Cell N="Y" V="' + h + '"/></Row>' +
                '<Row T="LineTo" IX="2"><Cell N="X" V="' + w + '"/><Cell N="Y" V="' + round(h / 2) + '"/></Row>' +
                '<Row T="LineTo" IX="3"><Cell N="X" V="' + round(w / 2) + '"/><Cell N="Y" V="0"/></Row>' +
                '<Row T="LineTo" IX="4"><Cell N="X" V="0"/><Cell N="Y" V="' + round(h / 2) + '"/></Row>' +
                '<Row T="LineTo" IX="5"><Cell N="X" V="' + round(w / 2) + '"/><Cell N="Y" V="' + h + '"/></Row>';
        }
        return '<Row T="MoveTo" IX="1"><Cell N="X" V="0"/><Cell N="Y" V="0"/></Row>' +
            '<Row T="LineTo" IX="2"><Cell N="X" V="' + w + '"/><Cell N="Y" V="0"/></Row>' +
            '<Row T="LineTo" IX="3"><Cell N="X" V="' + w + '"/><Cell N="Y" V="' + h + '"/></Row>' +
            '<Row T="LineTo" IX="4"><Cell N="X" V="0"/><Cell N="Y" V="' + h + '"/></Row>' +
            '<Row T="LineTo" IX="5"><Cell N="X" V="0"/><Cell N="Y" V="0"/></Row>';
    }

    function visioNameForNode(node) {
        if (node.type === 'terminator') return 'Terminator';
        if (node.type === 'decision') return 'Decision';
        if (node.type === 'data') return 'Data';
        if (node.type === 'note') return 'Document';
        return 'Process';
    }

    async function loadVsdxToState(buffer) {
        const entries = await readZipEntries(buffer);
        const pageName = Object.keys(entries).find((name) => /^visio\/pages\/page\d+\.xml$/i.test(name));
        if (!pageName) return false;
        return loadVisioPageXmlToState(entries[pageName]);
    }

    function loadVdxToState(content) {
        if (!/<VisioDocument[\s>]/i.test(content || '')) return false;
        return loadVisioPageXmlToState(content);
    }

    function loadVisioPageXmlToState(content) {
        const doc = new DOMParser().parseFromString(content, 'text/xml');
        if (doc.querySelector('parsererror')) return false;
        const shapes = Array.from(doc.getElementsByTagNameNS('*', 'Shape'));
        const nodes = [];
        const visioIdToNode = new Map();
        const connectorShapes = [];

        shapes.forEach((shape) => {
            const name = (shape.getAttribute('NameU') || shape.getAttribute('Name') || '').toLowerCase();
            const beginX = visioCell(shape, 'BeginX');
            const endX = visioCell(shape, 'EndX');
            if (name.includes('connector') || (beginX !== null && endX !== null)) {
                connectorShapes.push(shape);
                return;
            }
            const pinX = visioCell(shape, 'PinX');
            const pinY = visioCell(shape, 'PinY');
            const width = visioCell(shape, 'Width');
            const height = visioCell(shape, 'Height');
            if (pinX === null || pinY === null || width === null || height === null) return;
            const type = visioTypeFromName(name);
            const node = makeNode(
                type,
                pinX * 100 - width * 50,
                CANVAS_MIN_HEIGHT - pinY * 100 - height * 50,
                textFromVisioShape(shape) || defaultLabel(type),
                Math.max(50, width * 100),
                Math.max(34, height * 100),
                state.colors
            );
            const fill = visioCellText(shape, 'FillForegnd');
            const stroke = visioCellText(shape, 'LineColor');
            if (normalizeHex(fill)) node.fill = normalizeHex(fill);
            if (normalizeHex(stroke)) node.stroke = normalizeHex(stroke);
            nodes.push(node);
            visioIdToNode.set(shape.getAttribute('ID'), node);
        });

        if (!nodes.length) return false;
        const connects = Array.from(doc.getElementsByTagNameNS('*', 'Connect'));
        const edgeByConnector = new Map();
        connects.forEach((connect) => {
            const from = connect.getAttribute('FromSheet');
            const to = visioIdToNode.get(connect.getAttribute('ToSheet'));
            if (!from || !to) return;
            if (!edgeByConnector.has(from)) edgeByConnector.set(from, []);
            edgeByConnector.get(from).push(to);
        });
        const edges = [];
        edgeByConnector.forEach((targets) => {
            if (targets.length >= 2 && targets[0].id !== targets[1].id) edges.push(makeEdge(targets[0].id, targets[1].id));
        });

        if (!edges.length) {
            connectorShapes.forEach((shape) => {
                const beginX = visioCell(shape, 'BeginX');
                const beginY = visioCell(shape, 'BeginY');
                const endX = visioCell(shape, 'EndX');
                const endY = visioCell(shape, 'EndY');
                if ([beginX, beginY, endX, endY].some((v) => v === null)) return;
                const source = nearestNode(nodes, { x: beginX * 100, y: CANVAS_MIN_HEIGHT - beginY * 100 });
                const target = nearestNode(nodes, { x: endX * 100, y: CANVAS_MIN_HEIGHT - endY * 100 });
                if (source && target && source.id !== target.id) edges.push(makeEdge(source.id, target.id));
            });
        }

        state.local.nodes = nodes;
        state.local.edges = dedupeEdges(edges);
        state.local.backgrounds = [];
        selectNone();
        return true;
    }

    function visioTypeFromName(name) {
        if (name.includes('decision')) return 'decision';
        if (name.includes('terminator') || name.includes('start') || name.includes('end')) return 'terminator';
        if (name.includes('data')) return 'data';
        if (name.includes('document')) return 'note';
        return 'process';
    }

    function visioCell(shape, name) {
        const cell = Array.from(shape.getElementsByTagNameNS('*', 'Cell')).find((item) => item.getAttribute('N') === name);
        if (!cell) return null;
        const value = Number(cell.getAttribute('V'));
        return Number.isFinite(value) ? value : null;
    }

    function visioCellText(shape, name) {
        const cell = Array.from(shape.getElementsByTagNameNS('*', 'Cell')).find((item) => item.getAttribute('N') === name);
        return cell ? (cell.getAttribute('V') || '') : '';
    }

    function textFromVisioShape(shape) {
        const text = Array.from(shape.getElementsByTagNameNS('*', 'Text'))[0];
        return text ? text.textContent.trim() : '';
    }

    function updateXmlSnapshot() {
        state.xml = exportMxGraphXml();
    }

    function exportMxGraphXml() {
        const cells = ['<mxCell id="0"/>', '<mxCell id="1" parent="0"/>'];
        state.local.backgrounds.forEach((bg) => {
            const opacity = Math.round((bg.opacity || 0.35) * 100);
            const style = 'shape=image;image=' + encodeStyleValue(bg.href) + ';aspect=fixed;imageAspect=0;opacity=' + opacity + ';';
            cells.push(
                '<mxCell id="' + escapeAttr(bg.id) + '" value="' + escapeAttr(bg.name || '底图') + '" style="' + escapeAttr(style) + '" vertex="1" parent="1">' +
                '<mxGeometry x="' + round(bg.x) + '" y="' + round(bg.y) + '" width="' + round(bg.width) + '" height="' + round(bg.height) + '" as="geometry"/></mxCell>'
            );
        });
        state.local.nodes.forEach((node) => {
            cells.push(
                '<mxCell id="' + escapeAttr(node.id) + '" value="' + escapeAttr(node.label || '') + '" style="' + escapeAttr(styleForNode(node)) + '" vertex="1" parent="1">' +
                '<mxGeometry x="' + round(node.x) + '" y="' + round(node.y) + '" width="' + round(node.width) + '" height="' + round(node.height) + '" as="geometry"/></mxCell>'
            );
        });
        state.local.edges.forEach((edge) => {
            cells.push(
                '<mxCell id="' + escapeAttr(edge.id) + '" value="" style="' + escapeAttr(styleForEdge(edge)) + '" edge="1" source="' + escapeAttr(edge.source) + '" target="' + escapeAttr(edge.target) + '" parent="1">' +
                '<mxGeometry relative="1" as="geometry"/></mxCell>'
            );
        });
        return '<mxGraphModel dx="' + CANVAS_MIN_WIDTH + '" dy="' + CANVAS_MIN_HEIGHT + '" grid="1" gridSize="10" guides="1" tooltips="1" connect="1" arrows="1" page="1" pageScale="1" pageWidth="' + CANVAS_MIN_WIDTH + '" pageHeight="' + CANVAS_MIN_HEIGHT + '" math="0" shadow="0"><root>' + cells.join('') + '</root></mxGraphModel>';
    }

    function styleForNode(node) {
        const base = 'whiteSpace=wrap;html=1;fillColor=' + node.fill + ';strokeColor=' + node.stroke + ';fontColor=' + node.font + ';scifigShape=' + node.type + ';';
        if (node.type === 'terminator') return 'rounded=1;arcSize=50;' + base;
        if (node.type === 'decision') return 'rhombus;' + base;
        if (node.type === 'data') return 'shape=parallelogram;perimeter=parallelogramPerimeter;' + base;
        if (node.type === 'note') return 'shape=note;' + base;
        if (node.type === 'database' || node.type === 'storedData') return 'shape=cylinder3d;' + base;
        if (node.type === 'dataset' || node.type === 'cache') return 'rounded=1;' + base;
        if (node.type === 'document' || node.type === 'paper' || node.type === 'multiDocument') return 'shape=document;' + base;
        if (node.type === 'preparation') return 'shape=hexagon;perimeter=hexagonPerimeter2;' + base;
        if (node.type === 'manualInput') return 'shape=manualInput;' + base;
        if (node.type === 'delay') return 'shape=delay;' + base;
        if (node.type === 'connector' || node.type === 'metric') return 'ellipse;whiteSpace=wrap;html=1;fillColor=' + node.fill + ';strokeColor=' + node.stroke + ';fontColor=' + node.font + ';scifigShape=' + node.type + ';';
        if (node.type === 'offpage') return 'shape=offPageConnector;' + base;
        if (node.type === 'display') return 'shape=display;' + base;
        if (node.type === 'subroutine') return 'shape=process;' + base;
        if (node.type === 'model' || node.type === 'code' || node.type === 'api' || node.type === 'service') return 'rounded=1;' + base;
        if (node.type === 'server' || node.type === 'web' || node.type === 'mobile' || node.type === 'message' || node.type === 'queue') return 'rounded=1;' + base;
        if (node.type === 'cloud') return 'ellipse;shape=cloud;' + base;
        if (node.type === 'text') return 'text;html=1;strokeColor=none;fillColor=none;fontColor=' + node.font + ';scifigShape=text;';
        return 'rounded=0;' + base;
    }

    function styleForEdge(edge) {
        const type = edge.type || 'orthogonal';
        let style = 'edgeStyle=orthogonalEdgeStyle;rounded=0;orthogonalLoop=1;jettySize=auto;html=1;endArrow=block;';
        if (type === 'straight' || type === 'thick') style = 'edgeStyle=none;rounded=0;html=1;endArrow=block;';
        if (type === 'curve') style = 'edgeStyle=orthogonalEdgeStyle;curved=1;rounded=1;html=1;endArrow=block;';
        if (type === 'dashed') style += 'dashed=1;dashPattern=8 6;';
        if (type === 'dotted') style += 'dashed=1;dashPattern=2 6;';
        if (type === 'thick') style += 'strokeWidth=3;';
        if (type === 'bidirectional') style += 'startArrow=block;';
        if (type === 'noArrow') style = style.replace('endArrow=block;', 'endArrow=none;');
        return style + 'strokeColor=' + (edge.stroke || state.colors.stroke) + ';scifigEdge=' + type + ';';
    }

    function edgeTypeFromStyle(style) {
        if (style.scifigEdge) return style.scifigEdge;
        if (style.endArrow === 'none') return 'noArrow';
        if (style.startArrow && style.startArrow !== 'none') return 'bidirectional';
        if (style.dashed === '1' && String(style.dashPattern || '').startsWith('2')) return 'dotted';
        if (style.dashed === '1') return 'dashed';
        if (style.strokeWidth && Number(style.strokeWidth) >= 3) return 'thick';
        if (style.curved === '1') return 'curve';
        if (style.edgeStyle === 'none') return 'straight';
        return 'orthogonal';
    }

    function typeFromStyle(style) {
        if (style.scifigShape) return style.scifigShape;
        if (style.rhombus === true || style.shape === 'rhombus') return 'decision';
        if (style.shape === 'parallelogram') return 'data';
        if (style.shape === 'note') return 'note';
        if (style.shape === 'cylinder3d' || style.shape === 'cylinder' || style.shape === 'cylinder3') return 'database';
        if (style.shape === 'document') return 'document';
        if (style.shape === 'hexagon') return 'preparation';
        if (style.shape === 'manualInput') return 'manualInput';
        if (style.shape === 'delay') return 'delay';
        if (style.ellipse === true || style.shape === 'ellipse') return 'connector';
        if (style.shape === 'offPageConnector') return 'offpage';
        if (style.shape === 'display') return 'display';
        if (style.shape === 'cloud') return 'cloud';
        if (style.shape === 'swimlane') return 'process';
        if (style.shape === 'mxgraph.flowchart.database') return 'database';
        if (style.shape === 'mxgraph.flowchart.terminator') return 'terminator';
        if (style.shape === 'mxgraph.flowchart.process') return 'process';
        if (style.shape === 'mxgraph.flowchart.decision') return 'decision';
        if (style.shape === 'mxgraph.flowchart.document') return 'document';
        if (style.shape === 'mxgraph.flowchart.predefined_process') return 'subroutine';
        if (style.shape === 'mxgraph.flowchart.merge' || style.shape === 'merge') return 'merge';
        if (style.shape === 'mxgraph.flowchart.extract' || style.shape === 'extract') return 'extract';
        if (style.shape === 'mxgraph.flowchart.sort' || style.shape === 'sort') return 'sort';
        if (style.shape === 'mxgraph.flowchart.collate' || style.shape === 'collate') return 'collate';
        if (style.shape === 'mxgraph.flowchart.manual_operation' || style.shape === 'manualOperation') return 'manualOperation';
        if (style.shape === 'trapezoid') return 'manualOperation';
        if (style.shape === 'partialRectangle' || style.shape === 'tape') return 'tape';
        if (style.shape === 'step') return 'process';
        if (style.shape === 'mxgraph.arrows2.arrow') return 'process';
        if (style.text === true || style.shape === 'text') return 'text';
        if (style.rounded === '1' && (style.arcSize === '50' || style.arcSize === '40')) return 'terminator';
        return 'process';
    }

    function parseStyle(styleText) {
        const result = {};
        const imageMatch = styleText.match(/(?:^|;)image=(data:[^;]+;base64,[^;]*|[^;]*)/);
        let normalizedStyle = styleText;
        if (imageMatch) {
            result.image = decodeStyleValue(imageMatch[1]);
            normalizedStyle = styleText.replace(imageMatch[0], ';image=__image__');
        }
        normalizedStyle.split(';').forEach((part) => {
            const item = part.trim();
            if (!item) return;
            const eq = item.indexOf('=');
            if (eq === -1) result[item] = true;
            else if (item.slice(0, eq) !== 'image') result[item.slice(0, eq)] = item.slice(eq + 1);
        });
        return result;
    }

    function makeNode(type, x, y, label, width, height, colors) {
        return {
            id: uniqueId('n'),
            type,
            label: label || defaultLabel(type),
            x: Math.round(x),
            y: Math.round(y),
            width,
            height,
            fill: type === 'text' ? 'transparent' : colors.fill,
            stroke: colors.stroke,
            font: colors.font
        };
    }

    function makeEdge(source, target, type) {
        return { id: uniqueId('e'), source, target, type: type || state.edgeType || 'orthogonal', stroke: state.colors.stroke };
    }

    function defaultSize(type) {
        if (type === 'terminator') return { width: 160, height: 50 };
        if (type === 'decision') return { width: 160, height: 90 };
        if (type === 'data') return { width: 180, height: 62 };
        if (type === 'document' || type === 'paper') return { width: 180, height: 72 };
        if (type === 'multiDocument') return { width: 184, height: 82 };
        if (type === 'database' || type === 'storedData' || type === 'dataset' || type === 'cache') return { width: 170, height: 76 };
        if (type === 'preparation') return { width: 170, height: 64 };
        if (type === 'manualInput') return { width: 180, height: 62 };
        if (type === 'delay') return { width: 150, height: 64 };
        if (type === 'connector' || type === 'metric') return { width: 82, height: 82 };
        if (type === 'offpage') return { width: 130, height: 86 };
        if (type === 'display') return { width: 180, height: 70 };
        if (type === 'subroutine' || type === 'model' || type === 'code' || type === 'api' || type === 'service') return { width: 200, height: 66 };
        if (type === 'server' || type === 'web' || type === 'message' || type === 'queue') return { width: 178, height: 70 };
        if (type === 'mobile') return { width: 112, height: 120 };
        if (type === 'note' || type === 'callout') return { width: 180, height: 82 };
        if (type === 'tag') return { width: 150, height: 54 };
        if (type === 'cloud') return { width: 160, height: 86 };
        if (type === 'person') return { width: 100, height: 92 };
        if (type === 'text') return { width: 150, height: 42 };
        if (type === 'training') return { width: 170, height: 66 };
        if (type === 'evaluation') return { width: 170, height: 70 };
        if (type === 'experiment') return { width: 170, height: 66 };
        if (type === 'loss') return { width: 170, height: 66 };
        if (type === 'optimizer') return { width: 170, height: 66 };
        if (type === 'augment') return { width: 170, height: 66 };
        if (type === 'inference' || type === 'prediction') return { width: 170, height: 66 };
        if (type === 'deployment') return { width: 170, height: 66 };
        if (type === 'embedding') return { width: 170, height: 76 };
        if (type === 'backbone') return { width: 170, height: 66 };
        if (type === 'attention') return { width: 170, height: 66 };
        if (type === 'gateway') return { width: 178, height: 70 };
        if (type === 'loadBalancer') return { width: 178, height: 70 };
        if (type === 'firewall') return { width: 178, height: 70 };
        if (type === 'card') return { width: 180, height: 72 };
        if (type === 'tape') return { width: 180, height: 62 };
        if (type === 'class') return { width: 180, height: 72 };
        if (type === 'interface') return { width: 180, height: 62 };
        if (type === 'component') return { width: 180, height: 72 };
        if (type === 'actor') return { width: 100, height: 120 };
        if (type === 'usecase') return { width: 160, height: 90 };
        if (type === 'package') return { width: 200, height: 72 };
        if (type === 'pipeline') return { width: 178, height: 66 };
        if (type === 'container' || type === 'docker') return { width: 178, height: 70 };
        if (type === 'function') return { width: 170, height: 66 };
        if (type === 'warning' || type === 'alert') return { width: 130, height: 90 };
        if (type === 'error') return { width: 100, height: 100 };
        if (type === 'success') return { width: 100, height: 100 };
        if (type === 'info') return { width: 100, height: 100 };
        if (type === 'manualOperation') return { width: 170, height: 66 };
        if (type === 'merge') return { width: 170, height: 66 };
        if (type === 'extract') return { width: 170, height: 80 };
        if (type === 'sort') return { width: 160, height: 90 };
        if (type === 'collate') return { width: 170, height: 70 };
        if (type === 'fork' || type === 'join') return { width: 160, height: 40 };
        if (type === 'timer') return { width: 100, height: 100 };
        if (type === 'table') return { width: 180, height: 72 };
        if (type === 'image') return { width: 180, height: 96 };
        if (type === 'lane') return { width: 220, height: 100 };
        if (type === 'semaphore' || type === 'event') return { width: 100, height: 100 };
        if (type === 'stream') return { width: 180, height: 70 };
        if (type === 'batch') return { width: 178, height: 82 };
        if (type === 'cron' || type === 'gitBranch' || type === 'monitor' || type === 'log' || type === 'config') return { width: 178, height: 70 };
        return { width: 190, height: 62 };
    }

    function defaultLabel(type) {
        const labels = {
            terminator: '开始/结束',
            process: '处理步骤',
            decision: '判断条件',
            data: '输入/输出',
            subroutine: '子流程',
            preparation: '准备',
            manualInput: '手动输入',
            delay: '等待',
            connector: 'A',
            database: '数据库',
            document: '文档',
            multiDocument: '多文档',
            storedData: '存储数据',
            internalStorage: '内部存储',
            display: '显示结果',
            offpage: '跨页',
            dataset: '数据集',
            model: '模型',
            training: '训练',
            evaluation: '评估',
            experiment: '实验',
            metric: '指标',
            paper: '论文输出',
            code: '代码模块',
            api: 'API 接口',
            service: '服务模块',
            server: '服务器',
            queue: '消息队列',
            cache: '缓存',
            message: '消息事件',
            web: 'Web 页面',
            mobile: '移动端',
            note: '注释',
            callout: '说明',
            tag: '标签',
            cloud: '云端服务',
            person: '角色',
            text: '文本',
            training: '训练',
            evaluation: '评估',
            experiment: '实验',
            loss: '损失函数',
            optimizer: '优化器',
            augment: '数据增强',
            inference: '推理',
            prediction: '预测',
            deployment: '部署',
            embedding: '特征表示',
            backbone: '骨干网络',
            attention: '注意力',
            gateway: '网关',
            loadBalancer: '负载均衡',
            firewall: '防火墙',
            card: '卡片',
            tape: '纸带',
            class: '类',
            interface: '接口',
            component: '组件',
            actor: '参与者',
            usecase: '用例',
            package: '包',
            pipeline: '流水线',
            container: '容器',
            docker: 'Docker',
            function: '函数',
            warning: '警告',
            alert: '告警',
            error: '错误',
            success: '成功',
            info: '信息',
            manualOperation: '人工操作',
            merge: '合并',
            extract: '提取',
            sort: '排序',
            collate: '汇总',
            fork: '并行分叉',
            join: '并行汇合',
            timer: '定时器',
            table: '表格',
            image: '图片',
            lane: '泳道',
            semaphore: '信号量',
            event: '事件',
            stream: '数据流',
            batch: '批处理',
            cron: '定时任务',
            gitBranch: 'Git 分支',
            monitor: '监控',
            log: '日志',
            config: '配置'
        };
        return labels[type] || '步骤';
    }

    function getNode(id) {
        return state.local.nodes.find((node) => node.id === id);
    }

    function getSelectedEdge() {
        if (state.local.selectedKind !== 'edge' || !state.local.selectedId) return null;
        return state.local.edges.find((edge) => edge.id === state.local.selectedId) || null;
    }

    function syncEdgeTypeControl() {
        const select = $('#edgeTypeSelect');
        if (!select) return;
        const edge = getSelectedEdge();
        const type = edge ? (edge.type || 'orthogonal') : (state.edgeType || 'orthogonal');
        select.value = type;
    }

    function selectedEdgeTypeLabel() {
        const select = $('#edgeTypeSelect');
        if (!select) return '折线箭头';
        const option = select.options[select.selectedIndex];
        return option ? option.textContent : '折线箭头';
    }

    function nearestNode(nodes, point) {
        let best = null;
        let bestDist = Infinity;
        nodes.forEach((node) => {
            const cx = node.x + node.width / 2;
            const cy = node.y + node.height / 2;
            const d = Math.hypot(cx - point.x, cy - point.y);
            if (d < bestDist) {
                bestDist = d;
                best = node;
            }
        });
        return bestDist < 180 ? best : null;
    }

    function normalizeNode(node) {
        const type = node.type || 'process';
        const size = defaultSize(type);
        return {
            id: node.id || uniqueId('n'),
            type,
            label: node.label || defaultLabel(type),
            x: Number(node.x) || 0,
            y: Number(node.y) || 0,
            width: Math.max(40, Number(node.width) || size.width),
            height: Math.max(30, Number(node.height) || size.height),
            fill: node.fill || (type === 'text' ? 'transparent' : state.colors.fill),
            stroke: node.stroke || state.colors.stroke,
            font: node.font || state.colors.font
        };
    }

    function layoutNodes(nodes, direction) {
        const gap = direction === 'LR' ? 220 : 120;
        nodes.forEach((node, index) => {
            if (direction === 'LR') {
                node.x = 100 + index * gap;
                node.y = 410 - node.height / 2;
            } else {
                node.x = 700 - node.width / 2;
                node.y = 90 + index * gap;
            }
        });
    }

    function parseSvgPoints(pointsText) {
        const nums = (pointsText || '').match(/-?\d+(?:\.\d+)?/g) || [];
        const points = [];
        for (let i = 0; i + 1 < nums.length; i += 2) {
            points.push({ x: Number(nums[i]), y: Number(nums[i + 1]) });
        }
        return points;
    }

    function pointsBox(points) {
        const xs = points.map((point) => point.x);
        const ys = points.map((point) => point.y);
        const minX = Math.min(...xs);
        const minY = Math.min(...ys);
        const maxX = Math.max(...xs);
        const maxY = Math.max(...ys);
        return { x: minX, y: minY, width: maxX - minX, height: maxY - minY };
    }

    function normalizePaint(value) {
        if (!value || value === 'none' || value.startsWith('url(')) return '';
        return normalizeHex(value);
    }

    function dedupeNodes(nodes) {
        const result = [];
        nodes.forEach((node) => {
            const duplicate = result.some((item) => {
                const a = { minX: item.x, minY: item.y, maxX: item.x + item.width, maxY: item.y + item.height };
                const b = { minX: node.x, minY: node.y, maxX: node.x + node.width, maxY: node.y + node.height };
                return overlapRatio(a, b) > 0.7;
            });
            if (!duplicate) result.push(node);
        });
        return result;
    }

    function dedupeEdges(edges) {
        const seen = new Set();
        return edges.filter((edge) => {
            const key = edge.source + '->' + edge.target;
            if (seen.has(key)) return false;
            seen.add(key);
            return true;
        });
    }

    function psEscape(value) {
        return String(value || '').replace(/\\/g, '\\\\').replace(/\(/g, '\\(').replace(/\)/g, '\\)');
    }

    function readFileAsText(file) {
        return new Promise((resolve, reject) => {
            const reader = new FileReader();
            reader.onload = (event) => resolve(event.target.result);
            reader.onerror = () => reject(new Error('文件读取失败'));
            reader.readAsText(file);
        });
    }

    function readFileAsArrayBuffer(file) {
        return new Promise((resolve, reject) => {
            const reader = new FileReader();
            reader.onload = (event) => resolve(event.target.result);
            reader.onerror = () => reject(new Error('文件读取失败'));
            reader.readAsArrayBuffer(file);
        });
    }

    async function readZipEntries(buffer) {
        const bytes = new Uint8Array(buffer);
        const view = new DataView(buffer);
        let eocd = -1;
        for (let i = bytes.length - 22; i >= Math.max(0, bytes.length - 66000); i -= 1) {
            if (view.getUint32(i, true) === 0x06054b50) {
                eocd = i;
                break;
            }
        }
        if (eocd < 0) throw new Error('不是有效 ZIP/VSDX 文件');
        const total = view.getUint16(eocd + 10, true);
        let offset = view.getUint32(eocd + 16, true);
        const decoder = new TextDecoder('utf-8');
        const entries = {};
        for (let i = 0; i < total; i += 1) {
            if (view.getUint32(offset, true) !== 0x02014b50) break;
            const method = view.getUint16(offset + 10, true);
            const compressedSize = view.getUint32(offset + 20, true);
            const nameLen = view.getUint16(offset + 28, true);
            const extraLen = view.getUint16(offset + 30, true);
            const commentLen = view.getUint16(offset + 32, true);
            const localOffset = view.getUint32(offset + 42, true);
            const name = decoder.decode(bytes.slice(offset + 46, offset + 46 + nameLen));
            const localNameLen = view.getUint16(localOffset + 26, true);
            const localExtraLen = view.getUint16(localOffset + 28, true);
            const dataStart = localOffset + 30 + localNameLen + localExtraLen;
            const compressed = bytes.slice(dataStart, dataStart + compressedSize);
            let data;
            if (method === 0) data = compressed;
            else if (method === 8) data = await inflateRaw(compressed);
            else throw new Error('暂不支持该 VSDX 压缩方式：' + method);
            entries[name] = decoder.decode(data);
            offset += 46 + nameLen + extraLen + commentLen;
        }
        return entries;
    }

    async function inflateRaw(bytes) {
        if (!('DecompressionStream' in window)) {
            throw new Error('当前浏览器不支持解压该 VSDX，请先用 Visio 另存为 VDX 或 XML');
        }
        const stream = new Blob([bytes]).stream().pipeThrough(new DecompressionStream('deflate-raw'));
        return new Uint8Array(await new Response(stream).arrayBuffer());
    }

    async function inflateDeflate(bytes) {
        if (!('DecompressionStream' in window)) {
            throw new Error('当前浏览器不支持解压该文件');
        }
        const stream = new Blob([bytes]).stream().pipeThrough(new DecompressionStream('deflate'));
        return new Uint8Array(await new Response(stream).arrayBuffer());
    }

    function base64ToBytes(value) {
        const binary = atob(value.replace(/\s/g, ''));
        const bytes = new Uint8Array(binary.length);
        for (let i = 0; i < binary.length; i += 1) bytes[i] = binary.charCodeAt(i);
        return bytes;
    }

    function createZip(files) {
        const encoder = new TextEncoder();
        const localParts = [];
        const centralParts = [];
        let offset = 0;
        Object.keys(files).forEach((name) => {
            const nameBytes = encoder.encode(name);
            const data = encoder.encode(files[name]);
            const crc = crc32(data);
            const local = new Uint8Array(30 + nameBytes.length);
            const lv = new DataView(local.buffer);
            lv.setUint32(0, 0x04034b50, true);
            lv.setUint16(4, 20, true);
            lv.setUint16(6, 0, true);
            lv.setUint16(8, 0, true);
            lv.setUint16(10, 0, true);
            lv.setUint16(12, 0, true);
            lv.setUint32(14, crc, true);
            lv.setUint32(18, data.length, true);
            lv.setUint32(22, data.length, true);
            lv.setUint16(26, nameBytes.length, true);
            local.set(nameBytes, 30);
            localParts.push(local, data);

            const central = new Uint8Array(46 + nameBytes.length);
            const cv = new DataView(central.buffer);
            cv.setUint32(0, 0x02014b50, true);
            cv.setUint16(4, 20, true);
            cv.setUint16(6, 20, true);
            cv.setUint16(8, 0, true);
            cv.setUint16(10, 0, true);
            cv.setUint16(12, 0, true);
            cv.setUint16(14, 0, true);
            cv.setUint32(16, crc, true);
            cv.setUint32(20, data.length, true);
            cv.setUint32(24, data.length, true);
            cv.setUint16(28, nameBytes.length, true);
            cv.setUint32(42, offset, true);
            central.set(nameBytes, 46);
            centralParts.push(central);
            offset += local.length + data.length;
        });
        const centralOffset = offset;
        const centralSize = centralParts.reduce((sum, part) => sum + part.length, 0);
        const end = new Uint8Array(22);
        const ev = new DataView(end.buffer);
        ev.setUint32(0, 0x06054b50, true);
        ev.setUint16(8, Object.keys(files).length, true);
        ev.setUint16(10, Object.keys(files).length, true);
        ev.setUint32(12, centralSize, true);
        ev.setUint32(16, centralOffset, true);
        return new Blob(localParts.concat(centralParts, [end]), { type: 'application/vnd.visio' });
    }

    function crc32(bytes) {
        let crc = -1;
        for (let i = 0; i < bytes.length; i += 1) {
            crc ^= bytes[i];
            for (let j = 0; j < 8; j += 1) {
                crc = (crc >>> 1) ^ (0xedb88320 & -(crc & 1));
            }
        }
        return (crc ^ -1) >>> 0;
    }

    function updateCustomColorsFromSliders(shouldApply) {
        const h = parseFloat($('#hueRange').value);
        const s = parseFloat($('#satRange').value);
        const l = parseFloat($('#lightRange').value);
        const stroke = hslToHex(h, s, l);
        const fill = hslToHex(h, Math.max(20, s - 22), Math.min(94, l + 36));
        const font = readableTextColor(fill);
        state.currentScheme = 'custom';
        state.colors = { fill, stroke, font };
        syncColorInputsFromColors(state.colors);
        applyActiveSchemeMarker();
        if (shouldApply) applyColorsToAll(state.colors);
    }

    function syncColorInputsFromColors(colors) {
        $('#fillHex').value = colors.fill.toUpperCase();
        $('#strokeHex').value = colors.stroke.toUpperCase();
        $('#fontHex').value = colors.font.toUpperCase();
        const hsl = hexToHsl(colors.stroke);
        $('#hueRange').value = String(Math.round(hsl.h));
        $('#satRange').value = String(Math.round(hsl.s));
        $('#lightRange').value = String(Math.round(hsl.l));
        const preview = $('#colorPreview');
        preview.style.background = colors.fill;
        preview.style.color = colors.font;
        preview.style.borderColor = colors.stroke;
        preview.textContent = 'Aa / ' + colors.stroke.toUpperCase();
    }

    function applyActiveSchemeMarker() {
        $$('.color-swatch').forEach((swatch) => {
            swatch.classList.toggle('active', swatch.dataset.scheme === state.currentScheme);
        });
    }

    function parseSavedScheme(value) {
        if (value && value.startsWith('custom:')) {
            const parts = value.slice(7).split(',');
            return {
                fill: normalizeHex(parts[0]) || SCHEMES.default.fill,
                stroke: normalizeHex(parts[1]) || SCHEMES.default.stroke,
                font: normalizeHex(parts[2]) || SCHEMES.default.font
            };
        }
        return Object.assign({}, SCHEMES[value] || SCHEMES.default);
    }

    function savedSchemeValue() {
        if (state.currentScheme === 'custom') {
            return 'custom:' + state.colors.fill + ',' + state.colors.stroke + ',' + state.colors.font;
        }
        return state.currentScheme;
    }

    function hslToHex(h, s, l) {
        s /= 100;
        l /= 100;
        const c = (1 - Math.abs(2 * l - 1)) * s;
        const x = c * (1 - Math.abs((h / 60) % 2 - 1));
        const m = l - c / 2;
        let r = 0;
        let g = 0;
        let b = 0;
        if (h < 60) { r = c; g = x; }
        else if (h < 120) { r = x; g = c; }
        else if (h < 180) { g = c; b = x; }
        else if (h < 240) { g = x; b = c; }
        else if (h < 300) { r = x; b = c; }
        else { r = c; b = x; }
        return rgbToHex((r + m) * 255, (g + m) * 255, (b + m) * 255);
    }

    function hexToHsl(hex) {
        const rgb = hexToRgb(hex) || { r: 99, g: 102, b: 241 };
        let r = rgb.r / 255;
        let g = rgb.g / 255;
        let b = rgb.b / 255;
        const max = Math.max(r, g, b);
        const min = Math.min(r, g, b);
        let h = 0;
        let s = 0;
        const l = (max + min) / 2;
        if (max !== min) {
            const d = max - min;
            s = l > 0.5 ? d / (2 - max - min) : d / (max + min);
            if (max === r) h = ((g - b) / d + (g < b ? 6 : 0)) * 60;
            else if (max === g) h = ((b - r) / d + 2) * 60;
            else h = ((r - g) / d + 4) * 60;
        }
        return { h, s: s * 100, l: l * 100 };
    }

    function hexToRgb(hex) {
        const normalized = normalizeHex(hex);
        if (!normalized) return null;
        return {
            r: parseInt(normalized.slice(1, 3), 16),
            g: parseInt(normalized.slice(3, 5), 16),
            b: parseInt(normalized.slice(5, 7), 16)
        };
    }

    function rgbToHex(r, g, b) {
        return '#' + [r, g, b].map((value) => {
            const part = clamp(Math.round(value), 0, 255).toString(16);
            return part.length === 1 ? '0' + part : part;
        }).join('');
    }

    function normalizeHex(value) {
        if (!value) return '';
        const v = value.trim();
        if (/^#[0-9a-fA-F]{6}$/.test(v)) return v.toLowerCase();
        if (/^[0-9a-fA-F]{6}$/.test(v)) return '#' + v.toLowerCase();
        return '';
    }

    function readableTextColor(hex) {
        const rgb = hexToRgb(hex);
        if (!rgb) return '#0f172a';
        const luminance = (0.299 * rgb.r + 0.587 * rgb.g + 0.114 * rgb.b) / 255;
        return luminance > 0.62 ? '#0f172a' : '#ffffff';
    }

    function density(binary, width, x0, y0, x1, y1) {
        const height = Math.floor(binary.length / width);
        x0 = clamp(Math.floor(x0), 0, width - 1);
        x1 = clamp(Math.floor(x1), 0, width - 1);
        y0 = clamp(Math.floor(y0), 0, height - 1);
        y1 = clamp(Math.floor(y1), 0, height - 1);
        let total = 0;
        let count = 0;
        for (let y = y0; y <= y1; y += 1) {
            for (let x = x0; x <= x1; x += 1) {
                total += 1;
                count += binary[y * width + x] ? 1 : 0;
            }
        }
        return total ? count / total : 0;
    }

    function boxArea(box) {
        return (box.maxX - box.minX + 1) * (box.maxY - box.minY + 1);
    }

    function overlapRatio(a, b) {
        const x0 = Math.max(a.minX, b.minX);
        const y0 = Math.max(a.minY, b.minY);
        const x1 = Math.min(a.maxX, b.maxX);
        const y1 = Math.min(a.maxY, b.maxY);
        if (x1 <= x0 || y1 <= y0) return 0;
        const overlap = (x1 - x0) * (y1 - y0);
        return overlap / Math.min(boxArea(a), boxArea(b));
    }

    function containsBox(outer, inner, pad) {
        return inner.minX >= outer.minX - pad && inner.maxX <= outer.maxX + pad &&
            inner.minY >= outer.minY - pad && inner.maxY <= outer.maxY + pad;
    }

    function clientToSvg(event) {
        const rect = canvas.getBoundingClientRect();
        const viewBox = canvas.viewBox && canvas.viewBox.baseVal;
        const width = viewBox && viewBox.width ? viewBox.width : (parseFloat(canvas.getAttribute('width')) || CANVAS_MIN_WIDTH);
        const height = viewBox && viewBox.height ? viewBox.height : (parseFloat(canvas.getAttribute('height')) || CANVAS_MIN_HEIGHT);
        const x = ((event.clientX - rect.left) / Math.max(1, rect.width)) * width;
        const y = ((event.clientY - rect.top) / Math.max(1, rect.height)) * height;
        return { x: x, y: y };
    }

    function loadImage(src) {
        return new Promise((resolve, reject) => {
            const img = new Image();
            img.onload = () => resolve(img);
            img.onerror = () => reject(new Error('图片读取失败'));
            img.src = src;
        });
    }

    function closeImportModal() {
        const modal = bootstrap.Modal.getInstance($('#importModal'));
        if (modal) modal.hide();
    }

    function setStatus(text, type) {
        $('#statusText').textContent = text;
        const colors = { ok: '#10b981', busy: '#f59e0b', error: '#ef4444' };
        $('#statusDot').style.background = colors[type] || colors.ok;
    }

    function showToast() {
        const toast = $('#saveToast');
        toast.classList.add('show');
        setTimeout(() => toast.classList.remove('show'), 1500);
    }

    function downloadBlob(blob, filename) {
        if (!blob) return;
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = filename;
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        URL.revokeObjectURL(url);
    }

    function getFileName() {
        return ($('#diagramTitle').value.trim() || 'diagram').replace(/[\/\\:*?"<>|]/g, '_');
    }

    function uniqueId(prefix) {
        return prefix + '_' + Date.now().toString(36) + '_' + Math.random().toString(36).slice(2, 8);
    }

    function wrapText(text, maxChars, maxLines) {
        const clean = String(text || '').trim();
        if (!clean) return [''];
        const lines = [];
        let current = '';
        Array.from(clean).forEach((char) => {
            current += char;
            if (current.length >= maxChars) {
                lines.push(current);
                current = '';
            }
        });
        if (current) lines.push(current);
        if (lines.length > maxLines) {
            const clipped = lines.slice(0, maxLines);
            clipped[maxLines - 1] = clipped[maxLines - 1].slice(0, Math.max(1, maxChars - 1)) + '…';
            return clipped;
        }
        return lines;
    }

    function escapeText(value) {
        return String(value || '')
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;');
    }

    function escapeAttr(value) {
        return escapeText(value)
            .replace(/"/g, '&quot;')
            .replace(/'/g, '&#39;');
    }

    function encodeStyleValue(value) {
        return encodeURIComponent(String(value || ''));
    }

    function decodeStyleValue(value) {
        try {
            return decodeURIComponent(value || '');
        } catch (error) {
            return value || '';
        }
    }

    function clamp(value, min, max) {
        return Math.min(max, Math.max(min, value));
    }

    function round(value) {
        return Math.round(value * 100) / 100;
    }
})();
