# AIChat Full UI Redesign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the rigid ten-page UI with one accessible, animated, responsive cross-platform design system while preserving all current AIChat business contracts.

**Architecture:** Keep the existing uni-app pages, Pinia stores, API modules, and route responsibilities. Add a small presentational component layer and pure presentation-model helpers; use an H5 desktop shell conditionally while retaining the mobile tab/navigation flow. Generate Lucide icons from local Iconify data into committed static PNG assets so H5, App, and WeChat builds never depend on a runtime icon service.

**Tech Stack:** uni-app 3, Vue 3.4, TypeScript 5.4, Pinia, SCSS, Node test runner, Iconify Lucide data, Sharp (build-time icon generation), Playwright CLI for browser acceptance.

**Spec:** `docs/superpowers/specs/2026-10-27-full-ui-redesign-design.md`

## Global Constraints

- Preserve all existing API, Store, WSS, permission, idempotency, pairing, and Run-state behavior unless this plan explicitly extracts the same logic into a tested helper.
- The ten pages remain shared uni-app pages; shadcn-vue is a visual/interaction reference, not a runtime dependency.
- No icon CDN or runtime Iconify API. Generated assets and their license/source manifest ship in the repository.
- H5 desktop breakpoints are `<768`, `768–899`, `900–1099`, and `>=1100` CSS px.
- Touch targets are at least 44 CSS px; login inputs and primary actions are 48px high.
- Motion uses transform/opacity where practical and becomes functionally optional under `prefers-reduced-motion: reduce`.
- Do not introduce fake account recovery, health, online, cost, token, invitation-inbox, or model-market capabilities.
- Keep `recovery_required` retry available in Run details and unavailable in chat; add verification guidance rather than changing the state machine.
- Do not commit, push, deploy, or modify the production site unless the user separately authorizes it.
- Delete replaced UI code only after its replacement passes tests/builds; deletions include unused legacy classes/keyframes, CSS-drawn icons, the replaced tab icon script, duplicate local styles, and the superseded `docs/ui-redesign/` prototype package after durable requirements are migrated.

## Review Focus

- Directly opening or refreshing `/pages/chat/chat?id=…` at every breakpoint must restore the correct conversation without duplicating chat logic.
- Resizing across 767/768, 899/900, and 1099/1100 must not leave the H5 tab bar, desktop rail, modal focus, or selected conversation in a stale state.
- IME composition plus Enter must never send; desktop Enter sends only outside composition, while Shift+Enter and mobile confirmation preserve a newline path.
- Unknown mock routes must fail explicitly instead of returning empty success, so browser acceptance cannot pass against fabricated data.
- Reduced-motion mode must remove decorative loops and staggered movement while preserving loading/status text and every operation.

---

### Task 1: Cross-platform UI foundation and reproducible icons

**Files:**
- Create: `apps/mobile/src/ui/layout.ts`
- Create: `apps/mobile/src/ui/icons.ts`
- Create: `apps/mobile/src/components/ui/UiIcon.vue`
- Create: `apps/mobile/src/components/ui/UiButton.vue`
- Create: `apps/mobile/src/components/ui/PageHeader.vue`
- Create: `apps/mobile/src/components/ui/AccountAvatar.vue`
- Create: `apps/mobile/src/components/ui/StatusBadge.vue`
- Create: `apps/mobile/src/components/ui/EmptyState.vue`
- Create: `apps/mobile/src/components/ui/InlineNotice.vue`
- Create: `apps/mobile/src/components/ui/BottomSheet.vue`
- Create: `apps/mobile/src/components/layout/DesktopRail.vue`
- Create: `apps/mobile/src/components/layout/AppShell.vue`
- Create: `apps/mobile/scripts/gen-ui-icons.mjs`
- Create: `apps/mobile/src/static/icons/LICENSES.md`
- Modify: `apps/mobile/src/styles/base.scss`
- Modify: `apps/mobile/package.json`
- Modify: `apps/mobile/package-lock.json`
- Test: `apps/mobile/tests/ui-foundations.test.cjs`

**Interfaces:**
- Produces: `layoutMode(width: number): 'mobile' | 'compact' | 'desktop'` and `isDesktopWidth(width: number): boolean`.
- Produces: `UiIcon` with `name`, `tone`, and `size`; `UiButton` with `variant`, `loading`, `disabled`, and native button semantics.
- Produces: shared layout/status/feedback components with no API or Store dependency.

- [ ] **Step 1: Write failing layout and icon-generation tests**

