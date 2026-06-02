import { useEffect, useMemo, useRef, useState } from "react";
import { CalendarDays, ChevronLeft, ChevronRight } from "lucide-react";
import { createCalendarEvent, deleteCalendarEvent, fetchCalendarEvents, updateCalendarEvent } from "../../api/calendarApi";
import useAuth from "../../hooks/useAuth";

const CALENDAR_EVENT_STORAGE_KEY = "hrm:calendar-events:v1";
const CALENDAR_UPDATED_EVENT = "hrm:calendar-updated";
const CALENDAR_UPDATED_AT_KEY = "hrm:calendar-updated-at";
const EVENT_TYPE_OPTIONS = [
  { value: "meeting", label: "Meeting" },
  { value: "huddle", label: "Huddle" },
  { value: "leave", label: "Leave" },
  { value: "task", label: "Task" },
  { value: "reminder", label: "Reminder" },
  { value: "general", label: "General Event" },
];

function getMonthStart(value) {
  return new Date(value.getFullYear(), value.getMonth(), 1);
}

function formatLocalDate(value) {
  const year = value.getFullYear();
  const month = String(value.getMonth() + 1).padStart(2, "0");
  const day = String(value.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
}

function formatDateInput(value) {
  return formatLocalDate(value);
}

function formatSelectedDateLabel(value) {
  return value.toLocaleDateString("en-IN", {
    day: "2-digit",
    month: "long",
    year: "numeric",
  });
}

function createEmptyEventForm(dateValue) {
  return {
    title: "",
    description: "",
    date: dateValue,
    time: "",
    type: EVENT_TYPE_OPTIONS[0].value,
  };
}

function isValidEventType(value) {
  return EVENT_TYPE_OPTIONS.some((option) => option.value === value);
}

function isValidEventTime(value) {
  return !value || /^([01]\d|2[0-3]):([0-5]\d)$/.test(value);
}

function createCalendarEventId() {
  if (typeof window !== "undefined" && window.crypto?.randomUUID) {
    return window.crypto.randomUUID();
  }

  return `calendar-event-${Date.now()}-${Math.random().toString(16).slice(2, 10)}`;
}

function sortCalendarEvents(items) {
  return [...items].sort((leftEvent, rightEvent) => {
    if (leftEvent.date !== rightEvent.date) {
      return leftEvent.date.localeCompare(rightEvent.date);
    }

    const leftTime = leftEvent.time || "99:99";
    const rightTime = rightEvent.time || "99:99";
    if (leftTime !== rightTime) {
      return leftTime.localeCompare(rightTime);
    }

    return leftEvent.title.localeCompare(rightEvent.title);
  });
}

function normalizeStoredEvent(item) {
  if (!item || typeof item !== "object") {
    return null;
  }

  const normalizedDate = parseDateInput(String(item.date || ""));
  const normalizedTitle = String(item.title || "").trim();
  const normalizedType = String(item.type || "").trim();
  const normalizedTime = String(item.time || "").trim();

  if (!normalizedDate || !normalizedTitle || !isValidEventType(normalizedType) || !isValidEventTime(normalizedTime)) {
    return null;
  }

  return {
    id: String(item.id || createCalendarEventId()),
    title: normalizedTitle,
    description: String(item.description || "").trim(),
    date: formatLocalDate(normalizedDate),
    time: normalizedTime,
    type: normalizedType,
  };
}

function normalizeApiEvent(item) {
  if (!item || typeof item !== "object") {
    return null;
  }

  return normalizeStoredEvent({
    id: item.id,
    title: item.title,
    description: item.description,
    date: item.date,
    time: item.time,
    type: item.type || item.event_type,
  });
}

function loadStoredCalendarEvents() {
  if (typeof window === "undefined") {
    return [];
  }

  try {
    const rawValue = window.localStorage.getItem(CALENDAR_EVENT_STORAGE_KEY);
    if (!rawValue) {
      return [];
    }

    const parsedValue = JSON.parse(rawValue);
    if (!Array.isArray(parsedValue)) {
      return [];
    }

    return sortCalendarEvents(parsedValue.map(normalizeStoredEvent).filter(Boolean));
  } catch {
    return [];
  }
}

function notifyCalendarUpdated() {
  if (typeof window === "undefined") {
    return;
  }

  const updatedAt = String(Date.now());
  window.localStorage.setItem(CALENDAR_UPDATED_AT_KEY, updatedAt);
  window.dispatchEvent(new CustomEvent(CALENDAR_UPDATED_EVENT, { detail: { updatedAt } }));
}

function formatEventTime(value) {
  if (!value || !isValidEventTime(value)) {
    return "";
  }

  const [hoursValue, minutesValue] = value.split(":");
  const parsedHours = Number(hoursValue);
  const normalizedHours = parsedHours % 12 || 12;
  const period = parsedHours >= 12 ? "PM" : "AM";
  return `${normalizedHours}:${minutesValue} ${period}`;
}

function parseDateInput(value) {
  if (!value || !/^\d{4}-\d{2}-\d{2}$/.test(value)) {
    return null;
  }

  const [yearValue, monthValue, dayValue] = value.split("-");
  const year = Number(yearValue);
  const month = Number(monthValue);
  const day = Number(dayValue);

  if (!Number.isInteger(year) || !Number.isInteger(month) || !Number.isInteger(day) || month < 1 || month > 12 || day < 1) {
    return null;
  }

  const parsedDate = new Date(year, month - 1, day);

  if (
    parsedDate.getFullYear() !== year
    || parsedDate.getMonth() !== month - 1
    || parsedDate.getDate() !== day
  ) {
    return null;
  }

  return parsedDate;
}

function moveDateByMonths(value, months) {
  const year = value.getFullYear();
  const month = value.getMonth();
  const day = value.getDate();
  const targetMonthStart = new Date(year, month + months, 1);
  const lastDayOfTargetMonth = new Date(
    targetMonthStart.getFullYear(),
    targetMonthStart.getMonth() + 1,
    0,
  ).getDate();

  return new Date(
    targetMonthStart.getFullYear(),
    targetMonthStart.getMonth(),
    Math.min(day, lastDayOfTargetMonth),
  );
}

function getWeeksForMonth(monthDate) {
  const monthStart = getMonthStart(monthDate);
  const monthEnd = new Date(monthDate.getFullYear(), monthDate.getMonth() + 1, 0);
  const days = [];
  const totalDaysInMonth = monthEnd.getDate();

  for (let monthDayNumber = 1; monthDayNumber <= totalDaysInMonth; monthDayNumber += 1) {
    const day = new Date(monthDate.getFullYear(), monthDate.getMonth(), monthDayNumber);
    days.push({
      key: formatLocalDate(day),
      isoDate: formatLocalDate(day),
      dayLabel: String(day.getDate()).padStart(2, "0"),
      monthLabel: day.toLocaleDateString("en-IN", { month: "short" }).toUpperCase(),
      weekdayLabel: day.toLocaleDateString("en-IN", { weekday: "short" }).toUpperCase(),
    });
  }

  return days;
}

function CalendarPage() {
  const { hasPermission } = useAuth();
  const [selectedDate, setSelectedDate] = useState(() => new Date());
  const [dateInputValue, setDateInputValue] = useState(() => formatDateInput(new Date()));
  const [isEditingDate, setIsEditingDate] = useState(false);
  const [calendarEvents, setCalendarEvents] = useState([]);
  const [isScheduleOpen, setIsScheduleOpen] = useState(false);
  const [editingEventId, setEditingEventId] = useState(null);
  const [eventForm, setEventForm] = useState(() => createEmptyEventForm(formatLocalDate(new Date())));
  const [scheduleFeedback, setScheduleFeedback] = useState({ type: "", message: "" });
  const [isEventSaving, setIsEventSaving] = useState(false);
  const monthPickerRef = useRef(null);
  const canManageCalendarEvents = hasPermission("calendar.events.manage");
  const monthCursor = useMemo(() => getMonthStart(selectedDate), [selectedDate]);
  const selectedDateKey = useMemo(() => formatLocalDate(selectedDate), [selectedDate]);
  const todayKey = useMemo(() => formatLocalDate(new Date()), []);
  const monthHeading = useMemo(
    () => monthCursor.toLocaleDateString("en-IN", { month: "long" }),
    [monthCursor],
  );
  const yearHeading = useMemo(
    () => monthCursor.toLocaleDateString("en-IN", { year: "numeric" }),
    [monthCursor],
  );
  const selectedWeekdayLabel = useMemo(
    () => selectedDate.toLocaleDateString("en-IN", { weekday: "long" }),
    [selectedDate],
  );

  const calendarDays = useMemo(() => getWeeksForMonth(monthCursor), [monthCursor]);
  const eventsByDate = useMemo(() => {
    const groupedEvents = {};

    for (const calendarEvent of calendarEvents) {
      if (!groupedEvents[calendarEvent.date]) {
        groupedEvents[calendarEvent.date] = [];
      }
      groupedEvents[calendarEvent.date].push(calendarEvent);
    }

    return Object.fromEntries(
      Object.entries(groupedEvents).map(([dateKey, events]) => [dateKey, sortCalendarEvents(events)]),
    );
  }, [calendarEvents]);
  const selectedDateEvents = useMemo(() => eventsByDate[selectedDateKey] || [], [eventsByDate, selectedDateKey]);

  useEffect(() => {
    setDateInputValue(formatDateInput(selectedDate));
  }, [selectedDate]);

  useEffect(() => {
    let isMounted = true;

    async function loadCalendarEvents() {
      try {
        const response = await fetchCalendarEvents();
        const events = sortCalendarEvents((response.items || []).map(normalizeApiEvent).filter(Boolean));
        if (isMounted) {
          setCalendarEvents(events);
        }
      } catch (_error) {
        if (isMounted) {
          setCalendarEvents(loadStoredCalendarEvents());
          setScheduleFeedback({ type: "error", message: "Unable to load saved calendar events." });
        }
      }
    }

    loadCalendarEvents();

    return () => {
      isMounted = false;
    };
  }, []);

  useEffect(() => {
    if (typeof window === "undefined") {
      return;
    }

    try {
      window.localStorage.setItem(CALENDAR_EVENT_STORAGE_KEY, JSON.stringify(calendarEvents));
    } catch {
      // Ignore storage write failures and keep runtime state working.
    }
  }, [calendarEvents]);

  useEffect(() => {
    if (!isEditingDate || !monthPickerRef.current) {
      return;
    }

    const input = monthPickerRef.current;
    input.focus();

    if (typeof input.showPicker === "function") {
      input.showPicker();
    } else {
      input.click();
    }
  }, [isEditingDate]);

  useEffect(() => {
    if (!isScheduleOpen) {
      return undefined;
    }

    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";

    function handleKeyDown(event) {
      if (event.key === "Escape") {
        setIsScheduleOpen(false);
        setEditingEventId(null);
        setScheduleFeedback({ type: "", message: "" });
        setEventForm(createEmptyEventForm(selectedDateKey));
      }
    }

    document.addEventListener("keydown", handleKeyDown);
    return () => {
      document.body.style.overflow = previousOverflow;
      document.removeEventListener("keydown", handleKeyDown);
    };
  }, [isScheduleOpen, selectedDateKey]);

  useEffect(() => {
    if (!canManageCalendarEvents && isScheduleOpen) {
      closeScheduleModal();
    }
  }, [canManageCalendarEvents, isScheduleOpen]);

  function moveMonth(direction) {
    setSelectedDate((current) => moveDateByMonths(current, direction));
  }

  function jumpToCurrentMonth() {
    const today = new Date();
    setSelectedDate(today);
    setIsEditingDate(false);
  }

  function openMonthPicker() {
    setDateInputValue(formatDateInput(selectedDate));
    setIsEditingDate(true);
  }

  function handleDateSelectionChange(event) {
    const nextValue = event.target.value;
    setDateInputValue(nextValue);

    const nextDate = parseDateInput(nextValue);
    if (!nextDate) {
      return;
    }

    setSelectedDate(nextDate);
  }

  function handleDateInputBlur() {
    const nextDate = parseDateInput(dateInputValue);
    if (nextDate) {
      setSelectedDate(nextDate);
      setDateInputValue(formatDateInput(nextDate));
    } else {
      setDateInputValue(formatDateInput(selectedDate));
    }

    setIsEditingDate(false);
  }

  function handleDateInputKeyDown(event) {
    if (event.key === "Enter") {
      event.preventDefault();
      handleDateInputBlur();
      return;
    }

    if (event.key === "Escape") {
      event.preventDefault();
      setDateInputValue(formatDateInput(selectedDate));
      setIsEditingDate(false);
    }
  }

  function openScheduleModal(targetDateKey) {
    const parsedDate = parseDateInput(targetDateKey);
    if (parsedDate) {
      setSelectedDate(parsedDate);
    }

    if (!canManageCalendarEvents) {
      return;
    }

    setEventForm(createEmptyEventForm(targetDateKey));
    setEditingEventId(null);
    setScheduleFeedback({ type: "", message: "" });
    setIsScheduleOpen(true);
  }

  function closeScheduleModal() {
    setIsScheduleOpen(false);
    setEditingEventId(null);
    setEventForm(createEmptyEventForm(selectedDateKey));
    setScheduleFeedback({ type: "", message: "" });
  }

  function handleEventFormChange(event) {
    const { name, value } = event.target;
    setEventForm((current) => ({ ...current, [name]: value }));

    if (name === "date") {
      const parsedDate = parseDateInput(value);
      if (parsedDate) {
        setSelectedDate(parsedDate);
      }
    }
  }

  function resetEventForm() {
    setEditingEventId(null);
    setEventForm(createEmptyEventForm(selectedDateKey));
    setScheduleFeedback({ type: "", message: "" });
  }

  function validateEventForm() {
    if (!eventForm.title.trim()) {
      return "Event title is required.";
    }

    if (!parseDateInput(eventForm.date)) {
      return "Enter a valid event date.";
    }

    if (!isValidEventType(eventForm.type)) {
      return "Choose a valid event type.";
    }

    if (!isValidEventTime(eventForm.time.trim())) {
      return "Enter a valid time in HH:MM format.";
    }

    return "";
  }

  async function handleEventSubmit(event) {
    event.preventDefault();
    if (!canManageCalendarEvents) {
      setScheduleFeedback({ type: "error", message: "You do not have permission to create or update calendar schedules." });
      return;
    }

    const validationError = validateEventForm();
    if (validationError) {
      setScheduleFeedback({ type: "error", message: validationError });
      return;
    }

    const parsedDate = parseDateInput(eventForm.date);
    if (!parsedDate) {
      setScheduleFeedback({ type: "error", message: "Enter a valid event date." });
      return;
    }

    const eventPayload = {
      title: eventForm.title.trim(),
      description: eventForm.description.trim(),
      date: formatLocalDate(parsedDate),
      time: eventForm.time.trim(),
      event_type: eventForm.type,
    };

    setIsEventSaving(true);
    try {
      const response = editingEventId
        ? await updateCalendarEvent(editingEventId, eventPayload)
        : await createCalendarEvent(eventPayload);
      const savedEvent = normalizeApiEvent(response.event);
      if (!savedEvent) {
        throw new Error("Calendar event could not be saved.");
      }

      setCalendarEvents((current) => sortCalendarEvents(
        editingEventId
          ? current.map((calendarEvent) => (calendarEvent.id === editingEventId ? savedEvent : calendarEvent))
          : [...current, savedEvent],
      ));
      setSelectedDate(parsedDate);
      setEditingEventId(null);
      setEventForm(createEmptyEventForm(formatLocalDate(parsedDate)));
      setScheduleFeedback({
        type: "success",
        message: response.message || (editingEventId ? "Schedule updated successfully." : "Schedule added successfully."),
      });
      notifyCalendarUpdated();
    } catch (saveError) {
      setScheduleFeedback({
        type: "error",
        message: saveError.response?.data?.detail || saveError.message || "Unable to save calendar event.",
      });
    } finally {
      setIsEventSaving(false);
    }
  }

  function handleEditEvent(calendarEvent) {
    if (!canManageCalendarEvents) {
      return;
    }

    setEditingEventId(calendarEvent.id);
    setEventForm({
      title: calendarEvent.title,
      description: calendarEvent.description,
      date: calendarEvent.date,
      time: calendarEvent.time,
      type: calendarEvent.type,
    });
    setScheduleFeedback({ type: "", message: "" });

    const parsedDate = parseDateInput(calendarEvent.date);
    if (parsedDate) {
      setSelectedDate(parsedDate);
    }
  }

  async function handleDeleteEvent(eventId) {
    if (!canManageCalendarEvents) {
      setScheduleFeedback({ type: "error", message: "You do not have permission to delete calendar schedules." });
      return;
    }

    try {
      await deleteCalendarEvent(eventId);
      setCalendarEvents((current) => current.filter((calendarEvent) => calendarEvent.id !== eventId));

      if (editingEventId === eventId) {
        setEditingEventId(null);
        setEventForm(createEmptyEventForm(selectedDateKey));
      }

      setScheduleFeedback({ type: "success", message: "Schedule deleted successfully." });
      notifyCalendarUpdated();
    } catch (deleteError) {
      setScheduleFeedback({
        type: "error",
        message: deleteError.response?.data?.detail || "Unable to delete calendar event.",
      });
    }
  }

  return (
    <div className="page-container employee-page calendar-page">
      <div className="page-section-header">
        <div className="page-section-header-icon">
          <CalendarDays size={22} />
        </div>
        <div>
          <h2 className="page-section-header-title">Calendar</h2>
          <p className="page-section-header-sub">
            Review the current month in a single calendar view without affecting any existing HRM workflows.
          </p>
        </div>
      </div>

      <section className="employee-panel calendar-shell">
        <div className="calendar-hero">
          <div className="calendar-hero-copy">
            <p className="sidebar-section-label">Monthly View</p>

            {isEditingDate ? (
              <input
                aria-label="Select full date"
                className="calendar-hero-date-input"
                onBlur={handleDateInputBlur}
                onChange={handleDateSelectionChange}
                onKeyDown={handleDateInputKeyDown}
                ref={monthPickerRef}
                type="date"
                value={dateInputValue}
              />
            ) : (
              <button
                aria-label="Select full date"
                className="calendar-hero-date-trigger"
                onClick={openMonthPicker}
                type="button"
              >
                <span className="calendar-hero-month">{monthHeading}</span>
                <span className="calendar-hero-year">{yearHeading}</span>
                <span className="calendar-hero-selected-date">{formatSelectedDateLabel(selectedDate)}</span>
              </button>
            )}
          </div>

          <div className="calendar-hero-visual" aria-hidden="true">
            <div className="calendar-hero-orb calendar-hero-orb--large" />
            <div className="calendar-hero-orb calendar-hero-orb--small" />
            <div className="calendar-hero-note">
              <span className="calendar-hero-note-label">Selected Day</span>
              <strong>{selectedWeekdayLabel}</strong>
              <span>{formatSelectedDateLabel(selectedDate)}</span>
            </div>
          </div>
        </div>

        <div className="calendar-toolbar">
          <div className="employee-row-actions">
            <button className="ghost-button employee-row-btn" onClick={() => moveMonth(-1)} type="button">
              <ChevronLeft size={14} />
              Previous
            </button>
            <button className="ghost-button employee-row-btn" onClick={jumpToCurrentMonth} type="button">
              <CalendarDays size={14} />
              Current Month
            </button>
            <button className="ghost-button employee-row-btn" onClick={() => moveMonth(1)} type="button">
              Next
              <ChevronRight size={14} />
            </button>
          </div>
        </div>

        <div className="calendar-board">
          <div className="calendar-grid">
            {calendarDays.map((day) => {
              const isSelectedDate = day.isoDate === selectedDateKey;
              const isToday = day.isoDate === todayKey;
              const dayEvents = eventsByDate[day.isoDate] || [];
              const dayCardClassName = [
                "calendar-day-card",
                isSelectedDate ? "is-selected" : "",
                isToday ? "is-today" : "",
              ].filter(Boolean).join(" ");

              return (
                <article
                  className={dayCardClassName}
                  key={day.key}
                  onClick={() => openScheduleModal(day.isoDate)}
                  onKeyDown={(event) => {
                    if (event.key === "Enter" || event.key === " ") {
                      event.preventDefault();
                      openScheduleModal(day.isoDate);
                    }
                  }}
                  role="button"
                  tabIndex={0}
                >
                  <div className="calendar-day-card-head">
                    <span className="calendar-day-month-label">{day.weekdayLabel} · {day.monthLabel}</span>
                    <div className="calendar-day-head-badges">
                      {dayEvents.length ? <span className="calendar-day-chip calendar-day-chip--count">{dayEvents.length}</span> : null}
                      {isToday ? <span className="calendar-day-chip">Today</span> : null}
                    </div>
                  </div>

                  <div className="calendar-day-card-body">
                    <strong className="calendar-day-number">{day.dayLabel}</strong>
                    <span className="calendar-day-date">{day.isoDate}</span>
                    {isSelectedDate ? <span className="calendar-day-caption">Selected day</span> : null}

                    {dayEvents.length ? (
                      <div className="calendar-day-events">
                        {dayEvents.slice(0, 2).map((calendarEvent) => (
                          <span
                            className={`calendar-event-pill is-${calendarEvent.type}`}
                            key={calendarEvent.id}
                            title={`${calendarEvent.title}${calendarEvent.time ? ` • ${formatEventTime(calendarEvent.time)}` : ""}`}
                          >
                            {calendarEvent.title}
                          </span>
                        ))}
                        {dayEvents.length > 2 ? (
                          <span className="calendar-event-pill is-more">+{dayEvents.length - 2} more</span>
                        ) : null}
                      </div>
                    ) : null}
                  </div>
                </article>
              );
            })}
          </div>
        </div>

        <div className="calendar-readonly-panel">
          <div className="calendar-schedule-list-header">
            <p className="sidebar-section-label">Saved Events</p>
            <h3 className="module-panel-title">{formatSelectedDateLabel(selectedDate)}</h3>
          </div>

          {selectedDateEvents.length ? (
            <div className="calendar-schedule-list">
              {selectedDateEvents.map((calendarEvent) => (
                <article className="calendar-schedule-card" key={calendarEvent.id}>
                  <div className="calendar-schedule-card-head">
                    <div className="calendar-schedule-card-title-group">
                      <strong>{calendarEvent.title}</strong>
                      <span className={`calendar-event-type-badge is-${calendarEvent.type}`}>
                        {EVENT_TYPE_OPTIONS.find((option) => option.value === calendarEvent.type)?.label || "General Event"}
                      </span>
                    </div>
                  </div>

                  {calendarEvent.time ? <p className="calendar-schedule-card-time">{formatEventTime(calendarEvent.time)}</p> : null}
                  {calendarEvent.description ? <p className="calendar-schedule-card-description">{calendarEvent.description}</p> : null}
                </article>
              ))}
            </div>
          ) : (
            <div className="employee-empty-state calendar-schedule-empty-state">
              <span>No schedules saved for this date yet.</span>
            </div>
          )}
        </div>
      </section>

      {canManageCalendarEvents && isScheduleOpen ? (
        <div className="calendar-schedule-overlay" onClick={closeScheduleModal} role="presentation">
          <section className="employee-panel calendar-schedule-modal" onClick={(event) => event.stopPropagation()}>
            <div className="module-toolbar">
              <div>
                <p className="sidebar-section-label">Schedule Manager</p>
                <h3 className="module-panel-title">{formatSelectedDateLabel(parseDateInput(eventForm.date) || selectedDate)}</h3>
              </div>

              <button className="ghost-button employee-row-btn" onClick={closeScheduleModal} type="button">
                Close
              </button>
            </div>

            {scheduleFeedback.message ? (
              <div className={`employee-feedback employee-feedback--${scheduleFeedback.type || "success"}`}>
                <span>{scheduleFeedback.message}</span>
              </div>
            ) : null}

            <div className="calendar-schedule-layout">
              <form className="employee-form-grid calendar-schedule-form" onSubmit={handleEventSubmit}>
                <label className="sf-field employee-form-span-2">
                  <span className="sf-label">Event Title</span>
                  <input
                    className="sf-input"
                    maxLength={120}
                    name="title"
                    onChange={handleEventFormChange}
                    required
                    value={eventForm.title}
                  />
                </label>

                <label className="sf-field employee-form-span-2">
                  <span className="sf-label">Event Description</span>
                  <textarea
                    className="sf-input employee-textarea"
                    name="description"
                    onChange={handleEventFormChange}
                    rows="3"
                    value={eventForm.description}
                  />
                </label>

                <label className="sf-field">
                  <span className="sf-label">Date</span>
                  <input
                    className="sf-input"
                    name="date"
                    onChange={handleEventFormChange}
                    required
                    type="date"
                    value={eventForm.date}
                  />
                </label>

                <label className="sf-field">
                  <span className="sf-label">Time</span>
                  <input
                    className="sf-input"
                    name="time"
                    onChange={handleEventFormChange}
                    type="time"
                    value={eventForm.time}
                  />
                </label>

                <label className="sf-field employee-form-span-2">
                  <span className="sf-label">Event Type</span>
                  <select className="sf-input" name="type" onChange={handleEventFormChange} value={eventForm.type}>
                    {EVENT_TYPE_OPTIONS.map((option) => (
                      <option key={option.value} value={option.value}>{option.label}</option>
                    ))}
                  </select>
                </label>

                <div className="employee-form-actions employee-form-span-2">
                  <button className="ghost-button" onClick={resetEventForm} type="button">
                    {editingEventId ? "Cancel Edit" : "Reset"}
                  </button>
                  <button className="primary-button" disabled={isEventSaving} type="submit">
                    {isEventSaving ? "Saving..." : editingEventId ? "Update Schedule" : "Save Schedule"}
                  </button>
                </div>
              </form>

              <div className="calendar-schedule-list-panel">
                <div className="calendar-schedule-list-header">
                  <p className="sidebar-section-label">Saved Events</p>
                  <h3 className="module-panel-title">Schedules for selected date</h3>
                </div>

                {selectedDateEvents.length ? (
                  <div className="calendar-schedule-list">
                    {selectedDateEvents.map((calendarEvent) => (
                      <article className="calendar-schedule-card" key={calendarEvent.id}>
                        <div className="calendar-schedule-card-head">
                          <div className="calendar-schedule-card-title-group">
                            <strong>{calendarEvent.title}</strong>
                            <span className={`calendar-event-type-badge is-${calendarEvent.type}`}>
                              {EVENT_TYPE_OPTIONS.find((option) => option.value === calendarEvent.type)?.label || "General Event"}
                            </span>
                          </div>
                          {canManageCalendarEvents ? (
                            <div className="employee-row-actions">
                              <button className="ghost-button employee-row-btn" onClick={() => handleEditEvent(calendarEvent)} type="button">
                                Edit
                              </button>
                            </div>
                          ) : null}
                        </div>

                        {calendarEvent.time ? <p className="calendar-schedule-card-time">{formatEventTime(calendarEvent.time)}</p> : null}
                        {calendarEvent.description ? <p className="calendar-schedule-card-description">{calendarEvent.description}</p> : null}
                      </article>
                    ))}
                  </div>
                ) : (
                  <div className="employee-empty-state calendar-schedule-empty-state">
                    <span>No schedules saved for this date yet.</span>
                  </div>
                )}
              </div>
            </div>
          </section>
        </div>
      ) : null}
    </div>
  );
}

export default CalendarPage;
