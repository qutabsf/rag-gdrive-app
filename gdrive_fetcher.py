"""Google Drive authentication and file fetching."""

import io
import json
import os
import re
from pathlib import Path

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload

SCOPES = ["https://www.googleapis.com/auth/drive.readonly"]
TOKEN_PATH = Path(__file__).parent / "token.json"

# Supported MIME types and how to handle them
SUPPORTED_MIME_TYPES = {
    "application/vnd.google-apps.document": "text/plain",
    "application/vnd.google-apps.spreadsheet": "text/csv",
    "application/vnd.google-apps.presentation": "text/plain",
    "application/pdf": None,  # download directly
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": None,
    "text/plain": None,
    "text/markdown": None,
}


def parse_drive_url(url: str) -> tuple[str | None, str]:
    """Parse a Google Drive/Docs URL and return (resource_id, resource_type).

    Returns resource_type as 'folder' or 'file'.
    """
    patterns = [
        (r"/drive/folders/([a-zA-Z0-9_-]+)", "folder"),
        (r"/file/d/([a-zA-Z0-9_-]+)", "file"),
        (r"/document/d/([a-zA-Z0-9_-]+)", "file"),
        (r"/spreadsheets/d/([a-zA-Z0-9_-]+)", "file"),
        (r"/presentation/d/([a-zA-Z0-9_-]+)", "file"),
    ]
    for pattern, kind in patterns:
        m = re.search(pattern, url)
        if m:
            return m.group(1), kind
    return None, "unknown"


def load_credentials(credentials_path: str = "credentials.json") -> Credentials | None:
    """Load saved OAuth credentials from token.json if they exist."""
    if TOKEN_PATH.exists():
        creds = Credentials.from_authorized_user_file(str(TOKEN_PATH), SCOPES)
        if creds and creds.valid:
            return creds
        if creds and creds.expired and creds.refresh_token:
            try:
                creds.refresh(Request())
                _save_token(creds)
                return creds
            except Exception:
                pass
    return None


def authenticate(credentials_path: str = "credentials.json") -> Credentials:
    """Run OAuth flow and return valid credentials.

    Opens the browser for the user to authorise the app, then saves the token.
    """
    if not Path(credentials_path).exists():
        raise FileNotFoundError(
            f"Google OAuth credentials file not found at '{credentials_path}'.\n"
            "Download it from Google Cloud Console → APIs & Services → Credentials."
        )
    flow = InstalledAppFlow.from_client_secrets_file(credentials_path, SCOPES)
    creds = flow.run_local_server(port=0, prompt="consent")
    _save_token(creds)
    return creds


def _save_token(creds: Credentials) -> None:
    TOKEN_PATH.write_text(creds.to_json())


def build_service(creds: Credentials):
    """Build and return a Google Drive service client."""
    return build("drive", "v3", credentials=creds)


def list_folder_files(service, folder_id: str) -> list[dict]:
    """Recursively list all supported files in a Drive folder."""
    files = []
    page_token = None
    while True:
        query = f"'{folder_id}' in parents and trashed = false"
        resp = (
            service.files()
            .list(
                q=query,
                fields="nextPageToken, files(id, name, mimeType)",
                pageToken=page_token,
            )
            .execute()
        )
        for item in resp.get("files", []):
            if item["mimeType"] == "application/vnd.google-apps.folder":
                # Recurse into sub-folders
                files.extend(list_folder_files(service, item["id"]))
            elif item["mimeType"] in SUPPORTED_MIME_TYPES:
                files.append(item)
        page_token = resp.get("nextPageToken")
        if not page_token:
            break
    return files


def fetch_file_bytes(service, file_id: str, mime_type: str) -> tuple[bytes, str]:
    """Download or export a file and return (raw_bytes, effective_mime_type).

    Google Workspace files are exported to a plain-text format; binary files are
    downloaded directly.
    """
    export_mime = SUPPORTED_MIME_TYPES.get(mime_type)

    if export_mime is not None:
        # Google Workspace file — export
        response = service.files().export(fileId=file_id, mimeType=export_mime).execute()
        return response if isinstance(response, bytes) else response.encode(), export_mime
    else:
        # Binary file — download
        request = service.files().get_media(fileId=file_id)
        buf = io.BytesIO()
        downloader = MediaIoBaseDownload(buf, request)
        done = False
        while not done:
            _, done = downloader.next_chunk()
        return buf.getvalue(), mime_type


def get_file_metadata(service, file_id: str) -> dict:
    """Return name and mimeType for a single file."""
    return service.files().get(fileId=file_id, fields="id, name, mimeType").execute()
