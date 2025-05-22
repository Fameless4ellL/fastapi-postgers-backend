import os
from sqlalchemy import event
from src.models.user import Document


@event.listens_for(Document, "before_delete")
def delete_document_file(mapper, connection, target):
    if target.file and os.path.exists(target.file.path):
        os.remove(target.file.path)
