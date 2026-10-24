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
];
