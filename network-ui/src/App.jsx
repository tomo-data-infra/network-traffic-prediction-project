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
  const [events, setEvents] = useState([]);
  const [pingData, setPingData] = useState([]); // Traffic data state
  const [isAuthenticated, setIsAuthenticated] = useState(false);
  const [modalState, setModalState] = useState({ show: false, mode: 'create', data: null });
  const [authError, setAuthError] = useState('');
  
  // --- Refs ---
  const calendarRef = useRef(null);
  const passwordRef = useRef(null);

  const PASSWORD = import.meta.env.VITE_PASSWORD;

  // --- 1. Fetch Traffic (The "Flask Recreation" part) ---
  const fetchTraffic = async (start, end) => {
    try {
      const response = await fetch(`http://localhost:8000/api/ping_data?start=${start}&end=${end}`);
      const data = await response.json();
      const chartPoints = data.times.map((t, i) => ({
        time: new Date(t).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
        rtt: data.features[i][0] // Adjust index based on your features.py output
      }));
      setPingData(chartPoints);
    } catch (err) {
      console.error("Traffic fetch error:", err);
    }
  };

  // --- 2. Fetch Events (With Background Layer) ---
  const fetchEvents = async () => {
    try {
      const response = await fetch('http://localhost:8000/api/event_sessions/');
      const data = await response.json();
      const allEntries = [];

      data.forEach(evt => {
        // Foreground: The actual interactive event
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
        // Background: The "Third Layer" visual highlight
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
    // Initial traffic: +/- 30m from now
    const now = new Date();
    fetchTraffic(new Date(now - 30*60000).toISOString(), new Date(now + 30*60000).toISOString());
  }, []);

  // --- Auth Handler (Preserved) ---
  const handleAuth = (e) => {
    e.preventDefault();
    if (passwordRef.current.value === PASSWORD) {
      setIsAuthenticated(true);
      setAuthError('');
    } else {
      setAuthError('Incorrect Password');
    }
  };

  // --- Modal Handlers (Preserved) ---
  const openModal = (mode, data = null) => setModalState({ show: true, mode, data });
  const closeModal = () => setModalState({ show: false, mode: 'create', data: null });

  // --- CRUD Operations (Preserved & Enhanced) ---
  const handleDateSelect = (selectInfo) => {
    if (!isAuthenticated) return;
    openModal('create', { start: selectInfo.startStr, end: selectInfo.endStr });
  };

  const handleEventClick = (clickInfo) => {
    if (!isAuthenticated) return;
    
    // When clicked, update the chart window to match the event
    fetchTraffic(clickInfo.event.startStr, clickInfo.event.endStr);

    openModal('edit', {
      id: clickInfo.event.id,
      title: clickInfo.event.title,
      start: clickInfo.event.startStr.substring(0, 16),
      end: clickInfo.event.endStr.substring(0, 16),
      category: clickInfo.event.extendedProps.category,
      devices: clickInfo.event.extendedProps.devices
    });
  };

  const handleSubmitEvent = async (e) => {
    e.preventDefault();
    const formData = new FormData(e.target);
    const eventData = {
      event_name: formData.get('title'),
      expected_devices: parseInt(formData.get('devices')),
      session_category: formData.get('category'),
      start_ts: formData.get('start_ts'), // Updated to allow manual time edits
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

  const handleRealTimeView = () => {
    const calendarApi = calendarRef.current.getApi();
    const now = new Date();
    calendarApi.gotoDate(now);
    calendarApi.changeView('timeGridDay');
    fetchTraffic(new Date(now - 30*60000).toISOString(), new Date(now + 30*60000).toISOString());
  };

  return (
    <div style={{ padding: '20px' }}>
      <h1>Network Event Dashboard</h1>

      {/* --- Auth Screen Overlay --- */}
      {!isAuthenticated && (
        <form onSubmit={handleAuth} className="auth-overlay">
          <h2>Admin Login</h2>
          <input type="password" ref={passwordRef} placeholder="Password" />
          <button type="submit">Login</button>
          {authError && <p style={{ color: 'red' }}>{authError}</p>}
        </form>
      )}

      {/* --- Traffic Chart (Integrated Top Section) --- */}
      <div className="chart-container" style={{ height: '250px', marginBottom: '20px', background: '#fff', padding: '15px', borderRadius: '8px', boxShadow: '0 2px 5px rgba(0,0,0,0.1)' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between' }}>
          <h3 style={{ margin: 0 }}>RTT Traffic Analysis</h3>
          <button onClick={handleRealTimeView}>View Real-Time (±30m)</button>
        </div>
        <ResponsiveContainer width="100%" height="90%">
          <LineChart data={pingData}>
            <CartesianGrid strokeDasharray="3 3" />
            <XAxis dataKey="time" />
            <YAxis label={{ value: 'ms', angle: -90, position: 'insideLeft' }} />
            <Tooltip />
            <Line type="monotone" dataKey="rtt" stroke="#3b82f6" dot={false} strokeWidth={2} />
          </LineChart>
        </ResponsiveContainer>
      </div>

      {/* --- Event Modal --- */}
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

            <label>Devices</label>
            <input name="devices" type="number" defaultValue={modalState.data?.devices || 1} />

            <label>Category</label>
            <select name="category" defaultValue={modalState.data?.category}>
              <option value="video_session">Video Session</option>
              <option value="system_update">System Update</option>
            </select>

            <div className="modal-actions">
              <button type="button" onClick={closeModal}>Cancel</button>
              {modalState.mode === 'edit' && <button type="button" className="delete-btn" onClick={handleDeleteEvent}>Delete</button>}
              <button type="submit">Save</button>
            </div>
          </form>
        </div>
      )}

      <FullCalendar
        ref={calendarRef}
        plugins={[dayGridPlugin, timeGridPlugin, interactionPlugin]}
        initialView="timeGridDay"
        events={events}
        selectable={isAuthenticated}
        select={handleDateSelect}
        eventClick={handleEventClick}
        headerToolbar={{ left: 'prev,next today', center: 'title', right: 'dayGridMonth,timeGridWeek,timeGridDay' }}
        height="70vh"
      />
    </div>
  );
}

export default App;
