from __future__ import annotations

import html
import json
from urllib.parse import parse_qs

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, RedirectResponse


router = APIRouter()
STATUS_COOKIE_NAME = "flint_status_user"
STATUS_DEVICE_IP_COOKIE_NAME = "flint_status_device_ip"
STATUS_DEVICE_MAC_COOKIE_NAME = "flint_status_device_mac"
STATUS_COOKIE_MAX_AGE = 60 * 60 * 12


@router.get("/", response_class=HTMLResponse)
@router.get("/status", response_class=HTMLResponse)
@router.get("/status/{username}", response_class=HTMLResponse)
def hotspot_status_page(request: Request, username: str | None = None) -> HTMLResponse:
    return HTMLResponse(
        _render_status_page(
            _resolve_page_username(request),
            _resolve_current_device_ip(request),
            _resolve_current_device_mac(request),
        )
    )


@router.get("/launch-status")
def launch_status_redirect(request: Request) -> RedirectResponse:
    return _build_launch_response(
        request,
        _first_query_value(
            request,
            ("username", "user", "name", "login", "hotspot_user"),
        ),
        _first_query_value(request, ("ip", "ip_address", "address")),
        _first_query_value(request, ("mac", "mac_address", "mac-address")),
    )


@router.post("/launch-status")
async def launch_status_page(request: Request) -> RedirectResponse:
    posted_values = _extract_posted_values(await request.body())
    username = _first_posted_value(
        posted_values,
        ("username", "user", "name", "login", "hotspot_user"),
    )
    device_ip = _first_posted_value(posted_values, ("ip", "ip_address", "address"))
    device_mac = _first_posted_value(posted_values, ("mac", "mac_address", "mac-address"))
    return _build_launch_response(request, username, device_ip, device_mac)


def _build_launch_response(
    request: Request,
    username: str | None,
    device_ip: str | None,
    device_mac: str | None,
) -> RedirectResponse:
    response = RedirectResponse(url="/", status_code=303)
    if username:
        _set_status_cookie(response, request, STATUS_COOKIE_NAME, username)
        if device_ip:
            _set_status_cookie(response, request, STATUS_DEVICE_IP_COOKIE_NAME, device_ip)
        else:
            response.delete_cookie(STATUS_DEVICE_IP_COOKIE_NAME, path="/")
        if device_mac:
            _set_status_cookie(response, request, STATUS_DEVICE_MAC_COOKIE_NAME, device_mac)
        else:
            response.delete_cookie(STATUS_DEVICE_MAC_COOKIE_NAME, path="/")
    else:
        response.delete_cookie(STATUS_COOKIE_NAME, path="/")
        response.delete_cookie(STATUS_DEVICE_IP_COOKIE_NAME, path="/")
        response.delete_cookie(STATUS_DEVICE_MAC_COOKIE_NAME, path="/")

    return response


def _resolve_page_username(request: Request) -> str | None:
    return _normalize_optional_text(request.cookies.get(STATUS_COOKIE_NAME))


def _resolve_current_device_ip(request: Request) -> str | None:
    query_ip = _first_query_value(request, ("ip", "ip_address", "address"))
    if query_ip:
        return query_ip
    cookie_ip = _normalize_optional_text(request.cookies.get(STATUS_DEVICE_IP_COOKIE_NAME))
    if cookie_ip:
        return cookie_ip
    for header_name in ("cf-connecting-ip", "x-real-ip", "x-forwarded-for"):
        header_value = _normalize_optional_text(request.headers.get(header_name))
        if header_value:
            return header_value.split(",", 1)[0].strip()
    if request.client is None:
        return None
    return _normalize_optional_text(request.client.host)


def _resolve_current_device_mac(request: Request) -> str | None:
    return _first_query_value(request, ("mac", "mac_address", "mac-address")) or (
        _normalize_optional_text(request.cookies.get(STATUS_DEVICE_MAC_COOKIE_NAME))
    )


def _first_query_value(request: Request, keys: tuple[str, ...]) -> str | None:
    for key in keys:
        value = _normalize_optional_text(request.query_params.get(key))
        if value:
            return value
    return None


def _extract_posted_values(body: bytes) -> dict[str, list[str]]:
    try:
        return parse_qs(body.decode("utf-8"), keep_blank_values=False)
    except UnicodeDecodeError:
        return {}


def _first_posted_value(
    posted_values: dict[str, list[str]],
    keys: tuple[str, ...],
) -> str | None:
    for key in keys:
        values = posted_values.get(key)
        if not values:
            continue

        normalized_value = _normalize_optional_text(values[0])
        if normalized_value:
            return normalized_value

    return None


def _set_status_cookie(
    response: RedirectResponse,
    request: Request,
    name: str,
    value: str,
) -> None:
    response.set_cookie(
        name,
        value,
        max_age=STATUS_COOKIE_MAX_AGE,
        httponly=True,
        samesite="lax",
        secure=request.url.scheme == "https",
        path="/",
    )


def _normalize_optional_text(value: object) -> str | None:
    if not isinstance(value, str):
        return None

    normalized_value = value.strip()
    return normalized_value or None


