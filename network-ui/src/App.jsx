import React, { useState, useEffect, useRef } from 'react';
import FullCalendar from '@fullcalendar/react';
import dayGridPlugin from '@fullcalendar/daygrid';
import timeGridPlugin from '@fullcalendar/timegrid';
import interactionPlugin from '@fullcalendar/interaction';
import './App.css'; // Assuming you add the CSS below

function App() {
  const [events, setEvents] = useState([]);
  const [isAuthenticated, setIsAuthenticated] = useState(false);
  const [modalState, setModalState] = useState({ show: false, mode: 'create', data: null });
  const [authError, setAuthError] = useState('');
  const passwordRef = useRef(null);

  const PASSWORD = import.meta.env.VITE_PASSWORD;

  // Fetch events
  const fetchEvents = async () => {
    try {
      const response = await fetch('http://localhost:8000/api/event_sessions/');
      const data = await response.json();
      const formattedEvents = data.map(evt => ({
        id: evt.session_id,
        title: evt.event_name,
        start: evt.start_ts,
        end: evt.end_ts,
        extendedProps: {
          category: evt.session_category,
          devices: evt.expected_devices
        }
      }));
      setEvents(formattedEvents);
    } catch (error) {
      console.error('Error fetching events:', error);
    }
  };

  useEffect(() => {
    fetchEvents();
  }, []);

  // --- Auth Handler ---
  const handleAuth = (e) => {
    e.preventDefault();
    if (passwordRef.current.value === PASSWORD) {
      setIsAuthenticated(true);
      setAuthError('');
    } else {
      setAuthError('Incorrect Password');
    }
  };

  // --- Modal Handlers ---
  const openModal = (mode, data = null) => {
    setModalState({ show: true, mode, data });
  };

  const closeModal = () => {
    setModalState({ show: false, mode: 'create', data: null });
  };

  // --- CRUD Operations ---
  const handleDateSelect = (selectInfo) => {
    if (!isAuthenticated) return;
    openModal('create', { start: selectInfo.startStr, end: selectInfo.endStr });
  };

  const handleEventClick = (clickInfo) => {
    if (!isAuthenticated) return;
    openModal('edit', {
      id: clickInfo.event.id,
      title: clickInfo.event.title,
      start: clickInfo.event.startStr,
      end: clickInfo.event.endStr,
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
      session_category: formData.get('category')
    };

    try {
      if (modalState.mode === 'create') {
        const payload = { ...eventData, start_ts: modalState.data.start, end_ts: modalState.data.end };
        await fetch('http://localhost:8000/api/event_sessions/', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(payload),
        });
      } else {
        await fetch(`http://localhost:8000/api/event_sessions/${modalState.data.id}/`, {
          method: 'PATCH',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(eventData),
        });
      }
      fetchEvents();
      closeModal();
    } catch (err) {
      console.error('Error saving event:', err);
    }
  };

  const handleDeleteEvent = async () => {
    if (!window.confirm('Are you sure?')) return;
    try {
      await fetch(`http://localhost:8000/api/event_sessions/${modalState.data.id}/`, {
        method: 'DELETE',
      });
      fetchEvents();
      closeModal();
    } catch (err) {
      console.error('Delete error:', err);
    }
  };

  return (
    <div style={{ padding: '20px' }}>
      <h1>RTT Prediction Calendar</h1>

      {/* --- Auth Screen --- */}
      {!isAuthenticated && (
        <form onSubmit={handleAuth} className="auth-overlay">
          <h2>Enter Admin Password</h2>
          <input type="password" ref={passwordRef} placeholder="Password" />
          <button type="submit">Login</button>
          {authError && <p style={{ color: 'red' }}>{authError}</p>}
        </form>
      )}

      {/* --- Event Modal --- */}
      {modalState.show && (
        <div className="modal-backdrop">
          <form className="modal-content" onSubmit={handleSubmitEvent}>
            <h3>{modalState.mode === 'create' ? 'Add Event' : 'Edit Event'}</h3>
            <input name="title" defaultValue={modalState.data?.title} placeholder="Title" required />
            <input name="devices" type="number" defaultValue={modalState.data?.devices || 1} placeholder="Devices" />
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

      <FullCalendar
        plugins={[dayGridPlugin, timeGridPlugin, interactionPlugin]}
        initialView="timeGridDay"
        headerToolbar={{ left: 'prev,next today', center: 'title', right: 'dayGridMonth,timeGridWeek,timeGridDay' }}
        editable={isAuthenticated} // Only editable if authenticated
        selectable={isAuthenticated} // Only selectable if authenticated
        selectMirror={true}
        dayMaxEvents={true}
        slotDuration={'00:05:00'} // Lines every 5 mins
        snapDuration={'00:01:00'} // Can drag/resize in 1-min increments
        select={handleDateSelect}
        eventClick={handleEventClick}
        events={events}
        height="85vh"
      />
    </div>
  );
}

export default App;
