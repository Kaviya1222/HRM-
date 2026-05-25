import apiClient from "./client";

export async function fetchCalendarEvents(params = {}) {
  const response = await apiClient.get("/calendar/events", { params });
  return response.data;
}

export async function createCalendarEvent(payload) {
  const response = await apiClient.post("/calendar/events", payload);
  return response.data;
}

export async function updateCalendarEvent(eventId, payload) {
  const response = await apiClient.put(`/calendar/events/${eventId}`, payload);
  return response.data;
}

export async function deleteCalendarEvent(eventId) {
  const response = await apiClient.delete(`/calendar/events/${eventId}`);
  return response.data;
}

