import React from 'react';
import ReactDOM from 'react-dom/client';
import { CssBaseline, ThemeProvider, createTheme } from '@mui/material';
import App from './traffic-dashboard.jsx';
import './styles.css';

const theme = createTheme({
  palette: {
    mode: 'dark',
    background: { default: '#0b1220', paper: '#111c2f' },
    primary: { main: '#31d6c3' },
  },
  typography: { fontFamily: 'Inter, ui-sans-serif, system-ui, sans-serif' },
  shape: { borderRadius: 14 },
});

ReactDOM.createRoot(document.getElementById('root')).render(
  <React.StrictMode>
    <ThemeProvider theme={theme}>
      <CssBaseline />
      <App />
    </ThemeProvider>
  </React.StrictMode>,
);
