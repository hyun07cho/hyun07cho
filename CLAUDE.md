# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What This Repository Is

This is a GitHub special profile repository (`hyun07cho/hyun07cho`) that serves a static career portfolio page via **GitHub Pages**. The entire site lives in a single file: `index.html`.

- `index.html` — Self-contained HTML/CSS portfolio page (Korean-language, ~700 lines)
- `.nojekyll` — Tells GitHub Pages to skip Jekyll processing and serve the HTML directly

There is no build step, no package manager, no JavaScript framework, and no test suite.

## Editing the Site

Edit `index.html` directly. To preview locally, open it in a browser:

```bash
open index.html          # macOS
xdg-open index.html      # Linux
```

Changes pushed to `main` are automatically deployed to GitHub Pages.

## Page Structure

The HTML is organized into named anchor sections:

| Anchor | Content |
|---|---|
| `#future-jobs` | 미래유망직무 TOP 3 — three job-card articles |
| `#core-skills` | 핵심 역량 — three competency items with evidence grids |
| `#roadmap` | 4년 로드맵 — vertical timeline with four year entries |
| `#checklist` | 핵심 역량 Checklist — three check-cards |

Navigation links at the top (`<nav>`) reference these anchors.

## CSS Conventions

All colors and shadows are defined as CSS custom properties on `:root` at the top of the `<style>` block (e.g. `--bg-color`, `--primary-color`, `--accent-color`). Use these variables rather than hardcoded hex values when adding or modifying styles.

Responsive breakpoints:
- `max-width: 900px` — collapses multi-column grids (`.job-container`, `.evidence-list`, `.checklist-grid`) to single-column
- `max-width: 600px` — adjusts nav font size and hero alignment

## Content Language

All visible content is written in Korean (`lang="ko"`). The font is Pretendard (loaded from Google Fonts). Maintain Korean for user-facing text unless the owner explicitly requests a change.
