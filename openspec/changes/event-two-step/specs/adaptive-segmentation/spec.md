## ADDED Requirements

### Requirement: Time-gap based adaptive segmentation
The system SHALL replace fixed-size message window splitting with adaptive segmentation based on inter-message time gaps. One segment SHALL represent one natural conversation burst intended as one candidate event.

#### Scenario: Peak period segmented at natural conversation boundaries
- **WHEN** a peak period spans 14:00-18:00 with 850 messages, and there is a 35-minute gap at 15:30 and a 45-minute gap at 16:40
- **THEN** system SHALL split the period into segments at those gap boundaries, producing 3 event windows

#### Scenario: No significant gaps in dense conversation
- **WHEN** a peak period has 200 messages with all inter-message gaps under 10 minutes
- **THEN** system SHALL produce exactly one event window covering the entire peak period

#### Scenario: Minimum gap threshold
- **WHEN** calculating gap thresholds for segmentation
- **THEN** the minimum gap considered a boundary SHALL be the greater of: 15 minutes absolute, or 1.5× the 75th percentile gap within the peak period (capped at 60 minutes)

### Requirement: Event group size constraints
The system SHALL enforce minimum and maximum message counts for event windows to ensure meaningful AI analysis context.

#### Scenario: Segment too small merged with neighbor
- **WHEN** a segment contains fewer than 10 messages
- **THEN** the segment SHALL be merged into the adjacent segment with the smaller boundary gap

#### Scenario: Segment too large further split
- **WHEN** a segment contains more than 500 messages
- **THEN** system SHALL attempt a secondary split at the next-largest gap within the segment that produces two groups of at least 50 messages each

#### Scenario: Small group with few messages
- **WHEN** a group's total message count in a peak period is between 10 and 500
- **THEN** system SHALL produce exactly one event window

### Requirement: Python-extracted event group summary
The system SHALL extract a structured summary for each event window using Python-only computation, without AI calls.

#### Scenario: Summary includes key metadata
- **WHEN** an event window of 185 messages is created
- **THEN** the summary SHALL include: time_range (start~end), duration_minutes, message_count, text_message_count, top_speakers (top 5 by message count), preview (first 3-5 messages with sender and content preview), hourly_distribution, and trigger_message (first message in the window)

#### Scenario: Summary stored with window
- **WHEN** a window is persisted to the database
- **THEN** the summary SHALL be stored as JSON in the `summary_json` column

### Requirement: Peak detection parameters preserved
The system SHALL preserve the existing Phase 1 peak detection logic (hourly counting, active/quiet group classification, peak merging) and only replace the final splitting step.

#### Scenario: Existing peak detection still works
- **WHEN** event detection runs for an active group with hourly counts [120, 140, 30, 25, 90, 100]
- **THEN** hours with count >= active_threshold SHALL be flagged as peaks, adjacent peaks within 2 hours SHALL be merged, and the merged segments SHALL be passed to adaptive segmentation

#### Scenario: Quiet group detection still works
- **WHEN** event detection runs for a quiet group with average hourly count 5
- **THEN** hours exceeding 3× the average SHALL be flagged as peaks

### Requirement: Deprecated configuration
The system SHALL deprecate `EVENT_WINDOW_SIZE` and `EVENT_WINDOW_OVERLAP` configuration keys in favor of new adaptive segmentation parameters.

#### Scenario: New config keys
- **WHEN** the system starts with default configuration
- **THEN** the following config keys SHALL take effect: `EVENT_MIN_GAP_MINUTES` (default 15), `EVENT_MIN_GROUP_SIZE` (default 10), `EVENT_MAX_GROUP_SIZE` (default 500)

#### Scenario: Old config keys ignored
- **WHEN** `EVENT_WINDOW_SIZE` is set to 200 in app_settings
- **THEN** the adaptive segmentation SHALL ignore this value and use the new config keys instead
