PERM_STUDENTS_VIEW = "students:view"
PERM_STUDENTS_EDIT = "students:edit"

PERM_GROUPS_VIEW = "groups:view"
PERM_GROUPS_EDIT = "groups:edit"

PERM_CONTRACTS_VIEW = "contracts:view"
PERM_CONTRACTS_EDIT = "contracts:edit"

PERM_ATTENDANCE_COACH_MARK = "attendance:coach:mark"
PERM_ATTENDANCE_VIEW = "attendance:view"

PERM_SESSIONS_CREATE = "sessions:create"
PERM_SESSIONS_MANAGE = "sessions:manage"

PERM_REPORTS_ATTENDANCE_VIEW = "reports:attendance:view"
PERM_REPORTS_DASHBOARD_VIEW = "reports:dashboard:view"

PERM_SETTINGS_SYSTEM_EDIT = "settings:system:edit"
PERM_SETTINGS_SYSTEM_VIEW = "settings:system:view"

PERM_ROLES_MANAGE = "roles:manage"
PERM_USERS_MANAGE = "users:manage"

PERM_GATE_LOGS_VIEW = "gate:logs:view"

ALL_PERMISSIONS = [
    {"code": PERM_STUDENTS_VIEW, "description": "View students"},
    {"code": PERM_STUDENTS_EDIT, "description": "Edit students"},
    {"code": PERM_GROUPS_VIEW, "description": "View groups"},
    {"code": PERM_GROUPS_EDIT, "description": "Edit groups"},
    {"code": PERM_CONTRACTS_VIEW, "description": "View contracts"},
    {"code": PERM_CONTRACTS_EDIT, "description": "Edit contracts"},
    {"code": PERM_ATTENDANCE_COACH_MARK, "description": "Mark attendance as coach"},
    {"code": PERM_ATTENDANCE_VIEW, "description": "View attendance records"},
    {"code": PERM_SESSIONS_CREATE, "description": "Create training sessions"},
    {"code": PERM_SESSIONS_MANAGE, "description": "Manage all training sessions"},
    {"code": PERM_REPORTS_ATTENDANCE_VIEW, "description": "View attendance reports"},
    {"code": PERM_REPORTS_DASHBOARD_VIEW, "description": "View dashboard"},
    {"code": PERM_SETTINGS_SYSTEM_EDIT, "description": "Edit system settings"},
    {"code": PERM_SETTINGS_SYSTEM_VIEW, "description": "View system settings"},
    {"code": PERM_ROLES_MANAGE, "description": "Manage roles and permissions"},
    {"code": PERM_USERS_MANAGE, "description": "Manage users"},
    {"code": PERM_GATE_LOGS_VIEW, "description": "View gate logs"},
]

DEFAULT_ROLES = {
    "Super Admin": {
        "description": "Full system access",
        "permissions": [],
    },
    "Director": {
        "description": "Director with access to all reports and management",
        "permissions": [
            PERM_STUDENTS_VIEW,
            PERM_GROUPS_VIEW,
            PERM_CONTRACTS_VIEW,
            PERM_ATTENDANCE_VIEW,
            PERM_REPORTS_ATTENDANCE_VIEW,
            PERM_REPORTS_DASHBOARD_VIEW,
            PERM_GATE_LOGS_VIEW,
            PERM_SETTINGS_SYSTEM_VIEW,
        ],
    },
    "Accountant": {
        "description": "Financial management",
        "permissions": [
            PERM_STUDENTS_VIEW,
            PERM_CONTRACTS_VIEW,
            PERM_REPORTS_DASHBOARD_VIEW,
        ],
    },
    "Head Coach": {
        "description": "Head Coach with session creation and management capabilities",
        "permissions": [
            PERM_STUDENTS_VIEW,
            PERM_GROUPS_VIEW,
            PERM_GROUPS_EDIT,
            PERM_ATTENDANCE_COACH_MARK,
            PERM_ATTENDANCE_VIEW,
            PERM_SESSIONS_CREATE,
            PERM_SESSIONS_MANAGE,
            PERM_REPORTS_ATTENDANCE_VIEW,
        ],
    },
    "Coach": {
        "description": "Coach with attendance marking capabilities",
        "permissions": [
            PERM_STUDENTS_VIEW,
            PERM_GROUPS_VIEW,
            PERM_ATTENDANCE_COACH_MARK,
            PERM_ATTENDANCE_VIEW,
        ],
    },
    "Admin": {
        "description": "Administrative staff with student and group management",
        "permissions": [
            PERM_STUDENTS_VIEW,
            PERM_STUDENTS_EDIT,
            PERM_GROUPS_VIEW,
            PERM_GROUPS_EDIT,
            PERM_CONTRACTS_VIEW,
            PERM_CONTRACTS_EDIT,
            PERM_ATTENDANCE_VIEW,
            PERM_GATE_LOGS_VIEW,
            PERM_REPORTS_DASHBOARD_VIEW,
        ],
    },
}
