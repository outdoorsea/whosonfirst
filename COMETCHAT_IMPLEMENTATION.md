# CometChat Implementation Guide

**Version**: 1.0
**Date**: November 2025

## 1. Introduction

This document provides a high-level guide for developers implementing the `IChatAdapter` interface using the CometChat SDK. The goal is to create a `CometChatAdapter` that encapsulates all interactions with the CometChat service, allowing the rest of the Lilypad application to remain agnostic to the specific chat provider.

These instructions assume that the CometChat application has been created and the necessary credentials (`APP_ID`, `REGION`, `AUTH_KEY`) are available as environment variables.

---

## 2. Initialization and Configuration

The first step is to initialize the CometChat SDK when the application starts. This should be done once.

### 2.1. SDK Initialization

In the main entry point of the web application (e.g., `_app.tsx` in a Next.js project), you will initialize CometChat.

```typescript
import { CometChat } from "@cometchat-pro/chat";

const APP_ID = process.env.NEXT_PUBLIC_COMETCHAT_APP_ID;
const REGION = process.env.NEXT_PUBLIC_COMETCHAT_REGION;

const appSettings = new CometChat.AppSettingsBuilder()
  .subscribePresenceForAllUsers()
  .setRegion(REGION)
  .build();

CometChat.init(APP_ID, appSettings).then(
  () => {
    console.log("CometChat initialization completed successfully");
  },
  (error) => {
    console.log("CometChat initialization failed with error:", error);
  }
);
```

---

## 3. Implementing the `IChatAdapter`

The `CometChatAdapter` will implement the `IChatAdapter` interface, providing concrete logic for each method using the CometChat SDK.

### 3.1. User Authentication

The Lilypad backend will provide a CometChat Auth Token for an authenticated user. The adapter will use this token to log the user into CometChat.

```typescript
// In CometChatAdapter.ts

class CometChatAdapter implements IChatAdapter {
  private authToken: string;

  constructor(authToken: string) {
    this.authToken = authToken;
  }

  async login(userId: string): Promise<CometChat.User> {
    if (!this.authToken) {
      throw new Error("CometChat Auth Token is required.");
    }
    return CometChat.login(userId, this.authToken);
  }

  async logout(): Promise<void> {
    return CometChat.logout();
  }
  
  // ... other methods
}
```

### 3.2. Core Chat Functionality

Here are examples of how to implement some of the key methods from the `IChatAdapter` interface.

#### Fetching Conversations

```typescript
// In CometChatAdapter.ts

async getConversations(): Promise<CometChat.Conversation[]> {
  const limit = 50;
  const conversationsRequest = new CometChat.ConversationsRequestBuilder()
    .setLimit(limit)
    .build();

  return conversationsRequest.fetchNext();
}
```

#### Sending a Message

```typescript
// In CometChatAdapter.ts

async sendMessage(receiverId: string, messageText: string, receiverType: 'user' | 'group'): Promise<CometChat.TextMessage> {
  const textMessage = new CometChat.TextMessage(
    receiverId,
    messageText,
    receiverType
  );

  return CometChat.sendMessage(textMessage);
}
```

#### Fetching Messages for a Conversation

```typescript
// In CometChatAdapter.ts

async getMessages(conversationWithId: string, conversationType: 'user' | 'group'): Promise<CometChat.BaseMessage[]> {
  const limit = 50;
  const messagesRequest = new CometChat.MessagesRequestBuilder()
    .setLimit(limit)
    .setConversationId(conversationWithId)
    .setConversationType(conversationType)
    .build();

  return messagesRequest.fetchPrevious();
}
```

#### Joining a Group

```typescript
// In CometChatAdapter.ts

async joinGroup(groupId: string): Promise<CometChat.Group> {
  // Assuming public groups for regional chats
  return CometChat.joinGroup(groupId, CometChat.GROUP_TYPE.PUBLIC, "");
}
```

---

## 4. Real-Time Event Listening

A critical part of the chat implementation is listening for real-time events, such as incoming messages. A listener should be added after a user successfully logs in.

```typescript
// In your main chat component or context provider

useEffect(() => {
  const listenerID = "UNIQUE_LISTENER_ID";

  CometChat.addMessageListener(
    listenerID,
    new CometChat.MessageListener({
      onTextMessageReceived: (textMessage: CometChat.TextMessage) => {
        console.log("Text message received successfully", textMessage);
        // Add the new message to your component's state to update the UI
      },
      onMediaMessageReceived: (mediaMessage: CometChat.MediaMessage) => {
        console.log("Media message received successfully", mediaMessage);
      },
      // ... other listeners like onCustomMessageReceived
    })
  );

  return () => {
    // Clean up the listener when the component unmounts
    CometChat.removeMessageListener(listenerID);
  };
}, []);
```

---

## 5. Next Steps

1.  **Complete the Adapter**: Implement all required methods from the `IChatAdapter` interface.
2.  **State Management**: Integrate the adapter with your application's state management solution (e.g., Redux, Zustand) to update the UI in response to new messages and other events.
3.  **UI Components**: Build the UI components (Conversation List, Message Window, etc.) that will call the adapter's methods and display the data.
4.  **Error Handling**: Implement robust error handling for API calls and real-time events.
