# Lilypad Website Sitemap

**Version**: 1.0  
**Date**: November 2025

This sitemap covers the Lilypad website surfaces planned through the MVP (Phase 1) and highlights the first post-MVP additions. Each entry lists the primary route, purpose, key components, backend dependencies, and integration notes to keep Discourse and the Lilypad mobile app untouched.

---

## MVP Scope (Phase 1)

### `/login`
- **Purpose**: Entry point for existing community members.
- **Components**: Form fields, error messaging, password reset link (to existing mobile workflow), CTA to register.
- **Backend Dependencies**: `/login`, `/me`.
- **Integration Notes**: Consumes auth adapter only; redirects to dashboard after session bootstrap.

### `/register`
- **Purpose**: Create new Lilypad accounts with required profile basics.
- **Components**: Registration form, optional location selector, success state with direct dashboard link.
- **Backend Dependencies**: `/register`, `/me`, `WhosOnFirstService`.
- **Integration Notes**: Shares validation schema with mobile; emits analytic event if user continues in mobile app.

### `/dashboard`
- **Purpose**: Home hub surfacing location-based Discourse forums and quick links.
- **Components**: Welcome hero, forum list cards, deep links that launch Discourse SSO flow in new tab, CTA tiles for Messages and Regional Chat.
- **Backend Dependencies**: Forum adapter (`IForumAdapter` via `ForumGateway`), `/api/location/context`.
- **Integration Notes**: All Discourse metadata delivered via adapter to avoid template or plugin edits.

### `/messages`
- **Purpose**: Unified CometChat-powered messaging space (friends, DMs, group threads).
- **Components**: Three-pane layout (conversations, thread, participant info), composer, presence indicators.
- **Backend Dependencies**: Chat adapter for token exchange, CometChat web SDK sandboxed behind `ChatBridgeService`.
- **Integration Notes**: Frontend imports only the bridge service; contract tests ensure parity with mobile payloads.

### `/regional-chat`
- **Purpose**: Always-on live chat for the user's active region.
- **Components**: Region selector fallback, live feed, pinned messages, quick reactions.
- **Backend Dependencies**: Same chat adapter contracts plus regional context API.
- **Integration Notes**: Feature flag can reroute users to the Lilypad mobile chat if stability issues arise.

### `/legal/privacy` and `/legal/terms`
- **Purpose**: Web-friendly copies of the privacy policy and terms of use.
- **Components**: Static markdown render, last-updated banner, contact CTA.
- **Backend Dependencies**: Static assets only.
- **Integration Notes**: Shared source files with mobile; surfaced via footer links.

### Shared UI Surfaces
- **Header/Nav**: Links to Dashboard, Messages, Regional Chat, Map (post-MVP placeholder), Profile menu (logout, account settings placeholder).
- **Footer**: Legal links, support email, download-the-app CTA that deep-links to mobile stores.
- **Error States**: `/error/unauthorized`, `/error/offline` to catch adapter or auth failures before contacting Discourse.

---

## Post-MVP Additions (Phase 2+)

### `/map`
- **Purpose**: Interactive Mapbox visualization of active users and events.
- **Components**: Map canvas, filters (region, activity), user detail drawer.
- **Backend Dependencies**: `/api/users/active-locations`.
- **Integration Notes**: Read-only; no live heartbeat until Phase 3 review.

### `/community/latest-topics`
- **Purpose**: Surfacing Discourse "Latest Topics" widget on the web.
- **Components**: Topic list, inline badges, link-outs launching SSO.
- **Backend Dependencies**: Forum adapter extension for topic feeds.
- **Integration Notes**: Keeps Discourse widgets untouched by rendering data server-side.

### Web Push Preferences (`/settings/notifications`)
- **Purpose**: User control for web push notifications when forum mentions or replies occur.
- **Components**: Toggle list, test notification action, opt-out confirmation.
- **Backend Dependencies**: Notification service + Discourse webhook adapter.
- **Integration Notes**: All pushes initiated via Lilypad backend; no Discourse plugin mods.

---

## Supporting Routes
- **`/api/*` (public docs view)**: Minimal documentation page summarizing available endpoints for internal partners.
- **`/status`**: Simple uptime page calling adapter health checks (forum, chat, location DB) to quickly spot integration regressions.
- **`/app-redirect`**: Utility route the mobile app can deep-link into for future cross-platform handoffs without requiring app updates.
