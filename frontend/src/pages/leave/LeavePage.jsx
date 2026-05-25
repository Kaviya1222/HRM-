import { useEffect, useMemo, useState } from "react";
import {
  CalendarDays,
  CheckCircle2,
  Send,
  ShieldCheck,
  XCircle,
} from "lucide-react";
import { useSearchParams } from "react-router-dom";
import { applyLeave, decideLeave, fetchLeaveMeta, fetchLeaveRequests } from "../../api/leaveApi";
import useAuth from "../../hooks/useAuth";

const EMPLOYEE_DIRECTORY_UPDATED_EVENT = "hrm:employees-updated";
const EMPLOYEE_DIRECTORY_UPDATED_AT_KEY = "hrm:employees-updated-at";

function createEmptyLeaveForm() {
  return {
    leave_type_id: "",
    start_date: "",
    end_date: "",
    reason: "",
  };
}

function formatDate(value) {
  if (!value) {
    return "--";
  }
  return new Date(value).toLocaleDateString("en-IN");
}

function calculateTotalDays(startDate, endDate) {
  if (!startDate || !endDate || endDate < startDate) {
    return 0;
  }
  const start = new Date(`${startDate}T00:00:00`);
  const end = new Date(`${endDate}T00:00:00`);
  return Math.floor((end.getTime() - start.getTime()) / 86400000) + 1;
}

function formatApiError(error, fallback) {
  const detail = error.response?.data?.detail;
  if (typeof detail === "string") {
    return detail;
  }
  if (Array.isArray(detail)) {
    return detail.map((item) => item.msg || item.message || String(item)).join(" ");
  }
  if (detail && typeof detail === "object") {
    return detail.msg || detail.message || fallback;
  }
  return error.message || fallback;
}