Test `layoutMode()` at 767/768, 899/900, and 1099/1100. Spawn `npm run icons:generate`, assert required navigation/action/status PNGs exist, have a PNG signature, and a second run is byte-identical. Assert an unknown icon name is rejected by the catalog.

- [ ] **Step 2: Run the focused test and verify RED**

Run: `node --test --test-name-pattern="layout|icon" tests/*.test.cjs` from `apps/mobile`  
Expected: FAIL because `src/ui/layout.ts`, the icon catalog, and `icons:generate` do not exist.

- [ ] **Step 3: Implement the foundation**

Add exact dev dependencies `@iconify-json/lucide`, `@iconify/utils`, and `sharp`. Generate 24px Lucide-style PNG assets in local tone folders plus the existing 81px tab variants; write the Iconify/Lucide license provenance to `LICENSES.md`. Rebuild `base.scss` around the approved tokens, focus ring, typography, spacing, motion durations, and reduced-motion overrides. Components accept presentation props/slots only and emit events upward.

- [ ] **Step 4: Run focused tests, type-check, and icon determinism verification**

Run: `node --test --test-name-pattern="layout|icon" tests/*.test.cjs`  
Run: `npm run type-check`  
Expected: PASS with identical icon output on consecutive generation runs.

- [ ] **Step 5: Review checkpoint**

Inspect `git diff -- apps/mobile/src/ui apps/mobile/src/components apps/mobile/src/styles/base.scss apps/mobile/scripts apps/mobile/package*.json` and confirm no business API/Store behavior changed.

### Task 2: Accessible animated login, registration, and server settings

**Files:**
- Create: `apps/mobile/src/pages/login/model.ts`
- Modify: `apps/mobile/src/pages/login/login.vue`
- Modify: `apps/mobile/src/api/client.ts`
- Modify: `apps/mobile/src/pages.json`
- Modify: `apps/mobile/vite.config.ts`
- Modify: `apps/mobile/package.json`
- Modify: `apps/mobile/package-lock.json`
- Test: `apps/mobile/tests/login-ui.test.cjs`

**Interfaces:**
- Produces: `validateAuthForm(input): AuthFieldErrors`, `loginCopy(mode): { title; accountPlaceholder; passwordAutocomplete }`, and `normalizeServerOrigin(value): string`.
- Consumes: Task 1 UI primitives and icon assets.

- [ ] **Step 1: Capture the current A01–A10 runtime failures**

Build/preview the unchanged H5 and use Playwright CLI to record the Tab sequence, password Enter behavior, input accessible names/autocomplete, disappearing errors, `https://` server error, document height, registration title, and the exact Vue Router console warning. Store only concise observations in the task notes; do not add raw session logs to Git.

- [ ] **Step 2: Write failing model tests**

Test independent field errors for login/registration, login vs registration copy/title/autocomplete, valid `http`/`https` origin normalization, and distinct failures for empty value, missing scheme, missing host, credentials, query/hash, and path.

- [ ] **Step 3: Run the focused test and verify RED**

Run: `node --test --test-name-pattern="auth form|server origin|login copy" tests/*.test.cjs`  
Expected: FAIL because the model and strict origin normalizer do not exist.

- [ ] **Step 4: Implement the public-entry redesign**

Use one real form submission path for click and Enter; render native semantic buttons/labels in final H5 DOM; bind `name`, `autocomplete`, `aria-invalid`, and described error IDs. Keep field errors visible until correction, focus the first invalid field, add password visibility, and provide the administrator-reset explanation without inventing a recovery service. Replace the solid green block with the approved mint/ink/purple animated collaboration scene and reduced-motion fallback. Set the login page to custom navigation, provide an in-page H1, and update document/navigation titles on mode change.

- [ ] **Step 5: Remove the Vue Router deprecation at its dependency source**

Pin the `@dcloudio/uni-h5` nested `vue-router` override to exact `4.3.0`, whose bundler entry does not emit the 4.6 deprecation warning; regenerate the lockfile. Do not patch `node_modules` or built assets.

- [ ] **Step 6: Run tests, type-check, build, and browser acceptance**

Run: `node --test --test-name-pattern="auth form|server origin|login copy" tests/*.test.cjs`  
Run: `npm run type-check`  
Run: `npm run build:h5`  
Use Playwright CLI at 1440×900, 390×844, and 320×568 to verify A01–A10, normal/reduced motion, no horizontal overflow, no fixed 44px excess height, and no console warning. Expected: all ten findings have observable passing evidence.

- [ ] **Step 7: Review checkpoint**

Re-read the A01–A10 matrix in the spec and link each item to a test or browser observation before moving on.

