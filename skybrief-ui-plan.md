# SkyBrief UI Mockup Plan

## Top-Level Overview

Build five static React + TypeScript web pages (screens) for the SkyBrief MVP — an AI-powered educational drone-flight coach for California beginners. These are **UI mockups only**: no backend calls, no live data. All screens use hardcoded props/state that represent realistic demo scenarios. The goal is a working, navigable prototype that can be demoed live at SpartHill Hacks 2026.

**Stack:** Vite + React + TypeScript, CSS Modules, React Router v6, Leaflet (map), Lucide React (icons).
**Design language:** Dark-sky/cockpit aesthetic — deep navy (`#0D1B2A`) and charcoal (`#1A2B3C`) backgrounds, amber/gold (`#F59E0B`) primary accents, crisp white (`#F1F5F9`) text. Deliberately avoids the blue-green palette common in aviation apps (B4UFLY, AutoPylot).
**AppShell nav:** Linear 1→2→3→4→5 stepper shown at the top of every screen, with the current step highlighted.
**Skye chat header:** Small circular avatar icon (Lucide `Bot` icon in an amber circle) beside the "Skye" wordmark.
**No backend code** in this phase.

---

## Sub-Tasks

---

### Sub-Task 1 — Project Scaffold

**Intent:** Initialize the Vite + React + TypeScript project, install dependencies (React Router, Leaflet + react-leaflet), set up CSS reset and global design tokens, and wire up routing so all five screens are reachable via `<Link>` or `useNavigate`.

**Expected Outcomes:**
- `npm run dev` starts the app with no errors.
- Navigating to `/`, `/flight-plan`, `/briefing`, `/lesson`, `/chat` renders a placeholder for each screen.
- Global CSS variables for the dark-sky palette are defined and available.

**Todo List:**
1. `npm create vite@latest skybrief -- --template react-ts` inside `sparthill-2026-group4-ibm/`.
2. `cd skybrief && npm install react-router-dom leaflet react-leaflet @types/leaflet lucide-react`.
3. Create `src/styles/tokens.css` with CSS custom properties for all color, spacing, typography, and shadow tokens.
4. Create `src/main.tsx` wrapping `<App>` in `<BrowserRouter>`.
5. Create `src/App.tsx` with `<Routes>` for all five paths: `/`, `/flight-plan`, `/briefing`, `/lesson`, `/chat`.
6. Create five placeholder page components: `PilotProfilePage`, `FlightPlanPage`, `BriefingPage`, `LessonPage`, `ChatPage`.
7. Create `src/components/AppShell.tsx` — a nav bar with the SkyBrief wordmark and a linear 1→2→3→4→5 stepper (Lucide `Check` for completed steps, amber highlight for active step) shared across all screens.

**Relevant Context:**
- `sparthill-2026-group4-ibm/` is the repo root.
- All source lives under `sparthill-2026-group4-ibm/skybrief/src/`.
- Tokens must define: `--color-bg`, `--color-surface`, `--color-accent`, `--color-accent-muted`, `--color-text-primary`, `--color-text-secondary`, `--color-success`, `--color-caution`, `--color-danger`, `--radius-md`, `--shadow-card`.

**Status:** `[x] done`

---

### Sub-Task 2 — Screen 1: Pilot Profile

**Intent:** Onboarding form that captures pilot status, certifications, and drone weight class. On submit it stores the profile in React state (or a simple context) and navigates to Screen 2.

**Expected Outcomes:**
- Form with four logical sections: Flight Purpose, Certifications, Drone Weight, Summary.
- Selecting "recreational" and no certifications renders a prominent "Not ready to fly yet" callout with the TRUST test link.
- Selecting valid combination enables the "Save Profile & Continue" CTA.
- Amber accent used for section labels; card-style layout with rounded corners and subtle shadow.

**Todo List:**
1. Create `src/types/index.ts` with `PilotProfile`, `DroneWeightClass`, `FlightPurpose` TypeScript types (no backend logic, just shapes).
2. Create `src/pages/PilotProfilePage.tsx`.
3. Implement the four-section form using controlled inputs; validate on submit.
4. Create `src/components/NotReadyBanner.tsx` — amber warning card shown when TRUST is not passed for recreational pilots.
5. Create `src/context/AppContext.tsx` — a React context holding `pilotProfile` and `setPilotProfile` so downstream screens can read it.
6. Wire "Save Profile & Continue" to write to context and navigate to `/flight-plan`.
7. Style with `PilotProfilePage.module.css` using the dark-sky tokens.

