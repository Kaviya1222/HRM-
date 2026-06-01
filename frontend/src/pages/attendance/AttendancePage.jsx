import { useEffect, useMemo, useRef, useState } from "react";
import {
  CalendarDays,
  CalendarCheck,
  Clock3,
  Edit3,
  RefreshCw,
  Search,
  SlidersHorizontal,
  ShieldCheck,
} from "lucide-react";
import {
  correctAttendance,
  fetchAttendance,
  fetchAttendanceMeta,
  updateManualAttendance,
} from "../../api/attendanceApi";
import useAuth from "../../hooks/useAuth";

const EMPLOYEE_DIRECTORY_UPDATED_EVENT = "hrm:employees-updated";
const EMPLOYEE_DIRECTORY_UPDATED_AT_KEY = "hrm:employees-updated-at";
const ATTENDANCE_UPDATED_EVENT = "hrm:attendance-updated";
const ATTENDANCE_UPDATED_AT_KEY = "hrm:attendance-updated-at";
const MANUAL_ATTENDANCE_OPTIONS = [
  { value: "present", label: "Present" },
  { value: "absent", label: "Absent" },
  { value: "late_come", label: "Late Entry" },
  { value: "half_day", label: "Half Day" },
];

function formatDate(value) {
  if (!value) {
    return "--";
  }
  return new Date(value).toLocaleDateString("en-IN");
}

function formatTime(value) {
  if (!value) {
    return "--";
  }
  return new Date(value).toLocaleTimeString("en-IN", {
    hour: "numeric",
    minute: "2-digit",
  }).toUpperCase();
}

function formatHours(minutes) {
  if (!minutes) {
    return "0h 0m";
  }
  const totalMinutes = Number(minutes);
  const hours = Math.floor(totalMinutes / 60);
  const mins = totalMinutes % 60;
  return `${hours}h ${mins}m`;
}

function formatWorkedClock(minutes, seconds) {
  const totalSeconds = seconds != null
    ? Math.max(Number(seconds) || 0, 0)
    : Math.max(Number(minutes) || 0, 0) * 60;
  const hours = Math.floor(totalSeconds / 3600);
  const remainingSeconds = totalSeconds % 3600;
  const minutesPart = Math.floor(remainingSeconds / 60);
  const secondsPart = remainingSeconds % 60;
  return `${String(hours).padStart(2, "0")}:${String(minutesPart).padStart(2, "0")}:${String(secondsPart).padStart(2, "0")}`;
}

function toInputDateTime(value) {
  if (!value) {
    return "";
  }
  const parsed = new Date(value);
  const timezoneOffsetMs = parsed.getTimezoneOffset() * 60 * 1000;
  return new Date(parsed.getTime() - timezoneOffsetMs).toISOString().slice(0, 16);
}

function formatInputDate(value) {
  const parsed = value instanceof Date ? value : new Date(value);
  const year = parsed.getFullYear();
  const month = String(parsed.getMonth() + 1).padStart(2, "0");
  const day = String(parsed.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
}

function getMonthStart(value) {
  if (!value) {
    return "";
  }
  return `${value}-01`;
}

function getMonthEnd(value) {
  if (!value) {
    return "";
  }
  const [year, month] = value.split("-").map(Number);
  return formatInputDate(new Date(year, month, 0));
}

function formatMonthLabel(value) {
  if (!value) {
    return "--";
  }
  return new Date(`${value}-01T00:00:00`).toLocaleDateString("en-IN", {
    month: "long",
    year: "numeric",
  });
}

function getWeekRange(value = new Date()) {
  const baseDate = value instanceof Date ? new Date(value) : new Date(value);
  const dayOfWeek = baseDate.getDay();
  const distanceFromMonday = dayOfWeek === 0 ? -6 : 1 - dayOfWeek;
  const monday = new Date(baseDate);
  monday.setDate(baseDate.getDate() + distanceFromMonday);
  const saturday = new Date(monday);
  saturday.setDate(monday.getDate() + 5);

  return {
    start_date: formatInputDate(monday),
    end_date: formatInputDate(saturday),
  };
}

function getLastWeekRange(value = new Date()) {
  const currentWeek = getWeekRange(value);
  const previousMonday = new Date(`${currentWeek.start_date}T00:00:00`);
  previousMonday.setDate(previousMonday.getDate() - 7);
  const previousSaturday = new Date(previousMonday);
  previousSaturday.setDate(previousMonday.getDate() + 5);

  return {
    start_date: formatInputDate(previousMonday),
    end_date: formatInputDate(previousSaturday),
  };
}

function getLastSevenDaysRange(value = new Date()) {
  const endDate = value instanceof Date ? new Date(value) : new Date(value);
  const startDate = new Date(endDate);
  startDate.setDate(endDate.getDate() - 6);

  return {
    start_date: formatInputDate(startDate),
    end_date: formatInputDate(endDate),
  };
}

function buildAttendanceRecordKey(record) {
  const attendanceDate = record?.attendance_date ? formatInputDate(record.attendance_date) : "unknown-date";
  return `${record?.employee_id || "unknown-employee"}:${attendanceDate}`;
}

function normalizeAttendanceRecords(items) {
  const dedupedItems = new Map();

  for (const item of Array.isArray(items) ? items : []) {
    if (!item?.employee_id) {
      continue;
    }

    const normalizedItem = {
      ...item,
      employee_name: item.employee_name || "Unknown Employee",
      employee_code: item.employee_code || "--",
      department_name: item.department_name || "",
      designation_name: item.designation_name || "",
      status: item.status || "absent",
    };
    const itemKey = buildAttendanceRecordKey(normalizedItem);
    const existingItem = dedupedItems.get(itemKey);

    if (!existingItem || (normalizedItem.id && !existingItem.id)) {
      dedupedItems.set(itemKey, normalizedItem);
    }
  }

  return Array.from(dedupedItems.values());
}

function getInitials(name) {
  const parts = String(name || "Unknown Employee")
    .trim()
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2);

  if (!parts.length) {
    return "UE";
  }

  return parts.map((part) => part[0]?.toUpperCase() || "").join("");
}

function getAvatarTone(value) {
  const source = String(value || "employee");
  const tones = ["is-amber", "is-blue", "is-green", "is-purple"];
  const total = source.split("").reduce((sum, character) => sum + character.charCodeAt(0), 0);
  return tones[total % tones.length];
}

function getAttendanceStatusLabel(status) {
  if (status === "present") {
    return "Present";
  }
  if (status === "not_checked_in") {
    return "Not Checked In";
  }
  if (status === "leave") {
    return "Leave";
  }
  if (status === "absent") {
    return "Absent";
  }
  if (status === "half_day") {
    return "Half Day";
  }
  return String(status || "unknown").replace("_", " ");
}

