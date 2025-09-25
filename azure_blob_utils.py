import os
from datetime import datetime, timedelta
from azure.storage.blob import BlobServiceClient, generate_blob_sas, BlobSasPermissions

AZURE_CONNECTION_STRING = os.getenv("AZURE_STORAGE_CONNECTION_STRING")
AZURE_BLOB_CONTAINER = os.getenv("AZURE_BLOB_CONTAINER", "lms")

# Init client
blob_service_client = BlobServiceClient.from_connection_string(AZURE_CONNECTION_STRING)
container_client = blob_service_client.get_container_client(AZURE_BLOB_CONTAINER)

# Ensure container exists
try:
    container_client.create_container()
    print(f"[INFO] Container '{AZURE_BLOB_CONTAINER}' created.")
except Exception:
    print(f"[INFO] Using existing container '{AZURE_BLOB_CONTAINER}'.")


def upload_file_to_blob(local_file_path: str, blob_name: str) -> str:
    """
    Upload a file to Azure Blob and return a SAS URL (read-only, expires in 10 years).
    """
    print(f"[UPLOAD] {local_file_path} -> {blob_name}")

    blob_client = container_client.get_blob_client(blob_name)

    # Upload file
    with open(local_file_path, "rb") as data:
        blob_client.upload_blob(data, overwrite=True)

    # Generate SAS token (10 years expiry)
    sas_token = generate_blob_sas(
        account_name=blob_service_client.account_name,
        container_name=AZURE_BLOB_CONTAINER,
        blob_name=blob_name,
        permission=BlobSasPermissions(read=True),
        expiry=datetime.utcnow() + timedelta(days=3650),  # ~10 years
        account_key=blob_service_client.credential.account_key
    )

    # SAS URL
    sas_url = f"https://{blob_service_client.account_name}.blob.core.windows.net/{AZURE_BLOB_CONTAINER}/{blob_name}?{sas_token}"
    print(f"[UPLOAD-SUCCESS] SAS URL (expires in ~10 years): {sas_url}")

    return sas_url

def list_all_scorm_files():
    """Return all .zip SCORM files in container."""
    files = []
    for blob in container_client.list_blobs():
        if blob.name.endswith(".zip"):
            files.append(blob.name)
    return files

def search_scorm_files(query: str):
    """Search SCORM files by substring in blob name."""
    return [name for name in list_all_scorm_files() if query.lower() in name.lower()]


def filter_scorm_files(filter_text: str):
    """Filter SCORM files by substring match in blob name."""
    return [name for name in list_all_scorm_files() if filter_text.lower() in name.lower()]



def list_blobs_in_container():
    """
    List all blobs inside the container.
    """
    print(f"[DEBUG] Listing blobs in container '{AZURE_BLOB_CONTAINER}':")
    blobs = container_client.list_blobs()
    for blob in blobs:
        print(f" - {blob.name}")

def get_blob_sas_url(blob_name: str) -> str:
    """
    Generate a SAS URL for an existing blob (without re-upload).
    """
    from azure.storage.blob import generate_blob_sas, BlobSasPermissions
    from datetime import datetime, timedelta

    sas_token = generate_blob_sas(
        account_name=blob_service_client.account_name,
        container_name=AZURE_BLOB_CONTAINER,
        blob_name=blob_name,
        permission=BlobSasPermissions(read=True),
        expiry=datetime.utcnow() + timedelta(days=3650),  # 10 years
        account_key=blob_service_client.credential.account_key
    )
    return f"https://{blob_service_client.account_name}.blob.core.windows.net/{AZURE_BLOB_CONTAINER}/{blob_name}?{sas_token}"

