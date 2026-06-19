## ADDED Requirements

### Requirement: Event timeline page
The system SHALL provide a new frontend route `/events` that displays a chronological event timeline for the current group.

#### Scenario: User navigates to events page
- **WHEN** user clicks "事件" in the navigation bar
- **THEN** system SHALL navigate to `/events` and display the event timeline page

#### Scenario: Events grouped by month
- **WHEN** events span multiple months (e.g., March and April 2025)
- **THEN** events SHALL be displayed grouped under month headers in reverse chronological order (newest month first)

#### Scenario: Event card display
- **WHEN** an event exists with title "小明宣布拿到字节offer", type "social", description, participants, and key quotes
- **THEN** the event card SHALL show: event type icon, title, description (1-2 lines), participant list, key quote (italicized), and date/time span

### Requirement: Event type filtering
The system SHALL allow users to filter events by type using a filter bar above the timeline.

#### Scenario: Filter by single type
- **WHEN** user clicks "讨论" filter chip
- **THEN** only events with event_type "discussion" SHALL be displayed; other filter chips remain unselected

#### Scenario: Show all events
- **WHEN** user clicks "全部" filter chip (default active)
- **THEN** all event types SHALL be displayed

#### Scenario: No events match filter
- **WHEN** user selects "决策" filter but no decision-type events exist
- **THEN** system SHALL display an empty state message "该类型暂无事件"

### Requirement: Event analysis trigger from timeline page
The system SHALL provide a UI on the events page to select a time range and trigger event detection.

#### Scenario: Initial state with no events
- **WHEN** no events have been analyzed for the group
- **THEN** the page SHALL show a date range picker (defaulting to full history) and a "🔍 开始分析事件" button

#### Scenario: Trigger analysis with custom range
- **WHEN** user selects date range `[2025-03-01, 2025-04-30]` and clicks "开始分析"
- **THEN** system SHALL call `POST /api/groups/{id}/events/detect` and show a loading spinner with task progress

#### Scenario: Re-analysis
- **WHEN** events already exist and user clicks "重新分析"
- **THEN** system SHALL trigger a new detection task for the selected time range, replacing old events in that range

### Requirement: Event detail and context viewing
The system SHALL allow users to view event details including the original conversation context.

#### Scenario: View event detail
- **WHEN** user clicks on an event card
- **THEN** system SHALL expand the card or open a modal showing: full description, complete participant list, all key quotes, exact time span, and message count

#### Scenario: View conversation context
- **WHEN** user clicks "查看完整对话" on an event
- **THEN** system SHALL display the original messages in the event's time range, formatted as `[HH:MM] 发送者: 内容`, limited to the messages that form the event

### Requirement: Loading and error states
The system SHALL provide clear feedback for loading, empty, and error states on the events page.

#### Scenario: Analysis in progress
- **WHEN** an event detection task is running for the group
- **THEN** the page SHALL show a loading indicator with the task status, and auto-refresh when the task completes

#### Scenario: Empty state after analysis
- **WHEN** event detection completes but finds 0 events
- **THEN** the page SHALL display "该时间段内未发现明显事件" with a suggestion to try a different time range

#### Scenario: Analysis error
- **WHEN** event detection fails (e.g., all AI calls failed)
- **THEN** the page SHALL display an error message with a "重试" button
