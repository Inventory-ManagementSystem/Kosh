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
  - invite and remove employees
- Receives low-stock and procurement notifications.

### Employee
- Joins a business by accepting an invite sent by the owner (by email).
- Can view products, categories, the warehouse, suppliers, RFQs and reorder alerts.
- Can adjust stock, create outlets, create dispatch notes, and add or edit customers.
- Cannot add/edit/delete products, manage suppliers, create or cancel RFQs, or manage
  employees.
- In this assistant, employees are not shown prices, costs, stock value or quotation
  amounts.

### Supplier
- A separate account type. Suppliers register a supplier profile (company name, GSTIN,
  city, pincode, supply categories). Kosh admins verify suppliers.
- Suppliers see the RFQs sent to them, submit or withdraw a quotation, or decline an RFQ.
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
- Customers: name, phone, email, address.
- Notifications: in-app and push notifications for events such as low stock, RFQ
  updates, quotations and employee invites.
- Account: profile, change password, login with email, Google or GitHub.

## Not available in Kosh (never suggest these)
Payments, invoices or billing, purchase orders, sales orders, custom roles,
role/permission settings, multiple warehouses.

## Screens
(No screen names provided yet. Do not name any screen, menu, tab, page, button or
settings section. Describe the feature instead, e.g. "you can do this from the reorder
alerts feature" — or say you are not sure where it is in the app.)
"""


def get_app_help(business):
  return {"guide": APP_GUIDE.strip()}