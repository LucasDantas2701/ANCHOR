(args = {}) => {
    // Aceita o formato antigo [selector, includeHidden] ou um objeto de opções.
    const opts = Array.isArray(args)
        ? { selector: args[0], includeHidden: args[1] }
        : args;

    const {
        mode = "interactive",     // "interactive" (clicar, preencher) | "content" (extrair texto)
        selector = null,          // seletor CSS fixo; ignora o modo
        includeHidden = false,
        detectPointer = true,     // inclui elementos com cursor:pointer (divs clicáveis de SPAs)
        contextSelectors = [],    // containers específicos de um site (ex.: ".inventory_item")
        maxElements = 1000,
        maxText = 200,
    } = opts;

    const ATTR = "data-er-id";

    // ------------------------------------------------------------------
    // Configuração
    // ------------------------------------------------------------------

    const ROLES = [
        "button", "link", "checkbox", "radio", "switch", "tab", "menuitem",
        "menuitemcheckbox", "menuitemradio", "option", "combobox", "textbox",
        "searchbox", "slider", "spinbutton", "treeitem",
    ];

    const INTERACTIVE = [
        "a[href]", "area[href]", "button", "summary", "select", "textarea",
        "input:not([type=hidden])", "[contenteditable='']", "[contenteditable=true]",
        "[onclick]", "[tabindex]:not([tabindex='-1'])",
        "video[controls]", "audio[controls]",
        ...ROLES.map((r) => `[role=${r}]`),
    ].join(",");

    const CONTEXT = [
        ...contextSelectors,
        "[role=dialog]", "[role=row]", "tr", "li", "[role=listitem]",
        "article", "[role=article]", "fieldset",
    ];

    const IMPLICIT_ROLE = { a: "link", area: "link", button: "button", summary: "button", textarea: "textbox" };
    const INPUT_ROLE = {
        checkbox: "checkbox", radio: "radio", range: "slider", number: "spinbutton",
        search: "searchbox", button: "button", submit: "button", reset: "button",
        image: "button", file: "button",
    };

    const ICON_NOISE = new Set([
        "icon", "icons", "svg", "img", "image", "png", "jpg", "jpeg", "webp", "gif",
        "fas", "far", "fab", "fal", "solid", "regular", "light", "brands", "outline",
        "mdi", "glyphicon", "sprite", "static", "assets", "images", "default",
    ]);

    // ------------------------------------------------------------------
    // Utilitários
    // ------------------------------------------------------------------

    const clean = (s, n = maxText) => String(s || "").replace(/\s+/g, " ").trim().slice(0, n);

    // Palavras úteis de nomes de arquivo, classes e ids de ícones ("icon-shopping_cart.svg" → "shopping cart").
    const words = (s) => String(s || "")
        .replace(/\.[a-z0-9]{2,5}$/i, "")
        .split(/[^a-zA-Z]+/)
        .filter((w) => w.length >= 3 && !ICON_NOISE.has(w.toLowerCase()))
        .join(" ");

    const fileName = (url) =>
        !url || url.startsWith("data:") ? "" : words(url.split(/[?#]/)[0].split("/").pop());

    const iconClass = (c) =>
        /icon|^(fa|bi|mdi|ti|ri)-/i.test(c) ? words(c) : "";

    // Elemento com texto próprio (nó de texto filho direto), não só herdado dos filhos.
    const hasOwnText = (el) =>
        Array.from(el.childNodes).some((n) => n.nodeType === Node.TEXT_NODE && n.textContent.trim());

    // Percorre o DOM, entrando em shadow roots abertos.
    function* walk(root) {
        const it = document.createTreeWalker(root, NodeFilter.SHOW_ELEMENT);
        for (let el = it.nextNode(); el; el = it.nextNode()) {
            yield el;
            if (el.shadowRoot) yield* walk(el.shadowRoot);
        }
    }

    // "a contém b", atravessando fronteiras de shadow DOM.
    function containsDeep(a, b) {
        for (let n = b; n; n = n.parentNode || n.host) if (n === a) return true;
        return false;
    }

    // ------------------------------------------------------------------
    // Filtros
    // ------------------------------------------------------------------

    // Elementos que só entram pelo cursor:pointer (divs clicáveis) recebem o papel "clickable".
    const pointerOnly = new WeakSet();

    function isInteractive(el) {
        if (el.matches(INTERACTIVE)) return true;
        if (!detectPointer) return false;

        // cursor:pointer é herdado; fica só o elemento mais externo,
        // e só se ele não estiver dentro de um controle já reconhecido.
        if (getComputedStyle(el).cursor !== "pointer") return false;
        const parent = el.parentElement;
        const ok = !parent || (getComputedStyle(parent).cursor !== "pointer" && !parent.closest(INTERACTIVE));
        if (ok) pointerOnly.add(el);
        return ok;
    }

    // Modo "content": interativos + qualquer elemento com texto próprio + imagens com alt.
    function isContent(el) {
        if (el.matches(INTERACTIVE)) return true;
        if (el.tagName === "IMG") return !!el.getAttribute("alt");
        return hasOwnText(el);
    }

    function isVisible(el) {
        if (el.checkVisibility) {
            if (!el.checkVisibility({ checkOpacity: true, checkVisibilityCSS: true })) return false;
        } else {
            const s = getComputedStyle(el);
            if (s.display === "none" || s.visibility === "hidden" || s.opacity === "0") return false;
        }
        const r = el.getBoundingClientRect();
        return r.width > 0 && r.height > 0;
    }

    // ------------------------------------------------------------------
    // Extração
    // ------------------------------------------------------------------

    function roleOf(el, tag) {
        if (el.getAttribute("role")) return el.getAttribute("role");
        if (tag === "input") return INPUT_ROLE[el.type] || "textbox";
        if (tag === "select") return el.multiple ? "listbox" : "combobox";
        if (el.isContentEditable) return "textbox";
        if (pointerOnly.has(el)) return "clickable";
        return IMPLICIT_ROLE[tag] || tag;
    }

    function accessibleName(el) {
        const root = el.getRootNode();
        const byIds = (el.getAttribute("aria-labelledby") || "")
            .split(/\s+/)
            .map((id) => id && root.getElementById?.(id))
            .filter(Boolean)
            .map((e) => e.innerText || e.textContent)
            .join(" ");

        return clean(
            byIds
            || el.getAttribute("aria-label")
            || Array.from(el.labels || [], (l) => l.innerText).join(" ")
            || el.getAttribute("alt")
            || el.getAttribute("title")
            || el.getAttribute("placeholder")
        );
    }

    function visibleText(el, tag) {
        if (tag === "select" || tag === "input" || tag === "textarea") return "";
        return clean(el.innerText ?? el.textContent);
    }

    // Pistas visuais: alt de imagens, <title> de SVG, nome do arquivo, classes de ícone.
    // É o que identifica botões que só têm ícone.
    function visualHint(el) {
        const hints = [];
        const media = [el, ...el.querySelectorAll("img, svg, i, [class*=icon]")].slice(0, 6);

        for (const m of media) {
            const tag = m.tagName.toLowerCase();
            if (tag === "img" || (tag === "input" && m.type === "image")) {
                hints.push(m.getAttribute("alt"), m.getAttribute("title"), fileName(m.currentSrc || m.src));
            } else if (tag === "svg") {
                const use = m.querySelector("use");
                hints.push(
                    m.getAttribute("aria-label"),
                    m.querySelector("title")?.textContent,
                    words((use?.getAttribute("href") || use?.getAttribute("xlink:href") || "").split("#").pop())
                );
            }
            for (const c of m.classList) hints.push(iconClass(c));
        }

        const bg = getComputedStyle(el).backgroundImage;
        if (bg && bg !== "none") hints.push(fileName(bg.match(/url\(["']?(.*?)["']?\)/)?.[1]));

        return clean([...new Set(hints.map((h) => clean(h)).filter(Boolean))].join(" "), 100);
    }

    function valueOf(el, tag) {
        if (tag === "select") return clean(Array.from(el.selectedOptions, (o) => o.text).join(", "));
        if (tag === "input" && el.type === "password") return el.value ? "********" : ""; // senha nunca vai para a IA
        if (tag === "input" && ["checkbox", "radio", "button", "submit", "reset", "file"].includes(el.type)) return "";
        if (tag === "input" || tag === "textarea") return clean(el.value);
        return "";
    }

    function stateOf(el, tag) {
        const s = {};
        if (el.disabled || el.getAttribute("aria-disabled") === "true") s.disabled = true;
        if (el.required || el.getAttribute("aria-required") === "true") s.required = true;

        if (tag === "input" && (el.type === "checkbox" || el.type === "radio")) s.checked = el.checked;
        else if (el.hasAttribute("aria-checked")) s.checked = el.getAttribute("aria-checked") === "true";

        for (const a of ["expanded", "selected", "pressed"]) {
            const v = el.getAttribute("aria-" + a);
            if (v !== null) s[a] = v === "true";
        }
        return s;
    }

    const textCache = new Map();
    const innerTextOf = (node) => {
        if (!textCache.has(node)) textCache.set(node, node.innerText || "");
        return textCache.get(node);
    };

    const signature = (e) => e.tagName + "|" + e.className + "|" + innerTextOf(e).trim();

    // Seletor do caminho de "container" até "el" (tags + classes), ex.:
    // ":scope > div.card > h3 > a". Se ele casa com mais de um elemento,
    // o container repete a mesma estrutura: é uma lista, não um card.
    function structuralPath(container, el) {
        const parts = [];
        for (let n = el; n && n !== container; n = n.parentElement) {
            const classes = n.classList.length
                ? Array.from(n.classList, (c) => "." + CSS.escape(c)).join("")
                : ":not([class])";   // "a" sem classe não é gêmeo de "a.logo"
            parts.unshift(n.tagName.toLowerCase() + classes);
        }
        return ":scope > " + parts.join(" > ");
    }

    function hasTwin(container, el) {
        // Gêmeo idêntico (mesma tag, classe e texto) ...
        const sig = signature(el);
        for (const other of container.getElementsByTagName(el.tagName)) {
            if (other !== el && signature(other) === sig) return true;
        }
        // ... ou gêmeo estrutural (mesmo caminho de tags e classes).
        try {
            return container.querySelectorAll(structuralPath(container, el)).length > 1;
        } catch (e) {
            return false;
        }
    }

    function contextOf(el) {
        let container = null;
        for (const sel of CONTEXT) if ((container = el.closest(sel))) break;

        // Fallback genérico: sobe até 5 níveis e fica com o maior bloco que ainda
        // cabe em 400 caracteres. Para antes de um container que tenha um "gêmeo"
        // do elemento (mesma tag, classe e texto): ali já é a lista, não o card.
        if (!container) {
            let p = el.parentElement;
            for (let i = 0; i < 5 && p && p !== document.body; i++, p = p.parentElement) {
                if (innerTextOf(p).length > 400 || hasTwin(p, el)) break;
                container = p;
            }

            // Se o próprio pai já repete a estrutura (ex.: dois botões soltos
            // num cabeçalho), ele ainda é o melhor contexto disponível.
            const first = el.parentElement;
            if (!container && first && first !== document.body && innerTextOf(first).length <= 400) {
                container = first;
            }
        }
        // Texto original (sem minúsculas): o scoring normaliza por conta própria,
        // e o desempate mostra o contexto ao usuário.
        return container ? clean(innerTextOf(container), 300) : "";
    }

    // Camada aberta por cima da página: diálogo, menu, lista de sugestões, ou um
    // elemento fixo que cobre boa parte da tela (pop-ups sem papel ARIA).
    const LAYER_SEL = "dialog[open], [role=dialog], [role=alertdialog], [aria-modal=true], [role=listbox], [role=menu]";
    const layerCache = new Map();
    function isLayerRoot(n) {
        if (n.matches(LAYER_SEL)) return true;
        const s = getComputedStyle(n);
        if (s.position !== "fixed") return false;
        const r = n.getBoundingClientRect();
        return r.width * r.height >= 0.2 * innerWidth * innerHeight && r.height >= 0.3 * innerHeight;
    }
    function inLayer(el) {
        const path = [];
        let result = false;
        for (let n = el; n && n !== document.body && n.nodeType === 1; n = n.parentElement) {
            if (layerCache.has(n)) { result = layerCache.get(n); break; }
            path.push(n);
            if (isLayerRoot(n)) { result = true; break; }
        }
        for (const n of path) layerCache.set(n, result);
        return result;
    }

    function geometry(el) {
        const r = el.getBoundingClientRect();
        const inViewport = r.bottom > 0 && r.right > 0 && r.top < innerHeight && r.left < innerWidth;

        // Coberto por outro elemento (modal, banner de cookies, overlay)?
        let obscured = false;
        if (inViewport) {
            const x = Math.min(Math.max(r.left + r.width / 2, 0), innerWidth - 1);
            const y = Math.min(Math.max(r.top + r.height / 2, 0), innerHeight - 1);
            let hit = document.elementFromPoint(x, y);
            while (hit?.shadowRoot) {
                const inner = hit.shadowRoot.elementFromPoint(x, y);
                if (!inner || inner === hit) break;
                hit = inner;
            }
            obscured = !!hit && !containsDeep(el, hit) && !containsDeep(hit, el);
        }

        const rect = { x: Math.round(r.x), y: Math.round(r.y), width: Math.round(r.width), height: Math.round(r.height) };
        return { rect, inViewport, obscured };
    }

    // ------------------------------------------------------------------
    // Execução
    // ------------------------------------------------------------------

    const matches = selector ? (el) => el.matches(selector)
        : mode === "content" ? isContent
        : isInteractive;
    const records = [];
    let index = 0;

    for (const el of walk(document.body || document.documentElement)) {
        el.removeAttribute(ATTR); // limpa IDs de indexações anteriores

        if (records.length >= maxElements) continue;
        if (!matches(el)) continue;
        if (!includeHidden && !isVisible(el)) continue;

        const id = "el-" + index++;
        el.setAttribute(ATTR, id);

        const tag = el.tagName.toLowerCase();
        const role = roleOf(el, tag);
        const label = accessibleName(el);
        const text = visibleText(el, tag);
        const value = valueOf(el, tag);
        const hint = visualHint(el);
        const type = tag === "input" || tag === "button" ? el.type : "";
        const href = el.href ? clean(el.getAttribute("href"), 150) : "";
        const testId = el.getAttribute("data-testid") || el.getAttribute("data-test") || el.getAttribute("data-qa") || "";

        const content = [...new Set([
            label, text, value, hint,
            el.getAttribute("placeholder"), el.getAttribute("title"), el.getAttribute("name"),
            testId, el.id, tag, role, type,
        ].filter(Boolean))].join(" ").toLowerCase();

        const record = {
            id, tag, role, type, label, text, value, hint, href, testId,
            state: stateOf(el, tag),
            layer: inLayer(el),
            context: contextOf(el),
            content,
            ...geometry(el),
        };

        if (tag === "select") {
            record.options = Array.from(el.options, (o) => clean(o.text, 60)).slice(0, 30);
        }

        records.push(record);
    }

    return records;
}