import type { Lesson, QuizQuestion } from '../types';

export const mockLesson: Lesson = {
  title: 'FAA 400 ft AGL Ceiling in Uncontrolled Airspace',
  ruleText:
    'Recreational flyers operating under the Exception for Limited Recreational Operations (49 U.S.C. § 44809) must not fly above 400 feet above ground level (AGL) in uncontrolled Class G airspace, unless flying within a 400-foot radius of a structure and no higher than 400 feet above the structure\'s immediate uppermost limit.',
  context:
    'Your planned flight over Coyote Lake is in Class G uncontrolled airspace. This means the 400 ft AGL ceiling applies directly to you. Flying higher risks conflict with manned aircraft, which have priority.',
  citation: {
    source: '49 U.S.C. § 44809 / FAA Recreational UAS Safety Test (TRUST)',
    url: 'https://www.faa.gov/uas/recreational_fliers',
    layer: 'federal',
  },
};

export const preQuestion: QuizQuestion = {
  question:
    'Before we begin — in uncontrolled airspace, what is the maximum altitude a recreational drone pilot can fly?',
  options: [
    { text: '200 ft AGL', correct: false, explanation: '' },
    { text: '400 ft AGL', correct: true, explanation: '' },
    { text: '500 ft AGL', correct: false, explanation: '' },
    { text: 'No limit', correct: false, explanation: '' },
  ],
  correctIndex: 1,
  explanation:
    'The FAA limits recreational flyers to 400 ft AGL in uncontrolled (Class G) airspace under 49 U.S.C. § 44809.',
};

