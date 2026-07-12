# AI4Papers Research Workspace Design QA

Scope: phases 2–3 — shared research workspace shell, responsive secondary toolbar, card/list mode switch, dense paper list, persistent paper inspector, selection, and bulk actions. The immersive reader and remaining page migrations are not claimed as complete here.

- Source visual truth: `C:\Users\Liu Lin\.codex\generated_images\019f4f0d-dd4d-70a0-96aa-b8985fd41394\exec-7296fdea-5561-486f-9ff7-b41c460af9de.png`
- Implementation route: `http://127.0.0.1:4174/?view=list&digest_paper=2605.20022`
- Primary implementation screenshot: `D:\Datas\Programming\Cursor\AI4Paper02\ArxivPaper4\View\test-results\workspace-shell-list-light-1488x1045.png`
- Responsive screenshots:
  - `D:\Datas\Programming\Cursor\AI4Paper02\ArxivPaper4\View\test-results\workspace-shell-list-1180x800.png`
  - `D:\Datas\Programming\Cursor\AI4Paper02\ArxivPaper4\View\test-results\workspace-shell-list-1024x768.png`
- Full-view comparison evidence: `D:\Datas\Programming\Cursor\AI4Paper02\ArxivPaper4\View\test-results\workspace-shell-comparison-full.png`
- Focused toolbar comparison evidence: `D:\Datas\Programming\Cursor\AI4Paper02\ArxivPaper4\View\test-results\workspace-shell-comparison-top.png`
- Reference viewport: 1488 × 1045.
- Responsive viewports: 1180 × 800 and 1024 × 768.
- State: light theme for reference comparison; dark theme for compact-width checks; local FastAPI data; guest session; list mode with one available paper.

## Findings

No actionable P0, P1, or P2 issues were found within the phase-2 scope.

- Typography: the implementation keeps the existing Inter/PingFang/Microsoft YaHei stack and uses 11–13 px controls with a clear title/count hierarchy. Labels do not clip at the tested widths.
- Spacing and layout rhythm: mode selection is isolated in the global navigation, while count/filter/sort controls occupy a dedicated 46–50 px workspace toolbar. At 1488, 1180, and 1024 px, `body.scrollWidth`, navbar `scrollWidth`, and their client widths match; no persistent control is hidden by overflow.
- Colors and tokens: active mode, focus rings, borders, and surfaces use the existing AI4Papers theme tokens in light and dark themes. The active pink state follows the selected reference direction without introducing a parallel palette.
- Image and asset fidelity: phase 2 introduces no new raster imagery, illustrations, or substitute icons. The existing product logo and established icon system are preserved.
- Copy and content: `卡片`, `列表`, `今日论文`, category, sorting, clearing, and missed-paper labels are concise and match their actions.
- Accessibility: the switch is a labelled `radiogroup`; arrow, Home, and End keys are implemented; filters have accessible labels; focus-visible states are present.

## Full-view comparison

The combined full view proves that the new shell establishes the intended top-level hierarchy: global mode choice above a page-owned filter row. The reference's dense research navigation, multi-row paper table, and right inspector are intentionally absent because they are phase 3, not phase 2. They remain required for the overall redesign goal.

## Focused comparison

The focused top-region comparison was required because typography and control density are too small to judge reliably in the full 2976 px-wide comparison. It confirms:

- mode selection remains visible and separated from filters;
- the secondary toolbar aligns context on the left and filters on the right;
- the current product's global research navigation is preserved rather than replaced wholesale;
- the compact desktop layout does not reproduce the previous toolbar collision.

## Primary interactions tested

- Closed the first-visit welcome panel.
- Switched card → list → card and verified `aria-checked` plus `view` URL state.
- Selected a category and sort mode and verified their values.
- Verified `digest_paper` remains in the URL without colliding with the existing `paper` query used by uploaded-paper views.
- Checked current-source console errors for `127.0.0.1:4174`: none.

## Comparison history

Iteration 1 normalized the implementation from dark to light theme so the visual evidence matched the source state. No code-level P0/P1/P2 issue remained after state normalization. Responsive evidence at 1180 and 1024 px confirmed the toolbar separation resolved the compact-desktop collision.

## Follow-up implementation

- Phase 3: replace the current narrow list with the dense central list and persistent paper inspector.
- Phase 4: add the immersive reader and expose the third mode.
- Later phases: migrate research projects, knowledge base, compare, and deep research into the shared shell.

phase 2 result: passed

# Phase 3 — Dense list and paper inspector

