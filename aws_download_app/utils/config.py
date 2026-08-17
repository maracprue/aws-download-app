"""App-wide configuration. Edit values here or override with environment variables."""

import os

# Default S3 bucket (override with S3_BUCKET env var)
S3_BUCKET: str = os.environ.get("S3_BUCKET", "barseq-prod-802451596237-us-west-2")

# Default prefix to start browsing from (empty = bucket root)
S3_PREFIX: str = os.environ.get("S3_PREFIX", "")

# AWS profile (optional — leave empty to use default credential chain)
AWS_PROFILE: str = os.environ.get("AWS_PROFILE", "storage-aibs")
