"""Conditional transfer mutations run on RouterOS, never cleanup by username alone."""

import re

from routeros_api.exceptions import RouterOsApiError

from app.integrations.mikrotik.client import _HOTSPOT_USER_TRANSFER_FIELDS, _parse_routeros_duration


def _literal(value: object) -> str:
    # Encode every byte: quotes, backslashes, dollar substitutions and newlines
    # from a username/comment/password cannot become RouterOS script syntax.
    return '"' + "".join(f"\\{byte:02X}" for byte in str(value).encode("utf-8")) + '"'


def guarded_script(
    expected: dict[str, str], *, comment=None, disabled=None, remove=False, settle=False
) -> str:
    item_id = str(expected.get("id") or "")
    if not re.fullmatch(r"\*[0-9A-Fa-f]+", item_id):
        raise ValueError("A confirmed RouterOS user ID is required.")
    if remove and (comment is not None or disabled is not None):
        raise ValueError("Removal cannot change account settings.")
    checks = [f"([/ip hotspot user get $transferId name] = {_literal(expected['name'])})"]
    fields = set(_HOTSPOT_USER_TRANSFER_FIELDS) | (
        {"bytes-in", "bytes-out", "uptime"} if remove else set()
    )
    for field in sorted(fields):
        if field == "name" or field not in expected:
            continue
        value = expected[field]
        if field == "disabled":
            rhs = "true" if str(value).lower() in {"yes", "true", "1"} else "false"
            lhs = f"[/ip hotspot user get $transferId {field}]"
        elif field in {"limit-uptime", "uptime"}:
            rhs = f"[:totime {_literal(str(_parse_routeros_duration(value)) + 's')}]"
            lhs = f"[/ip hotspot user get $transferId {field}]"
        else:
            rhs = _literal(value)
            lhs = f"[:tostr [/ip hotspot user get $transferId {field}]]"
        checks.append(f"({lhs} = {rhs})")
    command = f"/ip hotspot user {'remove' if remove else 'set'} $transferId"
    if comment is not None:
        command += f" comment={_literal(comment)}"
    if disabled is not None:
        command += f" disabled={'yes' if disabled else 'no'}"
    if settle:
        if remove or not str(expected.get("disabled")).lower() in {"yes", "true", "1"}:
            raise ValueError("Only a frozen transfer account can settle authentication.")
        command = (
            f"/ip hotspot active remove [find where user={_literal(expected['name'])}]; "
            f"/ip hotspot cookie remove [find where user={_literal(expected['name'])}]"
        )
    return (
        f":local transferId {_literal(item_id)}; "
        f":if ({' && '.join(checks)}) do={{ {command}; }} "
        'else={ :error "Transfer account changed"; };'
    )


def mutate_transfer_user(
    client, expected, *, comment=None, disabled=None, remove=False, settle=False
):
    script = guarded_script(
        expected, comment=comment, disabled=disabled, remove=remove, settle=settle
    )
    # Synchronous execution is essential: a queued mutation could otherwise run
    # after a rollback/retry. Lost replies are reconciled from observed state.
    client.connect().get_resource("/").call("execute", {"script": script, "as-string": ""})
    observed = client.get_hotspot_user(expected["name"])
    if remove and observed is not None:
        raise RouterOsApiError("Transfer account removal was not confirmed.")
    return observed
