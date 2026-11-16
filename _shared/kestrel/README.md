# kestrel-outfitters

> **Kestrel Outfitters is a fictional company; any resemblance to real businesses or products is coincidental.**

The shared company, systems and synthetic data behind every capstone in the free *Agentic AI* book series on [iambishal.com](https://iambishal.com/resources/books). Read [UNIVERSE.md](UNIVERSE.md) for the company, its people and the storyline across the books.

```bash
uv run kestrel info                      # what's in the package
uv run kestrel up                        # .kestrel/ workspace, then the mock API on http://127.0.0.1:8700
uv run kestrel data --out kestrel.sqlite # only the database
```

```python
from kestrel.data import generate

dataset = generate(seed=2026, scale=0.1)  # 10% of the full size, for quick tests
print(dataset.customers[0])
```

**Status (0.3.0):** the data model and seeded generator for customers, employees, products, orders, shipments (four fictional carriers), tickets and expense claims; synthetic policy documents; `kestrel up` workspace and a read-only mock API (orders, shipments, stock, tickets, policies) on port 8700, standard library only. The mock services (CRM, ticketing, finance, orders, docs) arrive with the capstones that use them. Each book pins the version of this package it was written against.
