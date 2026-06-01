import { useEffect, useMemo, useState } from "react";
import {
  Briefcase,
  Pencil,
  Plus,
  RefreshCw,
  Search,
  ShieldCheck,
  Trash2,
  UserCheck,
  UserPlus,
  Users,
  X,
  ChevronDown,
} from "lucide-react";
import {
  createEmployee,
  deleteEmployee,
  fetchEmployeeDetail,
  fetchEmployeeMeta,
  fetchEmployees,
  updateEmployee,
  updateEmployeeStatus,
} from "../../api/employeeApi";
import useAuth from "../../hooks/useAuth";

const EMPLOYEE_DIRECTORY_UPDATED_EVENT = "hrm:employees-updated";
const EMPLOYEE_DIRECTORY_UPDATED_AT_KEY = "hrm:employees-updated-at";

function EmployeeSelectField({
  label,
  name,
  value,
  placeholder,
  options,
  openSelectName,
  setOpenSelectName,
  onChange,
}) {
  const selectedOption = options.find((option) => String(option.value) === String(value));
  const isOpen = openSelectName === name;

  function chooseOption(optionValue) {
    onChange(name, optionValue);
    setOpenSelectName("");
  }

  return (
    <div className="sf-field employee-select-field">
      <span className="sf-label">{label}</span>
      <div className={`employee-combobox ${isOpen ? "is-open" : ""}`}>
        <button
          aria-expanded={isOpen}
          aria-haspopup="listbox"
          className="sf-input employee-combobox-trigger"
          onClick={() => setOpenSelectName(isOpen ? "" : name)}
          type="button"
        >
          <span className={!selectedOption ? "employee-combobox-placeholder" : ""}>
            {selectedOption?.label || placeholder}
          </span>
          <ChevronDown size={16} />
        </button>

        {isOpen ? (
          <div className="employee-combobox-menu" role="listbox">
            {options.map((option) => (
              <button
                aria-selected={String(option.value) === String(value)}
                className="employee-combobox-option"
                key={option.value || `${name}-empty`}
                onClick={() => chooseOption(option.value)}
                role="option"
                type="button"
              >
                {option.label}
              </button>
            ))}
          </div>
        ) : null}
      </div>
    </div>
  );
}

function createEmptyForm() {
  return {
    email: "",
    password: "",
    first_name: "",
    last_name: "",
    role_id: "",
    employee_code: "",
    department_id: "",
    designation_id: "",
    manager_id: "",
    joining_date: "",
    date_of_birth: "",
    phone_number: "",
    address: "",
    base_salary: "",
    is_billable: true,
  };
}

function normalizeEmployeeToForm(employee) {
  return {
    email: employee.email || "",
    password: "",
    first_name: employee.first_name || "",
    last_name: employee.last_name || "",
    role_id: employee.role?.id || "",
    employee_code: employee.employee_code || "",
    department_id: employee.department?.id || "",
    designation_id: employee.designation?.id || "",
    manager_id: employee.manager?.id || "",
    joining_date: employee.joining_date || "",
    date_of_birth: employee.date_of_birth || "",
    phone_number: employee.phone_number || "",
    address: employee.address || "",
    base_salary: employee.base_salary ?? "",
    is_billable: Boolean(employee.is_billable),
  };
}

function notifyEmployeeDirectoryUpdated() {
  window.dispatchEvent(new Event(EMPLOYEE_DIRECTORY_UPDATED_EVENT));

  try {
    window.localStorage.setItem(EMPLOYEE_DIRECTORY_UPDATED_AT_KEY, String(Date.now()));
  } catch {
    // Ignore storage errors and rely on the in-tab event.
  }
}

function getErrorMessage(error, fallback) {
  const detail = error?.response?.data?.detail;

  if (typeof detail === "string") {
    return detail;
  }

  if (Array.isArray(detail)) {
    return detail
      .map((item) => item?.msg || item?.message || String(item))
      .filter(Boolean)
      .join(" ");
  }

  if (detail && typeof detail === "object") {
    return detail.msg || detail.message || fallback;
  }

  if (error?.request && !error?.response) {
    return fallback;
  }

  return error?.message || fallback;
}

