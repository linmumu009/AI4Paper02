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

phase 4 result: passed

# Phase 5 — Research project workspace

- Source visual truth: `C:\Users\Liu Lin\.codex\generated_images\019f4f0d-dd4d-70a0-96aa-b8985fd41394\exec-d5c28b7a-fc7b-4193-8e7e-8592b3698652.png`
- Isolated implementation route: `http://127.0.0.1:4174/test-results/project-workspace-preview.html`
- Responsive browser-rendered screenshots:
  - `D:\Datas\Programming\Cursor\AI4Paper02\ArxivPaper4\View\test-results\project-workspace-1024.png`
  - `D:\Datas\Programming\Cursor\AI4Paper02\ArxivPaper4\View\test-results\project-workspace-720.png`
  - `D:\Datas\Programming\Cursor\AI4Paper02\ArxivPaper4\View\test-results\project-workspace-390.png`
- Reference viewport: 1487 × 1058. Responsive viewports: 1024 × 768, 720 × 900, and 390 × 844.
- State: isolated authenticated-project fixture for visual review; production implementation loads the current user's actual project, assets, research sessions, latest digest, and paper details through existing APIs.

## Phase 5 findings

No actionable P0, P1, or P2 issues remain after the mobile-drawer correction.

- Information architecture: the selected design is implemented as a task-specific project workspace with project navigation, progress, workbench tabs, core question, evidence matrix, synthesis, candidate-paper inbox, and a persistent research composer.
- Real data: progress is derived from the project's papers, comparisons, notes, and research sessions. Evidence rows use real structured method, results, evidence-chain, and limitation fields. Candidate papers are ranked from the latest digest against project terms and exclude papers already in the project.
- Workflow continuity: edit/archive, add/remove/open asset, open research session, create/switch project, add a candidate paper, project-scoped comparison, and project-owned deep research all call existing application actions and APIs.
- Deep-research handoff: a question entered in the project composer is passed through the route and prefilled in the existing ResearchPanel. It is never auto-submitted, so navigation does not consume quota unexpectedly.
- Responsive behavior: desktop keeps three columns; below 1200 px the candidate inbox becomes a drawer; below 768 px the project rail is removed, evidence rows stack, actions reflow, and the composer remains reachable. At 390 px, `scrollWidth` equals `clientWidth` (390 px).
- Accessibility: interactive controls use semantic buttons; icon-only controls have accessible names; the candidate drawer has a unique close button and a separately labelled backdrop; no emoji or custom-drawn icon substitutes are used.
- Asset fidelity: all visible project, asset, research, comparison, add, close, and archive icons use official Tailwind Labs Heroicons already stored in the project.

## Phase 5 comparison history

- Iteration 1 finding (P1): the responsive candidate-paper drawer opened correctly but covered its trigger and had no explicit close control. Fix: added an accessible close button and click-to-close backdrop, then verified the drawer returns off-screen after close.
- Final responsive review: the 1024 px layout keeps project navigation and the complete workbench while moving candidates into a drawer. The 720 px and 390 px layouts preserve the research question, evidence, synthesis, and composer without horizontal overflow.

## Phase 5 interactions tested

- Verified real project question, structured evidence, candidate recommendations, and research synthesis render from component props.
- Verified candidate-paper add, tab selection, and prompted deep-research events with Vitest.
- Opened and closed the mobile candidate drawer using its semantic controls.
- Verified `innerWidth = scrollWidth = 390` and zero browser console errors/warnings after the final mobile correction.
- Targeted project suite passed: 2 files, 3 tests. Final full View suite passed: 12 files, 37 tests; TypeScript check passed; production build passed (1218 modules).

## Remaining redesign work

- Phase 6: migrate the knowledge-base surface into the shared workspace language.
- Later phases: migrate comparison and deep-research surfaces, then run cross-page regression, source synchronization, and deployment verification.

phase 5 result: passed

# Phase 6 — Knowledge library workspace