function getAttendanceStatusTone(status) {
  if (status === "present") {
    return "is-active";
  }
  if (status === "not_checked_in") {
    return "is-neutral";
  }
  if (status === "leave") {
    return "is-leave";
  }
  if (status === "absent") {
    return "is-absent";
  }
  if (status === "half_day") {
    return "is-warning";
  }
  return "is-neutral";
}

function buildDateColumns(startDateValue, endDateValue) {
  if (!startDateValue || !endDateValue) {
    return [];
  }

  let startDate = new Date(`${startDateValue}T00:00:00`);
  let endDate = new Date(`${endDateValue}T00:00:00`);

  if (Number.isNaN(startDate.getTime()) || Number.isNaN(endDate.getTime())) {
    return [];
  }

  if (startDate > endDate) {
    [startDate, endDate] = [endDate, startDate];
  }

  const columns = [];
  const cursor = new Date(startDate);

  while (cursor <= endDate) {
    columns.push({
      key: formatInputDate(cursor),
      weekday: cursor.toLocaleDateString("en-IN", { weekday: "long" }),
      shortWeekday: cursor.toLocaleDateString("en-IN", { weekday: "short" }),
      dayNumber: cursor.getDate(),
      fullLabel: cursor.toLocaleDateString("en-IN", {
        day: "2-digit",
        month: "short",
        year: "numeric",
      }),
    });
    cursor.setDate(cursor.getDate() + 1);
  }

  return columns;
}

function getAttendanceCellPresentation(record, dateKey, defaultPresentDateKey) {
  if (!record) {
    if (dateKey !== defaultPresentDateKey) {
      return {
        primaryLabel: "",
        primaryTone: "is-neutral",
        secondaryLabel: "",
      };
    }

    return {
      primaryLabel: "Absent",
      primaryTone: "is-absent",
      secondaryLabel: "",
    };
  }

  if (record.status === "leave") {
    return {
      primaryLabel: "Leave",
      primaryTone: "is-leave",
      secondaryLabel: "",
    };
  }

  if (record.status === "absent") {
    return {
      primaryLabel: "Absent",
      primaryTone: "is-absent",
      secondaryLabel: "",
    };
  }

  if (record.status === "half_day") {
    return {
      primaryLabel: "Half Day",
      primaryTone: "is-late",
      secondaryLabel: record.work_minutes ? formatHours(record.work_minutes) : "",
    };
  }

  if (record.status === "present") {
    return {
      primaryLabel: record.is_late ? "Late Entry" : "Present",
      primaryTone: record.is_late ? "is-late" : "is-present",
      secondaryLabel: record.work_minutes ? formatHours(record.work_minutes) : "",
    };
  }

  return {
    primaryLabel: getAttendanceStatusLabel(record.status),
    primaryTone: "is-neutral",
    secondaryLabel: "",
  };
}

function getManualAttendanceValue(record, dateKey, defaultPresentDateKey) {
  if (!record) {
    return dateKey === defaultPresentDateKey ? "absent" : "";
  }
  if (record.status === "present" && record.is_late) {
    return "late_come";
  }
  if (record.status === "present") {
    return "present";
  }
  if (record.status === "half_day") {
    return "half_day";
  }
  return "absent";
}

function escapePdfText(value) {
  return String(value ?? "--").replace(/\\/g, "\\\\").replace(/\(/g, "\\(").replace(/\)/g, "\\)");
}

function createAttendanceReportPdf({ rows, rangeLabel, fromMonth, toMonth }) {
  const pageWidth = 842;
  const pageHeight = 595;
  const left = 28;
  const top = 550;
  const lineHeight = 14;
  const rowsPerPage = 28;
  const header = [
    "Date",
    "Emp ID",
    "Employee",
    "Dept",
    "Status",
    "In",
    "Out",
    "Hours",
    "P",
    "A",
  ];

  const pageRows = [];
  for (let index = 0; index < rows.length; index += rowsPerPage) {
    pageRows.push(rows.slice(index, index + rowsPerPage));
  }
  if (!pageRows.length) {
    pageRows.push([]);
  }

  const objects = [];
  function addObject(content) {
    objects.push(content);
    return objects.length;
  }

  const fontObjectId = addObject("<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>");
  const pageObjectIds = [];

  for (const [pageIndex, page] of pageRows.entries()) {
    const commands = [];
    const writeText = (x, y, text, size = 8, font = "F1") => {
      commands.push(`BT /${font} ${size} Tf ${x} ${y} Td (${escapePdfText(text)}) Tj ET`);
    };

    writeText(left, top, "Attendance Report", 18);
    writeText(left, top - 22, `Date Range: ${rangeLabel || `${formatMonthLabel(fromMonth)} - ${formatMonthLabel(toMonth)}`}`, 10);
    writeText(left, top - 40, `Generated: ${new Date().toLocaleString("en-IN")}`, 8);

    const columnX = [28, 96, 148, 260, 350, 420, 474, 532, 588, 616];
    header.forEach((label, index) => writeText(columnX[index], top - 66, label, 8));
    commands.push(`0.7 w ${left} ${top - 72} m 810 ${top - 72} l S`);

    page.forEach((row, rowIndex) => {
      const y = top - 90 - rowIndex * lineHeight;
      [
        row.attendanceDate,
        row.employeeCode,
        row.employeeName,
        row.department,
        row.status,
        row.checkIn,
        row.checkOut,
        row.hours,
        row.presentCount,
        row.absentCount,
      ].forEach((value, index) => {
        const safeValue = String(value ?? "--");
        writeText(columnX[index], y, safeValue.length > 18 ? `${safeValue.slice(0, 17)}...` : safeValue, 7);
      });
    });

    writeText(left, 24, `Generated: ${new Date().toLocaleString("en-IN")}`, 8);
    writeText(760, 24, `Page ${pageIndex + 1} of ${pageRows.length}`, 8);
    const stream = commands.join("\n");
    const contentObjectId = addObject(`<< /Length ${stream.length} >>\nstream\n${stream}\nendstream`);
    const pageObjectId = addObject(`<< /Type /Page /Parent 0 0 R /MediaBox [0 0 ${pageWidth} ${pageHeight}] /Resources << /Font << /F1 ${fontObjectId} 0 R >> >> /Contents ${contentObjectId} 0 R >>`);
    pageObjectIds.push(pageObjectId);
  }

  const pagesObjectId = addObject(`<< /Type /Pages /Kids [${pageObjectIds.map((id) => `${id} 0 R`).join(" ")}] /Count ${pageObjectIds.length} >>`);
  for (const pageObjectId of pageObjectIds) {
    objects[pageObjectId - 1] = objects[pageObjectId - 1].replace("/Parent 0 0 R", `/Parent ${pagesObjectId} 0 R`);
  }
  const catalogObjectId = addObject(`<< /Type /Catalog /Pages ${pagesObjectId} 0 R >>`);

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
  pdf += `trailer\n<< /Size ${objects.length + 1} /Root ${catalogObjectId} 0 R >>\nstartxref\n${xrefOffset}\n%%EOF`;

  return new Blob([pdf], { type: "application/pdf" });
}

