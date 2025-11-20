# GEMINI Project: Lilypad Chat

This document provides a comprehensive overview of the Lilypad Chat project, its architecture, and instructions for development, building, and testing.

## Project Overview

Lilypad Chat is a feature-rich chat application composed of three main components:

*   **Backend (`lilypad-chat-backend`):** A robust API built with Node.js and the NestJS framework. It handles business logic, data persistence, and real-time communication.
*   **Mobile App (`lilypad-chat-mobile`):** A cross-platform mobile application built with React Native, providing users with a seamless chat experience.
*   **Admin Panel (`lilypad-admin-panel`):** A web-based interface for administrators to manage the application, built with React and Material-UI.

The project also includes a `lilypad-terraform` repository for managing infrastructure as code.

### Architecture and Technologies

The Lilypad Chat application utilizes a modern and scalable technology stack:

*   **Backend:**
    *   **Framework:** NestJS (Node.js)
    *   **Database:** PostgreSQL
    *   **Caching:** Redis
    *   **Real-time Communication:** CometChat SDK, WebSockets
    *   **Geolocation:** Mapbox API
    *   **Cloud Services (AWS):** S3 for file storage, SES for email, SSM for parameter management, and KMS for data encryption.
    *   **Containerization:** Docker

*   **Mobile App:**
    *   **Framework:** React Native
    *   **State Management:** Redux Toolkit
    *   **Navigation:** React Navigation
    *   **Maps:** Mapbox Maps
    *   **Push Notifications:** Firebase
    *   **Real-time Chat:** CometChat

*   **Admin Panel:**
    *   **Framework:** React
    *   **UI Library:** Material-UI

## Building and Running

The recommended development setup involves running the database and Redis in Docker containers while running the backend, mobile app, and admin panel locally.

### Prerequisites

*   Node.js (v20.x recommended)
*   `nvm` (Node Version Manager)
*   Docker and Docker Compose
*   Yarn
*   Android SDK (for mobile development)
*   AWS CLI (optional, for AWS integration)

### 1. Backend Setup

```bash
# Navigate to the backend directory
cd lilypad-chat-backend

# Install dependencies
npm install --legacy-peer-deps

# Start the database and Redis containers
docker-compose -f docker/docker-compose.yml up db redis -d

# Run the development server
npm run start:dev
```

The backend API will be available at `http://localhost:3000`.

### 2. Admin Panel Setup

```bash
# Navigate to the admin panel directory
cd lilypad-admin-panel

# Install dependencies
npm i --legacy-peer-deps

# Start the development server
npm start
```

The admin panel will be accessible at `http://localhost:3000`.

### 3. Mobile App Setup

```bash
# Navigate to the mobile app directory
cd lilypad-chat-mobile

# Install dependencies
yarn install

# Start the Metro bundler
ENVFILE=.env.local yarn start

# In a new terminal, run the Android app
ENVFILE=.env.local npx react-native run-android --mode developmentdebug
```

## Development Conventions

*   **Code Style:** The `lilypad-admin-panel` repository contains a `CODESTYLE.md` file that outlines the architecture, folder structure, and coding style guidelines.
*   **Branching:** The projects use a Gitflow-like branching model. Pushing to `develop`, `staging`, and `master` branches triggers builds on the respective servers.
*   **Environment Variables:** Each component uses `.env` files for configuration. Examples are provided in each repository (`.env.example`).
*   **Local Development:** The `DEVELOPMENT.md` file provides a detailed guide for local development, including how to mock AWS services for a faster development loop.

## Testing

The backend has a comprehensive test suite.

### Backend Tests

```bash
# Navigate to the backend directory
cd lilypad-chat-backend

# Run unit tests
npm run test

# Run end-to-end tests
npm run test:e2e

# Run integration tests
npm run test:integration
```
