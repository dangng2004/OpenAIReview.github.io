"""Background review jobs stored in Firestore."""

import os
import tempfile
from pathlib import Path

import resend

resend.api_key = os.environ.get("RESEND_API_KEY", "")

FRONTEND_URL = os.environ.get("FRONTEND_URL", "https://openaireview.github.io")
FROM_EMAIL = os.environ.get("FROM_EMAIL", "onboarding@resend.dev")


def _send_done_email(email: str, token: str) -> None:
    url = f"{FRONTEND_URL}/results/?token={token}"
    try:
        resend.Emails.send({
            "from": FROM_EMAIL,
            "to": email,
            "subject": "Your OpenAIReview review is ready",
            "html": (
                f"<p>Hi,</p>"
                f"<p>Your paper review from OpenAIReview is complete.</p>"
                f"<p><a href='{url}'>Click here to view your results</a></p>"
                f"<p>Or copy this link: {url}</p>"
                f"<p>— OpenAIReview</p>"
            ),
            "text": (
                f"Your paper review from OpenAIReview is complete.\n\n"
                f"View your results: {url}\n\n"
                f"— OpenAIReview"
            ),
        })
    except Exception as exc:
        print(f"[worker] Failed to send email to {email}: {exc}")


def _send_error_email(email: str, token: str, error: str) -> None:
    try:
        resend.Emails.send({
            "from": FROM_EMAIL,
            "to": email,
            "subject": "Your OpenAIReview review encountered an error",
            "html": (
                f"<p>Unfortunately your paper review failed.</p>"
                f"<p>Error: {error}</p>"
                f"<p>Please try submitting again at <a href='{FRONTEND_URL}'>{FRONTEND_URL}</a>.</p>"
            ),
        })
    except Exception as exc:
        print(f"[worker] Failed to send error email to {email}: {exc}")


def run_review(token: str, pdf_bytes: bytes, filename: str, email: str, method: str = "progressive") -> None:
    """Synchronous background task (runs in FastAPI's thread-pool executor)."""
    from store import insert_pending, set_done, set_error
    insert_pending(token, email)

    tmp_path = None
    try:
        suffix = Path(filename).suffix or ".pdf"
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as f:
            f.write(pdf_bytes)
            tmp_path = f.name

        from reviewer.parsers import parse_document
        from reviewer.utils import split_into_paragraphs
        from reviewer.method_progressive import review_progressive
        from reviewer.method_local import review_local
        from reviewer.method_zero_shot import review_zero_shot
        from reviewer.cli import _build_paper_json, slugify, _method_key

        file_path = Path(tmp_path)
        title, content = parse_document(file_path)

        slug = slugify(Path(filename).stem)
        paragraphs = split_into_paragraphs(content)

        model = os.environ.get("MODEL", "anthropic/claude-opus-4-6")

        if method == "progressive":
            result, _full = review_progressive(slug, content, model=model)
        elif method == "local":
            result = review_local(slug, content, model=model)
        else:  # zero_shot
            result = review_zero_shot(slug, content, model=model)

        key = _method_key(method, model)
        paper_data = _build_paper_json(
            slug, title, content, paragraphs, method, key, result
        )

        set_done(token, paper_data)
        _send_done_email(email, token)

    except SystemExit as exc:
        msg = f"Process exited (code {exc.code}). Check OPENROUTER_API_KEY."
        set_error(token, msg)
        _send_error_email(email, token, msg)
    except Exception as exc:
        msg = str(exc)
        set_error(token, msg)
        _send_error_email(email, token, msg)

    finally:
        if tmp_path and Path(tmp_path).exists():
            Path(tmp_path).unlink(missing_ok=True)
