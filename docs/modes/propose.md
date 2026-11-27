# Propose

```
/blueprint <the change you have in mind>
```

This is the main mode. You arrive with a **concrete solution**, not an open question, and blueprint helps you sharpen it and write it down. It treats your design as the starting point. It only challenges the design where it collides with a fact.

## 1. Play it back

Blueprint reads the code the change touches, the capability specs for it, other open blueprints touching the same capabilities, and any glossary or ADRs. Then it plays your solution back in a short block (destination, solution, what it touches, what is out of scope, what it collides with), along with a rough before/after sketch. Correct it, or say yes. From then on, the destination and the scope are fixed.

## 2. Grill the solution

The questions test *your* design. Blueprint isn't looking for a better one. A question is only asked if its answer changes the spec, an interface, a data shape, a migration or a test. Blueprint decides everything else itself and lists it under **Assumed** for you to skim.

Questions come in rounds of up to five, each with a recommendation, so you can answer a whole round in one line: *"yes, 2: no, keep the cookie, rest yes"*. Grilling stops after three rounds at most. Anything still open goes into the brief as an open question.

When talk can't settle something, blueprint can **research** a fact from primary sources, such as an API's limits. Or it can build a throwaway **prototype** so you can choose how something should look or behave.

## 3. The blueprint

A blueprint is written as two documents side by side in your [backend](/backends):

- **The brief**, for agents: the destination, decisions with their reasons, the **spec delta** (requirements added, modified, removed or renamed, per capability), a code map, and tasks. It is the source of truth. Apply and sync read nothing else.
- **The review**, for people: a picture first, then the same change in plain words. Every review opens with a before → after diagram with the change colored in. If the change involves behavior over time (retries, ordering, offline, caching), blueprint offers a **playground**: a small interactive model with scenario buttons, knobs and a before/after switch.

You see the draft before anything is written. After you approve it, the tasks become tickets in your tracker, if you use one.

## Next

Build it with [Apply](/modes/apply). To comment on the review from inside Claude Code, use the [review pane](/review-pane).