**Relevant Context:**
- `PilotProfile` type fields: `purpose: 'recreational' | 'commercial'`, `trustPassed: boolean`, `part107: boolean`, `droneWeightClass: 'under250g' | 'over250g'`.
- The "Not ready to fly" state is an important demo talking point — make it visually distinct.

**Status:** `[x] done`

---

### Sub-Task 3 — Screen 2: Flight Plan

**Intent:** Let the user pick a California location on a Leaflet map, choose a date/time, and trigger the CA-scope guard. On submit, navigate to Screen 3 (Briefing) with the plan in context.

**Expected Outcomes:**
- Leaflet map centered on California; user can click to drop a pin.
- Date picker and time picker inputs below the map.
- If the pin is outside California (mocked with a simple lat/lng bounding box check), a "SkyBrief currently covers California only" banner replaces the CTA.
- "Plan this flight" CTA navigates to `/briefing`.

**Todo List:**
1. Add `FlightPlan` type to `src/types/index.ts`: `location: { lat, lng, displayName }`, `date: string`, `time: string`.
2. Create `src/pages/FlightPlanPage.tsx`.
3. Integrate `react-leaflet` `MapContainer` + `TileLayer` + `Marker`; handle click-to-place-pin.
4. Add date/time inputs in a sidebar panel beside the map.
5. Create `src/utils/caScope.ts` — a function `isInCalifornia(lat, lng): boolean` using a bounding box check (lat 32.5–42.0, lng -124.5 to -114.1).
6. Show `src/components/OutOfScopeBanner.tsx` when `!isInCalifornia`.
7. Wire "Plan this flight" to write `FlightPlan` to context and navigate to `/briefing`.
8. Style with `FlightPlanPage.module.css`.

**Relevant Context:**
- Map tile: OpenStreetMap (`https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png`).
- Leaflet needs a CSS import; add `import 'leaflet/dist/leaflet.css'` in `main.tsx`.
- Default Leaflet marker icons break with Vite bundling; apply the standard icon fix (`delete L.Icon.Default.prototype._getIconUrl; L.Icon.Default.mergeOptions(...)`) in a `src/utils/leafletIconFix.ts`.

**Status:** `[x] done`

---

### Sub-Task 4 — Screen 3: Flight Briefing

**Intent:** Display a rich, layered briefing for the hardcoded demo scenario (lakeside park, late afternoon, gusty wind, sunset soon → Caution verdict). Organized into: Verdict card, Layered Rules accordion (Federal → CA State → Local), Risk Factors, and Alternative Location suggestion.

**Expected Outcomes:**
- Prominent "⚠ CAUTION" verdict card in amber.
- Rules accordion with three layers: each layer has a label badge ("Federal", "CA State", "Local"), a plain-language explanation, a cited source link, and a pass/warn/fail icon.
- Risk Factors section with icon cards: Wind (gusty), Light (sunset in 42 min), Water nearby.
- Alternative Location card: "Kelley Park (0.8 mi) — uncontrolled airspace, no posted ban."
- Disclaimer banner at the bottom.
- "Continue to Lesson →" CTA navigates to `/lesson`.

**Todo List:**
1. Add `RuleLayer`, `RuleFinding`, `RiskFactor`, `Verdict`, `Citation` types to `src/types/index.ts`.
2. Create `src/data/mockBriefing.ts` — hardcoded `BriefingResult` object for the Caution scenario (Coyote Lake Harvey Bear Ranch, San José area, gusty wind, sunset 42 min away).
3. Create `src/pages/BriefingPage.tsx`; import mock data.
4. Create `src/components/VerdictCard.tsx` — large card showing Go/Caution/No-Go with color, icon, and summary text.
5. Create `src/components/RulesAccordion.tsx` — collapsible sections per layer; each rule card has a badge, icon, explanation, and citation link.
6. Create `src/components/RiskFactorCard.tsx` — compact icon card for each risk.
7. Create `src/components/AlternativeSuggestion.tsx` — card with pin icon, alternative name, distance, and brief reason.
8. Style with `BriefingPage.module.css`.