function LeavePage() {
  const { hasPermission, user } = useAuth();
  const [searchParams, setSearchParams] = useSearchParams();
  const [meta, setMeta] = useState({ leave_types: [], balances: [], employees: [] });
  const [requests, setRequests] = useState([]);
  const [allRequests, setAllRequests] = useState([]);
  const [statusFilter, setStatusFilter] = useState("all");
  const [employeeFilter, setEmployeeFilter] = useState("all");
  const [formState, setFormState] = useState(createEmptyLeaveForm);
  const [formErrors, setFormErrors] = useState({});
  const [isApplyModalOpen, setIsApplyModalOpen] = useState(false);
  const [feedback, setFeedback] = useState({ type: "", message: "" });
  const [isLoading, setIsLoading] = useState(true);
  const [isRefreshing, setIsRefreshing] = useState(false);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [decisionInFlightId, setDecisionInFlightId] = useState("");
  const [rejectTarget, setRejectTarget] = useState(null);
  const [rejectReason, setRejectReason] = useState("");
  const [rejectError, setRejectError] = useState("");

  const canApply = hasPermission("leave.apply");
  const canApprove = hasPermission("leave.approve") || hasPermission("leave.recommend");
  const canShowApplyLeave = canApply;

  const requestStats = useMemo(() => {
    const pending = allRequests.filter((item) => item.status === "pending").length;
    const approved = allRequests.filter((item) => item.status === "approved").length;
    const rejected = allRequests.filter((item) => item.status === "rejected").length;
    return [
      { label: "Leave Types", value: meta.leave_types.length },
      { label: "Pending Requests", value: pending },
      { label: "Approved Requests", value: approved },
      { label: "Rejected Requests", value: rejected },
    ];
  }, [allRequests, meta.leave_types.length]);

  async function loadData({ silent = false } = {}) {
    if (silent) {
      setIsRefreshing(true);
    } else {
      setIsLoading(true);
    }

    try {
      const [metaResponse, requestsResponse, allRequestsResponse] = await Promise.all([
        fetchLeaveMeta(),
        fetchLeaveRequests({
          status: statusFilter === "all" ? undefined : statusFilter,
          employee_id: employeeFilter === "all" ? undefined : employeeFilter,
        }),
        fetchLeaveRequests(),
      ]);
      setMeta(metaResponse);
      setRequests(requestsResponse.items);
      setAllRequests(allRequestsResponse.items);
    } catch (error) {
      setFeedback({
        type: "error",
        message: formatApiError(error, "Unable to load leave data."),
      });
    } finally {
      setIsLoading(false);
      setIsRefreshing(false);
    }
  }

  useEffect(() => {
    loadData();
  }, [employeeFilter, statusFilter]);

  useEffect(() => {
    if (canApply && searchParams.get("apply") === "1") {
      openApplyModal();
      setSearchParams({}, { replace: true });
    }
  }, [canApply, searchParams, setSearchParams]);

  useEffect(() => {
    function handleEmployeeDirectoryUpdate() {
      void loadData({ silent: true });
    }

    function handleStorage(event) {
      if (event.key === EMPLOYEE_DIRECTORY_UPDATED_AT_KEY) {
        void loadData({ silent: true });
      }
    }

    window.addEventListener(EMPLOYEE_DIRECTORY_UPDATED_EVENT, handleEmployeeDirectoryUpdate);
    window.addEventListener("storage", handleStorage);

    return () => {
      window.removeEventListener(EMPLOYEE_DIRECTORY_UPDATED_EVENT, handleEmployeeDirectoryUpdate);
      window.removeEventListener("storage", handleStorage);
    };
  }, [employeeFilter, statusFilter]);

  function openApplyModal() {
    setFormState(createEmptyLeaveForm());
    setFormErrors({});
    setFeedback({ type: "", message: "" });
    setIsApplyModalOpen(true);
  }

  function closeApplyModal() {
    if (isSubmitting) {
      return;
    }
    setIsApplyModalOpen(false);
    setFormErrors({});
  }

  function handleLeaveFormChange(event) {
    const { name, value } = event.target;
    setFormState((current) => ({ ...current, [name]: value }));
    setFormErrors((current) => {
      if (!current[name]) {
        return current;
      }
      const next = { ...current };
      delete next[name];
      return next;
    });
  }

  function validateLeaveForm() {
    const errors = {};
    if (!formState.leave_type_id) {
      errors.leave_type_id = "Leave type is required.";
    }
    if (!formState.start_date) {
      errors.start_date = "Start date is required.";
    }
    if (!formState.end_date) {
      errors.end_date = "End date is required.";
    }
    if (formState.start_date && formState.end_date && formState.end_date < formState.start_date) {
      errors.end_date = "End date cannot be before start date.";
    }
    if (!formState.reason.trim()) {
      errors.reason = "Reason is required.";
    }
    return errors;
  }

  async function handleApplyLeave(event) {
    event.preventDefault();
    const validationErrors = validateLeaveForm();
    if (Object.keys(validationErrors).length) {
      setFormErrors(validationErrors);
      return;
    }

    setIsSubmitting(true);
    setFeedback({ type: "", message: "" });
    try {
      const selectedLeaveType = meta.leave_types.find((leaveType) => String(leaveType.id) === String(formState.leave_type_id));
      await applyLeave({
        employee_id: user?.employee_id || undefined,
        leave_type_id: formState.leave_type_id,
        leave_type: selectedLeaveType?.name,
        start_date: formState.start_date,
        end_date: formState.end_date,
        total_days: calculateTotalDays(formState.start_date, formState.end_date),
        reason: formState.reason.trim(),
        remarks: formState.reason.trim(),
        status: "pending",
      });
      setFormState(createEmptyLeaveForm());
      setFormErrors({});
      setIsApplyModalOpen(false);
      setFeedback({ type: "success", message: "Leave request submitted successfully." });
      await loadData({ silent: true });
    } catch (error) {
      setFeedback({
        type: "error",
        message: formatApiError(error, "Unable to submit leave request."),
      });
    } finally {
      setIsSubmitting(false);
    }
  }

  async function handleDecision(requestId, decision, remarks = "") {
    setDecisionInFlightId(requestId);
    setFeedback({ type: "", message: "" });
    try {
      await decideLeave(requestId, { decision, remarks });
      setFeedback({ type: "success", message: `Leave request ${decision} successfully.` });
      await loadData({ silent: true });
      return true;
    } catch (error) {
      setFeedback({
        type: "error",
        message: formatApiError(error, `Unable to ${decision} this leave request.`),
      });
      return false;
    } finally {
      setDecisionInFlightId("");
    }
  }

  function openRejectModal(request) {
    setRejectTarget(request);
    setRejectReason("");
    setRejectError("");
    setFeedback({ type: "", message: "" });
  }

  function closeRejectModal() {
    if (decisionInFlightId) {
      return;
    }
    setRejectTarget(null);
    setRejectReason("");
    setRejectError("");
  }

  async function handleRejectSubmit(event) {
    event.preventDefault();
    const normalizedReason = rejectReason.trim();
    if (!normalizedReason) {
      setRejectError("Rejection reason is required.");
      return;
    }
    if (!rejectTarget?.id) {
      return;
    }
    setRejectError("");
    const didReject = await handleDecision(rejectTarget.id, "rejected", normalizedReason);
    if (didReject) {
      closeRejectModal();
    }
  }

  if (isLoading) {
    return (
      <div className="page-container">
        <div className="settings-loading">
          <div className="settings-loading-spinner" />
          <span>Loading leave management...</span>
        </div>
      </div>
    );
  }

  return (
    <div className="page-container employee-page">
      <div className="page-section-header">
        <div className="page-section-header-icon">
          <CalendarDays size={22} />
        </div>
        <div>
          <h2 className="page-section-header-title">Leave Management</h2>
          <p className="page-section-header-sub">
            Apply for leave, review balances, and process approvals with overlap validation and attendance integration.
          </p>
        </div>
      </div>

      {feedback.message ? (
        <div className={`employee-feedback employee-feedback--${feedback.type || "info"}`}>
          <ShieldCheck size={16} />
          <span>{feedback.message}</span>
        </div>
      ) : null}

      <div className="employee-stats-grid">
        {requestStats.map((card) => (
          <div className="employee-stat-card" key={card.label}>
            <span>{card.label}</span>
            <strong>{card.value}</strong>
          </div>
        ))}
      </div>

      <section className="employee-panel">
        <div className="module-toolbar">
          <div>
            <p className="sidebar-section-label">History</p>
            <h3 className="module-panel-title">Leave requests</h3>
          </div>
          <div className="leave-filter-row">
            {canShowApplyLeave ? (
              <button className="primary-button leave-apply-button" onClick={openApplyModal} type="button">
                <Send size={14} />
                Apply Leave
              </button>
            ) : null}
            <select className="sf-input module-filter-select" onChange={(event) => setEmployeeFilter(event.target.value)} value={employeeFilter}>
              <option value="all">All employees</option>
              {(meta.employees || []).map((employee) => (
                <option key={employee.id} value={employee.id}>
                  {employee.full_name} ({employee.employee_code})
                </option>
              ))}
            </select>
            <select className="sf-input module-filter-select" onChange={(event) => setStatusFilter(event.target.value)} value={statusFilter}>
              <option value="all">All statuses</option>
              <option value="pending">Pending</option>
              <option value="approved">Approved</option>
              <option value="rejected">Rejected</option>
            </select>
          </div>
        </div>

        <div className="employee-table-wrap">
          <table className="employee-table">
            <thead>
              <tr>
                <th>Employee</th>
                <th>Leave Type</th>
                <th>Start</th>
                <th>End</th>
                <th>Total Days</th>
                <th>Status</th>
                <th>Remarks</th>
                <th>Action</th>
              </tr>
            </thead>
            <tbody>
              {requests.map((request) => (
                <tr key={request.id}>
                  <td>
                    <div className="employee-primary-cell">
                      <strong>{request.employee_name || "--"}</strong>
                      <span>{request.employee_code || "--"}</span>
                    </div>
                  </td>
                  <td>{request.leave_type_name}</td>
                  <td>{formatDate(request.start_date)}</td>
                  <td>{formatDate(request.end_date)}</td>
                  <td>{request.total_days}</td>
                  <td>
                    <span className={`status-chip status-chip--${request.status}`}>
                      {request.status}
                    </span>
                  </td>
                  <td>{request.remarks || "--"}</td>
                  <td>
                    {canApprove && request.status === "pending" ? (
                      <div className="employee-row-actions">
                        <button
                          className="leave-action-button leave-action-button--approve"
                          disabled={decisionInFlightId === request.id}
                          onClick={() => handleDecision(request.id, "approved")}
                          type="button"
                        >
                          <CheckCircle2 size={14} />
                          {decisionInFlightId === request.id ? "Saving..." : "Approve"}
                        </button>
                        <button
                          className="leave-action-button leave-action-button--reject"
                          disabled={decisionInFlightId === request.id}
                          onClick={() => openRejectModal(request)}
                          type="button"
                        >
                          <XCircle size={14} />
                          Reject
                        </button>
                      </div>
                    ) : "--"}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>

          {!requests.length ? (
            <div className="employee-empty-state">
              <CalendarDays size={18} />
              <span>No leave requests found for the selected status.</span>
            </div>
          ) : null}
        </div>
      </section>

      {isApplyModalOpen ? (
        <div className="employee-form-overlay" role="presentation" onClick={closeApplyModal}>
          <form className="employee-panel employee-form-modal leave-apply-modal" onClick={(event) => event.stopPropagation()} onSubmit={handleApplyLeave}>
            <div className="employee-form-header">
              <div>
                <p className="sidebar-section-label">Apply Leave</p>
                <h3>New leave application</h3>
              </div>
              <button className="ghost-button employee-row-btn" onClick={closeApplyModal} type="button">
                Close
              </button>
            </div>

            <div className="employee-form-grid leave-apply-grid">
              <label className="sf-field employee-form-span-2">
                <span className="sf-label">Leave Type</span>
                <select
                  className={`sf-input ${formErrors.leave_type_id ? "is-invalid" : ""}`}
                  name="leave_type_id"
                  onChange={handleLeaveFormChange}
                  value={formState.leave_type_id}
                >
                  <option value="">Select leave type</option>
                  {(meta.leave_types || []).map((leaveType) => (
                    <option key={leaveType.id} value={leaveType.id}>
                      {leaveType.name}
                    </option>
                  ))}
                </select>
                {formErrors.leave_type_id ? <span className="sf-hint leave-reject-error">{formErrors.leave_type_id}</span> : null}
              </label>

              <label className="sf-field">
                <span className="sf-label">Start Date</span>
                <input
                  className={`sf-input ${formErrors.start_date ? "is-invalid" : ""}`}
                  name="start_date"
                  onChange={handleLeaveFormChange}
                  type="date"
                  value={formState.start_date}
                />
                {formErrors.start_date ? <span className="sf-hint leave-reject-error">{formErrors.start_date}</span> : null}
              </label>

              <label className="sf-field">
                <span className="sf-label">End Date</span>
                <input
                  className={`sf-input ${formErrors.end_date ? "is-invalid" : ""}`}
                  min={formState.start_date || undefined}
                  name="end_date"
                  onChange={handleLeaveFormChange}
                  type="date"
                  value={formState.end_date}
                />
                {formErrors.end_date ? <span className="sf-hint leave-reject-error">{formErrors.end_date}</span> : null}
              </label>

              <label className="sf-field employee-form-span-2">
                <span className="sf-label">Reason / Remarks</span>
                <textarea
                  className={`sf-input employee-textarea ${formErrors.reason ? "is-invalid" : ""}`}
                  name="reason"
                  onChange={handleLeaveFormChange}
                  placeholder="Enter your reason for leave"
                  value={formState.reason}
                />
                {formErrors.reason ? <span className="sf-hint leave-reject-error">{formErrors.reason}</span> : null}
              </label>
            </div>

            <div className="employee-form-header-actions leave-apply-actions">
              <button className="ghost-button" onClick={closeApplyModal} type="button">
                Cancel
              </button>
              <button className="primary-button" disabled={isSubmitting} type="submit">
                <Send size={14} />
                {isSubmitting ? "Submitting..." : "Submit Request"}
              </button>
            </div>
          </form>
        </div>
      ) : null}

      {rejectTarget ? (
        <div className="employee-form-overlay" role="presentation" onClick={closeRejectModal}>
          <form className="employee-panel employee-form-modal leave-reject-modal" onClick={(event) => event.stopPropagation()} onSubmit={handleRejectSubmit}>
            <div className="employee-form-header">
              <div>
                <p className="sidebar-section-label">Reject Leave</p>
                <h3>Rejection reason</h3>
              </div>
              <button className="ghost-button employee-row-btn" onClick={closeRejectModal} type="button">
                Close
              </button>
            </div>

            <div className="leave-reject-summary">
              <strong>{rejectTarget.employee_name || "Employee"}</strong>
              <span>{rejectTarget.leave_type_name} | {formatDate(rejectTarget.start_date)} - {formatDate(rejectTarget.end_date)}</span>
            </div>

            <label className="sf-field leave-reject-field">
              <span className="sf-label">Reason</span>
              <textarea
                className={`sf-input employee-textarea ${rejectError ? "is-invalid" : ""}`}
                onChange={(event) => {
                  setRejectReason(event.target.value);
                  if (rejectError) {
                    setRejectError("");
                  }
                }}
                placeholder="Enter the reason for rejecting this leave request"
                value={rejectReason}
              />
              {rejectError ? <span className="sf-hint leave-reject-error">{rejectError}</span> : null}
            </label>

            <div className="employee-form-header-actions leave-reject-actions">
              <button className="ghost-button" onClick={closeRejectModal} type="button">
                Cancel
              </button>
              <button className="primary-button leave-submit-reject" disabled={decisionInFlightId === rejectTarget.id} type="submit">
                <XCircle size={14} />
                {decisionInFlightId === rejectTarget.id ? "Rejecting..." : "Submit Rejection"}
              </button>
            </div>
          </form>
        </div>
      ) : null}
    </div>
  );
}

export default LeavePage;
