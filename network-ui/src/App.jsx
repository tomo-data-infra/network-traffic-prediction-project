import React, { useState, useEffect, useRef } from 'react';
import FullCalendar from '@fullcalendar/react';
import dayGridPlugin from '@fullcalendar/daygrid';
import timeGridPlugin from '@fullcalendar/timegrid';
import interactionPlugin from '@fullcalendar/interaction';
// Import Recharts for the traffic visualization
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from 'recharts';
import './App.css'; // Assuming you add the CSS below


function App() {
  // --- States ---
  const [viewMode, setViewMode] = useState('calendar'); // 'calendar' or 'dashboard'
  const [events, setEvents] = useState([]);
  const [pingData, setPingData] = useState([]); // Traffic data state
  const [isAuthenticated, setIsAuthenticated] = useState(false);
  const [modalState, setModalState] = useState({ show: false, mode: 'create', data: null });
  const [authError, setAuthError] = useState('');
  
  // --- Refs ---  
  const calendarRef = useRef(null);
  const passwordRef = useRef(null);
  const PASSWORD = import.meta.env.VITE_PASSWORD;

  // --- 1. Fetch Traffic Data (For Dashboard) ---
  const fetchTraffic = async (start, end) => {
    try {
      const response = await fetch(`http://localhost:8000/api/ping_data?start=${start}&end=${end}`);
      const data = await response.json();
      const chartPoints = data.times.map((t, i) => ({
        time: new Date(t).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
        rtt: data.features[i] 
      }));
      setPingData(chartPoints);
    } catch (err) {
      console.error("Traffic fetch error:", err);
    }
  };

  // --- 2. Fetch Events (Standard + Background Layers) ---
  const fetchEvents = async () => {
    try {
      const response = await fetch('http://localhost:8000/api/event_sessions/');
      const data = await response.json();
      const allEntries = [];
      
      data.forEach(evt => {
        // Interactive Foreground Event
        allEntries.push({
          id: evt.session_id,
          title: evt.event_name,
          start: evt.start_ts,
          end: evt.end_ts,
          extendedProps: {
            category: evt.session_category,
            devices: evt.expected_devices
          }
        });
        // Visual Background Layer
        allEntries.push({
          start: evt.start_ts,
          end: evt.end_ts,
          display: 'background',
          color: evt.session_category === 'system_update' ? '#ffebee' : '#e3f2fd'
        });
      });
      setEvents(allEntries);
    } catch (error) {
      console.error('Error fetching events:', error);
    }
  };

  useEffect(() => {
    fetchEvents();
  }, []);

  // --- Handlers ---
  const switchToDashboard = () => {
    const now = new Date();
    const start = new Date(now - 30 * 60000).toISOString();
    const end = new Date(now + 30 * 60000).toISOString();
    fetchTraffic(start, end);
    setViewMode('dashboard');
  };

  const handleAuth = (e) => {
    e.preventDefault();
    if (passwordRef.current.value === PASSWORD) {
      setIsAuthenticated(true);
      setAuthError('');
    } else {
      setAuthError('Incorrect Password');
    }
  };

  const openModal = (mode, data = null) => setModalState({ show: true, mode, data });
  const closeModal = () => setModalState({ show: false, mode: 'create', data: null });

  // --- CRUD Operations ---
  const handleSubmitEvent = async (e) => {
    e.preventDefault();
    const formData = new FormData(e.target);
    const eventData = {
      event_name: formData.get('title'),
      expected_devices: parseInt(formData.get('devices')),
      session_category: formData.get('category'),
      start_ts: formData.get('start_ts'),
      end_ts: formData.get('end_ts')
    };

    try {
      const url = modalState.mode === 'create' 
        ? 'http://localhost:8000/api/event_sessions/' 
        : `http://localhost:8000/api/event_sessions/${modalState.data.id}/`;
      
      await fetch(url, {
        method: modalState.mode === 'create' ? 'POST' : 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(eventData),
      });
      fetchEvents();
      closeModal();
    } catch (err) { console.error('Save error:', err); }
  };

  const handleDeleteEvent = async () => {
    if (!window.confirm('Are you sure?')) return;
    try {
      await fetch(`http://localhost:8000/api/event_sessions/${modalState.data.id}/`, { method: 'DELETE' });
      fetchEvents();
      closeModal();
    } catch (err) { console.error('Delete error:', err); }
  };

  // --- Render Helpers (Defined ABOVE the main return) ---
  const renderDashboard = () => (
    <div className="dashboard-page">
      <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '20px' }}>
        <h2>Independent Traffic Dashboard</h2>
        <button onClick={() => setViewMode('calendar')}>Back to Calendar</button>
      </div>
      <div style={{ height: '500px', background: '#fff', padding: '20px', borderRadius: '10px', boxShadow: '0 4px 6px rgba(0,0,0,0.1)' }}>
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={pingData}>
            <CartesianGrid strokeDasharray="3 3" />
            <XAxis dataKey="time" />
            <YAxis label={{ value: 'RTT (ms)', angle: -90, position: 'insideLeft' }} />
            <Tooltip />
            <Line type="monotone" dataKey="rtt" stroke="#3b82f6" strokeWidth={3} dot={false} />
          </LineChart>
        </ResponsiveContainer>
      </div>
    </div>
  );

  const renderCalendar = () => (
    <FullCalendar
      ref={calendarRef}
      plugins={[dayGridPlugin, timeGridPlugin, interactionPlugin]}
      initialView="timeGridDay"
      events={events}
      headerToolbar={{
        left: 'prev,next today realtimeBtn',
        center: 'title',
        right: 'dayGridMonth,timeGridWeek,timeGridDay'
      }}
      customButtons={{
        realtimeBtn: {
          text: 'Real Time',
          click: switchToDashboard
        }
      }}
      selectable={isAuthenticated}
      select={(info) => openModal('create', { start: info.startStr, end: info.endStr })}
      eventClick={(info) => {
        if (!isAuthenticated) return;
        openModal('edit', {
          id: info.event.id,
          title: info.event.title,
          start: info.event.startStr.substring(0, 16),
          end: info.event.endStr.substring(0, 16),
          category: info.event.extendedProps.category,
          devices: info.event.extendedProps.devices
        });
      }}
      height="85vh"
    />
  );

  // --- Main Return ---
  return (
    <div style={{ padding: '20px' }}>
      <h1>Network Event Manager</h1>
      
      {/* --- Auth Screen Overlay --- */}
      {!isAuthenticated && (
        <form onSubmit={handleAuth} className="auth-overlay">
          <h2>Admin Login</h2>
          <input type="password" ref={passwordRef} placeholder="Password" />
          <button type="submit">Login</button>
          {authError && <p style={{ color: 'red' }}>{authError}</p>}
        </form>
      )}

      {/* Switch between Dashboard and Calendar views */}
      {viewMode === 'calendar' ? renderCalendar() : renderDashboard()}

      {/* Event Modal (Shows in both modes if triggered) */}
      {modalState.show && (
        <div className="modal-backdrop">
          <form className="modal-content" onSubmit={handleSubmitEvent} key={modalState.data?.id || modalState.data?.start}>
            <h3>{modalState.mode === 'create' ? 'Add Event' : 'Edit Event'}</h3>
            
            <label>Event Name</label>
            <input name="title" defaultValue={modalState.data?.title} required />

            <label>Start Time</label>
            <input name="start_ts" type="datetime-local" defaultValue={modalState.data?.start} required />

            <label>End Time</label>
            <input name="end_ts" type="datetime-local" defaultValue={modalState.data?.end} required />

            <label>Number of Devices</label>
            <input name="devices" type="number" defaultValue={modalState.data?.devices || 1} />
            
            <label>Category</label>
            <select name="category" defaultValue={modalState.data?.category || 'video_session'}>
              <option value="video_session">Video Session</option>
              <option value="system_update">System Update!!!!!</option>
            </select>

            <div className="modal-actions">
              <button type="button" onClick={closeModal}>Cancel</button>
              {modalState.mode === 'edit' && (
                <button type="button" className="delete-btn" onClick={handleDeleteEvent}>Delete</button>
              )}
              <button type="submit">Save</button>
            </div>
          </form>
        </div>
      )}
    </div>
  );
}

export default App;
