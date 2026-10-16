"""Interactive dashboard for Cisco CML REST API inventory reports."""

import json
from pathlib import Path
import streamlit as st
from collectors.api_collector import REPORT_FILE, collect_inventory

PROJECT_DIR = Path(__file__).resolve().parent
SAMPLE_FILE = PROJECT_DIR / "reports" / "sample_inventory.json"

def load_inventory():
    """Read the latest report, or use the sample before the first API call."""
    path = REPORT_FILE if REPORT_FILE.exists() else SAMPLE_FILE
    with path.open("r", encoding="utf-8") as file:
        return json.load(file), path

def main():
    st.set_page_config(page_title="Cisco CML REST API Automation", layout="wide")
    st.title("Cisco CML REST API Automation")
    st.write(
        "View Cisco CML lab details, device inventory, interface IPv4 addresses, "
        "and SSH port mappings collected using REST APIs."
    )

    if st.button("Refresh from CML", type="primary"):
        try:
            with st.spinner("Collecting lab information..."):
                collect_inventory()
            st.success("Inventory updated successfully.")
        except Exception as error:
            st.error(f"Unable to refresh inventory: {error}")

    try:
        inventory, path = load_inventory()
    except (FileNotFoundError, OSError, json.JSONDecodeError) as error:
        st.error(f"Unable to load the inventory JSON: {error}")
        st.stop()

    if path == SAMPLE_FILE:
        st.info("Showing sample data. Click 'Refresh from CML' to get live lab inventory.")

    nodes = inventory.get("nodes", [])
    router_count = sum(node.get("node_definition") == "iosv" for node in nodes)
    switch_count = sum(node.get("node_definition") == "iosvl2" for node in nodes)

    # 1. Lab summary
    st.subheader(inventory.get("lab_title", "CML Lab"))
    st.write(inventory.get("lab_description", ""))

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Lab Nodes", inventory.get("node_count", 0))
    c2.metric("Routers", router_count)
    c3.metric("Switches", switch_count)
    c4.metric("Links", inventory.get("link_count", 0))
    st.caption("Lab Nodes includes the external connector; inventory tables do not.")

    # 2. Device filter
    device_names = [node["device"] for node in nodes]
    selected = st.multiselect("Select devices", device_names, default=device_names)
    selected_nodes = [node for node in nodes if node["device"] in selected]

    # 3. Device table
    st.subheader("Device Inventory")
    device_rows = [
        {
            "Device": node["device"],
            "Type": node["node_definition"],
            "SSH Port": node.get("port"),
            "Interfaces": len(node.get("interfaces", [])),
        }
        for node in selected_nodes
    ]
    if device_rows:
        st.dataframe(device_rows, hide_index=True, use_container_width=True)
    else:
        st.info("Select a device to view inventory.")

    # 4. Interface table
    st.subheader("Interface Details")
    ip_filter = st.radio(
        "IPv4 filter", ["All", "Assigned", "Unassigned"], horizontal=True
    )
    interface_rows = [
        {
            "Device": node["device"],
            "Interface": iface["interface"],
            "IPv4 Address": iface["ip"],
        }
        for node in selected_nodes
        for iface in node.get("interfaces", [])
        if ip_filter == "All"
        or (ip_filter == "Assigned" and iface["ip"] not in ("unassigned", "unavailable"))
        or (ip_filter == "Unassigned" and iface["ip"] == "unassigned")
    ]
    if interface_rows:
        st.dataframe(interface_rows, hide_index=True, use_container_width=True)
    else:
        st.info("No interfaces match the filters.")

    # 5. JSON output
    with st.expander("Combined JSON Output"):
        st.json(inventory)

    st.download_button(
        "Download JSON Report",
        data=json.dumps(inventory, indent=4),
        file_name="cml_inventory.json",
        mime="application/json",
    )

if __name__ == "__main__":
    main()
