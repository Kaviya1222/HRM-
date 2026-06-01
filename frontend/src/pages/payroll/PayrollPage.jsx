import { useEffect, useMemo, useState } from "react";
import {
  Banknote,
  ChevronDown,
  CircleDollarSign,
  Download,
  Eye,
  Landmark,
  Pencil,
  Plus,
  ReceiptText,
  RefreshCw,
  ShieldCheck,
  WalletCards,
  X,
} from "lucide-react";
import {
  addPayrollTransaction,
  calculatePayslip,
  fetchPayrollAttendanceSummary,
  fetchPayrollMeta,
  fetchPayrollTransactions,
  fetchSalaryProfile,
  fetchSalaryProfiles,
  saveSalaryProfile,
  updateSalaryProfile,
} from "../../api/payrollApi";
import useAuth from "../../hooks/useAuth";

const ACTIONS = [
  { type: "income", label: "Income" },
  { type: "expense", label: "Expense" },
  { type: "salary", label: "Salary" },
  { type: "amount", label: "Amount" },
];
const PAYROLL_UPDATED_EVENT = "hrm:payroll-updated";
const PAYROLL_UPDATED_AT_KEY = "hrm:payroll-updated-at";

function notifyPayrollUpdated() {
  const updatedAt = String(Date.now());
  localStorage.setItem(PAYROLL_UPDATED_AT_KEY, updatedAt);
  window.dispatchEvent(new CustomEvent(PAYROLL_UPDATED_EVENT, { detail: { updatedAt } }));
}

function createEmptyForm(type = "income") {
  return {
    transaction_type: type,
    amount: "",
    employee_id: "",
    transaction_date: new Date().toISOString().slice(0, 10),
    description: "",
  };
}

function createSalaryProfileForm() {
  return {
    employee_id: "",
    employee_name: "",
    date_joined: "",
    department: "",
    sub_department: "",
    designation: "",
    payment_mode: "",
    bank: "",
    bank_ifsc: "",
    bank_account_number: "",
    uan: "",
    pf_number: "",
    pan_number: "",
    actual_payable_days: "",
    total_working_days: "",
    loss_of_pay: "",
    present_days: "",
  };
}

