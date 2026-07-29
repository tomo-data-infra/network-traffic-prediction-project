import React, { useState, useEffect, useRef } from 'react';
import FullCalendar from '@fullcalendar/react';
import dayGridPlugin from '@fullcalendar/daygrid';
import timeGridPlugin from '@fullcalendar/timegrid';
import interactionPlugin from '@fullcalendar/interaction';
// Import Recharts for the traffic visualization
import { 
  AreaChart,
  Area,
  BarChart, 
  Bar, 
  XAxis, 
  YAxis, 
  CartesianGrid, 
  Tooltip, 
  ResponsiveContainer,
  Cell
} from 'recharts';
import './App.css'; 

function App() {
  // --- States ---
  const [viewMode, setViewMode] = useState('calendar'); // 'calendar' or 'dashboard'
  const [events, setEvents] = useState([]);
  const [pingData, setPingData] = useState([]); // Traffic data state 
  const [dashboardEvents, setDashboardEvents] = useState([]); // Real-time concurrent events track
  const [isAuthenticated, setIsAuthenticated] = useState(false);
  const [modalState, setModalState] = useState({ show: false, mode: 'create', data: null });
  const [authError, setAuthError] = useState('');
  const getJSTStringWithOffset = (minutesOffset = 0) => {
    const currentMs = Date.now() + (minutesOffset * 60000);
    // Explicitly add 9 hours in milliseconds to offset the native system clock string conversion
    const jstDate = new Date(currentMs + (9 * 60 * 60 * 1000)); 
    return jstDate.toISOString().substring(0, 16);
  };

  const [range, setRange] = useState({
    start: getJSTStringWithOffset(-30), // Current JST minus 30 minutes
    end: getJSTStringWithOffset(30)     // Current JST plus 30 minutes
  });

  // --- AI Chat Agent States ---
  const [isChatOpen, setIsChatOpen] = useState(false);
  const [chatInput, setChatInput] = useState('');
  const [chatHistory, setChatHistory] = useState([
    { sender: 'agent', text: 'Hello! Ask me network telemetry parameters in English or Japanese. (e.g. "What was the highest RTT on May 22?")' }
  ]);
  const [isAgentTyping, setIsAgentTyping] = useState(false);

  // --- Refs --- 
  const calendarRef = useRef(null);
  const passwordRef = useRef(null);
  const DJANGO_URL = "http://localhost:8000/api"; 
  const PASSWORD = import.meta.env.VITE_PASSWORD;

  // --- API Handlers FETCH TRAFFIC FROM DJANGO --- --- Updated fetchTraffic to bundle actual and forecast pipelines ---
  const fetchTraffic = async (start, end) => {
    try {
      const res = await fetch(`${DJANGO_URL}/ping_data/?start=${start}&end=${end}`);
      const data = await res.json();

      // Check if data exists
      if (!data.times || data.times.length === 0) {
        setPingData([]);
        setDashboardEvents([]);
        return;
      }

      const now = new Date(); // Current real-time clock anchor
      // Map combined properties into unified array models for chart ingestion
      // Map backend datasets into synchronous React chart coordinates
      // Combine 'times' and 'features' into a format Recharts understands
      // Map combined properties into unified array models for chart ingestion
      const chartPoints = data.times.map((t, i) => {
        const binTime = new Date(t);
        const isFuture = binTime > now; // Check if this time slot is in the future

        const rtt = data.features[i];
        const jitter = data.jitters ? data.jitters[i] : 0;
        
        // Find matching minute item in forecast array matrix
        const matchingForecast = data.forecast ? data.forecast.find(f => 
          new Date(f.ts).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }) === 
          binTime.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
        ) : null;

        return {
          time: binTime.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
          rawTime: binTime, 
          
          // Hide actual metrics completely if the time slot has not come yet
          rtt: isFuture ? null : parseFloat(Number(rtt).toFixed(2)),
          jitterHigh: isFuture ? null : parseFloat(Number(rtt + jitter).toFixed(2)),
          jitterLow: isFuture ? null : parseFloat(Number(Math.max(0, rtt - jitter)).toFixed(2)), 
          loss: isFuture ? null : (data.loss_rates ? data.loss_rates[i] : 0),
          
          // Pull the statistical prediction profiles
          predRtt: matchingForecast ? matchingForecast.pred_rtt : null,
          predLoss: matchingForecast ? matchingForecast.pred_loss : 0
        };
      });

      setPingData(chartPoints);
      if (data.events) setDashboardEvents(data.events);
    } catch (err) {
      console.error("Traffic Sync Failure:", err);
    }
  };

  const handleTrainModel = async () => {
    if (!window.confirm("Retrain the statistical baseline profile using the past 30 days of data?")) return;
    try {
      const res = await fetch(`${DJANGO_URL}/train_model/`, { method: 'POST' });
      const data = await res.json();
      alert(data.status || "Training complete!");
      handleManualUpdate(); // Force visualization refresh
    } catch (err) {
      console.error("Training Error:", err);
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
      console.error("Events Fetch Exception:", err);
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
  // This handles the "Real Time" (latest 30 mins)
  const switchToDashboard = () => {
    // Generate accurate local time strings using our utility helper function
    const jstStartString = getJSTStringWithOffset(-30);
    const jstEndString = getJSTStringWithOffset(0);
    
    // Update the UI inputs to show the 30m window
    setRange({ start: jstStartString, end: jstEndString });

    fetchTraffic(jstStartString, jstEndString);
    setViewMode('dashboard');
  };

    // This handles the "Designated Period" from your inputs
  const handleManualUpdate = () => {
    // Use the values from your datetime-local inputs
    fetchTraffic(range.start, range.end);
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

  // --- Overlapping Events Calculations ---
  // Processes matching events and assigns distinct lane indices to handle stacking
  const computeEventTimelineGantt = () => {
    // 1. Guard check to ensure both datasets are present before iterating
    if (!pingData || pingData.length === 0 || !dashboardEvents || dashboardEvents.length === 0) {
      return { processedGantt: [], totalLanes: 0 };
    }

    const formattedGanttRows = [];
    const executionLanes = []; // Stacks track allocation values to split overlaps cleanly

    dashboardEvents.forEach(evt => {
      const eStart = new Date(evt.start);
      const eEnd = new Date(evt.end);

      // 2. Multi-lane tracking allocation logic
      let assignedLane = 0;
      while (true) {
        if (!executionLanes[assignedLane] || executionLanes[assignedLane] <= eStart) {
          executionLanes[assignedLane] = eEnd; // Store completion point for this track lane
          break;
        }
        assignedLane++; // Increment lane pointer until an open time slot is discovered
      }

      // 3. FIX: Iterate directly over the clean array objects instead of linear string searching
      pingData.forEach(binPoint => {
        // Evaluate the continuous raw timestamp to ensure absolute chronological accuracy
        if (binPoint.rawTime >= eStart && binPoint.rawTime <= eEnd) {
          formattedGanttRows.push({
            time: binPoint.time, // The display X-Axis timestamp string
            [`lane_${assignedLane}`]: 1, // High marker payload to draw a standard block segment
            eventTitle: evt.title,
            category: evt.category,
            devices: evt.devices,
            duration: `${eStart.toLocaleTimeString([], {hour: '2-digit', minute:'2-digit'})} - ${eEnd.toLocaleTimeString([], {hour: '2-digit', minute:'2-digit'})}`
          });
        }
      });
    });

    return { processedGantt: formattedGanttRows, totalLanes: executionLanes.length };
  };

  const { processedGantt, totalLanes } = computeEventTimelineGantt();

  // Combines performance graphs with the current event row blocks
  const integratedChartData = pingData.map(p => {
    const matchingGanttSlices = processedGantt.filter(g => g.time === p.time);
    const combinedPoint = { ...p };
    matchingGanttSlices.forEach(slice => {
      Object.keys(slice).forEach(k => {
        if (k.startsWith('lane_') || k === 'eventTitle' || k === 'devices' || k === 'duration') {
          combinedPoint[k] = slice[k];
        }
      });
    });
    return combinedPoint;
  });

  const handleSendMessage = async (e) => {
    e.preventDefault();
    if (!chatInput.trim()) return;

    const userMessage = chatInput.trim();
    setChatHistory(prev => [...prev, { sender: 'user', text: userMessage }]);
    setChatInput('');
    setIsAgentTyping(true);

    try {
      const res = await fetch(`${DJANGO_URL}/netops_agent_core/`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ question: userMessage }),
      });
      const data = await res.json();
      
      setChatHistory(prev => [...prev, { sender: 'agent', text: data.answer }]);
    } catch (err) {
      console.error("Agent communication failure:", err);
      setChatHistory(prev => [...prev, { sender: 'agent', text: "I don't know. (Network connectivity issue)" }]);
    } finally {
      setIsAgentTyping(false);
    }
  };

  // --- Render Helpers (Defined ABOVE the main return) ---
  // --- Replace the Top Control Row inside your renderDashboard helper ---
  const renderDashboard = () => (
    <div className="dashboard-view" style={{ background: '#f9fafb', paddingTop: '10px' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '20px' }}>
        <h2>Traffic Dashboard</h2>
        
        {/* Control Row Layout Panel */}
        <div style={{ display: 'flex', gap: '8px', alignItems: 'center' }}>
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
          
          <button onClick={handleManualUpdate} style={{ padding: '6px 12px', background: '#2563eb', color: '#fff', border: 'none', borderRadius: '4px', cursor: 'pointer', fontWeight: 'bold' }}>
            Update Window
          </button>

          <button onClick={() => { handleManualUpdate(); alert("Projected curves overlay refreshed based on calendar parameters."); }} style={{ padding: '6px 12px', background: '#10b981', color: '#fff', border: 'none', borderRadius: '4px', cursor: 'pointer', fontWeight: 'bold' }}>
            Predict Traffic
          </button>

          <button onClick={handleTrainModel} style={{ padding: '6px 12px', background: '#4b5563', color: '#fff', border: 'none', borderRadius: '4px', cursor: 'pointer', fontSize: '12px' }}>
            Train Model
          </button>
        </div>
        <button onClick={() => setViewMode('calendar')} style={{ padding: '6px 12px', cursor: 'pointer' }}>Back to Calendar</button>
      </div>

      {/* TIER 1: Latency Profile Line Chart (Stretched Y-Axis / Text-Only Jitter) */}
      <div style={{ height: '320px', background: '#fff', padding: '20px', borderRadius: '8px', boxShadow: '0 1px 3px rgba(0,0,0,0.1)', marginBottom: '20px' }}>
        <h4 style={{ margin: '0 0 10px 0', color: '#4b5563' }}>Latency Profile (Actual vs Predicted)</h4>
        <ResponsiveContainer width="100%" height="90%">
          <AreaChart data={integratedChartData}>
            <CartesianGrid strokeDasharray="3 3" stroke="#f3f4f6" />
            <XAxis dataKey="time" tick={{ fill: '#4b5563', fontSize: 11 }} />
            <YAxis width={60} label={{ value: 'ms', angle: -90, position: 'insideLeft' }} domain={[0, 'auto']} /> 
            
            <Tooltip 
              formatter={(value, name, props) => {
                if (name === "Actual Mean RTT" && props.payload.rtt !== null) {
                  return [
                    `${value} ms (Jitter Upper Boundary: ${props.payload.jitterHigh} ms, Jitter Lower Boundary: ${props.payload.jitterLow} ms)`,
                    name
                  ];
                }
                return [`${value} ms`, name];
              }}
            />
            
            <Area type="monotone" dataKey="rtt" stroke="#111827" strokeWidth={2.5} fill="none" name="Actual Mean RTT" connectNulls />
            <Area type="monotone" dataKey="predRtt" stroke="#dc2626" strokeWidth={2.5} strokeDasharray="6 4" fill="none" name="Predicted Mean RTT" connectNulls />
          </AreaChart>
        </ResponsiveContainer>
      </div>

      {/* TIER 2: Packet Loss Histogram */}
      <div style={{ height: '180px', background: '#fff', padding: '20px', borderRadius: '8px', boxShadow: '0 1px 3px rgba(0,0,0,0.1)', marginBottom: '20px' }}>
        <h4 style={{ margin: '0 0 10px 0', color: '#4b5563' }}>Packet Loss Ratios</h4>
        <ResponsiveContainer width="100%" height="90%">
          <BarChart data={integratedChartData}>
            <CartesianGrid strokeDasharray="3 3" stroke="#f3f4f6" />
            <XAxis dataKey="time" tick={{ fill: '#4b5563', fontSize: 11 }} />
            <YAxis width={60} domain={[0, 1]} tickFormatter={(val) => `${(val * 100).toFixed(0)}%`} tick={{ fill: '#4b5563' }} />
            <Tooltip formatter={(val) => [`${(val * 100).toFixed(1)}%`, 'Drop Density']} />
            <Bar dataKey="loss">
              {integratedChartData.map((entry, index) => {
                const isHeavyPrediction = entry.predLoss > 0.15;
                const cellColor = isHeavyPrediction 
                  ? `rgba(153, 27, 27, ${Math.max(0.4, entry.loss || entry.predLoss)})` 
                  : `rgba(239, 68, 68, ${Math.max(0.15, entry.loss)})`; 
                return <Cell key={`cell-${index}`} fill={cellColor} />;
              })}
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      </div>

      {/* TIER 3: Event Scheduler Lane Tracker (Perfect Vertical Alignment) */}
      <div style={{ height: `${120 + (totalLanes * 40)}px`, background: '#fff', padding: '20px', borderRadius: '8px', boxShadow: '0 1px 3px rgba(0,0,0,0.1)' }}>
        <h4 style={{ margin: '0 0 15px 0', color: '#4b5563' }}>Event Scheduler</h4>
        {totalLanes === 0 ? (
          <p style={{ color: '#9ca3af', fontSize: '13px' }}>No event is monitored.</p>
        ) : (
          <ResponsiveContainer width="100%" height="80%">
            <BarChart data={integratedChartData} barGap={4}>
              <CartesianGrid strokeDasharray="3 3" stroke="#f3f4f6" />
              <XAxis dataKey="time" tick={{ fill: '#4b5563', fontSize: 11 }} />
              <YAxis width={60} domain={[0, 1]} tickFormatter={() => ''} axisLine={true} tickLine={false} />
              <Tooltip 
                cursor={{ fill: '#f3f4f6', opacity: 0.4 }}
                formatter={(value, name, props) => {
                  if (!props.payload.eventTitle) return null;
                  return [
                    `Devices: ${props.payload.devices} (${props.payload.duration})`, 
                    `Event: ${props.payload.eventTitle}`
                  ];
                }} 
              />
              {Array.from({ length: totalLanes }).map((_, laneIdx) => (
                <Bar 
                  key={`lane_${laneIdx}`} 
                  dataKey={`lane_${laneIdx}`} 
                  stackId="gantt" 
                  fill="#3b82f6" 
                  radius={4} 
                  maxBarSize={28} 
                />
              ))}
            </BarChart>
          </ResponsiveContainer>
        )}
      </div>
    </div>
  );

  // --- Calendar View Sub-render ---
  const renderCalendar = () => (
    <div className="calendar-view">
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '20px' }}>
        <h2>Event Calendar</h2>
        <button onClick={switchToDashboard} className="btn-dashboard" style={{ padding: '8px 16px', background: '#111827', color: '#fff', border: 'none', borderRadius: '4px', cursor: 'pointer' }}>View Dashboard</button>
      </div>
      <FullCalendar
        key={events.length} 
        ref={calendarRef}
        plugins={[dayGridPlugin, timeGridPlugin, interactionPlugin]}
        initialView="timeGridWeek"
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
    </div>
  );

  // --- Main Structural Return ---
  return (
    /* MASTER WRAPPER NODE - RETAINING THE APP-CONTAINER CLASS TYPE */
    <div className="app-container" style={{ padding: '20px', fontFamily: 'sans-serif', position: 'relative', minHeight: '100vh' }}>
      
      {/* Global Framework Header & Admin Status Bar */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', borderBottom: '1px solid #e5e7eb', paddingBottom: '10px', marginBottom: '20px' }}>
        <h1>Network Traffic EDA Platform</h1>
        <div style={{ fontSize: '14px', color: '#6b7280' }}>
          Status: {isAuthenticated ? <strong style={{ color: '#10b981' }}>Admin Mode</strong> : <strong style={{ color: '#ef4444' }}>Read-Only</strong>}
        </div>
      </div>

      {/* --- Auth Screen Overlay (If user is not logged in) --- */}
      {!isAuthenticated && (
        <form onSubmit={handleAuth} style={{ display: 'flex', gap: '10px', alignItems: 'center', background: '#f3f4f6', padding: '12px', borderRadius: '6px', marginBottom: '20px' }}>
          <span style={{ fontSize: '14px', fontWeight: 'bold', color: '#374151' }}>Unlock Admin Controls:</span>
          <input type="password" ref={passwordRef} placeholder="Enter Admin Password" style={{ padding: '4px 8px', borderRadius: '4px', border: '1px solid #d1d5db' }} />
          <button type="submit" style={{ padding: '4px 12px', background: '#4b5563', color: '#fff', border: 'none', borderRadius: '4px', cursor: 'pointer' }}>Login</button>
          {authError && <p style={{ color: 'red', margin: 0, fontSize: '13px' }}>{authError}</p>}
        </form>
      )}

      {/* --- Dynamic Render Switch (Ternary cleanly renders a single page child node) --- */}
      {viewMode === 'calendar' ? renderCalendar() : renderDashboard()}

      {/* --- FLOATING AI OPERATIONS AGENT CHATBOX PANEL --- */}
      <div style={{ position: 'fixed', bottom: '20px', right: '20px', zIndex: 10000 }}>
        {!isChatOpen ? (
          <button 
            onClick={() => setIsChatOpen(true)} 
            style={{ padding: '12px 20px', background: '#111827', color: '#fff', border: 'none', borderRadius: '50px', boxShadow: '0 4px 12px rgba(0,0,0,0.15)', cursor: 'pointer', fontWeight: 'bold', display: 'flex', alignItems: 'center', gap: '8px' }}
          >
            💬 Ask AI Agent
          </button>
        ) : (
          <div style={{ width: '340px', height: '420px', background: '#fff', borderRadius: '12px', boxShadow: '0 8px 24px rgba(0,0,0,0.18)', border: '1px solid #e5e7eb', display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>
            {/* Header */}
            <div style={{ background: '#111827', color: '#fff', padding: '12px 16px', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <span style={{ fontWeight: 'bold', fontSize: '14px' }}>Traffic Analytics Agent</span>
              <button onClick={() => setIsChatOpen(false)} style={{ background: 'none', border: 'none', color: '#fff', cursor: 'pointer', fontSize: '16px' }}>✕</button>
            </div>

            {/* Chat Messages Body Log */}
            <div style={{ flex: 1, padding: '16px', overflowY: 'auto', display: 'flex', flexDirection: 'column', gap: '10px', background: '#f9fafb' }}>
              {chatHistory.map((msg, idx) => (
                <div key={idx} style={{ alignSelf: msg.sender === 'user' ? 'flex-end' : 'flex-start', maxWidth: '80%' }}>
                  <div style={{ 
                    padding: '8px 12px', 
                    borderRadius: '8px', 
                    fontSize: '13px', 
                    lineHeight: '1.4',
                    background: msg.sender === 'user' ? '#2563eb' : '#e5e7eb', 
                    color: msg.sender === 'user' ? '#fff' : '#1f2937' 
                  }}>
                    {msg.text}
                  </div>
                </div>
              ))}
              {isAgentTyping && (
                <div style={{ alignSelf: 'flex-start', color: '#9ca3af', fontSize: '12px', fontStyle: 'italic' }}>
                  Agent running analytics queries...
                </div>
              )}
            </div>

            {/* Input Action Form Footer */}
            <form onSubmit={handleSendMessage} style={{ padding: '10px', borderTop: '1px solid #e5e7eb', display: 'flex', gap: '8px', background: '#fff' }}>
              <input 
                type="text" 
                value={chatInput}
                onChange={(e) => setChatInput(e.target.value)}
                placeholder="Ask basic parameters..." 
                style={{ flex: 1, padding: '8px', borderRadius: '6px', border: '1px solid #d1d5db', fontSize: '13px', outline: 'none' }}
              />
              <button type="submit" style={{ padding: '8px 14px', background: '#2563eb', color: '#fff', border: 'none', borderRadius: '6px', cursor: 'pointer', fontSize: '13px', fontWeight: 'bold' }}>
                Send
              </button>
            </form>
          </div>
        )}
      </div>

      {/* --- Global Event Modal Window Overlay --- */}
      {modalState.show && (
        <div className="modal-backdrop" style={{ position: 'fixed', top: 0, left: 0, right: 0, bottom: 0, background: 'rgba(0,0,0,0.5)', display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 9999 }}>
          <form className="modal-content" onSubmit={handleSubmitEvent} key={modalState.data?.id || modalState.data?.start} style={{ background: '#fff', padding: '24px', borderRadius: '8px', width: '360px', display: 'flex', flexDirection: 'column', gap: '12px' }}>
            <h3>{modalState.mode === 'create' ? 'Add Operation Session' : 'Edit Operation Parameters'}</h3>
            
            <label style={{ fontSize: '13px', fontWeight: 'bold' }}>Event Name</label>
            <input name="title" defaultValue={modalState.data?.title} required style={{ padding: '6px', borderRadius: '4px', border: '1px solid #ccc' }} />

            <label style={{ fontSize: '13px', fontWeight: 'bold' }}>Start Time</label>
            <input name="start_ts" type="datetime-local" defaultValue={modalState.data?.start} required style={{ padding: '6px', borderRadius: '4px', border: '1px solid #ccc' }} />

            <label style={{ fontSize: '13px', fontWeight: 'bold' }}>End Time</label>
            <input name="end_ts" type="datetime-local" defaultValue={modalState.data?.end} required style={{ padding: '6px', borderRadius: '4px', border: '1px solid #ccc' }} />

            <label style={{ fontSize: '13px', fontWeight: 'bold' }}>Expected Connected Devices</label>
            <input name="devices" type="number" defaultValue={modalState.data?.devices || 1} style={{ padding: '6px', borderRadius: '4px', border: '1px solid #ccc' }} />
            
            <label style={{ fontSize: '13px', fontWeight: 'bold' }}>Category</label>
            <select name="category" defaultValue={modalState.data?.category || 'video_session'} style={{ padding: '6px', borderRadius: '4px', border: '1px solid #ccc' }}>
              <option value="video_session">Video Session</option>
              <option value="system_update">System Update</option>
            </select>

            <div className="modal-actions" style={{ display: 'flex', justifyContent: 'flex-end', gap: '10px', marginTop: '10px' }}>
              <button type="button" onClick={closeModal} style={{ padding: '6px 12px', cursor: 'pointer' }}>Cancel</button>
              {modalState.mode === 'edit' && (
                <button type="button" onClick={handleDeleteEvent} style={{ padding: '6px 12px', background: '#ef4444', color: '#fff', border: 'none', borderRadius: '4px', cursor: 'pointer' }}>Delete</button>
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
