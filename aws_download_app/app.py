"""
AWS Download App — Streamlit entry point.

Run with:
    cd aws_download_app
    streamlit run app.py
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

import streamlit as st
from dotenv import load_dotenv

# Load .env from the app directory
load_dotenv(Path(__file__).parent / ".env")

# Make sure sibling modules are importable
sys.path.insert(0, str(Path(__file__).parent))

from download.s3_browser import folder_name, list_prefix, prefix_to_breadcrumbs
from download.s3_download import download_prefix, list_all_objects
from download.download_runner import (
    clear_download_job,
    get_current_download_job,
    start_download_job,
)
from upload.s3_upload import (
    TooManyFilesError,
    check_existing_keys,
    collect_local_files,
    upload_files,
)
from upload.upload_runner import clear_job, get_current_job, start_upload_job
from utils.aws_auth import check_credentials, run_sso_login
from utils.config import AWS_PROFILE, MAX_UPLOAD_FILES_WARN, S3_BUCKET, S3_PREFIX
from utils.upload_checkpoint import checkpoint_id_for


def _run_conflict_check(items, upload_bucket, upload_prefix, aws_profile) -> None:
    """Run the S3 existing-keys check for *items* and stash the result for
    the confirm/summary UI. Shared by the normal and large-scan-confirmed
    paths so both end up in the same place."""
    with st.spinner("Checking S3 for existing files..."):
        prefix_clean = upload_prefix.strip("/")
        target_keys = [
            f"{prefix_clean}/{rel}" if prefix_clean else rel
            for _, rel in items
        ]
        try:
            existing = check_existing_keys(upload_bucket, target_keys, profile=aws_profile)
        except Exception as e:
            st.error(f"Could not check S3 for existing files: {e}")
            existing = set()

        total_bytes = sum(p.stat().st_size for p, _ in items)
        size_label = (
            f"{total_bytes / 1e9:.2f} GB" if total_bytes >= 1e9
            else f"{total_bytes / 1e6:.1f} MB" if total_bytes >= 1e6
            else f"{total_bytes / 1e3:.1f} KB"
        )
        st.session_state.upload_conflict_result = {
            "items": items,
            "existing": existing,
            "total_bytes": total_bytes,
            "size_label": size_label,
        }

# ──────────────────────────────────────────────
# Page config
# ──────────────────────────────────────────────
st.set_page_config(
    page_title="AWS S3 App",
    page_icon="☁️",
    layout="wide",
)
st.title("☁️ AWS S3 App")

# ──────────────────────────────────────────────
# Sidebar — AWS credentials
# ──────────────────────────────────────────────
with st.sidebar:
    st.header("☁️ AWS Login")

    if "aws_profile_default" not in st.session_state:
        st.session_state.aws_profile_default = AWS_PROFILE or ""

    aws_profile = st.text_input(
        "AWS profile name",
        value=st.session_state.aws_profile_default,
        placeholder="e.g. storage-aibs  (leave blank for default)",
        key="aws_profile_input",
    ).strip() or None

    if st.button("🔍 Check credentials"):
        with st.spinner("Checking..."):
            ok, msg = check_credentials(aws_profile)
        if ok:
            st.success(f"✅ Logged in\n\n{msg}")
        else:
            st.error(f"❌ {msg}")

    st.caption("If not logged in, click below to open the AWS SSO browser login.")
    if st.button("🔑 Login to AWS (SSO)"):
        st.info("A browser window will open. Complete login there, then click **Check credentials** to verify.")
        with st.spinner("Waiting for browser login... (up to 5 minutes)"):
            ok, output = run_sso_login(aws_profile)
        if ok:
            st.success("Login successful!")
        else:
            st.error(f"Login failed: {output}")
            st.caption("If the browser did not open, run `aws sso login` in the terminal manually.")

    st.divider()

# ──────────────────────────────────────────────
# Session state defaults
# ──────────────────────────────────────────────
if "current_prefix" not in st.session_state:
    st.session_state.current_prefix = S3_PREFIX

if "s3_bucket" not in st.session_state:
    st.session_state.s3_bucket = S3_BUCKET

if "local_dest" not in st.session_state:
    st.session_state.local_dest = ""

# Upload-specific state
if "upload_bucket" not in st.session_state:
    st.session_state.upload_bucket = S3_BUCKET

if "upload_prefix" not in st.session_state:
    st.session_state.upload_prefix = ""

if "upload_source" not in st.session_state:
    st.session_state.upload_source = ""

if "upload_conflict_result" not in st.session_state:
    # Stores (items, existing_keys, overwrite_choice) after conflict check
    st.session_state.upload_conflict_result = None

if "upload_large_scan_pending" not in st.session_state:
    # Set to a (items, source_path) tuple when a scan finds more files than
    # MAX_UPLOAD_FILES_WARN and is waiting on user confirmation before
    # continuing to the (potentially slow) S3 conflict check.
    st.session_state.upload_large_scan_pending = None


# ──────────────────────────────────────────────
# Main tabs
# ──────────────────────────────────────────────
tab_download, tab_upload = st.tabs(["📥 Download", "📤 Upload"])


# ══════════════════════════════════════════════
# DOWNLOAD TAB
# ══════════════════════════════════════════════
with tab_download:
    _dl_job = get_current_download_job()

    # ──────────────────────────────────────────────────────────────────────
    # PHASE 2 — Download in progress
    # ──────────────────────────────────────────────────────────────────────
    if _dl_job is not None and _dl_job.is_running:
        st.info("⏳ **Download in progress.** Running safely in the background — accidental clicks won't interrupt it.")
        st.code(_dl_job.get_log(), language=None)
        time.sleep(2)
        st.rerun()

    # ──────────────────────────────────────────────────────────────────────
    # PHASE 3 — Download complete or failed
    # ──────────────────────────────────────────────────────────────────────
    elif _dl_job is not None and not _dl_job.is_running:
        if _dl_job.status == "done":
            dl, sk = _dl_job.result or (0, 0)
            st.success(f"✅ Download complete — **{dl}** file(s) downloaded, **{sk}** skipped.")
        else:
            st.error(f"❌ Download failed: {_dl_job.error}")

        with st.expander("📋 View download log"):
            st.code(_dl_job.get_log(), language=None)
        st.caption(f"Log saved to: `{_dl_job.log_path}`")

        if st.button("🔄 Clear / Start New Download", key="clear_download_job_btn"):
            clear_download_job()
            st.rerun()

    # ──────────────────────────────────────────────────────────────────────
    # PHASE 1 — Configure & start
    # ──────────────────────────────────────────────────────────────────────
    else:
        # ──────────────────────────────────────────
        # Bucket input
        # ──────────────────────────────────────────
        st.header("⚙️ Settings")
        col_bucket, col_go = st.columns([4, 1])
        with col_bucket:
            entered_bucket = st.text_input(
                "S3 bucket name",
                value=st.session_state.s3_bucket,
                placeholder="e.g. barseq-prod-802451596237-us-west-2",
                key="bucket_input",
            ).strip()
        with col_go:
            st.write("")
            st.write("")
            if st.button("🔄 Load bucket"):
                if entered_bucket and entered_bucket != st.session_state.s3_bucket:
                    st.session_state.s3_bucket = entered_bucket
                    st.session_state.current_prefix = ""
                    st.rerun()

        if entered_bucket and entered_bucket != st.session_state.s3_bucket:
            st.caption("Click **🔄 Load bucket** to browse this bucket.")

        bucket = st.session_state.s3_bucket
        st.divider()

        # ──────────────────────────────────────────
        # S3 Folder Browser
        # ──────────────────────────────────────────
        st.header("📂 Browse S3")

        if not aws_profile:
            st.warning("⚠️ Enter your AWS profile name in the sidebar (e.g. `storage-aibs`) and click **Check credentials** before browsing.")
            st.stop()

        current_prefix = st.session_state.current_prefix

        # Breadcrumb navigation
        crumbs = prefix_to_breadcrumbs(current_prefix)
        crumb_cols = st.columns(len(crumbs))
        for col, (label, crumb_prefix) in zip(crumb_cols, crumbs):
            with col:
                if st.button(label, key=f"crumb_{crumb_prefix}"):
                    st.session_state.current_prefix = crumb_prefix
                    st.rerun()

        st.caption(f"**Bucket:** `{bucket}`  |  **Current path:** `/{current_prefix}`")
        st.divider()

        # List current prefix
        try:
            with st.spinner("Loading..."):
                folders, objects = list_prefix(bucket, current_prefix, profile=aws_profile)
        except Exception as e:
            st.error(f"Could not list S3 contents: {e}")
            st.stop()

        # Go up button
        if current_prefix:
            parent = "/".join(current_prefix.rstrip("/").split("/")[:-1])
            parent = parent + "/" if parent else ""
            if st.button("⬆ Go up"):
                st.session_state.current_prefix = parent
                st.rerun()

        # Show sub-folders
        if folders:
            hdr_col, btn_col = st.columns([7, 3])
            with hdr_col:
                st.subheader("📁 Folders")
            with btn_col:
                st.write("")
                ca_col, cc_col = st.columns(2)
                with ca_col:
                    if st.button("☑ Select all", key="sel_all_folders"):
                        for fp in folders:
                            st.session_state[f"cb_{fp}"] = True
                        st.rerun()
                with cc_col:
                    if st.button("☐ Clear", key="clear_all_folders"):
                        for fp in folders:
                            st.session_state[f"cb_{fp}"] = False
                        st.rerun()

            for folder_prefix in folders:
                name = folder_name(folder_prefix)
                cb_col, nav_col = st.columns([1, 11])
                with cb_col:
                    st.checkbox("Select", key=f"cb_{folder_prefix}", label_visibility="collapsed")
                with nav_col:
                    if st.button(f"📁  {name}", key=f"folder_{folder_prefix}"):
                        st.session_state.current_prefix = folder_prefix
                        st.rerun()
        else:
            st.caption("_(No sub-folders)_")

        selected_folders = [fp for fp in folders if st.session_state.get(f"cb_{fp}", False)]

        # Show files at this level
        if objects:
            st.subheader(f"📄 Files ({len(objects)})")
            total_size = sum(o.size for o in objects)
            size_label = (
                f"{total_size / 1e9:.2f} GB" if total_size >= 1e9
                else f"{total_size / 1e6:.1f} MB" if total_size >= 1e6
                else f"{total_size / 1e3:.1f} KB"
            )
            st.caption(f"Total: {len(objects)} file(s), {size_label}")
            with st.expander("View file list"):
                for obj in objects:
                    st.text(f"  {obj.name}  ({obj.size_human})")

        if not folders and not objects:
            st.info("This folder is empty.")

        # ──────────────────────────────────────────
        # Download section
        # ──────────────────────────────────────────
        st.divider()
        st.header("📥 Download")

        if not current_prefix and not folders and not objects:
            st.info("Navigate into a folder above to download it.")
        else:
            local_dest = st.text_input(
                "Local destination folder",
                value=st.session_state.local_dest,
                placeholder=r"e.g. C:\Users\you\Downloads\my_data",
                key="local_dest_input",
            ).strip()
            st.session_state.local_dest = local_dest

            if not local_dest:
                st.caption("Enter a local destination path to enable download.")

            skip_existing = st.checkbox(
                "⏭️ Skip files that already exist locally",
                value=True,
                key="skip_existing_checkbox",
                help="If checked, files already present at the destination will not be re-downloaded.",
            )

            # ── Option A: download selected subfolders ────────────────────────
            if selected_folders:
                sel_names = [folder_name(fp) for fp in selected_folders]
                st.markdown(
                    f"**{len(selected_folders)} subfolder(s) selected:** "
                    + ", ".join(f"`{n}`" for n in sel_names)
                )
                st.caption("Each selected folder will be created as its own sub-folder inside your destination.")

                multi_download_clicked = st.button(
                    f"📥 Download {len(selected_folders)} selected folder(s)",
                    disabled=not local_dest,
                    type="primary",
                    key="multi_download_btn",
                )

                if multi_download_clicked and local_dest:
                    dest_path = Path(local_dest)
                    prefixes = [
                        (fp, str(dest_path / folder_name(fp)))
                        for fp in selected_folders
                    ]
                    start_download_job(
                        bucket=bucket,
                        prefixes=prefixes,
                        skip_existing=skip_existing,
                        profile=aws_profile,
                    )
                    st.rerun()

                st.divider()

            # ── Option B: download the entire current folder ──────────────────
            folder_label = folder_name(current_prefix) if current_prefix else bucket
            st.markdown(f"**Or download entire current folder:** `{current_prefix or '(bucket root)'}` — **{folder_label}**")

            download_clicked = st.button(
                f"📥 Download  **{folder_label}**",
                disabled=not local_dest,
                type="primary" if not selected_folders else "secondary",
            )

            if download_clicked and local_dest:
                dest_path = Path(local_dest)
                start_download_job(
                    bucket=bucket,
                    prefixes=[(current_prefix, str(dest_path))],
                    skip_existing=skip_existing,
                    profile=aws_profile,
                )
                st.rerun()


# ══════════════════════════════════════════════
# UPLOAD TAB
# ══════════════════════════════════════════════
with tab_upload:
    st.header("📤 Upload to S3")

    if not aws_profile:
        st.warning("⚠️ Enter your AWS profile name in the sidebar (e.g. `storage-aibs`) and click **Check credentials** before uploading.")
        st.stop()

    _job = get_current_job()

    # ──────────────────────────────────────────────────────────────────────
    # PHASE 2 — Upload in progress
    # ──────────────────────────────────────────────────────────────────────
    if _job is not None and _job.is_running:
        st.info("⏳ **Upload in progress.** Do not close this tab — the upload will continue even if you click elsewhere in the app.")

        prog = _job.progress or {}
        total = prog.get("total") or 0
        done = prog.get("done") or 0
        total_bytes = prog.get("total_bytes") or 0
        bytes_done = prog.get("bytes_done") or 0

        if total:
            fraction = min(done / total, 1.0)
            size_bit = ""
            if total_bytes:
                size_bit = (
                    f" — {bytes_done / 1e9:.2f}/{total_bytes / 1e9:.2f} GB"
                    if total_bytes >= 1e9
                    else f" — {bytes_done / 1e6:.1f}/{total_bytes / 1e6:.1f} MB"
                )
            st.progress(
                fraction,
                text=f"{done}/{total} files ({fraction * 100:.0f}%){size_bit}",
            )
            current_file = prog.get("current_file")
            if current_file:
                st.caption(f"Current: `{current_file}`")

        st.code(_job.get_log(), language=None)
        time.sleep(2)
        st.rerun()

    # ──────────────────────────────────────────────────────────────────────
    # PHASE 3 — Upload complete or failed
    # ──────────────────────────────────────────────────────────────────────
    elif _job is not None and not _job.is_running:
        if _job.status == "done":
            uploaded, skipped = _job.result or (0, 0)
            st.success(f"✅ Upload complete — **{uploaded}** file(s) uploaded, **{skipped}** skipped.")
        else:
            st.error(f"❌ Upload failed: {_job.error}")

        with st.expander("📋 View upload log"):
            st.code(_job.get_log(), language=None)

        if st.button("🔄 Clear / Start New Upload", key="clear_upload_job"):
            clear_job()
            st.session_state.upload_conflict_result = None
            st.session_state.upload_large_scan_pending = None
            st.rerun()

    # ──────────────────────────────────────────────────────────────────────
    # PHASE 1 — Configure & check
    # ──────────────────────────────────────────────────────────────────────
    else:
        st.markdown(
            "Upload a local file or folder to an S3 bucket. "
            "Large uploads run in a **background thread** — accidental clicks won't interrupt them."
        )
        st.divider()

        # ── Source ──────────────────────────────────────────────────────
        st.subheader("📁 Local Source")
        upload_source = st.text_input(
            "Local file or folder path",
            value=st.session_state.upload_source,
            placeholder=r"e.g. C:\Users\you\data\experiment1",
            key="upload_source_input",
        ).strip()
        st.session_state.upload_source = upload_source

        # ── Destination ─────────────────────────────────────────────────
        st.subheader("🪣 S3 Destination")
        col_up_bucket, col_up_prefix = st.columns([2, 3])
        with col_up_bucket:
            upload_bucket = st.text_input(
                "Target bucket",
                value=st.session_state.upload_bucket,
                placeholder="e.g. aibs-storage",
                key="upload_bucket_input",
            ).strip()
            st.session_state.upload_bucket = upload_bucket
        with col_up_prefix:
            upload_prefix = st.text_input(
                "Destination prefix (sub-folder, optional)",
                value=st.session_state.upload_prefix,
                placeholder="e.g. experiments/2025/my_dataset",
                key="upload_prefix_input",
            ).strip()
            st.session_state.upload_prefix = upload_prefix

        _src_is_dir = upload_source and Path(upload_source).is_dir()
        _folder_suffix = f"/{Path(upload_source).name}" if _src_is_dir else ""
        if upload_bucket and upload_prefix:
            st.caption(f"Files will be uploaded to: `s3://{upload_bucket}/{upload_prefix.strip('/')}{_folder_suffix}/…`")
        elif upload_bucket:
            st.caption(f"Files will be uploaded to: `s3://{upload_bucket}{_folder_suffix}/…` (bucket root)")

        st.divider()

        # ── Conflict check ──────────────────────────────────────────────
        can_check = bool(upload_source and upload_bucket)

        if st.button("🔍 Check for conflicts", disabled=not can_check, key="check_conflicts"):
            source_path = Path(upload_source)
            if not source_path.exists():
                st.error(f"Path does not exist: `{upload_source}`")
            else:
                with st.spinner("Scanning local files..."):
                    try:
                        items = collect_local_files(source_path)
                    except TooManyFilesError as e:
                        st.error(f"🚫 {e}")
                        items = None
                if items is None:
                    st.session_state.upload_large_scan_pending = None
                elif not items:
                    st.warning("No files found at the specified path.")
                    st.session_state.upload_large_scan_pending = None
                elif len(items) > MAX_UPLOAD_FILES_WARN:
                    # Large but supported — ask for confirmation before doing
                    # the (potentially slow) S3 listing/conflict check.
                    st.session_state.upload_large_scan_pending = {
                        "items": items,
                        "source_path": str(source_path),
                    }
                else:
                    st.session_state.upload_large_scan_pending = None
                    _run_conflict_check(items, upload_bucket, upload_prefix, aws_profile)

        _pending = st.session_state.upload_large_scan_pending
        if _pending:
            n = len(_pending["items"])
            st.warning(
                f"⚠️ Found **{n:,} files** under `{_pending['source_path']}`. "
                "This app can handle uploads this large — it uploads in "
                "chunks and can resume if interrupted — but a scan/upload "
                "this size can take a long time. Confirm to continue."
            )
            col_confirm, col_cancel = st.columns(2)
            with col_confirm:
                if st.button(f"✅ Proceed with {n:,} files", key="confirm_large_scan"):
                    items = _pending["items"]
                    st.session_state.upload_large_scan_pending = None
                    _run_conflict_check(items, upload_bucket, upload_prefix, aws_profile)
                    st.rerun()
            with col_cancel:
                if st.button("Cancel", key="cancel_large_scan"):
                    st.session_state.upload_large_scan_pending = None
                    st.rerun()

        if not can_check:
            st.caption("Enter a local path and target bucket above to enable conflict check.")

        # ── Confirm & upload ────────────────────────────────────────────
        conflict_result = st.session_state.upload_conflict_result
        if conflict_result:
            items = conflict_result["items"]
            existing = conflict_result["existing"]
            size_label = conflict_result["size_label"]

            _summary_src = Path(upload_source)
            _folder_seg = f"{_summary_src.name}/" if _summary_src.is_dir() else ""
            _prefix_seg = upload_prefix.strip("/") + "/" if upload_prefix.strip("/") else ""
            st.subheader("📋 Upload Summary")
            st.markdown(
                f"- **Files found:** {len(items)}\n"
                f"- **Total size:** {size_label}\n"
                f"- **Target:** `s3://{upload_bucket}/{_prefix_seg}{_folder_seg}`"
            )

            if existing:
                st.warning(f"⚠️ **{len(existing)} file(s) already exist** in S3 at the target location.")
                with st.expander(f"View {len(existing)} conflicting key(s)"):
                    for key in sorted(existing):
                        st.text(f"  {key}")

                overwrite_choice = st.radio(
                    "How should existing files be handled?",
                    options=["Skip existing files (safe)", "Overwrite existing files"],
                    key="overwrite_radio",
                )
                overwrite = overwrite_choice.startswith("Overwrite")
            else:
                st.success("✅ No conflicts — all files are new.")
                overwrite = True

            st.divider()

            if st.button("✅ Confirm & Start Upload", type="primary", key="confirm_upload"):
                source_path = Path(upload_source)
                cp_id = checkpoint_id_for(upload_bucket, upload_prefix, str(source_path))

                def _do_upload(emit, progress_cb, **kw):
                    return upload_files(
                        bucket=kw["bucket"],
                        items=kw["items"],
                        dest_prefix=kw["dest_prefix"],
                        profile=kw["profile"],
                        overwrite=kw["overwrite"],
                        emit=emit,
                        progress_cb=progress_cb,
                        checkpoint_id=kw["checkpoint_id"],
                    )

                start_upload_job(
                    _do_upload,
                    bucket=upload_bucket,
                    items=items,
                    dest_prefix=upload_prefix,
                    profile=aws_profile,
                    overwrite=overwrite,
                    checkpoint_id=cp_id,
                )
                st.session_state.upload_conflict_result = None
                st.rerun()
