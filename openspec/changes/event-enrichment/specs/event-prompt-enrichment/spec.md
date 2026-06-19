## ADDED Requirements

### Requirement: Enriched AI output format
The event analysis AI prompt SHALL request an enriched single-event JSON object with narrative, mood, key moments, participant roles, and aftermath fields.

#### Scenario: Full enriched output
- **WHEN** AI analyzes a message window containing a complex social event
- **THEN** the response SHALL include at minimum: headline, narrative, event_type, participants (with roles), key_quotes, time_span. Optional fields: mood, mood_emoji, key_moments, aftermath.

#### Scenario: Simple event with minimal fields
- **WHEN** AI analyzes a window with a straightforward announcement
- **THEN** the response SHALL include headline, narrative, event_type, participants, key_quotes, time_span. Optional fields may be omitted.

#### Scenario: No event found
- **WHEN** AI determines the conversation is idle chat
- **THEN** the response SHALL be null (unchanged behavior)

### Requirement: report_json storage
The system SHALL store the complete AI response JSON in a new `report_json` TEXT column in the events table.

#### Scenario: Event stored with report_json
- **WHEN** an enriched AI analysis completes
- **THEN** the full AI response JSON SHALL be serialized and stored in `events.report_json`

#### Scenario: Migration for existing DB
- **WHEN** the v1.18.2 migration runs on an existing database
- **THEN** `ALTER TABLE events ADD COLUMN report_json TEXT DEFAULT ''` SHALL execute, and existing rows SHALL have empty report_json

### Requirement: Backward-compatible field mapping
The system SHALL continue to populate existing structured columns (title, description, event_type, participant_ids, key_quotes, start_time, end_time) from the enriched response.

#### Scenario: Structured fields populated from enriched response
- **WHEN** AI returns enriched format with headline and participants array
- **THEN** events.title SHALL be set to headline, events.description to narrative[:200], events.event_type to event_type, events.participant_ids to resolved participant IDs, events.key_quotes to JSON array of key_quotes strings

### Requirement: Prompt preserves humorous style
The enriched prompt SHALL retain the existing humorous flavor (群聊历史学家+八卦记者+脱口秀段子手风格) while requesting the additional fields.

#### Scenario: Prompt tone
- **WHEN** the system prompt is built for event analysis
- **THEN** it SHALL instruct the AI to write narrative in a lively, humorous style matching the existing event detection prompt tone
