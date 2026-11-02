import boto3
from botocore.config import Config
from botocore.exceptions import BotoCoreError, ClientError
from flask import current_app


class R2StorageService:
    def __init__(self):
        self.bucket_name = current_app.config.get("R2_BUCKET_NAME")
        endpoint_url = current_app.config.get("R2_ENDPOINT_URL")
        access_key_id = current_app.config.get("R2_ACCESS_KEY_ID")
        secret_access_key = current_app.config.get("R2_SECRET_ACCESS_KEY")
        if not all((self.bucket_name, endpoint_url, access_key_id, secret_access_key)):
            raise RuntimeError("Cloudflare R2 storage is not configured.")
        self.endpoint_url = endpoint_url.rstrip("/")
        self.s3_client = boto3.client(
            service_name="s3",
            endpoint_url=self.endpoint_url,
            aws_access_key_id=access_key_id,
            aws_secret_access_key=secret_access_key,
            region_name="auto",
            config=Config(signature_version="s3v4"),
        )

    def upload_file_stream(self, file_buffer, destination_filename):
        try:
            self.s3_client.upload_fileobj(
                file_buffer,
                self.bucket_name,
                destination_filename,
                ExtraArgs={"ContentType": "image/webp", "CacheControl": "private, max-age=3600"},
            )
        except (BotoCoreError, ClientError) as error:
            current_app.logger.exception("Cloudflare R2 upload failed")
            raise RuntimeError("Cloudflare R2 could not store the profile image.") from error
        return f"{self.endpoint_url}/{self.bucket_name}/{destination_filename}"

    def get_file(self, object_key):
        try:
            return self.s3_client.get_object(Bucket=self.bucket_name, Key=object_key)
        except (BotoCoreError, ClientError) as error:
            current_app.logger.exception("Cloudflare R2 download failed")
            raise RuntimeError("Cloudflare R2 could not retrieve the profile image.") from error

    def delete_file(self, object_key):
        try:
            self.s3_client.delete_object(Bucket=self.bucket_name, Key=object_key)
        except (BotoCoreError, ClientError) as error:
            current_app.logger.exception("Cloudflare R2 delete failed")
            raise RuntimeError("Cloudflare R2 could not delete the profile image.") from error


def r2_storage():
    return R2StorageService()
