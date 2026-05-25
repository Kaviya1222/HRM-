import { useEffect, useMemo, useState } from "react";
import {
  Banknote,
  ChevronDown,
  CircleDollarSign,
  Landmark,
  Plus,
  ReceiptText,
  RefreshCw,
  ShieldCheck,
  WalletCards,
  X,
} from "lucide-react";
import {
  addPayrollTransaction,
  fetchPayrollMeta,
  fetchPayrollTransactions,
} from "../../api/payrollApi";
import useAuth from "../../hooks/useAuth";

const ACTIONS = [
  { type: "income", label: "Income" },
  { type: "expense", label: "Expense" },
  { type: "salary", label: "Salary" },
  { type: "amount", label: "Amount" },
];

function createEmptyForm(type = "income") {
  return {
    transaction_type: type,
    amount: "",
    employee_id: "",
    transaction_date: new Date().toISOString().slice(0, 10),
    description: "",
  };
}

function formatCurrency(value) {
  return new Intl.NumberFormat("en-IN", {
    style: "currency",
    currency: "INR",
    maximumFractionDigits: 2,
  }).format(Number(value || 0));
}

function formatDate(value) {
  if (!value) {
    return "--";
  }
  return new Date(`${value}T00:00:00`).toLocaleDateString("en-IN");
}

function getErrorMessage(error, fallback) {
  const detail = error?.response?.data?.detail;
  if (typeof detail === "string") {
    return detail;
  }
  if (Array.isArray(detail)) {
    return detail.map((item) => item?.msg || item?.message || String(item)).filter(Boolean).join(" ");
  }
  if (detail && typeof detail === "object") {
    return detail.msg || detail.message || fallback;
  }
  return error?.message || fallback;
}

