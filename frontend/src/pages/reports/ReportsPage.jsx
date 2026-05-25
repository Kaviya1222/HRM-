import { useEffect, useMemo, useState } from "react";
import {
  BarChart3,
  Eye,
  FileText,
  Send,
  ShieldCheck,
  Users,
  X,
} from "lucide-react";
import { fetchEmployeeSubmittedReport, fetchEmployeeSubmittedReports, submitEmployeeReport } from "../../api/reportApi";
import useAuth from "../../hooks/useAuth";

function formatSubmittedDate(value) {
  if (!value) {
    return "--";
  }

  return new Date(value).toLocaleDateString("en-IN", {
    day: "2-digit",
    month: "short",
    year: "numeric",
  });
}

function formatSubmittedTime(value) {
  if (!value) {
    return "--";
  }

  return new Date(value).toLocaleTimeString("en-IN", {
    hour: "2-digit",
    minute: "2-digit",
  });
}

function ReportsPage() {
  const { hasPermission } = useAuth();
  const [report, setReport] = useState({ items: [], total: 0 });
  const [feedback, setFeedback] = useState({ type: "", message: "" });
  const [isLoading, setIsLoading] = useState(true);
  const [selectedReport, setSelectedReport] = useState(null);
  const [formState, setFormState] = useState({ title: "", report_body: "" });
  const [formErrors, setFormErrors] = useState({});
  const [isSubmitting, setIsSubmitting] = useState(false);
  const canViewSubmittedReports = hasPermission("reports.view");
  const canSubmitReport = hasPermission("reports.submit") && !canViewSubmittedReports;

  const reportOverview = useMemo(() => {
    return {
      cards: [
        {
          label: "Employees in Report",
          value: report.total,
          icon: Users,
        },
      ],
    };
  }, [report]);

  async function loadReport() {
    if (!canViewSubmittedReports) {
      setIsLoading(false);
      return;
    }

    setIsLoading(true);

    try {
      const response = await fetchEmployeeSubmittedReports();
      setReport(response);
    } catch (error) {
      setFeedback({
        type: "error",
        message: error.response?.data?.detail || "Unable to load submitted reports.",
      });
    } finally {
      setIsLoading(false);
    }
  }

  useEffect(() => {
    loadReport();
  }, [canViewSubmittedReports]);

  function handleReportFormChange(event) {
    const { name, value } = event.target;
    setFormState((current) => ({ ...current, [name]: value }));
    if (formErrors[name]) {
      setFormErrors((current) => ({ ...current, [name]: "" }));
    }
  }

  function validateReportForm() {
    const errors = {};
    if (!formState.title.trim()) {
      errors.title = "Report title is required.";
    }
    if (!formState.report_body.trim()) {
      errors.report_body = "Report content is required.";
    }
    setFormErrors(errors);
    return Object.keys(errors).length === 0;
  }

  async function handleSubmitReport(event) {
    event.preventDefault();
    if (!validateReportForm()) {
      return;
    }

    setIsSubmitting(true);
    setFeedback({ type: "", message: "" });
    try {
      await submitEmployeeReport({
        title: formState.title.trim(),
        report_body: formState.report_body.trim(),
      });
      setFormState({ title: "", report_body: "" });
      setFeedback({ type: "success", message: "Report submitted successfully." });
    } catch (error) {
      setFeedback({
        type: "error",
        message: error.response?.data?.detail || "Unable to submit report.",
      });
    } finally {
      setIsSubmitting(false);
    }
  }

  async function handleViewReport(reportItem) {
    setFeedback({ type: "", message: "" });
    try {
      const response = await fetchEmployeeSubmittedReport(reportItem.id);
      setSelectedReport(response);
    } catch (error) {
      setFeedback({
        type: "error",
        message: error.response?.data?.detail || "Unable to load full report.",
      });
    }
  }

  if (isLoading) {
    return (
      <div className="page-container">
        <div className="settings-loading">
          <div className="settings-loading-spinner" />
          <span>Loading reports...</span>
        </div>
      </div>
    );
  }

  return (
    <div className="page-container employee-page reports-page">
      <div className="page-section-header">
        <div className="page-section-header-icon">
          <BarChart3 size={22} />
        </div>
        <div>
          <h2 className="page-section-header-title">Report</h2>
        </div>
      </div>

      {feedback.message ? (
        <div className={`employee-feedback employee-feedback--${feedback.type || "info"}`}>
          <ShieldCheck size={16} />
          <span>{feedback.message}</span>
        </div>
      ) : null}

      {canViewSubmittedReports ? (
        <div className="reports-summary-grid">
          {reportOverview.cards.map((card) => {
            const Icon = card.icon;
            return (
              <article className="reports-summary-card" key={card.label}>
                <div className="reports-summary-icon">
                  <Icon size={18} />
                </div>
                <div className="reports-summary-content">
                  <span>{card.label}</span>
                  <strong>{card.value}</strong>
                </div>
              </article>
            );
          })}
        </div>
      ) : null}

      {canSubmitReport ? (
        <section className="employee-panel reports-submit-panel">
          <form className="employee-form-grid reports-submit-form" onSubmit={handleSubmitReport}>
            <label className="sf-field employee-form-span-2">
              <span className="sf-label">Report Title / Subject</span>
              <input
                className={`sf-input ${formErrors.title ? "is-invalid" : ""}`}
                name="title"
                onChange={handleReportFormChange}
                placeholder="Enter report title"
                type="text"
                value={formState.title}
              />
              {formErrors.title ? <span className="sf-hint leave-reject-error">{formErrors.title}</span> : null}
            </label>
            <label className="sf-field employee-form-span-2">
              <span className="sf-label">Full Report Content</span>
              <textarea
                className={`sf-input employee-textarea reports-submit-textarea ${formErrors.report_body ? "is-invalid" : ""}`}
                name="report_body"
                onChange={handleReportFormChange}
                placeholder="Write your report details"
                value={formState.report_body}
              />
              {formErrors.report_body ? <span className="sf-hint leave-reject-error">{formErrors.report_body}</span> : null}
            </label>
            <div className="employee-form-actions employee-form-span-2">
              <button className="primary-button" disabled={isSubmitting} type="submit">
                <Send size={14} />
                {isSubmitting ? "Submitting..." : "Submit Report"}
              </button>
            </div>
          </form>
        </section>
      ) : null}

      {canViewSubmittedReports ? (
        <section className="employee-panel reports-results-panel">
          <div className="employee-table-wrap reports-table-wrap">
            <table className="employee-table reports-table">
              <thead>
                <tr>
                  <th>Employee Name</th>
                  <th>Department</th>
                  <th>Submitted Date</th>
                  <th>Submitted Time</th>
                  <th>Action</th>
                </tr>
              </thead>
              <tbody>
                {report.items.map((item) => (
                  <tr key={item.id}>
                    <td>
                      <div className="employee-primary-cell">
                        <strong>{item.employee_name}</strong>
                      </div>
                    </td>
                    <td>{item.department || "--"}</td>
                    <td>{formatSubmittedDate(item.submitted_at)}</td>
                    <td>{formatSubmittedTime(item.submitted_at)}</td>
                    <td>
                      <button
                        className="ghost-button reports-view-button"
                        onClick={() => handleViewReport(item)}
                        type="button"
                      >
                        <Eye size={14} />
                        View Full Report
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>

            {!report.items.length ? (
              <div className="employee-empty-state">
                <FileText size={18} />
                <span>No employee submitted reports found.</span>
              </div>
            ) : null}
          </div>
        </section>
      ) : null}

      {selectedReport ? (
        <div className="employee-form-overlay" role="presentation" onClick={() => setSelectedReport(null)}>
          <div className="employee-panel employee-form-modal reports-view-modal" role="dialog" aria-modal="true" onClick={(event) => event.stopPropagation()}>
            <div className="employee-form-header">
              <div>
                <p className="sidebar-section-label">Submitted Report</p>
                <h3>{selectedReport.employee_name}</h3>
              </div>
              <button
                className="ghost-button employee-row-btn"
                onClick={() => setSelectedReport(null)}
                type="button"
              >
                <X size={14} />
                Close
              </button>
            </div>

            <div className="reports-view-details">
              <div>
                <span>Department</span>
                <strong>{selectedReport.department || "--"}</strong>
              </div>
              <div>
                <span>Submitted Date</span>
                <strong>{formatSubmittedDate(selectedReport.submitted_at)}</strong>
              </div>
              <div>
                <span>Submitted Time</span>
                <strong>{formatSubmittedTime(selectedReport.submitted_at)}</strong>
              </div>
              <div>
                <span>Report Title</span>
                <strong>{selectedReport.title || "Employee Report"}</strong>
              </div>
            </div>

            <div className="reports-view-content">
              {selectedReport.report_body || "No report details were submitted."}
            </div>
          </div>
        </div>
      ) : null}
    </div>
  );
}

export default ReportsPage;
