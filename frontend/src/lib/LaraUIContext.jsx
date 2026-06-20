import React, { createContext, useCallback, useContext, useMemo, useState } from 'react';

// Global UI state for the Lara side-drawer.
// The drawer BODY is owned by the Lara module agent; this context just
// tracks open/close so sidebar buttons, ⌘J hotkey, and "Ask Lara" CTAs
// in module code can all toggle it.

const LaraUIContext = createContext(null);

export function LaraUIProvider({ children }) {
  const [open, setOpen] = useState(false);
  const [seed, setSeed] = useState(null); // optional opening payload (prompt, context, etc.)

  const openDrawer = useCallback((payload = null) => {
    setSeed(payload);
    setOpen(true);
  }, []);
  const closeDrawer = useCallback(() => setOpen(false), []);
  const toggleDrawer = useCallback(() => setOpen((v) => !v), []);

  const value = useMemo(
    () => ({ open, seed, openDrawer, closeDrawer, toggleDrawer }),
    [open, seed, openDrawer, closeDrawer, toggleDrawer],
  );

  return <LaraUIContext.Provider value={value}>{children}</LaraUIContext.Provider>;
}

export function useLaraUI() {
  const ctx = useContext(LaraUIContext);
  if (!ctx) throw new Error('useLaraUI must be used inside <LaraUIProvider>');
  return ctx;
}
