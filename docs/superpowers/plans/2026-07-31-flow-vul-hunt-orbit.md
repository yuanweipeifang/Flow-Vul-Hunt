# Flow-Vul-Hunt Orbit Navigation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Upgrade the home-page orbit visualization into an accessible eight-module Flow-Vul-Hunt navigation graph.

**Architecture:** Keep the existing SVG orbit renderer and React Router. Define one shared node data array in `HomePage.tsx`; render decorative SVG geometry plus HTML buttons/description overlay so hover, keyboard focus, and click behavior are reliable.

**Tech Stack:** React 19, TypeScript, React Router 7, Vite, CSS animations.

---

### Task 1: Define the eight navigation nodes and interaction contract

**Files:**
- Modify: `frontend/src/pages/HomePage.tsx`

- [ ] Add eight node definitions with routes `/console`, `/datasets`, `/events`, `/incidents`, `/vulnerabilities`, `/hunt`, `/jobs`, `/agent`, retaining the existing accent variables and concise Chinese descriptions.
- [ ] Add local `activeNode` state and derive `isPaused` from whether a node is active.
- [ ] Keep `useNavigate` as the navigation mechanism and expose node buttons with `aria-label` and keyboard activation through native buttons.

### Task 2: Replace the six-node SVG core with an eight-node orbit

**Files:**
- Modify: `frontend/src/pages/HomePage.tsx`

- [ ] Calculate node positions from eight evenly spaced angles around the SVG center.
- [ ] Render the center label as three lines: `Flow`, `Vul`, `Hunt`.
- [ ] Render all decorative lines and node circles from the shared node array so the count cannot drift from navigation data.
- [ ] Add the active node label and description overlay next to the SVG, with a route CTA that navigates to the same node.

### Task 3: Implement smooth hover/focus styling and responsive layout

**Files:**
- Modify: `frontend/src/App.css`

- [ ] Add `.orbit-node-hit`, `.orbit-node-visual`, `.orbit-node-card`, and active-state styles with transform/opacity/box-shadow transitions.
- [ ] Ensure hover/focus pauses the orbit animation and increases node scale without changing layout.
- [ ] Add responsive rules for the overlay and reduced-motion behavior.

### Task 4: Verify behavior and build output

**Files:**
- Test: `frontend` project scripts

- [ ] Run `npm run lint` from `frontend` and confirm exit code 0.
- [ ] Run `npm run build` from `frontend` and confirm Vite emits a production bundle.
- [ ] Inspect the rendered page in the local browser at the Vite URL, verify eight nodes, hover description, click routing, and keyboard focus.

