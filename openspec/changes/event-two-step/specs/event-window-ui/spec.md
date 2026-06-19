## ADDED Requirements

### Requirement: Event window list display
The frontend SHALL display detected but unanalyzed event windows as a list grouped by month in reverse chronological order, after Phase 1 detection completes.

#### Scenario: Windows grouped by month
- **WHEN** detection produces windows spanning 2025-03 and 2025-02
- **THEN** windows SHALL be displayed under month headers "2025年3月" and "2025年2月", with March first (newest)

#### Scenario: Window card shows summary
- **WHEN** a pending window exists with summary data
- **THEN** the card SHALL display: time range (date + HH:MM~HH:MM), message count, top 3 speakers, time span duration, and a preview of the first 2-3 messages

#### Scenario: Window card shows status badge
- **WHEN** a window has status `pending`
- **THEN** the card SHALL display a red/orange badge "待分析"
- **WHEN** a window has status `analyzed`
- **THEN** the card SHALL display a green badge "已分析" with the event title
- **WHEN** a window has status `empty`
- **THEN** the card SHALL display a gray badge "无事件"
- **WHEN** a window has status `analyzing`
- **THEN** the card SHALL display a spinning loader

### Requirement: Per-window analyze button
Each event window card SHALL have an "分析" button that triggers AI analysis for that single window.

#### Scenario: Click analyze on a pending window
- **WHEN** user clicks "分析" on a window card
- **THEN** system SHALL POST to `/api/groups/{id}/events/windows/{wid}/analyze`, the button SHALL show a loading state, and the card SHALL auto-refresh upon completion

#### Scenario: Analyze button hidden during analysis
- **WHEN** a window is being analyzed (status `analyzing`)
- **THEN** the "分析" button SHALL be replaced with a loading indicator

### Requirement: One-click analyze all button
The frontend SHALL provide a "一键分析" button that triggers sequential analysis of all pending windows.

#### Scenario: Analyze all pending windows
- **WHEN** user clicks "一键分析" with 5 pending windows
- **THEN** system SHALL begin analyzing windows one at a time, updating each card's status as it completes, and the button SHALL show progress "分析中 (2/5)"

#### Scenario: No pending windows
- **WHEN** all windows are already analyzed or empty
- **THEN** the "一键分析" button SHALL be hidden or disabled with text "全部已分析"

### Requirement: Auto-refresh on analysis completion
The frontend SHALL automatically refresh the window list and event timeline when an analysis completes.

#### Scenario: Window analyzed, card refreshes
- **WHEN** a per-window analysis completes (success or empty)
- **THEN** the window card SHALL update its status badge and summary without requiring manual page refresh

#### Scenario: New events appear in timeline
- **WHEN** an analysis produces a new event
- **THEN** the event SHALL appear in the existing event timeline below the window list without page refresh

### Requirement: Empty state for no windows
The frontend SHALL display an appropriate empty state when detection finds no candidate windows.

#### Scenario: No peaks detected
- **WHEN** Phase 1 detection completes with 0 windows
- **THEN** the page SHALL display "未发现候选事件时段" with a suggestion to try a different time range

### Requirement: Detection trigger UI adjustment
The detection trigger UI SHALL be updated to reflect the two-step workflow.

#### Scenario: Detection results replace loading state
- **WHEN** Phase 1 detection completes
- **THEN** the loading spinner SHALL be replaced by the window list (not the event timeline); the date range picker and "重新检测" button SHALL remain visible

#### Scenario: Detection in progress
- **WHEN** Phase 1 detection is running (Python only, fast)
- **THEN** the button SHALL briefly show "检测中..." with a spinner; this state SHALL typically last under 3 seconds
