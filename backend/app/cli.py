from app.core.config import get_settings
from app.integrations.mikrotik.client import MikroTikClient, MikroTikConfig
from app.integrations.mikrotik.registry import DEFAULT_ROUTER_ID, UnknownRouterError, get_router


def _print_menu() -> None:
    print("Available actions:")
    print("1. Show router identity")
    print("2. List interfaces")
    print("3. Show active devices for a hotspot user")
    print("0. Exit")


def _format_bytes(num_bytes: int | None) -> str:
    if num_bytes is None:
        return "none"

    units = ["B", "KB", "MB", "GB", "TB"]
    value = float(num_bytes)
    unit = units[0]
    for unit in units:
        if value < 1024 or unit == units[-1]:
            break
        value /= 1024

    if unit == "B":
        return f"{int(value)} {unit}"
    return f"{value:.2f} {unit}"


def _print_user_usage_summary(summary: dict[str, int | str | None]) -> None:
    print("Usage summary:")
    print(f"  User Comment: {summary.get('user_comment') or 'none'}")
    print("  Cumulative User Usage So Far:")
    print(f"    Bytes In: {_format_bytes(summary.get('user_bytes_in'))}")
    print(f"    Bytes Out: {_format_bytes(summary.get('user_bytes_out'))}")
    print(f"    Total: {_format_bytes(summary.get('user_bytes_total'))}")
    print(
        "  Active Session Traffic Right Now: "
        f"in={_format_bytes(summary.get('active_bytes_in'))}, "
        f"out={_format_bytes(summary.get('active_bytes_out'))}, "
        f"total={_format_bytes(summary.get('active_bytes_total'))}"
    )
    print(
        "  Combined User + Active Session Traffic: "
        f"in={_format_bytes(summary.get('combined_bytes_in'))}, "
        f"out={_format_bytes(summary.get('combined_bytes_out'))}, "
        f"total={_format_bytes(summary.get('combined_bytes_total'))}"
    )
    print(f"  Total Bytes Used So Far: {_format_bytes(summary.get('combined_bytes_total'))}")
    print(
        "  Data Limit: "
        f"in={_format_bytes(summary.get('limit_bytes_in'))}, "
        f"out={_format_bytes(summary.get('limit_bytes_out'))}, "
        f"total={_format_bytes(summary.get('limit_bytes_total'))}"
    )


def _print_active_device(device: dict[str, str], index: int) -> None:
    print(f"Device {index}:")
    print(f"  Session ID: {device.get('id', 'unknown')}")
    print(f"  Device Name: {device.get('device-name', 'unknown')}")
    print(f"  Device Type: {device.get('device-type', 'Unknown')}")
    print(f"  IP Address: {device.get('address', 'unknown')}")
    print(f"  MAC Address: {device.get('mac-address', 'unknown')}")
    print(f"  Login By: {device.get('login-by', 'unknown')}")
    print(f"  Uptime: {device.get('uptime', 'unknown')}")
    print(f"  Server: {device.get('server', 'unknown')}")
    print(f"  Bytes In: {_format_bytes(int(device.get('bytes-in', '0')))}")
    print(f"  Bytes Out: {_format_bytes(int(device.get('bytes-out', '0')))}")
    print(f"  Total Session Traffic: {_format_bytes(int(device.get('bytes-total', '0')))}")
    print(f"  User Comment: {device.get('user-comment', 'none')}")


def main() -> None:
    router_id = get_settings().mikrotik_router_id or DEFAULT_ROUTER_ID
    try:
        router = get_router(router_id)
        config = MikroTikConfig.from_env(router)
    except UnknownRouterError:
        print("Router is not configured.")
        return
    except ValueError:
        print("Router service is not configured.")
        return

    print(f"Using router: {router.name} ({router.router_id})")
    try:
        with MikroTikClient(config) as client:
            while True:
                _print_menu()
                choice = input("Select an action: ").strip()

                if choice == "0":
                    print("Exiting.")
                    return

                if choice == "1":
                    identities = client.get_system_identity()
                    router_name = (
                        identities[0].get("name", "unknown") if identities else "unknown"
                    )
                    print(f"Router identity: {router_name}")
                    continue

                if choice == "2":
                    interfaces = client.get_interfaces()
                    print(f"Interfaces found: {len(interfaces)}")
                    for interface in interfaces:
                        print(interface.get("name", "unknown"))
                    continue

                if choice == "3":
                    username = input("Enter hotspot username: ").strip()
                    if not username:
                        print("Username is required.")
                        continue
                    devices = client.get_hotspot_active_devices(username)
                    usage_summary = client.get_hotspot_user_usage(username)
                    print(f"Active devices for {username}: {len(devices)}")
                    _print_user_usage_summary(usage_summary)
                    for index, device in enumerate(devices, start=1):
                        _print_active_device(device, index)
                    continue

                print("Invalid selection.")
    except Exception:
        print("Connection failed. Check the router service and try again.")


if __name__ == "__main__":
    main()
