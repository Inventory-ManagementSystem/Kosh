# Kosh

**Automated invoice generation and inventory monitoring for B2B businesses.**
Kosh watches warehouse stock, raises low-stock alerts, sends RFQs to suppliers, ranks their quotations, and carries each order through advance payment, dispatch, an automatically generated invoice and goods receipt (GRN).

This repository is the **backend** (Django REST Framework). The frontend (React + Vite + Tailwind) is a separate repository.

- Frontend: https://koshh.me
- API: https://kosh.dev-sushant.me
- Swagger UI (local): http://localhost:8000/api/docs/

---

## Features

1. **Role-based access.** Business owners, invited employees and suppliers. Roles are derived from the data (a `Business`, an `Employee` record or a `SupplierProfile`), not stored on the user.
2. **Inventory ledger.** Every stock change is a `StockMovement` (opening balance, GRN received, dispatch, damaged, adjustment). A product's quantity always equals the sum of its movements.
3. **Automatic low-stock alerts.** Celery Beat compares stock with a reorder point (average daily dispatch x supplier lead time + safety stock) and creates a `ReorderSuggestion`.
4. **Automatic RFQs.** Alerts are grouped by supply category and sent to the owner's verified suppliers, optionally plus the verified platform pool in the same city.
5. **Supplier panel.** Suppliers get an RFQ inbox, quote every item at full quantity, and can revise, withdraw or decline.
6. **Ranked quotation comparison.** A weighted score for price, delivery, payment terms and reliability (default 50/25/10/15, adjustable per request) with "recommended", "cheapest" and "fastest" badges.
7. **Purchase orders with advance payment.** Accepting a quotation creates a PO that is issued once the advance is paid (Razorpay sandbox). Only then are the other suppliers told the RFQ is closed.
8. **Dispatch and automatic invoice.** When the supplier marks the order dispatched, an invoice (`INV-0001`, numbered per supplier) is generated from the dispatched quantities, PO prices and GST. Nobody types an invoice.
9. **GRN with automatic discrepancies.** The owner records goods received. Shortages and damage are calculated against the invoice, stock is updated through the ledger, linked alerts are closed and the balance payable is computed. PO, invoice and GRN make up the 3-way match.
10. **Automatic supplier payouts.** The advance is paid out to the supplier through RazorpayX when the order is dispatched, and the balance after the owner settles it post-GRN. See [Payments](#payments-razorpay).
11. **Kosh Assistant.** A chatbot built on Gemini function calling that answers questions about stock, alerts, RFQs, quotations and orders from live data. Employees never get cost or pricing from it. See [Kosh Assistant](#kosh-assistant-chatbot).
12. **Notifications.** In-app and push (Firebase) notifications for each step of the flow.

---

## How it works

```text
Celery Beat (nightly)            Owner                          Supplier
  low-stock check
        |
  ReorderSuggestion (alert)
        |  automatic, or owner approves
       RFQ ----------------------------------------------->  inbox
        |                                                      quotation (all items)
  ranked comparison <-----------------------------------------+
        |
  owner accepts + pays advance (Razorpay)
        |
  Purchase Order (issued) ---------------------------------->  dispatch
        |                                                         |
        |                                          invoice generated automatically
        |                                          advance paid out (RazorpayX)
        |                                                         |
  GRN (owner counts the goods) <----------------------------------+
        |
  discrepancies calculated -> stock added -> balance payable
        |
  owner pays balance (Razorpay) ---------------------------->  balance paid out (RazorpayX)
```

Purchase order status: `awaiting_advance -> issued -> dispatched -> partially_received -> received` (or `cancelled`). A PO whose advance is 0 skips `awaiting_advance`.

---

## Payments (Razorpay)

Money moves in two directions. Both run in sandbox (test) mode.

| Direction | Service | When |
| --- | --- | --- |
| Owner -> Kosh | Razorpay Checkout | Advance when a quotation is accepted, balance after the GRN |
| Kosh -> Supplier | RazorpayX Payouts | Advance when the supplier dispatches, balance once the owner has paid it |

1. **Advance in the quotation.** The supplier states the advance as a percentage or a fixed amount when quoting.
2. **Owner pays the advance.** Accepting a quotation creates a PO in `awaiting_advance`. The owner pays through Razorpay Checkout and Kosh verifies the payment with Razorpay before moving the PO to `issued`. A PO waits `PO_ADVANCE_EXPIRY_HOURS` for its advance.
3. **Advance paid out on dispatch.** When the supplier marks the order dispatched and the invoice is generated, the advance is sent to the supplier through RazorpayX automatically. The owner does not have to confirm anything.
4. **Balance after the GRN.** The balance is the value of the accepted goods minus the advance already paid. The owner pays it through Razorpay and the payout to the supplier follows automatically.
5. **Advance larger than accepted goods.** If the accepted goods are worth less than the advance, the difference is recorded as owed by the supplier and deducted from their next payout.

Test keys are in `.env.example`. Use Razorpay's test cards and UPI IDs at checkout.

---

## Kosh Assistant (chatbot)

An in-app chatbot that answers questions about the business in plain language, for example:

- "Which products are below their reorder level?"
- "Compare the quotations for my latest RFQ."
- "Has the steel order been dispatched yet?"

**How it works**

1. The question goes to the **Google Gemini API** along with a fixed list of Kosh functions (stock levels, alerts, RFQs, quotations, purchase orders, invoices, GRNs).
2. Gemini picks the function and arguments it needs. Kosh runs that function itself, using the logged-in user's business and role.
3. The result goes back to Gemini, which writes the answer.

The model never sees the database directly and never writes SQL. Function calling was chosen over RAG and Text-to-SQL so that every answer comes from a known, permission-checked query.

**Access rules**

- Every function is scoped to the user's own business.
- Owners can ask about everything, including prices, quotation amounts and payments.
- Employees can ask about stock and order status, but the functions available to them return no cost or pricing data.

---

## Tech stack

| Area | Technology |
| --- | --- |
| Language / framework | Python 3.11, Django 5.2, Django REST Framework |
| Auth | SimpleJWT (refresh-token blacklist), django-allauth (Google, GitHub), OTP password reset by email |
| Database | PostgreSQL (container locally, AWS RDS in production) |
| Cache / queue | Redis, Celery worker + Celery Beat |
| Files | AWS S3 (`django-storages`) for media, WhiteNoise for static files |
| Payments | Razorpay Checkout (owner payments), RazorpayX Payouts (supplier payouts), sandbox mode |
| AI assistant | Google Gemini API (function calling) |
| PDFs / push | ReportLab, Firebase Cloud Messaging |
| API docs | drf-spectacular (Swagger / OpenAPI) |
| Serving | Gunicorn, Nginx, Certbot (HTTPS) on AWS EC2 |
| DevOps | Docker, Docker Compose, GitHub Actions (CI/CD) |

---

## Architecture

```text
              Browser (React)
                    |  HTTPS
                    v
        Nginx (EC2, Certbot TLS)
                    |
          Gunicorn: Django + DRF  ------>  Razorpay / RazorpayX
           |        |         |    ------>  Gemini API
      PostgreSQL   Redis    S3 media
        (RDS)    (cache, Celery broker)
                    ^
     Celery worker + Celery Beat (separate containers)
```

### Project structure

```text
backend/
├── config/                  # settings, urls, ASGI/WSGI, Celery app
├── accounts/                # auth, profile, business, employee invites, shared permissions
├── suppliers/               # supplier onboarding, owner's supplier links, supply categories
├── inventory/               # products, categories, warehouse, outlets, stock ledger
│   ├── ledger.py            # record_movement(): the only place stock changes
│   └── reorder.py           # reorder-point calculation
├── procurement/             # alert -> RFQ -> quotation -> PO -> shipment/invoice -> GRN
│   ├── models.py
│   ├── alert_services.py    # low-stock alerts
│   ├── rfq_services.py      # RFQ creation and recipient matching
│   ├── services.py          # quotation submit / withdraw / decline
│   ├── po_services.py       # accept quotation, confirm order
│   ├── ranking.py           # weighted quotation scoring
│   ├── tasks.py             # Celery tasks
│   └── serializers.py, views.py, urls.py, SwaggerDocs.py
├── notifications/           # in-app and push notifications
│   └── events.py            # one function per notification event
├── docker-compose.yml       # local: db, redis, backend, worker, beat
├── docker-compose.prod.yml  # production: backend, redis, worker, beat (database on RDS)
├── Dockerfile
├── requirements.txt
└── .env.example
```

Business rules live in `*_services.py` modules. Views only validate input, call a service and format the response.

---

## Getting started (local)

**Requirements:** Git, Docker Desktop (or Docker Engine with Compose v2).

```bash
# 1. Clone and configure
git clone <repository-url>
cd backend
cp .env.example .env          # Windows PowerShell: copy .env.example .env
```

Open `.env` and fill in the values (see the table below). Never commit `.env`.

```bash
# 2. Build and start db, redis, backend, worker and beat
docker compose up -d --build
docker compose ps

# 3. Create the tables and an admin user
docker compose exec backend python manage.py migrate
docker compose exec backend python manage.py createsuperuser

# 4. Only if the admin pages look unstyled
docker compose exec backend python manage.py collectstatic --noinput
```

Then open:

| What | URL |
| --- | --- |
| API | http://localhost:8000 |
| Swagger UI | http://localhost:8000/api/docs/ |
| Django admin | http://localhost:8000/admin/ |

### Try the procurement flow quickly

1. Register an owner, create a business, and add products with a **supply category** and a low stock level.
2. Register a second user as a supplier and create the supplier profile. In the Django admin, tick **is_verified** on that profile.
3. As the owner, add the supplier by email, then run the nightly jobs by hand instead of waiting for Celery Beat:

```bash
docker compose exec backend python manage.py shell -c "from procurement.tasks import check_low_stock, create_auto_rfqs; print(check_low_stock(), create_auto_rfqs())"
```

4. The supplier now sees the RFQ in the inbox. Post a quotation, then accept it as the owner and continue through payment, dispatch and GRN.

### Environment variables

| Variable | Purpose |
| --- | --- |
| `SECRET_KEY`, `DEBUG`, `ALLOWED_HOSTS` | Core Django settings |
| `POSTGRES_DB`, `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_HOST`, `POSTGRES_PORT` | Database connection |
| `CELERY_BROKER_URL` | Redis URL for Celery (default `redis://redis:6379/0`) |
| `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`, `GITHUB_CLIENT_ID`, `GITHUB_CLIENT_SECRET` | Social login |
| `EMAIL_BACKEND`, `EMAIL_HOST`, `EMAIL_PORT`, `EMAIL_USE_TLS`, `EMAIL_HOST_USER`, `EMAIL_HOST_PASSWORD`, `DEFAULT_FROM_EMAIL` | SMTP for OTP emails |
| `AWS_STORAGE_BUCKET_NAME`, `AWS_S3_REGION_NAME`, `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY` | S3 media storage |
| `FIREBASE_*` | Push notifications |
| `RAZORPAY_KEY_ID`, `RAZORPAY_KEY_SECRET` | Razorpay Checkout (owner payments) |
| `RAZORPAYX_ACCOUNT_NUMBER` | RazorpayX account that supplier payouts are sent from |
| `GEMINI_API_KEY` | Kosh Assistant |
| `FRONTEND_URL` | Used in links sent to users |
| `PO_ADVANCE_EXPIRY_HOURS` | Hours a purchase order waits for its advance (default 24) |

The Razorpay sandbox keys are listed in `.env.example`.

### Useful commands

```bash
docker compose logs -f backend            # follow the API logs
docker compose logs -f worker beat        # Celery logs
docker compose exec backend python manage.py shell
docker compose exec backend python manage.py showmigrations
docker compose exec backend python manage.py makemigrations
```

### Production (EC2 / Linux)

Pushes to the `production` branch run GitHub Actions, which connects to the server over SSH and runs:

```bash
docker compose -f docker-compose.prod.yml up -d --build
docker compose -f docker-compose.prod.yml exec backend python manage.py migrate
```

Nginx terminates HTTPS and forwards to Gunicorn on `127.0.0.1:8001`. PostgreSQL runs on RDS, so there is no database container in production.

---

## API overview

Interactive documentation for every endpoint is in Swagger UI. Protected endpoints need a JWT:

```http
Authorization: Bearer <access_token>
```

The access token lasts 10 minutes. The refresh token is kept in an HttpOnly cookie, and logout blacklists it. Responses share one shape:

```json
{ "success": true, "message": "Quotations fetched.", "data": [] }
{ "success": false, "message": "Validation failed.", "code": "VALIDATION_ERROR", "errors": {} }
```

| Area | Examples (relative to `/procurement/`) | Who |
| --- | --- | --- |
| Alerts | `GET alerts/`, `POST alerts/refresh/`, `POST alerts/create-rfq/` | Owner |
| RFQs | `GET rfqs/`, `GET rfqs/{id}/`, `POST rfqs/{id}/cancel/` | Owner |
| Quotation comparison | `GET rfqs/{id}/quotations/` (ranked) | Owner |
| Accept quotation | `POST quotations/{id}/accept/` (creates the PO) | Owner |
| Supplier inbox | `GET supplier/rfqs/`, `PUT supplier/rfqs/{id}/quotation/` | Supplier |
| Accounts | register, verify OTP, login, logout, token refresh, profile, password reset (under `/accounts/`) | Everyone |

Purchase orders, payments, dispatch and invoices, GRN and assistant endpoints are documented in Swagger.

Example: rank quotations with price weighted highest.

```bash
curl "http://localhost:8000/procurement/rfqs/<rfq_id>/quotations/?weight_price=70&weight_delivery=15&weight_payment=15" \
  -H "Authorization: Bearer <access_token>"
```

Each quotation comes back with `rank`, `score`, a per-parameter `breakdown` and `badges`.

---

## Team

| Name | Role |
| --- | --- |
| `Sushant` | Backend: Django |
| `Shabd Rastogi` | Backend: Django |
| `Manasvi Kapoor` | Frontend: React |
| `Aryan Gupta` | Frontend: React |

---

## Status and future work

- **Done:** authentication and onboarding, inventory ledger, reorder alerts, automatic RFQs, quotations and ranking, purchase orders, Razorpay advance and balance payments, RazorpayX supplier payouts, dispatch and automatic invoices, GRN with discrepancies, Kosh Assistant (Gemini chatbot) over order and quotation data.
- **Planned:** demand forecasting to replace the formula-based reorder point, delivery-based supplier reliability scores.

## License

Developed as a college project.
