# 🏆 BUNYODKOR CIMS

**Comprehensive Integrated Management System for Bunyodkor Football Academy**

A professional FastAPI backend for managing students, attendance, contracts, and turnstile access control.

---

## 🚀 Quick Start

### Prerequisites
- Python 3.11+
- PostgreSQL 14+
- pip

### Installation

1. **Clone the repository**
```bash
git clone <repository-url>
cd Bunyodkor_FastApi
```

2. **Install dependencies**
```bash
pip install -r requirements.txt
```

3. **Configure environment**
```bash
cp .env.example .env
# Edit .env and set POSTGRES_*, SECRET_KEY, and Telegram settings if needed
```

4. **Create database**
```bash
createdb bunyodkor_cims
```

5. **Run migrations**
```bash
alembic upgrade head
```

6. **Seed database**
```bash
python seed.py
```

This creates:
- All permissions
- 5 default roles (Super Admin, Director, Accountant, Coach, Admin)
- Super admin user (phone: `+998901234567`, password: `admin123`)

7. **Start the server**
```bash
uvicorn main:app --reload
# or
python main.py
```

Server runs at: `http://localhost:8000`

---

## 📚 Documentation

- **API Documentation** (Frontend): [API_DOCS.md](./API_DOCS.md)
- **Backend Architecture** (Backend devs): [BACKEND_DEV.md](./BACKEND_DEV.md)
- **Interactive API Docs**: `http://localhost:8000/docs`
- **ReDoc**: `http://localhost:8000/redoc`

---

## 🔑 Default Credentials

After running `python seed.py`:

**Super Admin**:
- Phone: `+998901234567`
- Password: `admin123`

**⚠️ IMPORTANT**: Change this password immediately after first login!

---

## 🏗️ Project Structure

```
Bunyodkor_FastApi/
├── app/
│   ├── core/          # Config, DB, Security, Permissions
│   ├── models/        # SQLAlchemy models
│   ├── schemas/       # Pydantic schemas
│   ├── routers/       # API endpoints
│   ├── services/      # Business logic
│   └── deps.py        # Dependencies (auth, RBAC)
├── alembic/           # Database migrations
├── main.py            # FastAPI app
├── seed.py            # Database seeding
├── requirements.txt
├── .env.example
├── README.md
├── BACKEND_DEV.md     # For backend developers
└── API_DOCS.md        # For frontend developers
```

---

## 🎯 Key Features

### ✅ Implemented
- JWT authentication with RBAC
- User & role management
- Student, parent, group, contract CRUD
- Coach attendance management
- Turnstile integration
- Attendance-focused reports
- System settings management
- Excel import stub

### 🔜 To Implement
- SMS notifications
- Excel import parsing
- File uploads (student photos)
- WebSocket for real-time updates
- Background job processing

---

## 🧪 Testing

Visit `http://localhost:8000/docs` for interactive API testing via Swagger UI.

**Test Flow**:
1. Login with super admin credentials
2. Create a student, group, contract
3. Test gate callback with student ID
4. Mark attendance as coach
5. Check reports

---

## 📦 Dependencies

Core:
- **FastAPI** - Web framework
- **SQLAlchemy 2.0** - Async ORM
- **Alembic** - Migrations
- **asyncpg** - PostgreSQL driver
- **pydantic-settings** - Configuration
- **python-jose** - JWT
- **passlib** - Password hashing
- **python-dateutil** - Date calculations

See [requirements.txt](./requirements.txt) for full list.

---

## 🔒 Security

- Passwords hashed with bcrypt
- JWT tokens for authentication
- Permission-based access control (RBAC)
- Super admin bypass for all permissions
- SQL injection protected by ORM
- Input validation via Pydantic

---

## 🌐 API Overview

### Authentication
- `POST /auth/login` - Login
- `GET /auth/me` - Current user info

### Management (Staff Only)
- `/users` - User CRUD
- `/roles` - Role & permission management
- `/students` - Student CRUD
- `/groups` - Group CRUD
- `/contracts` - Contract CRUD
### Coach
- `/coach/groups` - Assigned groups
- `/coach/sessions` - Training sessions
- `/coach/sessions/{id}/attendance` - Mark attendance

### Turnstile
- `POST /gate/callback` - Entry check (called by hardware)
- `GET /gate/logs` - Entry logs

### Reports
- `/reports/dashboard/summary` - Quick stats
- `/reports/attendance/*` - Attendance analytics

---

## 🚦 Health Check

```bash
curl http://localhost:8000/health
```

Response:
```json
{
  "status": "ok",
  "service": "bunyodkor-cims"
}
```

---

## 📝 Environment Variables

See `.env.example` for all available variables.

**Required**:
- `DATABASE_URL` - PostgreSQL connection string
- `SECRET_KEY` - JWT signing key (generate with `openssl rand -hex 32`)

**Optional**:
- `SMS_*` - SMS provider
- `TELEGRAM_BACKUP_*` - backup bot token/chat id
- `TELEGRAM_ERROR_*` - error alert bot token/chat id
- `TIMEZONE` - Default: Asia/Tashkent
- `CURRENCY` - Default: UZS

---

## 🤝 Contributing

This is a closed-source project for Bunyodkor Football Academy.

For issues or questions, contact the backend team.

---

## 📄 License

Proprietary - Bunyodkor Football Academy

---

## 🙏 Support

For technical support:
- Check [BACKEND_DEV.md](./BACKEND_DEV.md) for architecture details
- Check [API_DOCS.md](./API_DOCS.md) for endpoint documentation
- Use `/docs` for interactive testing

---

**Built with ❤️ by the Bunyodkor Development Team**
