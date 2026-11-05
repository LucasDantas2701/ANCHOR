(() => {
    let count = 0;
    const en = (document.documentElement.lang || "").startsWith("en");
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
        if (e.target.closest && e.target.closest(ACTIONABLE)) show(en ? "Action recorded" : "Ação registrada");
    });
    document.addEventListener("keydown", (e) => {
        if (e.key === "Enter" && e.target.matches && e.target.matches("input, textarea")) show(en ? "Enter key received" : "Tecla Enter recebida");
    });
})();
