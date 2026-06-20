import React, { useEffect, useRef } from 'react';
import Message from './Message.jsx';
import ThinkingIndicator from './ThinkingIndicator.jsx';

// Scrollable message list. Sticks to bottom on new content.
export default function MessageStream({ messages, thinking, padding = '20px 20px 12px' }) {
  const scrollRef = useRef(null);

  useEffect(() => {
    const el = scrollRef.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [messages, thinking]);

  return (
    <div ref={scrollRef} style={{ flex: 1, overflow: 'auto', padding }}>
      {messages.map((m, i) => <Message key={i} m={m} />)}
      {thinking && <ThinkingIndicator />}
    </div>
  );
}
