import { defineConfig } from "vitepress";

// The docs site at blueprint.karolnov.dev. `npm run docs:build` first writes docs/public/map.html
// with `graph.py --no-drift`, so the Capability map page embeds this commit's own map.
export default defineConfig({
  title: "Blueprint",
  description:
    "Claude Code skills for architecting larger changes against capability specs, and keeping specs and code in step.",
  cleanUrls: true,
  lastUpdated: false,
  // map.html is a static file in public/, not a page: links to it are fine.
  ignoreDeadLinks: [/^\/map\.html/],
  head: [["meta", { name: "theme-color", content: "#3451b2" }]],
  themeConfig: {
    nav: [
      { text: "Get started", link: "/getting-started" },
      { text: "Modes", link: "/modes/propose" },
      { text: "Capability map", link: "/capability-map" },
      { text: "GitHub", link: "https://github.com/KarolNov/skills" },
    ],
    sidebar: [
      {
        text: "Introduction",
        items: [
          { text: "What is blueprint?", link: "/" },
          { text: "Getting started", link: "/getting-started" },
        ],
      },
      {
        text: "Modes",
        items: [
          { text: "Setup", link: "/modes/setup" },
          { text: "Propose", link: "/modes/propose" },
          { text: "Apply", link: "/modes/apply" },
          { text: "Ask", link: "/modes/ask" },
          { text: "Map", link: "/modes/map" },
          { text: "Coverage", link: "/modes/coverage" },
          { text: "Drift", link: "/modes/drift" },
          { text: "Sync", link: "/modes/sync" },
          { text: "Tidy", link: "/modes/tidy" },
          { text: "Backfill", link: "/modes/backfill" },
        ],
      },
      {
        text: "Reference",
        items: [
          { text: "Review pane", link: "/review-pane" },
          { text: "Backends", link: "/backends" },
          { text: "Upgrading", link: "/upgrading" },
          { text: "Capability map", link: "/capability-map" },
        ],
      },
    ],
    search: { provider: "local" },
    socialLinks: [{ icon: "github", link: "https://github.com/KarolNov/skills" }],
    footer: { message: "MIT licensed", copyright: "Karol Novljaković" },
  },
});
