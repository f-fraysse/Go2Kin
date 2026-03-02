# GoPro USB Preview Stream – UDP Reception Failure (Windows Firewall Fix)

## Context

A GoPro HERO12 was connected to a Windows PC via **USB-NCM** (network-over-USB).  
The camera was configured to send a live preview stream using:

- **UDP MPEG-TS**
- Destination = **PC's GoPro NIC IP**
- Port = **8554**

Wireshark confirmed that the GoPro was transmitting ~3.6 Mbps of UDP MPEG-TS packets to:

- **Source:** `172.27.100.51` (GoPro)  
- **Destination:** `172.27.100.56` (PC, GoPro USB-NCM interface)  
- **UDP destination port:** `8554`

However, **Python**, **VLC**, and other apps binding to UDP port 8554 received **no packets**, despite Wireshark showing continuous traffic.

---

## Symptoms

- Wireshark shows continuous GoPro UDP traffic to `172.27.100.56:8554`.
- Python UDP listener (e.g. `sock.recvfrom()`) receives nothing.
- VLC with `udp://@:8554` (or `udp://@172.27.100.56:8554`) displays no video.
- Local loopback UDP tests (`127.0.0.1:8554`) work perfectly:
  - Listener receives packets when sender targets `127.0.0.1`.
- No explicit errors from Python or VLC — just no data.

This indicates that packets are reaching the NIC but being dropped before reaching application sockets.

---

## Root Cause

**Windows Defender Firewall was silently blocking inbound UDP packets from the GoPro USB-NCM interface.**

Key points:

- The GoPro USB-NCM adapter is treated by Windows as an **edge / untrusted network** (similar to tethering or modem connections).
- By default, Windows Firewall:
  - Blocks unsolicited **inbound UDP** on such interfaces.
  - Requires rules to explicitly allow **edge traversal** for this traffic to reach applications.

Even with an inbound rule like:

- Direction: **Inbound**
- Protocol: **UDP**
- Local port: **8554**
- Profiles: **All**
- Local/Remote IP: **Any**

…packets were still dropped because:

- **Edge traversal** was left at the default: **“Block edge traversal”**.

Wireshark still saw the packets because it hooks in **below** the firewall, at the capture driver level.

---

## Fix

### 1. Create an inbound rule for UDP 8554

In **Windows Defender Firewall with Advanced Security → Inbound Rules**:

1. **New Rule…**
2. **Port**
3. Protocol: **UDP**
4. Specific local port: **8554**
5. **Allow the connection**
6. Apply to all profiles (Domain, Private, Public) or as appropriate.
7. Name: e.g. `GoPro stream UDP 8554`.

### 2. Enable Edge Traversal

1. In the same console, under **Inbound Rules**, locate `GoPro stream UDP 8554`.
2. Double-click the rule to open its properties.
3. Go to the **Advanced** tab.
4. Set:

   - **Edge traversal:** `Allow edge traversal`

5. Click **OK**.

> Note: This must be edited on the actual rule under **Inbound Rules**, not under the read-only **Monitoring → Firewall** view.

### 3. (Optional) Reboot the PC

After enabling edge traversal and rebooting, the UDP listener and VLC both started receiving GoPro packets reliably.

---

## Result

After the rule was created and **edge traversal was allowed**:

- A simple Python listener bound to `172.27.100.56:8554` started receiving packets:

  ```text
  Received 1358 bytes from ('172.27.100.51', 42902)
