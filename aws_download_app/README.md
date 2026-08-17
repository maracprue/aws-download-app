# AWS S3 App

A browser-based app for downloading **and uploading** files to/from AWS S3 — no command line required.

Built with [Streamlit](https://streamlit.io/) and [boto3](https://boto3.amazonaws.com/).

---

## Prerequisites

1. **Python 3.9+** installed
2. **AWS CLI** installed and on your PATH ([install guide](https://docs.aws.amazon.com/cli/latest/userguide/install-cliv2.html))
3. Your AWS SSO profile configured (e.g. `aws configure sso --profile storage-aibs`)

## Setup

```bash
cd aws_download_app
pip install -r requirements.txt
```

## Running the app

```bash
cd aws_download_app
streamlit run app.py
```

The app opens automatically in your browser at `http://localhost:8501`.

## Usage

1. **AWS Login** (sidebar)
   - Enter your AWS profile name (e.g. `storage-aibs`), or leave blank for the default profile.
   - Click **Check credentials** to verify your session is active.
   - If not logged in, click **Login to AWS (SSO)** — a browser window will open for authentication.

2. **📥 Download tab**
   - The default bucket is `Storage-AIBS`. Change it in the Settings section if needed.
   - Use the folder browser to navigate into sub-folders. Click folder names to go deeper; use **⬆ Go up** or the breadcrumb buttons to go back.
   - Enter a local destination path and click **📥 Download this folder**.

3. **📤 Upload tab**
   - Enter the path to a **local file or folder** to upload.
   - Enter the **target bucket** and an optional **destination prefix** (sub-folder within the bucket).
   - Click **🔍 Check for conflicts** to scan which files already exist in S3.
   - If conflicts are found, choose to **Skip** or **Overwrite** them.
   - Click **✅ Confirm & Start Upload** to begin. The upload runs in a **background thread** — accidental clicks or page reruns will not interrupt it.
   - Progress is streamed live and written to a `.log` file in the app directory.

## Configuration

Override defaults via environment variables or the `.env` file:

| Variable     | Default        | Description                   |
|--------------|----------------|-------------------------------|
| `S3_BUCKET`  | `Storage-AIBS` | Default S3 bucket to browse   |
| `S3_PREFIX`  | *(empty)*      | Starting prefix (folder)      |
| `AWS_PROFILE`| *(empty)*      | Default AWS profile name      |