- Source visual truth: `C:\Users\Liu Lin\.codex\generated_images\019f4f0d-dd4d-70a0-96aa-b8985fd41394\exec-f9e74772-821e-4c9d-8d2e-9d86e8bc4535.png`
- Isolated implementation route: `http://127.0.0.1:4174/test-results/knowledge-workspace-preview.html`
- Primary browser-rendered screenshot: `D:\Datas\Programming\Cursor\AI4Paper02\ArxivPaper4\View\test-results\knowledge-workspace-1487x1058-final.png`
- Responsive screenshot: `D:\Datas\Programming\Cursor\AI4Paper02\ArxivPaper4\View\test-results\knowledge-workspace-390x844-final.png`
- Full-view comparison: `D:\Datas\Programming\Cursor\AI4Paper02\ArxivPaper4\View\test-results\phase6-knowledge-full-comparison.png`
- Reference viewport: 1487 × 1058; responsive viewports: 1024 × 768 and 390 × 844.
- State: isolated light-theme fixture with eight realistic KB papers. Production keeps the authenticated Sidebar as the real folder-management surface and feeds the workspace with the actual `KbTree`.

## Phase 6 findings

No actionable P0, P1, or P2 issues remain after the final iteration.

- Structure: the production screen now uses the existing folder Sidebar plus a dense central paper list and persistent desktop inspector, matching the selected three-column research-library pattern without duplicating folder CRUD.
- Data behavior: all root and nested-folder papers are flattened with their real folder paths. Selecting a Sidebar folder narrows the list to that folder and its descendants. Search covers title, authors, institution, abstract, ID, and folder path.
- Research workflow: status filtering, relevance/title/date sorting, select-all, multi-paper comparison, multi-paper deep research, PDF, precision reading, add-to-project, remove-from-library, and read-state cycling connect to existing APIs or application handlers.
- Detail fidelity: the inspector reuses the structured paper-detail loader and shows recommendation, abstract, research problem, contribution, key thoughts, analysis, memory, and evidence. A failed enrichment request no longer leaks raw Axios errors when summary content is already available.
- Action hierarchy: authenticated users receive a full-width pink `加入课题` primary action. `从知识库移除` is a restrained danger-outline action instead of a misleading primary CTA.
- Responsive behavior: below 1280 px the inspector becomes an overlay drawer; below 768 px list metadata collapses to title, score, and read state. The folder control remains available and the 390 px viewport has no horizontal overflow.
- Accessibility: the workspace is a labelled region, the paper collection is a listbox, each row is an option, checkboxes have paper-specific labels, filters are labelled, and drawer/backdrop close controls have distinct accessible names.

## Phase 6 comparison history

- Iteration 1 finding (P1): the visual fixture inherited the application's dark default tokens, which prevented a valid comparison against the selected light design. Fix: set only the isolated QA fixture to the light theme; production continues to honor the user's theme.
- Iteration 2 finding (P1): the inspector exposed raw `Request failed with status code 404` copy when enrichment failed, and styled library removal as the primary pink action. Fix: hide low-level enrichment errors when complete summary content exists and introduce a dedicated danger-outline treatment.
- Iteration 3 finding (P2): `加入课题` remained visually secondary even though the reference treats project organization as the primary next step. Fix: promote it to the first full-width primary action for the knowledge workspace.

## Phase 6 interactions tested

- Verified all-paper and active-folder data states with Vitest.
- Selected two papers and verified compare and deep-research payloads; verified read-status cycling payloads.
- At 390 px, opened a paper inspector, closed it with the unique semantic close control, and confirmed `scrollWidth = innerWidth = 390`.
- Searched for `ReMamba`, then filtered all papers to `待读`; verified the resulting visible papers and labels.
- Verified zero browser console errors/warnings after the final interaction pass.
- Final View suite passed: 13 files, 39 tests; TypeScript check passed; production build passed (1221 modules).

## Remaining redesign work

- Phase 7: migrate the comparison workspace into the same research-shell language.
- Phase 8: migrate the deep-research workspace, then run cross-page regression, source synchronization, and deployment verification.