**Relevant Context:**
- Verdict colors: Go = `--color-success` (#22C55E), Caution = `--color-caution` (#F59E0B), No-Go = `--color-danger` (#EF4444).
- Layer badge colors: Federal = blue (#3B82F6), CA State = gold (#D97706), Local = purple (#8B5CF6).
- Use Lucide React icons or Unicode symbols (no icon library install needed if using Unicode).
- The disclaimer must read: "SkyBrief is an educational tool, not legal advice or FAA authorization. The pilot makes the final decision."

**Status:** `[x] done`

---

### Sub-Task 5 — Screen 4: Rules Lesson + Quiz

**Intent:** Teach one rule in context (derived from the Caution briefing), then present 2–3 comprehension questions. Show correct/incorrect feedback and a "lesson complete" summary. Navigate to Chat screen.

**Expected Outcomes:**
- Lesson card: rule name, rule text (plain language), cited source, and a "Why this matters for your flight" contextual note.
- Quiz section: 2–3 multiple-choice questions; selecting an answer reveals immediate color feedback (green/red) and a one-sentence explanation.
- "All correct" or "Review complete" state with score badge; "Ask Skye a follow-up →" CTA navigates to `/chat`.
- Pre/post quiz framing (a brief "before" question at top, same question revisited at end) to show learning delta in the demo.

**Todo List:**
1. Add `Lesson`, `QuizQuestion`, `QuizAnswer` types to `src/types/index.ts`.
2. Create `src/data/mockLesson.ts` — hardcoded lesson on "FAA 400 ft AGL limit in uncontrolled airspace" with 2 quiz questions.
3. Create `src/pages/LessonPage.tsx`.
4. Create `src/components/LessonCard.tsx` — styled rule explanation card with source badge.
5. Create `src/components/QuizQuestion.tsx` — renders one MCQ with answer options; manages selected/submitted state.
6. Create `src/components/QuizSummary.tsx` — shows score, badge (🎓 if all correct), and CTA.
7. Implement pre-question at page load before the lesson card is revealed, then the same question again in the summary to show the delta.
8. Style with `LessonPage.module.css`.

**Relevant Context:**
- The lesson topic should flow naturally from the Caution briefing: teach the 400 ft rule since the briefing scenario involved altitude concerns.
- Quiz questions must have a `correct: boolean` flag and an `explanation: string`.

**Status:** `[x] done`

---

### Sub-Task 6 — Screen 5: Skye Agent Q&A

**Intent:** A chat interface where the user asks follow-up questions and "Skye" (the AI coach) responds. In mockup mode, responses are drawn from a hardcoded FAQ map (no live LLM). The UI must show Skye's grounding behavior: each response cites a source and its rule layer.

**Expected Outcomes:**
- Chat bubble interface: user messages on the right (amber), Skye responses on the left (dark surface card).
- Skye avatar/icon in the header.
- Each Skye response includes a source citation chip at the bottom (e.g., "Source: FAA UAS Safety — Federal").
- "Grounded only" badge on Skye's messages indicating she only answers from official sources.
- Hardcoded responses for 3–4 realistic follow-up questions (e.g., "Can I fly over the lake?", "What is a TFR?", "Do I need to register my drone?").
- Input field + send button; unrecognized questions return a polite fallback: "I can only answer from my official source library. Try the FAA website at faa.gov/uas."
- Skye identity: friendly, calm, aviation-adjacent name; amber accent on her bubble borders.

**Todo List:**
1. Add `ChatMessage`, `SkyeResponse` types to `src/types/index.ts`.
2. Create `src/data/mockSkye.ts` — map of keyword patterns to hardcoded `SkyeResponse` objects.
3. Create `src/pages/ChatPage.tsx`.
4. Create `src/components/ChatBubble.tsx` — renders a single user or Skye message with appropriate alignment and styling.
5. Create `src/components/CitationChip.tsx` — compact inline badge showing source name and layer color.
6. Implement a simple keyword matcher in `ChatPage.tsx`: scan input for keywords, return matching response or fallback.
7. Auto-scroll to latest message on new entry.
8. Style with `ChatPage.module.css`.

**Relevant Context:**
- Skye's name and personality are a key differentiator vs. generic aviation apps — make the chat header visually distinct.
- The "grounded only" behavior is a Responsible AI talking point for the demo; make it visually prominent.

**Status:** `[x] done`

---

## File / Folder Structure

```
sparthill-2026-group4-ibm/
└── skybrief/
    ├── index.html
    ├── vite.config.ts
    ├── tsconfig.json
    ├── package.json
    └── src/
        ├── main.tsx
        ├── App.tsx
        ├── styles/
        │   ├── tokens.css
        │   └── reset.css
        ├── types/
        │   └── index.ts
        ├── context/
        │   └── AppContext.tsx
        ├── data/
        │   ├── mockBriefing.ts
        │   ├── mockLesson.ts
        │   └── mockSkye.ts
        ├── utils/
        │   ├── caScope.ts
        │   └── leafletIconFix.ts
        ├── components/
        │   ├── AppShell.tsx
        │   ├── NotReadyBanner.tsx
        │   ├── OutOfScopeBanner.tsx
        │   ├── VerdictCard.tsx
        │   ├── RulesAccordion.tsx
        │   ├── RiskFactorCard.tsx
        │   ├── AlternativeSuggestion.tsx
        │   ├── LessonCard.tsx
        │   ├── QuizQuestion.tsx
        │   ├── QuizSummary.tsx
        │   ├── ChatBubble.tsx
        │   └── CitationChip.tsx
        └── pages/
            ├── PilotProfilePage.tsx
            ├── FlightPlanPage.tsx
            ├── BriefingPage.tsx
            ├── LessonPage.tsx
            └── ChatPage.tsx
```

---

## Key TypeScript Types (shapes only, no logic)

All defined in `src/types/index.ts`:

- `PilotProfile` — purpose, trustPassed, part107, droneWeightClass
- `FlightPlan` — location (lat/lng/displayName), date, time
- `RuleLayer` — `'federal' | 'ca-state' | 'local'`
- `RuleFinding` — layer, title, status (pass/warn/fail), explanation, citation
- `RiskFactor` — type, label, severity, detail
- `Verdict` — result (go/caution/no-go), summary, factors
- `Citation` — source, url, layer
- `Lesson` — title, ruleText, context, citation
- `QuizQuestion` — question, options, correctIndex, explanation
- `ChatMessage` — role (user/skye), text, citation?
- `BriefingPack` — verdict, findings, riskFactors, alternative, generatedAt

---

## Design Tokens (CSS custom properties)

| Token | Value | Use |
|---|---|---|
| `--color-bg` | `#0D1B2A` | Page background |
| `--color-surface` | `#1A2B3C` | Cards, panels |
| `--color-surface-raised` | `#243447` | Elevated cards |
| `--color-accent` | `#F59E0B` | Primary CTA, labels |
| `--color-accent-muted` | `#78350F` | Accent hover states |
| `--color-text-primary` | `#F1F5F9` | Body text |
| `--color-text-secondary` | `#94A3B8` | Labels, captions |
| `--color-success` | `#22C55E` | Go verdict |
| `--color-caution` | `#F59E0B` | Caution verdict |
| `--color-danger` | `#EF4444` | No-Go verdict |
| `--color-federal` | `#3B82F6` | Federal rule badge |
| `--color-ca-state` | `#D97706` | CA State rule badge |
| `--color-local` | `#8B5CF6` | Local rule badge |
| `--radius-md` | `8px` | Card corners |
| `--radius-lg` | `16px` | Screen panels |
| `--shadow-card` | `0 4px 24px rgba(0,0,0,0.4)` | Card elevation |

---

## Demo Scenario (hardcoded into mock data)

**Pilot:** Recreational, TRUST passed, drone 249 g (under 250 g).
**Location:** Coyote Lake–Harvey Bear Ranch County Park, San José area (~37.10°N, 121.45°W).
**Date/Time:** Oct 24, 2026, 17:15 PDT.
**Verdict:** ⚠ CAUTION

**Briefing findings:**
- Federal/Pass: Uncontrolled Class G airspace, 400 ft AGL limit applies, no LAANC needed.
- Federal/Pass: Drone under 250 g — FAA registration not required.
- Federal/Warn: Sunset at 18:02 — 47 min from planned takeoff. Daylight window is tight.
- CA State/Pass: No active State Parks ban at this location.
- CA State/Warn: Water body (Coyote Lake) within 200 ft — privacy law caution.
- Local/Warn: Check Santa Clara County Parks posted signs — no confirmed digital ban, but verify on-site.

**Risk Factors:** Wind gusts 22 mph (marginal for sub-250 g), sunset 47 min, lake proximity.
**Alternative:** Ed Levin County Park, 4.2 mi north — same airspace class, no water adjacency, earlier sunset clearance.

**Lesson topic:** FAA 400 ft AGL ceiling in uncontrolled airspace.
**Skye FAQ topics:** TFR definition, drone registration thresholds, LAANC explanation, flying at sunset rules.