function validateEmployeeForm(formState, formMode) {
  if (!formState.first_name.trim()) {
    return "First name is required.";
  }
  if (!formState.last_name.trim()) {
    return "Last name is required.";
  }
  if (!formState.email.trim()) {
    return "Email is required.";
  }
  if (!formState.role_id) {
    return "Select a role before saving the employee.";
  }
  if (!formState.employee_code.trim()) {
    return "Employee code is required.";
  }
  if (formMode === "create" && !formState.password.trim()) {
    return "Password is required.";
  }
  if ((formMode === "create" || formState.password.trim()) && formState.password.trim().length < 8) {
    return "Password must be at least 8 characters.";
  }

  return "";
}

function EmployeesPage() {
  const { hasPermission } = useAuth();
  const [employees, setEmployees] = useState([]);
  const [totalEmployees, setTotalEmployees] = useState(0);
  const [meta, setMeta] = useState({
    roles: [],
    departments: [],
    designations: [],
    managers: [],
  });
  const [search, setSearch] = useState("");
  const [statusFilter, setStatusFilter] = useState("all");
  const [isInitialLoading, setIsInitialLoading] = useState(true);
  const [isListLoading, setIsListLoading] = useState(false);
  const [isFormLoading, setIsFormLoading] = useState(false);
  const [isSaving, setIsSaving] = useState(false);
  const [showEmployeeForm, setShowEmployeeForm] = useState(false);
  const [selectedEmployeeId, setSelectedEmployeeId] = useState(null);
  const [formMode, setFormMode] = useState("create");
  const [formState, setFormState] = useState(createEmptyForm());
  const [feedback, setFeedback] = useState({ type: "", message: "" });
  const [openSelectName, setOpenSelectName] = useState("");

  const canCreate = hasPermission("employees.create");
  const canEdit = hasPermission("employees.edit");
  const canDeactivate = hasPermission("employees.deactivate") && hasPermission("users.deactivate");
  const canActivate = hasPermission("employees.deactivate") && hasPermission("users.activate");
  const canDelete = canDeactivate;

  const managerOptions = useMemo(
    () => meta.managers.filter((manager) => manager.id !== selectedEmployeeId),
    [meta.managers, selectedEmployeeId],
  );

  const roleSelectOptions = useMemo(
    () => [
      { value: "", label: "Select role" },
      ...meta.roles.map((role) => ({ value: role.id, label: role.name })),
    ],
    [meta.roles],
  );

  const departmentSelectOptions = useMemo(
    () => [
      { value: "", label: "Select department" },
      ...meta.departments.map((department) => ({ value: department.id, label: department.name })),
    ],
    [meta.departments],
  );

  const designationSelectOptions = useMemo(
    () => [
      { value: "", label: "Select designation" },
      ...meta.designations.map((designation) => ({ value: designation.id, label: designation.name })),
    ],
    [meta.designations],
  );

  const managerSelectOptions = useMemo(
    () => [
      { value: "", label: "No manager" },
      ...managerOptions.map((manager) => ({
        value: manager.id,
        label: `${manager.full_name} (${manager.employee_code})`,
      })),
    ],
    [managerOptions],
  );

  useEffect(() => {
    async function loadInitialData() {
      setIsInitialLoading(true);
      const [metaResult, employeeResult] = await Promise.allSettled([
        fetchEmployeeMeta(),
        fetchEmployees(),
      ]);

      if (metaResult.status === "fulfilled") {
        setMeta(metaResult.value);
      }

      if (employeeResult.status === "fulfilled") {
        setEmployees(employeeResult.value.items);
        setTotalEmployees(employeeResult.value.total);
        setFeedback((current) => (current.type === "error" ? { type: "", message: "" } : current));
      } else {
        setFeedback({
          type: "error",
          message: getErrorMessage(employeeResult.reason, "Unable to load employee management data."),
        });
      }

      setIsInitialLoading(false);
    }

    loadInitialData();
  }, []);

  useEffect(() => {
    if (!canCreate && canEdit && formMode === "create") {
      setFormMode("edit");
    }
  }, [canCreate, canEdit, formMode]);

  useEffect(() => {
    if (!showEmployeeForm) {
      return undefined;
    }

    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";

    return () => {
      document.body.style.overflow = previousOverflow;
    };
  }, [showEmployeeForm]);

  useEffect(() => {
    if (showEmployeeForm && meta.roles.length === 0) {
      refreshMeta();
    }
  }, [showEmployeeForm, meta.roles.length]);

  useEffect(() => {
    if (!openSelectName) {
      return undefined;
    }

    function handlePointerDown(event) {
      if (!event.target.closest(".employee-combobox")) {
        setOpenSelectName("");
      }
    }

    function handleKeyDown(event) {
      if (event.key === "Escape") {
        setOpenSelectName("");
      }
    }

    document.addEventListener("pointerdown", handlePointerDown);
    document.addEventListener("keydown", handleKeyDown);

    return () => {
      document.removeEventListener("pointerdown", handlePointerDown);
      document.removeEventListener("keydown", handleKeyDown);
    };
  }, [openSelectName]);

  function buildFilters() {
    return {
      search: search || undefined,
      status: statusFilter === "all" ? undefined : statusFilter,
    };
  }

  async function loadEmployees(params = {}) {
    setIsListLoading(true);
    try {
      const response = await fetchEmployees(params);
      setEmployees(response.items);
      setTotalEmployees(response.total);
      setFeedback((current) => (current.type === "error" ? { type: "", message: "" } : current));
    } catch (error) {
      setFeedback({
        type: "error",
        message: getErrorMessage(error, "Unable to refresh employee list."),
      });
    } finally {
      setIsListLoading(false);
    }
  }

  async function refreshMeta() {
    try {
      const response = await fetchEmployeeMeta();
      setMeta(response);
      setFeedback((current) => (current.type === "error" ? { type: "", message: "" } : current));
    } catch (error) {
      setFeedback((current) => {
        const hasCatalogData = meta.roles.length || meta.departments.length || meta.designations.length || meta.managers.length;
        if (hasCatalogData) {
          return current.type === "error" ? { type: "", message: "" } : current;
        }

        return {
          type: "error",
          message: getErrorMessage(error, "Unable to refresh employee catalogs."),
        };
      });
    }
  }

  async function handleFilterSubmit(event) {
    event.preventDefault();
    setFeedback({ type: "", message: "" });
    await loadEmployees(buildFilters());
  }

  async function handleRefresh() {
    setFeedback({ type: "", message: "" });
    await Promise.all([loadEmployees(buildFilters()), refreshMeta()]);
  }

  function handleFormChange(event) {
    const { name, value, type, checked } = event.target;
    setFormState((current) => ({
      ...current,
      [name]: type === "checkbox" ? checked : value,
    }));
  }

  function handleSelectChange(name, value) {
    setFormState((current) => ({
      ...current,
      [name]: value,
    }));
  }

  function startCreateMode({ clearFeedback = true } = {}) {
    setShowEmployeeForm(true);
    setSelectedEmployeeId(null);
    setFormMode(canCreate ? "create" : "edit");
    setFormState(createEmptyForm());
    if (clearFeedback) {
      setFeedback({ type: "", message: "" });
    }
  }

  function closeFormPanel() {
    setShowEmployeeForm(false);
    setOpenSelectName("");
    setSelectedEmployeeId(null);
    setFormMode(canCreate ? "create" : "edit");
    setFormState(createEmptyForm());
    setIsFormLoading(false);
  }

  async function startEditMode(employeeId) {
    setShowEmployeeForm(true);
    setIsFormLoading(true);
    setFeedback({ type: "", message: "" });
    try {
      const employee = await fetchEmployeeDetail(employeeId);
      setSelectedEmployeeId(employee.id);
      setFormMode("edit");
      setFormState(normalizeEmployeeToForm(employee));
    } catch (error) {
      setFeedback({
        type: "error",
        message: getErrorMessage(error, "Unable to load employee details."),
      });
    } finally {
      setIsFormLoading(false);
    }
  }

  function buildPayload() {
    const payload = {
      email: formState.email.trim(),
      first_name: formState.first_name.trim(),
      last_name: formState.last_name.trim(),
      role_id: formState.role_id || null,
      employee_code: formState.employee_code.trim(),
      department_id: formState.department_id || null,
      designation_id: formState.designation_id || null,
      manager_id: formState.manager_id || null,
      joining_date: formState.joining_date || null,
      date_of_birth: formState.date_of_birth || null,
      phone_number: formState.phone_number.trim() || null,
      address: formState.address.trim() || null,
      base_salary: formState.base_salary === "" ? null : Number(formState.base_salary),
      is_billable: Boolean(formState.is_billable),
    };

    if (formMode === "create" || formState.password.trim()) {
      payload.password = formState.password.trim();
    }

    return payload;
  }

  async function handleSubmit(event) {
    event.preventDefault();
    setFeedback({ type: "", message: "" });

    try {
      if (formMode === "create" && !canCreate) {
        throw new Error("You do not have permission to create employees.");
      }
      if (formMode === "edit" && !selectedEmployeeId) {
        throw new Error("Select an employee from the list before saving edits.");
      }

      const validationError = validateEmployeeForm(formState, formMode);
      if (validationError) {
        throw new Error(validationError);
      }

      setIsSaving(true);
      const payload = buildPayload();
      if (formMode === "edit" && selectedEmployeeId) {
        await updateEmployee(selectedEmployeeId, payload);
        setFeedback({ type: "success", message: "Employee updated successfully." });
      } else {
        const createdEmployee = await createEmployee(payload);
        setShowEmployeeForm(false);
        setFormState(createEmptyForm());
        setSearch("");
        setStatusFilter("all");
        setEmployees((current) => [createdEmployee, ...current.filter((employee) => employee.id !== createdEmployee.id)]);
        setTotalEmployees((current) => current + 1);
      }

      const nextFilters = formMode === "edit" ? buildFilters() : {};
      await loadEmployees(nextFilters);
      await refreshMeta();
      setFeedback({ type: "success", message: formMode === "edit" ? "Employee updated successfully." : "Employee created successfully." });
      notifyEmployeeDirectoryUpdated();
    } catch (error) {
      setFeedback({
        type: "error",
        message: getErrorMessage(error, formMode === "create" ? "Unable to create employee. Please check the details and try again." : "Unable to save employee details."),
      });
    } finally {
      setIsSaving(false);
    }
  }

  async function handleStatusToggle(employee) {
    const targetState = !employee.is_active;
    setFeedback({ type: "", message: "" });

    try {
      await updateEmployeeStatus(employee.id, targetState);
      setFeedback({
        type: "success",
        message: `Employee ${targetState ? "activated" : "deactivated"} successfully.`,
      });
      await Promise.all([loadEmployees(buildFilters()), refreshMeta()]);
      notifyEmployeeDirectoryUpdated();
    } catch (error) {
      setFeedback({
        type: "error",
        message: getErrorMessage(error, "Unable to update employee status."),
      });
    }
  }

  async function handleDeleteEmployee(employee) {
    if (!canDelete) {
      setFeedback({ type: "error", message: "You do not have permission to delete employees." });
      return;
    }

    const confirmed = window.confirm(`Delete ${employee.full_name}? This will remove the employee from the Employee page.`);
    if (!confirmed) {
      return;
    }

    setIsListLoading(true);
    setFeedback({ type: "", message: "" });
    try {
      await deleteEmployee(employee.id);
      setEmployees((current) => current.filter((item) => item.id !== employee.id));
      setTotalEmployees((current) => Math.max(0, current - 1));
      setFeedback({ type: "success", message: "Employee deleted successfully." });
      await refreshMeta();
      notifyEmployeeDirectoryUpdated();
    } catch (error) {
      setFeedback({
        type: "error",
        message: getErrorMessage(error, "Unable to delete employee."),
      });
    } finally {
      setIsListLoading(false);
    }
  }

  if (isInitialLoading) {
    return (
      <div className="page-container">
        <div className="settings-loading">
          <div className="settings-loading-spinner" />
          <span>Loading employee management...</span>
        </div>
      </div>
    );
  }

  return (
    <div className="page-container employee-page">
      <div className="page-section-header">
        <div className="page-section-header-icon">
          <Users size={22} />
        </div>
        <div>
          <h2 className="page-section-header-title">Employee Management</h2>
          <p className="page-section-header-sub">
            Create employee profiles, assign reporting managers, and control activation state through permission-aware workflows.
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
        <div className="employee-stat-card">
          <span>Total Employees</span>
          <strong>{totalEmployees}</strong>
        </div>
        <div className="employee-stat-card">
          <span>Departments</span>
          <strong>{meta.departments.length}</strong>
        </div>
        <div className="employee-stat-card">
          <span>Designations</span>
          <strong>{meta.designations.length}</strong>
        </div>
        <div className="employee-stat-card">
          <span>Assignable Roles</span>
          <strong>{meta.roles.length}</strong>
        </div>
      </div>

      <div className="employee-layout">
        <section className="employee-panel">
          <div className="employee-toolbar">
            <form className="employee-filter-row" onSubmit={handleFilterSubmit}>
              <div className="employee-search-wrap">
                <Search size={15} className="employee-search-icon" />
                <input
                  className="sf-input employee-search-input"
                  onChange={(event) => setSearch(event.target.value)}
                  placeholder="Search by name, email, or employee code"
                  type="text"
                  value={search}
                />
              </div>

              <select className="sf-input employee-select" onChange={(event) => setStatusFilter(event.target.value)} value={statusFilter}>
                <option value="all">All statuses</option>
                <option value="active">Active</option>
                <option value="inactive">Inactive</option>
              </select>

              <button className="ghost-button" type="submit">
                <Search size={15} />
                Search
              </button>

              <button className="ghost-button" onClick={handleRefresh} type="button">
                <RefreshCw size={15} />
                Refresh
              </button>
            </form>

            {canCreate ? (
              <button className="primary-button" onClick={startCreateMode} type="button">
                <Plus size={15} />
                New Employee
              </button>
            ) : null}
          </div>

          <div className="employee-table-wrap">
            <table className="employee-table">
              <thead>
                <tr>
                  <th>Employee</th>
                  <th>Code</th>
                  <th>Role</th>
                  <th>Department</th>
                  <th>Designation</th>
                  <th>Manager</th>
                  <th>Status</th>
                  <th>Actions</th>
                </tr>
              </thead>
              <tbody>
                {employees.map((employee) => {
                  const showDeactivate = employee.is_active && canDeactivate;
                  const showActivate = !employee.is_active && canActivate;

                  return (
                    <tr key={employee.id}>
                      <td>
                        <div className="employee-primary-cell">
                          <strong>{employee.full_name}</strong>
                          <span>{employee.email || "No linked user email"}</span>
                        </div>
                      </td>
                      <td>{employee.employee_code}</td>
                      <td>{employee.role?.name || "--"}</td>
                      <td>{employee.department?.name || "--"}</td>
                      <td>{employee.designation?.name || "--"}</td>
                      <td>{employee.manager?.full_name || "--"}</td>
                      <td>
                        <span className={`employee-status-badge ${employee.is_active ? "is-active" : "is-inactive"}`}>
                          {employee.is_active ? "Active" : "Inactive"}
                        </span>
                      </td>
                      <td>
                        <div className="employee-row-actions">
                          {canEdit ? (
                            <button className="ghost-button employee-row-btn" onClick={() => startEditMode(employee.id)} type="button">
                              <Pencil size={14} />
                              Edit
                            </button>
                          ) : null}

                          {showDeactivate || showActivate ? (
                            <button
                              className="ghost-button employee-row-btn"
                              onClick={() => handleStatusToggle(employee)}
                              type="button"
                            >
                              <UserCheck size={14} />
                              {employee.is_active ? "Deactivate" : "Activate"}
                            </button>
                          ) : null}

                        </div>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>

            {!employees.length && !isListLoading ? (
              <div className="employee-empty-state">
                <UserPlus size={18} />
                <span>No employees matched the current filters.</span>
              </div>
            ) : null}

            {isListLoading ? (
              <div className="employee-empty-state">
                <RefreshCw size={18} className="spin" />
                <span>Refreshing employee list...</span>
              </div>
            ) : null}
          </div>
        </section>

        {(canCreate || canEdit) && showEmployeeForm ? (
          <div className="employee-form-overlay" onClick={closeFormPanel} role="presentation">
            <aside
              className="employee-panel employee-form-panel employee-form-modal"
              onClick={(event) => event.stopPropagation()}
            >
              <div className="employee-form-header">
                <div>
                  <p className="sidebar-section-label">{formMode === "edit" ? "Edit Employee" : "Create Employee"}</p>
                  <h3>{formMode === "edit" ? "Update employee profile" : "Create a new employee profile"}</h3>
                </div>
                <div className="employee-form-header-actions">
                  {formMode === "edit" ? (
                    <button className="ghost-button" onClick={startCreateMode} type="button">
                      <Plus size={14} />
                      New
                    </button>
                  ) : null}
                  <button className="ghost-button" onClick={closeFormPanel} type="button">
                    <X size={14} />
                    Close
                  </button>
                </div>
              </div>

              {isFormLoading ? (
                <div className="employee-empty-state">
                  <RefreshCw size={18} className="spin" />
                  <span>Loading employee details...</span>
                </div>
              ) : (!canCreate && formMode === "edit" && !selectedEmployeeId) ? (
                <div className="employee-empty-state">
                  <Users size={18} />
                  <span>Select an employee from the table to edit their profile.</span>
                </div>
              ) : (
                <form className="employee-form-grid" onSubmit={handleSubmit}>
                  <label className="sf-field">
                    <span className="sf-label">First Name</span>
                    <input className="sf-input" name="first_name" onChange={handleFormChange} required value={formState.first_name} />
                  </label>

                  <label className="sf-field">
                    <span className="sf-label">Last Name</span>
                    <input className="sf-input" name="last_name" onChange={handleFormChange} required value={formState.last_name} />
                  </label>

                  <label className="sf-field employee-form-span-2">
                    <span className="sf-label">Email</span>
                    <input className="sf-input" name="email" onChange={handleFormChange} required type="email" value={formState.email} />
                  </label>

                  <label className="sf-field">
                    <span className="sf-label">{formMode === "edit" ? "New Password (optional)" : "Password"}</span>
                    <input
                      className="sf-input"
                      name="password"
                      onChange={handleFormChange}
                      required={formMode === "create"}
                      type="password"
                      value={formState.password}
                    />
                  </label>

                  <label className="sf-field">
                    <span className="sf-label">Employee Code</span>
                    <input className="sf-input" name="employee_code" onChange={handleFormChange} required value={formState.employee_code} />
                  </label>

                  <EmployeeSelectField
                    label="Role"
                    name="role_id"
                    value={formState.role_id}
                    placeholder="Select role"
                    options={roleSelectOptions}
                    openSelectName={openSelectName}
                    setOpenSelectName={setOpenSelectName}
                    onChange={handleSelectChange}
                  />

                  <EmployeeSelectField
                    label="Department"
                    name="department_id"
                    value={formState.department_id}
                    placeholder="Select department"
                    options={departmentSelectOptions}
                    openSelectName={openSelectName}
                    setOpenSelectName={setOpenSelectName}
                    onChange={handleSelectChange}
                  />

                  <EmployeeSelectField
                    label="Designation"
                    name="designation_id"
                    value={formState.designation_id}
                    placeholder="Select designation"
                    options={designationSelectOptions}
                    openSelectName={openSelectName}
                    setOpenSelectName={setOpenSelectName}
                    onChange={handleSelectChange}
                  />

                  <EmployeeSelectField
                    label="Reporting Manager"
                    name="manager_id"
                    value={formState.manager_id}
                    placeholder="No manager"
                    options={managerSelectOptions}
                    openSelectName={openSelectName}
                    setOpenSelectName={setOpenSelectName}
                    onChange={handleSelectChange}
                  />

                  <label className="sf-field">
                    <span className="sf-label">Joining Date</span>
                    <input className="sf-input" name="joining_date" onChange={handleFormChange} type="date" value={formState.joining_date} />
                  </label>

                  <label className="sf-field">
                    <span className="sf-label">Date of Birth</span>
                    <input className="sf-input" name="date_of_birth" onChange={handleFormChange} type="date" value={formState.date_of_birth} />
                  </label>

                  <label className="sf-field">
                    <span className="sf-label">Phone Number</span>
                    <input className="sf-input" name="phone_number" onChange={handleFormChange} value={formState.phone_number} />
                  </label>

                  <label className="sf-field">
                    <span className="sf-label">Base Salary</span>
                    <input className="sf-input" min="0" name="base_salary" onChange={handleFormChange} step="0.01" type="number" value={formState.base_salary} />
                  </label>

                  <label className="sf-field employee-form-span-2">
                    <span className="sf-label">Address</span>
                    <textarea className="sf-input employee-textarea" name="address" onChange={handleFormChange} rows="3" value={formState.address} />
                  </label>

                  <label className="sf-field sf-field--inline employee-checkbox-row employee-form-span-2">
                    <input checked={formState.is_billable} name="is_billable" onChange={handleFormChange} type="checkbox" />
                    <span className="sf-label">Billable employee</span>
                  </label>

                  <div className="employee-form-actions employee-form-span-2">
                    <button className="ghost-button" onClick={startCreateMode} type="button">
                      <RefreshCw size={14} />
                      {canCreate ? "Reset" : "Clear"}
                    </button>

                    <button className="ghost-button" onClick={closeFormPanel} type="button">
                      <X size={14} />
                      Cancel
                    </button>

                    <button className="primary-button" disabled={isSaving} type="submit">
                      {formMode === "edit" ? <Pencil size={15} /> : <Briefcase size={15} />}
                      {isSaving ? "Saving..." : formMode === "edit" ? "Update Employee" : "Create Employee"}
                    </button>
                  </div>
                </form>
              )}
            </aside>
          </div>
        ) : null}
      </div>
    </div>
  );
}

export default EmployeesPage;
