## MODIFIED Requirements

### Requirement: Manual event detection trigger
The system SHALL allow users to manually trigger event detection for a group within a specified time range. Detection SHALL NOT run automatically. Detection SHALL now only execute Phase 1 (Python peak detection + adaptive segmentation); AI analysis is a separate step.

#### Scenario: User triggers event detection
- **WHEN** user clicks "开始分析" button on the events page with time range `[2025-03-01, 2025-06-19]`
- **THEN** system SHALL run Python-only Phase 1 detection (peak detection + adaptive segmentation), persist event windows to DB, and return `{windows: [...], count: N}` (no longer returns a task_id for a combined detection+analysis task)

#### Scenario: No time range specified
- **WHEN** user clicks "开始分析" without specifying a date range
- **THEN** system SHALL default to the group's full message history range

#### Scenario: Detection already in progress
- **WHEN** user clicks "开始分析" while a detection task is already running for the same group
- **THEN** system SHALL return HTTP 409 with message "该群已有正在执行的事件分析任务"

### Requirement: Message volume peak detection
The system SHALL scan message volume by hour to identify candidate event windows. Detection parameters SHALL differ between active and quiet groups.

#### Scenario: Quiet group peak detection
- **WHEN** a group's average hourly message count is below the active-group threshold
- **THEN** system SHALL flag any hour where message count exceeds 3× the group's daily average hourly volume as a candidate peak

#### Scenario: Active group peak detection
- **WHEN** a group's average hourly message count meets or exceeds the active-group threshold
- **THEN** system SHALL flag any 30-minute window where message count exceeds the absolute peak threshold (default 80) as a candidate peak

#### Scenario: Adjacent peaks merged
- **WHEN** two candidate peaks are within 2 hours of each other
- **THEN** system SHALL merge them into a single candidate segment covering the full time span plus padding

### Requirement: AI event analysis with full conversation context
The system SHALL send each event window to the AI with the full conversation text. The AI SHALL judge whether the conversation constitutes a single noteworthy event. AI analysis SHALL run sequentially (one at a time) via a dedicated endpoint, NOT as part of the detection task.

#### Scenario: AI identifies an event in a window
- **WHEN** AI receives a window containing "小明 announces new job, everyone cheers and decides to celebrate Friday"
- **THEN** AI SHALL return a single event object with title, description, event_type, participants, key_quotes, and time_span

#### Scenario: AI finds no event (idle chat)
- **WHEN** AI receives a window containing only casual small talk without any distinct event
- **THEN** AI SHALL return null; system SHALL mark the window status as `empty`

#### Scenario: Sequential processing
- **WHEN** "一键分析" processes 5 pending windows
- **THEN** windows SHALL be analyzed one at a time in chronological order; window N+1 analysis SHALL NOT begin until window N's result is persisted

#### Scenario: AI call fails on a window
- **WHEN** an AI call for a window fails (network error, API error)
- **THEN** system SHALL leave the window status as `pending` for later retry and continue to the next window

### Requirement: Event post-processing and participant name resolution
The system SHALL resolve AI-returned participant names to member IDs upon event insertion.

#### Scenario: Participant name resolution
- **WHEN** AI returns participant display names like "小明", "老王"
- **THEN** system SHALL resolve them to internal member IDs using the group's member list

### Requirement: Event data storage
The system SHALL store detected events in the `events` database table. Each event SHALL be linked to its source window via `window_id`.

#### Scenario: Event stored after successful window analysis
- **WHEN** AI analysis of window id=5 returns a valid event
- **THEN** the event SHALL be inserted into `events` with group_id, title, description, event_type, participant_ids, key_quotes, start_time, end_time, message_count, window_id=5, and created_at

#### Scenario: Re-analysis of a single window replaces only that window's event
- **WHEN** user re-analyzes window id=5 that previously produced event id=42
- **THEN** event id=42 SHALL be deleted before the new analysis runs; events from other windows SHALL NOT be affected

### Requirement: Event detection configuration
All event detection parameters SHALL be configurable via `app_settings` and exposed in the advanced settings UI.

#### Scenario: User changes min gap threshold
- **WHEN** user sets `EVENT_MIN_GAP_MINUTES` to 20 in advanced settings
- **THEN** the next Phase 1 detection SHALL use 20 minutes as the minimum gap for segmentation boundaries

#### Scenario: Default configuration values
- **WHEN** no custom configuration is set
- **THEN** system SHALL use defaults: event_min_gap_minutes=15, event_min_group_size=10, event_max_group_size=500, active_group_threshold=30, active_peak_absolute=80, quiet_peak_multiplier=3

## REMOVED Requirements

### Requirement: Fixed-size message window splitting
**Reason**: Replaced by adaptive time-gap segmentation (see `adaptive-segmentation` spec). Fixed 200-message windows ignored natural conversation boundaries, causing events to be split across windows or unrelated messages to be grouped together.
**Migration**: Config keys `EVENT_WINDOW_SIZE` and `EVENT_WINDOW_OVERLAP` are deprecated. Existing detection runs automatically use the new adaptive segmentation with default parameters.
