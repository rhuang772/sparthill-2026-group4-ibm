// ── Pilot Profile ────────────────────────────────────────────────────────────

export type FlightPurpose = 'recreational' | 'commercial';
export type DroneWeightClass = 'under250g' | 'over250g';
export type ExperienceLevel = 'first-flight' | 'some-experience' | 'experienced';

export interface PilotProfile {
  purpose: FlightPurpose;
  trustPassed: boolean;
  part107: boolean;
  droneWeightClass: DroneWeightClass;
  experienceLevel: ExperienceLevel;
}

// ── Flight Plan ──────────────────────────────────────────────────────────────

export interface FlightPlan {
  location: {
    lat: number;
    lng: number;
    displayName: string;
  };
  date: string;
  time: string;
  plannedAltitudeFt: number;
  radiusMeters: number;
}

// ── Briefing ─────────────────────────────────────────────────────────────────

export type RuleLayer = 'federal' | 'ca-state' | 'local';

export interface Citation {
  source: string;
  url: string;
  layer: RuleLayer;
}

export interface RuleFinding {
  layer: RuleLayer;
  title: string;
  status: 'pass' | 'warn' | 'fail';
  explanation: string;
  citation: Citation;
  /** True when the underlying data is simulated for the demo (e.g. no live TFR feed). */
  mocked?: boolean;
}

export interface RiskFactor {
  type: string;
  label: string;
  severity: 'low' | 'medium' | 'high';
  detail: string;
}

export type VerdictResult = 'go' | 'caution' | 'no-go';

export interface Verdict {
  result: VerdictResult;
  summary: string;
  factors: string[];
}

export interface AlternativeLocation {
  name: string;
  distance: string;
  reason: string;
  coordinates: { lat: number; lng: number };
}

export interface BriefingPack {
  locationLabel: string;
  dateTimeLabel: string;
  verdict: Verdict;
  findings: RuleFinding[];
  riskFactors: RiskFactor[];
  alternative: AlternativeLocation;
  generatedAt: string;
}

// ── Lesson & Quiz ────────────────────────────────────────────────────────────

export interface Lesson {
  title: string;
  ruleText: string;
  context: string;
  citation: Citation;
}

export interface QuizAnswer {
  text: string;
  correct: boolean;
  explanation: string;
}

export interface QuizQuestion {
  question: string;
  options: QuizAnswer[];
  correctIndex: number;
  explanation: string;
}

// ── Chat ─────────────────────────────────────────────────────────────────────

export interface ChatMessage {
  role: 'user' | 'skye';
  text: string;
  citation?: Citation;
}

export interface SkyeResponse {
  text: string;
  citation: Citation;
}
