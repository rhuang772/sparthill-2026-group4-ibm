# sparthill-2026-group4-ibm

## Inspiration

Video demo link:
[link](https://drive.google.com/file/d/1DHqV3_5GdISXVMiOeBo7ZNXoYr3fH7wz/view?usp=sharing)

SkyBrief is a pre-flight coach for beginner drone pilots. Before
takeoff, it gives one **Go / Caution / No-Go** verdict for a chosen location and time, explains why in plain language, and teaches the rule behind it.

It combines legality (airspace, restrictions, and altitude) with
real-world conditions (wind, light, visibility, signal interference,
water, and crowds) into one decision. It works offline in the field and keeps the pilot's data on their phone.

Beginner pilots often don't know whether a spot is legal or safe until something goes wrong. They may unknowingly fly into controlled airspace, over crowds, at dusk, or in strong wind.

This matters beyond the pilot: drones near airports, stadiums, and wildfires can create public-safety hazards, and incidents can lead to stricter rules and park bans for the broader hobby community.

### Why this is difficult today

-   Information is scattered across airspace apps, weather apps, and FAA
    pages.
-   Cell service may be unavailable at the actual flying location.
-   Beginners may not understand which rules apply to their
    certification status and drone weight.

**Target users:** Beginner recreational drone pilots. Commercial
operators are out of scope for the MVP.

**Pilot inputs:** Certification status, drone weight, and a flight plan
(location, time, and planned altitude). SkyBrief does not collect drone
flight data or black-box logs.

## What it does
The workflow is **plan online, fly offline**: the pilot prepares a
briefing while connected, then uses it in the field.

1.  **Set up a profile.** The pilot enters certification status, drone
    weight, and experience level. The profile is stored on the phone; no
    login or account is required.
2.  **Plan the flight.** Choose a location, time, and planned altitude.
3.  **Check the plan.** A rules engine evaluates airspace data, rules
    associated with certification and drone weight, weather, sunset, and
    terrain hazards. It returns a Go / Caution / No-Go verdict, with a
    reason and source for each factor.
4.  **Generate an AI briefing.** AI explains the verdict in plain
    language, weighs risks together, suggests a safer nearby spot when
    appropriate, and teaches a "rule of the flight." Pilots can also ask
    questions about their planned flight.
5.  **Save for offline use.** The briefing, weather, and timestamp are
    stored on the phone.
6.  **Use it at the flying spot.** The saved briefing opens without
    signal. The phone re-checks GPS position and time against sunset and
    labels the age of each data point. If restriction or weather data is
    too old, the verdict drops to Caution.
7.  **Take a quick quiz.** Three questions check whether the pilot
    learned the rules presented in the briefing.

**Offline limitation:** The AI model runs in the cloud and does not run
offline. Offline functionality comes from the saved briefing and
on-device checks, including GPS, sunset calculations, and cached rules.

## How we built it
We used React for the frontend. FastAPI connects the frontend, application logic and AI components. The OpenAI API powers the agent that generates personalized explanations. ChromaDB retrieves relevant context from reference material. 

## Challenges we ran into

1. UI/UX Implementation - One challenge we ran into was theming the landing page without a real dark/light system to build on. Our UI components were all originally styled once, against a single light background. That worked fine until we wanted a deliberate visual hierarchy down the page: a dark hero, a dark-gray capabilities section, a light-gray profile form. Flipping a section's background wasn't just a color swap, but every child element had been hardcoded for the opposite contrast direction, so near-black text on a newly dark section would just vanish. 

2. Git Branch Conflicts - Another challenge we ran into was managing Git branches while multiple members worked on different parts of the web. When merging changes, we ran into conflicts because some files had been modified or moved. Communication and reviewing the conflicting files resolved the issue, but it took time away spending most of the time. debugging. 

3. Datasets - One of our biggest challenges was finding free, reliable datasets and APIs that provided all the information needed for a complete flight-safety assessment. Sometimes, no single API covered every factor, so we had to combine multiple APIs to gather the necessary data. Integrating these sources introduced additional complexity, including handling different data formats, reconciling information, and managing API limitations. Beyond the hackathon, we would need to improve data reliability, verify that information stays up to date, and expand coverage while keeping costs manageable.

## What's next for SkyBrief
For future work, we plan to explore integrating real-time data from drone sensors-such as battery status, wind measurements and other flight telemetry into the agent's risk assessment. This could allow SkyBrief to provide more context-aware assessments. We would also like to refine and add more datasets to provide more accurate results for the pilots.
