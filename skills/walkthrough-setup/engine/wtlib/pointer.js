// Walkthrough overlay: an animated dot standing in for the cursor, plus click
// ripples, element highlights and a step label. Injected into every page as an
// init script; the recorder drives it through window.__wt. Init scripts also run in
// iframes, which would each get a stray dot, so only the top frame mounts it.
(() => {
  if (window.__wt || window !== window.top) return;
  const COLOR = "__WT_COLOR__";
  const KEY = "__wt_pos";
  const pos = { x: window.innerWidth / 2, y: window.innerHeight / 2 };
  try {
    const saved = JSON.parse(sessionStorage.getItem(KEY));
    if (saved) Object.assign(pos, saved);
  } catch (e) {}

  let host, shadow, dot, labelEl;

  const css = `
    :host { all: initial; }
    .layer { position: fixed; inset: 0; pointer-events: none; z-index: 2147483647; }
    .dot { position: fixed; left: 0; top: 0; width: 20px; height: 20px; margin: -10px 0 0 -10px;
      border-radius: 50%; background: ${COLOR}; border: 2px solid #fff; box-sizing: border-box;
      box-shadow: 0 2px 10px rgba(0,0,0,.35); opacity: .95; transition: scale .12s ease; }
    .dot.down { scale: .7; }
    .ripple { position: fixed; width: 20px; height: 20px; margin: -10px 0 0 -10px; border-radius: 50%;
      border: 3px solid ${COLOR}; box-sizing: border-box; animation: ripple .55s ease-out forwards; }
    @keyframes ripple { from { scale: 1; opacity: .9; } to { scale: 3.2; opacity: 0; } }
    .hl { position: fixed; border: 3px solid ${COLOR}; border-radius: 10px; box-sizing: border-box;
      opacity: 0; transition: opacity .25s ease; }
    .hl.dim { box-shadow: 0 0 0 9999px rgba(0,0,0,.35); }
    .hl.on { opacity: 1; }
    .label { position: fixed; left: 28px; bottom: 28px; max-width: 70vw; padding: 10px 18px;
      border-radius: 999px; background: rgba(17,17,17,.88); color: #fff;
      font: 600 18px/1.3 -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
      box-shadow: 0 4px 18px rgba(0,0,0,.25); opacity: 0; translate: 0 8px;
      transition: opacity .25s ease, translate .25s ease; }
    .label.on { opacity: 1; translate: 0 0; }
  `;

  function mount() {
    if (host && host.isConnected) return;
    host = document.createElement("walkthrough-overlay");
    shadow = host.attachShadow({ mode: "open" });
    shadow.innerHTML = `<style>${css}</style><div class="layer"><div class="dot"></div><div class="label"></div></div>`;
    dot = shadow.querySelector(".dot");
    labelEl = shadow.querySelector(".label");
    document.documentElement.appendChild(host);
    place();
  }

  function place() {
    if (dot) dot.style.translate = `${pos.x}px ${pos.y}px`;
  }

  function set(x, y) {
    pos.x = x;
    pos.y = y;
    mount();
    place();
    try { sessionStorage.setItem(KEY, JSON.stringify(pos)); } catch (e) {}
  }

  function layer() {
    mount();
    return shadow.querySelector(".layer");
  }

  window.__wt = {
    set,
    press(down) {
      mount();
      dot.classList.toggle("down", down);
      if (down) {
        const ripple = document.createElement("div");
        ripple.className = "ripple";
        ripple.style.left = pos.x + "px";
        ripple.style.top = pos.y + "px";
        layer().appendChild(ripple);
        setTimeout(() => ripple.remove(), 700);
      }
    },
    highlight(rect, ms, dim) {
      const el = document.createElement("div");
      el.className = "hl" + (dim ? " dim" : "");
      const pad = 6;
      Object.assign(el.style, {
        left: rect.x - pad + "px", top: rect.y - pad + "px",
        width: rect.width + pad * 2 + "px", height: rect.height + pad * 2 + "px",
      });
      layer().appendChild(el);
      requestAnimationFrame(() => el.classList.add("on"));
      setTimeout(() => el.classList.remove("on"), Math.max(ms - 250, 0));
      setTimeout(() => el.remove(), ms + 50);
    },
    label(text) {
      mount();
      if (text) labelEl.textContent = text;
      labelEl.classList.toggle("on", !!text);
    },
    hide(hidden) {
      mount();
      dot.style.display = hidden ? "none" : "";
    },
  };

  window.addEventListener("mousemove", (e) => set(e.clientX, e.clientY), true);
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", mount);
  } else {
    mount();
  }
})();