### Task 3: Responsive application shell, sessions, and chat workspace

**Files:**
- Create: `apps/mobile/src/ui/chat.ts`
- Create: `apps/mobile/src/components/chat/ConversationList.vue`
- Create: `apps/mobile/src/components/chat/ChatWorkspace.vue`
- Modify: `apps/mobile/src/pages/sessions/sessions.vue`
- Modify: `apps/mobile/src/pages/chat/chat.vue`
- Modify: `apps/mobile/src/pages.json`
- Test: `apps/mobile/tests/chat-ui.test.cjs`

**Interfaces:**
- Produces: `shouldSubmitMessageKey({ key, shiftKey, isComposing, desktop }): boolean` and `shouldFollowNewMessage(distanceFromBottom: number): boolean`.
- Produces: `ConversationList` and `ChatWorkspace`, reused by the sessions and direct chat routes.
- Consumes: Task 1 `AppShell`, `PageHeader`, avatars, statuses, buttons, icons, notices, and sheets.

- [ ] **Step 1: Write failing interaction-model tests**

Cover Enter, Shift+Enter, composition Enter, mobile confirmation, at-bottom threshold, scrolled-history behavior, and direct-route conversation selection.

- [ ] **Step 2: Run the focused test and verify RED**

Run: `node --test --test-name-pattern="message key|follow new message|conversation route" tests/*.test.cjs`  
Expected: FAIL because `src/ui/chat.ts` and the shared route selection behavior do not exist.

- [ ] **Step 3: Extract shared chat presentation without duplicating business logic**

Move the conversation list template/presentation into `ConversationList`; move the current chat view and interaction orchestration into `ChatWorkspace` while keeping Store/API calls unchanged. `chat.vue` becomes a route wrapper; `sessions.vue` shows the list plus purposeful desktop empty state. Direct URLs and refresh continue to initialize from `id`.

- [ ] **Step 4: Implement desktop and mobile layouts**

At `>=1100`, render rail + 320px list + workspace; at 900–1099 compress; at 768–899 show one content pane with compact rail; below 768 use mobile navigation and native tab flow. Desktop conversation switching updates the selected workspace and H5 URL state without creating a new page stack; mobile still navigates into chat.

- [ ] **Step 5: Implement chat interaction and motion improvements**

Add local conversation filtering, semantic new-conversation actions, message hierarchy, AI reply blocks, quote/mention chips, connection/generation status motion, new-message affordance when scrolled up, focus-safe AI picker, and visible reasons for disabled/closed states. Preserve client-message IDs, structured mentions, Run actions, and read reporting.

- [ ] **Step 6: Run focused/full tests, type-check, and build**

Run: `node --test --test-name-pattern="message key|follow new message|conversation route" tests/*.test.cjs`  
Run: `npm test`  
Run: `npm run type-check`  
Run: `npm run build:h5`  
Expected: all pass; direct route, refresh, resize, and mobile back behavior work in Playwright CLI with mock data.

- [ ] **Step 7: Review checkpoint**

Confirm there is exactly one chat business implementation and one conversation list implementation; reject copied API/Store logic.

### Task 4: Contacts, requests, group creation, and group settings

**Files:**
- Create: `apps/mobile/src/ui/contacts.ts`
- Modify: `apps/mobile/src/pages/contacts/contacts.vue`
- Modify: `apps/mobile/src/pages/group/settings.vue`
- Test: `apps/mobile/tests/contact-ui.test.cjs`

**Interfaces:**
- Produces: `nextGroupCreationState(state, event): GroupCreationState` and permission-derived `groupMemberActions(role, target): Action[]`.
- Consumes: Task 1 shell/form/list/button/sheet primitives.

- [ ] **Step 1: Write failing group-flow and permission tests**

Cover member selection → title → confirmation, cancellation reset, empty contacts, outgoing vs incoming requests, owner/admin/member permissions, AI role restrictions, and closed groups.

- [ ] **Step 2: Run the focused test and verify RED**

Run: `node --test --test-name-pattern="group creation|group member actions|contact request" tests/*.test.cjs`  
Expected: FAIL because the presentation state model does not exist.

- [ ] **Step 3: Redesign contacts and requests**

Separate exact account lookup from local contact filtering, use semantic segmented controls, make received/outgoing states visually distinct, prioritize message/add/accept actions, and move destructive operations behind a labeled menu. Replace the fixed bottom creation bar with the tested three-step group flow.

- [ ] **Step 4: Redesign group settings**

