"""Run two versions of a prompt on the same Kestrel tickets and print a Markdown report.

uv run python -m ch04.compare support_reply 1 2
uv run python -m ch04.compare support_reply 1 2 --extra ch04/fixtures/embedded_instruction.json
"""

import argparse
import json
import sys
from pathlib import Path

import httpx
from pydantic import BaseModel

from ch04.model_client import ModelClient, ModelError, build_client
from ch04.prompt_builder import Draft, Prompt, Ticket, TicketData, draft_reply, load_prompt
from ch04.settings import Settings

TICKETS_FILE = Path(__file__).parent / "tickets.json"
POLICIES = ("returns-policy", "shipping-policy")  # current versions only
NEEDS_INFO = "Notes for reviewer: NEEDS INFO:"
WORD_LIMIT = 150


class Cell(BaseModel):
    draft: Draft | None = None
    error: str | None = None


class Row(BaseModel):
    ticket_id: str
    probe: str
    cells: dict[int, Cell]  # prompt version -> result


def needs_info(draft_text: str) -> bool:
    return any(line.strip().startswith(NEEDS_INFO) for line in draft_text.splitlines())


def reply_words(text: str) -> int:
    """Words in the reply body. A draft without the labels (v1) counts as one body."""
    body = text.partition("Reply:")[2] if "Reply:" in text else text
    body = body.partition("Notes for reviewer:")[0]
    kept = [line for line in body.splitlines() if not line.startswith("Subject:")]
    return len(" ".join(kept).split())


def flags(draft: Draft) -> list[str]:
    found = ["NEEDS INFO"] if needs_info(draft.text) else []
    if reply_words(draft.text) > WORD_LIMIT:
        found.append(f"OVER {WORD_LIMIT} WORDS")
    if "EXAMPLE" in draft.text:
        found.append("COPIED EXAMPLE")  # placeholder IDs from the few-shot examples
    if draft.stop_reason == "truncated":
        found.append("TRUNCATED")
    return found


def get_text(http: httpx.Client, path: str) -> str | None:
    """The JSON body as text, or None on 404 (unknown ticket, order not shipped)."""
    response = http.get(path)
    if response.status_code == 404:
        return None
    response.raise_for_status()  # anything else is a setup problem: stop
    return response.text


def fetch_policies(http: httpx.Client) -> str:
    bodies = {name: json.loads(get_text(http, f"/policies/{name}") or "{}") for name in POLICIES}
    return json.dumps({name: body.get("body") for name, body in bodies.items()})


def load_ticket(http: httpx.Client, entry: str, policies: str) -> tuple[Ticket, TicketData] | None:
    """`entry` is a ticket ID from the API, or the path of a local fixture file."""
    if entry.endswith(".json"):
        raw = Path(entry).read_text(encoding="utf-8")
    elif (raw := get_text(http, f"/tickets/{entry}")) is None:
        return None  # tickets.json and the seeded data have drifted apart
    ticket = Ticket.model_validate_json(raw)
    data = TicketData(policies=policies)
    if ticket.order_id:
        data.order = get_text(http, f"/orders/{ticket.order_id}")
        data.shipment = get_text(http, f"/orders/{ticket.order_id}/shipment")
    return ticket, data


def run_cell(
    client: ModelClient, prompt: Prompt, ticket: Ticket, data: TicketData, max_tokens: int
) -> Cell:
    try:
        return Cell(draft=draft_reply(client, prompt, ticket, data, max_tokens))
    except ModelError as exc:  # one failed call becomes an error cell; the run goes on
        return Cell(error=f"{exc.kind}: {exc}")


def compare(
    client: ModelClient,
    http: httpx.Client,
    prompts: tuple[Prompt, Prompt],
    entries: list[tuple[str, str]],
    max_tokens: int,
) -> list[Row]:
    policies = fetch_policies(http)
    rows = []
    for entry, probe in entries:
        loaded = load_ticket(http, entry, policies)
        if loaded is None:
            rows.append(Row(ticket_id=entry, probe=f"{probe} (skipped: not found)", cells={}))
            continue
        ticket, data = loaded
        cells = {p.version: run_cell(client, p, ticket, data, max_tokens) for p in prompts}
        rows.append(Row(ticket_id=ticket.ticket_id, probe=probe, cells=cells))
    return rows


def summary(cell: Cell | None) -> str:
    if cell is None:
        return "skipped"
    if cell.draft is None:
        return f"ERROR {cell.error}"
    d = cell.draft
    return f"{reply_words(d.text)} words · {', '.join(flags(d)) or 'no flags'}"


def report(rows: list[Row], prompts: tuple[Prompt, Prompt], model: str, max_tokens: int) -> str:
    a, b = prompts
    out = [
        f"# {a.name} v{a.version} vs v{b.version}",
        "",
        f"Model: {model} · max output tokens: {max_tokens} · tickets: {len(rows)}",
        "",
        f"| Ticket | Probe | v{a.version} | v{b.version} |",
        "|---|---|---|---|",
    ]
    for r in rows:
        cells = [summary(r.cells.get(p.version)) for p in prompts]
        out.append(f"| {r.ticket_id} | {r.probe} | {cells[0]} | {cells[1]} |")
    for r in rows:
        out += ["", f"## {r.ticket_id} · {r.probe}"]
        for version, cell in r.cells.items():
            if cell.draft is None:
                out += ["", f"**v{version}**: ERROR {cell.error}"]
                continue
            d = cell.draft
            meta = f"stop: {d.stop_reason} · tokens in/out: {d.input_tokens}/{d.output_tokens}"
            out += ["", f"**v{version}** ({meta})", "", "```text", d.text.strip(), "```"]
    return "\n".join(out) + "\n"


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="python -m ch04.compare")
    parser.add_argument("name")
    parser.add_argument("version_a", type=int)
    parser.add_argument("version_b", type=int)
    parser.add_argument("--extra", action="append", default=[], help="a local fixture ticket")
    args = parser.parse_args(argv)

    settings = Settings.from_env()
    prompts = (load_prompt(args.name, args.version_a), load_prompt(args.name, args.version_b))
    listed = json.loads(TICKETS_FILE.read_text(encoding="utf-8"))
    entries = [(t["ticket"], t["probe"]) for t in listed]
    entries += [(path, "local fixture") for path in args.extra]
    client = build_client(settings)
    try:
        with httpx.Client(base_url=settings.kestrel_url, timeout=5.0) as http:
            rows = compare(client, http, prompts, entries, settings.max_output_tokens)
    except httpx.HTTPError as exc:
        print(f"error: Kestrel API at {settings.kestrel_url}: {exc!r}", file=sys.stderr)
        return 1
    print(report(rows, prompts, settings.model, settings.max_output_tokens), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
