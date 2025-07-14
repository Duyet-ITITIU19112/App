import click
from flask.cli import with_appcontext
from src.models import db, User
from src.services.microsoft_graph import MicrosoftGraphService
from src.services.parser import parse_stream
from hashlib import sha256
from dateutil.parser import parse as parse_datetime

@click.command("backfill-hashes")
@click.argument("user_id", type=int)
@with_appcontext
def backfill_hashes(user_id):
    user = User.query.get(user_id)
    if not user:
        click.echo(f"❌ User with ID {user_id} not found.")
        return

    svc = MicrosoftGraphService(
        access_token=user.access_token,
        refresh_token=user.refresh_token,
        token_expires=user.token_expires,
        user_id=user.id
    )
    svc.ensure_valid_token()

    from src.models.document_model import Document  # import inside to avoid circulars
    docs = Document.query.filter_by(user_id=user_id).all()
    updated = 0

    for doc in docs:
        if doc.content_hash and doc.modified_at:
            continue

        try:
            meta = svc.get_item(doc.file_id)
            raw = svc.fetch_file_content(doc.file_id)
            text = parse_stream(doc.filename, raw)

            doc.content_hash = sha256(text.encode("utf-8")).hexdigest()
            modified_at_str = meta.get("lastModifiedDateTime")
            doc.modified_at = parse_datetime(modified_at_str) if modified_at_str else None
            updated += 1

        except Exception as e:
            click.echo(f"⚠️ Failed to backfill {doc.filename}: {e}")

    db.session.commit()
    click.echo(f"✅ Done: {updated} documents updated for user {user.email}")
