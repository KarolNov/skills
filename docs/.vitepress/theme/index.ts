import DefaultTheme from "vitepress/theme";
import type { Theme } from "vitepress";
import "./custom.css";

// How far the landing page's blueprint sheet tilts, in degrees per axis.
const MAX_TILT = 12;
// How far the phone has to turn, in degrees, for the sheet to reach MAX_TILT.
const PHONE_RANGE = 25;
// How quickly the phone's "level" follows the way it is held, per reading: a new grip settles back.
const PHONE_RELEVEL = 0.01;

const clamp = (v: number) => Math.max(-1, Math.min(1, v));
const sheetEl = () => document.querySelector<HTMLElement>(".VPHero .image-src");

/** Tilts the sheet by dx, dy in -1 … 1 (right, down), around its centre (see custom.css). */
function tilt(img: HTMLElement, dx: number, dy: number) {
  const ax = -dy * MAX_TILT; // down tips the bottom toward the reader
  const ay = dx * MAX_TILT;
  const angle = Math.hypot(ax, ay);
  img.classList.add("is-tilting");
  img.style.rotate = angle < 0.01 ? "x 0deg" : `${ax} ${ay} 0 ${angle}deg`;
  img.style.scale = "1.04";
}

function untilt(img: HTMLElement | null) {
  if (!img) return;
  img.style.removeProperty("rotate");
  img.style.removeProperty("scale");
  img.classList.remove("is-tilting");
}

/** With a mouse: tilt toward the pointer while it is over the sheet, settle back when it leaves. */
function followMouse() {
  let tilted: HTMLElement | null = null;
  const release = () => {
    untilt(tilted);
    tilted = null;
  };

  document.addEventListener("pointermove", (e) => {
    if (e.pointerType !== "mouse") return;
    const box = (e.target as Element | null)?.closest?.(".VPHero .image-container");
    const img = box?.querySelector<HTMLElement>(".image-src");
    if (!box || !img) return release();
    // Measured on the container, which doesn't move, so the tilt doesn't feed back into itself.
    const r = box.getBoundingClientRect();
    tilted = img;
    tilt(img, clamp((e.clientX - r.left) / (r.width / 2) - 1), clamp((e.clientY - r.top) / (r.height / 2) - 1));
  });
  document.documentElement.addEventListener("pointerleave", release);
}

/**
 * On a phone: tilt with the gyroscope. The way the phone is held counts as level, so the sheet moves
 * as it is turned from there. iOS asks for permission first, on the first tap on the sheet.
 */
function followPhone() {
  let level: { x: number; y: number } | null = null;
  let frame = 0;

  const onOrientation = (e: DeviceOrientationEvent) => {
    if (e.beta === null || e.gamma === null) return;
    // beta tips the top away, gamma tips the right side down, both relative to the screen held
    // upright; turn them with the screen when the phone is on its side.
    const turn = (screen.orientation?.angle ?? 0) % 360;
    const [x, y] =
      turn === 90 ? [e.beta, -e.gamma] : turn === 270 ? [-e.beta, e.gamma] : [e.gamma, e.beta];
    if (!level) level = { x, y };
    level.x += (x - level.x) * PHONE_RELEVEL;
    level.y += (y - level.y) * PHONE_RELEVEL;
    const dx = clamp((x - level.x) / PHONE_RANGE);
    const dy = clamp((y - level.y) / PHONE_RANGE);
    cancelAnimationFrame(frame);
    frame = requestAnimationFrame(() => {
      const img = sheetEl();
      if (img) tilt(img, dx, dy);
    });
  };

  const listen = () => window.addEventListener("deviceorientation", onOrientation);
  screen.orientation?.addEventListener?.("change", () => (level = null));

  const DOE = DeviceOrientationEvent as unknown as { requestPermission?: () => Promise<string> };
  if (typeof DOE.requestPermission !== "function") return listen();
  const onTap = (e: Event) => {
    if (!(e.target as Element | null)?.closest?.(".VPHero .image-container")) return;
    document.removeEventListener("click", onTap);
    DOE.requestPermission!().then((answer) => answer === "granted" && listen(), () => {});
  };
  document.addEventListener("click", onTap);
}

function tiltHeroSheet() {
  if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;
  followMouse();
  if (window.matchMedia("(hover: none) and (pointer: coarse)").matches && "DeviceOrientationEvent" in window) {
    followPhone();
  }
}

export default {
  extends: DefaultTheme,
  enhanceApp() {
    if (typeof window !== "undefined") tiltHeroSheet();
  },
} satisfies Theme;