phase 6 result: passed

# Phase 7 — Comparison workspace

- Source visual truth: `C:\Users\Liu Lin\.codex\generated_images\019f4f0d-dd4d-70a0-96aa-b8985fd41394\exec-f9e74772-821e-4c9d-8d2e-9d86e8bc4535.png`
- Isolated implementation route: `http://127.0.0.1:4174/test-results/compare-workspace-preview.html`
- Browser-rendered desktop screenshot: `D:\Datas\Programming\Cursor\AI4Paper02\ArxivPaper4\View\test-results\compare-workspace-desktop.png`
- Browser-rendered mobile screenshot: `D:\Datas\Programming\Cursor\AI4Paper02\ArxivPaper4\View\test-results\compare-workspace-mobile.png`
- Full-view comparison evidence: `D:\Datas\Programming\Cursor\AI4Paper02\ArxivPaper4\View\test-results\compare-workspace-qa-board.png`
- Viewports: 1440 × 900 and 390 × 844.
- State: light-theme comparison preparation state with three realistic source papers and one saved comparison as reference context. The source is the approved shared research-workspace language rather than a comparison-specific mock, so content/state differences are intentional.

## Phase 7 findings

No actionable P0, P1, or P2 differences remain.

- Information architecture: the previous centered single-panel prompt is now a task-specific three-column workspace: paper sources and historical context on the left, the generated report in the center, and status plus the six-step analysis structure on the right.
- Fonts and typography: the implementation retains the approved Inter/PingFang/Microsoft YaHei stack, compact 8–11 px workspace metadata, a 20 px page title, and a 20–22 px report hierarchy. Long Chinese and English source titles clamp without colliding with IDs or column edges.
- Spacing and layout rhythm: 230/auto/250 px desktop tracks, 1 px dividers, 7–12 px card gaps, restrained 8–10 px radii, and a quiet centered preparation state reproduce the selected dense research-tool rhythm. At 1199 px the outline is removed; at 767 px sources become a two-column strip above the report.
- Colors and visual tokens: pink is reserved for active/progress/primary action, blue identifies source scope, green indicates completion, and all surfaces/borders use the existing AI4Papers tokens. No parallel color system or gradient was introduced.
- Image quality and asset fidelity: the workspace has no photographic content. All visible comparison, archive, document, status, and close imagery uses the project's official Tailwind Labs Heroicons assets; no emoji, inline SVG, custom SVG, placeholder, or CSS-drawn icon replaces a visible asset.
- Copy and content: source range, report status, analysis dimensions, quota, historical-report context, and structured-output guidance describe the real comparison workflow. HTTP failures are converted to concise user-facing explanations instead of exposing raw response bodies.
- Formula support: active and saved comparison reports both use the tested shared Markdown + KaTeX renderer with dollar, bracket, and LaTeX-environment delimiters. Display formulas scroll within the report instead of widening the viewport.
- Responsive behavior: at 390 × 844, `scrollWidth = innerWidth = 390`; the close action, all three sources, historical context, primary CTA, and report explanation remain visible without a disordered toolbar or horizontal overflow.
- Accessibility: the workspace, source rail, and outline are labelled regions; close and generation controls are semantic buttons; phase copy is visible text; source titles remain available in the DOM even when visually clamped.
- Focused-region comparison: no separate crop was required because the source defines shared shell density and hierarchy, not comparison-specific typography or component geometry. The original 1440 × 900 implementation screenshot was inspected at full resolution for source cards, CTA, status, and outline details, while the side-by-side board establishes the overall visual-language comparison.

## Phase 7 comparison history

- Initial implementation review: no P0/P1/P2 visual mismatch was found. The three-track shell, thin dividers, quiet surfaces, restrained pink accent, and compact research-tool typography align with the source language. The intentionally larger empty center is the pre-generation state and will be occupied by the streamed report.
- Responsive review: the first 390 px capture showed the expected stacked source/report structure with no horizontal overflow, clipped toolbar, or unreachable primary action; no responsive correction was required.

