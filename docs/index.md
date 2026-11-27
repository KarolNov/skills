---
layout: home
hero:
  name: Blueprint
  text: You bring the solution. Blueprint writes it down, builds it, and keeps it true.
  tagline: Claude Code skills for architecting larger changes against capability specs, and keeping specs and code from drifting apart.
  actions:
    - theme: brand
      text: Get started
      link: /getting-started
    - theme: alt
      text: See the capability map
      link: /capability-map
features:
  - title: Solution-first grilling
    details: Blueprint pressure-tests the design you already have in a few short rounds of questions. It doesn't go hunting for a different one.
    link: /modes/propose
  - title: Specs where your team reads
    details: Capability specs and blueprints live in Notion, Obsidian, Linear, Jira, GitHub or a notes folder. Only a small map of them lives in the repo.
    link: /backends
  - title: Specs and code stay honest
    details: Drift detection from git alone, and two skills that reconcile it, by whichever side is right.
    link: /modes/drift
  - title: Tests point at scenarios
    details: A comment tag above a test claims a spec scenario. Coverage shows which scenarios no test claims.
    link: /modes/coverage
---

## What is blueprint?

Blueprint is a family of [Claude Code](https://claude.com/claude-code) skills for larger, architected changes. You describe the solution you have in mind, and blueprint:

1. **Grills it**, briefly. It asks only the questions whose answers change the spec, an interface, a data shape or a test.
2. **Writes it up** as a *blueprint*: a text **brief** for agents (decisions, the spec change, tasks) and a visual **review** for people, side by side in your notes tool.
3. **Builds it** task by task, checks every requirement against the code, then folds the change into the **capability specs**: the lasting description of what each part of the system does.
4. **Keeps the specs and the code in step** afterwards. Each capability is mapped to the code that implements it, so blueprint can tell from git when one side moved without the other.

It sits between [wayfinder](https://github.com/mattpocock/skills) and [OpenSpec](https://github.com/Fission-AI/OpenSpec): more structure than a plan in chat, with less ceremony than a spec-first process.

## The pieces

- **Capability spec**: one page per capability (`auth/session`, say), with requirements and scenarios. It says what the capability does, never how.
- **Blueprint**: one change, written twice. The **brief** is the source of truth. The **review** leads with a diagram, and when the change involves behavior over time it can include an interactive playground.
- **Domain**: a group of related capabilities, with an overview page that holds them like a folder.
- **`.blueprint/`**: the only part that lives in the repo. It maps each capability to its page and its *anchors* (globs for its code), and keeps the spec text from the last sync so changes can be merged three ways.

This repo runs blueprint on itself. Its [capability map](/capability-map) is rebuilt from the repo on every deploy.
