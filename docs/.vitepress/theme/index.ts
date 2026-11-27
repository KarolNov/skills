import DefaultTheme from "vitepress/theme";
import type { Theme } from "vitepress";
import "./custom.css";

// How far the landing page's blueprint sheet tilts toward the pointer, in degrees.
const MAX_TILT = 12;

/**
 * Tilts the hero sheet in 3D toward the mouse while it is over it, and lets it settle back when the
 * mouse leaves (the transition lives in custom.css). Mouse only, and off for reduced motion.
 */
function tiltHeroSheet() {
  const fine = window.matchMedia("(hover: hover) and (pointer: fine)");
  const still = window.matchMedia("(prefers-reduced-motion: reduce)");
  let sheet: HTMLElement | null = null;

  const release = () => {
    if (!sheet) return;
    sheet.style.removeProperty("rotate");
    sheet.style.removeProperty("scale");
    sheet.classList.remove("is-tilting");
    sheet = null;
  };

  document.addEventListener("pointermove", (e) => {
    if (!fine.matches || still.matches) return;
    const box = (e.target as Element | null)?.closest?.(".VPHero .image-container");
    const img = box?.querySelector<HTMLElement>(".image-src");
    if (!box || !img) return release();
    // Measured on the container, which doesn't move, so the tilt doesn't feed back into itself.
    const r = box.getBoundingClientRect();
    // -1 … 1 from the sheet's centre, clamped so the edge of the container doesn't overshoot.
    const dx = Math.max(-1, Math.min(1, (e.clientX - (r.left + r.width / 2)) / (r.width / 2)));
    const dy = Math.max(-1, Math.min(1, (e.clientY - (r.top + r.height / 2)) / (r.height / 2)));
    const ax = -dy * MAX_TILT; // pointer above the centre tips the top toward the reader
    const ay = dx * MAX_TILT;
    const angle = Math.hypot(ax, ay);
    sheet = img;
    img.classList.add("is-tilting");
    img.style.rotate = angle < 0.01 ? "x 0deg" : `${ax} ${ay} 0 ${angle}deg`;
    img.style.scale = "1.04";
  });
  document.documentElement.addEventListener("pointerleave", release);
}

export default {
  extends: DefaultTheme,
  enhanceApp() {
    if (typeof window !== "undefined") tiltHeroSheet();
  },
} satisfies Theme;
