# Kosh — Backend

Backend API for **Kosh**, an inventory and business management platform built with Django and Django REST Framework.

The backend provides authentication, business onboarding, JWT-based authorization, Google OAuth, business management APIs, API documentation, PostgreSQL database integration, Redis support, and production deployment using Docker, Gunicorn, and Nginx.

---

## Tech Stack

| Technology            | Purpose                                    |
| --------------------- | ------------------------------------------ |
| Python 3.11           | Backend programming language               |
| Django 5.2.17         | Web framework                              |
| Django REST Framework | REST API development                       |
| Simple JWT            | JWT authentication                         |
| Django Allauth        | Google OAuth integration                   |
| PostgreSQL 16         | Relational database                        |
| Redis 7               | Caching and backend service support        |
| Gunicorn              | Production WSGI server                     |
| Nginx                 | Reverse proxy and static file serving      |
| WhiteNoise            | Static file handling                       |
| Docker                | Containerization                           |
| Docker Compose        | Multi-container development and deployment |
| AWS EC2               | Production server                          |

---

## Project Structure

```text
backend/
│
├── config/
│   ├── __init__.py
│   ├── settings.py
│   ├── urls.py
│   ├── asgi.py
│   └── wsgi.py
│
├── accounts/
│   ├── migrations/
│   ├── admin.py
│   ├── apps.py
│   ├── models.py
│   ├── serializers.py
│   ├── urls.py
│   └── views.py
│
├── manage.py
├── requirements.txt
├── Dockerfile
├── docker-compose.yml
├── .env.example
├── .gitignore
└── README.md
```

---

## Authentication

Kosh uses a hybrid authentication system.

### Supported authentication methods

* Email/password registration
* Email/password login
* JWT access tokens
* JWT refresh tokens
* JWT token blacklisting on logout
* Google OAuth
* Business onboarding after authentication

---

## JWT Authentication Flow

The authentication flow is:

```text
User
 │
 ├── Register
 │      ↓
 │   User Created
 │
 ├── Login
 │      ↓
 │   Access Token + Refresh Token
 │
 └── Send Access Token
        ↓
   Protected API
```

### Access Token

The access token is used to access protected APIs.

```http
Authorization: Bearer <access_token>
```

### Refresh Token

The refresh token is used to obtain a new access token after the access token expires.

```http
POST /api/token/refresh/
```

---

## Logout

Logout is handled using JWT token blacklisting.

When a user logs out:

```text
Refresh Token
      ↓
Blacklist
      ↓
Token becomes invalid
```

The project uses:

```text
rest_framework_simplejwt.token_blacklist
```

---

## Google OAuth

The backend supports authentication through Google OAuth using Django Allauth.

The basic flow is:

```text
Frontend
   │
   │ Google Login
   ↓
Google OAuth
   │
   │ Authorization
   ↓
Backend
   │
   ├── Existing User
   │       ↓
   │    Dashboard
   │
   └── New User
           ↓
      Business Registration
           ↓
        Dashboard
```

Google authentication is used to verify the user's identity. After successful authentication, the backend handles the application's user and business onboarding flow.

---

## Business Onboarding

After authentication, a business owner can register their business.

The onboarding flow is:

```text
Register / Google Login
        ↓
   User Created
        ↓
Business Registration
        ↓
 Business Exists?
     /       \
   No         Yes
   ↓           ↓
Create       Existing
Business     Business
   ↓           ↓
      Dashboard
```

The business is associated with the authenticated user.

---

## API Structure

The backend follows REST API architecture.

Typical endpoint structure:

```text
/api/
│
├── auth/
│   ├── register/
│   ├── login/
│   ├── logout/
│   └── ...
│
├── token/
│   ├── refresh/
│   └── ...
│
├── business/
│   └── register/
│
└── ...
```

Exact endpoint paths may vary depending on the current API routing configuration.

---

## API Documentation

The project uses Swagger/OpenAPI for API documentation and testing.

Swagger provides:

* API endpoint documentation
* Request schemas
* Response schemas
* Authentication testing
* JWT authorization
* Example requests
* Example responses

After starting the backend, open the configured Swagger URL in your browser.

