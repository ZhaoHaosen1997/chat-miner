## ADDED Requirements

### Requirement: Event detail page route
The system SHALL provide a dedicated route `/event/:eventId` for viewing enriched event details.

#### Scenario: Navigate to event detail from dashboard
- **WHEN** user clicks an event item in the dashboard events section
- **THEN** system SHALL navigate to `/event/:eventId` and render the event detail page

#### Scenario: Event not found
- **WHEN** user navigates to `/event/99999` for a non-existent event
- **THEN** system SHALL display an error state "事件不存在" with a back button

### Requirement: Type-adaptive Hero Banner
The event detail page SHALL render a full-width Hero Banner with gradient background adapted to the event type.

#### Scenario: Decision event Hero
- **WHEN** an event with type "decision" is loaded
- **THEN** the Hero SHALL use amber-gold gradient (`#DC2626→#F59E0B`) with headline, time range, and statistics bar

#### Scenario: Meme event Hero
- **WHEN** an event with type "meme" is loaded
- **THEN** the Hero SHALL use purple-gold gradient (`#9333EA→#FBBF24`)

### Requirement: Narrative and role cards layout
The system SHALL render the AI narrative and participant roles in a two-column layout below the Hero.

#### Scenario: Narrative with participant roles
- **WHEN** an event has narrative text and participant roles
- **THEN** the left column SHALL display the narrative in prose, and the right column SHALL display role badges (主角/催化剂/和事佬)

### Requirement: Key moments timeline
The system SHALL render key moments as a vertical timeline with timestamps and quotes.

#### Scenario: Event has 3 key moments
- **WHEN** the event's key_moments array has 3 entries
- **THEN** each moment SHALL display as: time dot, description, and optional quote in italic

### Requirement: Memorable quotes section
The system SHALL render key quotes in a visually distinct quotation style.

#### Scenario: Event has key quotes
- **WHEN** the event has key_quotes
- **THEN** quotes SHALL display with a left border accent bar, italic text, and attribution line

### Requirement: Floating navigation between events
The event detail page SHALL support left/right navigation to adjacent events via FloatingNav component.

#### Scenario: Press right arrow to next event
- **WHEN** user presses → or D key on an event detail page
- **THEN** system SHALL navigate to the next event (chronologically later, or wrap around)

#### Scenario: No adjacent events
- **WHEN** there is only one event (no adjacent events)
- **THEN** FloatingNav buttons SHALL be hidden

### Requirement: Backward compatibility for old events
The event detail page SHALL degrade gracefully for events without report_json.

#### Scenario: Old event without report_json
- **WHEN** an event has empty report_json but has description and key_quotes
- **THEN** the page SHALL render description in the narrative area, key_quotes in the quotes area, and hide the timeline section
