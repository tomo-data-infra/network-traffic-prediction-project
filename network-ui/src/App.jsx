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
  const [range, setRange] = useState({
    start: new Date(new Date() - 30 * 60000).toISOString().substring(0, 16),
    end: new Date(new Date() + 30 * 60000).toISOString().substring(0, 16)
  });

  // --- Refs --- 
  const calendarRef = useRef(null);
  const passwordRef = useRef(null);
  const DJANGO_URL = "http://localhost:8000/api"; // Your Django Server
  const PASSWORD = import.meta.env.VITE_PASSWORD;

  // FETCH TRAFFIC FROM DJANGO
  const fetchTraffic = async (start, end) => {
    try {
      const res = await fetch(`${DJANGO_URL}/ping_data/?start=${start}&end=${end}`);
      const data = await res.json();
      const chartPoints = data.times.map((t, i) => ({
        time: new Date(t).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
        rtt: data.features[i][0] 
      }));
      setPingData(chartPoints);
    } catch (err) {
      console.error("Django Traffic Error:", err);
    }
  };

  // FETCH EVENTS FROM DJANGO
  const fetchEvents = async () => {
    try {
      const res = await fetch(`${DJANGO_URL}/event_sessions/`);
      const data = await res.json();
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
    } catch (err) {
      console.error("Django Events Error:", err);
    }
  };

  useEffect(() => {
    fetchEvents();
    // Force a small delay to ensure FullCalendar recalculates its size
    if (viewMode === 'calendar' && calendarRef.current) {
      const calendarApi = calendarRef.current.getApi();
      setTimeout(() => {
        calendarApi.updateSize();
      }, 100);
    }
  }, [viewMode]); // Trigger every time we switch back to calendar

  // --- Handlers ---
  const switchToDashboard = () => {
    const now = new Date();
    fetchTraffic(new Date(now - 30*60000).toISOString(), new Date(now + 30*60000).toISOString());
    setViewMode('dashboard');
  };

  // UI RENDER HELPERS
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
    <div className="dashboard-view">
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: '10px' }}>
        <h2>Traffic Analysis</h2>
        
        {/* Manual Range Controls */}
        <div style={{ display: 'flex', gap: '10px', alignItems: 'center' }}>
          <input 
            type="datetime-local" 
            value={range.start} 
            onChange={(e) => setRange({ ...range, start: e.target.value })}
          />
          <span>to</span>
          <input 
            type="datetime-local" 
            value={range.end} 
            onChange={(e) => setRange({ ...range, end: e.target.value })}
          />
          <button onClick={() => fetchTraffic(range.start, range.end)}>Update Range</button>
        </div>

        <button onClick={() => setViewMode('calendar')}>Back to Calendar</button>
      </div>

      <div style={{ height: '450px', background: '#fff', padding: '20px', marginTop: '20px', borderRadius: '8px' }}>
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={pingData}>
            <CartesianGrid strokeDasharray="3 3" />
            <XAxis dataKey="time" />
            <YAxis />
            <Tooltip />
            <Line type="monotone" dataKey="rtt" stroke="#3b82f6" strokeWidth={3} dot={false} />
          </LineChart>
        </ResponsiveContainer>
      </div>
    </div>
  );

  const renderCalendar = () => (
    <FullCalendar
      key={events.length} // <--- ADD THIS. It forces refresh when data arrives
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
          text: 'Real Time Monitor',
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
      <h1>Network Traffic Monitor</h1>

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
              <option value="system_update">System Update</option>
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