export const quizQuestions: QuizQuestion[] = [
  {
    question:
      'If you plan to fly recreationally near a 300 ft tall building in Class G airspace, what is the maximum altitude you can reach above the building\'s roof?',
    options: [
      { text: '100 ft', correct: false, explanation: '' },
      { text: '400 ft', correct: true, explanation: '' },
      { text: '700 ft', correct: false, explanation: '' },
      { text: 'No additional height allowed', correct: false, explanation: '' },
    ],
    correctIndex: 1,
    explanation:
      'You may fly up to 400 ft above the uppermost limit of a structure within a 400 ft radius — so 300 ft + 400 ft = 700 ft AGL total, but the rule allows 400 ft above the structure, making 400 ft above the roof the cap.',
  },
  {
    question:
      'Which airspace class requires LAANC authorization instead of the 400 ft AGL recreational limit applying automatically?',
    options: [
      { text: 'Class G', correct: false, explanation: '' },
      { text: 'Class E', correct: false, explanation: '' },
      { text: 'Class B, C, D, or E near airports', correct: true, explanation: '' },
      { text: 'Class A', correct: false, explanation: '' },
    ],
    correctIndex: 2,
    explanation:
      'In controlled airspace (Class B, C, D, or E within airport surface area), recreational flyers need LAANC authorization — the recreational 400 ft rule applies in uncontrolled Class G airspace.',
  },
  {
    question: 'Recreational drone pilots must keep their aircraft within:',
    options: [
      { text: 'Visual line of sight at all times', correct: true, explanation: '' },
      { text: '100 feet of the pilot', correct: false, explanation: '' },
      { text: 'Cellular data range', correct: false, explanation: '' },
      { text: 'Line of sight only during takeoff and landing', correct: false, explanation: '' },
    ],
    correctIndex: 0,
    explanation:
      '49 U.S.C. § 44809 requires recreational flyers to maintain visual line of sight of their drone (or use a visual observer) throughout the entire flight.',
  },
  {
    question:
      'What must every recreational drone pilot complete before flying, regardless of experience level?',
    options: [
      { text: 'The TRUST (Recreational UAS Safety Test)', correct: true, explanation: '' },
      { text: 'A Part 107 written exam', correct: false, explanation: '' },
      { text: 'A medical certificate', correct: false, explanation: '' },
      { text: 'An in-person FAA interview', correct: false, explanation: '' },
    ],
    correctIndex: 0,
    explanation:
      'The free Recreational UAS Safety Test (TRUST) is required for all recreational flyers under 49 U.S.C. § 44809, confirming they understand the safety rules.',
  },
  {
    question: 'At what weight does a recreational drone need to be registered with the FAA?',
    options: [
      { text: '100 g or more', correct: false, explanation: '' },
      { text: '250 g or more', correct: true, explanation: '' },
      { text: '500 g or more', correct: false, explanation: '' },
      { text: 'Registration is never required for recreational drones', correct: false, explanation: '' },
    ],
    correctIndex: 1,
    explanation:
      'Drones weighing 250 grams (about 0.55 lb) or more must be registered with the FAA before flying outdoors, per 14 CFR Part 48.',
  },
  {
    question: 'Can recreational pilots legally fly at night?',
    options: [
      { text: 'No — recreational flights are daylight-only', correct: false, explanation: '' },
      {
        text: 'Yes, but only with anti-collision lighting visible for 3 statute miles',
        correct: true,
        explanation: '',
      },
      { text: 'Yes, with no additional requirements', correct: false, explanation: '' },
      { text: 'Only with a Part 107 waiver', correct: false, explanation: '' },
    ],
    correctIndex: 1,
    explanation:
      'Recreational flyers may fly during civil twilight or at night if the drone has anti-collision lighting visible for at least 3 statute miles, per 49 U.S.C. § 44809(a)(6).',
  },
  {
    question: 'What is Remote ID, and when is it required?',
    options: [
      { text: "A pilot's license number, required only for Part 107 operators", correct: false, explanation: '' },
      {
        text: "A drone's \"digital license plate\" broadcasting identification and location, required for most drones",
        correct: true,
        explanation: '',
      },
      { text: 'A paid subscription for weather alerts', correct: false, explanation: '' },
      { text: 'An optional FAA app for logging flights', correct: false, explanation: '' },
    ],
    correctIndex: 1,
    explanation:
      "Remote ID broadcasts a drone's identification, location, and altitude in flight. It's required for most registered drones, including recreational ones, with narrow exceptions like FAA-recognized identification areas.",
  },
  {
    question: 'Under recreational rules, can you fly directly over uninvolved people?',
    options: [
      { text: 'Yes, with no restrictions', correct: false, explanation: '' },
      { text: "No — avoid flying over people who aren't part of your operation", correct: true, explanation: '' },
      { text: 'Yes, but only above 400 ft', correct: false, explanation: '' },
      { text: 'Only with a permit from local police', correct: false, explanation: '' },
    ],
    correctIndex: 1,
    explanation:
      'Recreational pilots should avoid flying over uninvolved people and moving vehicles. Operating over people is a Part 107 commercial allowance (with a waiver), not a recreational one.',
  },
  {
    question: 'You see a Temporary Flight Restriction (TFR) over your planned flight area. What should you do?',
    options: [
      { text: 'Fly below 400 ft to avoid it', correct: false, explanation: '' },
      { text: 'Do not fly in that airspace until the TFR is lifted', correct: true, explanation: '' },
      { text: "Fly only during the TFR's off-hours", correct: false, explanation: '' },
      { text: "TFRs don't apply to recreational drones", correct: false, explanation: '' },
    ],
    correctIndex: 1,
    explanation:
      'TFRs (14 CFR § 91.137) prohibit all aircraft, including drones, from flying in the restricted area for the restricted time — regardless of altitude or pilot type.',
  },
  {
    question: 'Can you launch or land a recreational drone in a U.S. National Park?',
    options: [
      { text: 'Yes, anywhere in the park', correct: false, explanation: '' },
      {
        text: 'No — NPS policy generally prohibits launching, landing, or operating drones in national parks',
        correct: true,
        explanation: '',
      },
      { text: 'Only with a fishing license', correct: false, explanation: '' },
      { text: 'Only on weekends', correct: false, explanation: '' },
    ],
    correctIndex: 1,
    explanation:
      'National Park Service policy (36 CFR § 1.5) generally bans launching, landing, or operating drones from or on lands and waters it administers, unless specifically authorized.',
  },
  {
    question: 'When must a recreational drone pilot report an incident to the FAA?',
    options: [
      { text: 'Never — recreational flyers are exempt from reporting', correct: false, explanation: '' },
      { text: 'Only if the drone is destroyed', correct: false, explanation: '' },
      {
        text: 'If the operation causes serious injury or over $500 in property damage',
        correct: true,
        explanation: '',
      },
      { text: 'Only if requested by local police', correct: false, explanation: '' },
    ],
    correctIndex: 2,
    explanation:
      'Recreational operators must report to the FAA within 10 days if their operation results in serious injury, loss of consciousness, or property damage exceeding $500.',
  },
  {
    question:
      'What system do recreational pilots use to request authorization to fly in controlled airspace near an airport?',
    options: [
      { text: 'LAANC (Low Altitude Authorization and Notification Capability)', correct: true, explanation: '' },
      { text: 'Filing a NOTAM', correct: false, explanation: '' },
      { text: 'A phone call to air traffic control only', correct: false, explanation: '' },
      { text: 'A paper form mailed to the FAA', correct: false, explanation: '' },
    ],
    correctIndex: 0,
    explanation:
      'LAANC gives near-real-time authorization to fly in controlled airspace below approved altitudes, accessed through FAA-approved apps like Aloft or Kittyhawk.',
  },
];
