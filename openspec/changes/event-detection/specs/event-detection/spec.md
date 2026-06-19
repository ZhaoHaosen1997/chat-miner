## ADDED Requirements

### Requirement: Manual event detection trigger
The system SHALL allow users to manually trigger event detection for a group within a specified time range. Detection SHALL NOT run automatically.

#### Scenario: User triggers event detection
- **WHEN** user clicks "开始分析" button on the events page with time range `[2025-03-01, 2025-06-19]`
- **THEN** system creates an async task, returns a `task_id`, and begins Phase 1 (peak detection)

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

### Requirement: Fixed-size message window splitting
The system SHALL split candidate segments into fixed-size message windows for AI analysis. Each window SHALL contain at most N messages (default 200), with adjacent windows overlapping by M messages (default 20).

#### Scenario: Segment fits in one window
- **WHEN** a candidate segment contains 150 messages (below the 200-message window limit)
- **THEN** system SHALL create exactly one window containing all 150 messages plus context padding

#### Scenario: Segment exceeds one window
- **WHEN** a candidate segment contains 450 messages
- **THEN** system SHALL split into windows of [1–200], [181–400], [381–450] with 20-message overlap

#### Scenario: Segment is entire chat history (small group)
- **WHEN** a group's total message count is below the window size (200)
- **THEN** system SHALL create one window covering the entire history

### Requirement: AI event analysis with full conversation context
The system SHALL send each message window to the AI with the full conversation text. The AI SHALL identify 0 or more events within each window. AI analysis SHALL be concurrent with a configurable semaphore limit.

#### Scenario: AI identifies events in a window
- **WHEN** AI receives a 200-message window containing "小明 announces new job" and "AI tool discussion"
- **THEN** AI SHALL return two events with title, description, event_type, participants, key_quotes, and time_span for each

#### Scenario: AI finds no events (idle chat)
- **WHEN** AI receives a window containing only casual small talk without any distinct event
- **THEN** AI SHALL return an empty events array

#### Scenario: Concurrency limited by semaphore
- **WHEN** 7 windows are ready for analysis and the concurrency limit is 3
- **THEN** at most 3 AI calls SHALL run simultaneously; remaining windows SHALL queue and execute as slots free

#### Scenario: AI call fails and retries
- **WHEN** an AI call for a window fails (network error, API error)
- **THEN** system SHALL retry up to the configured retry count before marking that window as failed

### Requirement: Event post-processing and deduplication
The system SHALL merge overlapping events across windows and resolve participant names to member IDs.

#### Scenario: Same event detected in overlapping windows
- **WHEN** window N (msgs 1–200) and window N+1 (msgs 181–400) both detect a "火锅聚会" event with overlapping time ranges
- **THEN** system SHALL merge them into a single event, keeping the longer description and union of participants

#### Scenario: Participant name resolution
- **WHEN** AI returns participant display names like "小明", "老王"
- **THEN** system SHALL resolve them to internal member IDs using the group's member list

### Requirement: Event data storage
The system SHALL store detected events in a new `events` database table with all AI-returned fields plus metadata.

#### Scenario: Events stored after successful analysis
- **WHEN** Phase 3 post-processing completes with 11 merged events
- **THEN** all 11 events SHALL be inserted into the `events` table with group_id, title, description, event_type, participant_ids, key_quotes, start_time, end_time, message_range, and created_at

#### Scenario: Re-analysis replaces old events
- **WHEN** user triggers event detection for a time range that already has stored events
- **THEN** system SHALL delete all existing events within that time range before inserting new ones

### Requirement: Event detection configuration
All event detection parameters SHALL be configurable via `app_settings` and exposed in the advanced settings UI.

#### Scenario: User changes concurrency limit
- **WHEN** user sets AI concurrency to 5 in advanced settings
- **THEN** the next event detection task SHALL use at most 5 concurrent AI calls

#### Scenario: Default configuration values
- **WHEN** no custom configuration is set
- **THEN** system SHALL use defaults: window_size=200, window_overlap=20, ai_concurrency=3, active_group_threshold=30, active_peak_absolute=80, quiet_peak_multiplier=3

### Requirement: Configurable system prompt via prompt_profiles
The system SHALL use the existing `prompt_profiles` mechanism for the event detection system prompt, with `analysis_type` = `event_detection`. The default prompt SHALL match the humorous style of weekly/monthly/annual reports.

#### Scenario: Default prompt used when no profile configured
- **WHEN** no `prompt_profiles` row exists for `analysis_type='event_detection'`
- **THEN** system SHALL use the hardcoded default system prompt with humorous flavor (群聊历史学家+八卦记者+脱口秀段子手风格)

#### Scenario: Custom prompt profile takes effect
- **WHEN** user creates a custom prompt profile for `analysis_type='event_detection'` and sets it as default
- **THEN** all subsequent event detection SHALL use that custom system prompt

#### Scenario: Prompt editable in advanced settings
- **WHEN** user navigates to Settings → 高级设置
- **THEN** the event detection system prompt SHALL appear in the prompt profiles list, editable alongside daily/weekly/monthly/annual prompts
