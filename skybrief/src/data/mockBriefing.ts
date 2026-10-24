import type { BriefingPack, AlternativeLocation } from '../types';

export const mockBriefing: BriefingPack = {
  locationLabel: 'Coyote Lake–Harvey Bear Ranch County Park',
  dateTimeLabel: 'Oct 24, 2026 · 17:15 PDT',
  verdict: {
    result: 'caution',
    summary:
      'Your flight is legal in federal airspace but requires attention: sunset is approaching, wind is gusty, and the lake creates a privacy consideration. Review each factor below before flying.',
    factors: ['sunset-approaching', 'gusty-wind', 'water-proximity'],
  },

  findings: [
    {
      layer: 'federal',
      title: 'Class G Airspace — No Authorization Required',
      status: 'pass',
      explanation:
        'Uncontrolled airspace (Class G). The 400 ft AGL ceiling applies. No LAANC authorization needed.',
      citation: {
        source: 'FAA UAS Recreational Rules',
        url: 'https://www.faa.gov/uas/recreational_fliers',
        layer: 'federal',
      },
    },
    {
      layer: 'federal',
      title: 'FAA Registration — Not Required',
      status: 'pass',
      explanation: 'Drone under 250 g — FAA registration not required.',
      citation: {
        source: '14 CFR § 48.15',
        url: 'https://www.ecfr.gov/current/title-14/chapter-I/subchapter-F/part-48/section-48.15',
        layer: 'federal',
      },
    },
    {
      layer: 'federal',
      title: 'Daylight Window — Tight',
      status: 'warn',
      explanation:
        'Sunset at 18:02 PDT — 47 minutes from planned takeoff. Daylight window is tight; civil twilight ends at 18:28.',
      citation: {
        source: '14 CFR § 107.29',
        url: 'https://www.ecfr.gov/current/title-14/chapter-I/subchapter-F/part-107/section-107.29',
        layer: 'federal',
      },
    },
    {
      layer: 'ca-state',
      title: 'California State Parks — No Active Ban',
      status: 'pass',
      explanation: 'No active California State Parks ban at this location.',
      citation: {
        source: '14 CCR § 4351',
        url: 'https://govt.westlaw.com/calregs/Document/I7E8AEB7FA51211E1B0AE9B7B9D2B4D98',
        layer: 'ca-state',
      },
    },
    {
      layer: 'ca-state',
      title: 'Privacy Law — Lake Adjacency',
      status: 'warn',
      explanation:
        'Coyote Lake is within 200 ft. California Civil Code § 1708.8 covers drone-based invasion of privacy. Avoid flying over people on adjacent private land.',
      citation: {
        source: 'CA Civil Code § 1708.8',
        url: 'https://leginfo.legislature.ca.gov/faces/codes_displaySection.xhtml?sectionNum=1708.8.&lawCode=CIV',
        layer: 'ca-state',
      },
    },
    {
      layer: 'local',
      title: 'Santa Clara County Parks — Verify On-Site',
      status: 'warn',
      explanation:
        'Santa Clara County Parks: no confirmed digital drone ban posted, but rules may be posted on-site. Verify at the trailhead before flying.',
      citation: {
        source: 'Santa Clara County Parks',
        url: 'https://parks.sccgov.org/santa-clara-county-parks/coyote-lake-harvey-bear-ranch-county-park',
        layer: 'local',
      },
    },
  ],

  riskFactors: [
    {
      type: 'wind',
      label: 'Wind',
      severity: 'medium',
      detail: 'Gusts 22 mph — marginal for sub-250 g drones in open terrain. Consider landing before gusts increase.',
    },
    {
      type: 'light',
      label: 'Light',
      severity: 'medium',
      detail: 'Sunset in 47 min. Plan to land by 17:50 to allow a comfortable margin.',
    },
    {
      type: 'water',
      label: 'Water',
      severity: 'low',
      detail: 'Coyote Lake within 200 ft. Risk of flyaway landing in water. Fly away from the lake shore.',
    },
  ],

  alternative: {
    name: 'Ed Levin County Park, Milpitas',
    distance: '4.2 mi north',
    reason:
      'Same Class G airspace, no water adjacency, no posted ban. Earlier sunset clearance from higher elevation.',
    coordinates: { lat: 37.46, lng: -121.86 },
  } satisfies AlternativeLocation,

  generatedAt: '2026-10-24T17:15:00-07:00',
};

