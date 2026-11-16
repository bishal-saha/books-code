"""Seeded generator for the Kestrel Outfitters dataset.

The same seed and scale always give the same rows, on every machine, so a book can
say "ticket T-000042" and every reader sees the same ticket. Nothing reads the
clock: all timestamps are offsets from a fixed start date.
"""

from __future__ import annotations

import random
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from kestrel.data.model import (
    ClaimStatus,
    Customer,
    CustomerType,
    Employee,
    ExpenseClaim,
    Order,
    OrderLine,
    OrderStatus,
    Product,
    Ticket,
    TicketMessage,
    TicketPriority,
    TicketStatus,
)

START = datetime(2025, 1, 1, tzinfo=UTC)
DAYS = 365  # one year of trading: 2025

# Full-size counts (scale=1.0), matching UNIVERSE.md.
FULL_SIZE = {
    "customers": 5_000,
    "employees": 400,
    "products": 400,
    "orders": 20_000,
    "tickets": 3_000,
    "claims": 2_500,
}

FIRST = [
    "Ava",
    "Ben",
    "Chloe",
    "Dev",
    "Elena",
    "Femi",
    "Grace",
    "Hiro",
    "Isla",
    "Jonas",
    "Kavya",
    "Liam",
    "Mei",
    "Noah",
    "Olu",
    "Priya",
    "Quinn",
    "Rosa",
    "Sven",
    "Tara",
    "Umar",
    "Vera",
    "Wen",
    "Yusuf",
    "Zara",
]
LAST = [
    "Abara",
    "Becker",
    "Costa",
    "Dubois",
    "Evans",
    "Fischer",
    "Gupta",
    "Hansen",
    "Ito",
    "Jensen",
    "Khan",
    "Lopez",
    "Moreau",
    "Nakamura",
    "Okafor",
    "Patel",
    "Rossi",
    "Silva",
    "Tanaka",
    "Usman",
    "Varga",
    "Walsh",
    "Young",
    "Zhou",
]
TRADE = [
    "Lakeside Lodge",
    "Pinecrest Campsite",
    "Northfield School",
    "Harbour Hotel Group",
    "Greenway Facilities",
    "Summit Outdoor Centre",
    "Meadowbank Holiday Park",
    "Riverside Academy",
    "Oakridge Retreats",
    "Coastline Leisure",
]
COUNTRIES = [("US", "USD", 0.6), ("GB", "GBP", 0.2), ("DE", "EUR", 0.1), ("FR", "EUR", 0.1)]
DEPARTMENTS = [
    ("Support", "CC-100", 90),
    ("Sales", "CC-200", 40),
    ("Finance", "CC-300", 25),
    ("Operations", "CC-400", 170),
    ("People", "CC-500", 15),
    ("Engineering", "CC-600", 30),
    ("Marketing", "CC-700", 30),
]
# Invented product names only: "Kestrel" is never a product name.
CATEGORIES = {
    "Camping": [
        "Ridgeline 40L pack",
        "Ember two-person tent",
        "Driftwood sleeping bag",
        "Cinder camp stove",
        "Brook water filter",
    ],
    "Garden": [
        "Fernhill pruning shears",
        "Hollow oak planter",
        "Meadow hose reel",
        "Thornby leaf rake",
        "Larkspur seed tray",
    ],
    "Outdoor furniture": [
        "Fernhill folding chair",
        "Bayleaf bistro set",
        "Saltmarsh lounger",
        "Copse picnic bench",
        "Willowmere parasol",
    ],
    "Home storage": [
        "Ashby storage crate",
        "Millbrook shelf unit",
        "Cobble underbed box",
        "Hearth log basket",
        "Quarry toolbox",
    ],
    "Small appliances": [
        "Glow lantern",
        "Breeze desk fan",
        "Kettlebrook travel kettle",
        "Spark power bank",
        "Frost cool box",
    ],
}
TICKET_SUBJECTS = [
    "Where is my order?",
    "Item arrived damaged",
    "Wrong item received",
    "Return request",
    "Refund not received",
    "Change delivery address",
    "Product question",
    "Invoice copy needed",
    "Trade account pricing",
    "Missing parts",
]
CHANNELS = ["email", "chat", "phone", "web form"]
CLAIM_CATEGORIES = [
    ("Travel", 2_000, 60_000),
    ("Meals", 800, 9_000),
    ("Software", 1_000, 30_000),
    ("Equipment", 2_000, 120_000),
    ("Training", 5_000, 150_000),
]


@dataclass(frozen=True)
class Dataset:
    customers: tuple[Customer, ...]
    employees: tuple[Employee, ...]
    products: tuple[Product, ...]
    orders: tuple[Order, ...]
    tickets: tuple[Ticket, ...]
    claims: tuple[ExpenseClaim, ...]


def _count(name: str, scale: float) -> int:
    return max(1, round(FULL_SIZE[name] * scale))


def _when(rng: random.Random, start: datetime = START, days: int = DAYS) -> datetime:
    return start + timedelta(seconds=rng.randrange(days * 24 * 3600))


def _person(rng: random.Random) -> str:
    return f"{rng.choice(FIRST)} {rng.choice(LAST)}"


