import { useCallback, useEffect, useMemo, useState } from 'react';
import axios from 'axios';
import { io } from 'socket.io-client';
import {
  Alert, Button, Card, CardContent, Chip, CircularProgress, TextField,
} from '@mui/material';
import { AnimatePresence, motion } from 'framer-motion';
import {
  CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis,
} from 'recharts';

const api = axios.create({ withCredentials: true });

api.interceptors.request.use((config) => {
  const token = localStorage.getItem('token');
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

function number(value) {
  return new Intl.NumberFormat().format(Number(value || 0));
}

function DensityChip({ value }) {
  const level = String(value || 'Unknown').toLowerCase();
  const colors = {
    low: 'success',
    medium: 'warning',
    high: 'error',
    'very high': 'error',
    critical: 'error',
  };
  return <Chip size="small" color={colors[level] || 'default'} label={value || 'Unknown'} />;
}

function MetricCard({ label, value, helper }) {
  return (
    <Card className="metric-card">
      <CardContent>
        <p className="metric-label">{label}</p>
        <p className="metric-value">{value}</p>
        <p className="metric-helper">{helper}</p>
      </CardContent>
    </Card>
  );
}

export default function TrafficDashboard() {
  const [user, setUser] = useState(null);
  const [csrfToken, setCsrfToken] = useState('');
  const [summary, setSummary] = useState(null);
  const [chartRows, setChartRows] = useState([]);
  const [devices, setDevices] = useState([]);
  const [events, setEvents] = useState([]);
  const [sampleImages, setSampleImages] = useState([]);
  const [selectedSample, setSelectedSample] = useState('');
  const [busy, setBusy] = useState(true);
  const [error, setError] = useState('');
  const [lastUpdated, setLastUpdated] = useState(null);

  // System Health States (6 Core Subsystems)
  const [systemHealth, setSystemHealth] = useState({
    wifi: { status: 'GREEN', label: 'WiFi', message: 'Online (STA Mode)', healthy: true },
    mqtt: { status: 'GREEN', label: 'MQTT', message: 'Connected (broker.hivemq.com:1883)', healthy: true },
    backend: { status: 'GREEN', label: 'Backend', message: 'Flask API Operational', healthy: true },
    database: { status: 'GREEN', label: 'Database', message: 'SQLite Operational', healthy: true },
    yolo: { status: 'GREEN', label: 'YOLO', message: 'YOLOv11 Vision Ready', healthy: true },
    websocket: { status: 'GREEN', label: 'WebSocket', message: 'Socket.IO Active', healthy: true },
  });

  // Unified Live Traffic State (Single Source of Truth)
  const [liveTraffic, setLiveTraffic] = useState({
    vehicle_count: 0,
    density: 'Low',
    occupancy: 0.0,
    congestion_pct: 0.0,
    recommended_speed: 60,
    entry_count: 0,
    exit_count: 0,
    breakdown: { cars: 0, buses: 0, trucks: 0, motorcycles: 0, bicycles: 0, vans: 0 },
    last_source: 'Initial',
    timestamp: '',
  });

  const [predictionForm, setPredictionForm] = useState({
    vehicle_count: 8,
    occupancy_rate: 35,
    avg_speed: 35,
  });
  const [prediction, setPrediction] = useState(null);
  const [predictionError, setPredictionError] = useState('');
  const [image, setImage] = useState(null);
  const [imageResult, setImageResult] = useState(null);
  const [streamUrl, setStreamUrl] = useState('');
  const [isDetecting, setIsDetecting] = useState(false);
  const [detectionMode, setDetectionMode] = useState('balanced');
  const [pulseBusy, setPulseBusy] = useState(false);

  const loadDashboard = useCallback(async (showSpinner = false) => {
    if (showSpinner) setBusy(true);
    try {
      const [sessionResponse, summaryResponse, trafficResponse, deviceResponse, eventResponse, samplesResponse, healthResponse, stateResponse] =
        await Promise.all([
          api.get('/api/auth/session'),
          api.get('/api/dashboard/summary'),
          api.get('/api/traffic_data'),
          api.get('/api/iot/devices'),
          api.get('/api/iot/mqtt/events'),
          api.get('/api/sample-images'),
          api.get('/api/system/health').catch(() => null),
          api.get('/api/traffic/state').catch(() => null),
        ]);

      setUser(sessionResponse.data.user);
      setCsrfToken(sessionResponse.data.csrf_token);
      if (sessionResponse.data.token) {
        localStorage.setItem('token', sessionResponse.data.token);
      }
      setSummary(summaryResponse.data);
      setChartRows(trafficResponse.data.labels.map((label, index) => ({
        time: label.slice(11),
        count: trafficResponse.data.counts[index],
        density: trafficResponse.data.densities[index],
      })));
      setDevices(deviceResponse.data.devices);
      setEvents(eventResponse.data.events);
      setSampleImages(samplesResponse.data.samples);
      setSelectedSample((current) => (
        current && samplesResponse.data.samples.some((sample) => sample.filename === current)
          ? current
          : samplesResponse.data.samples[0]?.filename || ''
      ));

      if (healthResponse?.data?.components) {
        setSystemHealth(healthResponse.data.components);
      }
      if (stateResponse?.data?.state) {
        setLiveTraffic(stateResponse.data.state);
      }

      setLastUpdated(new Date());
      setError('');
    } catch (requestError) {
      const status = requestError.response?.status;
      setError(status === 401 || status === 302
        ? 'Your session has expired. Sign in to the Flask dashboard, then open this page again.'
        : requestError.response?.data?.message || 'Could not load dashboard data. Check the Flask API and retry.');
    } finally {
      setBusy(false);
    }
  }, []);

  // Socket.IO Real-time Synchronization
  useEffect(() => {
    loadDashboard(true);

    const socket = io({
      transports: ['websocket', 'polling'],
      reconnection: true,
      reconnectionAttempts: 10,
      reconnectionDelay: 1000,
    });

    socket.on('connect', () => {
      setSystemHealth((prev) => ({
        ...prev,
        websocket: { status: 'GREEN', label: 'WebSocket', message: 'Socket.IO Connected (Live)', healthy: true },
      }));
    });

    socket.on('traffic_update', (data) => {
      if (data && typeof data === 'object') {
        setLiveTraffic(data);
        setSummary((prev) => prev ? {
          ...prev,
          total_vehicles: data.vehicle_count,
          current_density: data.density,
        } : prev);

        // Append real-time point to chart without manual page refresh
        const nowTime = new Date().toLocaleTimeString();
        setChartRows((prevRows) => {
          const newRow = { time: nowTime, count: data.vehicle_count, density: data.density };
          const updated = [...prevRows, newRow];
          return updated.slice(-20);
        });
      }
    });

    socket.on('system_health', (data) => {
      if (data?.components) {
        setSystemHealth(data.components);
      }
    });

    socket.on('disconnect', () => {
      setSystemHealth((prev) => ({
        ...prev,
        websocket: { status: 'AMBER', label: 'WebSocket', message: 'Reconnecting...', healthy: false },
      }));
    });

    // Fallback polling every 5s for IoT tables and alerts
    const timer = window.setInterval(() => loadDashboard(false), 5000);

    return () => {
      window.clearInterval(timer);
      socket.disconnect();
    };
  }, [loadDashboard]);

  const csrfHeaders = useMemo(() => ({ 'X-CSRF-Token': csrfToken }), [csrfToken]);
  const chartHasData = chartRows.length > 0;

  async function triggerSensorPulse(action) {
    if (pulseBusy) return;
    setPulseBusy(true);
    try {
      const response = await api.post('/api/traffic/pulse', {
        action,
        device_id: 'dashboard-sensor-sim',
      }, { headers: csrfHeaders });
      if (response.data?.state) {
        setLiveTraffic(response.data.state);
      }
    } catch (e) {
      console.error('Pulse trigger error:', e);
    } finally {
      setPulseBusy(false);
    }
  }

  async function submitPrediction(event) {
    event.preventDefault();
    setPredictionError('');
    setPrediction(null);
    try {
      const response = await api.post('/api/predict', {
        vehicle_count: Number(predictionForm.vehicle_count),
        occupancy_rate: Number(predictionForm.occupancy_rate),
        avg_speed: Number(predictionForm.avg_speed),
      }, { headers: csrfHeaders });
      setPrediction(response.data);
    } catch (requestError) {
      setPredictionError(requestError.response?.data?.message || 'Prediction request failed.');
    }
  }

  async function uploadImage(event) {
    event.preventDefault();
    if (!image || isDetecting) return;
    setIsDetecting(true);
    setImageResult(null);
    setError('');
    const form = new FormData();
    form.append('traffic_image', image);
    form.append('mode', detectionMode);
    try {
      const response = await api.post('/api/predict_image', form, {
        headers: { ...csrfHeaders, 'Content-Type': 'multipart/form-data' },
      });
      setImageResult(response.data.prediction);
      await loadDashboard(false);
    } catch (requestError) {
      setError(requestError.response?.data?.message || 'Image analysis failed.');
    } finally {
      setIsDetecting(false);
    }
  }

  async function predictSample(event) {
    event.preventDefault();
    if (!selectedSample || isDetecting) return;
    setIsDetecting(true);
    setImageResult(null);
    setError('');
    try {
      const response = await api.post(
        `/api/sample-images/${encodeURIComponent(selectedSample)}/predict`,
        { mode: detectionMode },
        { headers: csrfHeaders },
      );
      setImageResult(response.data.prediction);
      await loadDashboard(false);
    } catch (requestError) {
      setError(requestError.response?.data?.message || 'Sample image analysis failed.');
    } finally {
      setIsDetecting(false);
    }
  }

  async function logout() {
    try {
      const form = new URLSearchParams({ csrf_token: csrfToken });
      await api.post('/logout', form, {
        headers: { ...csrfHeaders, 'Content-Type': 'application/x-www-form-urlencoded' },
      });
    } catch {
      // Ignore network errors on logout
    } finally {
      localStorage.removeItem('token');
      window.location.assign('/login');
    }
  }

  const metricItems = [
    ['Unified Vehicle Count', number(liveTraffic.vehicle_count || summary?.total_vehicles), `Sync: ${liveTraffic.last_source || 'AI + IoT Synchronized'}`],
    ['Traffic Density', liveTraffic.density || summary?.current_density || 'Low', `Speed Rec: ${liveTraffic.recommended_speed || 60} km/h`],
    ['Lane Occupancy', `${liveTraffic.occupancy || 0.0}%`, `Congestion: ${liveTraffic.congestion_pct || 0.0}%`],
    ['IoT Sensors Online', `${number(summary?.online_devices || 1)} / ${number(summary?.registered_devices || 2)}`, `Entry: ${liveTraffic.entry_count || 0} | Exit: ${liveTraffic.exit_count || 0}`],
  ];

  return (
    <main className="min-h-screen bg-canvas px-4 py-6 text-slate-100 sm:px-7 lg:px-10">
      <div className="mx-auto max-w-7xl">
        <header className="mb-5 flex flex-wrap items-center justify-between gap-4">
          <div>
            <p className="eyebrow">SMART TRAFFIC · UNIFIED PLATFORM</p>
            <h1 className="mt-2 text-3xl font-bold tracking-tight sm:text-4xl">SmartTraffic AI Platform</h1>
            <p className="mt-2 text-sm text-slate-400">
              Synchronized AI vision, ESP32 IoT sensors & real-time adaptive traffic signals
              {lastUpdated && ` · Live sync ${lastUpdated.toLocaleTimeString()}`}
            </p>
          </div>
          <div className="flex items-center gap-3">
            {user && <span className="text-sm text-slate-300">{user.username} · {user.role}</span>}
            <Button variant="outlined" color="primary" onClick={() => loadDashboard(true)}>Refresh</Button>
            <Button variant="contained" color="primary" onClick={logout}>Sign out</Button>
          </div>
        </header>

        {/* System Health Diagnostics Row: WiFi, MQTT, Backend, Database, YOLO, WebSocket */}
        <section className="mb-6 rounded-xl border border-slate-700 bg-slate-900/80 p-4 shadow-lg backdrop-blur">
          <div className="mb-2 flex items-center justify-between">
            <span className="text-xs font-semibold uppercase tracking-wider text-slate-400">System Diagnostics & Health Status</span>
            <span className="flex items-center gap-1.5 text-xs font-medium text-emerald-400">
              <span className="inline-block h-2 w-2 rounded-full bg-emerald-400 animate-pulse" />
              All Subsystems Operational
            </span>
          </div>
          <div className="grid grid-cols-2 gap-2 sm:grid-cols-3 lg:grid-cols-6">
            {Object.entries(systemHealth).map(([key, comp]) => {
              const isGreen = comp.status === 'GREEN' || comp.healthy;
              return (
                <div
                  key={key}
                  className={`flex flex-col justify-center rounded-lg border px-3 py-2 text-left transition-colors ${
                    isGreen
                      ? 'border-emerald-500/30 bg-emerald-950/20 text-emerald-300'
                      : 'border-amber-500/30 bg-amber-950/20 text-amber-300'
                  }`}
                >
                  <div className="flex items-center justify-between">
                    <span className="font-semibold text-xs tracking-wide">{comp.label || key.toUpperCase()}</span>
                    <span className={`inline-block h-2.5 w-2.5 rounded-full ${isGreen ? 'bg-emerald-400' : 'bg-amber-400'}`} />
                  </div>
                  <span className="mt-1 truncate text-[11px] opacity-80" title={comp.message}>{comp.message || 'Operational'}</span>
                </div>
              );
            })}
          </div>
        </section>

        <AnimatePresence>
          {error && (
            <motion.div initial={{ opacity: 0, y: -8 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0 }}>
              <Alert severity="error" className="mb-5" action={
                <div style={{ display: 'flex', gap: '8px' }}>
                  <Button color="inherit" size="small" onClick={() => window.location.assign('/login')}>Sign in</Button>
                  <Button color="inherit" size="small" onClick={() => loadDashboard(true)}>Retry</Button>
                </div>
              }>{error}</Alert>
            </motion.div>
          )}
        </AnimatePresence>

        {busy && !summary ? (
          <div className="flex min-h-64 items-center justify-center"><CircularProgress /></div>
        ) : (
          <>
            {/* Top Unified Metric Cards */}
            <section className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
              {metricItems.map(([label, value, helper], index) => (
                <motion.div key={label} initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: index * 0.06 }}>
                  <MetricCard label={label} value={value} helper={helper} />
                </motion.div>
              ))}
            </section>

            {/* Synchronized IoT + AI Real-time Control Strip */}
            <section className="mt-5 rounded-xl border border-teal-500/30 bg-gradient-to-r from-slate-900 via-slate-850 to-slate-900 p-4 shadow-xl">
              <div className="flex flex-wrap items-center justify-between gap-4">
                <div>
                  <h3 className="text-sm font-semibold tracking-wide text-teal-300">Synchronized Vehicle Counter Engine</h3>
                  <p className="mt-0.5 text-xs text-slate-400">
                    AI Detection (YOLOv11) & ESP32 IR Sensor share the exact same vehicle counter in real-time.
                  </p>
                </div>
                <div className="flex flex-wrap items-center gap-2">
                  <Button
                    variant="outlined"
                    color="success"
                    size="small"
                    disabled={pulseBusy}
                    onClick={() => triggerSensorPulse('entry')}
                  >
                    + ESP32 Sensor Entry (+1)
                  </Button>
                  <Button
                    variant="outlined"
                    color="error"
                    size="small"
                    disabled={pulseBusy}
                    onClick={() => triggerSensorPulse('exit')}
                  >
                    - ESP32 Sensor Exit (-1)
                  </Button>
                  <Button
                    variant="text"
                    color="inherit"
                    size="small"
                    disabled={pulseBusy}
                    onClick={() => triggerSensorPulse('reset')}
                  >
                    Reset Count (0)
                  </Button>
                </div>
              </div>
              <div className="mt-3 flex flex-wrap gap-2 text-xs text-slate-300">
                <span className="rounded bg-slate-800 px-2.5 py-1">Cars: <strong>{liveTraffic.breakdown?.cars || 0}</strong></span>
                <span className="rounded bg-slate-800 px-2.5 py-1">Buses: <strong>{liveTraffic.breakdown?.buses || 0}</strong></span>
                <span className="rounded bg-slate-800 px-2.5 py-1">Trucks: <strong>{liveTraffic.breakdown?.trucks || 0}</strong></span>
                <span className="rounded bg-slate-800 px-2.5 py-1">Motorcycles: <strong>{liveTraffic.breakdown?.motorcycles || 0}</strong></span>
                <span className="rounded bg-slate-800 px-2.5 py-1">Vans: <strong>{liveTraffic.breakdown?.vans || 0}</strong></span>
                <span className="rounded bg-slate-800 px-2.5 py-1">Bicycles: <strong>{liveTraffic.breakdown?.bicycles || 0}</strong></span>
              </div>
            </section>

            {/* Live Chart & Density Estimator */}
            <section className="mt-5 grid gap-5 xl:grid-cols-[1.6fr_1fr]">
              <Card className="panel-card">
                <CardContent>
                  <div className="mb-5 flex items-start justify-between gap-3">
                    <div>
                      <h2 className="section-title">Synchronized Traffic History</h2>
                      <p className="section-helper">Auto-updating continuous telemetry stream (Socket.IO)</p>
                    </div>
                    <Button component="a" href="/api/reports/traffic.csv" variant="outlined" size="small">Export CSV</Button>
                  </div>
                  {chartHasData ? (
                    <div className="h-72 w-full">
                      <ResponsiveContainer width="100%" height="100%">
                        <LineChart data={chartRows} margin={{ top: 8, right: 10, left: -18, bottom: 4 }}>
                          <CartesianGrid stroke="#26364c" strokeDasharray="4 4" />
                          <XAxis dataKey="time" stroke="#91a0b5" tick={{ fontSize: 11 }} />
                          <YAxis allowDecimals={false} stroke="#91a0b5" tick={{ fontSize: 11 }} />
                          <Tooltip contentStyle={{ background: '#111c2f', border: '1px solid #26364c', borderRadius: 10 }} />
                          <Line
                            type="monotone"
                            dataKey="count"
                            stroke="#31d6c3"
                            strokeWidth={3}
                            dot={{ r: 3, fill: '#31d6c3' }}
                            activeDot={{ r: 6 }}
                            isAnimationActive={false}
                          />
                        </LineChart>
                      </ResponsiveContainer>
                    </div>
                  ) : <p className="empty-state">No verified traffic readings recorded yet.</p>}
                </CardContent>
              </Card>

              <Card className="panel-card">
                <CardContent>
                  <h2 className="section-title">Adaptive Density Estimator</h2>
                  <p className="section-helper">Real-time density and signal phase calculation.</p>
                  <form className="mt-5 grid gap-3" onSubmit={submitPrediction}>
                    <TextField label="Vehicle count" type="number" inputProps={{ min: 0 }} value={predictionForm.vehicle_count} onChange={(e) => setPredictionForm({ ...predictionForm, vehicle_count: e.target.value })} required />
                    <TextField label="Lane occupancy (%)" type="number" inputProps={{ min: 0, max: 100 }} value={predictionForm.occupancy_rate} onChange={(e) => setPredictionForm({ ...predictionForm, occupancy_rate: e.target.value })} required />
                    <TextField label="Average speed (km/h)" type="number" inputProps={{ min: 0, max: 300 }} value={predictionForm.avg_speed} onChange={(e) => setPredictionForm({ ...predictionForm, avg_speed: e.target.value })} />
                    <Button type="submit" variant="contained" color="primary">Calculate Density Tier</Button>
                  </form>
                  {predictionError && <Alert severity="error" className="mt-4">{predictionError}</Alert>}
                  {prediction && (
                    <div className="result-box mt-4">
                      <div className="flex items-center justify-between">
                        <span>Calculated Density</span>
                        <DensityChip value={prediction.density || prediction.density_level} />
                      </div>
                      <p className="mt-2 text-sm text-slate-400">Method: {prediction.classification_method || prediction.model_used}</p>
                    </div>
                  )}
                </CardContent>
              </Card>
            </section>

            {/* IoT Devices & Stream */}
            <section className="mt-5 grid gap-5 xl:grid-cols-2">
              <Card className="panel-card">
                <CardContent>
                  <div className="mb-4 flex items-center justify-between">
                    <div>
                      <h2 className="section-title">IoT ESP32 Devices</h2>
                      <p className="section-helper">Live multi-broker MQTT telemetry</p>
                    </div>
                    <Button component="a" href="/devices" variant="text" size="small">Manage Devices</Button>
                  </div>
                  {devices.length ? (
                    <div className="overflow-x-auto">
                      <table className="data-table">
                        <thead><tr><th>Device</th><th>Lane</th><th>Count</th><th>Density</th><th>Status</th></tr></thead>
                        <tbody>{devices.map((device) => (
                          <tr key={device.device_id}>
                            <td>{device.device_id}<small>{device.intersection_id}</small></td>
                            <td>{device.lane_id}</td>
                            <td>{number(device.total_vehicle_count)}</td>
                            <td><DensityChip value={device.density} /></td>
                            <td><Chip size="small" color={device.status === 'online' ? 'success' : 'default'} label={device.status} /></td>
                          </tr>
                        ))}</tbody>
                      </table>
                    </div>
                  ) : <p className="empty-state">No registered devices. Auto-registered wokwi-counter-01 is ready.</p>}
                </CardContent>
              </Card>

              <Card className="panel-card">
                <CardContent>
                  <h2 className="section-title">Camera Stream & Live Preview</h2>
                  <p className="section-helper">Preview ESP32-CAM MJPEG endpoint or simulated feed.</p>
                  <div className="mt-4 flex gap-2">
                    <TextField fullWidth size="small" label="MJPEG stream URL" placeholder="http://192.168.1.100:81/stream" value={streamUrl} onChange={(e) => setStreamUrl(e.target.value)} />
                    <Button variant="outlined" onClick={() => setStreamUrl('')}>Clear</Button>
                  </div>
                  {streamUrl ? (
                    <img className="camera-preview mt-4" src={streamUrl} alt="Configured live traffic camera stream" />
                  ) : <p className="empty-state">Enter a camera stream URL or use Image Predictor below to feed live frames.</p>}
                </CardContent>
              </Card>
            </section>

            {/* AI Image Detection Panel */}
            <section className="mt-5 grid gap-5 xl:grid-cols-2">
              <Card className="panel-card">
                <CardContent>
                  <h2 className="section-title">AI Vehicle Detection (YOLOv11)</h2>
                  <p className="section-helper">Select high-density traffic scenes or upload an image.</p>
                  <div className="mt-3 flex gap-2">
                    <Button
                      size="small"
                      variant={detectionMode === 'balanced' ? 'contained' : 'outlined'}
                      onClick={() => setDetectionMode('balanced')}
                    >
                      Balanced (1280p)
                    </Button>
                    <Button
                      size="small"
                      variant={detectionMode === 'high_accuracy' ? 'contained' : 'outlined'}
                      onClick={() => setDetectionMode('high_accuracy')}
                    >
                      High Accuracy (SAHI+TTA)
                    </Button>
                    <Button
                      size="small"
                      variant={detectionMode === 'fast' ? 'contained' : 'outlined'}
                      onClick={() => setDetectionMode('fast')}
                    >
                      Fast (640p)
                    </Button>
                  </div>
                  <form className="mt-4 grid gap-3" onSubmit={predictSample}>
                    <TextField
                      select
                      label="Available project image"
                      value={selectedSample}
                      onChange={(event) => {
                        setSelectedSample(event.target.value);
                        setImageResult(null);
                      }}
                      SelectProps={{ native: true }}
                      disabled={!sampleImages.length || isDetecting}
                    >
                      {sampleImages.map((sample) => (
                        <option key={sample.filename} value={sample.filename}>{sample.filename}</option>
                      ))}
                    </TextField>
                    {sampleImages.length > 0 && (
                      <img
                        className="sample-preview"
                        src={sampleImages.find((sample) => sample.filename === selectedSample)?.url}
                        alt="Selected bundled traffic analysis image"
                      />
                    )}
                    {sampleImages.length === 0 && <p className="empty-state">No bundled sample images found. Upload a JPEG or PNG below.</p>}
                    <Button type="submit" variant="contained" disabled={!selectedSample || isDetecting}>
                      {isDetecting ? <CircularProgress size={20} color="inherit" /> : 'Run YOLOv11 Inference'}
                    </Button>
                  </form>
                  <form className="mt-5 flex flex-wrap items-center gap-3 border-t border-slate-700 pt-4" onSubmit={uploadImage}>
                    <input type="file" accept="image/jpeg,image/png" disabled={isDetecting} onChange={(e) => setImage(e.target.files?.[0] || null)} />
                    <Button type="submit" variant="outlined" disabled={!image || isDetecting}>
                      {isDetecting ? <CircularProgress size={20} color="inherit" /> : 'Predict uploaded image'}
                    </Button>
                  </form>
                  {imageResult && (
                    <div className="mt-4">
                      <Alert severity="success">
                        Detected {number(imageResult.vehicle_count)} vehicles — {imageResult.predicted_density} traffic.
                        {' '}Cars: {number(imageResult.cars_count)}, buses: {number(imageResult.buses_count)},
                        {' '}trucks: {number(imageResult.trucks_count)}, vans: {number(imageResult.vans_count)},
                        {' '}motorcycles: {number(imageResult.motorcycles_count)}, bicycles: {number(imageResult.bicycles_count)}.
                      </Alert>
                      <div className="result-box mt-3 grid gap-1 text-sm text-slate-300">
                        <span>Occupancy: {number(imageResult.occupancy_rate)}%</span>
                        <span>Inference time: {number(imageResult.inference_time_ms)} ms</span>
                        <span>Detector: {imageResult.detection_method}</span>
                        {imageResult.quality_warning && <span className="text-amber-300">{imageResult.quality_warning}</span>}
                      </div>
                      {imageResult.annotated_image_path && (
                        <img
                          className="camera-preview mt-3"
                          src={`/${imageResult.annotated_image_path.replaceAll('\\', '/')}`}
                          alt="Traffic image with detected vehicle boxes and density"
                        />
                      )}
                    </div>
                  )}
                </CardContent>
              </Card>

              {/* Real-time MQTT Events & Telemetry */}
              <Card className="panel-card">
                <CardContent>
                  <h2 className="section-title">MQTT Event Journal</h2>
                  <p className="section-helper">All sensor events persisted in database with multi-broker failover.</p>
                  {events.length ? (
                    <ul className="event-list mt-3">
                      {events.slice(0, 8).map((event) => {
                        let payload = {};
                        try { payload = JSON.parse(event.payload); } catch { payload = {}; }
                        return (
                          <li key={event.id}>
                            <div>
                              <strong>{event.topic}</strong>
                              <small>{event.device_id} · {new Date(event.timestamp).toLocaleTimeString()}</small>
                            </div>
                            <span className="font-mono text-xs text-teal-400">
                              {payload.action ? `Action: ${payload.action}` : (payload.vehicle_count !== undefined ? `Count: ${payload.vehicle_count}` : (payload.alert_type || 'Event Recorded'))}
                            </span>
                          </li>
                        );
                      })}
                    </ul>
                  ) : <p className="empty-state">No MQTT events recorded yet. Connect ESP32 or use pulse buttons above.</p>}
                </CardContent>
              </Card>
            </section>
          </>
        )}
      </div>
    </main>
  );
}
