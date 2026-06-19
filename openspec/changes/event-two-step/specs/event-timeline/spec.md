## MODIFIED Requirements

### Requirement: Event timeline page
The system SHALL provide a frontend route `/events` that displays BOTH unanalyzed event windows AND analyzed event cards in a unified chronological view.

#### Scenario: User navigates to events page
- **WHEN** user clicks "事件" in the navigation bar
- **THEN** system SHALL navigate to `/events` and display the event timeline page

#### Scenario: Windows and events grouped by month
- **WHEN** unanalyzed windows and analyzed events span multiple months
- **THEN** both SHALL be displayed grouped under month headers in reverse chronological order (newest month first), with windows listed alongside events in time order

#### Scenario: Analyzed event card display
- **WHEN** an event exists with title "小明宣布拿到字节offer", type "social", and metadata
- **THEN** the event card SHALL show: event type icon, title, description, participant list, key quotes, date/time span, and source window indicator

#### Scenario: Window card display (unanalyzed)
- **WHEN** a window exists with status `pending`
- **THEN** the window card SHALL show: summary preview (first messages), time range, message count, top speakers, and an "分析" button

### Requirement: Event analysis trigger from timeline page
The system SHALL provide a UI on the events page to select a time range and trigger Phase 1 detection. After detection completes, event windows SHALL appear in the timeline with per-window and "analyze all" buttons.

#### Scenario: Initial state with no windows or events
- **WHEN** no events and no windows exist for the group
- **THEN** the page SHALL show a date range picker (defaulting to full history) and a "开始分析事件" button

#### Scenario: Trigger detection
- **WHEN** user selects date range and clicks "开始分析"
- **THEN** system SHALL call `POST /api/groups/{id}/events/detect`, briefly show "检测中...", then display the window list

#### Scenario: Windows displayed after detection
- **WHEN** Phase 1 detection completes with 8 windows
- **THEN** the page SHALL display 8 window cards grouped by month, each with an "分析" button, and a "一键分析" button at the top

#### Scenario: Re-detection
- **WHEN** windows already exist and user clicks "重新检测"
- **THEN** system SHALL run Phase 1 detection again, replacing old windows with new ones

### Requirement: Loading and error states
The system SHALL provide clear feedback for loading, empty, and error states on the events page.

#### Scenario: Detection in progress
- **WHEN** Phase 1 detection is running
- **THEN** the page SHALL briefly show a loading indicator; this state typically lasts under 3 seconds

#### Scenario: Window analysis in progress
- **WHEN** a window or batch analysis is running
- **THEN** the analyzed window card SHALL show a spinning loader; completed windows SHALL auto-refresh their status

#### Scenario: Empty state after detection
- **WHEN** Phase 1 detection completes but finds 0 windows
- **THEN** the page SHALL display "该时间段内未发现候选事件时段" with a suggestion to try a different time range

#### Scenario: Analysis error
- **WHEN** a window analysis fails
- **THEN** the window card SHALL show an error indicator with a "重试" option

## ADDED Requirements

### Requirement: Analyze-all progress tracking
The system SHALL display real-time progress during a "一键分析" operation.

#### Scenario: Progress shown during batch analysis
- **WHEN** "一键分析" is processing window 3 of 8
- **THEN** the "一键分析" button SHALL show "分析中 (3/8)" with a progress bar; completed windows SHALL update their cards to show results

#### Scenario: Batch analysis completes
- **WHEN** all 8 windows finish analysis
- **THEN** the "一键分析" button SHALL reset to enabled state; all window cards SHALL show their final status
