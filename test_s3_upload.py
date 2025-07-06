import boto3
import os
from botocore.exceptions import NoCredentialsError, ClientError
from dotenv import load_dotenv

# Load the .env file
load_dotenv()

# Retrieve AWS credentials from environment
AWS_ACCESS_KEY_ID = os.getenv("AWS_ACCESS_KEY_ID")
AWS_SECRET_ACCESS_KEY = os.getenv("AWS_SECRET_ACCESS_KEY")
S3_BUCKET = "posteritylog-screenshots"  # change this if needed

# Create S3 client
s3 = boto3.client(
    's3',
    aws_access_key_id=AWS_ACCESS_KEY_ID,
    aws_secret_access_key=AWS_SECRET_ACCESS_KEY
)

# Attempt upload
local_file = "test-upload.txt"
s3_key = "test/test-upload.txt"

try:
    s3.upload_file(local_file, S3_BUCKET, s3_key)
    print(f"✅ Upload succeeded. File available at:")
    print(f"https://{S3_BUCKET}.s3.amazonaws.com/{s3_key}")
except FileNotFoundError:
    print("❌ Local file not found.")
except NoCredentialsError:
    print("❌ AWS credentials missing.")
except ClientError as e:
    print(f"❌ Upload failed: {e.response['Error']['Message']}")
