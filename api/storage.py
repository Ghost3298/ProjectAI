import os, boto3
from botocore.exceptions import ClientError

s3_client = boto3.client(
        's3',
        endpoint_url = os.environ.get('MINIO_ENDPOINT'),
        aws_access_key_id = os.environ.get('MINIO_ROOT_USER'),
        aws_secret_access_key = os.environ.get('MINIO_ROOT_PASSWORD')
    )

def ensure_bucket_exists(bucket_name: str):
    try:
        s3_client.head_bucket(Bucket= bucket_name)
    except ClientError:
        s3_client.create_bucket(Bucket = bucket_name)