function PayrollPage() {
  const { hasPermission } = useAuth();
  const [meta, setMeta] = useState({ employees: [] });
  const [transactions, setTransactions] = useState([]);
  const [summary, setSummary] = useState({
    total_income: 0,
    total_expense: 0,
    total_salary: 0,
    total_amount: 0,
  });
  const [formState, setFormState] = useState(createEmptyForm());
  const [isActionMenuOpen, setIsActionMenuOpen] = useState(false);
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [isLoading, setIsLoading] = useState(true);
  const [isRefreshing, setIsRefreshing] = useState(false);
  const [isSaving, setIsSaving] = useState(false);
  const [feedback, setFeedback] = useState({ type: "", message: "" });

  const canManagePayroll = hasPermission("payroll.manage");

  const selectedAction = useMemo(
    () => ACTIONS.find((action) => action.type === formState.transaction_type) || ACTIONS[0],
    [formState.transaction_type],
  );

  const cards = useMemo(
    () => [
      { label: "Total Income", value: summary.total_income, icon: Landmark },
      { label: "Total Expense", value: summary.total_expense, icon: ReceiptText },
      { label: "Total Salary", value: summary.total_salary, icon: Banknote },
      { label: "Total Amount / Balance", value: summary.total_amount, icon: WalletCards },
    ],
    [summary],
  );

  async function loadPayrollData({ silent = false } = {}) {
    if (silent) {
      setIsRefreshing(true);
    } else {
      setIsLoading(true);
    }

    try {
      const [metaResponse, transactionResponse] = await Promise.all([
        fetchPayrollMeta(),
        fetchPayrollTransactions(),
      ]);
      setMeta(metaResponse);
      setTransactions(transactionResponse.items || []);
      setSummary(transactionResponse.summary || {
        total_income: 0,
        total_expense: 0,
        total_salary: 0,
        total_amount: 0,
      });
      setFeedback((current) => (current.type === "error" ? { type: "", message: "" } : current));
    } catch (error) {
      setFeedback({
        type: "error",
        message: getErrorMessage(error, "Unable to load payroll data."),
      });
    } finally {
      setIsLoading(false);
      setIsRefreshing(false);
    }
  }

  useEffect(() => {
    loadPayrollData();
  }, []);

  function openTransactionModal(type) {
    setFormState(createEmptyForm(type));
    setIsActionMenuOpen(false);
    setFeedback({ type: "", message: "" });
    setIsModalOpen(true);
  }

  function closeTransactionModal() {
    if (isSaving) {
      return;
    }
    setIsModalOpen(false);
  }

  function handleFormChange(event) {
    const { name, value } = event.target;
    setFormState((current) => {
      const next = {
        ...current,
        [name]: value,
      };

      if (name === "transaction_type" && value !== "salary") {
        next.employee_id = "";
      }

      return next;
    });
  }

  async function handleSubmit(event) {
    event.preventDefault();
    setFeedback({ type: "", message: "" });

    const amount = Number(formState.amount);
    if (!Number.isFinite(amount) || amount <= 0) {
      setFeedback({ type: "error", message: "Amount must be positive." });
      return;
    }
    if (formState.transaction_type === "salary" && !formState.employee_id) {
      setFeedback({ type: "error", message: "Employee selection is required for salary transactions." });
      return;
    }

    setIsSaving(true);
    try {
      const response = await addPayrollTransaction({
        transaction_type: formState.transaction_type,
        amount,
        employee_id: formState.transaction_type === "salary" ? formState.employee_id : null,
        transaction_date: formState.transaction_date,
        description: formState.description.trim() || null,
      });
      setSummary(response.summary);
      setTransactions((current) => [response.transaction, ...current]);
      setIsModalOpen(false);
      setFeedback({ type: "success", message: `${selectedAction.label} transaction added successfully.` });
    } catch (error) {
      setFeedback({
        type: "error",
        message: getErrorMessage(error, "Unable to save payroll transaction."),
      });
    } finally {
      setIsSaving(false);
    }
  }

  if (isLoading) {
    return (
      <div className="page-container">
        <div className="settings-loading">
          <div className="settings-loading-spinner" />
          <span>Loading payroll...</span>
        </div>
      </div>
    );
  }

  return (
    <div className="page-container employee-page payroll-page">
      <div className="page-section-header">
        <div className="page-section-header-icon">
          <CircleDollarSign size={22} />
        </div>
        <div>
          <h2 className="page-section-header-title">Payroll</h2>
          <p className="page-section-header-sub">Track income, expenses, salary payouts, and available payroll balance.</p>
        </div>
      </div>

      {feedback.message ? (
        <div className={`employee-feedback employee-feedback--${feedback.type || "info"}`}>
          <ShieldCheck size={16} />
          <span>{feedback.message}</span>
        </div>
      ) : null}

      <div className="payroll-summary-grid">
        {cards.map((card) => {
          const Icon = card.icon;
          return (
            <div className="payroll-summary-card" key={card.label}>
              <div className="payroll-summary-icon">
                <Icon size={20} />
              </div>
              <div className="payroll-summary-content">
                <span>{card.label}</span>
                <strong>{formatCurrency(card.value)}</strong>
              </div>
            </div>
          );
        })}
      </div>

      <section className="employee-panel payroll-table-panel">
        <div className="module-toolbar">
          <div>
            <p className="sidebar-section-label">History</p>
            <h3 className="module-panel-title">Payroll transactions</h3>
          </div>
          <div className="payroll-action-group">
            <button className="ghost-button" disabled={isRefreshing} onClick={() => loadPayrollData({ silent: true })} type="button">
              <RefreshCw className={isRefreshing ? "spin" : ""} size={15} />
              Refresh
            </button>

            {canManagePayroll ? (
              <div className="payroll-action-menu">
                <button
                  aria-expanded={isActionMenuOpen}
                  className="primary-button"
                  onClick={() => setIsActionMenuOpen((current) => !current)}
                  type="button"
                >
                  <Plus size={15} />
                  Payroll Action
                  <ChevronDown size={15} />
                </button>
                {isActionMenuOpen ? (
                  <div className="payroll-action-dropdown">
                    {ACTIONS.map((action) => (
                      <button key={action.type} onClick={() => openTransactionModal(action.type)} type="button">
                        {action.label}
                      </button>
                    ))}
                  </div>
                ) : null}
              </div>
            ) : null}
          </div>
        </div>

        <div className="employee-table-wrap payroll-table-wrap">
          <table className="employee-table payroll-table">
            <thead>
              <tr>
                <th>Type</th>
                <th>Employee</th>
                <th>Date</th>
                <th>Description</th>
                <th>Amount</th>
              </tr>
            </thead>
            <tbody>
              {transactions.map((transaction) => (
                <tr key={transaction.id}>
                  <td>
                    <span className={`status-chip status-chip--${transaction.transaction_type}`}>
                      {transaction.transaction_type}
                    </span>
                  </td>
                  <td>
                    <div className="employee-primary-cell">
                      <strong>{transaction.employee_name || "--"}</strong>
                      <span>{transaction.employee_code || "--"}</span>
                    </div>
                  </td>
                  <td>{formatDate(transaction.transaction_date)}</td>
                  <td>{transaction.description || "--"}</td>
                  <td className="payroll-table-highlight">{formatCurrency(transaction.amount)}</td>
                </tr>
              ))}
            </tbody>
          </table>

          {!transactions.length ? (
            <div className="employee-empty-state">
              <ReceiptText size={18} />
              <span>No payroll transactions found.</span>
            </div>
          ) : null}
        </div>
      </section>

      {isModalOpen ? (
        <div className="employee-form-overlay" onClick={closeTransactionModal} role="presentation">
          <form className="employee-panel employee-form-modal payroll-transaction-modal" onClick={(event) => event.stopPropagation()} onSubmit={handleSubmit}>
            <div className="employee-form-header">
              <div>
                <p className="sidebar-section-label">Payroll Action</p>
                <h3>{selectedAction.label}</h3>
              </div>
              <button className="ghost-button employee-row-btn" onClick={closeTransactionModal} type="button">
                <X size={14} />
                Close
              </button>
            </div>

            <div className="employee-form-grid payroll-form-grid">
              <label className="sf-field">
                <span className="sf-label">Type</span>
                <select className="sf-input" name="transaction_type" onChange={handleFormChange} value={formState.transaction_type}>
                  {ACTIONS.map((action) => (
                    <option key={action.type} value={action.type}>
                      {action.label}
                    </option>
                  ))}
                </select>
              </label>

              <label className="sf-field">
                <span className="sf-label">Amount</span>
                <input className="sf-input" min="0.01" name="amount" onChange={handleFormChange} required step="0.01" type="number" value={formState.amount} />
              </label>

              {formState.transaction_type === "salary" ? (
                <label className="sf-field employee-form-span-2">
                  <span className="sf-label">Employee</span>
                  <select className="sf-input" name="employee_id" onChange={handleFormChange} required value={formState.employee_id}>
                    <option value="">Select employee</option>
                    {(meta.employees || []).map((employee) => (
                      <option key={employee.id} value={employee.id}>
                        {employee.full_name} ({employee.employee_code})
                      </option>
                    ))}
                  </select>
                </label>
              ) : null}

              <label className="sf-field">
                <span className="sf-label">Date</span>
                <input className="sf-input" name="transaction_date" onChange={handleFormChange} required type="date" value={formState.transaction_date} />
              </label>

              <label className={`sf-field ${formState.transaction_type === "salary" ? "" : "employee-form-span-2"}`}>
                <span className="sf-label">Description</span>
                <textarea className="sf-input employee-textarea" name="description" onChange={handleFormChange} rows="3" value={formState.description} />
              </label>
            </div>

            <div className="employee-form-header-actions payroll-submit-row">
              <button className="ghost-button" onClick={closeTransactionModal} type="button">
                Cancel
              </button>
              <button className="primary-button" disabled={isSaving} type="submit">
                <WalletCards size={15} />
                {isSaving ? "Saving..." : "Save Transaction"}
              </button>
            </div>
          </form>
        </div>
      ) : null}
    </div>
  );
}

export default PayrollPage;
