## REMOVED Requirements

### Requirement: Event timeline page
**Reason**: The standalone `/events` route and EventTimeline component are replaced by the Dashboard events section and the `/event/:eventId` detail page. Events are no longer a separate navigation destination.
**Migration**: `/events` route SHALL redirect to `/` (Dashboard). EventTimeline.vue and Events.vue components are removed.

### Requirement: Event analysis trigger from timeline page
**Reason**: The date range picker and analysis trigger move to the Dashboard events section.
**Migration**: The phase 1 detection trigger is now in the Dashboard events section as a "扫描新事件" button.

### Requirement: Event type filtering
**Reason**: Filter chips are not included in the Dashboard integration for v1.18.2. Event browsing is chronological (month groups) rather than type-based.
**Migration**: Event type filtering is removed from the UI. It may be reintroduced in a future version.

## ADDED Requirements

### Requirement: Event detail page as primary event view
The event detail page `/event/:eventId` SHALL be the primary destination for viewing event content, replacing the inline card expansion from v1.18.1.

#### Scenario: Click event anywhere
- **WHEN** user clicks an event reference anywhere in the app (Dashboard, weekly report, portrait page)
- **THEN** system SHALL navigate to `/event/:eventId`

### Requirement: Redirect from old events route
The old `/events` route SHALL redirect to the Dashboard.

#### Scenario: User navigates to /events
- **WHEN** user directly accesses `/events` URL
- **THEN** system SHALL redirect to `/` (Dashboard) where the events section is visible
