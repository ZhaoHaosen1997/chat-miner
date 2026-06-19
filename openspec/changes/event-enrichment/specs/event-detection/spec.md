## MODIFIED Requirements

### Requirement: AI event analysis with enriched output
The system SHALL send each event window to the AI requesting an enriched single-event response with narrative, mood, key moments, participant roles, and aftermath. The response SHALL still be a single event object or null.

#### Scenario: AI returns enriched event
- **WHEN** AI receives a window and identifies a complex social event
- **THEN** the response SHALL include: headline, narrative, event_type, participants (with roles), key_quotes, key_moments (with time/description/quote), mood, mood_emoji, aftermath, time_span

#### Scenario: AI returns null (idle chat)
- **WHEN** AI receives a window containing only casual small talk
- **THEN** AI SHALL return null; system SHALL mark the window status as `empty`

### Requirement: Event data storage with report_json
The system SHALL store events with the full AI response JSON in a new `report_json` column, in addition to existing structured columns.

#### Scenario: Event stored with report_json
- **WHEN** AI analysis of window id=5 returns an enriched event
- **THEN** the event SHALL be inserted with: existing structured fields populated, plus `report_json` containing the full serialized AI response

#### Scenario: Old events without report_json
- **WHEN** querying events created before v1.18.2
- **THEN** `report_json` SHALL be empty string; the event detail page SHALL degrade gracefully

### Requirement: Event detection configuration
All event detection parameters SHALL remain configurable. The enriched prompt output format SHALL be determined by the prompt itself, not by a separate configuration toggle.

#### Scenario: Prompt defines output format
- **WHEN** the system prompt instructs AI to return the enriched format
- **THEN** AI SHALL follow that format; no additional configuration is needed

## ADDED Requirements

### Requirement: Enriched system prompt
The default event detection system prompt SHALL instruct the AI to produce narrative, mood, key moments, participant roles, and aftermath in addition to existing fields.

#### Scenario: Default prompt requests enriched output
- **WHEN** no custom prompt profile is configured for event_detection
- **THEN** the hardcoded default prompt SHALL include instructions for all enriched fields with the existing humorous flavor