function buildAttendanceReportRows(employees, records, defaultPresentDateKey) {
  const rowsByEmployee = new Map();

  for (const employee of Array.isArray(employees) ? employees : []) {
    rowsByEmployee.set(String(employee.id), {
      employeeName: employee.full_name || employee.employee_code || "Unknown Employee",
      employeeCode: employee.employee_code || "--",
      department: employee.department_name || "--",
      records: [],
    });
  }

  for (const record of Array.isArray(records) ? records : []) {
    const employeeId = String(record.employee_id);
    if (!rowsByEmployee.has(employeeId)) {
      rowsByEmployee.set(employeeId, {
        employeeName: record.employee_name || "Unknown Employee",
        employeeCode: record.employee_code || "--",
        department: record.department_name || "--",
        records: [],
      });
    }
    rowsByEmployee.get(employeeId).records.push(record);
  }

  const reportRows = [];
  for (const employee of rowsByEmployee.values()) {
    const presentCount = employee.records.filter((record) => record.status === "present").length;
    const absentCount = employee.records.filter((record) => record.status === "absent").length;

    if (!employee.records.length) {
      reportRows.push({
        employeeName: employee.employeeName,
        employeeCode: employee.employeeCode,
        department: employee.department,
        presentCount: 0,
        absentCount: 0,
        checkIn: "--",
        checkOut: "--",
        hours: "--",
        attendanceDate: "--",
        status: "--",
      });
      continue;
    }

    for (const record of employee.records) {
      const presentation = getAttendanceCellPresentation(
        record,
        formatInputDate(record.attendance_date),
        defaultPresentDateKey,
      );
      reportRows.push({
        employeeName: employee.employeeName,
        employeeCode: employee.employeeCode,
        department: employee.department,
        presentCount,
        absentCount,
        checkIn: record.check_in_at ? formatTime(record.check_in_at) : "--",
        checkOut: record.check_out_at ? formatTime(record.check_out_at) : "--",
        hours: record.work_minutes ? formatHours(record.work_minutes) : "--",
        attendanceDate: record.attendance_date ? formatDate(record.attendance_date) : "--",
        status: presentation.primaryLabel || getAttendanceStatusLabel(record.status),
      });
    }
  }

  return reportRows.sort((first, second) => String(first.employeeName).localeCompare(String(second.employeeName)));
}