Add the group summary/header, consistent identity and role badges, permission-filtered controls, focus-safe invitation sheet, accurate history wording, and a separated danger section. Keep all rename/role/transfer/invite/remove/leave/dissolve API calls unchanged.

- [ ] **Step 5: Run focused/full tests, type-check, and build**

Run: `node --test --test-name-pattern="group creation|group member actions|contact request" tests/*.test.cjs`  
Run: `npm test`  
Run: `npm run type-check`  
Run: `npm run build:h5`

- [ ] **Step 6: Review checkpoint**

Verify “invitation sent” is never rendered as “joined,” AI roles remain restricted, and unavailable actions are absent rather than merely grey.

### Task 5: Profile, AI catalog, and AI management

**Files:**
- Create: `apps/mobile/src/ui/accounts.ts`
- Modify: `apps/mobile/src/pages/me/me.vue`
- Modify: `apps/mobile/src/pages/agents/agents.vue`
- Modify: `apps/mobile/src/pages/agents/detail.vue`
- Test: `apps/mobile/tests/account-ui.test.cjs`

**Interfaces:**
- Produces: `agentPresentation(agent): { connectionLabel; verificationLabel; tone }` and `sessionPresentation(session): { title; activityLabel; current }`.
- Consumes: Task 1 settings/header/avatar/status/form primitives.

- [ ] **Step 1: Write failing presentation tests**

Cover model binding vs connector binding, online-but-unverified, disabled agents, missing binding, current/other sessions, missing device summary, and server-setting validation reuse.

- [ ] **Step 2: Run the focused test and verify RED**

Run: `node --test --test-name-pattern="agent presentation|session presentation" tests/*.test.cjs`  
Expected: FAIL because `src/ui/accounts.ts` does not exist.

- [ ] **Step 3: Redesign My and My AI pages**

Build profile/header plus AI & devices/account/advanced sections; move edit profile, sessions, and server address into clear panels/sheets; separate logout danger. Render owned AI as a responsive grid with accurate binding/connection/verification language and a single primary create action.

- [ ] **Step 4: Redesign AI details**

Split profile, connection method, grants, and connectors into distinct sections; keep credentials write-only, show only non-secret binding summaries, move internal IDs to technical details, and separate save from destructive revoke operations.

- [ ] **Step 5: Run focused/full tests, type-check, and build**

Run: `node --test --test-name-pattern="agent presentation|session presentation" tests/*.test.cjs`  
Run: `npm test`  
Run: `npm run type-check`  
Run: `npm run build:h5`

- [ ] **Step 6: Review checkpoint**

Confirm that configured/bound/connected/verified remain distinct and no credential is rendered back into the DOM.

### Task 6: Pairing flow and Run detail states

**Files:**
- Create: `apps/mobile/src/ui/operations.ts`
- Modify: `apps/mobile/src/pages/pairing/scan.vue`
- Modify: `apps/mobile/src/pages/runs/detail.vue`
- Test: `apps/mobile/tests/operation-ui.test.cjs`

**Interfaces:**
- Produces: `pairingStep(status): PairingStep`, `pairingMotion(status): 'active' | 'still'`, and `runPresentation(state, surface): RunPresentation`.
- Consumes: Task 1 step/status/notice/button/icon components.

- [ ] **Step 1: Write failing pairing and Run-state tests**

Cover every current PairingStatus and RunState, terminal polling/motion stop, expired time, pending-user approval requirements, `recovery_required` action difference between chat/detail, and safe unknown-state fallback.

- [ ] **Step 2: Run the focused test and verify RED**

Run: `node --test --test-name-pattern="pairing step|run presentation" tests/*.test.cjs`  
Expected: FAIL because `src/ui/operations.ts` does not exist.

- [ ] **Step 3: Implement the pairing stepper UI**

Present scan/manual acquisition, device/code verification, AI selection, approval, and waiting as explicit steps; keep pairing ID and short code inputs intact, explain them in user language, stop active motion and polling at terminal states, and keep H5 manual entry discoverable.

- [ ] **Step 4: Implement the Run summary UI**

Lead with agent/request/state/next action, place IDs and generations in technical details, provide distinct icon/text/background states, keep active cancel and detail-only retry behavior, and require a clear result-check explanation for `recovery_required`.

- [ ] **Step 5: Run focused/full tests, type-check, and build**

Run: `node --test --test-name-pattern="pairing step|run presentation" tests/*.test.cjs`  
Run: `npm test`  
Run: `npm run type-check`  
Run: `npm run build:h5`

- [ ] **Step 6: Review checkpoint**

