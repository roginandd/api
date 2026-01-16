import os
import boto3
from dotenv import load_dotenv

load_dotenv() # loads the .env

class AWSConfig:

    """When called, u can just call AWSConfig.s3.method_name(). Ofc, you need to import the class from the module"""

    #extracts the credentials
    AWS_ACCESS_KEY_ID = os.getenv("AWS_ACCESS_KEY_ID")
    AWS_SECRET_ACCESS_KEY = os.getenv("AWS_SECRET_ACCESS_KEY")
    AWS_REGION = os.getenv("AWS_REGION")
    AWS_S3_BUCKET = os.getenv("AWS_S3_BUCKET")

    #creates the instance of s3 bucket
    s3 = boto3.client(
        "s3",
        aws_access_key_id=AWS_ACCESS_KEY_ID,
        aws_secret_access_key=AWS_SECRET_ACCESS_KEY,
        region_name=AWS_REGION
    )