def _customers(rng: random.Random, n: int) -> list[Customer]:
    out = []
    for i in range(1, n + 1):
        trade = rng.random() < 0.06
        country, currency, _ = rng.choices(COUNTRIES, weights=[c[2] for c in COUNTRIES])[0]
        name = f"{rng.choice(TRADE)} {i}" if trade else _person(rng)
        handle = name.lower().replace(" ", ".")
        out.append(
            Customer(
                id=f"C-{i:06d}",
                type=CustomerType.TRADE if trade else CustomerType.CONSUMER,
                name=name,
                email=f"{handle}@example.com",
                country=country,
                currency=currency,
                created_at=_when(rng, START - timedelta(days=3 * 365), 3 * 365),
            )
        )
    return out


def _employees(rng: random.Random, n: int) -> list[Employee]:
    weights = [d[2] for d in DEPARTMENTS]
    leads: dict[str, str] = {}
    out = []
    for i in range(1, n + 1):
        dept, cost_centre, _ = rng.choices(DEPARTMENTS, weights=weights)[0]
        emp_id = f"E-{i:04d}"
        manager = leads.get(dept)
        if manager is None:
            leads[dept] = emp_id
        out.append(Employee(emp_id, _person(rng), dept, manager, cost_centre))
    return out


def _products(rng: random.Random, n: int) -> list[Product]:
    names = [(cat, name) for cat, items in CATEGORIES.items() for name in items]
    out = []
    for i in range(1, n + 1):
        cat, base = names[(i - 1) % len(names)]
        variant = (i - 1) // len(names)
        name = base if variant == 0 else f"{base} (edition {variant + 1})"
        price = rng.randrange(900, 45_000, 100) - 1  # prices end in .99
        out.append(
            Product(
                sku=f"SKU-{i:05d}",
                name=name,
                category=cat,
                price_cents=price,
                cost_cents=round(price * rng.uniform(0.35, 0.6)),
                weight_kg=round(rng.uniform(0.2, 25.0), 1),
                active=rng.random() > 0.05,
            )
        )
    return out


def _orders(
    rng: random.Random, n: int, customers: list[Customer], products: list[Product]
) -> list[Order]:
    statuses = [
        OrderStatus.DELIVERED,
        OrderStatus.SHIPPED,
        OrderStatus.PLACED,
        OrderStatus.CANCELLED,
        OrderStatus.RETURNED,
    ]
    out = []
    for i in range(1, n + 1):
        customer = rng.choice(customers)
        trade = customer.type is CustomerType.TRADE
        lines = []
        for product in rng.sample(products, k=rng.randint(1, 4)):
            qty = rng.randint(5, 60) if trade else rng.randint(1, 3)
            lines.append(OrderLine(product.sku, qty, product.price_cents))
        out.append(
            Order(
                id=f"O-{i:07d}",
                customer_id=customer.id,
                placed_at=_when(rng),
                status=rng.choices(statuses, weights=[78, 8, 5, 4, 5])[0],
                currency=customer.currency,
                lines=tuple(lines),
            )
        )
    return out


def _tickets(
    rng: random.Random,
    n: int,
    customers: list[Customer],
    orders: list[Order],
    employees: list[Employee],
) -> list[Ticket]:
    agents = [e for e in employees if e.department == "Support"] or employees
    out = []
    for i in range(1, n + 1):
        order = rng.choice(orders) if rng.random() < 0.8 else None
        customer_id = order.customer_id if order else rng.choice(customers).id
        opened = order.placed_at + timedelta(days=rng.randint(1, 20)) if order else _when(rng)
        subject = rng.choice(TICKET_SUBJECTS)
        ref = f" Order {order.id}." if order else ""
        messages = [TicketMessage("customer", opened, f"{subject}.{ref}")]
        status = rng.choices(list(TicketStatus), weights=[15, 10, 75])[0]
        if status is not TicketStatus.OPEN:
            agent = rng.choice(agents)
            messages.append(
                TicketMessage(
                    agent.id,
                    opened + timedelta(hours=rng.randint(1, 48)),
                    "Thanks for getting in touch. We're looking into it.",
                )
            )
        out.append(
            Ticket(
                id=f"T-{i:06d}",
                customer_id=customer_id,
                order_id=order.id if order else None,
                channel=rng.choice(CHANNELS),
                priority=rng.choices(list(TicketPriority), weights=[20, 60, 15, 5])[0],
                status=status,
                subject=subject,
                messages=tuple(messages),
            )
        )
    return out


def _claims(rng: random.Random, n: int, employees: list[Employee]) -> list[ExpenseClaim]:
    out = []
    for i in range(1, n + 1):
        category, low, high = rng.choice(CLAIM_CATEGORIES)
        out.append(
            ExpenseClaim(
                id=f"X-{i:05d}",
                employee_id=rng.choice(employees).id,
                submitted_at=_when(rng),
                category=category,
                amount_cents=rng.randrange(low, high),
                currency="USD",
                has_receipt=rng.random() > 0.12,
                status=rng.choices(list(ClaimStatus), weights=[15, 78, 7])[0],
            )
        )
    return out


def generate(seed: int = 2026, scale: float = 1.0) -> Dataset:
    """Build the dataset. `scale` shrinks every table (0.1 = 10%) for fast tests."""
    if scale <= 0:
        raise ValueError("scale must be positive")
    rng = random.Random(seed)
    customers = _customers(rng, _count("customers", scale))
    employees = _employees(rng, _count("employees", scale))
    products = _products(rng, _count("products", scale))
    orders = _orders(rng, _count("orders", scale), customers, products)
    tickets = _tickets(rng, _count("tickets", scale), customers, orders, employees)
    claims = _claims(rng, _count("claims", scale), employees)
    return Dataset(
        tuple(customers),
        tuple(employees),
        tuple(products),
        tuple(orders),
        tuple(tickets),
        tuple(claims),
    )