Confirm confirmation code never replaces the lookup short code, approved is not rendered as connected, and terminal states have no looping motion.

### Task 7: Scenario mock, complete browser acceptance, cleanup, and documentation

**Files:**
- Create: `apps/mobile/scripts/mock-scenarios.mjs`
- Modify: `apps/mobile/scripts/mock-server.mjs`
- Modify: `apps/mobile/tests/clients.test.cjs`
- Create: `apps/mobile/tests/mock-server.test.cjs`
- Modify: `apps/mobile/README.md`
- Modify: `README.md`
- Modify: `项目最终架构.md`
- Modify: `阶段步骤实现.md`
- Delete after replacement verification: `apps/mobile/scripts/gen-tabbar-icons.mjs`
- Delete after usage audit: superseded rules in `apps/mobile/src/styles/base.scss` and duplicate page-scoped UI rules
- Delete after durable content migration: `docs/ui-redesign/README.md`
- Delete after durable content migration: `docs/ui-redesign/handoff-prompt.md`
- Delete after durable content migration: `docs/ui-redesign/prototype.html`
- Delete after durable content migration: `docs/ui-redesign/verification.md`
- Test: `apps/mobile/tests/mock-server.test.cjs`

**Interfaces:**
- Produces: deterministic named mock scenarios for authenticated default, empty, loading/error, pairing terminal, and each Run-state family.
- Produces: explicit 404 standard envelopes for unknown mock routes.

- [ ] **Step 1: Write failing mock-contract tests**

Start the server on an ephemeral port and assert login/me/conversations/messages/contacts/groups/agents/connectors/pairings/runs return complete standard envelopes, declared mutations advance scenario state, and an unknown route returns 404 `NOT_FOUND` rather than `{}` success.

- [ ] **Step 2: Run the focused test and verify RED**

Run: `node --test --test-name-pattern="mock server" tests/*.test.cjs`  
Expected: FAIL because unknown routes currently return empty success and mutation/scenario coverage is incomplete.

- [ ] **Step 3: Refactor the mock into deterministic scenarios**

Extract fixtures/route handling from the process entry, add only the states needed for browser acceptance, keep all data fictional, and preserve the simple `node scripts/mock-server.mjs` developer entrypoint.

- [ ] **Step 4: Run the complete automated verification suite**

Run: `npm run icons:generate`  
Run: `npm test`  
Run: `npm run type-check`  
Run: `npm run build:h5`  
Run: `npm run build:app` with the documented non-secret test server base if the local toolchain supports it  
Run: `npm run build:mp-weixin` if the local toolchain supports it  
Expected: zero test/type/build failures; unsupported platform prerequisites are reported precisely.

- [ ] **Step 5: Run the full Playwright CLI matrix**

Use the built H5 plus scenario mock. Check all ten pages at 1440×900, 390×844, 320×568, plus 767/768, 899/900, and 1099/1100 widths. Exercise keyboard focus, Enter/IME rules, sheets, resize, direct chat URL/refresh/back, empty/error/loading states, reduced motion, horizontal overflow, titles, console errors/warnings, and visible status motion. Save representative screenshots under `output/playwright/` only.

- [ ] **Step 6: Audit and delete replaced UI code**

Use `rg` to prove no template uses the legacy selectors or assets, then delete the old `rise-in`, `pop-in`, `breath`, `stagger`, `enter-rise`, old login keyframes, CSS-drawn FAB symbols, duplicated row/button/form rules, and the replaced tab-icon script. Migrate still-valid business boundaries from `docs/ui-redesign/` into the new spec/README, verify links, then remove the superseded prototype package. Every deletion is recoverable from Git history.

- [ ] **Step 7: Re-run verification after cleanup**

Run: `npm test`  
Run: `npm run type-check`  
Run: `npm run build:h5`  
Run: `rg -n "ui-redesign|gen-tabbar-icons|rise-in|pop-in|enter-rise|brand-fade-in|logo-pulse" README.md apps/mobile docs 项目最终架构.md 阶段步骤实现.md -g '!docs/superpowers/**' -g '!node_modules'`  
Expected: tests/type/build pass and the reference scan returns no stale production/documentation dependency.

- [ ] **Step 8: Update maintained documentation and final evidence**

Document the final component tree, icon generation, mock scenarios, H5/App/mini build status, browser matrix, known limitations, and exact cleanup list. Do not mark real authenticated business, Android device, or production deployment as accepted unless separately executed.

- [ ] **Step 9: Final review checkpoint**

Compare the final diff against every spec section and the original A01–A10 report; list any unmet requirement rather than weakening the acceptance wording.
