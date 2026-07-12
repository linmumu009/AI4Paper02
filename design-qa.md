# AI4Papers Research Workspace Design QA

Scope: phase 2 only — shared research workspace shell, responsive secondary toolbar, and card/list mode switch. The dense three-column list, paper inspector, and immersive reader remain later phases and are not claimed as complete here.

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

final result: passed
