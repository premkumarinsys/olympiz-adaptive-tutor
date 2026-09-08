# Open tutor design QA

Source visual truth: references/selected-design.png (1487 x 1058).
Implementation: references/chat-desktop-qa.jpg; Chrome /chat at 1487 x 1058 CSS px, DPR 1.
Mobile: Chrome capture at 390 x 844 CSS px, DPR 1; document scrollWidth equals viewport width.

This is the requested open-conversation extension of the selected lesson workspace. The source depicts a multiple-choice lesson; the implementation depicts conversation after a graded exercise. Different content and activity names are intentional. Layout and design language are compared, rather than claiming pixel identity between these states.

## Comparison and findings
The source and rendered desktop screenshots were opened together in one comparison input. Both retain the compact header, narrow left memory/goal rail, four-stage path, primary learning area and bottom session band. Sand surfaces, green actions, cobalt links and restrained borders are maintained. The composer replaces the original lesson answer controls for the new user-requested flow.

- Typography: existing app font stack retained; readable hierarchy, bold message emphasis, paragraphs and lists render without raw Markdown.
- Spacing: 290px desktop rail approximates the source 297px rail; conversation, fixed composer and bottom band remain separate. Long messages scroll within the desktop conversation.
- Colors: existing forest/sand palette; no unnecessary coral on ordinary conversation.
- Assets: existing Phosphor icons; no fabricated illustration or raster placeholders. The chat does not require the original lesson diagram.
- Copy: fixed shared lesson explained clearly; learner support uses student-facing terms; actual memory and graded feedback appear in the interface.

## Iteration history
1. Initial desktop capture showed raw policy modifier names. Replaced with student-facing support phrases; later comparison confirms readable labels.
2. Live response exposed raw Markdown and stale retry advice after a corrected answer. Added safe React paragraph/list/bold rendering and scoped retry advice to active unanswered exercises. Post-fix desktop and mobile captures confirm readable messages and historical feedback.
3. Post-fix comparison: no remaining actionable P0/P1/P2 visual findings. Focused message typography and rail text were legible in the full-resolution captures; mobile message region was separately inspected.

## Interactions and checks
- Open question sent to configured live provider and actual reply rendered.
- Practice, hint disclosure, ungradable input retry and correct-answer feedback tested.
- Memory version advanced from 10 to 11 after a checked answer; questions did not grade.
- Switched to Meera: independent challenge support and isolated history; shared lesson remained the same.
- Preparation and revision produced appropriate follow-up content.
- Desktop reload restored Kabir conversation.
- Mobile has no horizontal overflow; document scroll makes all sections reachable.
- Browser console checked: no errors or warnings.
- Build, four Sites packaging tests, 22 backend unit tests and golden policy evaluation passed.

## Follow-up polish
P3: Mobile uses normal document scrolling; a jump-to-composer action could shorten navigation in long conversations.

final result: passed
