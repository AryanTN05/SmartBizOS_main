import { useEffect } from 'react';
import { useLaraUI } from '../../lib/LaraUIContext.jsx';

// Binds ⌘J / Ctrl+J to toggle the Lara drawer. Mount once per page that
// should expose the hotkey (admin shell + post-demo landing).
export default function LaraHotkey() {
  const { toggleDrawer } = useLaraUI();
  useEffect(() => {
    const onKey = (e) => {
      const meta = e.metaKey || e.ctrlKey;
      if (meta && (e.key === 'j' || e.key === 'J')) {
        e.preventDefault();
        toggleDrawer();
      }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [toggleDrawer]);
  return null;
}
