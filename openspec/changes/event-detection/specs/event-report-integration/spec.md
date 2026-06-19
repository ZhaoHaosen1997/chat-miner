## ADDED Requirements

### Requirement: Weekly report references events
The system SHALL display events that fall within a weekly report's time range, if events have been analyzed for that period.

#### Scenario: Weekly report with events
- **WHEN** user views weekly report "2025-W11" and 2 events exist within that week
- **THEN** the report SHALL show an "📅 本周事件" section listing those events with title, type icon, and a link to the events page

#### Scenario: Weekly report without events
- **WHEN** user views a weekly report but no events have been analyzed for that week
- **THEN** the "本周事件" section SHALL NOT appear

#### Scenario: Click event in weekly report
- **WHEN** user clicks an event listed in the weekly report
- **THEN** system SHALL navigate to `/events` with the event scrolled into view

### Requirement: Monthly report references events
The system SHALL display events that fall within a monthly report's time range.

#### Scenario: Monthly report with events
- **WHEN** user views monthly report "2025-06" and 5 events exist within that month
- **THEN** the report SHALL show a "📅 本月事件回顾" section listing those events

#### Scenario: Monthly report without events
- **WHEN** user views a monthly report but no events exist for that month
- **THEN** the event section SHALL NOT appear

### Requirement: Annual report references events
The system SHALL display events that fall within an annual report's year.

#### Scenario: Annual report with events
- **WHEN** user views annual report "2025" and events exist for that year
- **THEN** the report SHALL show a "📅 年度事件" section with the most significant events (sorted by message count descending, top 10)

### Requirement: Member portrait shows event participation
The system SHALL display events a member participated in on their portrait page.

#### Scenario: Member with event participation
- **WHEN** user views 小明's portrait and 小明 participated in 3 events
- **THEN** the portrait page SHALL show a "参与的关键事件" section listing those events with role (发起者 for first participant, 参与者 for others)

#### Scenario: Member with no events
- **WHEN** user views a member's portrait but the member has not participated in any detected events
- **THEN** the event section SHALL NOT appear

#### Scenario: Click event in portrait
- **WHEN** user clicks an event in the portrait's event list
- **THEN** system SHALL navigate to `/events` with that event highlighted

### Requirement: Events and reports are independently generated
Event detection SHALL NOT depend on reports being generated, and report generation SHALL NOT depend on events being analyzed.

#### Scenario: Report generated before events
- **WHEN** a weekly report is generated before any events are analyzed
- **THEN** the report SHALL display normally without an event section; if events are analyzed later and the user revisits the report, the event section SHALL appear

#### Scenario: Events generated before reports
- **WHEN** events are analyzed before a weekly report is generated for that period
- **THEN** the report generation SHALL include an event reference section populated from the existing events
