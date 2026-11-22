"""Shared Streamlit authentication with salted password hashing and fail-closed resets.

User records are stored locally for backward compatibility. For production, move the
user store and sessions to a managed identity provider / shared database.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import re
import secrets
import smtplib
import ssl
import time
from email.message import EmailMessage
from pathlib import Path
from typing import Any

import streamlit as st

USER_FILE = Path(__file__).with_name("users.json")
PBKDF2_ITERATIONS = 600_000
RESET_TTL_SECONDS = 600
MAX_RESET_ATTEMPTS = 5
USERNAME_RE = re.compile(r"^[A-Za-z0-9_.@-]{3,120}$")


def hash_password(password: str, *, salt: bytes | None = None) -> str:
    """Return a versioned PBKDF2-SHA256 hash with a unique random salt."""
    if not isinstance(password, str) or not password:
        raise ValueError("Password cannot be empty.")
    salt = salt or secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), salt, PBKDF2_ITERATIONS
    )
    return f"pbkdf2_sha256${PBKDF2_ITERATIONS}${salt.hex()}${digest.hex()}"


def _verify_password(password: str, stored: str) -> tuple[bool, bool]:
    """Return (valid, needs_upgrade); supports legacy SHA-256 hashes once."""
    if stored.startswith("pbkdf2_sha256$"):
        try:
            _, rounds, salt_hex, digest_hex = stored.split("$", 3)
            rounds_int = int(rounds)
            if rounds_int < 100_000 or rounds_int > 2_000_000:
                return False, False
            candidate = hashlib.pbkdf2_hmac(
                "sha256", password.encode("utf-8"), bytes.fromhex(salt_hex), rounds_int
            ).hex()
            return hmac.compare_digest(candidate, digest_hex), False
        except (ValueError, TypeError):
            return False, False
    # Legacy hashes in the uploaded project used unsalted SHA-256.
    if re.fullmatch(r"[0-9a-fA-F]{64}", stored or ""):
        candidate = hashlib.sha256(password.encode("utf-8")).hexdigest()
        valid = hmac.compare_digest(candidate, stored.lower())
        return valid, valid
    return False, False


def load_users() -> dict[str, dict[str, Any]]:
    if not USER_FILE.exists():
        return {}
    try:
        data = json.loads(USER_FILE.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError):
        st.error("The local user store could not be read. Contact the administrator.")
        st.stop()
    return {}


def save_users(users: dict[str, dict[str, Any]]) -> None:
    USER_FILE.parent.mkdir(parents=True, exist_ok=True)
    temporary = USER_FILE.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(users, indent=2), encoding="utf-8")
    try:
        os.chmod(temporary, 0o600)
    except OSError:
        pass
    temporary.replace(USER_FILE)


def _smtp_send(to_email: str, subject: str, body: str) -> bool:
    host = os.getenv("SMTP_HOST")
    username = os.getenv("SMTP_USER")
    password = os.getenv("SMTP_PASSWORD")
    sender = os.getenv("SMTP_FROM") or username
    if not all((host, sender, to_email)):
        return False
    try:
        port = int(os.getenv("SMTP_PORT", "587"))
        message = EmailMessage()
        message["Subject"] = subject
        message["From"] = sender
        message["To"] = to_email
        message.set_content(body)
        context = ssl.create_default_context()
        with smtplib.SMTP(host, port, timeout=15) as server:
            server.ehlo()
            if os.getenv("SMTP_STARTTLS", "true").lower() in {"1", "true", "yes"}:
                server.starttls(context=context)
                server.ehlo()
            if username and password:
                server.login(username, password)
            server.send_message(message)
        return True
    except (OSError, smtplib.SMTPException, ValueError):
        return False


def _valid_new_password(password: str) -> bool:
    """Accept any non-empty password; complexity rules are intentionally disabled."""
    return isinstance(password, str) and bool(password.strip())


def _login(users: dict[str, dict[str, Any]]) -> None:
    st.markdown("### Sign in")
    username = st.text_input("Username", key="auth_username")
    password = st.text_input("Password", type="password", key="auth_password")
    if st.button("Sign in", type="primary", width="stretch"):
        record = users.get(username)
        valid, upgrade = _verify_password(password, str(record.get("password", ""))) if record else (False, False)
        if valid:
            if upgrade:
                record["password"] = hash_password(password)
                save_users(users)
            st.session_state.update(
                logged_in=True,
                username=username,
                role=record.get("role", "user"),
                auth_time=int(time.time()),
                last_activity=int(time.time()),
            )
            st.rerun()
        else:
            st.error("Invalid username or password.")


def _signup(users: dict[str, dict[str, Any]]) -> None:
    st.markdown("### Create account")
    username = st.text_input("Username", key="signup_username").strip()
    email = st.text_input("Email address", key="signup_email").strip()
    password = st.text_input("Password", type="password", key="signup_password")
    confirm = st.text_input("Confirm password", type="password", key="signup_confirm")
    st.caption("Choose any password you can remember. Passwords cannot be empty.")
    if st.button("Create account", type="primary", width="stretch"):
        if not USERNAME_RE.fullmatch(username):
            st.error("Username must be 3–120 characters and use only letters, numbers, . _ @ or -.")
        elif username in users:
            st.error("That username is already registered.")
        elif email and not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email):
            st.error("Enter a valid email address.")
        elif password != confirm:
            st.error("Passwords do not match.")
        elif not _valid_new_password(password):
            st.error("Password cannot be empty.")
        else:
            users[username] = {
                "password": hash_password(password),
                "email": email,
                "role": "user",
            }
            save_users(users)
            st.success("Account created. Sign in to continue.")
            st.session_state["auth_mode"] = "login"
            st.rerun()


def _forgot_password(users: dict[str, dict[str, Any]]) -> None:
    st.markdown("### Password recovery")
    username = st.text_input("Username", key="reset_username").strip()
    if st.button("Send recovery code", width="stretch"):
        record = users.get(username)
        # Do not disclose whether an account exists.
        if record and record.get("email"):
            code = f"{secrets.randbelow(1_000_000):06d}"
            sent = _smtp_send(
                str(record["email"]),
                "Universal AI Studio password recovery",
                f"Your password recovery code is {code}. It expires in 10 minutes.",
            )
            if sent:
                st.session_state["reset_code_hash"] = hashlib.sha256(code.encode()).hexdigest()
                st.session_state["reset_user"] = username
                st.session_state["reset_expires"] = int(time.time()) + RESET_TTL_SECONDS
                st.session_state["reset_attempts"] = 0
        st.info("If the account is eligible and mail is configured, a recovery code has been sent.")
    if st.session_state.get("reset_code_hash"):
        code = st.text_input("Recovery code", key="reset_code")
        new_password = st.text_input("New password", type="password", key="reset_new_password")
        confirm = st.text_input("Confirm new password", type="password", key="reset_confirm_password")
        if st.button("Reset password", type="primary", width="stretch"):
            attempts = int(st.session_state.get("reset_attempts", 0)) + 1
            st.session_state["reset_attempts"] = attempts
            expected = st.session_state.get("reset_code_hash", "")
            actual = hashlib.sha256(code.encode()).hexdigest()
            valid = (
                attempts <= MAX_RESET_ATTEMPTS
                and int(time.time()) <= int(st.session_state.get("reset_expires", 0))
                and hmac.compare_digest(actual, expected)
            )
            if not valid:
                st.session_state.pop("reset_code_hash", None)
                st.error("The recovery code is invalid or expired. Start again.")
            elif new_password != confirm or not _valid_new_password(new_password):
                st.error("Passwords must match and cannot be empty.")
            else:
                user = str(st.session_state.get("reset_user", ""))
                if user in users:
                    users[user]["password"] = hash_password(new_password)
                    save_users(users)
                for key in ("reset_code_hash", "reset_user", "reset_expires", "reset_attempts"):
                    st.session_state.pop(key, None)
                st.success("Password updated. Sign in with your new password.")
                st.session_state["auth_mode"] = "login"
                st.rerun()


def _bootstrap_admin(users: dict[str, dict[str, Any]]) -> None:
    """Create the first administrator from optional explicit environment credentials."""
    username = os.getenv("UAS_BOOTSTRAP_ADMIN_USERNAME")
    password = os.getenv("UAS_BOOTSTRAP_ADMIN_PASSWORD")
    if not users and username and _valid_new_password(password):
        users[username] = {
            "password": hash_password(password),
            "email": os.getenv("UAS_BOOTSTRAP_ADMIN_EMAIL", ""),
            "role": "admin",
        }
        save_users(users)


def login_manager() -> None:
    if st.session_state.get("logged_in"):
        return
    users = load_users()
    _bootstrap_admin(users)
    if not users:
        st.warning("No user accounts are configured.")
        st.caption(
            "Add a local account to auth/users.json or set UAS_BOOTSTRAP_ADMIN_USERNAME "
            "and UAS_BOOTSTRAP_ADMIN_PASSWORD in your environment, then restart the app."
        )
    st.title("Universal AI Studio")
    st.caption("Secure access to your AI application workspace")
    mode = st.session_state.get("auth_mode", "login")
    if mode == "signup":
        _signup(users)
    elif mode == "forgot":
        _forgot_password(users)
    else:
        _login(users)
    left, right = st.columns(2)
    with left:
        if st.button("Create account", width="stretch"):
            st.session_state["auth_mode"] = "signup"
            st.rerun()
    with right:
        if st.button("Forgot password?", width="stretch"):
            st.session_state["auth_mode"] = "forgot"
            st.rerun()
    st.stop()