- Source visual truth: `C:\Users\Liu Lin\.codex\generated_images\019f4f0d-dd4d-70a0-96aa-b8985fd41394\exec-7296fdea-5561-486f-9ff7-b41c460af9de.png`
- Implementation route: `http://127.0.0.1:4174/?view=list&digest_paper=2605.20022`
- Primary implementation screenshot: `D:\Datas\Programming\Cursor\AI4Paper02\ArxivPaper4\View\test-results\workspace-list-inspector-1488x1045-final.png`
- Responsive drawer screenshot: `D:\Datas\Programming\Cursor\AI4Paper02\ArxivPaper4\View\test-results\workspace-list-inspector-1024x768.png`
- Full-view comparison: `D:\Datas\Programming\Cursor\AI4Paper02\ArxivPaper4\View\test-results\phase3-list-full-comparison.png`
- Focused list/inspector comparison: `D:\Datas\Programming\Cursor\AI4Paper02\ArxivPaper4\View\test-results\phase3-list-focused-comparison.png`
- Reference viewport: 1488 × 1045; responsive viewport: 1024 × 768.
- State: light theme, local FastAPI data, guest session, one locally available paper selected. The reference contains many papers and an authenticated project sidebar, so row count and account-only content were treated as data-state differences rather than layout defects.

## Phase 3 findings

No actionable P0, P1, or P2 issues were found after the final iteration.

- Structure: the implementation now matches the source's three-part research workspace at desktop width: existing product navigation, a dense central paper list, and a persistent right inspector.
- List fidelity: checkbox, paper metadata, relevance score, author, date, and actions remain visible at 1488 px. The selected row uses a restrained pink surface and leading marker. `documentElement.scrollWidth` does not exceed its client width.
- Inspector fidelity: selected-paper metadata, high-priority actions, summary, research question, contribution, key thoughts, analysis, memory, and evidence occupy a dedicated scrollable surface. List data remains available when a detail response omits authors or categories.
- Responsive behavior: below 1280 px, the persistent inspector becomes a 460 px overlay drawer with backdrop and an explicit close control. It is hidden initially, opens from a row click, closes successfully, and creates no horizontal overflow at 1024 × 768.
- Interaction model: single-click selects and previews; double-click or Enter opens precision reading; checkboxes support multi-selection; `S` collects selected papers; `B` toggles bookmark; `J/K` and arrow keys move the active paper; `P` opens PDF; Escape closes the inspector before leaving list mode.
- Accessibility: the list exposes an option model, each checkbox has a paper-specific accessible name, actions have descriptive names, active state is announced, and the responsive close button is keyboard-addressable.
- Product continuity: the existing date context, category/sort controls, guest registration state, knowledge-base collection, PDF, precision reading, deep research, and project dialog integrations are retained instead of becoming static mock controls.

## Phase 3 interactions tested

- Selected the only local paper and verified `批量收藏`, disabled one-paper `加入对比`, and `清除选择` appear.
- Cleared selection, reduced the viewport to 1024 × 768, opened the paper row, verified the inspector drawer is 460 px wide, then closed it.
- Confirmed all six desktop list columns are rendered at 1488 px and the inspector shows merged author metadata.
- Checked current-source console errors for `127.0.0.1:4174`: none.
- TypeScript check passed; targeted workspace tests passed: 2 files, 9 tests; full View suite passed: 9 files, 30 tests; production build passed (1193 modules).

## Remaining redesign work

- Phase 4: implement the immersive reader and expose the third `沉浸` mode.
- Later phases: migrate project space, knowledge base, comparison, and deep research pages into the shared shell while preserving their task-specific tools.

phase 3 result: passed
# Phase 4 — Immersive reader

- Source visual truth: `C:\Users\Liu Lin\.codex\generated_images\019f4f0d-dd4d-70a0-96aa-b8985fd41394\exec-61458479-d277-4f94-9d0e-d14efd472e53.png`
- Implementation route: `http://127.0.0.1:4174/?view=immersive&digest_paper=2605.20022`
- Primary browser-rendered screenshot: `D:\Datas\Programming\Cursor\AI4Paper02\ArxivPaper4\View\test-results\workspace-immersive-1487x1058-final.png`
- Responsive screenshots:
  - `D:\Datas\Programming\Cursor\AI4Paper02\ArxivPaper4\View\test-results\workspace-immersive-1024x768.png`
  - `D:\Datas\Programming\Cursor\AI4Paper02\ArxivPaper4\View\test-results\workspace-immersive-720x800.png`