## Phase 7 primary interactions tested

- Verified the preparation state contains all real source paper titles, source scope, historical comparison count, six analysis dimensions, quota summary, and generation CTA.
- Clicked the unique `开始生成对比报告` action in the browser fixture. The unauthenticated API response transitioned to the designed error state and displayed `请先登录` instead of raw transport text.
- Verified close-event wiring with a component test.
- Verified zero browser console errors at both desktop and mobile viewports.
- Targeted comparison and formula suite passed: 2 files, 5 tests. Final View suite passed: 14 files, 41 tests; TypeScript check passed; production build passed (1221 modules).

## Remaining redesign work

- Phase 8: migrate the deep-research workspace into the same research-shell language.
- Final phase: run cross-page regression, finalize the changed-file manifest, then synchronize/deploy only when production upload is explicitly requested.

phase 7 result: passed

# Phase 8 — Deep research workspace

- Source visual truth: `C:\Users\Liu Lin\.codex\generated_images\019f4f0d-dd4d-70a0-96aa-b8985fd41394\exec-f9e74772-821e-4c9d-8d2e-9d86e8bc4535.png`
- Isolated implementation route: `http://127.0.0.1:4174/test-results/research-workspace-preview.html`
- Browser-rendered desktop screenshot: `D:\Datas\Programming\Cursor\AI4Paper02\ArxivPaper4\View\test-results\research-workspace-desktop-final.png`
- Browser-rendered mobile screenshot: `D:\Datas\Programming\Cursor\AI4Paper02\ArxivPaper4\View\test-results\research-workspace-mobile-final.png`
- Full-view comparison evidence: `D:\Datas\Programming\Cursor\AI4Paper02\ArxivPaper4\View\test-results\research-workspace-qa-board.png`
- Viewports: 1440 × 900, 1024 × 768, and 390 × 844.
- State: light-theme project-owned research preparation state with four realistic source papers and a prefilled research question. The source is the approved shared research-workspace language rather than a deep-research-specific mock, so content/state differences are intentional.

## Phase 8 findings

No actionable P0, P1, or P2 issues remain after the final iteration.

- Information architecture: deep research now uses a three-track workspace: the current research corpus on the left, the existing real R1–R3 stream/input/history experience in the center, and a concise execution plan plus output contract on the right. No research API, session, follow-up, download, or save behavior was replaced.
- Fonts and typography: the implementation keeps the approved Inter/PingFang/Microsoft YaHei stack, 8–10 px rail metadata, 13–15 px rail headings, a 28 px central task title, and a 13–14 px question/input hierarchy. Long source titles clamp without obscuring identifiers.
- Spacing and layout rhythm: desktop uses 230/auto/250 px tracks with thin dividers, 6–14 px gaps, restrained 8–16 px radii, and a deliberately quiet preparation canvas. At 1199 px the plan rail is removed; at 767 px the corpus becomes a compact two-column strip above the main research flow.
- Colors and tokens: the workspace uses existing background, border, text, accent, status, and disabled tokens. Pink is reserved for research progress and the primary action; light blue is limited to process guidance. No parallel palette or gradient was introduced.
- Image quality and asset fidelity: the screen contains no raster imagery. All visible corpus, plan, settings, history, close, remove, suggestion, loading, and error icons on the primary path now use the project's official Tailwind Labs Heroicons assets. The old inline SVG and text-glyph substitutes were removed from the migrated path.
- Copy and content: the corpus scope, project ownership, R1–R3 descriptions, final deliverable, progressive-reading rule, suggested questions, and Top N control describe actual behavior. The initial question from a project is preserved without auto-submission or unexpected quota use.
- Responsiveness: `scrollWidth` equals `innerWidth` at 1440, 1024, and 390 px. At 390 × 844 the four sources, history, question, paper chips, Top N, primary action, and suggestions remain reachable without a broken toolbar or horizontal page overflow.
- Accessibility: the workspace, corpus, and plan are labelled regions. History drawer backdrop and close controls have distinct accessible names. Source-removal buttons have paper-specific labels, and all primary controls remain semantic and keyboard reachable.
- Focused-region comparison: a separate crop was not required because the source defines the shared shell and density rather than deep-research-specific controls. The full-resolution desktop and mobile captures were inspected for corpus cards, input toolbar, history control, plan rail, and suggested-question spacing; the side-by-side board establishes overall visual-language fidelity.