Example:

```text
http://localhost:8000/api/docs/
```

Use the actual configured documentation route if it differs from the example above.

---

## Database

The backend uses PostgreSQL as the primary database.

Database configuration is managed through environment variables.

Example:

```env
POSTGRES_DB=kosh
POSTGRES_USER=postgres
POSTGRES_PASSWORD=your_password
POSTGRES_HOST=db
POSTGRES_PORT=5432
```

Django migrations are used to manage database schema changes.

Run:

```bash
python manage.py makemigrations
python manage.py migrate
```

When using Docker:

```bash
docker compose exec backend python manage.py makemigrations
docker compose exec backend python manage.py migrate
```

---

## Redis

Redis is included in the backend infrastructure.

It can be used for:

* Caching
* Session-related operations
* Background task infrastructure
* Performance optimization

Example Docker service:

```yaml
redis:
  image: redis:7-alpine
```

---

## Docker Setup

The backend is containerized using Docker.

The application uses a Python 3.11 image and runs Django through Gunicorn.

Basic flow:

```text
Docker Image
     ↓
Install Python dependencies
     ↓
Copy backend source code
     ↓
Run Gunicorn
     ↓
Django Application
```

---

## Docker Compose

The backend infrastructure contains multiple services:

```text
┌─────────────────────────┐
│         Nginx           │
│      Reverse Proxy      │
└────────────┬────────────┘
             │
             ↓
┌─────────────────────────┐
│        Backend          │
│   Django + Gunicorn     │
└────────────┬────────────┘
             │
       ┌─────┴─────┐
       ↓           ↓
┌────────────┐ ┌───────────┐
│ PostgreSQL │ │   Redis   │
└────────────┘ └───────────┘
```

---

## Environment Variables

Create a `.env` file in the appropriate project location.

Example:

```env
DEBUG=True

SECRET_KEY=your_secret_key

POSTGRES_DB=kosh
POSTGRES_USER=postgres
POSTGRES_PASSWORD=your_password
POSTGRES_HOST=db
POSTGRES_PORT=5432

GOOGLE_CLIENT_ID=your_google_client_id
GOOGLE_CLIENT_SECRET=your_google_client_secret

ALLOWED_HOSTS=localhost,127.0.0.1
```

Never commit the actual `.env` file to Git.

Use `.env.example` to document required environment variables.

---

## Local Development

### 1. Clone the repository

```bash
git clone <repository-url>
cd backend
```

### 2. Create environment file

```bash
cp .env.example .env
```

Update `.env` with the required values.

### 3. Build Docker containers

```bash
docker compose build
```

### 4. Start the application

```bash
docker compose up -d
```

Check running containers:

```bash
docker compose ps
```

### 5. Apply migrations

```bash
docker compose exec backend python manage.py migrate
```

### 6. Create superuser

```bash
docker compose exec backend python manage.py createsuperuser
```

### 7. Collect static files

```bash
docker compose exec backend python manage.py collectstatic --noinput
```

---

## Testing APIs

The APIs can be tested using:

* Swagger UI
* Postman
* Thunder Client
* cURL
* Frontend application

Example login request:

```http
POST /api/auth/login/
Content-Type: application/json
```

Request:

```json
{
    "email": "user@example.com",
    "password": "your_password"
}
```

Example response:

```json
{
    "success": true,
    "message": "Login successful.",
    "access": "<access_token>",
    "refresh": "<refresh_token>"
}
```

---

## Protected APIs

Protected endpoints use JWT authentication.

Example:

```http
GET /api/business/
Authorization: Bearer <access_token>
```

In Django REST Framework:

```python
permission_classes = [IsAuthenticated]
```

This ensures that only authenticated users can access the endpoint.

---

## Code Quality

Before creating a pull request, make sure to:

* Run migrations
* Test authentication APIs
* Test protected endpoints
* Verify Swagger documentation
* Check Docker containers
* Check environment variables
* Verify static files
* Review logs for errors

---

## Production Deployment

The backend is designed to run in production using:

```text
AWS EC2
   ↓
Nginx
   ↓
Gunicorn
   ↓
Django
   ↓
PostgreSQL
```

