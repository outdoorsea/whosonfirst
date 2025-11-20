# Lilypad Website Development Roadmap

**Version**: 1.2
**Date**: November 2025

## 1. Introduction

This document outlines the strategic roadmap for the design, development, and launch of the new Lilypad website. The roadmap is divided into sequential phases, each with clear milestones and deliverables. The primary goal is to launch a Minimum Viable Product (MVP) that delivers core social and communication features, followed by subsequent phases for enhancement and growth.

---

## 2. High-Level Phases

*   **Phase 0: Foundation (Backend & Pre-Development)**
    *   *Goal*: Prepare all necessary backend services, APIs, legal documents, and initial design mockups.
    *   *Estimated Timeline*: 3 Weeks

*   **Phase 1: MVP Launch ("The Social Hub")**
    *   *Goal*: Launch the initial version of the website with core features for authentication, chat, and forum access.
    *   *Estimated Timeline*: 3 Weeks

*   **Phase 2: Post-MVP Enhancements ("Visual & Community Features")**
    *   *Goal*: Enhance the user experience with visual features like the user map and deeper integration with the forum.
    *   *Estimated Timeline*: 2-3 Weeks

*   **Phase 3: Future Growth**
    *   *Goal*: Long-term development of advanced features to increase user engagement and platform value.
    *   *Estimated Timeline*: Ongoing

---

## 3. Detailed Roadmap

### Phase 0: Foundation (Backend & Pre-Development)
*(Estimated Timeline: 3-4 Weeks)*

This phase is critical and must be completed before frontend MVP development can be finalized. It involves backend setup, DevOps, and initial design work.

*   **Milestone 0.1: Third-Party Platform Setup**
    *   ✅ **Task**: Deploy the Discourse forum platform.
    *   ✅ **Task**: Set up and configure the CometChat application for web usage.
    *   ✅ **Task**: Provision a PostGIS-enabled PostgreSQL database for WOF data.
    *   ✅ **Task**: Run the ETL script (`import_wof_data.py`) to populate the WOF database.

*   **Milestone 0.2: WOF Standalone Service**
    *   ✅ **Task**: Scaffold a new FastAPI application for the WOF service.
    *   ✅ **Task**: Implement the `/api/v1/hierarchy` endpoint to resolve coordinates.
    *   ✅ **Task**: Connect the service to the PostGIS database.
    *   ✅ **Task**: Containerize the service (e.g., with Docker) and deploy it.

*   **Milestone 0.3: Lilypad Backend Service Implementation**
    *   ✅ **Task**: Implement the `IForumAdapter` interface and the concrete `DiscourseAdapter`.
    *   ✅ **Task**: Implement the `IChatAdapter` interface and the concrete `CometChatAdapter`.
    *   ✅ **Task**: **Implement a client to consume the new WOF API Service.**

*   **Milestone 0.4: Core API Endpoint Development**
    *   ✅ **Task**: Implement user authentication endpoints (`/register`, `/login`, `/logout`, `/me`).
    *   ✅ **Task**: Implement the critical forum SSO endpoint (`/api/discourse/sso`).
    *   ✅ **Task**: Update the location context endpoint (`/api/location/context`) to use the WOF API client.
    *   ✅ **Task**: Implement the endpoint to provide CometChat auth tokens.

*   **Milestone 0.5: Legal & Design Foundation**
    *   ✅ **Task**: Adapt the existing mobile app's Privacy Policy and Terms of Use for web.
    *   ✅ **Task**: Create initial wireframes and mockups for the MVP pages.

*   **Milestone 0.6: Integration Contracts & Adapters**
    *   ✅ **Task**: Document all API contracts, including the new WOF service contract.
    *   ✅ **Task**: Build provider-agnostic facades and stub implementations for local development.
    *   ✅ **Task**: Establish contract and integration tests.

> **Integration Change Control**: All MVP-visible work must route through backend adapters, keep the Discourse instance vanilla (SSO + API keys only), and treat Lilypad mobile changes as configuration toggles rather than code edits.

### Phase 1: MVP Launch ("The Social Hub")
*(Estimated Timeline: 3 Weeks)*

This phase focuses on building the core user-facing features of the website.

*   **Milestone 1.1: Application Shell & User Authentication**
    *   ✅ **Task**: Scaffold the Next.js web application.
    *   ✅ **Task**: Implement the main site layout and responsive navigation based on the mockups from Phase 0.
    *   ✅ **Task**: Build the Login and Registration pages, connecting them to the backend API.
    *   ✅ **Task**: Implement client-side session management.
    *   ✅ **Task**: **Consume only backend contracts from the web client via `IForumAdapter` and `IChatAdapter`—no direct imports of third-party SDKs.**
    *   ✅ **Task**: Add a CI/static-analysis guardrail that fails builds when unauthorized SDKs are referenced in the frontend.

*   **Milestone 1.2: Core Feature Implementation**
    *   ✅ **Task**: **(Forum List)** Build the user dashboard to display the location-based forum list, ensuring links work with the SSO flow.
    *   ✅ **Task**: **(Unified Chat)** Build the "Messages" page using the CometChat SDK, implementing the three-pane layout from the design guidelines.
    *   ✅ **Task**: **(Regional Chat)** Implement the dedicated regional live chat feature.
    *   ✅ **Task**: Introduce a message/forum data normalization layer with shared DTO schemas so both web and mobile rely on identical payloads.
    *   ✅ **Task**: Implement feature flags that can redirect specific forum or chat surfaces back to the mobile application without touching Discourse or mobile code.

*   **Milestone 1.3: MVP Launch Readiness**
    *   ✅ **Task**: Conduct thorough end-to-end testing of all MVP features.
    *   ✅ **Task**: Perform a final design review against the mockups.
    *   ✅ **Task**: Deploy the Next.js application to a production environment.
    *   ✅ **Task**: Run cross-client regression tests to confirm the mobile application continues working against the updated backend contracts.
    *   ✅ **Task**: Execute Discourse smoke tests using only the adapter interfaces to ensure no admin-UI changes are required.
    *   🚀 **DELIVERABLE**: **Live, public version of the Lilypad Website.**

### Phase 2: Post-MVP Enhancements ("Visual & Community Features")
*(Estimated Timeline: 2-3 Weeks)*

With the MVP live, this phase focuses on adding high-value features that were deferred.

*   **Milestone 2.1: Interactive User Map**
    *   ✅ **Task**: Implement the backend API (`/api/users/active-locations`).
    *   ✅ **Task**: Build the "Map" page on the website using Mapbox GL JS.

*   **Milestone 2.2: Deeper Forum & Web Integration**
    *   ✅ **Task**: Create a homepage widget that displays "Latest Topics" from the forum.
    *   ✅ **Task**: Implement web push notifications for forum mentions or replies.

### Phase 3: Future Growth
*(Estimated Timeline: Ongoing)*

This phase includes long-term features to be prioritized based on user feedback and business goals.

*   **Milestone 3.1: Richer User Profiles**
    *   💡 **Idea**: Enhance website profiles to show forum statistics (post count, badges).

*   **Milestone 3.2: Real-Time Location Features**
    *   💡 **Idea**: Re-evaluate and implement the "heartbeat" location feature for a live-updating map.