APP_GUIDE = """
# Kosh — app guide

Kosh is a B2B inventory and procurement app. Each business has one owner, optional
employees, one warehouse, and links to suppliers.

## Roles and permissions
There are exactly three kinds of account. There are NO custom roles, NO "manager" roles
and NO permission settings — what each role can do is fixed.

### Business owner
- The person who registered the business. One owner per business.
- Can do everything employees can, plus (owner only):
  - add, edit and delete products and product categories
  - edit warehouse details
  - edit or delete outlets
  - add, edit and remove suppliers
  - create RFQs from reorder alerts, dismiss or refresh reorder alerts, cancel RFQs
  - accept a supplier's quotation (this creates a purchase order)
  - pay the advance for a purchase order, or cancel an order whose advance is unpaid
  - invite and remove employees
- Receives low-stock and procurement notifications.

### Employee
- Joins a business by accepting an invite sent by the owner (by email).
- Can view products, categories, the warehouse, suppliers, RFQs, reorder alerts,
  purchase orders and goods receipts.
- Can adjust stock, create outlets, create dispatch notes, add or edit customers, and
  record a goods receipt when a supplier's delivery arrives.
- Cannot add/edit/delete products, manage suppliers, create or cancel RFQs, accept
  quotations, pay advances, cancel purchase orders, or manage employees.
- In this assistant, employees are not shown prices, costs, stock value, quotation
  amounts, payment amounts or invoices.

### Supplier
- A separate account type. Suppliers register a supplier profile (company name, GSTIN,
  city, pincode, supply categories). Kosh admins verify suppliers.
- Suppliers see the RFQs sent to them, submit or withdraw a quotation, or decline an RFQ.
- Suppliers see a purchase order only once it is issued (advance paid, or no advance
  needed). They then mark it dispatched, and can see the invoice and goods receipt for it.
- Suppliers cannot see a business's inventory.

## Features
- Products: name, SKU, category, selling price, cost price, quantity, low-stock
  threshold, lead time, safety stock, reorder quantity, image.
- Stock: every change is recorded as a stock movement (opening balance, goods received,
  dispatch, damaged, adjustment).
- Outlets and dispatches: a dispatch note (numbered DN-0001, DN-0002, ...) sends stock from
  the warehouse to an outlet and reduces warehouse stock.
- Reorder alerts: Kosh checks stock automatically and raises a reorder
  suggestion with a suggested quantity when a product runs low.
- RFQs (requests for quotation): sent to the business's own suppliers and optionally to
  verified suppliers on the Kosh platform for a supply category, with a deadline.
  Status: open, closed, awarded or cancelled.
- Quotations: a supplier quotes unit price, GST rate, delivery date, advance amount and
  validity for each RFQ item.
- Purchase orders (PO-0001, PO-0002, ...): created when the owner accepts a quotation.
  Accepting needs an RFQ that is not cancelled or already awarded, and a quotation that
  is still valid and covers every item at the full quantity.
  Order statuses: awaiting advance, issued, dispatched, received, cancelled.
- Advance payment: if the quotation asks for an advance, the order waits in "awaiting
  advance" until the owner pays it online through Razorpay. It must be paid within the
  advance deadline (24 hours by default) or Kosh cancels the order automatically; the
  owner can also cancel it before paying. When an order is cancelled, the RFQ and the
  quotation become available again. A payment that arrives after cancellation is
  refunded automatically. With no advance, the order is issued straight away.
- When an order is issued, the other suppliers' quotations for that RFQ are rejected and
  the supplier is notified.
- Dispatch: the supplier marks the order dispatched once, with an expected delivery date
  and an optional tracking note. They may ship less than ordered. Kosh then creates the
  supplier's invoice automatically. A shipment is late when its expected delivery date
  is after the date agreed in the quotation.
- Goods receipt (GRN-0001, GRN-0002, ...): recorded once per order when the delivery
  arrives, with the received and rejected quantity of each item. Only accepted units
  are added to stock. Kosh records issues automatically: shipped less than ordered,
  received less than shipped, rejected or damaged, received more than shipped.
- Invoices: one per order, created when the supplier dispatches, numbered per supplier.
  Shows the total, the advance applied, a credit for missing or rejected units, the
  balance due, and any refund due when the advance is more than what is payable.
- Customers: name, phone, email, address.
- Notifications: in-app and push notifications for events such as low stock, RFQ
  updates, quotations, purchase orders, payments, dispatches, goods receipts and
  employee invites.
- Account: profile, change password, login with email, Google or GitHub.

## Not available in Kosh (never suggest these)
Paying the invoice balance inside Kosh (only the advance is paid online), sales orders,
billing or invoices for customers, splitting one order into several shipments or goods
receipts, custom roles, role/permission settings, multiple warehouses.

## Screens
(No screen names provided yet. Do not name any screen, menu, tab, page, button or
settings section. Describe the feature instead, e.g. "you can do this from the reorder
alerts feature" — or say you are not sure where it is in the app.)
"""


def get_app_help(business):
  return {"guide": APP_GUIDE.strip()}