function AttendancePage() {
  const { hasPermission } = useAuth();
  const correctionPanelRef = useRef(null);
  const loadDataRef = useRef(null);
  const fromMonthInputRef = useRef(null);
  const [meta, setMeta] = useState({ employees: [], thresholds: {} });
  const [records, setRecords] = useState([]);
  const [todaySummaryRecords, setTodaySummaryRecords] = useState([]);
  const [searchQuery, setSearchQuery] = useState("");
  const [dateFilterMode, setDateFilterMode] = useState("current_week");
  const [filters, setFilters] = useState(() => {
    const weekRange = getWeekRange();
    return {
      start_date: weekRange.start_date,
      end_date: weekRange.end_date,
      employee_id: "",
    };
  });
  const [feedback, setFeedback] = useState({ type: "", message: "" });
  const [isLoading, setIsLoading] = useState(true);
  const [isRefreshing, setIsRefreshing] = useState(false);
  const [isSubmittingAction, setIsSubmittingAction] = useState(false);
  const [savingAttendanceKey, setSavingAttendanceKey] = useState("");
  const [selectedEmployeeIds, setSelectedEmployeeIds] = useState([]);
  const [commonAttendanceStatus, setCommonAttendanceStatus] = useState("present");
  const [isSavingBulkAttendance, setIsSavingBulkAttendance] = useState(false);
  const [reportFromMonth, setReportFromMonth] = useState(() => formatInputDate(new Date()).slice(0, 7));
  const [reportToMonth, setReportToMonth] = useState(() => formatInputDate(new Date()).slice(0, 7));
  const [isReportModalOpen, setIsReportModalOpen] = useState(false);
  const [isGeneratingReport, setIsGeneratingReport] = useState(false);
  const [reportFilterMode, setReportFilterMode] = useState("today");
  const [reportStartDate, setReportStartDate] = useState(() => formatInputDate(new Date()));
  const [reportEndDate, setReportEndDate] = useState(() => formatInputDate(new Date()));
  const [correctionTarget, setCorrectionTarget] = useState(null);
  const [correctionForm, setCorrectionForm] = useState({
    check_in_at: "",
    check_out_at: "",
    reason: "",
  });
  const [correctionErrors, setCorrectionErrors] = useState({});

  const canCorrect = hasPermission("attendance.correct");

  function buildAttendanceFilters(activeFilters = filters, activeMode = dateFilterMode) {
    const today = new Date();
    const todayValue = formatInputDate(today);

    if (activeMode === "current_week") {
      const weekRange = getWeekRange(today);
      return {
        ...weekRange,
        employee_id: activeFilters.employee_id || undefined,
      };
    }

    if (activeMode === "today") {
      return {
        start_date: todayValue,
        end_date: todayValue,
        employee_id: activeFilters.employee_id || undefined,
      };
    }

    if (activeMode === "last_week") {
      const lastWeekRange = getLastWeekRange(today);
      return {
        ...lastWeekRange,
        employee_id: activeFilters.employee_id || undefined,
      };
    }

    if (activeMode === "last_7_days") {
      const lastSevenDaysRange = getLastSevenDaysRange(today);
      return {
        ...lastSevenDaysRange,
        employee_id: activeFilters.employee_id || undefined,
      };
    }

    if (activeMode === "current_month") {
      return {
        start_date: formatInputDate(new Date(today.getFullYear(), today.getMonth(), 1)),
        end_date: todayValue,
        employee_id: activeFilters.employee_id || undefined,
      };
    }

    if (activeMode === "custom_date") {
      const normalizedStartDate = activeFilters.start_date || activeFilters.end_date || "";
      const normalizedEndDate = activeFilters.end_date || activeFilters.start_date || "";
      return {
        start_date: normalizedStartDate || undefined,
        end_date: normalizedEndDate || undefined,
        employee_id: activeFilters.employee_id || undefined,
      };
    }

    if (activeMode === "month_range") {
      const fromMonth = activeFilters.from_month || reportFromMonth;
      const toMonth = activeFilters.to_month || reportToMonth || fromMonth;
      return {
        start_date: getMonthStart(fromMonth) || todayValue,
        end_date: getMonthEnd(toMonth || fromMonth) || todayValue,
        employee_id: activeFilters.employee_id || undefined,
      };
    }

    return {
      ...getWeekRange(today),
      employee_id: activeFilters.employee_id || undefined,
    };
  }

  const activeFilters = useMemo(
    () => buildAttendanceFilters(filters, dateFilterMode),
    [dateFilterMode, filters, reportFromMonth, reportToMonth],
  );

  const dateColumns = useMemo(
    () => buildDateColumns(activeFilters.start_date, activeFilters.end_date),
    [activeFilters.end_date, activeFilters.start_date],
  );

  const dateRangeLabel = useMemo(() => {
    if (!dateColumns.length) {
      return "No date range selected";
    }

    if (dateColumns.length === 1) {
      return dateColumns[0].fullLabel;
    }

    return `${dateColumns[0].fullLabel} - ${dateColumns[dateColumns.length - 1].fullLabel}`;
  }, [dateColumns]);

  const targetDateColumn = useMemo(() => {
    if (!dateColumns.length) {
      return null;
    }

    const todayValue = formatInputDate(new Date());
    return dateColumns.find((column) => column.key === todayValue) || dateColumns[dateColumns.length - 1];
  }, [dateColumns]);

  const summaryCards = useMemo(() => {
    const summaryDateKey = targetDateColumn?.key || formatInputDate(new Date());
    const summaryRecords = records.filter(
      (item) => item.attendance_date && formatInputDate(item.attendance_date) === summaryDateKey,
    );
    const employeeCount = meta.employees.length || summaryRecords.length;
    const lateCount = summaryRecords.filter((item) => item.status === "present" && item.is_late).length;
    const halfDayCount = summaryRecords.filter((item) => item.status === "half_day").length;
    const absentCount = summaryRecords.filter((item) => item.status === "absent").length;
    const presentRecordCount = summaryRecords.filter((item) => item.status === "present" && !item.is_late).length;
    const nonPresentCount = lateCount + halfDayCount + absentCount;
    const presentCount = Math.max(employeeCount - nonPresentCount, presentRecordCount);
    const unmarkedCount = 0;

    return [
      {
        label: "Present Today",
        value: String(presentCount).padStart(2, "0"),
        helper: `${unmarkedCount} people remaining`,
        icon: CalendarCheck,
        tone: "is-present",
      },
      {
        label: "Late Entry",
        value: String(lateCount).padStart(2, "0"),
        helper: `${presentCount} people are on time`,
        icon: Clock3,
        tone: "is-late",
      },
      {
        label: "Half Day",
        value: String(halfDayCount).padStart(2, "0"),
        helper: halfDayCount ? "Half-day attendance" : "No half-day records today",
        icon: ShieldCheck,
        tone: "is-half-day",
      },
      {
        label: "Absent",
        value: String(absentCount).padStart(2, "0"),
        helper: absentCount ? "Without informing" : "No unreported absence",
        icon: CalendarDays,
        tone: "is-absent",
      },
    ];
  }, [meta.employees.length, records, targetDateColumn]);

  const attendanceRows = useMemo(() => {
    const normalizedQuery = searchQuery.trim().toLowerCase();

    const rowsByEmployee = new Map();

    for (const employee of Array.isArray(meta.employees) ? meta.employees : []) {
      rowsByEmployee.set(String(employee.id), {
        employee_id: String(employee.id),
        employee_name: employee.full_name || employee.employee_code || "Unknown Employee",
        employee_code: employee.employee_code || "--",
        department_name: employee.department_name || "",
        designation_name: employee.designation_name || "",
        recordsByDate: {},
      });
    }

    for (const record of records) {
      const employeeId = String(record.employee_id);
      if (!rowsByEmployee.has(employeeId)) {
        rowsByEmployee.set(employeeId, {
          employee_id: employeeId,
          employee_name: record.employee_name || "Unknown Employee",
          employee_code: record.employee_code || "--",
          department_name: record.department_name || "",
          designation_name: record.designation_name || "",
          recordsByDate: {},
        });
      }

      const row = rowsByEmployee.get(employeeId);
      row.recordsByDate[formatInputDate(record.attendance_date)] = record;
    }

    return Array.from(rowsByEmployee.values())
      .filter((row) => {
        if (!normalizedQuery) {
          return true;
        }

        return [
          row.employee_name,
          row.employee_code,
          row.department_name,
          row.designation_name,
        ]
          .filter(Boolean)
          .some((value) => String(value).toLowerCase().includes(normalizedQuery));
      })
      .sort((first, second) => String(first.employee_name).localeCompare(String(second.employee_name)));
  }, [meta.employees, records, searchQuery]);

  const selectedAttendanceRows = useMemo(
    () => attendanceRows.filter((row) => selectedEmployeeIds.includes(row.employee_id)),
    [attendanceRows, selectedEmployeeIds],
  );

  const areAllVisibleEmployeesSelected = attendanceRows.length > 0 && selectedAttendanceRows.length === attendanceRows.length;

  const attendanceStatusCounts = useMemo(() => {
    const counts = MANUAL_ATTENDANCE_OPTIONS.reduce((result, option) => ({
      ...result,
      [option.value]: 0,
    }), {});

    if (!targetDateColumn) {
      return counts;
    }

    for (const row of attendanceRows) {
      const record = row.recordsByDate[targetDateColumn.key] || null;
      const manualValue = getManualAttendanceValue(record, targetDateColumn.key, targetDateColumn.key);
      if (manualValue) {
        counts[manualValue] += 1;
      }
    }

    return counts;
  }, [attendanceRows, targetDateColumn]);

  const attendanceReportRows = useMemo(() => {
    return buildAttendanceReportRows(meta.employees, records, targetDateColumn?.key);
  }, [meta.employees, records, targetDateColumn]);

  async function loadData({ silent = false, filterOverride, modeOverride } = {}) {
    const activeFilters = buildAttendanceFilters(filterOverride || filters, modeOverride || dateFilterMode);
    if (silent) {
      setIsRefreshing(true);
    } else {
      setIsLoading(true);
    }

    try {
      const todayValue = formatInputDate(new Date());
      const [metaResponse, recordsResponse, todayRecordsResponse] = await Promise.all([
        fetchAttendanceMeta(),
        fetchAttendance({
          start_date: activeFilters.start_date,
          end_date: activeFilters.end_date,
          employee_id: activeFilters.employee_id,
        }),
        fetchAttendance({
          start_date: todayValue,
          end_date: todayValue,
        }),
      ]);
      setMeta(metaResponse);
      setRecords(normalizeAttendanceRecords(recordsResponse.items));
      setTodaySummaryRecords(normalizeAttendanceRecords(todayRecordsResponse.items));
    } catch (error) {
      setFeedback({
        type: "error",
        message: error.response?.data?.detail || "Unable to load attendance data.",
      });
    } finally {
      setIsLoading(false);
      setIsRefreshing(false);
    }
  }

  useEffect(() => {
    loadData();
  }, []);

  useEffect(() => {
    function handleEmployeeDirectoryUpdate() {
      void loadData({ silent: true });
    }

    function handleAttendanceUpdate() {
      void loadData({ silent: true });
    }

    function handleStorage(event) {
      if (event.key === EMPLOYEE_DIRECTORY_UPDATED_AT_KEY) {
        void loadData({ silent: true });
      }
      if (event.key === ATTENDANCE_UPDATED_AT_KEY) {
        void loadData({ silent: true });
      }
    }

    window.addEventListener(EMPLOYEE_DIRECTORY_UPDATED_EVENT, handleEmployeeDirectoryUpdate);
    window.addEventListener(ATTENDANCE_UPDATED_EVENT, handleAttendanceUpdate);
    window.addEventListener("storage", handleStorage);

    return () => {
      window.removeEventListener(EMPLOYEE_DIRECTORY_UPDATED_EVENT, handleEmployeeDirectoryUpdate);
      window.removeEventListener(ATTENDANCE_UPDATED_EVENT, handleAttendanceUpdate);
      window.removeEventListener("storage", handleStorage);
    };
  }, []);

  useEffect(() => {
    if (!correctionTarget || !correctionPanelRef.current) {
      return;
    }

    correctionPanelRef.current.scrollIntoView({ behavior: "smooth", block: "start" });
  }, [correctionTarget]);

  useEffect(() => {
    setSelectedEmployeeIds((current) => {
      const visibleEmployeeIds = new Set(attendanceRows.map((row) => row.employee_id));
      return current.filter((employeeId) => visibleEmployeeIds.has(employeeId));
    });
  }, [attendanceRows]);

  function handleFilterChange(event) {
    const { name, value } = event.target;
    setFilters((current) => ({ ...current, [name]: value }));
  }

  function getPresetFilters(nextMode) {
    if (nextMode === "current_week") {
      const weekRange = getWeekRange();
      return {
        ...filters,
        start_date: weekRange.start_date,
        end_date: weekRange.end_date,
      };
    }

    if (nextMode === "current_month") {
      const today = new Date();
      return {
        ...filters,
        start_date: formatInputDate(new Date(today.getFullYear(), today.getMonth(), 1)),
        end_date: formatInputDate(today),
      };
    }

    if (nextMode === "today") {
      const todayValue = formatInputDate(new Date());
      return {
        ...filters,
        start_date: todayValue,
        end_date: todayValue,
      };
    }

    if (nextMode === "last_week") {
      const lastWeekRange = getLastWeekRange();
      return {
        ...filters,
        ...lastWeekRange,
      };
    }

    if (nextMode === "last_7_days") {
      const lastSevenDaysRange = getLastSevenDaysRange();
      return {
        ...filters,
        ...lastSevenDaysRange,
      };
    }

    return filters;
  }

  async function handleTableDateFilterChange(event) {
    const nextMode = event.target.value;
    const nextFilters = nextMode === "custom_date" ? filters : getPresetFilters(nextMode);

    setFeedback({ type: "", message: "" });
    setDateFilterMode(nextMode);
    setFilters(nextFilters);

    if (nextMode !== "custom_date") {
      await loadData({ silent: true, filterOverride: nextFilters, modeOverride: nextMode });
    }
  }

  async function handleInlineCustomDateChange(event) {
    const { name, value } = event.target;
    const nextFilters = { ...filters, [name]: value };

    setFeedback({ type: "", message: "" });
    setFilters(nextFilters);

    if (!nextFilters.start_date || !nextFilters.end_date) {
      return;
    }

    if (nextFilters.end_date < nextFilters.start_date) {
      setFeedback({ type: "error", message: "End Date cannot be before Start Date." });
      return;
    }

    await loadData({ silent: true, filterOverride: nextFilters, modeOverride: "custom_date" });
  }

  async function handleLogFilterSubmit(event) {
    event.preventDefault();
    await handleApplyAttendanceFilter();
  }

  async function handleLogFilterReset() {
    const weekRange = getWeekRange();
    const nextFilters = {
      ...filters,
      start_date: weekRange.start_date,
      end_date: weekRange.end_date,
    };
    setDateFilterMode("current_week");
    setIsReportModalOpen(false);
    setFilters(nextFilters);
    await loadData({ silent: true, filterOverride: nextFilters, modeOverride: "current_week" });
  }

  function handleReportMonthChange(field, value) {
    if (field === "from") {
      setReportFromMonth(value);
      if (reportToMonth && value && reportToMonth < value) {
        setReportToMonth(value);
      }
    } else {
      setReportToMonth(value);
    }
  }

  function handleApplyFilterClick() {
    setFeedback({ type: "", message: "" });
    const reportModes = new Set(["today", "current_week", "last_week", "current_month", "custom_date"]);
    setReportFilterMode(reportModes.has(dateFilterMode) ? dateFilterMode : "today");
    setReportStartDate(filters.start_date || formatInputDate(new Date()));
    setReportEndDate(filters.end_date || filters.start_date || formatInputDate(new Date()));
    setIsReportModalOpen(true);
  }

  async function handleApplyAttendanceFilter() {
    setFeedback({ type: "", message: "" });

    if (dateFilterMode === "custom_date" && (!filters.start_date || !filters.end_date)) {
      setFeedback({ type: "error", message: "Select a start and end date before applying the custom filter." });
      return false;
    }

    if (dateFilterMode === "custom_date" && filters.end_date < filters.start_date) {
      setFeedback({ type: "error", message: "End Date cannot be before Start Date." });
      return false;
    }

    await loadData({ silent: true, filterOverride: filters, modeOverride: dateFilterMode });
    return true;
  }

  async function handleReportSubmit(event) {
    event.preventDefault();
    setFeedback({ type: "", message: "" });
    const selectedMode = reportFilterMode || "today";
    const isCustomReport = selectedMode === "custom_date";

    if (isCustomReport && (!reportStartDate || !reportEndDate)) {
      setFeedback({ type: "error", message: "Select a start and end date before generating the report." });
      return;
    }

    if (isCustomReport && reportEndDate < reportStartDate) {
      setFeedback({ type: "error", message: "End Date cannot be before Start Date." });
      return;
    }

    const reportFilters = isCustomReport
      ? {
        ...filters,
        start_date: reportStartDate,
        end_date: reportEndDate,
      }
      : getPresetFilters(selectedMode);
    const rangeLabel = `${formatDate(reportFilters.start_date)} - ${formatDate(reportFilters.end_date)}`;

    setIsGeneratingReport(true);
    setDateFilterMode(selectedMode);
    try {
      const [metaResponse, recordsResponse] = await Promise.all([
        fetchAttendanceMeta(),
        fetchAttendance({
          start_date: reportFilters.start_date,
          end_date: reportFilters.end_date,
          employee_id: filters.employee_id || undefined,
        }),
      ]);
      const normalizedRecords = normalizeAttendanceRecords(recordsResponse.items);
      setMeta(metaResponse);
      setRecords(normalizedRecords);
      setFilters(reportFilters);
      setIsReportModalOpen(false);

      const blob = createAttendanceReportPdf({
        rows: buildAttendanceReportRows(metaResponse.employees, normalizedRecords, null),
        rangeLabel,
      });
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = `attendance-report-${reportFilters.start_date}-${reportFilters.end_date}.pdf`;
      document.body.appendChild(link);
      link.click();
      link.remove();
      URL.revokeObjectURL(url);
    } catch (error) {
      setFeedback({
        type: "error",
        message: error.response?.data?.detail || "Unable to generate attendance report.",
      });
    } finally {
      setIsGeneratingReport(false);
    }
  }

  function resetCorrectionPanel() {
    setCorrectionTarget(null);
    setCorrectionForm({ check_in_at: "", check_out_at: "", reason: "" });
    setCorrectionErrors({});
  }

  function handleCorrectionSelect(record) {
    setCorrectionTarget(record);
    setCorrectionForm({
      check_in_at: toInputDateTime(record.check_in_at),
      check_out_at: toInputDateTime(record.check_out_at),
      reason: "",
    });
    setCorrectionErrors({});
    setFeedback({ type: "", message: "" });
  }

  function handleCorrectionFieldChange(field, value) {
    setCorrectionForm((current) => ({ ...current, [field]: value }));
    setCorrectionErrors((current) => {
      if (!current[field]) {
        return current;
      }

      const nextErrors = { ...current };
      delete nextErrors[field];
      return nextErrors;
    });
  }

  function toggleEmployeeSelection(employeeId) {
    setSelectedEmployeeIds((current) => (
      current.includes(employeeId)
        ? current.filter((selectedEmployeeId) => selectedEmployeeId !== employeeId)
        : [...current, employeeId]
    ));
  }

  function toggleAllEmployeeSelection() {
    setSelectedEmployeeIds((current) => (
      attendanceRows.length > 0 && current.length === attendanceRows.length
        ? []
        : attendanceRows.map((row) => row.employee_id)
    ));
  }

  async function handleBulkAttendanceSave() {
    if (!selectedAttendanceRows.length || !targetDateColumn) {
      setFeedback({ type: "error", message: "Select at least one employee before saving attendance." });
      return;
    }

    setIsSavingBulkAttendance(true);
    setSavingAttendanceKey("bulk");
    setFeedback({ type: "", message: "" });

    try {
      const responses = await Promise.all(selectedAttendanceRows.map((row) => (
        updateManualAttendance({
          employee_id: row.employee_id,
          attendance_date: targetDateColumn.key,
          status: commonAttendanceStatus,
        })
      )));
      const updatedLogs = responses.map((response) => response.log).filter(Boolean);
      const updatedKeys = new Set(updatedLogs.map((log) => buildAttendanceRecordKey(log)));

      setRecords((current) => normalizeAttendanceRecords([
        ...current.filter((item) => !updatedKeys.has(buildAttendanceRecordKey(item))),
        ...updatedLogs,
      ]));
      setFeedback({
        type: "success",
        message: `Attendance saved for ${updatedLogs.length} employee${updatedLogs.length === 1 ? "" : "s"}.`,
      });
      const updatedAt = String(Date.now());
      localStorage.setItem(ATTENDANCE_UPDATED_AT_KEY, updatedAt);
      window.dispatchEvent(new CustomEvent(ATTENDANCE_UPDATED_EVENT, { detail: { updatedAt } }));
      await loadData({ silent: true });
    } catch (error) {
      setFeedback({
        type: "error",
        message: error.response?.data?.detail || "Unable to save attendance.",
      });
    } finally {
      setIsSavingBulkAttendance(false);
      setSavingAttendanceKey("");
    }
  }

  function validateCorrectionForm() {
    const nextErrors = {};
    const normalizedCheckIn = correctionForm.check_in_at.trim();
    const normalizedCheckOut = correctionForm.check_out_at.trim();
    const normalizedReason = correctionForm.reason.trim();

    let parsedCheckIn = null;
    let parsedCheckOut = null;

    if (!normalizedCheckIn) {
      nextErrors.check_in_at = "Corrected check-in is required.";
    } else {
      parsedCheckIn = new Date(normalizedCheckIn);
      if (Number.isNaN(parsedCheckIn.getTime())) {
        nextErrors.check_in_at = "Enter a valid corrected check-in date and time.";
      }
    }

    if (normalizedCheckOut) {
      parsedCheckOut = new Date(normalizedCheckOut);
      if (Number.isNaN(parsedCheckOut.getTime())) {
        nextErrors.check_out_at = "Enter a valid corrected check-out date and time.";
      }
    }

    if (parsedCheckIn && parsedCheckOut && parsedCheckOut < parsedCheckIn) {
      nextErrors.check_out_at = "Corrected check-out cannot be before corrected check-in.";
    }

    if (!normalizedReason) {
      nextErrors.reason = "Reason is required.";
    }

    return {
      errors: nextErrors,
      isValid: Object.keys(nextErrors).length === 0,
      normalizedPayload: {
        check_in_at: normalizedCheckIn,
        check_out_at: normalizedCheckOut,
        reason: normalizedReason,
      },
    };
  }

  async function handleCorrectionSubmit(event) {
    event.preventDefault();
    if (!correctionTarget?.id) {
      return;
    }

    const validation = validateCorrectionForm();
    if (!validation.isValid) {
      setCorrectionErrors(validation.errors);
      setFeedback({ type: "error", message: "Please fix the correction form errors before saving." });
      return;
    }

    setIsSubmittingAction(true);
    setCorrectionErrors({});
    setFeedback({ type: "", message: "" });
    try {
      await correctAttendance(correctionTarget.id, {
        check_in_at: validation.normalizedPayload.check_in_at ? new Date(validation.normalizedPayload.check_in_at).toISOString() : null,
        check_out_at: validation.normalizedPayload.check_out_at ? new Date(validation.normalizedPayload.check_out_at).toISOString() : null,
        reason: validation.normalizedPayload.reason,
      });
      setFeedback({ type: "success", message: "Attendance correction saved." });
      resetCorrectionPanel();
      await loadData({ silent: true });
    } catch (error) {
      setFeedback({
        type: "error",
        message: error.response?.data?.detail || "Unable to save attendance correction.",
      });
    } finally {
      setIsSubmittingAction(false);
    }
  }

  if (isLoading) {
    return (
      <div className="page-container">
        <div className="settings-loading">
          <div className="settings-loading-spinner" />
          <span>Loading attendance module...</span>
        </div>
      </div>
    );
  }

  return (
    <div className="page-container employee-page attendance-page">
      <div className="page-section-header">
        <div className="page-section-header-icon">
          <CalendarCheck size={22} />
        </div>
        <div>
          <h2 className="page-section-header-title">Employee Attendance</h2>
          <p className="page-section-header-sub">
            Analyse attendance records of employees with a clean day-by-day operational overview.
          </p>
        </div>
      </div>

      {feedback.message ? (
        <div className={`employee-feedback employee-feedback--${feedback.type || "info"}`}>
          <ShieldCheck size={16} />
          <span>{feedback.message}</span>
        </div>
      ) : null}

      <div className="attendance-summary-grid">
        {summaryCards.map((card) => {
          const Icon = card.icon;
          return (
            <article className={`attendance-summary-card ${card.tone}`} key={card.label}>
              <div className="attendance-summary-icon">
                <Icon size={18} />
              </div>
              <div className="attendance-summary-content">
                <span>{card.label}</span>
                <strong>{card.value}</strong>
                <p>{card.helper}</p>
              </div>
            </article>
          );
        })}
      </div>

      <section className="employee-panel attendance-log-panel">
        <div className="attendance-panel-head">
          <div>
            <p className="sidebar-section-label">Attendance Register</p>
            <h3 className="module-panel-title">Employee attendance overview</h3>
          </div>

          <div className="attendance-panel-meta">
            <span className="attendance-range-pill">{dateRangeLabel}</span>
          </div>
        </div>

        <div className="attendance-toolbar">
          <div className="attendance-search-shell">
            <Search className="attendance-search-icon" size={18} />
            <input
              className="attendance-search-input"
              onChange={(event) => setSearchQuery(event.target.value)}
              placeholder="Search anything ..."
              type="search"
              value={searchQuery}
            />
          </div>

          <form className="attendance-filter-bar" onSubmit={handleLogFilterSubmit}>
            <div className="attendance-filter-field attendance-filter-field--compact">
              <SlidersHorizontal size={15} />
              <select
                aria-label="Attendance table date filter"
                className="sf-input"
                onChange={handleTableDateFilterChange}
                value={dateFilterMode}
              >
                <option value="today">Today</option>
                <option value="current_week">Current Week</option>
                <option value="last_week">Last Week</option>
                <option value="last_7_days">Last 7 Days</option>
                <option value="current_month">Current Month</option>
                <option value="custom_date">Custom Date</option>
              </select>
            </div>
            {dateFilterMode === "custom_date" ? (
              <div className="attendance-date-range">
                <div className="attendance-filter-field attendance-filter-field--date">
                  <CalendarDays size={15} />
                  <input
                    aria-label="Start date"
                    className="sf-input"
                    name="start_date"
                    onChange={handleInlineCustomDateChange}
                    type="date"
                    value={filters.start_date}
                  />
                </div>
                <div className="attendance-filter-field attendance-filter-field--date">
                  <CalendarDays size={15} />
                  <input
                    aria-label="End date"
                    className="sf-input"
                    min={filters.start_date}
                    name="end_date"
                    onChange={handleInlineCustomDateChange}
                    type="date"
                    value={filters.end_date}
                  />
                </div>
              </div>
            ) : null}
            <button className="ghost-button" onClick={handleLogFilterReset} type="button">
              <Clock3 size={14} />
              Reset
            </button>
            <div className="attendance-filter-dropdown">
              <button className="primary-button" onClick={handleApplyFilterClick} type="button">
                <SlidersHorizontal size={14} />
                Apply Filter
              </button>
            </div>
          </form>
        </div>

        <div className="attendance-legend-row">
          <div className="attendance-bulk-controls">
            <select
              aria-label="Common attendance status"
              className="attendance-common-status-select"
              onChange={(event) => setCommonAttendanceStatus(event.target.value)}
              value={commonAttendanceStatus}
            >
              {MANUAL_ATTENDANCE_OPTIONS.map((option) => (
                <option key={option.value} value={option.value}>
                  {option.label}
                </option>
              ))}
            </select>
            <button
              className="primary-button attendance-save-button"
              disabled={!selectedAttendanceRows.length || !targetDateColumn || isSavingBulkAttendance}
              onClick={handleBulkAttendanceSave}
              type="button"
            >
              <CalendarCheck size={14} />
              {isSavingBulkAttendance ? "Saving..." : "Save Attendance"}
            </button>
            <span className="attendance-selected-employee-pill">
              Selected: {selectedAttendanceRows.length}
              {targetDateColumn ? <small>{targetDateColumn.fullLabel}</small> : null}
            </span>
          </div>

          <div className="attendance-status-counts" aria-label="Attendance status counts">
            {MANUAL_ATTENDANCE_OPTIONS.map((option) => (
              <span className={`attendance-status-count is-${option.value}`} key={option.value}>
                {option.label}
                <strong>{attendanceStatusCounts[option.value] || 0}</strong>
              </span>
            ))}
          </div>
        </div>

        <div className="attendance-table-wrap">
          <table className="attendance-matrix-table">
            <thead>
              <tr>
                <th>
                  <div className="attendance-employee-heading">
                    <label className="attendance-row-selector" onClick={(event) => event.stopPropagation()}>
                      <input
                        checked={areAllVisibleEmployeesSelected}
                        disabled={!attendanceRows.length}
                        onChange={toggleAllEmployeeSelection}
                        type="checkbox"
                      />
                      <span />
                    </label>
                    <span>Employee</span>
                  </div>
                </th>
                {dateColumns.map((column) => (
                  <th key={column.key}>
                    <span className="attendance-weekday-label">{column.shortWeekday}</span>
                    <small>{column.fullLabel}</small>
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {attendanceRows.map((row) => (
                <tr
                  className={selectedEmployeeIds.includes(row.employee_id) ? "is-selected" : ""}
                  key={row.employee_id}
                  onClick={() => toggleEmployeeSelection(row.employee_id)}
                >
                  <td>
                    <div className="attendance-employee-cell">
                      <label className="attendance-row-selector" onClick={(event) => event.stopPropagation()}>
                        <input
                          checked={selectedEmployeeIds.includes(row.employee_id)}
                          onChange={() => toggleEmployeeSelection(row.employee_id)}
                          type="checkbox"
                        />
                        <span />
                      </label>
                      <div className={`attendance-avatar ${getAvatarTone(row.employee_id || row.employee_name)}`}>
                        {getInitials(row.employee_name)}
                      </div>
                      <div className="attendance-employee-meta">
                        <strong>{row.employee_name || "Unknown Employee"}</strong>
                        <span>{row.employee_code || row.employee_id || "--"}</span>
                        <small>{row.department_name || "--"}</small>
                      </div>
                    </div>
                  </td>
                  {dateColumns.map((column) => {
                    const record = row.recordsByDate[column.key] || null;
                    const cellPresentation = getAttendanceCellPresentation(record, column.key, targetDateColumn?.key);

                    return (
                      <td key={column.key}>
                        <div className="attendance-day-cell">
                          <span className="attendance-day-number">{column.dayNumber}</span>
                          <div className="attendance-day-content">
                            {cellPresentation.primaryLabel ? (
                              <span className={`attendance-status-pill ${cellPresentation.primaryTone}`}>
                                {cellPresentation.primaryLabel}
                              </span>
                            ) : (
                              <span className="attendance-cell-note">--</span>
                            )}

                            {cellPresentation.secondaryLabel ? (
                              <span className="attendance-cell-note">{cellPresentation.secondaryLabel}</span>
                            ) : null}

                            {cellPresentation.primaryLabel ? (
                              <div className="attendance-punch-inline">
                                {(record?.sessions?.length ? record.sessions : [record]).map((session, index) => (
                                  <div className="attendance-session-line" key={session?.id || `${column.key}-${index}`}>
                                    <span>Check In: {session?.check_in_at ? formatTime(session.check_in_at) : "--"}</span>
                                    <span>Check Out: {session?.check_out_at ? formatTime(session.check_out_at) : "--"}</span>
                                    <strong>Worked: {session?.work_seconds != null || session?.work_minutes != null ? formatWorkedClock(session.work_minutes, session.work_seconds) : "--"}</strong>
                                  </div>
                                ))}
                              </div>
                            ) : null}

                            {canCorrect && record?.id ? (
                              <button
                                className="attendance-cell-action"
                                onClick={() => handleCorrectionSelect(record)}
                                type="button"
                              >
                                Correct
                              </button>
                            ) : null}
                          </div>
                        </div>
                      </td>
                    );
                  })}
                </tr>
              ))}
            </tbody>
          </table>

          {!attendanceRows.length ? (
            <div className="employee-empty-state">
              <Clock3 size={18} />
              <span>No attendance records found for the selected filters.</span>
            </div>
          ) : null}
        </div>
      </section>

      {isReportModalOpen ? (
        <div className="employee-form-overlay" role="presentation">
          <form className="employee-form-modal attendance-report-modal" onSubmit={handleReportSubmit}>
            <div className="employee-form-header">
              <div>
                <p className="sidebar-section-label">Apply Filter</p>
                <h3 className="module-panel-title">Select attendance report range</h3>
              </div>
              <button
                className="ghost-button"
                onClick={() => setIsReportModalOpen(false)}
                type="button"
              >
                Close
              </button>
            </div>

            <label className="sf-field">
              <span className="sf-label">Filter Range</span>
              <select
                className="sf-input"
                onChange={(event) => setReportFilterMode(event.target.value)}
                value={reportFilterMode}
              >
                <option value="today">Today</option>
                <option value="current_week">Current Week</option>
                <option value="last_week">Last Week</option>
                <option value="current_month">Current Month</option>
                <option value="custom_date">Custom Date</option>
              </select>
            </label>

            {reportFilterMode === "custom_date" ? (
              <div className="attendance-report-modal-grid">
                <label className="sf-field">
                  <span className="sf-label">Start Date</span>
                  <input
                    className="sf-input"
                    onChange={(event) => setReportStartDate(event.target.value)}
                    required
                    type="date"
                    value={reportStartDate}
                  />
                </label>

                <label className="sf-field">
                  <span className="sf-label">End Date</span>
                  <input
                    className="sf-input"
                    min={reportStartDate}
                    onChange={(event) => setReportEndDate(event.target.value)}
                    required
                    type="date"
                    value={reportEndDate}
                  />
                </label>
              </div>
            ) : null}

            <div className="employee-form-actions">
              <button
                className="ghost-button"
                onClick={() => setIsReportModalOpen(false)}
                type="button"
              >
                Cancel
              </button>
              <button className="primary-button" disabled={isGeneratingReport} type="submit">
                <CalendarCheck size={14} />
                {isGeneratingReport ? "Generating..." : "Submit"}
              </button>
            </div>
          </form>
        </div>
      ) : null}

      {canCorrect && correctionTarget ? (
        <section className="employee-panel attendance-correction-panel" ref={correctionPanelRef}>
          <div className="module-toolbar">
            <div>
              <p className="sidebar-section-label">Corrections</p>
              <h3 className="module-panel-title">Attendance correction panel</h3>
            </div>
          </div>

          {!correctionTarget ? (
            <div className="employee-empty-state">
              <Edit3 size={18} />
              <span>Select a record from the attendance table to submit a correction.</span>
            </div>
          ) : (
            <form className="employee-form-grid" onSubmit={handleCorrectionSubmit}>
              <label className="sf-field">
                <span className="sf-label">Employee</span>
                <input className="sf-input" disabled value={correctionTarget.employee_name} />
              </label>

              <label className="sf-field">
                <span className="sf-label">Attendance Date</span>
                <input className="sf-input" disabled value={formatDate(correctionTarget.attendance_date)} />
              </label>

              <label className="sf-field">
                <span className="sf-label">Corrected Check-In</span>
                <input
                  aria-invalid={correctionErrors.check_in_at ? "true" : "false"}
                  className={`sf-input ${correctionErrors.check_in_at ? "is-invalid" : ""}`}
                  onChange={(event) => handleCorrectionFieldChange("check_in_at", event.target.value)}
                  required
                  type="datetime-local"
                  value={correctionForm.check_in_at}
                />
                {correctionErrors.check_in_at ? (
                  <span className="sf-hint attendance-correction-error">{correctionErrors.check_in_at}</span>
                ) : null}
              </label>

              <label className="sf-field">
                <span className="sf-label">Corrected Check-Out</span>
                <input
                  aria-invalid={correctionErrors.check_out_at ? "true" : "false"}
                  className={`sf-input ${correctionErrors.check_out_at ? "is-invalid" : ""}`}
                  onChange={(event) => handleCorrectionFieldChange("check_out_at", event.target.value)}
                  type="datetime-local"
                  value={correctionForm.check_out_at}
                />
                {correctionErrors.check_out_at ? (
                  <span className="sf-hint attendance-correction-error">{correctionErrors.check_out_at}</span>
                ) : null}
              </label>

              <label className="sf-field employee-form-span-2">
                <span className="sf-label">Reason</span>
                <textarea
                  aria-invalid={correctionErrors.reason ? "true" : "false"}
                  className={`sf-input employee-textarea ${correctionErrors.reason ? "is-invalid" : ""}`}
                  onChange={(event) => handleCorrectionFieldChange("reason", event.target.value)}
                  required
                  rows="3"
                  value={correctionForm.reason}
                />
                {correctionErrors.reason ? (
                  <span className="sf-hint attendance-correction-error">{correctionErrors.reason}</span>
                ) : null}
              </label>

              <div className="employee-form-actions employee-form-span-2">
                <button
                  className="ghost-button"
                  onClick={resetCorrectionPanel}
                  type="button"
                >
                  <RefreshCw size={14} />
                  Clear
                </button>
                <button className="primary-button" disabled={isSubmittingAction} type="submit">
                  <Edit3 size={15} />
                  {isSubmittingAction ? "Saving..." : "Save Correction"}
                </button>
              </div>
            </form>
          )}
        </section>
      ) : null}
    </div>
  );
}

export default AttendancePage;
