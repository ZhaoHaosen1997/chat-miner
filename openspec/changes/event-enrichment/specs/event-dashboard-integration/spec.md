## ADDED Requirements

### Requirement: Dashboard events section placement
The Dashboard SHALL display an events section between the calendar heatmap and the weekly reports section.

#### Scenario: Events section visible below calendar
- **WHEN** Dashboard loads with a group that has events or event windows
- **THEN** an "事件时间轴" section SHALL appear below the calendar heatmap and above the weekly reports list

#### Scenario: No events and no windows
- **WHEN** the group has zero events and zero event windows
- **THEN** the events section SHALL still appear with a "扫描新事件" prompt

### Requirement: Latest event Hero card
The Dashboard SHALL display a Hero card for the most recent analyzed event.

#### Scenario: Latest event preview
- **WHEN** at least one analyzed event exists
- **THEN** a Hero card SHALL display: event type icon, headline, date, message count, participant count, duration. Clicking navigates to `/event/:eventId`.

### Requirement: Monthly grouped event list
The Dashboard events section SHALL list events grouped by month, with expand/collapse toggles, defaulting to show only the latest month.

#### Scenario: Multiple months of events
- **WHEN** events span 2025-03 and 2025-02
- **THEN** March SHALL be expanded by default showing its events; February SHALL be collapsed

#### Scenario: Click event item
- **WHEN** user clicks an analyzed event item in the list
- **THEN** system SHALL navigate to `/event/:eventId`

### Requirement: Candidate window quick-analyze
The Dashboard events section SHALL list unanalyzed candidate windows alongside analyzed events, with an inline analyze trigger.

#### Scenario: Click candidate window
- **WHEN** user clicks a candidate (pending) window item
- **THEN** system SHALL call `POST /windows/{id}/analyze`, display a loading state, and upon completion navigate to `/event/:newEventId`

#### Scenario: Analyze fails
- **WHEN** the analyze call fails
- **THEN** the window item SHALL revert to its clickable state with an error indicator

### Requirement: Scan trigger button
The Dashboard events section SHALL include a "扫描新事件" button that triggers Phase 1 detection.

#### Scenario: Click scan button
- **WHEN** user clicks "扫描新事件"
- **THEN** system SHALL call `POST /events/detect`, briefly show a scanning state, and refresh the events section with new windows

### Requirement: Design consistency with existing sections
The events section SHALL use the same visual language as the weekly/monthly report sections (card container, section header with icon, list items with hover states).

#### Scenario: Visual consistency
- **WHEN** user views the Dashboard
- **THEN** the events section SHALL visually match the weekly/monthly sections in card styling, typography, and spacing
