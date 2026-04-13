import React, { useState, useEffect } from 'react';
import FullCalendar from '@fullcalendar/react'
import dayGridPlugin from '@fullcalendar/daygrid'
import timeGridPlugin from '@fullcalendar/timegrid'
import interactionPlugin from '@fullcalendar/interaction'

function App() {
  const [events, setEvents] = useState([]);

  // Fetch existing events from DB on load
  const fetchEvents = async () => {
    try {
      const response = await fetch('http://localhost:8000/api/event_sessions/');
      const data = await response.json();
      
      // Map API response to FullCalendar format
      const formattedEvents = data.map(evt => ({
        id: evt.session_id,
        title: evt.event_name,
        start: evt.start_ts,
        end: evt.end_ts,
        // color: evt.session_category === 'system_update' ? 'red' : 'blue',
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

  // Admin check function
  const PASSWORD = import.meta.env.VITE_PASSWORD;
  const isAdmin = () => {
    const password = prompt('Enter Admin Password:');
    return password === PASSWORD; // Replace with a better auth mechanism
  };

  // --- CREATE ---
  const handleDateSelect = async (selectInfo) => {
    if (!isAdmin()) return;

    const title = prompt('Enter Event Name:');
    if (!title) return;

    const devices = prompt('Number of expected devices:', '1');
    const category = prompt('Category (video_session or system_update):', 'video_session');

    const newEvent = {
      event_name: title,
      start_ts: selectInfo.startStr, 
      end_ts: selectInfo.endStr,
      expected_devices: parseInt(devices) || 1,
      session_category: category 
    };

    try {
      const response = await fetch('http://localhost:8000/api/event_sessions/', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(newEvent),
      });

      if (response.ok) {
        alert('Event created!');
        fetchEvents(); // Refresh data
      }
    } catch (err) {
      console.error('Error:', err);
    }
  };

  // --- UPDATE / DELETE ---
  const handleEventClick = async (clickInfo) => {
    if (!isAdmin()) return;

    const action = prompt('Enter "delete" to remove, or "update" to change name:', 'update');
    
    if (action === 'delete') {
      if (window.confirm(`Are you sure you want to delete '${clickInfo.event.title}'?`)) {
        try {
          await fetch(`http://localhost:8000/api/event_sessions/${clickInfo.event.id}/`, {
            method: 'DELETE',
          });
          clickInfo.event.remove();
          alert('Event deleted');
        } catch (err) {
          console.error('Delete error:', err);
        }
      }
    } else if (action === 'update') {
      const newTitle = prompt('New Event Name:', clickInfo.event.title);
      if (!newTitle) return;

      try {
        const response = await fetch(`http://localhost:8000/api/event_sessions/${clickInfo.event.id}/`, {
          method: 'PATCH',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ event_name: newTitle }),
        });

        if (response.ok) {
          fetchEvents(); // Refresh
          alert('Event updated');
        }
      } catch (err) {
        console.error('Update error:', err);
      }
    }
  };

  return (
    <div style={{ padding: '20px' }}>
      <h1>RTT Prediction Calendar</h1>
      <FullCalendar
        plugins={[dayGridPlugin, timeGridPlugin, interactionPlugin]}
        initialView="timeGridDay"
        headerToolbar={{
          left: 'prev,next today',
          center: 'title',
          right: 'dayGridMonth,timeGridWeek,timeGridDay'
        }}
        editable={true}
        selectable={true}
        selectMirror={true}
        dayMaxEvents={true}
        
        // --- Granularity Settings ---
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
