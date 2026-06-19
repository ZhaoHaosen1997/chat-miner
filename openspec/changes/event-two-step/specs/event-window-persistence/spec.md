## ADDED Requirements

### Requirement: Event window database table
The system SHALL persist event detection results in a new `event_windows` table with status tracking.

#### Scenario: Table schema
- **WHEN** database migration runs
- **THEN** `event_windows` table SHALL be created with columns: id (INTEGER PRIMARY KEY AUTOINCREMENT), group_id (INTEGER NOT NULL), start_time (TEXT NOT NULL), end_time (TEXT NOT NULL), message_count (INTEGER DEFAULT 0), status (TEXT DEFAULT 'pending' CHECK IN ('pending','analyzing','analyzed','empty')), event_count (INTEGER DEFAULT 0), summary_json (TEXT DEFAULT '{}'), event_id (INTEGER), created_at (TEXT), analyzed_at (TEXT), FOREIGN KEY group_id→chat_groups(id)

#### Scenario: Indexes for query performance
- **WHEN** event_windows table is created
- **THEN** indexes SHALL be created on (group_id, start_time) and (group_id, status)

### Requirement: Window CRUD operations
The system SHALL provide database functions to create, read, update, and delete event windows.

#### Scenario: Batch insert windows
- **WHEN** Phase 1 detection produces 8 event windows
- **THEN** `insert_windows(windows, group_id)` SHALL insert all 8 windows and return their IDs

#### Scenario: Get windows for a group
- **WHEN** frontend requests windows for a group
- **THEN** `get_windows(group_id, status_filter)` SHALL return windows ordered by start_time DESC, optionally filtered by status

#### Scenario: Update window status after analysis
- **WHEN** AI analysis completes for window id=5 and finds 1 event
- **THEN** `update_window_status(5, 'analyzed', event_count=1, event_id=...)` SHALL update the window's status, event_count, and analyzed_at timestamp

#### Scenario: Delete windows for a group
- **WHEN** a group is deleted
- **THEN** all windows for that group SHALL be cascade-deleted

### Requirement: Window status state machine
The system SHALL enforce a valid status transition flow for event windows.

#### Scenario: Valid status transitions
- **WHEN** a window is created
- **THEN** its initial status SHALL be `pending`
- **WHEN** analysis begins for a pending window
- **THEN** its status SHALL transition to `analyzing`
- **WHEN** analysis completes and events are found
- **THEN** its status SHALL transition to `analyzed`
- **WHEN** analysis completes but no events found
- **THEN** its status SHALL transition to `empty`

#### Scenario: Prevent re-analysis of in-progress window
- **WHEN** a request arrives to analyze a window with status `analyzing`
- **THEN** the system SHALL return HTTP 409 with message "该事件组正在分析中"

#### Scenario: Allow re-analysis of completed window
- **WHEN** user clicks "重新分析" on a window with status `analyzed`
- **THEN** the system SHALL delete the previously associated event(s), reset status to `pending`, and re-run analysis

### Requirement: Window summary JSON
The system SHALL store a Python-extracted summary for each window in the `summary_json` field.

#### Scenario: Summary structure
- **WHEN** a window is created from Phase 1 detection
- **THEN** `summary_json` SHALL contain: time_start, time_end, duration_minutes, message_count, text_message_count, top_speakers [{name, count}], preview [{time, sender, content}], hourly_distribution {hour: count}