### Production Request Flow

```text
Client
  │
  │ HTTPS
  ↓
Nginx
  │
  │ Reverse Proxy
  ↓
Gunicorn
  │
  ↓
Django REST Framework
  │
  ├── PostgreSQL
  │
  └── Redis
```

---

## Nginx

Nginx acts as the reverse proxy in production.

Responsibilities include:

* HTTPS termination
* Forwarding requests to Gunicorn
* Serving static files
* Handling incoming HTTP requests
* Connecting the public domain to the backend

Example:

```text
https://api.example.com
        ↓
      Nginx
        ↓
   127.0.0.1:8001
        ↓
     Gunicorn
        ↓
      Django
```

---

## Gunicorn

Gunicorn is used as the production WSGI server.

Example command:

```bash
gunicorn config.wsgi:application --bind 0.0.0.0:8000
```

Development Django server:

```bash
python manage.py runserver
```

Production:

```text
Nginx → Gunicorn → Django
```

---

## Static Files

Django static files are collected using:

```bash
python manage.py collectstatic
```

WhiteNoise is configured to help Django serve static assets efficiently.

Static files include:

```text
Admin CSS
Admin JavaScript
DRF assets
Application static files
```

---

## Security

The project follows several security practices:

* Environment variables for secrets
* JWT authentication
* Refresh-token blacklisting
* Django password hashing
* CSRF protection
* CORS configuration
* HTTPS in production
* Restricted `ALLOWED_HOSTS`
* Production `DEBUG=False`
* Secrets excluded from Git

Never commit:

```text
.env
Google client secrets
Database passwords
Django SECRET_KEY
Production credentials
Private keys
```

---

## Git Workflow

Recommended branch structure:

```text
main
 │
 ├── feature/auth-api
 ├── feature/business-registration
 ├── feature/google-oauth
 └── fix/static-files
```

Example commit:

```bash
git add .
git commit -m "feat: implement authentication APIs"
git push origin feature/auth-api
```

---

## Debugging

View backend logs:

```bash
docker compose logs backend
```

Follow logs:

```bash
docker compose logs -f backend
```

View all services:

```bash
docker compose logs
```

Enter the backend container:

```bash
docker compose exec backend bash
```

Run Django commands inside the container:

```bash
docker compose exec backend python manage.py <command>
```

Example:

```bash
docker compose exec backend python manage.py showmigrations
```

---

## Common Django Commands

### Create migrations

```bash
python manage.py makemigrations
```

### Apply migrations

```bash
python manage.py migrate
```

### Create superuser

```bash
python manage.py createsuperuser
```

### Collect static files

```bash
python manage.py collectstatic
```

### Check Django configuration

```bash
python manage.py check
```

### Open Django shell

```bash
python manage.py shell
```

---

## Backend Architecture

The backend follows a layered Django REST Framework architecture:

```text
                 Client
                   │
                   ↓
                API URL
                   │
                   ↓
                 View
                   │
          ┌────────┴────────┐
          ↓                 ↓
     Serializer          Model
          │                 │
          ↓                 ↓
     Validation         PostgreSQL
          │
          ↓
       Response
```

### URL

Responsible for routing the request.

### View

Handles API and business logic.

### Serializer

Responsible for:

* Request validation
* Data serialization
* Response formatting

### Model

Defines database structure and relationships.

### Database

PostgreSQL stores persistent application data.

---

## Future Improvements

Planned or extendable backend features include:

* Inventory management
* Product management
* Supplier management
* Employee management
* Invoice generation
* WhatsApp invoice delivery
* Inventory alerts
* Celery background tasks
* Advanced Redis caching
* Role-based permissions
* Automated testing
* CI/CD pipeline
* API versioning
* Monitoring and logging

---

## Development Team

**Project:** Kosh

**Backend:** Django + Django REST Framework

**Database:** PostgreSQL

**Authentication:** JWT + Google OAuth

**Infrastructure:** Docker + AWS EC2 + Nginx + Gunicorn

---

## License

This project is currently developed for internal/project purposes.

Add the appropriate license here if the project is released publicly.
