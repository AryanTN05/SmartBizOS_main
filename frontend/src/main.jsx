import React from 'react';
import ReactDOM from 'react-dom/client';
import App from './App.jsx';

// Order matters:
// 1. brand.css — zero → prod base tokens (--accent, --bg-primary, etc.)
// 2. tokens.css — SmartBiz product skin (--sb-* tokens + global reset)
// 3. global.css — keyframes + resets that depend on the tokens above
import './styles/brand.css';
import './styles/tokens.css';
import './styles/global.css';

ReactDOM.createRoot(document.getElementById('root')).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
);
