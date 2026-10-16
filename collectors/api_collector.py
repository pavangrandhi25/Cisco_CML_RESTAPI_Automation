"""Collect Cisco CML lab, topology, and IPv4 details into one JSON report."""

import json
import os
import re
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import requests
import urllib3
from dotenv import load_dotenv

PROJECT_DIR = Path(__file__).resolve().parent.parent
REPORT_FILE = PROJECT_DIR / "reports" / "cml_inventory.json"
load_dotenv(PROJECT_DIR / ".env")

# ---------- API requests ----------
def generate_token(base_url, username, password, verify_ssl, timeout):
    response = requests.post(
        f"{base_url}/authenticate",
        json={"username": username, "password": password},
        timeout=timeout,
        verify=verify_ssl,
    )
    response.raise_for_status()

    token_data = response.json()
    token = token_data if isinstance(token_data, str) else token_data.get("token")
    if not token:
        raise ValueError("CML did not return an authentication token")
    return token

def get_request(url, token, verify_ssl, timeout):
    response = requests.get(
        url,
        headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
        timeout=timeout,
        verify=verify_ssl,
    )
    response.raise_for_status()
    return response.json()

# ---------- JSON parsers ----------
def parse_lab_details(data):
    return {
        "lab_title": data["lab_title"],
        "lab_description": data.get("lab_description", ""),
        "node_count": data["node_count"],
        "link_count": data["link_count"],
    }

def parse_topology(data):
    nodes = []

    for node in data.get("nodes", []):
        if node.get("node_definition") == "external_connector":
            continue

        port = None
        for tag in node.get("tags", []):
            match = re.fullmatch(r"pat:(\d+):22", tag)
            if match:
                port = int(match.group(1))
                break

        nodes.append({
            "id": node["id"],  # Used internally to match API responses
            "device": node["label"],
            "node_definition": node["node_definition"],
            "port": port,
            "interfaces": [
                {"id": iface["id"], "interface": iface["label"]}
                for iface in node.get("interfaces", [])
                if iface.get("type") == "physical"
            ],
        })

    return nodes

def parse_ip_addresses(data):
    addresses = {}
    for node_id, node in data.items():
        addresses[node_id] = {}
        for iface in node.get("interfaces", {}).values():
            ip_list = iface.get("ip4", [])
            addresses[node_id][iface["id"]] = ip_list[0] if ip_list else "unassigned"
    return addresses

def build_inventory(lab_data, topology_data, ip_data):
    inventory = parse_lab_details(lab_data)
    addresses = parse_ip_addresses(ip_data)
    inventory["nodes"] = []
    for node in parse_topology(topology_data):
        interface_ips = addresses.get(node["id"], {})
        inventory["nodes"].append({
            "device": node["device"],
            "node_definition": node["node_definition"],
            "port": node["port"],
            "interfaces": [
                {
                    "interface": iface["interface"],
                    "ip": interface_ips.get(iface["id"], "unavailable"),
                }
                for iface in node["interfaces"]
            ],
        })
    return inventory

# ---------- Collect and save ----------
def collect_inventory():
    base_url = os.getenv("CML_BASE_URL", "").rstrip("/")
    lab_id = os.getenv("CML_LAB_ID", "")
    username = os.getenv("CML_USERNAME", "")
    password = os.getenv("CML_PASSWORD", "")
    verify_ssl = os.getenv("CML_VERIFY_SSL", "true").lower() == "true"
    timeout = float(os.getenv("CML_TIMEOUT", "10"))

    if not all((base_url, lab_id, username, password)):
        raise ValueError("Set CML_BASE_URL, CML_LAB_ID, CML_USERNAME and CML_PASSWORD in .env")

    if not verify_ssl:
        urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

    token = generate_token(base_url, username, password, verify_ssl, timeout)
    
    endpoints = {
        "lab_details": f"{base_url}/labs/{lab_id}",
        "topology": f"{base_url}/labs/{lab_id}/topology?exclude_configurations=true",
        "ip_addresses": f"{base_url}/labs/{lab_id}/layer3_addresses",
    }

    with ThreadPoolExecutor(max_workers=3) as executor:
        futures = {
            name: executor.submit(get_request, url, token, verify_ssl, timeout)
            for name, url in endpoints.items()
        }
        responses = {name: future.result() for name, future in futures.items()}

    inventory = build_inventory(
        responses["lab_details"],
        responses["topology"],
        responses["ip_addresses"],
    )

    REPORT_FILE.parent.mkdir(parents=True, exist_ok=True)
    REPORT_FILE.write_text(json.dumps(inventory, indent=4), encoding="utf-8")
    return inventory


def main():
    inventory = collect_inventory()
    print(json.dumps(inventory, indent=4))
    print(f"\nSaved report to: {REPORT_FILE}")

if __name__ == "__main__":
    main()
