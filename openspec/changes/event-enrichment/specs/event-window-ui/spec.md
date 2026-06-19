## MODIFIED Requirements

### Requirement: Event window list display
The frontend SHALL display detected event windows within the Dashboard events section, no longer on a standalone events page. Windows and analyzed events SHALL coexist in the same monthly-grouped list.

#### Scenario: Windows and events in same list
- **WHEN** detection produces windows and some are analyzed
- **THEN** both pending windows and analyzed events SHALL appear in the Dashboard events list, grouped by month, with visual distinction (pending badge vs analyzed title)

#### Scenario: Window card shows summary
- **WHEN** a pending window exists with summary data
- **THEN** the list item SHALL display: time range, message count, top 3 speakers, and an inline "分析" action link

### Requirement: Per-window analyze with redirect
Clicking a candidate window SHALL trigger analysis and redirect to the event detail page upon completion.

#### Scenario: Click candidate window
- **WHEN** user clicks a pending window item in the Dashboard events list
- **THEN** system SHALL call `POST /windows/{id}/analyze`, show a loading state, and upon success navigate to `/event/:newEventId`

## REMOVED Requirements

### Requirement: One-click analyze all button
**Reason**: "一键分析" batch operation is removed from the Dashboard integration — the Dashboard events section focuses on browsing and individual interaction. Batch analysis remains available as a backend API endpoint for future re-integration if needed.
**Migration**: Users can still trigger analysis individually per window. The `POST /windows/analyze-all` endpoint is preserved.

### Requirement: Window card with per-window analyze button (EventWindowCard.vue)
**Reason**: The standalone EventWindowCard component is replaced by inline list items in the Dashboard events section, matching the weekly/monthly report list style.
**Migration**: EventWindowCard.vue is removed. Its functionality is merged into the Dashboard events list.
