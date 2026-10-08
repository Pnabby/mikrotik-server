"""Fixed public messages; never expose raw RouterOS/database exceptions."""

TRANSFER_ERROR_DETAILS = {
    "hostel_both_routers_not_ready": "Both hostel router APIs need attention. No account changes were made.",
    "hostel_transfer_storage_unavailable": "The server could not record the move. No account changes were made. Please contact support.",
    "hostel_transfer_not_configured": "Hostel transfers need server configuration. No account changes were made. Please contact support.",
    "hostel_transfer_unconfirmed": "The move needs recovery before another attempt. Please contact support to check its progress.",
    "router_not_configured": "The router API connection is not configured. Please contact support.",
    "router_request_failed": "The router API rejected the requested operation. Please contact support.",
}

for _side, _label in (("source", "current hostel"), ("destination", "destination hostel")):
    for _reason, _message in {
        "unreachable": "could not be reached from the server",
        "authentication_failed": "did not accept the server's API credentials",
        "permission_denied": "denied the server permission to transfer accounts",
        "commands_unavailable": "does not support the required transfer commands",
        "request_failed": "could not complete the transfer checks",
        "not_configured": "is not configured for transfers",
    }.items():
        TRANSFER_ERROR_DETAILS[f"hostel_{_side}_router_{_reason}"] = (
            f"The {_label} router API {_message}. No account changes were made. Please contact support."
        )
