# books-code

Chapter code and capstone projects for the free books on **[iambishal.com/resources/books](https://iambishal.com/resources/books)**.

Each book has one folder, named after its URL slug:

```
<book-slug>/
├── README.md              # the book, with a link to every chapter
├── pyproject.toml
├── ch01-<chapter-slug>/   # the chapter's examples
├── …
├── images/                # the book's figures (SVG source)
└── capstone/
    ├── starter/           # where the capstone begins
    └── chNN-<slug>/       # the project at the end of each capstone chapter
```

## The Agentic AI series

Ten free books, from your first agent to production and the frontier. Every capstone builds an agent for **Kestrel Outfitters**, a fictional home and outdoor goods company whose systems and synthetic data live in [`_shared/kestrel`](_shared/kestrel/UNIVERSE.md).

| # | Book | Folder |
|---|---|---|
| 1 | Agentic AI Foundations | _coming soon_ |
| 2 | Context, Memory and Retrieval | _planned_ |
| 3 | Tools and Protocols: MCP, A2A and Agent Skills | _planned_ |
| 4 | Agent Design Patterns | _planned_ |
| 5 | Multi-Agent Systems | _planned_ |
| 6 | Architecture Patterns for Agentic Systems | _planned_ |
| 7 | Trustworthy Agents | _planned_ |
| 8 | Agents in Production: AgentOps | _planned_ |
| 9 | Business-Ready Agents | _planned_ |
| 10 | Advanced Agentic AI: The Frontier | _planned_ |

## Use one book

```bash
git clone --filter=blob:none --sparse https://github.com/bishal-saha/books-code
cd books-code
git sparse-checkout set <book-slug> _shared
cd <book-slug>
uv sync && uv run pytest
```

Each published book is on the [Releases](https://github.com/bishal-saha/books-code/releases) page as a zip that already includes `_shared/kestrel`.

## Requirements

Python 3.12+ and [uv](https://docs.astral.sh/uv/). API keys only where a `.env.example` asks for them; `.env` is never committed.

## Problems

Open an issue and say which book and chapter it's about.

## Licence

Code: [MIT](LICENSE). The books themselves are free to read on iambishal.com.