// ── No-Go demo scenario: SJSU campus, inside SJC's Class C controlled airspace ──

export const mockBriefingNoGo: BriefingPack = {
  locationLabel: 'San José State University campus — inside SJC Class C airspace',
  dateTimeLabel: 'Oct 24, 2026 · 13:30 PDT',

  verdict: {
    result: 'no-go',
    summary:
      'This spot sits inside Mineta San José International Airport\'s Class C controlled airspace, and no LAANC authorization is on file. A temporary flight restriction is also active nearby. Do not fly from this location.',
    factors: ['controlled-airspace-no-authorization', 'tfr-active', 'crowded-campus'],
  },

  findings: [
    {
      layer: 'federal',
      title: 'Class C Controlled Airspace — LAANC Authorization Required',
      status: 'fail',
      explanation:
        'This location is within 5 nm of Mineta San José International Airport (SJC), inside Class C surface airspace. Recreational pilots must obtain LAANC authorization through an FAA-approved app before flying here, and none is on file for this flight.',
      citation: {
        source: 'FAA LAANC — Low Altitude Authorization and Notification Capability',
        url: 'https://www.faa.gov/uas/programs_partnerships/data_exchange',
        layer: 'federal',
      },
    },
    {
      layer: 'federal',
      title: 'Temporary Flight Restriction Active',
      status: 'fail',
      mocked: true,
      explanation:
        'A TFR is shown as active over this area. This entry is simulated for the demo — in production it would come from the live FAA TFR feed. It stands in for how SkyBrief flags an active TFR, which would independently ground this flight even with airspace authorization.',
      citation: {
        source: 'FAA TFR Map (simulated — not a live feed)',
        url: 'https://tfr.faa.gov',
        layer: 'federal',
      },
    },
    {
      layer: 'federal',
      title: 'FAA Registration — Not Required',
      status: 'pass',
      explanation: 'Drone under 250 g — FAA registration not required.',
      citation: {
        source: '14 CFR § 48.15',
        url: 'https://www.ecfr.gov/current/title-14/chapter-I/subchapter-F/part-48/section-48.15',
        layer: 'federal',
      },
    },
    {
      layer: 'ca-state',
      title: 'California State Parks — No Active Ban',
      status: 'pass',
      explanation: 'No active California State Parks ban at this location.',
      citation: {
        source: '14 CCR § 4351',
        url: 'https://govt.westlaw.com/calregs/Document/I7E8AEB7FA51211E1B0AE9B7B9D2B4D98',
        layer: 'ca-state',
      },
    },
    {
      layer: 'local',
      title: 'SJSU Campus — High Pedestrian Density',
      status: 'warn',
      explanation:
        'Campus grounds see heavy foot traffic throughout the day. Even where airspace is authorized, flying over uninvolved people is not permitted without a Part 107 waiver.',
      citation: {
        source: 'San José State University — Campus Grounds Policy',
        url: 'https://www.sjsu.edu',
        layer: 'local',
      },
    },
  ],

  riskFactors: [
    {
      type: 'airspace',
      label: 'Controlled Airspace',
      severity: 'high',
      detail: 'Inside SJC Class C surface area — flight without LAANC authorization is illegal here.',
    },
    {
      type: 'crowds',
      label: 'Crowds',
      severity: 'high',
      detail: 'Dense pedestrian traffic across the SJSU campus — flying over uninvolved people is not permitted without a waiver.',
    },
  ],

  alternative: {
    name: 'Kelley Park, San José',
    distance: '1.6 mi south',
    reason:
      'Outside SJC\'s Class C surface area — uncontrolled Class G airspace with no LAANC requirement. Still check posted park rules before flying.',
    coordinates: { lat: 37.3283, lng: -121.8646 },
  } satisfies AlternativeLocation,

  generatedAt: '2026-10-24T13:30:00-07:00',
};
