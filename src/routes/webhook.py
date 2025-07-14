# src/routes/webhook.py

import json
from datetime import datetime
from flask import Blueprint, request, current_app
from src.models import db
from src.models.user_model import User
from src.models.document_model import Document  # Changed from File to Document
from src.services.microsoft_graph import MicrosoftGraphService
from src.utils.auth_utils import refresh_token_if_needed

webhook_bp = Blueprint("webhook", __name__)


@webhook_bp.route("/notifications", methods=["GET", "POST"])
def handle_graph_notification():
    """Handle Microsoft Graph webhook notifications for OneDrive changes"""
    
    # Step 1: Handle validation request from Microsoft (GET request)
    if request.method == "GET":
        validation_token = request.args.get("validationToken")
        if validation_token:
            current_app.logger.info("✅ Webhook validation successful")
            return validation_token, 200, {'Content-Type': 'text/plain'}
        current_app.logger.error("❌ Missing validation token")
        return "Missing validation token", 400
    
    # Step 2: Process actual notifications
    try:
        data = request.get_json()
        notifications = data.get("value", [])
        
        current_app.logger.info(f"📨 Received {len(notifications)} notifications")
        
        for notification in notifications:
            process_notification(notification)
        
        return "", 202  # Accepted
    
    except Exception as e:
        current_app.logger.error(f"❌ Webhook error: {str(e)}")
        return "", 500


def process_notification(notification):
    """Process a single notification from Microsoft Graph"""
    
    try:
        # Extract notification details
        client_state = notification.get("clientState")  # This is user_id
        resource = notification.get("resource")
        change_type = notification.get("changeType")
        
        current_app.logger.info(
            f"Processing notification: user={client_state}, "
            f"resource={resource}, change={change_type}"
        )
        
        # Get the user
        user = User.query.get(client_state)
        if not user:
            current_app.logger.error(f"User not found: {client_state}")
            return
        
        # Refresh tokens if needed
        user = refresh_token_if_needed(user)
        
        # Initialize Graph service
        graph_service = MicrosoftGraphService(
            access_token=user.access_token,
            refresh_token=user.refresh_token,
            token_expires=user.token_expires,
            user_id=user.id
        )
        
        # Get the changed item details
        if "/items/" in resource:
            item_id = resource.split("/items/")[1]
            handle_item_change(graph_service, user, item_id, change_type)
        
    except Exception as e:
        current_app.logger.error(f"Error processing notification: {str(e)}")


def handle_item_change(graph_service, user, item_id, change_type):
    """Handle changes to a specific OneDrive item"""
    
    try:
        if change_type in ["created", "updated"]:
            # Fetch the latest item details from Graph API
            item = graph_service.get_item(item_id)
            
            if not item:
                current_app.logger.warning(f"Item not found: {item_id}")
                return
            
            # Check if it's a file (not a folder)
            if "file" in item:
                sync_file(user, item, graph_service)
            elif "folder" in item:
                sync_folder(user, item, graph_service)
        
        elif change_type == "deleted":
            handle_deletion(user, item_id)
    
    except Exception as e:
        current_app.logger.error(f"Error handling item change: {str(e)}")


def sync_file(user, item, graph_service):
    """Sync a file from OneDrive to local database"""
    
    try:
        # Check if document already exists using file_id field
        document = Document.query.filter_by(
            user_id=user.id,
            file_id=item["id"]  # Using file_id field from Document model
        ).first()
        
        # Extract file metadata to match Document model fields
        file_data = {
            "filename": item["name"],  # Changed from 'name' to 'filename'
            "size": item.get("size", 0),
            "modified_at": parse_datetime(item.get("lastModifiedDateTime")),
            "web_url": item.get("webUrl"),
            "source": "onedrive"  # Set source as onedrive
        }
        
        if document:
            # Update existing document
            for key, value in file_data.items():
                setattr(document, key, value)
            document.indexed = False  # Mark for re-indexing
            current_app.logger.info(f"📝 Updated document: {file_data['filename']}")
        else:
            # Create new document record
            document = Document(
                user_id=user.id,
                file_id=item["id"],
                indexed=False,  # New files need to be indexed
                created_at=datetime.utcnow(),
                **file_data
            )
            db.session.add(document)
            current_app.logger.info(f"✨ Created new document: {file_data['filename']}")
        
        db.session.commit()
        
        # Trigger download to PC if needed
        if should_download_to_pc(document):
            queue_file_download(document, graph_service)
    
    except Exception as e:
        current_app.logger.error(f"Error syncing file: {str(e)}")
        db.session.rollback()


def sync_folder(user, item, graph_service):
    """Handle folder changes - placeholder for future implementation"""
    current_app.logger.info(f"📁 Folder sync not implemented yet: {item.get('name', 'Unknown')}")


def handle_deletion(user, item_id):
    """Handle item deletion"""
    
    try:
        # Find and delete the document
        document = Document.query.filter_by(
            user_id=user.id,
            file_id=item_id
        ).first()
        
        if document:
            db.session.delete(document)
            db.session.commit()
            current_app.logger.info(f"🗑️ Deleted document: {document.filename}")
    
    except Exception as e:
        current_app.logger.error(f"Error handling deletion: {str(e)}")
        db.session.rollback()


def should_download_to_pc(document):
    """Determine if a file should be downloaded to PC"""
    
    # Example: Only sync files under 100MB
    max_size = 100 * 1024 * 1024  # 100MB
    return document.size <= max_size


def queue_file_download(document, graph_service):
    """Queue a file for download to PC"""
    
    current_app.logger.info(f"📥 Queued for download: {document.filename}")
    
    # Option 1: Send webhook to PC app
    send_to_pc_app({
        "action": "download_file",
        "document_id": document.id,
        "file_id": document.file_id,
        "filename": document.filename,
        "web_url": document.web_url
    })
    
    # Option 2: Use a task queue
    # download_task.delay(document.id)


def send_to_pc_app(data):
    """Send notification to PC app - placeholder for implementation"""
    # TODO: Implement actual communication with PC app
    current_app.logger.info(f"📤 Would send to PC app: {data}")


@webhook_bp.route("/test", methods=["GET"])
def test_webhook():
    """Test endpoint to verify webhook is accessible"""
    return {
        "status": "webhook_active", 
        "timestamp": datetime.utcnow().isoformat(),
        "message": "Webhook endpoint is ready to receive Microsoft Graph notifications",
        "server": "103.98.161.94:5555"
    }, 200

def parse_datetime(dt_string):
    """Parse ISO datetime string"""
    if not dt_string:
        return None
    try:
        return datetime.fromisoformat(dt_string.replace("Z", "+00:00"))
    except:
        return None