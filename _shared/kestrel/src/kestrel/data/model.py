"""Kestrel Outfitters data model (see UNIVERSE.md for the full list of entities).

Plain dataclasses so any book can use them without extra dependencies. Money is
stored as integer cents to avoid floating-point rounding.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum


class CustomerType(StrEnum):
    CONSUMER = "consumer"
    TRADE = "trade"


class OrderStatus(StrEnum):
    PLACED = "placed"
    SHIPPED = "shipped"
    DELIVERED = "delivered"
    CANCELLED = "cancelled"
    RETURNED = "returned"


class ShipmentStatus(StrEnum):
    IN_TRANSIT = "in_transit"
    DELIVERED = "delivered"
    LOST = "lost"


class TicketStatus(StrEnum):
    OPEN = "open"
    PENDING = "pending"
    SOLVED = "solved"


class TicketPriority(StrEnum):
    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"
    URGENT = "urgent"


class ClaimStatus(StrEnum):
    SUBMITTED = "submitted"
    APPROVED = "approved"
    REJECTED = "rejected"


@dataclass(frozen=True)
class Customer:
    id: str
    type: CustomerType
    name: str
    email: str
    country: str
    currency: str
    created_at: datetime


@dataclass(frozen=True)
class Employee:
    id: str
    name: str
    department: str
    manager_id: str | None
    cost_centre: str


@dataclass(frozen=True)
class Product:
    sku: str
    name: str
    category: str
    price_cents: int
    cost_cents: int
    weight_kg: float
    active: bool = True


@dataclass(frozen=True)
class OrderLine:
    sku: str
    quantity: int
    unit_price_cents: int


@dataclass(frozen=True)
class Order:
    id: str
    customer_id: str
    placed_at: datetime
    status: OrderStatus
    currency: str
    lines: tuple[OrderLine, ...]

    @property
    def total_cents(self) -> int:
        return sum(line.quantity * line.unit_price_cents for line in self.lines)


@dataclass(frozen=True)
class Shipment:
    id: str
    order_id: str
    warehouse: str
    carrier: str
    shipped_at: datetime
    promised_by: datetime
    delivered_at: datetime | None
    status: ShipmentStatus

    @property
    def late(self) -> bool:
        if self.delivered_at is None:
            return self.status is ShipmentStatus.LOST
        return self.delivered_at > self.promised_by


@dataclass(frozen=True)
class TicketMessage:
    author: str  # "customer" or an employee id
    sent_at: datetime
    body: str


@dataclass(frozen=True)
class Ticket:
    id: str
    customer_id: str
    order_id: str | None
    channel: str
    priority: TicketPriority
    status: TicketStatus
    subject: str
    messages: tuple[TicketMessage, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class ExpenseClaim:
    id: str
    employee_id: str
    submitted_at: datetime
    category: str
    amount_cents: int
    currency: str
    has_receipt: bool
    status: ClaimStatus
