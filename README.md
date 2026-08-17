# AWS S3 Download & Upload App

A browser-based Windows app for downloading **and** uploading files to/from AWS S3 — no command line required.

Built with [Streamlit](https://streamlit.io/) and [boto3](https://boto3.amazonaws.com/).

---

## Repo layout

| Path | Purpose |
|---|---|
| `aws_download_app/` | The Streamlit application (`app.py`, `utils/`, `download/`, `upload/`) |
| `launch_aws_app.bat` | Launches the app (opens a console window, runs Streamlit) |
| `launch_aws_app_silent.vbs` | Launches the app with no visible console window |
| `create_desktop_shortcut.vbs` | One-time setup: creates a desktop shortcut with the app icon |
| `update_app.bat` | Pulls the latest version from GitHub and updates dependencies |

---

## Installing on a new computer

1. **Install prerequisites**
   - [Git for Windows](https://git-scm.com/download/win)
   - Python 3.9+ (this app expects a conda install at `%USERPROFILE%\AppData\Local\miniconda3\python.exe` — see [Configuration](#configuration) to change this)
   - [AWS CLI v2](https://docs.aws.amazon.com/cli/latest/userguide/install-cliv2.html)

2. **Clone the repo** to wherever you want it to live (e.g. `F:\AWS_Download_Upload`):
   ```bash
   git clone https://github.com/maracprue/aws-download-app.git
   ```

3. **Install dependencies:**
   ```bash
   cd aws-download-app\aws_download_app
   pip install -r requirements.txt
   ```

4. **Configure your AWS SSO profile:**
   ```bash
   aws configure sso --profile storage-aibs
   ```

5. **Create a desktop shortcut (optional, one-time):**
   Double-click `create_desktop_shortcut.vbs`. This creates an **AWS S3 App** shortcut on your Desktop with the correct icon.

6. **Launch the app:**
   Double-click the new desktop shortcut, or run `launch_aws_app.bat` directly.
   The app opens automatically in your browser at `http://localhost:8501`.

## Updating the app

Whenever a new version is pushed to GitHub, just double-click **`update_app.bat`**. It will:
- Pull the latest changes with `git pull`
- Reinstall/upgrade Python dependencies from `requirements.txt`

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

Override defaults via environment variables or `aws_download_app/.env` (never commit real credentials — this file is gitignored):

| Variable      | Default        | Description                 |
|---------------|----------------|------------------------------|
| `S3_BUCKET`   | `Storage-AIBS` | Default S3 bucket to browse |
| `S3_PREFIX`   | *(empty)*      | Starting prefix (folder)    |
| `AWS_PROFILE` | *(empty)*      | Default AWS profile name    |

If your Python isn't at the default conda path, edit the `PYTHON` variable at the top of `launch_aws_app.bat` and `update_app.bat` to point to your interpreter.
