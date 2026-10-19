# Definition: "Digitalisation"

**Author:** partner (Swiss-politics research, team member). **Method:** derived from how PolitMonitor actually tagged the 3,433 affairs in `politmonitor_digitalisierung.csv` (AI-assisted analysis by the partner, reviewed by the partner), not from the challenge slides. Where the slides and PolitMonitor differ, this definition follows PolitMonitor, because PolitMonitor is the ground truth we are measured against.

**Known difference from the slides:** PolitMonitor counts Swiss Post, SRG and the radio/TV licence fee as digitalisation, although the slides list them as "not digital". We follow PolitMonitor.

## Definition

An affair is about digitalisation if it deals with digital technology, data or telecommunications, or with their effects on government, the economy, education, media or society. This includes their use, regulation, infrastructure, security and social consequences. The digital aspect does not have to be the only topic, but it must be a central part of the affair, not a passing mention.

PolitMonitor uses a broad definition. It includes telecom infrastructure, media and public broadcasting, and the Swiss Post where services move online or are affected by digitalisation.

## Borderline cases (decided as PolitMonitor did)

Counts are approximate, from the partner's AI-assisted analysis of the list; they are supporting evidence, not reported results.

| Case | Decision | Evidence from the list |
|---|---|---|
| Cybersecurity, cybercrime | Yes | ~150 affairs |
| Artificial intelligence, deepfakes, algorithms | Yes | ~170 affairs |
| Data protection (incl. general data protection law, data protection officer) | Yes | ~145 affairs |
| E-voting | Yes | 57 affairs |
| E-ID | Yes | 30 affairs |
| E-government, digital administration, open data | Yes | ~50 affairs |
| Mobile networks, 5G, broadband, fibre (incl. antenna permits, 5G health concerns) | Yes | ~115 affairs |
| Digital education (devices, digital teaching material, computer science, smartphone bans) | Yes | ~120 affairs |
| Digital health (electronic patient record, health data) | Yes | frequent |
| Media and public broadcasting (SRG, radio/TV licence fee, online platforms, online hate speech) | Yes | ~58 SRG/radio/TV affairs |
| Swiss Post (digital services, e-voting by Post, parcel deals with platforms, home service changes) | Yes | 37 affairs |
| Energy use of data centres and AI | Yes | ~12 affairs |
| Energy, solar or economy in general, no digital link | No | only rare noise |
| Education, labour or budget in general, no digital link | No | only rare noise |

**Rule for unclear cases:** If digital technology, data or telecom is a central part of what the affair asks or regulates → Yes. If it is only mentioned in passing → No.

## Note for the evaluation

About one third of the tagged affairs (~1,100) have no digital keyword in the title. Most are still digital in the full text, but some look like tagging noise (e.g. "Archivgesetz", "Geschäftsbericht 2018").

Disagreements go to blind review by a team member **in both directions** (model yes / PolitMonitor no, and model no / PolitMonitor yes). The reviewer sees only the affair text, never which side said what. The review rules are fixed before results are seen, and metrics are reported before and after review.
