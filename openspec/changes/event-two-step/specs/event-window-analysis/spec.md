## ADDED Requirements

### Requirement: Independent per-window AI analysis endpoint
The system SHALL provide a dedicated endpoint to analyze a single event window with AI, independent of the detection phase.

#### Scenario: Analyze a pending window
- **WHEN** user clicks "分析" on a window with status `pending`
- **THEN** system SHALL call AI with the window's messages, parse the response as a single event object or null, insert the event if found, and update the window status to `analyzed` or `empty`

#### Scenario: AI returns a valid event
- **WHEN** AI receives a window's conversation and identifies an event
- **THEN** AI SHALL return a single JSON object with fields: title, description, event_type, participants, key_quotes, time_span {start, end}

#### Scenario: AI returns null (no event)
- **WHEN** AI receives a window's conversation and determines it is idle chat without a distinct event
- **THEN** AI SHALL return null or an empty object; system SHALL mark the window status as `empty`

#### Scenario: AI call fails
- **WHEN** an AI call for a window fails due to network error or API error
- **THEN** system SHALL return an error response, leave the window status unchanged (`pending`), and allow retry

### Requirement: Serial queue analysis for "analyze all"
The system SHALL process windows sequentially (one at a time) when the "一键分析" action is triggered.

#### Scenario: Analyze all pending windows serially
- **WHEN** user clicks "一键分析" and there are 5 pending windows
- **THEN** system SHALL analyze windows one at a time in chronological order, with each window's result persisted before the next begins

#### Scenario: Queue stops on cancellation
- **WHEN** user cancels the analyze-all operation after 3 of 5 windows
- **THEN** the first 3 windows SHALL retain their analysis results; the remaining 2 SHALL stay as `pending`

#### Scenario: Queue continues past failures
- **WHEN** window N fails analysis (AI error)
- **THEN** window N+1 SHALL still be processed; the failed window SHALL remain `pending` for later retry

### Requirement: Single event output format
The AI prompt for window analysis SHALL request exactly one event or null, not an array.

#### Scenario: Prompt requests single event
- **WHEN** the AI prompt is built for a window
- **THEN** the instruction SHALL ask the AI: "判断这段对话是否构成一个值得记录的事件。如果是，返回事件详情 JSON 对象；如果不是（日常闲聊），返回 null"

#### Scenario: Response parsing handles single object
- **WHEN** AI returns `{"title": "...", "event_type": "...", ...}`
- **THEN** system SHALL parse it as a single event and insert it
- **WHEN** AI returns `null` or empty
- **THEN** system SHALL treat it as "no event found"

#### Scenario: Backward compatibility with array response
- **WHEN** AI mistakenly returns `{"events": [...]}` (old format)
- **THEN** system SHALL extract the first event from the array if present, or treat as empty if array is empty

### Requirement: Per-window data safety
The system SHALL only delete events associated with a specific window when re-analyzing that window, never delete events globally for a time range.

#### Scenario: Re-analyze single window
- **WHEN** user re-analyzes window id=3 that previously produced event id=42
- **THEN** system SHALL delete event id=42, reset window status to `pending`, then run new analysis

#### Scenario: Initial detection does not delete existing events
- **WHEN** Phase 1 detection runs and creates new windows
- **THEN** no existing events SHALL be deleted; new analysis results SHALL coexist with old events

### Requirement: Event-to-window association
Each event inserted SHALL be linked to its source window via the `window_id` field in the events table.

#### Scenario: Event stores window reference
- **WHEN** an event is created from window id=5
- **THEN** the event's `window_id` column SHALL be set to 5

#### Scenario: Window stores event reference
- **WHEN** a window is analyzed and produces event id=99
- **THEN** the window's `event_id` column SHALL be set to 99
