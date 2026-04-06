import React, { useState, useEffect } from 'react';
import FullCalendar from '@fullcalendar/react'
import dayGridPlugin from '@fullcalendar/daygrid'
import timeGridPlugin from '@fullcalendar/timegrid'
import interactionPlugin from '@fullcalendar/interaction'

function App() {
  const [events, setEvents] = useState([]);

  // 1. Fetch existing events from DB on load
  useEffect(() => {
    fetch('http://localhost:8000/api/event_sessions/')
      .then(res => res.json())
      .then(data => setEvents(data));
  }, []);

  // 2. Logic to handle "Click and Drag" to create new event
    const handleDateSelect = async (selectInfo) => {
    const calendarApi = selectInfo.view.calendar;
    calendarApi.unselect(); 

    // 1. Collect inputs via prompts (or a custom modal later)
    const title = prompt('Enter Event Name:');
    if (!title) return;

    const devices = prompt('Number of expected devices:', '1');
    const category = prompt('Category (video_session or system_update):', 'video_session');

    // 2. Map FullCalendar strings to your DB schema
    const newEvent = {
      event_name: title,
      start_ts: selectInfo.startStr, // FullCalendar provides ISO8601 strings
      end_ts: selectInfo.endStr,
      expected_devices: parseInt(devices) || 1,
      session_category: category // Must exactly match your PostgreSQL 'event_type' enum
    };

    try {
      // 3. POST to Django API
      const response = await fetch('http://localhost:8000/api/event_sessions/', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(newEvent),
      });

      if (response.ok) {
        const savedEvent = await response.json();
        
        // Format for FullCalendar UI (maps session_id to id)
        const uiEvent = {
          id: savedEvent.session_id,
          title: savedEvent.event_name,
          start: savedEvent.start_ts,
          end: savedEvent.end_ts,
          extendedProps: {
            category: savedEvent.session_category,
            devices: savedEvent.expected_devices
          }
        };

        setEvents([...events, uiEvent]); 
        alert('Event saved to WSL PostgreSQL!');
      } else {
        const errorData = await response.json();
        console.error('Server Error:', errorData);
        alert('Failed to save: ' + JSON.stringify(errorData));
      }
    } catch (err) {
      console.error('Network Error:', err);
    }
  };

  return (
    //<div style={{ width: '100vw', height: '100vh' }}>
    <div style={{ padding: '20px' }}>
      <h1>RTT Prediction Calendar</h1>
      <FullCalendar
        plugins={[dayGridPlugin, timeGridPlugin, interactionPlugin]}
        initialView="timeGridDay" // Best for viewing hourly RTT data
        headerToolbar={{
          left: 'prev,next today',
          center: 'title',
          right: 'dayGridMonth,timeGridWeek,timeGridDay'
        }}
        selectable={true} // Allows clicking/dragging
        select={handleDateSelect}
        events={events} // Maps DB data to the UI
      />
    </div>
  );
}

export default App;
