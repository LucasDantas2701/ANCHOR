// The annotation recorder, injected in every page of a task (eval/annotate.py). It shows the request
// and the buttons in a panel at the top (in a shadow root, so it is never recorded and never changes the
// page's own elements), and records what the person does: fields filled, options chosen, boxes ticked,
// buttons and links clicked, Enter pressed. The steps survive a page change (sessionStorage).
(() => {
    if (window.top !== window) return;
    const KEY = "__annot_steps";
    const load = () => { try { return JSON.parse(sessionStorage.getItem(KEY) || "[]"); } catch (e) { return []; } };
    const save = (s) => sessionStorage.setItem(KEY, JSON.stringify(s));
    window.__annot = window.__annot || { state: "working", reason: "", answer: "", texts: [] };
    const css = (s) => (window.CSS && CSS.escape ? CSS.escape(s) : s.replace(/[^\w-]/g, "\\$&"));
    const unique = (sel) => { try { return document.querySelectorAll(sel).length === 1; } catch (e) { return false; } };

    // A selector a person would write: the id, the name, the test id, then a short path.
    function selector(el) {
        if (el.id && unique("#" + css(el.id))) return "#" + css(el.id);
        const tag = el.tagName.toLowerCase();
        const name = el.getAttribute("name");
        if (name && (el.type === "radio" || el.type === "checkbox") && el.value) {
            const s = `input[name="${name}"][value="${el.value}"]`; if (unique(s)) return s;
        }
        if (name && unique(`${tag}[name="${name}"]`)) return `${tag}[name="${name}"]`;
        for (const a of ["data-testid", "data-test", "aria-label"]) {
            const v = el.getAttribute(a); if (v && unique(`${tag}[${a}="${v}"]`)) return `${tag}[${a}="${v}"]`;
        }
        const parts = []; let e = el;
        while (e && e !== document.body && parts.length < 6) {
            if (e.id && unique("#" + css(e.id))) { parts.unshift("#" + css(e.id)); break; }
            const t = e.tagName.toLowerCase(); const sib = [...e.parentElement.children].filter((x) => x.tagName === e.tagName);
            parts.unshift(sib.length > 1 ? `${t}:nth-of-type(${sib.indexOf(e) + 1})` : t);
            e = e.parentElement;
        }
        return parts.join(" > ");
    }
    function label(el) {
        const lab = el.labels && el.labels[0] ? el.labels[0].innerText : "";
        return (el.getAttribute("aria-label") || lab || el.getAttribute("placeholder") || el.innerText || el.value || "")
            .replace(/\s+/g, " ").trim().slice(0, 60);
    }
    function kind(el) {
        if (el.tagName === "SELECT") return "lista";
        if (el.type === "checkbox") return "caixa";
        if (el.type === "radio") return "opção";
        if (el.tagName === "A") return "link";
        if (el.matches("button, [role=button], input[type=submit], input[type=button]")) return "botão";
        return "campo";
    }
    const inPanel = (el) => el && el.closest && el.closest("#__annot_host");
    function add(step) {
        const steps = load();
        if (step.action === "fill" || step.action === "select") {           // a field keeps its last value, in its place
            const i = steps.findIndex((s) => s.action === step.action && s.selector === step.selector);
            if (i >= 0) { steps[i] = step; save(steps); draw(); return; }
        }
        if (step.action === "uncheck") {
            const i = steps.findIndex((s) => s.action === "check" && s.selector === step.selector);
            if (i >= 0) { steps.splice(i, 1); save(steps); return; }
        }
        steps.push(step); save(steps); draw();
    }
    document.addEventListener("click", (ev) => {
        if (inPanel(ev.target)) return;
        const el = ev.target.closest("button, a[href], [role=button], input[type=submit], input[type=button]");
        if (el) add({ action: "click", selector: selector(el), label: `${kind(el)} ${label(el)}`, value: null });
    }, true);
    document.addEventListener("change", (ev) => {
        const el = ev.target; if (inPanel(el)) return;
        if (el.tagName === "SELECT") add({ action: "select", selector: selector(el), label: `lista ${label(el)}`, value: el.selectedOptions[0] ? el.selectedOptions[0].text.trim() : "" });
        else if (el.type === "checkbox" || el.type === "radio") add({ action: el.checked ? "check" : "uncheck", selector: selector(el), label: `${kind(el)} ${label(el)}`, value: null });
        else if (el.matches("input, textarea")) add({ action: "fill", selector: selector(el), label: `campo ${label(el)}`, value: el.value });
    }, true);
    document.addEventListener("keydown", (ev) => {
        if (ev.key !== "Enter" || inPanel(ev.target) || !ev.target.matches || !ev.target.matches("input")) return;
        const el = ev.target;
        add({ action: "fill", selector: selector(el), label: `campo ${label(el)}`, value: el.value });
        add({ action: "press", selector: selector(el), label: `campo ${label(el)}`, value: "Enter" });
    }, true);

    // ------------------------------------------------------------------ the panel
    let shadow = null;
    function selected() { return (window.getSelection() + "").replace(/\s+/g, " ").trim(); }
    function draw() {
        if (!shadow) return;
        shadow.getElementById("steps").textContent = load().map((s, i) => `${i + 1}. ${s.action} ${s.label}${s.value ? ` = "${s.value}"` : ""}`).join("\n") || "(nenhum passo ainda)";
        shadow.getElementById("texts").textContent = window.__annot.texts.map((t) => `• "${t}"`).join("\n");
    }
    function build() {
        if (document.getElementById("__annot_host")) return;
        const host = document.createElement("div"); host.id = "__annot_host";
        host.style.cssText = "position:fixed;left:0;right:0;bottom:0;z-index:2147483647";
        shadow = host.attachShadow({ mode: "open" });
        const req = (window.__annot_task || {}).request || "";
        shadow.innerHTML = `<style>
          .p{font:13px system-ui,sans-serif;background:#1e1b2e;color:#fff;padding:10px 12px;border-top:3px solid #c6f432;max-height:45vh;overflow:auto}
          .r{font-size:15px;font-weight:600;margin:4px 0 8px} button{font:inherit;margin:2px 4px 2px 0;padding:5px 9px;border-radius:5px;border:0;cursor:pointer}
          .ok{background:#c6f432} .q{background:#b9a7ff} .no{background:#ff9b9b} .sec{background:#ddd} pre{white-space:pre-wrap;margin:6px 0;color:#ddd}
          input{width:60%;padding:4px}</style>
          <div class="p"><div>${(window.__annot_task || {}).id || ""} · faça o pedido na página, como um usuário faria:</div>
          <div class="r" id="req"></div>
          <button class="ok" id="done">Pronto: fiz o pedido</button>
          <button class="q" id="answer">É uma pergunta: a resposta está selecionada</button>
          <button class="sec" id="text">Conferir também o texto selecionado</button>
          <button class="no" id="no">Não é possível nesta página</button>
          <input id="why" placeholder="por que não é possível (obrigatório para esse botão)">
          <button class="sec" id="restart">Recomeçar</button> <button class="sec" id="skip">Pular por agora</button>
          <div id="msg" style="color:#ffd27a;margin-top:4px"></div><pre id="steps"></pre><pre id="texts"></pre></div>`;
        shadow.getElementById("req").textContent = req;
        const set = (state, extra) => Object.assign(window.__annot, { state }, extra || {});
        const say = (m) => { shadow.getElementById("msg").textContent = m; };
        shadow.getElementById("done").onclick = () => set("done");
        shadow.getElementById("answer").onclick = () => { const a = selected(); if (!a) return say("Selecione com o mouse o trecho da página que responde, e clique de novo."); set("answer", { answer: a }); };
        shadow.getElementById("text").onclick = () => { const t = selected(); if (!t) return say("Selecione com o mouse o texto que deve aparecer no fim, e clique de novo."); window.__annot.texts.push(t); draw(); };
        shadow.getElementById("no").onclick = () => { const w = shadow.getElementById("why").value.trim(); if (!w) return say("Escreva, na caixa ao lado, por que não é possível."); set("impossible", { reason: w }); };
        shadow.getElementById("restart").onclick = () => { sessionStorage.removeItem(KEY); set("restart"); };
        shadow.getElementById("skip").onclick = () => set("skip");
        document.body.appendChild(host); draw();
    }
    if (document.body) build(); else document.addEventListener("DOMContentLoaded", build);
})();
