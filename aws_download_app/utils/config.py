"""App-wide configuration. Edit values here or override with environment variables."""

import os

# Default S3 bucket (override with S3_BUCKET env var)
S3_BUCKET: str = os.environ.get("S3_BUCKET", "barseq-prod-802451596237-us-west-2")

# Default prefix to start browsing from (empty = bucket root)
S3_PREFIX: str = os.environ.get("S3_PREFIX", "")

# AWS profile (optional — leave empty to use default credential chain)
AWS_PROFILE: str = os.environ.get("AWS_PROFILE", "storage-aibs")

# Hard cap on the number of files a single upload will collect into memory.
# collect_local_files() scans the whole source tree up front; without a cap,
# an accidentally-huge folder (millions of files) could load an unbounded
# list into memory before the upload even starts. If a folder exceeds this,
# the user is asked to split it into smaller batches.
MAX_UPLOAD_FILES: int = int(os.environ.get("MAX_UPLOAD_FILES", "50000"))

# Large uploads are processed in chunks of this size. After each chunk we
# log a checkpoint, persist resume state to disk, and force a garbage
# collection pass — this bounds peak resource usage and means a crash or
# interruption only loses progress within the current chunk, not the whole
# job.
UPLOAD_CHUNK_SIZE: int = int(os.environ.get("UPLOAD_CHUNK_SIZE", "500"))
