# Kestrel Outfitters: the company behind every capstone

> **Kestrel Outfitters is a fictional company; any resemblance to real businesses or products is coincidental.**
> It exists so the capstone projects in the free *Agentic AI* book series on [iambishal.com](https://iambishal.com/resources/books) share one realistic business. All data in this package is synthetic.

Each book's capstone builds one more agent for Kestrel. Every capstone also works on its own: its `capstone/starter/` folder ships whatever earlier pieces it needs, and each book pins its own version of this package.

## The company

| | |
|---|---|
| What it sells | Home and outdoor goods: camping and hiking gear, garden tools, outdoor furniture, home storage and small appliances |
| Size | About 400 staff; about 1.2 million orders a year |
| Channels | Its own online store (consumers, about 70% of revenue) and a trade portal for business customers (hotels, campsites, schools, facilities firms; about 30%) |
| Locations | Head office and one main warehouse; a second, smaller warehouse; customers in several countries, so multiple currencies and tax rules |
| Founded | 2011, as a single outdoor shop that moved online |
| Currency in the data | USD (base), EUR and GBP for some customers |

Kestrel is big enough to have every problem an agent book needs (support volume, sales pipelines, expense policy, inventory, internal docs, a small engineering team) and small enough that one reader can understand all of it.

## Departments and their systems

All systems are local mocks; none needs an outside account. `uv run kestrel up` writes `.kestrel/` (database, CSV exports, documents) and starts the read-only mock API on `http://127.0.0.1:8700`: `GET /health`, `/orders/{id}`, `/orders/{id}/shipment`, `/shipments?carrier=&late=&limit=`, `/stock/{sku}`, `/tickets/{id}`, `/tickets?status=`, `/policies`, `/policies/{name}` (unknown IDs: 404). Later books add write endpoints and more systems.

| Department | Lead (recurring character) | System (mock) | What's in it |
|---|---|---|---|
| Customer support | **Maya Okafor**, Support Lead | Ticketing (`kestrel.services.tickets`) + help centre articles | Tickets with priority, channel, status, customer, order, messages; about 60 help articles |
| Sales (trade accounts) | **Daniel Reyes**, Sales Manager | CRM (`kestrel.services.crm`) | Accounts, contacts, deals with stages and values, activities |
| Finance | **Priya Nair**, Finance Controller | Finance (`kestrel.services.finance`) | Invoices, payments, expense claims, cost centres, the expense policy |
| Operations | **Tomasz Wójcik**, Head of Operations | Orders and inventory (`kestrel.services.orders`) | Products (SKUs), stock per warehouse, orders, shipments, returns, suppliers |
| People and internal docs | **Grace Lin**, People Partner | Docs (`kestrel.docs`) | Employee handbook, policies, product manuals, wiki pages, deliberately messy (PDFs, tables, an outdated version or two) |
| Engineering | **Sam Adeyemi**, CTO | A small code repo (`kestrel-shop`) | The store's order-status API, used by the coding agent in Book 10 |

The characters set up each capstone with a request (for example, Priya: "Check every expense claim against policy before it reaches me").

## Data model (synthetic, generated from a fixed seed)

Every reader gets the same rows: `kestrel.data.generate(seed=2026)`.

| Entity | Key fields | Approx. rows |
|---|---|---|
| `Customer` | id, type (consumer / trade), name, email (fake domain), country, currency, created_at | 5,000 |
| `Product` | sku, name, category, price, cost, weight_kg, active | 400 |
| `Order` | id, customer_id, placed_at, status, currency, total, lines[] | 20,000 |
| `Shipment` | id, order_id, warehouse, carrier, shipped_at, delivered_at, status | 18,000 |
| `Return` | id, order_id, reason, status, refund_amount | 1,200 |
| `Ticket` | id, customer_id, order_id?, channel, priority, status, subject, messages[] | 3,000 |
| `Account` (CRM) | id, customer_id, segment, owner | 300 |
| `Deal` | id, account_id, stage, value, expected_close, owner | 600 |
| `Invoice` | id, customer_id, order_id?, issued_at, due_at, amount, status | 6,000 |
| `ExpenseClaim` | id, employee_id, submitted_at, category, amount, currency, receipt?, status | 2,500 |
| `Employee` | id, name, department, manager_id, cost_centre | 400 |
| `Document` | id, title, kind (handbook, policy, manual, wiki), version, updated_at, body | about 150 |

Emails use the reserved `example.com` domain; phone numbers and addresses are obviously fake.

## Naming rules

- **"Kestrel" is the company name only.** No product, plan or system is called "Kestrel …" (real products with that name exist). Products get invented names: *Ridgeline 40L pack*, *Fernhill folding chair*, *Ashby storage crate*.
- Characters are fictional and stay consistent across books (same name, same role).
- Every book's front matter and this README carry the disclaimer above.

## The capstone storyline across the series

Written in the series' order (Book 1, 3, 2, 4, 5, 7, 6, 8, 9, 10).

| Book | Who asks | What the reader builds for Kestrel |
|---|---|---|
| 1. Agentic AI Foundations | Sam (CTO) | A research assistant that answers questions with web search, files and citations |
| 3. Tools and Protocols | Maya and Priya | MCP servers for CRM, tickets and docs; finance and support agents that delegate over A2A; a Skills library |
| 2. Context, Memory and Retrieval | Grace | A knowledge agent over the handbook, policies and tickets, with hybrid search and long-term memory |
| 4. Agent Design Patterns | Priya | An expense-audit agent (plan-and-execute, reflection, human approval) |
| 5. Multi-Agent Systems | Daniel | A deep-research team for trade-account prospecting |
| 7. Trustworthy Agents | Sam | An eval harness, a red-team pass and a governance pack for the agents built so far |
| 6. Architecture Patterns | Sam | The Kestrel agent platform: gateway, durable workflows, sandboxed tools, multi-tenant memory |
| 8. Agents in Production | Tomasz and Sam | Deployment, tracing, dashboards and a failure drill |
| 9. Business-Ready Agents | Maya | The support agent: business case, pilot and results |
| 10. Advanced Agentic AI | Sam | A long-horizon coding agent on `kestrel-shop`, and a fine-tuned small model for one tool-use task |

## Package status

This package grows with the books. Version 0.3.0 provides the data model, the seeded generator, synthetic policy documents and `kestrel up` (database, CSV exports and documents in one folder); the mock services are added when the first capstone that needs them is written.

Carriers in the data (fictional): Northline Freight, Swiftway Parcel, Harbour Express, Tallpine Logistics. Warehouses: Main (Riverside) and North (Eastgate).