## Phase 8 comparison history

- Iteration 1 finding (P2, behavior/content): with four available papers, the visible settings button said `Top 5` while the range input was silently constrained to 4. Fix: make the paper-count watcher immediate, so the displayed Top N and slider value both initialize to 4. Post-fix browser evidence shows `Top 4`; a dedicated component regression test covers first render.
- Iteration 1 finding (P2, accessibility/icons): the history drawer close button had no accessible name, and the migrated preparation path still displayed older inline SVG controls. Fix: add separately named backdrop and close buttons, replace the visible history/settings/remove/suggestion/status icons with existing official Heroicons, and remove the `▶` text glyph. Post-fix DOM evidence exposes `关闭研究历史遮罩` and `关闭研究历史` as unique controls.
- Final responsive comparison: desktop retains all three tracks, 1024 px hides only the plan rail, and 390 px stacks the corpus above the complete research input. No actionable P0/P1/P2 differences remain.

## Phase 8 primary interactions tested

- Clicked a suggested research question and verified the textarea value changed to the selected question.
- Opened the Top N settings popover and verified the visible label and slider both use the available-paper maximum.
- Opened and closed the research-history drawer with its unique semantic controls; the unauthenticated fixture displayed its valid empty-history state.
- Verified existing workspace events continue to forward close, remove-paper, and save-to-library actions.
- Verified zero browser console errors at desktop and mobile viewports.
- Targeted deep-research suite passed: 4 files, 12 tests. Final View suite passed: 16 files, 44 tests; TypeScript check passed; production build passed (1226 modules).

## Remaining work

- Run the final cross-page manifest/status audit and create the deep-research commit.
- Synchronize and verify production only after explicit production-upload authorization.

phase 8 result: passed

# Phase 9 — Final cross-page regression

- Actual application route: `http://127.0.0.1:4174/?view=list`
- Browser-rendered desktop screenshot: `D:\Datas\Programming\Cursor\AI4Paper02\ArxivPaper4\View\test-results\final-app-desktop.png`
- Browser-rendered mobile screenshot: `D:\Datas\Programming\Cursor\AI4Paper02\ArxivPaper4\View\test-results\final-app-mobile-navbar-fixed.png`
- Viewports: 1440 × 900 and 390 × 844.

## Phase 9 findings

- Iteration 1 finding (P2, responsive navigation): at 390 px the registration action was clipped at the right edge even though the document itself did not report horizontal overflow. Fix: compact the navbar spacing and primary-item padding below 480 px, hide the secondary workbench and theme actions at that width, reduce registration padding, and reserve the search action until the narrower 359 px breakpoint.
- Post-fix evidence: at 390 × 844, `scrollWidth = innerWidth = 390`; the registration control occupies approximately 287.6–327.6 px and is fully visible. The logo, three primary navigation items, card/list/immersive mode switch, search, and registration actions remain available without overlap.
- Desktop regression: the 1440 × 900 application retains the complete navigation, research-space shell, paper workspace, and mode controls with no layout regression or horizontal overflow.
- Scope regression: list, immersive reader, research project, knowledge library, comparison, and deep-research surfaces now share the approved workspace language while preserving their existing behaviors and APIs.
- Final automated validation: 16 test files and 44 tests passed; TypeScript validation passed; the production build passed with 1226 transformed modules.

No actionable P0, P1, or P2 issue remains in the redesigned View scope.

## Remaining production action

- Source changes are ready for commit and are recorded in the changed-file manifest.
- Production synchronization and service reload remain intentionally pending until explicit production-upload authorization is given.

final result: passed