- Full-view comparison: `D:\Datas\Programming\Cursor\AI4Paper02\ArxivPaper4\View\test-results\phase4-immersive-full-comparison.png`
- Focused document comparison: `D:\Datas\Programming\Cursor\AI4Paper02\ArxivPaper4\View\test-results\phase4-immersive-focused-comparison.png`
- Reference viewport: 1487 × 1058. Responsive viewports: 1024 × 768 and 720 × 800.
- State: light theme, local FastAPI data, guest session, one locally available paper. The source uses an authenticated project and three related papers; the implementation deliberately renders real project/auth and related-paper states, so the empty guest context is a data-state difference rather than a static placeholder.

## Phase 4 findings

No actionable P0, P1, or P2 issues remain after two design-QA iterations.

- Fonts and typography: the implementation keeps the product's Inter/PingFang/Microsoft YaHei stack. The 24–34 px title, 10–13 px metadata/body hierarchy, readable line height, and restrained letter spacing preserve the source's document-first hierarchy without clipping long Chinese or English titles.
- Spacing and layout rhythm: desktop uses a 68 px icon rail, a 1000 px maximum document inner frame, a 336 px context panel, and an approximately 1287 × 85 px floating action dock. Section dividers, recommendation surface, evidence grid, and bottom action rhythm align with the source. At 1024 px the context panel is removed and the document expands; at 720 px the rail becomes horizontal and the dock becomes four equal actions.
- Colors and tokens: pink active/recommendation/research states, green relevance, blue evidence, card surfaces, borders, and muted copy all map to existing AI4Papers theme tokens. No parallel palette or hard-coded gradient was introduced.
- Image quality and asset fidelity: the screen contains no photographic or illustrative raster content. All visible rail, paging, inline, and action-dock icons use downloaded official Tailwind Labs Heroicons SVG assets; no inline SVG, custom SVG, emoji, CSS drawing, or placeholder icon substitutes are used. Dark-theme filters preserve icon contrast.
- Copy and content: `推荐理由`, `摘要`, `关键思路`, `核心证据`, `分析总结`, `研究课题`, `相关论文`, and the four decision actions map directly to research tasks. Missing personalized recommendation text falls back to the paper's real main-contribution field instead of fabricated copy.
- Accessibility: the reader is a labelled region; rail and icon-only paging controls have explicit accessible names and titles; disabled previous/next controls are semantic buttons; every action is keyboard reachable; URL state exposes the active mode and paper.
- Responsiveness: `documentElement.scrollWidth` never exceeds its client width at 1487, 1024, or 720 px. The 1024 context panel is hidden without leaving an empty track. The 720 rail, document, and fixed dock use the full viewport and preserve usable targets.
- Product behavior: card/list/immersive mode changes persist in `view`; selection persists in `digest_paper`; the full knowledge sidebar is collapsed on immersive entry and restored on exit; PDF, precision reading, bookmark, knowledge collection, comparison, related-paper selection, project dialog, skip, and deep research call the existing real actions.

## Phase 4 comparison history

- Iteration 1 finding (P2): the initial implementation used a 900 px inner reader and 284 px context panel, leaving the document visibly narrower than the target; the text-only rail also drifted from the source icon language. Fix: expanded the inner frame to 1000 px and context panel to 336 px, added the recommendation fallback, and replaced rail/action imagery with official Heroicons. Post-fix evidence: `workspace-immersive-1487x1058-final.png` and the focused comparison.
- Iteration 2 finding (P2): the first post-icon action dock remained centered in a roughly 720 px lane while the source dock spans most of the workspace. Fix: expanded the dock to 100 px insets, 12 px gaps, and 64 px action targets, producing an approximately 1287 × 85 px dock. The final full comparison shows the corrected proportion.
- Final comparison: source and implementation are both 1487 × 1058. Remaining visible differences are expected data/product-state differences: different paper content, the existing production Navbar, a guest project state, and zero related papers in the one-paper local digest.

## Phase 4 primary interactions tested

- Clicked `沉浸` from card mode and verified `view=immersive` plus the rendered reader.
- Clicked `列表` from immersive mode and verified `view=list` plus the dense list.
- Pressed `I` in list mode and verified the reader and URL state.
- Pressed Escape in immersive mode and verified a return to list mode.
- Verified the full asset-sidebar expand button stays hidden while the immersive rail is active.
- Verified previous/next disabled semantics in the one-paper state.
- Verified a clean newly opened browser tab reports zero console errors for `127.0.0.1:4174`.
- Targeted component/state suite passed: 4 files, 17 tests; full View suite passed: 10 files, 34 tests; TypeScript check passed; production build passed (1208 modules).

## Remaining redesign work

- Phase 5: migrate project space, knowledge base, comparison, and deep research pages into the shared workspace shell while preserving each page's task-specific tools.
- Final phase: run cross-page regression, production build, source synchronization, and deployment verification.

final result: passed