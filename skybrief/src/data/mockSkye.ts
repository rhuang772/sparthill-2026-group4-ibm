import type { SkyeResponse } from '../types';

interface SkyeEntry {
  keywords: string[];
  response: SkyeResponse;
}

const SKYE_ENTRIES: SkyeEntry[] = [
  {
    keywords: ['tfr', 'temporary flight restriction'],
    response: {
      text: 'A Temporary Flight Restriction (TFR) is a short-term restriction on flight in a specific airspace area. TFRs are issued by the FAA for emergencies, VIP movements, wildfires, and major events. In California, wildfire TFRs (14 CFR § 91.137) are especially important — they prohibit all drone flights within the restricted area. Always check the FAA TFR map before flying.',
      citation: {
        source: 'FAA TFR Map — 14 CFR § 91.137',
        url: 'https://tfr.faa.gov',
        layer: 'federal',
      },
    },
  },
  {
    keywords: ['register', 'registration', 'do i need to register'],
    response: {
      text: 'If your drone weighs 250 grams or more, you must register it with the FAA before flying outdoors. Registration costs $5 and is valid for 3 years. Drones under 250 g are exempt from registration, though the 400 ft AGL limit and other rules still apply. Your drone at 249 g does not require registration.',
      citation: {
        source: '14 CFR Part 48 — FAA Drone Registration',
        url: 'https://www.faa.gov/uas/getting_started/register_drone',
        layer: 'federal',
      },
    },
  },
  {
    keywords: ['laanc', 'authorization', 'controlled airspace'],
    response: {
      text: 'LAANC stands for Low Altitude Authorization and Notification Capability. It\'s the FAA system that gives recreational and commercial drone pilots near-real-time authorization to fly in controlled airspace below approved altitudes. You apply through an FAA-approved app (e.g., Aloft, Kittyhawk). Your planned flight is in Class G uncontrolled airspace — LAANC is not needed for this flight.',
      citation: {
        source: 'FAA LAANC Overview',
        url: 'https://www.faa.gov/uas/programs_partnerships/data_exchange',
        layer: 'federal',
      },
    },
  },
  {
    keywords: ['sunset', 'night', 'twilight', 'fly at night', 'fly after dark'],
    response: {
      text: 'Recreational drone pilots must fly during daylight or civil twilight (30 minutes before sunrise and 30 minutes after sunset), provided the drone has anti-collision lighting visible for at least 3 statute miles. Flying after civil twilight ends is not permitted for recreational flyers. For your flight today, civil twilight ends at 18:28 PDT — plan to land well before then.',
      citation: {
        source: '49 U.S.C. § 44809(a)(6) — Recreational UAS Night Flying',
        url: 'https://www.faa.gov/uas/recreational_fliers',
        layer: 'federal',
      },
    },
  },
  {
    keywords: ['lake', 'water', 'fly over water', 'privacy'],
    response: {
      text: 'Flying near or over water is not prohibited under federal FAA rules, but California Civil Code § 1708.8 prohibits capturing images or recordings of people on private property where they have a reasonable expectation of privacy, even from a drone. Near Coyote Lake, avoid hovering over adjacent private residences or campsites. There\'s also a practical risk: a drone that loses signal or power over water is difficult to recover.',
      citation: {
        source: 'California Civil Code § 1708.8 — Drone Privacy',
        url: 'https://leginfo.legislature.ca.gov/faces/codes_displaySection.xhtml?sectionNum=1708.8.&lawCode=CIV',
        layer: 'ca-state',
      },
    },
  },
];

export const SKYE_FALLBACK: SkyeResponse = {
  text: "I can only answer questions grounded in my official source library — FAA regulations, California statutes, NPS guidelines, and CA State Parks rules. For this question, I'd recommend checking the FAA's UAS help center at faa.gov/uas or California's official resources.",
  citation: {
    source: 'FAA UAS Resource Hub',
    url: 'https://www.faa.gov/uas',
    layer: 'federal',
  },
};

export function getSkyeResponse(input: string): SkyeResponse {
  const lower = input.toLowerCase();
  for (const entry of SKYE_ENTRIES) {
    if (entry.keywords.some((kw) => lower.includes(kw))) {
      return entry.response;
    }
  }
  return SKYE_FALLBACK;
}
