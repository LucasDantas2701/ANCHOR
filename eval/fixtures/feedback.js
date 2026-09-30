// Resposta visível às ações, como a de um site real. As páginas de teste não têm
// servidor, então muitos botões não fariam nada visível; sem isto, a verificação do
// efeito do agente acusaria "sem efeito" em ações que, num site real, teriam efeito.
// O aviso não é interativo e não entra no índice do ANCHOR.
(() => {
    let count = 0;
    const show = (text) => {
        let box = document.getElementById("__feedback");
        if (!box) {
            box = document.createElement("div");
            box.id = "__feedback";
            box.setAttribute("aria-hidden", "true");
            box.style.cssText = "position:fixed;bottom:4px;right:4px;font:11px sans-serif;" +
                "background:#eee;color:#555;padding:2px 6px;pointer-events:none";
            document.body.appendChild(box);
        }
        box.textContent = `${text} (${++count})`;
    };
    const ACTIONABLE = "a, button, summary, [role=button], [role=option], [role=tab], [role=switch], [onclick], .chip, .lupa";
    document.addEventListener("click", (e) => {
        if (e.target.closest && e.target.closest(ACTIONABLE)) show("Ação registrada");
    });
    document.addEventListener("keydown", (e) => {
        if (e.key === "Enter" && e.target.matches && e.target.matches("input, textarea")) show("Tecla Enter recebida");
    });
})();