def _render_status_page(
    username: str | None,
    current_device_ip: str | None = None,
    current_device_mac: str | None = None,
) -> str:
    initial_username = (username or "").strip()
    html_username = html.escape(initial_username, quote=True)
    json_username = json.dumps(initial_username)
    json_current_device_ip = json.dumps((current_device_ip or "").strip())
    json_current_device_mac = json.dumps((current_device_mac or "").strip())
    locked_username = html.escape(initial_username or "Waiting for hotspot session", quote=False)
    locked_message = html.escape(
        (
            "Voucher details are locked to your current hotspot session."
            if initial_username
            else "Open this page from your hotspot status page to load your voucher details."
        ),
        quote=False,
    )
    return """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1, maximum-scale=1, user-scalable=no">
    <title>FLINT WiFi | Hotspot Status</title>
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet">
    <style>
        :root {
            --bg: #f5f6fa;
            --surface: #ffffff;
            --border: #e4e6ed;
            --text: #1a1f36;
            --text-secondary: #6b7280;
            --text-tertiary: #9ca3af;
            --primary: #4f46e5;
            --primary-light: #eef2ff;
            --primary-hover: #4338ca;
            --success: #059669;
            --success-light: #ecfdf5;
            --danger: #dc2626;
            --danger-light: #fef2f2;
            --warning: #d97706;
            --warning-light: #fffbeb;
            --shadow: 0 1px 3px rgba(0,0,0,0.08);
            --radius: 12px;
            --radius-sm: 8px;
        }

        * {
            box-sizing: border-box;
            margin: 0;
            padding: 0;
        }

        body {
            font-family: "Inter", -apple-system, sans-serif;
            color: var(--text);
            background: var(--bg);
            line-height: 1.4;
            -webkit-font-smoothing: antialiased;
            -webkit-tap-highlight-color: transparent;
        }

        .container {
            max-width: 600px;
            margin: 0 auto;
            padding: 12px 12px 18px;
        }

        /* Header */
        .header {
            display: flex;
            align-items: center;
            gap: 8px;
            margin-bottom: 12px;
            padding: 0 4px;
        }

        .logo-icon {
            width: 32px;
            height: 32px;
            border-radius: 8px;
            background: linear-gradient(135deg, #4f46e5, #6366f1);
            display: flex;
            align-items: center;
            justify-content: center;
            flex-shrink: 0;
        }

        .logo-icon svg {
            width: 16px;
            height: 16px;
        }

        .logo-text {
            font-size: 1rem;
            font-weight: 700;
            letter-spacing: -0.02em;
        }

        .logo-text span {
            color: var(--primary);
        }

        .user-chip {
            margin-left: auto;
            display: inline-flex;
            align-items: center;
            gap: 4px;
            padding: 5px 10px;
            border-radius: 16px;
            background: var(--primary-light);
            color: var(--primary);
            font-size: 0.75rem;
            font-weight: 600;
            max-width: 140px;
            overflow: hidden;
            text-overflow: ellipsis;
            white-space: nowrap;
        }

        .user-chip.inactive {
            background: #f3f4f6;
            color: var(--text-tertiary);
        }

        .status-dot {
            width: 6px;
            height: 6px;
            border-radius: 50%;
            flex-shrink: 0;
        }

        .status-dot.active { background: var(--success); }
        .status-dot.idle { background: var(--text-tertiary); }
        .status-dot.error { background: var(--danger); }
        .status-dot.loading { 
            background: var(--primary);
            animation: pulse 1.5s infinite;
        }

        @keyframes pulse {
            0%, 100% { opacity: 1; }
            50% { opacity: 0.3; }
        }

        .loading-overlay {
            position: fixed;
            inset: 0;
            z-index: 1100;
            display: flex;
            align-items: center;
            justify-content: center;
            padding: 20px;
            background: rgba(245, 246, 250, 0.86);
            backdrop-filter: blur(4px);
        }

        .loading-overlay[hidden] {
            display: none;
        }

        .loading-card {
            width: min(100%, 360px);
            padding: 26px 22px;
            border: 1px solid var(--border);
            border-radius: 16px;
            background: var(--surface);
            box-shadow: 0 14px 40px rgba(26, 31, 54, 0.14);
            text-align: center;
        }

        .loading-spinner {
            width: 46px;
            height: 46px;
            margin: 0 auto 16px;
            border: 4px solid var(--primary-light);
            border-top-color: var(--primary);
            border-radius: 50%;
            animation: loading-spin 0.8s linear infinite;
        }

        .loading-title {
            font-size: 1rem;
            font-weight: 700;
            color: var(--text);
        }

        .loading-message {
            margin-top: 7px;
            font-size: 0.8rem;
            line-height: 1.55;
            color: var(--text-secondary);
        }

        .loading-progress {
            position: relative;
            height: 4px;
            margin-top: 18px;
            overflow: hidden;
            border-radius: 4px;
            background: var(--primary-light);
        }

        .loading-progress::after {
            content: "";
            position: absolute;
            inset: 0 auto 0 -40%;
            width: 40%;
            border-radius: inherit;
            background: var(--primary);
            animation: loading-progress 1.35s ease-in-out infinite;
        }

        @keyframes loading-spin {
            to { transform: rotate(360deg); }
        }

        @keyframes loading-progress {
            from { left: -40%; }
            to { left: 100%; }
        }

        @media (prefers-reduced-motion: reduce) {
            .loading-spinner,
            .loading-progress::after {
                animation-duration: 2.5s;
            }
        }

        /* Search */
        .search-section {
            margin-bottom: 10px;
        }

        .search-form {
            display: grid;
            grid-template-columns: minmax(0, 1fr) minmax(0, 1fr) auto;
            gap: 6px;
            padding: 12px;
            border: 1px solid var(--border);
            border-radius: var(--radius);
            background: var(--surface);
        }

        .search-heading {
            grid-column: 1 / -1;
            font-size: 0.82rem;
            font-weight: 700;
        }

        .search-help {
            grid-column: 1 / -1;
            margin-top: -2px;
            font-size: 0.74rem;
            color: var(--text-secondary);
        }

        .search-input {
            flex: 1;
            height: 42px;
            padding: 0 12px;
            border: 1.5px solid var(--border);
            border-radius: var(--radius-sm);
            background: var(--surface);
            font-size: 0.875rem;
            color: var(--text);
            outline: none;
            min-width: 0;
        }

        .search-input:focus {
            border-color: var(--primary);
            box-shadow: 0 0 0 3px rgba(79, 70, 229, 0.1);
        }

        .search-input::placeholder {
            color: var(--text-tertiary);
            font-size: 0.8rem;
        }

        .password-field {
            position: relative;
            min-width: 0;
        }

        .password-field .search-input {
            width: 100%;
            padding-right: 58px;
        }

        .password-toggle {
            position: absolute;
            top: 50%;
            right: 5px;
            height: 32px;
            padding: 0 8px;
            transform: translateY(-50%);
            border: 0;
            border-radius: 6px;
            background: transparent;
            color: var(--primary);
            font: inherit;
            font-size: 0.72rem;
            font-weight: 700;
            cursor: pointer;
        }

        .password-toggle:hover,
        .password-toggle:focus-visible {
            background: var(--primary-light);
            outline: none;
        }

        @media (max-width: 520px) {
            .search-form {
                grid-template-columns: 1fr;
            }

            .search-form .btn {
                width: 100%;
            }
        }

        .session-section {
            margin-bottom: 10px;
        }

        .session-bar {
            display: flex;
            align-items: center;
            gap: 10px;
            padding: 12px;
            border: 1px solid var(--border);
            border-radius: var(--radius);
            background: var(--surface);
        }

        .session-copy {
            flex: 1;
            min-width: 0;
        }

        .session-title {
            font-size: 0.7rem;
            font-weight: 700;
            color: var(--text-tertiary);
            text-transform: uppercase;
            letter-spacing: 0.06em;
        }

        .session-username {
            margin-top: 3px;
            font-size: 0.95rem;
            font-weight: 700;
            color: var(--text);
            word-break: break-word;
        }

        .session-username.empty {
            color: var(--text-tertiary);
        }

        .session-note {
            margin-top: 3px;
            font-size: 0.76rem;
            color: var(--text-secondary);
            line-height: 1.45;
        }

        .btn {
            height: 42px;
            padding: 0 14px;
            border: none;
            border-radius: var(--radius-sm);
            font-size: 0.8rem;
            font-weight: 600;
            cursor: pointer;
            white-space: nowrap;
            transition: all 0.15s;
            -webkit-tap-highlight-color: transparent;
        }

        .btn:active {
            transform: scale(0.97);
        }

        .btn-primary {
            background: var(--primary);
            color: #fff;
        }

        .btn-outline {
            background: var(--surface);
            color: var(--text);
            border: 1.5px solid var(--border);
            padding: 0 10px;
        }

        .btn:disabled {
            opacity: 0.5;
            pointer-events: none;
        }

        /* Status Bar */
        .status-bar {
            display: flex;
            align-items: center;
            gap: 6px;
            padding: 8px 12px;
            margin-bottom: 10px;
            border-radius: var(--radius-sm);
            background: var(--surface);
            border: 1px solid var(--border);
            font-size: 0.78rem;
            color: var(--text-secondary);
        }

        /* Stats Grid */
        .stats-grid {
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 8px;
            margin-bottom: 10px;
        }

        .stat-card {
            padding: 12px 14px;
            background: var(--surface);
            border: 1px solid var(--border);
            border-radius: var(--radius);
        }

        .stat-label {
            font-size: 0.68rem;
            font-weight: 600;
            color: var(--text-tertiary);
            text-transform: uppercase;
            letter-spacing: 0.04em;
            margin-bottom: 3px;
        }

        .stat-value {
            font-size: 1.1rem;
            font-weight: 700;
            color: var(--text);
            letter-spacing: -0.02em;
            word-break: break-word;
        }

        .stat-value.accent {
            color: var(--primary);
        }

        /* Panels */
        .panels {
            display: flex;
            flex-direction: column;
            gap: 8px;
        }

        .panel {
            background: var(--surface);
            border: 1px solid var(--border);
            border-radius: var(--radius);
            overflow: hidden;
        }

        .panel-header {
            display: flex;
            align-items: center;
            justify-content: space-between;
            padding: 12px 14px 10px;
        }

        .panel-title {
            font-size: 0.85rem;
            font-weight: 700;
        }

        .panel-badge {
            font-size: 0.7rem;
            font-weight: 600;
            padding: 3px 8px;
            border-radius: 10px;
            background: #f3f4f6;
            color: var(--text-secondary);
        }

        .panel-badge.active {
            background: var(--success-light);
            color: var(--success);
        }

        .panel-badge.error {
            background: var(--danger-light);
            color: var(--danger);
        }

        /* Info List */
        .info-list {
            border-top: 1px solid #f3f4f6;
        }

        .info-row {
            display: flex;
            justify-content: space-between;
            align-items: flex-start;
            padding: 9px 14px;
            border-bottom: 1px solid #f9fafb;
            gap: 12px;
        }

        .info-row:last-child {
            border-bottom: none;
        }

        .info-key {
            font-size: 0.78rem;
            color: var(--text-secondary);
            flex-shrink: 0;
        }

        .info-value {
            font-size: 0.8rem;
            font-weight: 600;
            color: var(--text);
            text-align: right;
            word-break: break-word;
            max-width: 60%;
        }

        /* Devices */
        .devices-container {
            border-top: 1px solid #f3f4f6;
        }

        .device-item {
            padding: 10px 14px;
            border-bottom: 1px solid #f3f4f6;
        }

        .device-item:last-child {
            border-bottom: none;
        }

        .device-top {
            display: flex;
            justify-content: space-between;
            align-items: flex-start;
            gap: 8px;
            margin-bottom: 8px;
        }

        .device-name {
            font-size: 0.82rem;
            font-weight: 600;
        }

        .device-session {
            font-size: 0.7rem;
            color: var(--text-tertiary);
            margin-top: 1px;
        }

        .device-status {
            display: inline-flex;
            align-items: center;
            gap: 4px;
            padding: 3px 8px;
            border-radius: 10px;
            background: var(--success-light);
            color: var(--success);
            font-size: 0.68rem;
            font-weight: 600;
            flex-shrink: 0;
        }

        .device-badges {
            display: flex;
            align-items: center;
            justify-content: flex-end;
            flex-wrap: wrap;
            gap: 4px;
        }

        .device-status.current {
            background: var(--primary-light);
            color: var(--primary);
        }

        .device-metrics {
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 6px;
            margin-bottom: 8px;
        }

        .device-metric {
            padding: 7px 10px;
            background: #fafbfc;
            border-radius: 6px;
            border: 1px solid #f3f4f6;
        }

        .device-metric.full {
            grid-column: 1 / -1;
        }

        .device-metric-label {
            font-size: 0.62rem;
            font-weight: 600;
            color: var(--text-tertiary);
            text-transform: uppercase;
            letter-spacing: 0.03em;
            margin-bottom: 1px;
        }

        .device-metric-value {
            font-size: 0.75rem;
            font-weight: 600;
            color: var(--text);
            word-break: break-all;
        }

        .device-action {
            display: flex;
            justify-content: flex-end;
        }

        .btn-logout {
            height: 32px;
            padding: 0 12px;
            border: 1px solid #fecaca;
            border-radius: 6px;
            background: var(--surface);
            color: var(--danger);
            font-size: 0.73rem;
            font-weight: 600;
            cursor: pointer;
            transition: all 0.15s;
        }

        .btn-logout:active {
            background: var(--danger-light);
            transform: scale(0.97);
        }

        .btn-logout:disabled {
            opacity: 0.5;
            pointer-events: none;
        }

        /* Empty States */
        .empty-state {
            padding: 28px 16px;
            text-align: center;
            color: var(--text-tertiary);
            font-size: 0.8rem;
            font-weight: 500;
        }

        .empty-state.error {
            color: var(--danger);
        }

        /* Footer */
        .footer-note {
            padding: 8px 14px;
            text-align: right;
            font-size: 0.7rem;
            color: var(--text-tertiary);
            border-top: 1px solid #f3f4f6;
        }

        .page-footer {
            padding: 10px 4px 0;
            text-align: center;
            font-size: 0.74rem;
            font-weight: 600;
            color: var(--text-tertiary);
        }

        .modal-backdrop[hidden] {
            display: none;
        }

        .modal-backdrop {
            position: fixed;
            inset: 0;
            z-index: 50;
            display: flex;
            align-items: center;
            justify-content: center;
            padding: 18px;
            background: rgba(15, 23, 42, 0.44);
            backdrop-filter: blur(8px);
        }

        .modal {
            width: min(100%, 420px);
            background: linear-gradient(180deg, rgba(255,255,255,0.98), rgba(248,250,252,0.98));
            border: 1px solid rgba(228, 230, 237, 0.95);
            border-radius: 18px;
            box-shadow: 0 24px 60px rgba(15, 23, 42, 0.22);
            overflow: hidden;
        }

        .modal-header {
            display: flex;
            align-items: flex-start;
            justify-content: space-between;
            gap: 12px;
            padding: 18px 18px 12px;
        }

        .modal-icon {
            width: 44px;
            height: 44px;
            border-radius: 14px;
            display: inline-flex;
            align-items: center;
            justify-content: center;
            background: linear-gradient(135deg, #fef2f2, #fee2e2);
            color: var(--danger);
            font-size: 1rem;
            font-weight: 700;
            flex-shrink: 0;
        }

        .modal-title-wrap {
            flex: 1;
            min-width: 0;
        }

        .modal-title {
            font-size: 1rem;
            font-weight: 700;
            letter-spacing: -0.02em;
            color: var(--text);
        }

        .modal-subtitle {
            margin-top: 4px;
            font-size: 0.8rem;
            color: var(--text-secondary);
            line-height: 1.5;
        }

        .modal-close {
            width: 34px;
            height: 34px;
            border: 1px solid var(--border);
            border-radius: 10px;
            background: rgba(255,255,255,0.92);
            color: var(--text-secondary);
            font-size: 0.9rem;
            font-weight: 700;
            cursor: pointer;
            flex-shrink: 0;
        }

        .modal-body {
            padding: 0 18px 18px;
        }

        .modal-card {
            padding: 12px;
            border: 1px solid #eef2f7;
            border-radius: 14px;
            background: rgba(255,255,255,0.92);
        }

        .modal-device {
            font-size: 0.92rem;
            font-weight: 700;
            color: var(--text);
            word-break: break-word;
        }

        .modal-user {
            margin-top: 3px;
            font-size: 0.76rem;
            color: var(--text-secondary);
        }

        .modal-meta {
            margin-top: 12px;
            display: grid;
            gap: 8px;
        }

        .modal-meta-row {
            display: flex;
            justify-content: space-between;
            gap: 12px;
            align-items: flex-start;
        }

        .modal-meta-label {
            font-size: 0.72rem;
            font-weight: 600;
            color: var(--text-tertiary);
            text-transform: uppercase;
            letter-spacing: 0.04em;
            flex-shrink: 0;
        }

        .modal-meta-value {
            font-size: 0.77rem;
            font-weight: 600;
            color: var(--text);
            text-align: right;
            word-break: break-word;
        }

        .modal-warning {
            margin-top: 14px;
            padding: 10px 12px;
            border: 1px solid #fde68a;
            border-radius: 12px;
            background: #fffbeb;
            color: #92400e;
            font-size: 0.76rem;
            line-height: 1.5;
        }

        .modal-error {
            margin-top: 12px;
            padding: 10px 12px;
            border: 1px solid #fecaca;
            border-radius: 12px;
            background: var(--danger-light);
            color: var(--danger);
            font-size: 0.76rem;
            line-height: 1.45;
        }

        .modal-actions {
            display: flex;
            gap: 10px;
            margin-top: 16px;
        }

        .modal-actions .btn {
            flex: 1;
        }

        .btn-danger {
            background: linear-gradient(135deg, #dc2626, #b91c1c);
            color: #fff;
            box-shadow: 0 12px 22px rgba(220, 38, 38, 0.18);
        }

        .btn-danger:disabled {
            box-shadow: none;
        }

        /* Larger screens */
        @media (min-width: 640px) {
            .container {
                padding: 20px;
            }

            .stats-grid {
                grid-template-columns: repeat(4, 1fr);
            }

            .device-metrics {
                grid-template-columns: repeat(3, 1fr);
            }

            .device-metric.full {
                grid-column: auto;
            }
        }
    </style>
</head>
<body>
    <div class="container">
        <!-- Header -->
        <div class="header">
            <div class="logo-icon">
                <svg viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
                    <path d="M12 18.5a1.35 1.35 0 1 1 0-2.7 1.35 1.35 0 0 1 0 2.7Z" fill="#ffffff"/>
                    <path d="M8.2 13.9a5.3 5.3 0 0 1 7.6 0" stroke="#ffffff" stroke-width="1.8" stroke-linecap="round"/>
                    <path d="M5.1 10.7a9.7 9.7 0 0 1 13.8 0" stroke="#ffffff" stroke-width="1.8" stroke-linecap="round"/>
                </svg>
            </div>
            <span class="logo-text">FLINT <span>WiFi</span></span>
            <span class="user-chip inactive" id="hero-badge">
                <span class="status-dot idle"></span>
                No user
            </span>
        </div>

        <!-- Voucher Search -->
        <div class="search-section">
            <form class="search-form" id="user-lookup-form">
                <div class="search-heading">Find another voucher</div>
                <div class="search-help">Enter its username and password to view the same account details.</div>
                <input class="search-input" id="lookup-username" name="username" type="text" autocomplete="username" placeholder="Username" aria-label="Voucher username" required>
                <div class="password-field">
                    <input class="search-input" id="lookup-password" name="password" type="password" autocomplete="current-password" placeholder="Password" aria-label="Voucher password" required>
                    <button class="password-toggle" id="password-toggle" type="button" aria-label="Show password" aria-pressed="false">Show</button>
                </div>
                <button id="lookup-button" class="btn btn-primary" type="submit">Search</button>
            </form>
        </div>

        <!-- Session Access -->
        <div class="session-section">
            <div class="session-bar">
                <div class="session-copy">
                    <div class="session-title">Voucher Details</div>
                    <div class="session-username" id="locked-username">__LOCKED_USERNAME_DISPLAY__</div>
                    <div class="session-note" id="locked-note">__LOCKED_ACCESS_MESSAGE__</div>
                </div>
                <button id="refresh-button" class="btn btn-outline" type="button">Refresh</button>
            </div>
        </div>

        <!-- Status Bar -->
        <div class="status-bar" id="status-indicator">
            <span class="status-dot idle"></span>
            <span>Waiting for locked hotspot session</span>
        </div>

        <!-- Stats -->
        <div class="stats-grid">
            <div class="stat-card">
                <div class="stat-label">Data Used</div>
                <div class="stat-value" id="total-data-used">--</div>
            </div>
            <div class="stat-card">
                <div class="stat-label">Data Left</div>
                <div class="stat-value" id="total-data-left">--</div>
            </div>
            <div class="stat-card">
                <div class="stat-label">Plan</div>
                <div class="stat-value accent" id="profile-value">--</div>
            </div>
            <div class="stat-card">
                <div class="stat-label">Devices</div>
                <div class="stat-value" id="connected-devices-count">--</div>
            </div>
        </div>

        <!-- Panels -->
        <div class="panels">
            <!-- Account Details -->
            <div class="panel">
                <div class="panel-header">
                    <h2 class="panel-title">Account</h2>
                    <span class="panel-badge" id="overview-pill">Idle</span>
                </div>
                <div class="info-list">
                    <div class="info-row">
                        <span class="info-key">Username</span>
                        <span class="info-value" id="detail-username">--</span>
                    </div>
                    <div class="info-row">
                        <span class="info-key">Login</span>
                        <span class="info-value" id="logged-in-date">--</span>
                    </div>
                    <div class="info-row">
                        <span class="info-key">Expiry</span>
                        <span class="info-value" id="expiry-date">--</span>
                    </div>
                    <div class="info-row">
                        <span class="info-key">Data Limit</span>
                        <span class="info-value" id="data-limit">--</span>
                    </div>
                </div>
                <div class="footer-note" id="last-updated">No data</div>
            </div>

            <!-- Devices -->
            <div class="panel">
                <div class="panel-header">
                    <h2 class="panel-title">Devices</h2>
                    <span class="panel-badge" id="devices-pill">0</span>
                </div>
                <div class="devices-container" id="devices-root">
                    <div class="empty-state">Open this page from the hotspot status page to view devices</div>
                </div>
            </div>
        </div>

        <div class="page-footer">Powered by FlintWiFi</div>
    </div>

    <div class="loading-overlay" id="loading-overlay" role="status" aria-live="polite" aria-busy="true" hidden>
        <div class="loading-card">
            <div class="loading-spinner" aria-hidden="true"></div>
            <div class="loading-title" id="loading-title">Loading voucher details</div>
            <div class="loading-message" id="loading-message">Please be patient. Contacting the router can sometimes take a little while.</div>
            <div class="loading-progress" aria-hidden="true"></div>
        </div>
    </div>

    <div class="modal-backdrop" id="logout-modal" hidden>
        <div class="modal" role="dialog" aria-modal="true" aria-labelledby="logout-modal-title">
            <div class="modal-header">
                <div class="modal-icon">!</div>
                <div class="modal-title-wrap">
                    <div class="modal-title" id="logout-modal-title">Confirm device logout</div>
                    <div class="modal-subtitle">
                        This will immediately disconnect the selected device from the hotspot session.
                    </div>
                </div>
                <button type="button" class="modal-close" id="logout-modal-close" aria-label="Close confirmation">x</button>
            </div>
            <div class="modal-body">
                <div class="modal-card">
                    <div class="modal-device" id="logout-modal-device">Unknown device</div>
                    <div class="modal-user" id="logout-modal-user">User: --</div>
                    <div class="modal-meta">
                        <div class="modal-meta-row">
                            <span class="modal-meta-label">Session</span>
                            <span class="modal-meta-value" id="logout-modal-session">--</span>
                        </div>
                        <div class="modal-meta-row">
                            <span class="modal-meta-label">IP address</span>
                            <span class="modal-meta-value" id="logout-modal-ip">--</span>
                        </div>
                        <div class="modal-meta-row">
                            <span class="modal-meta-label">MAC address</span>
                            <span class="modal-meta-value" id="logout-modal-mac">--</span>
                        </div>
                    </div>
                </div>
                <div class="modal-warning">
                    The device will need to authenticate again before it can reconnect.
                </div>
                <div class="modal-error" id="logout-modal-error" hidden></div>
                <div class="modal-actions">
                    <button type="button" class="btn btn-outline" id="logout-modal-cancel">Cancel</button>
                    <button type="button" class="btn btn-danger" id="logout-modal-confirm">Confirm logout</button>
                </div>
            </div>
        </div>
    </div>

    <script>
        const INITIAL_USERNAME = resolveInitialUsername(__INITIAL_USERNAME_JSON__);
        const CURRENT_DEVICE_IP = normalizeIpAddress(__CURRENT_DEVICE_IP_JSON__);
        const CURRENT_DEVICE_MAC = normalizeMacAddress(__CURRENT_DEVICE_MAC_JSON__);
        const lookupFormEl = document.getElementById('user-lookup-form');
        const lookupUsernameEl = document.getElementById('lookup-username');
        const lookupPasswordEl = document.getElementById('lookup-password');
        const passwordToggleEl = document.getElementById('password-toggle');
        const lookupButtonEl = document.getElementById('lookup-button');
        const refreshButtonEl = document.getElementById('refresh-button');
        const lockedUsernameEl = document.getElementById('locked-username');
        const lockedNoteEl = document.getElementById('locked-note');
        const heroBadgeEl = document.getElementById('hero-badge');
        const statusIndicatorEl = document.getElementById('status-indicator');
        const totalDataUsedEl = document.getElementById('total-data-used');
        const totalDataLeftEl = document.getElementById('total-data-left');
        const profileValueEl = document.getElementById('profile-value');
        const connectedDevicesCountEl = document.getElementById('connected-devices-count');
        const detailUsernameEl = document.getElementById('detail-username');
        const loggedInDateEl = document.getElementById('logged-in-date');
        const expiryDateEl = document.getElementById('expiry-date');
        const dataLimitEl = document.getElementById('data-limit');
        const overviewPillEl = document.getElementById('overview-pill');
        const lastUpdatedEl = document.getElementById('last-updated');
        const devicesRootEl = document.getElementById('devices-root');
        const devicesPillEl = document.getElementById('devices-pill');
        const loadingOverlayEl = document.getElementById('loading-overlay');
        const loadingTitleEl = document.getElementById('loading-title');
        const loadingMessageEl = document.getElementById('loading-message');
        const logoutModalEl = document.getElementById('logout-modal');
        const logoutModalCloseEl = document.getElementById('logout-modal-close');
        const logoutModalCancelEl = document.getElementById('logout-modal-cancel');
        const logoutModalConfirmEl = document.getElementById('logout-modal-confirm');
        const logoutModalDeviceEl = document.getElementById('logout-modal-device');
        const logoutModalUserEl = document.getElementById('logout-modal-user');
        const logoutModalSessionEl = document.getElementById('logout-modal-session');
        const logoutModalIpEl = document.getElementById('logout-modal-ip');
        const logoutModalMacEl = document.getElementById('logout-modal-mac');
        const logoutModalErrorEl = document.getElementById('logout-modal-error');

        let activeUsername = INITIAL_USERNAME;
        let activePassword = '';
        let isLookupResult = false;
        let isLoading = false;
        let longLoadingTimer = null;
        let pendingLogout = null;

        initializePage();

        function initializePage() {
            bindEvents();
            if (INITIAL_USERNAME) {
                loadStatus(INITIAL_USERNAME);
                return;
            }
            setIdleState();
        }

        function bindEvents() {
            passwordToggleEl.addEventListener('click', () => {
                const shouldShowPassword = lookupPasswordEl.type === 'password';
                lookupPasswordEl.type = shouldShowPassword ? 'text' : 'password';
                passwordToggleEl.textContent = shouldShowPassword ? 'Hide' : 'Show';
                passwordToggleEl.setAttribute(
                    'aria-label',
                    shouldShowPassword ? 'Hide password' : 'Show password'
                );
                passwordToggleEl.setAttribute('aria-pressed', String(shouldShowPassword));
                lookupPasswordEl.focus();
            });

            lookupFormEl.addEventListener('submit', (event) => {
                event.preventDefault();
                const username = normalizeText(lookupUsernameEl.value);
                const password = lookupPasswordEl.value;
                if (!username || !password || isLoading) return;
                loadStatus(username, password);
            });

            refreshButtonEl.addEventListener('click', () => {
                if (!activeUsername) return;
                loadStatus(activeUsername, activePassword);
            });

            logoutModalCloseEl.addEventListener('click', closeLogoutModal);
            logoutModalCancelEl.addEventListener('click', closeLogoutModal);
            logoutModalConfirmEl.addEventListener('click', confirmLogout);

            logoutModalEl.addEventListener('click', (event) => {
                if (event.target === logoutModalEl) {
                    closeLogoutModal();
                }
            });

            document.addEventListener('keydown', (event) => {
                if (event.key === 'Escape' && !logoutModalEl.hidden) {
                    closeLogoutModal();
                }
            });
        }

        async function loadStatus(username, password = '') {
            const normalizedUsername = normalizeText(username);
            if (!normalizedUsername || isLoading) return;

            activeUsername = normalizedUsername;
            activePassword = password;
            isLookupResult = Boolean(password);
            setLoadingState(normalizedUsername, isLookupResult);

            try {
                const response = isLookupResult
                    ? await fetch('/api/hotspot/user-lookup', {
                        method: 'POST',
                        headers: {
                            'Accept': 'application/json',
                            'Content-Type': 'application/json'
                        },
                        body: JSON.stringify({ username: normalizedUsername, password: password })
                    })
                    : await fetch('/api/hotspot/users/' + encodeURIComponent(normalizedUsername) + '/status', {
                        method: 'GET',
                        headers: { 'Accept': 'application/json' }
                    });

                if (!response.ok) {
                    throw new Error(await extractError(response));
                }

                const payload = await response.json();
                renderPayload(payload);
                lookupPasswordEl.value = '';
            } catch (error) {
                renderError(normalizedUsername, error.message || 'Failed to load');
            } finally {
                isLoading = false;
                hideLoadingIndicator();
                refreshButtonEl.disabled = false;
                lookupButtonEl.disabled = false;
            }
        }

        function renderPayload(payload) {
            const username = normalizeText(payload.username) || activeUsername || 'Unknown';
            activeUsername = username;
            
            // Update badge
            heroBadgeEl.innerHTML = '<span class="status-dot active"></span>' + escapeHtml(username);
            heroBadgeEl.className = 'user-chip';
            heroBadgeEl.title = username;
            lockedUsernameEl.textContent = username;
            lockedUsernameEl.className = 'session-username';
            lockedNoteEl.textContent = isLookupResult
                ? 'Voucher details were verified with the supplied username and password.'
                : 'Voucher details are locked to your current hotspot session.';
            if (isLookupResult) lookupUsernameEl.value = username;
            
            // Stats
            totalDataUsedEl.textContent = payload.total_data_used || '0 B';
            totalDataLeftEl.textContent = payload.total_data_left || 'Unlimited';
            profileValueEl.textContent = normalizeText(payload.profile) || 'None';
            connectedDevicesCountEl.textContent = String(payload.connected_devices_count || 0);
            
            // Account details
            detailUsernameEl.textContent = username;
            loggedInDateEl.textContent = normalizeText(payload.logged_in_date) || 'N/A';
            expiryDateEl.textContent = normalizeText(payload.expiry_date) || 'N/A';
            dataLimitEl.textContent = formatLimit(payload.data_limit_bytes);
            
            // Status indicators
            overviewPillEl.textContent = 'Active';
            overviewPillEl.className = 'panel-badge active';
            devicesPillEl.textContent = String(payload.connected_devices_count || 0) + ' dev';
            statusIndicatorEl.innerHTML = '<span class="status-dot active"></span><span>' + escapeHtml(username) + ' loaded</span>';
            lastUpdatedEl.textContent = formatTime(new Date());
            
            renderDevices(payload.connected_devices || []);
        }

        function renderDevices(devices) {
            if (!devices.length) {
                devicesRootEl.innerHTML = '<div class="empty-state">No active devices</div>';
                return;
            }

            devicesRootEl.innerHTML = devices.map((device) => {
                const deviceName = escapeHtml(normalizeText(device.device_name) || 'Unknown');
                const sessionId = escapeHtml(normalizeText(device.session_id) || 'N/A');
                const ipAddress = escapeHtml(normalizeText(device.ip_address) || 'N/A');
                const macAddress = escapeHtml(normalizeText(device.mac_address) || 'N/A');
                const uptime = escapeHtml(normalizeText(device.uptime) || 'N/A');
                const rawDeviceName = escapeHtml(normalizeText(device.device_name) || 'Unknown');
                const rawSessionId = escapeHtml(normalizeText(device.session_id) || '');
                const rawMacAddress = escapeHtml(normalizeText(device.mac_address) || '');
                const rawIpAddress = escapeHtml(normalizeText(device.ip_address) || '');
                const currentDeviceBadge = isCurrentSessionDevice(device)
                    ? '<span class="device-status current">This device</span>'
                    : '';

                return (
                    '<div class="device-item">' +
                        '<div class="device-top">' +
                            '<div>' +
                                '<div class="device-name">' + deviceName + '</div>' +
                                '<div class="device-session">' + sessionId + '</div>' +
                            '</div>' +
                            '<div class="device-badges">' +
                                currentDeviceBadge +
                                '<span class="device-status">Active</span>' +
                            '</div>' +
                        '</div>' +
                        '<div class="device-metrics">' +
                            '<div class="device-metric">' +
                                '<div class="device-metric-label">IP</div>' +
                                '<div class="device-metric-value">' + ipAddress + '</div>' +
                            '</div>' +
                            '<div class="device-metric">' +
                                '<div class="device-metric-label">MAC</div>' +
                                '<div class="device-metric-value">' + macAddress + '</div>' +
                            '</div>' +
                            '<div class="device-metric full">' +
                                '<div class="device-metric-label">Uptime</div>' +
                                '<div class="device-metric-value">' + uptime + '</div>' +
                            '</div>' +
                        '</div>' +
                        '<div class="device-action">' +
                            '<button class="btn-logout" data-device-name="' + rawDeviceName + '" data-session-id="' + rawSessionId + '" data-mac-address="' + rawMacAddress + '" data-ip-address="' + rawIpAddress + '">Logout</button>' +
                        '</div>' +
                    '</div>'
                );
            }).join('');

            devicesRootEl.querySelectorAll('.btn-logout').forEach((buttonEl) => {
                buttonEl.addEventListener('click', () => {
                    requestLogout(
                        buttonEl.dataset.deviceName || 'Unknown device',
                        buttonEl.dataset.sessionId || '',
                        buttonEl.dataset.macAddress || '',
                        buttonEl.dataset.ipAddress || '',
                        buttonEl
                    );
                });
            });
        }

        function isCurrentSessionDevice(device) {
            const deviceIp = normalizeIpAddress(device.ip_address);
            const deviceMac = normalizeMacAddress(device.mac_address);
            return Boolean(
                (CURRENT_DEVICE_IP && deviceIp === CURRENT_DEVICE_IP) ||
                (CURRENT_DEVICE_MAC && deviceMac === CURRENT_DEVICE_MAC)
            );
        }

        function normalizeIpAddress(value) {
            let normalized = normalizeText(value).toLowerCase();
            if (normalized.startsWith('::ffff:')) normalized = normalized.slice(7);
            if (normalized.startsWith('[') && normalized.includes(']')) {
                normalized = normalized.slice(1, normalized.indexOf(']'));
            }
            return normalized.split('%', 1)[0];
        }

        function normalizeMacAddress(value) {
            return normalizeText(value).toUpperCase().replace(/[^0-9A-F]/g, '');
        }

        function requestLogout(deviceName, sessionId, macAddress, ipAddress, buttonEl) {
            if (!activeUsername || !sessionId) return;

            pendingLogout = {
                deviceName: normalizeText(deviceName) || 'Unknown device',
                username: activeUsername,
                sessionId: normalizeText(sessionId),
                macAddress: normalizeText(macAddress),
                ipAddress: normalizeText(ipAddress),
                buttonEl: buttonEl || null
            };

            logoutModalDeviceEl.textContent = pendingLogout.deviceName;
            logoutModalUserEl.textContent = 'User: ' + pendingLogout.username;
            logoutModalSessionEl.textContent = pendingLogout.sessionId || '--';
            logoutModalIpEl.textContent = pendingLogout.ipAddress || 'N/A';
            logoutModalMacEl.textContent = pendingLogout.macAddress || 'N/A';
            logoutModalErrorEl.hidden = true;
            logoutModalErrorEl.textContent = '';
            logoutModalConfirmEl.disabled = false;
            logoutModalCancelEl.disabled = false;
            logoutModalCloseEl.disabled = false;
            logoutModalConfirmEl.textContent = 'Confirm logout';
            logoutModalEl.hidden = false;
            logoutModalConfirmEl.focus();
        }

        function closeLogoutModal(forceClose) {
            if (!forceClose && !logoutModalEl.hidden && logoutModalConfirmEl.disabled) return;

            logoutModalEl.hidden = true;
            logoutModalErrorEl.hidden = true;
            logoutModalErrorEl.textContent = '';
            logoutModalConfirmEl.textContent = 'Confirm logout';
            pendingLogout = null;
        }

        async function confirmLogout() {
            if (!pendingLogout) return;

            await logoutDevice(
                pendingLogout.sessionId,
                pendingLogout.macAddress,
                pendingLogout.ipAddress,
                pendingLogout.buttonEl
            );
        }

        async function logoutDevice(sessionId, macAddress, ipAddress, buttonEl) {
            if (!activeUsername) return;

            const originalLabel = buttonEl ? buttonEl.textContent : 'Logout';
            if (buttonEl) {
                buttonEl.disabled = true;
                buttonEl.textContent = '...';
            }

            logoutModalErrorEl.hidden = true;
            logoutModalErrorEl.textContent = '';
            logoutModalConfirmEl.disabled = true;
            logoutModalCancelEl.disabled = true;
            logoutModalCloseEl.disabled = true;
            logoutModalConfirmEl.textContent = 'Logging out...';

            try {
                const requestUrl = new URL(
                    '/api/hotspot/users/' +
                    encodeURIComponent(activeUsername) +
                    '/devices/' +
                    encodeURIComponent(sessionId || 'lookup') +
                    '/logout',
                    window.location.origin
                );

                if (macAddress) requestUrl.searchParams.set('mac_address', macAddress);
                if (ipAddress) requestUrl.searchParams.set('ip_address', ipAddress);

                const response = await fetch(requestUrl.toString(), {
                    method: 'POST',
                    headers: { 'Accept': 'application/json' }
                });

                if (!response.ok) {
                    throw new Error(await extractError(response));
                }

                closeLogoutModal(true);
                await loadStatus(activeUsername, activePassword);
            } catch (error) {
                if (buttonEl) {
                    buttonEl.disabled = false;
                    buttonEl.textContent = originalLabel;
                }

                logoutModalConfirmEl.disabled = false;
                logoutModalCancelEl.disabled = false;
                logoutModalCloseEl.disabled = false;
                logoutModalConfirmEl.textContent = 'Try again';
                logoutModalErrorEl.hidden = false;
                logoutModalErrorEl.textContent = error.message || 'Logout failed';
            }
        }

        function renderError(username, message) {
            heroBadgeEl.innerHTML = '<span class="status-dot error"></span>' + escapeHtml(username || 'Error');
            heroBadgeEl.className = 'user-chip';
            lockedUsernameEl.textContent = username || 'Unavailable';
            lockedUsernameEl.className = 'session-username';
            lockedNoteEl.textContent = isLookupResult
                ? 'The supplied voucher credentials could not be verified.'
                : 'The voucher session is locked, but the details could not be loaded right now.';
            detailUsernameEl.textContent = username || '--';
            totalDataUsedEl.textContent = '--';
            totalDataLeftEl.textContent = '--';
            profileValueEl.textContent = '--';
            connectedDevicesCountEl.textContent = '--';
            loggedInDateEl.textContent = '--';
            expiryDateEl.textContent = '--';
            dataLimitEl.textContent = '--';
            overviewPillEl.textContent = 'Error';
            overviewPillEl.className = 'panel-badge error';
            devicesPillEl.textContent = '0';
            statusIndicatorEl.innerHTML = '<span class="status-dot error"></span><span>Load failed</span>';
            lastUpdatedEl.textContent = 'Failed';
            devicesRootEl.innerHTML = '<div class="empty-state error">' + escapeHtml(message || 'Could not load') + '</div>';
            if (isLookupResult) lookupPasswordEl.focus();
        }

        function setIdleState() {
            activeUsername = '';
            heroBadgeEl.innerHTML = '<span class="status-dot idle"></span>No user';
            heroBadgeEl.className = 'user-chip inactive';
            lockedUsernameEl.textContent = 'Waiting for hotspot session';
            lockedUsernameEl.className = 'session-username empty';
            lockedNoteEl.textContent = 'Open this page from your hotspot status page, or search with voucher credentials.';
            detailUsernameEl.textContent = '--';
            totalDataUsedEl.textContent = '--';
            totalDataLeftEl.textContent = '--';
            profileValueEl.textContent = '--';
            connectedDevicesCountEl.textContent = '--';
            loggedInDateEl.textContent = '--';
            expiryDateEl.textContent = '--';
            dataLimitEl.textContent = '--';
            overviewPillEl.textContent = 'Idle';
            overviewPillEl.className = 'panel-badge';
            devicesPillEl.textContent = '0';
            statusIndicatorEl.innerHTML = '<span class="status-dot idle"></span><span>Waiting for a hotspot session or voucher search</span>';
            lastUpdatedEl.textContent = 'No data';
            devicesRootEl.innerHTML = '<div class="empty-state">Open this page from the hotspot status page to view devices</div>';
            refreshButtonEl.disabled = true;
        }

        function setLoadingState(username, fromLookup) {
            isLoading = true;
            showLoadingIndicator(fromLookup);
            refreshButtonEl.disabled = true;
            lookupButtonEl.disabled = true;
            heroBadgeEl.innerHTML = '<span class="status-dot loading"></span>' + escapeHtml(username);
            heroBadgeEl.className = 'user-chip';
            lockedUsernameEl.textContent = username;
            lockedUsernameEl.className = 'session-username';
            lockedNoteEl.textContent = fromLookup
                ? 'Verifying the voucher credentials and loading its details.'
                : 'Loading the locked voucher details for this hotspot user.';
            overviewPillEl.textContent = '...';
            devicesPillEl.textContent = '...';
            statusIndicatorEl.innerHTML = '<span class="status-dot loading"></span><span>Loading...</span>';
            lastUpdatedEl.textContent = 'Loading...';
            devicesRootEl.innerHTML = '<div class="empty-state">Loading...</div>';
        }

        function showLoadingIndicator(fromLookup) {
            if (longLoadingTimer) window.clearTimeout(longLoadingTimer);
            loadingTitleEl.textContent = fromLookup
                ? 'Verifying voucher details'
                : 'Loading voucher details';
            loadingMessageEl.textContent = 'Please be patient. Contacting the router can sometimes take a little while.';
            loadingOverlayEl.hidden = false;
            longLoadingTimer = window.setTimeout(() => {
                loadingTitleEl.textContent = 'Still working on it';
                loadingMessageEl.textContent = 'The router is taking longer than usual to respond. Please keep this page open.';
            }, 6000);
        }

        function hideLoadingIndicator() {
            if (longLoadingTimer) window.clearTimeout(longLoadingTimer);
            longLoadingTimer = null;
            loadingOverlayEl.hidden = true;
        }

        async function extractError(response) {
            try {
                const payload = await response.json();
                return payload.detail || 'Request failed';
            } catch (error) {
                return 'Request failed';
            }
        }

        function normalizeText(value) {
            return String(value || '').trim();
        }

        function resolveInitialUsername(serverUsername) {
            return normalizeText(serverUsername);
        }

        function formatLimit(value) {
            if (value === null || value === undefined) return 'Unlimited';
            return formatBytes(value);
        }

        function formatTime(date) {
            const now = new Date();
            const diff = Math.floor((now - date) / 1000);
            if (diff < 60) return 'Just now';
            if (diff < 3600) return Math.floor(diff / 60) + 'm ago';
            return date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
        }

        function formatBytes(bytes) {
            let value = Number(bytes || 0);
            if (!Number.isFinite(value) || value < 0) value = 0;

            const units = ['B', 'KB', 'MB', 'GB', 'TB'];
            let unitIndex = 0;
            while (value >= 1024 && unitIndex < units.length - 1) {
                value /= 1024;
                unitIndex += 1;
            }

            if (unitIndex === 0) return Math.round(value) + ' ' + units[unitIndex];
            return value.toFixed(1) + ' ' + units[unitIndex];
        }

        function escapeHtml(value) {
            return String(value)
                .replace(/&/g, '&amp;')
                .replace(/</g, '&lt;')
                .replace(/>/g, '&gt;')
                .replace(/"/g, '&quot;')
                .replace(/'/g, '&#39;');
        }
    </script>
</body>
</html>
""".replace("__INITIAL_USERNAME_ATTR__", html_username).replace(
        "__INITIAL_USERNAME_JSON__", json_username
    ).replace(
        "__CURRENT_DEVICE_IP_JSON__", json_current_device_ip
    ).replace(
        "__CURRENT_DEVICE_MAC_JSON__", json_current_device_mac
    ).replace(
        "__LOCKED_USERNAME_DISPLAY__", locked_username
    ).replace(
        "__LOCKED_ACCESS_MESSAGE__", locked_message
    )
