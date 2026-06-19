## ADDED Requirements

### Requirement: Event level in report category switch
The keyboard navigation (W/↑ and S/↓) in Layout SHALL include an event detail level between daily and weekly reports.

#### Scenario: Switch from daily to event
- **WHEN** user presses W or ↑ on a daily report page `/report/2025-03-15`
- **THEN** system SHALL attempt to navigate to an event on that date, falling back to the weekly report if no event exists

#### Scenario: Switch from event to daily
- **WHEN** user presses S or ↓ on an event detail page `/event/42`
- **THEN** system SHALL navigate to the daily report for the event's date

#### Scenario: Switch from event to weekly
- **WHEN** user presses W or ↑ on an event detail page `/event/42`
- **THEN** system SHALL navigate to the weekly report covering the event's date

#### Scenario: Switch from weekly to event
- **WHEN** user presses S or ↓ on a weekly report page `/weekly/2025-W12`
- **THEN** system SHALL attempt to navigate to the most recent event within that week, falling back to the Monday daily report if no event exists

### Requirement: Left/right event navigation via FloatingNav
The event detail page SHALL integrate FloatingNav for ← → (A/D) navigation between events in chronological order within the same group.

#### Scenario: Navigate to previous event
- **WHEN** user presses ← or A on `/event/42`
- **THEN** system SHALL navigate to the chronologically previous event (or wrap to the latest if at the earliest)

#### Scenario: Navigate to next event
- **WHEN** user presses → or D on `/event/42`
- **THEN** system SHALL navigate to the chronologically next event (or wrap to the earliest if at the latest)

#### Scenario: Single event only
- **WHEN** a group has exactly one event
- **THEN** FloatingNav SHALL not render prev/next buttons
