"""Grace's onboarding questions. Phrases are copied from the docs `kestrel up` writes."""

from ch09.grade import PolicyQuestion

QUESTIONS = [
    PolicyQuestion(
        id="trade-late-delivery",
        question="A trade customer's standard order arrived late. What was the delivery "
        "promise, and when does a delivery count as late?",
        expected_path="shipping-policy.md",
        expected_facts=["3 working days", "after its promised date"],
        stale_facts=["4 working days"],
    ),
    PolicyQuestion(
        id="training-over-limit",
        question="My training course costs more than the expense limit. What do I need "
        "before I claim it?",
        expected_path="expense-policy.md",
        expected_facts=["pre-approval"],
    ),
    PolicyQuestion(
        id="trade-returns",
        question="How long does a trade customer have to return unused items?",
        expected_path="returns-policy.md",
        expected_facts=["14 days"],
    ),
]
