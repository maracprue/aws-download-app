"""App-wide configuration. Edit values here or override with environment variables."""

import os

# Default S3 bucket (override with S3_BUCKET env var)
S3_BUCKET: str = os.environ.get("S3_BUCKET", "barseq-prod-802451596237-us-west-2")

# Default prefix to start browsing from (empty = bucket root)
S3_PREFIX: str = os.environ.get("S3_PREFIX", "")

# AWS profile (optional — leave empty to use default credential chain)
AWS_PROFILE: str = os.environ.get("AWS_PROFILE", "storage-aibs")

# Soft warning threshold. Folders with more files than this are still fully
# supported (the chunked/checkpointed upload path is designed to handle
# arbitrarily many files safely), but the UI asks for an explicit
# confirmation first since a scan/upload this large can take a long time and
# is worth a second look before committing to it.
MAX_UPLOAD_FILES_WARN: int = int(os.environ.get("MAX_UPLOAD_FILES_WARN", "50000"))

# Absolute hard cap on the number of files a single upload will collect into
# memory. This exists only to guard against truly runaway scans (e.g.
# accidentally pointing the app at an entire drive) — it is intentionally
# set far above real dataset sizes. Raise it only if you have a genuine
# single folder bigger than this.
MAX_UPLOAD_FILES_HARD: int = int(os.environ.get("MAX_UPLOAD_FILES_HARD", "2000000"))

# Large uploads are processed in chunks of this size. After each chunk we
# log a checkpoint, persist resume state to disk, and force a garbage
# collection pass — this bounds peak resource usage and means a crash or
# interruption only loses progress within the current chunk, not the whole
# job.
UPLOAD_CHUNK_SIZE: int = int(os.environ.get("UPLOAD_CHUNK_SIZE", "500"))