function createPayslipForm() {
  return {
    employee_id: "",
    monthly_salary: "",
    period: new Date().toISOString().slice(0, 7),
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

function formatDayValue(value) {
  if (value === null || value === undefined || value === "") {
    return "";
  }
  return Number(value || 0).toFixed(2);
}

function calculateLossOfPay(totalWorkingDays, presentDays) {
  const total = Number(totalWorkingDays || 0);
  const present = Number(presentDays || 0);
  return Math.max(total - present, 0).toFixed(2);
}

function formatPdfMoney(value) {
  return new Intl.NumberFormat("en-IN", {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  }).format(Number(value || 0));
}

function formatPdfDay(value) {
  return Number(value || 0).toFixed(2);
}

function escapePdfText(value) {
  return String(value ?? "N/A").replace(/\\/g, "\\\\").replace(/\(/g, "\\(").replace(/\)/g, "\\)");
}

function buildPayslipPdf(payslip) {
  const pageWidth = 595;
  const pageHeight = 842;
  const commands = [];
  const text = (value, x, y, size = 10, font = "F1") => {
    commands.push(`BT /${font} ${size} Tf ${x} ${pageHeight - y} Td (${escapePdfText(value)}) Tj ET`);
  };
  const line = (x1, y1, x2, y2, width = 1) => {
    commands.push(`${width} w ${x1} ${pageHeight - y1} m ${x2} ${pageHeight - y2} l S`);
  };
  const fillRect = (x, y, width, height, gray = 0.96) => {
    commands.push(`${gray} g ${x} ${pageHeight - y - height} ${width} ${height} re f 0 g`);
  };
  const wrapText = (value, limit) => {
    const words = String(value || "N/A").split(/\s+/);
    const lines = [];
    words.forEach((word) => {
      const current = lines[lines.length - 1] || "";
      if (!current || `${current} ${word}`.length > limit) {
        lines.push(word);
      } else {
        lines[lines.length - 1] = `${current} ${word}`;
      }
    });
    return lines;
  };
  const labelValue = (label, value, x, y, colWidth = 125) => {
    text(label, x, y, 9, "F1");
    wrapText(value, 22).slice(0, 2).forEach((lineText, index) => {
      text(lineText, x, y + 18 + index * 13, 11, "F2");
    });
    return colWidth;
  };
  const employee = payslip.employee || {};
  const details = payslip.salary_details || {};
  const earnings = payslip.earnings || {};
  const period = details.month && details.year ? `${String(details.month).padStart(2, "0")}/${details.year}` : "";

  text(`PAYSLIP ${period}`, 38, 32, 16, "F2");
  line(38, 48, 557, 48, 1.2);

  const rows = [
    [
      ["Employee Number", employee.employee_number],
      ["Date Joined", formatDate(employee.date_joined)],
      ["Department", employee.department],
      ["Sub Department", employee.sub_department],
    ],
    [
      ["Designation", employee.designation],
      ["Payment Mode", employee.payment_mode],
      ["Bank", employee.bank],
      ["Bank IFSC", employee.bank_ifsc],
    ],
    [
      ["Bank Account", employee.bank_account],
      ["UAN", employee.uan],
      ["PF Number", employee.pf_number],
      ["PAN Number", employee.pan_number],
    ],
  ];
  rows.forEach((row, rowIndex) => {
    const y = 66 + rowIndex * 58;
    row.forEach(([label, value], index) => labelValue(label, value, 38 + index * 142, y));
    line(38, y + 40, 557, y + 40, 0.5);
  });

  text("SALARY DETAILS", 38, 260, 12, "F2");
  line(38, 276, 557, 276, 1);
  [
    ["Actual Payable Days", formatPdfDay(details.actual_payable_days)],
    ["Total Working Days", formatPdfDay(details.total_working_days)],
    ["Loss Of Pay Days", formatPdfDay(details.loss_of_pay_days)],
    ["Days Payable", formatPdfDay(details.days_payable)],
  ].forEach(([label, value], index) => labelValue(label, value, 38 + index * 142, 294));
  line(38, 336, 557, 336, 0.5);

  text("EARNINGS", 38, 372, 12, "F2");
  const earningRows = [
    ["Basic", earnings.basic],
    ["HRA", earnings.hra],
    ["Medical Allowance", earnings.medical_allowance],
    ["Transport Allowance", earnings.transport_allowance],
    ["Special Allowance", earnings.special_allowance],
    ["Total Earnings", earnings.total_earnings, true],
  ];
  earningRows.forEach(([label, value, bold], index) => {
    const y = 398 + index * 22;
    text(label, 38, y, 11, bold ? "F2" : "F1");
    text(formatPdfMoney(value), 278, y, 11, bold ? "F2" : "F1");
  });

  fillRect(38, 552, 519, 72);
  text("Net Salary Payable", 58, 578, 11, "F1");
  text(formatPdfMoney(payslip.net_salary_payable), 278, 578, 11, "F2");
  text("Net Salary in words", 58, 610, 11, "F1");
  wrapText(payslip.net_salary_words, 48).slice(0, 2).forEach((lineText, index) => {
    text(lineText, 278, 610 + index * 13, 10, "F2");
  });
  text("**Note :", 38, 650, 11, "F2");
  text(payslip.note, 104, 650, 11, "F1");
  text(`*${payslip.footer}`, 38, 706, 9, "F1");

  const content = commands.join("\n");
  const objects = [
    "<< /Type /Catalog /Pages 2 0 R >>",
    "<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
    "<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Resources << /Font << /F1 4 0 R /F2 5 0 R >> >> /Contents 6 0 R >>",
    "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold >>",
    `<< /Length ${content.length} >>\nstream\n${content}\nendstream`,
  ];
  let pdf = "%PDF-1.4\n";
  const offsets = [0];
  objects.forEach((object, index) => {
    offsets.push(pdf.length);
    pdf += `${index + 1} 0 obj\n${object}\nendobj\n`;
  });
  const xrefOffset = pdf.length;
  pdf += `xref\n0 ${objects.length + 1}\n0000000000 65535 f \n`;
  offsets.slice(1).forEach((offset) => {
    pdf += `${String(offset).padStart(10, "0")} 00000 n \n`;
  });
  pdf += `trailer\n<< /Size ${objects.length + 1} /Root 1 0 R >>\nstartxref\n${xrefOffset}\n%%EOF`;
  return new Blob([pdf], { type: "application/pdf" });
}

function downloadPayslipPdf(payslip) {
  const employeeNumber = payslip.employee?.employee_number || "employee";
  const month = String(payslip.salary_details?.month || "").padStart(2, "0");
  const year = payslip.salary_details?.year || "";
  const blob = buildPayslipPdf(payslip);
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = `payslip-${employeeNumber}-${month}-${year}.pdf`;
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
}

function PayrollPage() {
  const { hasPermission } = useAuth();
  const [meta, setMeta] = useState({ employees: [] });
  const [transactions, setTransactions] = useState([]);
  const [salaryProfiles, setSalaryProfiles] = useState([]);
  const [summary, setSummary] = useState({
    total_income: 0,
    total_expense: 0,
    total_salary: 0,
    total_amount: 0,
  });
  const [formState, setFormState] = useState(createEmptyForm());
  const [salaryProfileForm, setSalaryProfileForm] = useState(createSalaryProfileForm());
  const [salaryProfileStatus, setSalaryProfileStatus] = useState("");
  const [payslipForm, setPayslipForm] = useState(createPayslipForm());
  const [attendanceSummary, setAttendanceSummary] = useState(null);
  const [isActionMenuOpen, setIsActionMenuOpen] = useState(false);
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [isSalaryModalOpen, setIsSalaryModalOpen] = useState(false);
  const [isPayslipModalOpen, setIsPayslipModalOpen] = useState(false);
  const [salaryModalMode, setSalaryModalMode] = useState("create");
  const [isLoading, setIsLoading] = useState(true);
  const [isRefreshing, setIsRefreshing] = useState(false);
  const [isSaving, setIsSaving] = useState(false);
  const [isPayslipSaving, setIsPayslipSaving] = useState(false);
  const [isProfileLoading, setIsProfileLoading] = useState(false);
  const [feedback, setFeedback] = useState({ type: "", message: "" });

  const canManagePayroll = hasPermission("payroll.manage");
  const canDownloadPayslip = hasPermission("payroll.download");
  const isSalaryReadOnly = salaryModalMode === "view";

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
      const [metaResponse, transactionResponse, salaryProfileResponse] = await Promise.all([
        fetchPayrollMeta(),
        fetchPayrollTransactions(),
        fetchSalaryProfiles(),
      ]);
      setMeta(metaResponse);
      setTransactions(transactionResponse.items || []);
      setSalaryProfiles(salaryProfileResponse.items || []);
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
    if (type === "salary") {
      setSalaryProfileForm(createSalaryProfileForm());
      setSalaryProfileStatus("");
      setAttendanceSummary(null);
      setSalaryModalMode("create");
      setIsActionMenuOpen(false);
      setFeedback({ type: "", message: "" });
      setIsSalaryModalOpen(true);
      return;
    }
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

  function closeSalaryModal() {
    if (isSaving || isProfileLoading) {
      return;
    }
    setIsSalaryModalOpen(false);
  }

  function openPayslipModal() {
    setPayslipForm(createPayslipForm());
    setFeedback({ type: "", message: "" });
    setIsPayslipModalOpen(true);
  }

  function closePayslipModal() {
    if (isPayslipSaving) {
      return;
    }
    setIsPayslipModalOpen(false);
  }

  function handlePayslipFormChange(event) {
    const { name, value } = event.target;
    setPayslipForm((current) => ({ ...current, [name]: value }));
  }

  function profileToForm(profile) {
    return {
      employee_id: profile?.employee_id || "",
      employee_name: profile?.employee_name || "",
      date_joined: (profile?.date_joined || "").slice(0, 10),
      department: profile?.department || "",
      sub_department: profile?.sub_department || "",
      designation: profile?.designation || "",
      payment_mode: profile?.payment_mode || "",
      bank: profile?.bank || "",
      bank_ifsc: profile?.bank_ifsc || "",
      bank_account_number: profile?.bank_account_number || "",
      uan: profile?.uan || "",
      pf_number: profile?.pf_number || "",
      pan_number: profile?.pan_number || "",
      actual_payable_days: formatDayValue(profile?.actual_payable_days),
      total_working_days: formatDayValue(profile?.total_working_days),
      loss_of_pay: formatDayValue(profile?.loss_of_pay),
      present_days: formatDayValue(profile?.present_days),
    };
  }

  function openSavedSalaryProfile(profile, mode) {
    setSalaryProfileForm(profileToForm(profile));
    setSalaryProfileStatus(mode === "view" ? "Viewing saved salary profile." : "Editing saved salary profile.");
    setAttendanceSummary(null);
    setSalaryModalMode(mode);
    setFeedback({ type: "", message: "" });
    setIsSalaryModalOpen(true);
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

  async function loadSalaryProfile(employeeId) {
    if (!employeeId) {
      setSalaryProfileForm(createSalaryProfileForm());
      setSalaryProfileStatus("");
      setAttendanceSummary(null);
      return;
    }

    const selectedEmployee = (meta.employees || []).find((employee) => employee.id === employeeId);
    setIsProfileLoading(true);
    setSalaryProfileStatus("Loading saved details...");
    try {
      const today = new Date();
      const [profileResponse, attendanceResponse] = await Promise.all([
        fetchSalaryProfile(employeeId),
        fetchPayrollAttendanceSummary({
          employee_id: employeeId,
          period_month: today.getMonth() + 1,
          period_year: today.getFullYear(),
        }),
      ]);
      const profile = profileResponse.profile;
      const defaults = profileResponse.defaults || {};
      const selectedEmployeeName = selectedEmployee?.full_name || "";
      const presentDays = profile?.present_days || defaults.present_days || attendanceResponse.worked_days;
      const totalWorkingDays = profile?.total_working_days || defaults.total_working_days || attendanceResponse.total_days;
      setSalaryProfileForm({
        employee_id: employeeId,
        employee_name: profile?.employee_name || selectedEmployeeName,
        date_joined: (profile?.date_joined || defaults.date_joined || selectedEmployee?.date_joined || "").slice(0, 10),
        department: profile?.department || defaults.department || selectedEmployee?.department || "",
        sub_department: profile?.sub_department || defaults.sub_department || "",
        designation: profile?.designation || defaults.designation || selectedEmployee?.designation || "",
        payment_mode: profile?.payment_mode || "",
        bank: profile?.bank || "",
        bank_ifsc: profile?.bank_ifsc || "",
        bank_account_number: profile?.bank_account_number || "",
        uan: profile?.uan || "",
        pf_number: profile?.pf_number || "",
        pan_number: profile?.pan_number || "",
        actual_payable_days: formatDayValue(profile?.actual_payable_days || defaults.actual_payable_days || presentDays),
        total_working_days: formatDayValue(totalWorkingDays),
        present_days: formatDayValue(presentDays),
        loss_of_pay: formatDayValue(profile?.loss_of_pay || defaults.loss_of_pay || calculateLossOfPay(totalWorkingDays, presentDays)),
      });
      setAttendanceSummary(attendanceResponse);
      setSalaryProfileStatus(profile ? "Saved salary profile loaded." : "No saved profile yet. Enter details once and save.");
    } catch (error) {
      setSalaryProfileStatus("");
      setAttendanceSummary(null);
      setFeedback({
        type: "error",
        message: getErrorMessage(error, "Unable to load salary profile."),
      });
    } finally {
      setIsProfileLoading(false);
    }
  }

  function handleSalaryProfileChange(event) {
    const { name, value } = event.target;
    if (isSalaryReadOnly) {
      return;
    }
    if (name === "employee_id") {
      loadSalaryProfile(value);
      return;
    }
    setSalaryProfileForm((current) => {
      const next = { ...current, [name]: value };
      if (name === "total_working_days" || name === "present_days") {
        const totalWorkingDays = name === "total_working_days" ? value : current.total_working_days;
        const presentDays = name === "present_days" ? value : current.present_days;
        next.loss_of_pay = calculateLossOfPay(totalWorkingDays, presentDays);
        if (name === "present_days" && !current.actual_payable_days) {
          next.actual_payable_days = formatDayValue(value);
        }
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
      notifyPayrollUpdated();
      void loadPayrollData({ silent: true });
    } catch (error) {
      setFeedback({
        type: "error",
        message: getErrorMessage(error, "Unable to save payroll transaction."),
      });
    } finally {
      setIsSaving(false);
    }
  }

  async function handleSalaryProfileSubmit(event) {
    event.preventDefault();
    setFeedback({ type: "", message: "" });

    if (!salaryProfileForm.employee_id) {
      setFeedback({ type: "error", message: "Employee ID is required." });
      return;
    }

    setIsSaving(true);
    try {
      const payload = {
        ...salaryProfileForm,
        date_joined: salaryProfileForm.date_joined || null,
        actual_payable_days: salaryProfileForm.actual_payable_days || null,
        total_working_days: salaryProfileForm.total_working_days || null,
        present_days: salaryProfileForm.present_days || null,
        loss_of_pay: salaryProfileForm.loss_of_pay || null,
      };
      const response = salaryProfiles.some((profile) => profile.employee_id === salaryProfileForm.employee_id)
        ? await updateSalaryProfile(salaryProfileForm.employee_id, payload)
        : await saveSalaryProfile(payload);
      setSalaryProfileForm((current) => ({
        ...current,
        ...(response.profile || {}),
        date_joined: (response.profile?.date_joined || current.date_joined || "").slice(0, 10),
        actual_payable_days: formatDayValue(response.profile?.actual_payable_days ?? current.actual_payable_days),
        total_working_days: formatDayValue(response.profile?.total_working_days ?? current.total_working_days),
        present_days: formatDayValue(response.profile?.present_days ?? current.present_days),
        loss_of_pay: formatDayValue(response.profile?.loss_of_pay ?? current.loss_of_pay),
      }));
      setSalaryProfiles((current) => {
        const savedProfile = response.profile;
        if (!savedProfile) {
          return current;
        }
        const exists = current.some((profile) => profile.employee_id === savedProfile.employee_id);
        if (exists) {
          return current.map((profile) => (profile.employee_id === savedProfile.employee_id ? savedProfile : profile));
        }
        return [savedProfile, ...current];
      });
      setSalaryModalMode("edit");
      setSalaryProfileStatus("Saved salary profile loaded.");
      if (response.summary) {
        setSummary(response.summary);
      }
      setFeedback({ type: "success", message: response.message || "Salary profile saved successfully." });
      notifyPayrollUpdated();
      void loadPayrollData({ silent: true });
    } catch (error) {
      setFeedback({
        type: "error",
        message: getErrorMessage(error, "Unable to save salary profile."),
      });
    } finally {
      setIsSaving(false);
    }
  }

  async function handlePayslipSubmit(event) {
    event.preventDefault();
    setFeedback({ type: "", message: "" });

    const salary = Number(payslipForm.monthly_salary);
    if (!payslipForm.employee_id) {
      setFeedback({ type: "error", message: "Employee ID is required." });
      return;
    }
    if (!Number.isFinite(salary) || salary <= 0) {
      setFeedback({ type: "error", message: "Monthly salary must be positive." });
      return;
    }
    if (!payslipForm.period) {
      setFeedback({ type: "error", message: "Month and year are required." });
      return;
    }

    const [year, month] = payslipForm.period.split("-").map(Number);
    setIsPayslipSaving(true);
    try {
      const response = await calculatePayslip({
        employee_id: payslipForm.employee_id,
        monthly_salary: salary,
        month,
        year,
      });
      downloadPayslipPdf(response.payslip);
      if (response.summary) {
        setSummary(response.summary);
      }
      if (response.transaction) {
        setTransactions((current) => {
          const exists = current.some((transaction) => transaction.id === response.transaction.id);
          if (exists) {
            return current.map((transaction) => (transaction.id === response.transaction.id ? response.transaction : transaction));
          }
          return [response.transaction, ...current];
        });
      }
      notifyPayrollUpdated();
      void loadPayrollData({ silent: true });
      setIsPayslipModalOpen(false);
      setFeedback({ type: "success", message: "Payslip PDF downloaded successfully." });
    } catch (error) {
      setFeedback({
        type: "error",
        message: getErrorMessage(error, "Unable to calculate payslip."),
      });
    } finally {
      setIsPayslipSaving(false);
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
            {canDownloadPayslip ? (
              <button className="ghost-button payroll-download-button" onClick={openPayslipModal} type="button">
                <Download size={15} />
                Download Payslip
              </button>
            ) : null}

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

      <section className="employee-panel payroll-table-panel">
        <div className="module-toolbar">
          <div>
            <p className="sidebar-section-label">Salary Details</p>
            <h3 className="module-panel-title">Saved salary employee details</h3>
          </div>
        </div>

        <div className="employee-table-wrap payroll-table-wrap">
          <table className="employee-table payroll-table payroll-salary-profile-table">
            <thead>
              <tr>
                <th>Employee ID</th>
                <th>Date of Joining</th>
                <th>Department</th>
                <th>Sub Department</th>
                <th>Designation</th>
                <th>Payment Mode</th>
                <th>Bank</th>
                <th>Bank IFSC</th>
                <th>Bank Account Number</th>
                <th>UAN</th>
                <th>PF Number</th>
                <th>PAN Number</th>
                <th>Actual Payable Days</th>
                <th>Total Working Days</th>
                <th>Present Days</th>
                <th>Loss of Pay</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              {salaryProfiles.map((profile) => (
                <tr key={profile.id || profile.employee_id}>
                  <td>
                    <div className="employee-primary-cell">
                      <strong>{profile.employee_name || "--"}</strong>
                      <span>{profile.employee_code || "--"}</span>
                    </div>
                  </td>
                  <td>{formatDate(profile.date_joined)}</td>
                  <td>{profile.department || "--"}</td>
                  <td>{profile.sub_department || "--"}</td>
                  <td>{profile.designation || "--"}</td>
                  <td>{profile.payment_mode || "--"}</td>
                  <td>{profile.bank || "--"}</td>
                  <td>{profile.bank_ifsc || "--"}</td>
                  <td>{profile.bank_account_number || "--"}</td>
                  <td>{profile.uan || "--"}</td>
                  <td>{profile.pf_number || "--"}</td>
                  <td>{profile.pan_number || "--"}</td>
                  <td>{formatDayValue(profile.actual_payable_days) || "--"}</td>
                  <td>{formatDayValue(profile.total_working_days) || "--"}</td>
                  <td>{formatDayValue(profile.present_days) || "--"}</td>
                  <td>{formatDayValue(profile.loss_of_pay) || "--"}</td>
                  <td>
                    <div className="employee-row-actions">
                      <button className="ghost-button employee-row-btn" onClick={() => openSavedSalaryProfile(profile, "view")} type="button">
                        <Eye size={14} />
                        View
                      </button>
                      {canManagePayroll ? (
                        <button className="ghost-button employee-row-btn" onClick={() => openSavedSalaryProfile(profile, "edit")} type="button">
                          <Pencil size={14} />
                          Edit
                        </button>
                      ) : null}
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>

          {!salaryProfiles.length ? (
            <div className="employee-empty-state">
              <WalletCards size={18} />
              <span>No salary employee details saved yet.</span>
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
                  {ACTIONS.filter((action) => action.type !== "salary").map((action) => (
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

      {isPayslipModalOpen ? (
        <div className="employee-form-overlay" onClick={closePayslipModal} role="presentation">
          <form className="employee-panel employee-form-modal payroll-transaction-modal payroll-payslip-modal" onClick={(event) => event.stopPropagation()} onSubmit={handlePayslipSubmit}>
            <div className="employee-form-header">
              <div>
                <p className="sidebar-section-label">Payroll</p>
                <h3>Download Payslip</h3>
              </div>
              <button className="ghost-button employee-row-btn" onClick={closePayslipModal} type="button">
                <X size={14} />
                Close
              </button>
            </div>

            <div className="employee-form-grid payroll-form-grid">
              <label className="sf-field employee-form-span-2">
                <span className="sf-label">Employee ID</span>
                <select className="sf-input" disabled={isPayslipSaving} name="employee_id" onChange={handlePayslipFormChange} required value={payslipForm.employee_id}>
                  <option value="">Select employee</option>
                  {(meta.employees || []).map((employee) => (
                    <option key={employee.id} value={employee.id}>
                      {employee.full_name} ({employee.employee_code})
                    </option>
                  ))}
                </select>
              </label>

              <label className="sf-field">
                <span className="sf-label">Monthly Salary</span>
                <input className="sf-input" disabled={isPayslipSaving} min="0.01" name="monthly_salary" onChange={handlePayslipFormChange} required step="0.01" type="number" value={payslipForm.monthly_salary} />
              </label>

              <label className="sf-field">
                <span className="sf-label">Month / Year</span>
                <input className="sf-input" disabled={isPayslipSaving} name="period" onChange={handlePayslipFormChange} required type="month" value={payslipForm.period} />
              </label>
            </div>

            <div className="employee-form-header-actions payroll-submit-row">
              <button className="ghost-button" onClick={closePayslipModal} type="button">
                Cancel
              </button>
              <button className="primary-button" disabled={isPayslipSaving} type="submit">
                <Download size={15} />
                {isPayslipSaving ? "Preparing..." : "Download PDF"}
              </button>
            </div>
          </form>
        </div>
      ) : null}

      {isSalaryModalOpen ? (
        <div className="employee-form-overlay" onClick={closeSalaryModal} role="presentation">
          <form className="employee-panel employee-form-modal payroll-transaction-modal payroll-salary-profile-modal" onClick={(event) => event.stopPropagation()} onSubmit={handleSalaryProfileSubmit}>
            <div className="employee-form-header">
              <div>
                <p className="sidebar-section-label">Payroll Action</p>
                <h3>{isSalaryReadOnly ? "View Salary Employee Details" : "Salary Employee Details"}</h3>
              </div>
              <button className="ghost-button employee-row-btn" onClick={closeSalaryModal} type="button">
                <X size={14} />
                Close
              </button>
            </div>

            <div className="employee-form-grid payroll-form-grid">
              <label className="sf-field employee-form-span-2">
                <span className="sf-label">Employee ID</span>
                <select className="sf-input" disabled={isProfileLoading || isSalaryReadOnly || salaryModalMode === "edit"} name="employee_id" onChange={handleSalaryProfileChange} required value={salaryProfileForm.employee_id}>
                  <option value="">Select employee</option>
                  {(meta.employees || []).map((employee) => (
                    <option key={employee.id} value={employee.id}>
                      {employee.full_name} ({employee.employee_code})
                    </option>
                  ))}
                </select>
              </label>

              <label className="sf-field">
                <span className="sf-label">Employee Name</span>
                <input className="sf-input" disabled name="employee_name" readOnly value={salaryProfileForm.employee_name} />
              </label>

              <label className="sf-field">
                <span className="sf-label">Date of Joining</span>
                <input className="sf-input" disabled={isSalaryReadOnly} name="date_joined" onChange={handleSalaryProfileChange} required type="date" value={salaryProfileForm.date_joined} />
              </label>

              <label className="sf-field">
                <span className="sf-label">Department</span>
                <input className="sf-input" disabled={isSalaryReadOnly} name="department" onChange={handleSalaryProfileChange} required value={salaryProfileForm.department} />
              </label>

              <label className="sf-field">
                <span className="sf-label">Sub Department</span>
                <input className="sf-input" disabled={isSalaryReadOnly} name="sub_department" onChange={handleSalaryProfileChange} required value={salaryProfileForm.sub_department} />
              </label>

              <label className="sf-field">
                <span className="sf-label">Designation</span>
                <input className="sf-input" disabled={isSalaryReadOnly} name="designation" onChange={handleSalaryProfileChange} required value={salaryProfileForm.designation} />
              </label>

              <label className="sf-field">
                <span className="sf-label">Payment Mode</span>
                <select className="sf-input" disabled={isSalaryReadOnly} name="payment_mode" onChange={handleSalaryProfileChange} required value={salaryProfileForm.payment_mode}>
                  <option value="">Select mode</option>
                  <option value="Bank Transfer">Bank Transfer</option>
                  <option value="Cash">Cash</option>
                  <option value="Cheque">Cheque</option>
                  <option value="UPI">UPI</option>
                </select>
              </label>

              <label className="sf-field">
                <span className="sf-label">Bank</span>
                <input className="sf-input" disabled={isSalaryReadOnly} name="bank" onChange={handleSalaryProfileChange} required value={salaryProfileForm.bank} />
              </label>

              <label className="sf-field">
                <span className="sf-label">Bank IFSC</span>
                <input className="sf-input" disabled={isSalaryReadOnly} name="bank_ifsc" onChange={handleSalaryProfileChange} required value={salaryProfileForm.bank_ifsc} />
              </label>

              <label className="sf-field">
                <span className="sf-label">Bank Account Number</span>
                <input className="sf-input" disabled={isSalaryReadOnly} name="bank_account_number" onChange={handleSalaryProfileChange} required value={salaryProfileForm.bank_account_number} />
              </label>

              <label className="sf-field">
                <span className="sf-label">UAN</span>
                <input className="sf-input" disabled={isSalaryReadOnly} name="uan" onChange={handleSalaryProfileChange} required value={salaryProfileForm.uan} />
              </label>

              <label className="sf-field">
                <span className="sf-label">PF Number</span>
                <input className="sf-input" disabled={isSalaryReadOnly} name="pf_number" onChange={handleSalaryProfileChange} required value={salaryProfileForm.pf_number} />
              </label>

              <label className="sf-field">
                <span className="sf-label">PAN Number</span>
                <input className="sf-input" disabled={isSalaryReadOnly} name="pan_number" onChange={handleSalaryProfileChange} required value={salaryProfileForm.pan_number} />
              </label>

              <label className="sf-field">
                <span className="sf-label">Actual Payable Days</span>
                <input className="sf-input" disabled={isSalaryReadOnly} min="0" name="actual_payable_days" onChange={handleSalaryProfileChange} required step="0.5" type="number" value={salaryProfileForm.actual_payable_days} />
              </label>

              <label className="sf-field">
                <span className="sf-label">Total Working Days</span>
                <input className="sf-input" disabled={isSalaryReadOnly} min="0" name="total_working_days" onChange={handleSalaryProfileChange} required step="0.5" type="number" value={salaryProfileForm.total_working_days} />
              </label>

              <label className="sf-field">
                <span className="sf-label">Present Days for selected/current month</span>
                <input className="sf-input" disabled={isSalaryReadOnly} min="0" name="present_days" onChange={handleSalaryProfileChange} required step="0.5" type="number" value={salaryProfileForm.present_days} />
              </label>

              <label className="sf-field">
                <span className="sf-label">Loss of Pay</span>
                <input className="sf-input" disabled={isSalaryReadOnly} min="0" name="loss_of_pay" onChange={handleSalaryProfileChange} required step="0.5" type="number" value={salaryProfileForm.loss_of_pay} />
              </label>

            </div>

            {salaryProfileStatus || attendanceSummary ? (
              <div className="payroll-profile-note">
                {salaryProfileStatus ? <span>{salaryProfileStatus}</span> : null}
                {attendanceSummary ? (
                  <strong>
                    Current month attendance: {Number(attendanceSummary.worked_days || 0).toFixed(2)} / {attendanceSummary.total_days || 0} days
                  </strong>
                ) : null}
              </div>
            ) : null}

            <div className="employee-form-header-actions payroll-submit-row">
              <button className="ghost-button" onClick={closeSalaryModal} type="button">
                {isSalaryReadOnly ? "Close" : "Cancel"}
              </button>
              {isSalaryReadOnly ? null : (
                <button className="primary-button" disabled={isSaving || isProfileLoading} type="submit">
                  <WalletCards size={15} />
                  {isSaving ? "Saving..." : "Save Salary Details"}
                </button>
              )}
            </div>
          </form>
        </div>
      ) : null}
    </div>
  );
}

export default PayrollPage;
