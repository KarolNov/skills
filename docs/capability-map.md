---
layout: page
title: Capability map
---

<div class="map-page">

# Capability map

This repo runs blueprint on itself. Below is its own capability map, built from the same commit as this site. Click a capability for its requirements and the tests that claim them. To search the map, click it first, then press <kbd>/</kbd> (outside the map, <kbd>/</kbd> searches this site). [Map](/modes/map) explains everything on it.

Drift is not shown on this map. It lives on the [blueprint project page](https://karolnov.dev/projects/blueprint).

<iframe class="map-frame" src="/map.html" title="Blueprint's capability map" loading="lazy"></iframe>

<p class="map-open"><a href="/map.html" target="_blank" rel="noopener">Open the map full screen ↗</a></p>

</div>

<style>
.map-page { max-width: 1440px; margin: 0 auto; padding: 32px 24px 48px; }
.map-page h1 { font-size: 32px; font-weight: 600; line-height: 40px; margin-bottom: 12px; }
.map-page p { line-height: 1.7; margin: 8px 0; color: var(--vp-c-text-2); }
.map-page a { color: var(--vp-c-brand-1); text-decoration: underline; text-underline-offset: 2px; }
.map-frame { display: block; width: 100%; height: calc(100vh - 220px); min-height: 520px; margin-top: 20px;
  border: 1px solid var(--vp-c-divider); border-radius: 8px; background: var(--vp-c-bg); }
@media (max-width: 640px) { .map-page { padding: 24px 16px; } .map-frame { height: 75vh; } }
</style>
