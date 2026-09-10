# Strategy pages — from a listing to the parcel

Five self-contained HTML pages. Open them in a browser; they need no server and
load nothing but Google Fonts. The German is deliberate: these are pages the
user reads, so they follow the interface language rule.

Every number in them was measured on 2026-09-01 against one real listing
(Kleinanzeigen 3499632623, a 502 m² plot in Großbothen). The measurements and
their caveats are written up in `../research/flurstueck-identifikation.md`.

| Page | What it settles |
|---|---|
| `fall-grossbothen.html` | The case itself: the pin is 6 235 m off, and four different routes through the same listing, three maps drawn from live ALKIS geometry. |
| `extraktion-prompting.html` | The escalation ladder from HTML attribute to OCR to language model, three ready prompts, and the two traps that break the cheap paths. |
| `suche-triangulation.html` | Filters ranked by discriminating power per cost, the soft trapezoid scoring, and a workbench that re-ranks the 25 real candidates live. |
| `ui-indizienkarte.html` | The interface draft: indicia appear on the map as they arrive, the camera follows the live candidate set rather than the newest finding, opacity encodes confidence. |
| `suchalgorithmus.html` | The search itself in six phases, each with its cost and its abort condition: the tolerance staircase, the confirmation rung, and the OCR ladder. |
| `inserat-pipeline.html` | The plan: every value read today and what it is allowed to decide, the six places the run breaks, an agenda of hypotheses in place of the fixed staircase, nineteen values worth extracting, and the model as a channel behind a citation gate. |

The pages are also published as artifacts:

* Fall Großbothen — https://claude.ai/code/artifact/47bd2a0f-88fa-499c-9bd2-8f63aea7b55d
* Indizien aus dem Inserat — https://claude.ai/code/artifact/2b875b5b-3049-497a-82b1-831d2f7137f2
* Kandidaten einkreisen — https://claude.ai/code/artifact/9f48ff2a-8710-4a2d-a0f9-1f0c88d8e059
* Die Indizienkarte — https://claude.ai/code/artifact/011946dd-fc87-4041-a3c5-2cff3fa03871
* Der Suchlauf — https://claude.ai/code/artifact/5792cc07-9ac0-41ea-83f7-578f50f886f2

Nothing here is implemented yet. The pages name where each piece would sit —
`SucheView.vue`, `IndizienKarte.vue`, `POST /api/parcels/search` — but no code
has been written against them.
