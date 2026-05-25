import { BrowserRouter, Route, Routes } from "react-router-dom";
import AppLayout from "../layouts/AppLayout";
import AttendancePage from "../pages/attendance/AttendancePage";
import CalendarPage from "../pages/calendar/CalendarPage";
import DashboardPage from "../pages/dashboard/DashboardPage";
import EmployeesPage from "../pages/employees/EmployeesPage";
import LeavePage from "../pages/leave/LeavePage";
import PayrollPage from "../pages/payroll/PayrollPage";
import ReportsPage from "../pages/reports/ReportsPage";
import TrackerPage from "../pages/tracker/TrackerPage";
import UnauthorizedPage from "../pages/UnauthorizedPage";
import LoginPage from "../pages/auth/LoginPage";
import SuperAdminSettingsPage from "../pages/settings/SuperAdminSettingsPage";
import ProtectedRoute from "./ProtectedRoute";

function AppRouter() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/login" element={<LoginPage />} />
        <Route path="/unauthorized" element={<UnauthorizedPage />} />

        <Route element={<ProtectedRoute />}>
          <Route element={<AppLayout />}>
            <Route
              index
              element={(
                <ProtectedRoute permission="page.dashboard.view">
                  <DashboardPage />
                </ProtectedRoute>
              )}
            />

            <Route
              path="/employees"
              element={
                <ProtectedRoute permission="page.employees.view">
                  <EmployeesPage />
                </ProtectedRoute>
              }
            />

            <Route
              path="/attendance"
              element={
                <ProtectedRoute permission="page.attendance.view">
                  <AttendancePage />
                </ProtectedRoute>
              }
            />

            <Route
              path="/leave"
              element={
                <ProtectedRoute permission="page.leave.view">
                  <LeavePage />
                </ProtectedRoute>
              }
            />

            <Route
              path="/payroll"
              element={
                <ProtectedRoute permission="page.payroll.view">
                  <PayrollPage />
                </ProtectedRoute>
              }
            />

            <Route
              path="/reports"
              element={
                <ProtectedRoute permission="page.reports.view">
                  <ReportsPage />
                </ProtectedRoute>
              }
            />

            <Route
              path="/calendar"
              element={
                <ProtectedRoute permission="page.calendar.view">
                  <CalendarPage />
                </ProtectedRoute>
              }
            />

            <Route
              path="/tracker"
              element={
                <ProtectedRoute permission="page.tracker.view">
                  <TrackerPage />
                </ProtectedRoute>
              }
            />

            <Route
              path="/settings"
              element={
                <ProtectedRoute permission="page.settings.view" superAdminOnly>
                  <SuperAdminSettingsPage />
                </ProtectedRoute>
              }
            />
          </Route>
        </Route>
      </Routes>
    </BrowserRouter>
  );
}

export default AppRouter;
