package com.hyperscale.command.core.model

/**
 * How a protocol groups in the UI and in the scan scheduler.
 */
enum class ProtocolFamily(val displayName: String) {
    IP_NETWORK("IP & Network"),
    WIRELESS_PAN("Wireless PAN / Mesh"),
    WIRELESS_LPWAN("Long Range / LPWAN"),
    SUB_GHZ_RF("Sub-GHz RF"),
    INFRARED("Infrared"),
    POWERLINE("Powerline"),
    WIRED_BUS("Wired Bus & Fieldbus"),
    VENDOR_LAN("Vendor LAN Protocols"),
    CLOUD("Cloud & Ecosystem"),
    PROXIMITY("Proximity"),
}

/**
 * Whether this phone can see the protocol itself, or whether it can only ever be observed
 * through a hub that speaks it (Homey Pro, in this app's case).
 *
 * This distinction matters: an Android handset has no Zigbee, Z-Wave, 433 MHz or IR *receiver*
 * radio, so promising a direct scan for those would be a lie. Those devices are surfaced through
 * the Homey Pro bridge instead, and the UI labels them as such.
 */
enum class Reachability(val label: String) {
    /** Discoverable directly by this handset's own radios. */
    PHONE_NATIVE("Direct scan"),

    /** Only reachable through a bridge/hub (Homey Pro). */
    HUB_BRIDGED("Via hub"),

    /** Partially direct (e.g. commissioning over BLE) and fully visible via a hub. */
    HYBRID("Direct + hub"),
}

/** The mechanism a scanner uses for this protocol. Drives which scanner engine runs. */
enum class DiscoveryMethod {
    MDNS,
    SSDP,
    UDP_BROADCAST,
    IP_MULTICAST,
    TCP_PORT_PROBE,
    ARP_SWEEP,
    BLE_ADVERTISEMENT,
    BLUETOOTH_CLASSIC,
    NFC_TAG,
    HUB_INVENTORY,
    MANUAL_ONLY,
}

/**
 * The catalogue of communication protocols this app knows about.
 *
 * Entries are deliberately exhaustive, including legacy and effectively-dead protocols (X10, UPB,
 * Insteon, Sigfox), because a mixed-brand house accumulates them and the user asked to be able to
 * identify anything. Each entry carries enough metadata for the UI to explain honestly what can and
 * cannot be found from a phone.
 */
enum class Protocol(
    val displayName: String,
    val aka: String? = null,
    val family: ProtocolFamily,
    val reachability: Reachability,
    val methods: Set<DiscoveryMethod>,
    /** Well-known TCP/UDP ports, used by the port-probe scanner and shown in device detail. */
    val ports: List<Int> = emptyList(),
    /** mDNS/DNS-SD service types advertised by devices speaking this protocol. */
    val serviceTypes: List<String> = emptyList(),
    val summary: String,
) {
    // ───────────────────────────── IP & network fundamentals ─────────────────────────────
    MDNS(
        displayName = "mDNS / DNS-SD", aka = "Bonjour, Zeroconf",
        family = ProtocolFamily.IP_NETWORK, reachability = Reachability.PHONE_NATIVE,
        methods = setOf(DiscoveryMethod.MDNS), ports = listOf(5353),
        summary = "Multicast DNS service discovery. The single richest source of identity on a home LAN.",
    ),
    SSDP(
        displayName = "SSDP / UPnP", aka = "Universal Plug and Play",
        family = ProtocolFamily.IP_NETWORK, reachability = Reachability.PHONE_NATIVE,
        methods = setOf(DiscoveryMethod.SSDP), ports = listOf(1900),
        summary = "Multicast search over UDP 1900. Finds TVs, media renderers, routers and older hubs.",
    ),
    DLNA(
        displayName = "DLNA", aka = "UPnP AV",
        family = ProtocolFamily.IP_NETWORK, reachability = Reachability.PHONE_NATIVE,
        methods = setOf(DiscoveryMethod.SSDP), ports = listOf(1900, 8200),
        summary = "Media sharing layered on UPnP. Servers, renderers and controllers.",
    ),
    HTTP(
        displayName = "HTTP / REST",
        family = ProtocolFamily.IP_NETWORK, reachability = Reachability.PHONE_NATIVE,
        methods = setOf(DiscoveryMethod.TCP_PORT_PROBE), ports = listOf(80, 8080, 8081, 8123, 8888),
        summary = "Plain web control endpoints. Most local-first devices expose one.",
    ),
    HTTPS(
        displayName = "HTTPS / TLS",
        family = ProtocolFamily.IP_NETWORK, reachability = Reachability.PHONE_NATIVE,
        methods = setOf(DiscoveryMethod.TCP_PORT_PROBE), ports = listOf(443, 8443),
        summary = "TLS-secured web control. Local devices usually present a self-signed certificate.",
    ),
    WEBSOCKET(
        displayName = "WebSocket",
        family = ProtocolFamily.IP_NETWORK, reachability = Reachability.PHONE_NATIVE,
        methods = setOf(DiscoveryMethod.TCP_PORT_PROBE), ports = listOf(80, 443, 8080, 9000),
        summary = "Persistent bidirectional channel, used for live state by Shelly Gen2, Homey and others.",
    ),
    MQTT(
        displayName = "MQTT",
        family = ProtocolFamily.IP_NETWORK, reachability = Reachability.PHONE_NATIVE,
        methods = setOf(DiscoveryMethod.TCP_PORT_PROBE, DiscoveryMethod.MDNS),
        ports = listOf(1883, 8883, 8083, 9001), serviceTypes = listOf("_mqtt._tcp", "_secure-mqtt._tcp"),
        summary = "Pub/sub broker protocol. Backbone of Zigbee2MQTT, Tasmota and ESPHome fleets.",
    ),
    MQTT_SN(
        displayName = "MQTT-SN",
        family = ProtocolFamily.IP_NETWORK, reachability = Reachability.PHONE_NATIVE,
        methods = setOf(DiscoveryMethod.UDP_BROADCAST), ports = listOf(1884),
        summary = "MQTT for sensor networks over UDP, used by constrained battery nodes.",
    ),
    COAP(
        displayName = "CoAP",
        family = ProtocolFamily.IP_NETWORK, reachability = Reachability.PHONE_NATIVE,
        methods = setOf(DiscoveryMethod.UDP_BROADCAST, DiscoveryMethod.IP_MULTICAST),
        ports = listOf(5683, 5684), serviceTypes = listOf("_coap._udp"),
        summary = "Constrained REST over UDP. Used by IKEA TRÅDFRI and Shelly Gen1 status pushes.",
    ),
    AMQP(
        displayName = "AMQP",
        family = ProtocolFamily.IP_NETWORK, reachability = Reachability.PHONE_NATIVE,
        methods = setOf(DiscoveryMethod.TCP_PORT_PROBE), ports = listOf(5671, 5672),
        summary = "Enterprise message queuing, occasionally seen on prosumer controllers.",
    ),
    XMPP(
        displayName = "XMPP",
        family = ProtocolFamily.IP_NETWORK, reachability = Reachability.PHONE_NATIVE,
        methods = setOf(DiscoveryMethod.TCP_PORT_PROBE), ports = listOf(5222, 5269),
        summary = "Legacy messaging transport, still used by some older cloud-tethered cameras.",
    ),
    SNMP(
        displayName = "SNMP",
        family = ProtocolFamily.IP_NETWORK, reachability = Reachability.PHONE_NATIVE,
        methods = setOf(DiscoveryMethod.UDP_BROADCAST), ports = listOf(161, 162),
        summary = "Network management. Identifies switches, APs, NAS and UPS hardware.",
    ),
    ONVIF(
        displayName = "ONVIF",
        family = ProtocolFamily.IP_NETWORK, reachability = Reachability.PHONE_NATIVE,
        methods = setOf(DiscoveryMethod.UDP_BROADCAST, DiscoveryMethod.SSDP), ports = listOf(3702, 80),
        summary = "IP camera discovery and control via WS-Discovery on UDP 3702.",
    ),
    RTSP(
        displayName = "RTSP",
        family = ProtocolFamily.IP_NETWORK, reachability = Reachability.PHONE_NATIVE,
        methods = setOf(DiscoveryMethod.TCP_PORT_PROBE), ports = listOf(554, 8554),
        serviceTypes = listOf("_rtsp._tcp"),
        summary = "Camera video streaming endpoints.",
    ),
    SSH(
        displayName = "SSH",
        family = ProtocolFamily.IP_NETWORK, reachability = Reachability.PHONE_NATIVE,
        methods = setOf(DiscoveryMethod.TCP_PORT_PROBE), ports = listOf(22),
        serviceTypes = listOf("_ssh._tcp"),
        summary = "Shell access. Present on hubs, NAS units and hacked-open devices.",
    ),
    TELNET(
        displayName = "Telnet",
        family = ProtocolFamily.IP_NETWORK, reachability = Reachability.PHONE_NATIVE,
        methods = setOf(DiscoveryMethod.TCP_PORT_PROBE), ports = listOf(23, 24),
        summary = "Legacy unencrypted control, still exposed by older lighting and AV gear.",
    ),

    // ───────────────────────────── Wireless PAN & mesh ─────────────────────────────
    WIFI(
        displayName = "Wi-Fi", aka = "IEEE 802.11",
        family = ProtocolFamily.WIRELESS_PAN, reachability = Reachability.PHONE_NATIVE,
        methods = setOf(DiscoveryMethod.ARP_SWEEP),
        summary = "The carrier for most of the LAN protocols here. Sweep finds anything with an IP.",
    ),
    WIFI_DIRECT(
        displayName = "Wi-Fi Direct", aka = "P2P",
        family = ProtocolFamily.WIRELESS_PAN, reachability = Reachability.PHONE_NATIVE,
        methods = setOf(DiscoveryMethod.MDNS),
        summary = "Peer-to-peer Wi-Fi. Used for setup handshakes and direct casting.",
    ),
    BLE(
        displayName = "Bluetooth LE", aka = "BLE, Bluetooth Smart",
        family = ProtocolFamily.WIRELESS_PAN, reachability = Reachability.PHONE_NATIVE,
        methods = setOf(DiscoveryMethod.BLE_ADVERTISEMENT),
        summary = "Advertisement scanning identifies sensors, locks, trackers and Matter commissioning windows.",
    ),
    BLUETOOTH_CLASSIC(
        displayName = "Bluetooth Classic", aka = "BR/EDR",
        family = ProtocolFamily.WIRELESS_PAN, reachability = Reachability.PHONE_NATIVE,
        methods = setOf(DiscoveryMethod.BLUETOOTH_CLASSIC),
        summary = "Speakers, remotes and older appliances that never moved to LE.",
    ),
    BLE_MESH(
        displayName = "Bluetooth Mesh",
        family = ProtocolFamily.WIRELESS_PAN, reachability = Reachability.HYBRID,
        methods = setOf(DiscoveryMethod.BLE_ADVERTISEMENT, DiscoveryMethod.HUB_INVENTORY),
        summary = "Managed BLE mesh lighting. Unprovisioned nodes beacon and are visible directly.",
    ),
    ZIGBEE(
        displayName = "Zigbee", aka = "IEEE 802.15.4",
        family = ProtocolFamily.WIRELESS_PAN, reachability = Reachability.HUB_BRIDGED,
        methods = setOf(DiscoveryMethod.HUB_INVENTORY),
        summary = "No handset has a Zigbee radio — these arrive through Homey Pro's built-in controller.",
    ),
    ZIGBEE_GREEN_POWER(
        displayName = "Zigbee Green Power",
        family = ProtocolFamily.WIRELESS_PAN, reachability = Reachability.HUB_BRIDGED,
        methods = setOf(DiscoveryMethod.HUB_INVENTORY),
        summary = "Battery-free kinetic switches riding the Zigbee network.",
    ),
    ZWAVE(
        displayName = "Z-Wave",
        family = ProtocolFamily.SUB_GHZ_RF, reachability = Reachability.HUB_BRIDGED,
        methods = setOf(DiscoveryMethod.HUB_INVENTORY),
        summary = "868/908 MHz mesh. Surfaced via the Homey Pro Z-Wave controller.",
    ),
    ZWAVE_LR(
        displayName = "Z-Wave Long Range",
        family = ProtocolFamily.SUB_GHZ_RF, reachability = Reachability.HUB_BRIDGED,
        methods = setOf(DiscoveryMethod.HUB_INVENTORY),
        summary = "Star-topology Z-Wave variant with far greater range.",
    ),
    THREAD(
        displayName = "Thread",
        family = ProtocolFamily.WIRELESS_PAN, reachability = Reachability.HYBRID,
        methods = setOf(DiscoveryMethod.MDNS, DiscoveryMethod.HUB_INVENTORY),
        serviceTypes = listOf("_meshcop._udp", "_meshcope._udp", "_trel._udp"),
        summary = "IPv6 mesh. Border routers announce over mDNS; end nodes come via the hub.",
    ),
    MATTER(
        displayName = "Matter", aka = "CHIP",
        family = ProtocolFamily.WIRELESS_PAN, reachability = Reachability.HYBRID,
        methods = setOf(DiscoveryMethod.MDNS, DiscoveryMethod.BLE_ADVERTISEMENT, DiscoveryMethod.HUB_INVENTORY),
        ports = listOf(5540), serviceTypes = listOf("_matter._tcp", "_matterc._udp", "_matterd._udp"),
        summary = "Commissioned nodes advertise _matter._tcp; uncommissioned ones beacon over BLE.",
    ),
    SIXLOWPAN(
        displayName = "6LoWPAN",
        family = ProtocolFamily.WIRELESS_PAN, reachability = Reachability.HUB_BRIDGED,
        methods = setOf(DiscoveryMethod.HUB_INVENTORY),
        summary = "IPv6 over 802.15.4, the substrate beneath Thread.",
    ),
    NFC(
        displayName = "NFC",
        family = ProtocolFamily.PROXIMITY, reachability = Reachability.PHONE_NATIVE,
        methods = setOf(DiscoveryMethod.NFC_TAG),
        summary = "Tap-to-identify tags and setup handoff on supported devices.",
    ),

    // ───────────────────────────── Sub-GHz, LPWAN, IR ─────────────────────────────
    RF_433(
        displayName = "433 MHz RF",
        family = ProtocolFamily.SUB_GHZ_RF, reachability = Reachability.HUB_BRIDGED,
        methods = setOf(DiscoveryMethod.HUB_INVENTORY),
        summary = "Cheap remotes, doorbells and legacy sockets. Homey Pro has the radio, your phone does not.",
    ),
    RF_868(
        displayName = "868 MHz RF",
        family = ProtocolFamily.SUB_GHZ_RF, reachability = Reachability.HUB_BRIDGED,
        methods = setOf(DiscoveryMethod.HUB_INVENTORY),
        summary = "European sub-GHz band shared with Z-Wave and many alarm systems.",
    ),
    RF_315(
        displayName = "315 MHz RF",
        family = ProtocolFamily.SUB_GHZ_RF, reachability = Reachability.HUB_BRIDGED,
        methods = setOf(DiscoveryMethod.HUB_INVENTORY),
        summary = "North American remote band, garage doors and older sensors.",
    ),
    ENOCEAN(
        displayName = "EnOcean",
        family = ProtocolFamily.SUB_GHZ_RF, reachability = Reachability.HUB_BRIDGED,
        methods = setOf(DiscoveryMethod.HUB_INVENTORY),
        summary = "Energy-harvesting switches and sensors with no batteries at all.",
    ),
    LORAWAN(
        displayName = "LoRaWAN",
        family = ProtocolFamily.WIRELESS_LPWAN, reachability = Reachability.HUB_BRIDGED,
        methods = setOf(DiscoveryMethod.HUB_INVENTORY, DiscoveryMethod.MANUAL_ONLY),
        summary = "Long-range low-power WAN, typically via a gateway and network server.",
    ),
    SIGFOX(
        displayName = "Sigfox",
        family = ProtocolFamily.WIRELESS_LPWAN, reachability = Reachability.HUB_BRIDGED,
        methods = setOf(DiscoveryMethod.MANUAL_ONLY),
        summary = "Legacy ultra-narrowband LPWAN. Cloud-side only.",
    ),
    INFRARED(
        displayName = "Infrared", aka = "Consumer IR",
        family = ProtocolFamily.INFRARED, reachability = Reachability.HYBRID,
        methods = setOf(DiscoveryMethod.HUB_INVENTORY),
        summary = "One-way line-of-sight control. Emitted by IR blasters; never discoverable by listening.",
    ),

    // ───────────────────────────── Powerline & wired bus ─────────────────────────────
    X10(
        displayName = "X10",
        family = ProtocolFamily.POWERLINE, reachability = Reachability.HUB_BRIDGED,
        methods = setOf(DiscoveryMethod.HUB_INVENTORY, DiscoveryMethod.MANUAL_ONLY),
        summary = "The original 1975 powerline standard. Address-based, with no discovery of any kind.",
    ),
    INSTEON(
        displayName = "Insteon",
        family = ProtocolFamily.POWERLINE, reachability = Reachability.HUB_BRIDGED,
        methods = setOf(DiscoveryMethod.HUB_INVENTORY),
        summary = "Dual-mesh powerline plus RF. Requires a PLM or hub to enumerate.",
    ),
    UPB(
        displayName = "UPB", aka = "Universal Powerline Bus",
        family = ProtocolFamily.POWERLINE, reachability = Reachability.HUB_BRIDGED,
        methods = setOf(DiscoveryMethod.MANUAL_ONLY),
        summary = "Higher-reliability powerline successor to X10. Configuration is manual.",
    ),
    KNX(
        displayName = "KNX", aka = "KNXnet/IP, EIB",
        family = ProtocolFamily.WIRED_BUS, reachability = Reachability.PHONE_NATIVE,
        methods = setOf(DiscoveryMethod.IP_MULTICAST, DiscoveryMethod.TCP_PORT_PROBE),
        ports = listOf(3671),
        summary = "Building automation bus. IP gateways answer a SEARCH_REQUEST on 224.0.23.12:3671.",
    ),
    BACNET(
        displayName = "BACnet/IP",
        family = ProtocolFamily.WIRED_BUS, reachability = Reachability.PHONE_NATIVE,
        methods = setOf(DiscoveryMethod.UDP_BROADCAST), ports = listOf(47808),
        summary = "HVAC and building controls. Who-Is broadcast on UDP 47808.",
    ),
    MODBUS_TCP(
        displayName = "Modbus TCP",
        family = ProtocolFamily.WIRED_BUS, reachability = Reachability.PHONE_NATIVE,
        methods = setOf(DiscoveryMethod.TCP_PORT_PROBE), ports = listOf(502),
        summary = "Industrial register access. Common on inverters, heat pumps and energy meters.",
    ),
    MODBUS_RTU(
        displayName = "Modbus RTU",
        family = ProtocolFamily.WIRED_BUS, reachability = Reachability.HUB_BRIDGED,
        methods = setOf(DiscoveryMethod.HUB_INVENTORY),
        summary = "Serial Modbus over RS-485, reachable through a gateway.",
    ),
    DALI(
        displayName = "DALI",
        family = ProtocolFamily.WIRED_BUS, reachability = Reachability.HUB_BRIDGED,
        methods = setOf(DiscoveryMethod.HUB_INVENTORY),
        summary = "Digital lighting control bus, bridged by a DALI/IP gateway.",
    ),
    ONE_WIRE(
        displayName = "1-Wire",
        family = ProtocolFamily.WIRED_BUS, reachability = Reachability.HUB_BRIDGED,
        methods = setOf(DiscoveryMethod.HUB_INVENTORY),
        summary = "Temperature sensor chains via a bus master.",
    ),
    RS485(
        displayName = "RS-485",
        family = ProtocolFamily.WIRED_BUS, reachability = Reachability.HUB_BRIDGED,
        methods = setOf(DiscoveryMethod.HUB_INVENTORY),
        summary = "Differential serial bus underlying Modbus RTU and many proprietary schemes.",
    ),
    CBUS(
        displayName = "C-Bus",
        family = ProtocolFamily.WIRED_BUS, reachability = Reachability.PHONE_NATIVE,
        methods = setOf(DiscoveryMethod.TCP_PORT_PROBE), ports = listOf(10001),
        summary = "Clipsal/Schneider lighting bus, exposed by a CNI over TCP.",
    ),
    LUTRON(
        displayName = "Lutron", aka = "ClearConnect, Caséta",
        family = ProtocolFamily.VENDOR_LAN, reachability = Reachability.PHONE_NATIVE,
        methods = setOf(DiscoveryMethod.MDNS, DiscoveryMethod.TCP_PORT_PROBE),
        ports = listOf(23, 8081), serviceTypes = listOf("_lutron._tcp"),
        summary = "Smart Bridge exposes an integration protocol over telnet and LEAP.",
    ),
    CRESTRON(
        displayName = "Crestron",
        family = ProtocolFamily.VENDOR_LAN, reachability = Reachability.PHONE_NATIVE,
        methods = setOf(DiscoveryMethod.TCP_PORT_PROBE), ports = listOf(41794, 41795),
        summary = "Professional AV/control processors on the LAN.",
    ),

    // ───────────────────────────── Vendor LAN protocols ─────────────────────────────
    HOMEKIT(
        displayName = "HomeKit", aka = "HAP",
        family = ProtocolFamily.VENDOR_LAN, reachability = Reachability.PHONE_NATIVE,
        methods = setOf(DiscoveryMethod.MDNS, DiscoveryMethod.BLE_ADVERTISEMENT),
        serviceTypes = listOf("_hap._tcp", "_hap._udp"),
        summary = "Apple's accessory protocol. TXT records reveal category, model and pairing state.",
    ),
    CHROMECAST(
        displayName = "Google Cast",
        family = ProtocolFamily.VENDOR_LAN, reachability = Reachability.PHONE_NATIVE,
        methods = setOf(DiscoveryMethod.MDNS), ports = listOf(8009),
        serviceTypes = listOf("_googlecast._tcp"),
        summary = "Chromecast, Nest Hub, Android TV and Cast-enabled speakers.",
    ),
    AIRPLAY(
        displayName = "AirPlay",
        family = ProtocolFamily.VENDOR_LAN, reachability = Reachability.PHONE_NATIVE,
        methods = setOf(DiscoveryMethod.MDNS), ports = listOf(7000, 5000),
        serviceTypes = listOf("_airplay._tcp", "_raop._tcp", "_companion-link._tcp"),
        summary = "Apple TV, HomePod and AirPlay 2 receivers.",
    ),
    SPOTIFY_CONNECT(
        displayName = "Spotify Connect",
        family = ProtocolFamily.VENDOR_LAN, reachability = Reachability.PHONE_NATIVE,
        methods = setOf(DiscoveryMethod.MDNS), serviceTypes = listOf("_spotify-connect._tcp"),
        summary = "Speakers advertising Spotify playback endpoints.",
    ),
    SONOS(
        displayName = "Sonos",
        family = ProtocolFamily.VENDOR_LAN, reachability = Reachability.PHONE_NATIVE,
        methods = setOf(DiscoveryMethod.SSDP, DiscoveryMethod.TCP_PORT_PROBE), ports = listOf(1400),
        serviceTypes = listOf("_sonos._tcp"),
        summary = "Sonos speakers answer UPnP and serve a description on TCP 1400.",
    ),
    PHILIPS_HUE(
        displayName = "Philips Hue",
        family = ProtocolFamily.VENDOR_LAN, reachability = Reachability.PHONE_NATIVE,
        methods = setOf(DiscoveryMethod.MDNS, DiscoveryMethod.SSDP), ports = listOf(80, 443),
        serviceTypes = listOf("_hue._tcp"),
        summary = "Hue Bridge REST/CLIP API. Bulbs themselves are Zigbee behind the bridge.",
    ),
    HUE_ENTERTAINMENT(
        displayName = "Hue Entertainment", aka = "DTLS streaming",
        family = ProtocolFamily.VENDOR_LAN, reachability = Reachability.PHONE_NATIVE,
        methods = setOf(DiscoveryMethod.TCP_PORT_PROBE), ports = listOf(2100),
        summary = "Low-latency DTLS light streaming for sync boxes.",
    ),
    LIFX_LAN(
        displayName = "LIFX LAN",
        family = ProtocolFamily.VENDOR_LAN, reachability = Reachability.PHONE_NATIVE,
        methods = setOf(DiscoveryMethod.UDP_BROADCAST), ports = listOf(56700),
        summary = "Binary UDP protocol. GetService broadcast returns every bulb on the subnet.",
    ),
    NANOLEAF(
        displayName = "Nanoleaf OpenAPI",
        family = ProtocolFamily.VENDOR_LAN, reachability = Reachability.PHONE_NATIVE,
        methods = setOf(DiscoveryMethod.MDNS), ports = listOf(16021),
        serviceTypes = listOf("_nanoleafapi._tcp", "_nanoleafms._tcp"),
        summary = "Panels and light strips with a documented local REST API.",
    ),
    TUYA_LAN(
        displayName = "Tuya LAN",
        family = ProtocolFamily.VENDOR_LAN, reachability = Reachability.PHONE_NATIVE,
        methods = setOf(DiscoveryMethod.UDP_BROADCAST), ports = listOf(6666, 6667, 6668),
        summary = "Tuya/Smart Life devices broadcast an encrypted heartbeat every few seconds.",
    ),
    ESPHOME(
        displayName = "ESPHome",
        family = ProtocolFamily.VENDOR_LAN, reachability = Reachability.PHONE_NATIVE,
        methods = setOf(DiscoveryMethod.MDNS, DiscoveryMethod.TCP_PORT_PROBE), ports = listOf(6053),
        serviceTypes = listOf("_esphomelib._tcp"),
        summary = "Native API for DIY ESP32/ESP8266 nodes.",
    ),
    TASMOTA(
        displayName = "Tasmota",
        family = ProtocolFamily.VENDOR_LAN, reachability = Reachability.PHONE_NATIVE,
        methods = setOf(DiscoveryMethod.MDNS, DiscoveryMethod.TCP_PORT_PROBE), ports = listOf(80),
        serviceTypes = listOf("_tasmota._tcp"),
        summary = "Open firmware for Sonoff-class hardware, controllable over HTTP and MQTT.",
    ),
    SHELLY(
        displayName = "Shelly RPC",
        family = ProtocolFamily.VENDOR_LAN, reachability = Reachability.PHONE_NATIVE,
        methods = setOf(DiscoveryMethod.MDNS, DiscoveryMethod.TCP_PORT_PROBE), ports = listOf(80),
        serviceTypes = listOf("_shelly._tcp", "_http._tcp"),
        summary = "Gen1 REST and Gen2+ JSON-RPC over HTTP/WebSocket.",
    ),
    KASA(
        displayName = "TP-Link Kasa",
        family = ProtocolFamily.VENDOR_LAN, reachability = Reachability.PHONE_NATIVE,
        methods = setOf(DiscoveryMethod.UDP_BROADCAST), ports = listOf(9999, 20002),
        summary = "XOR-obfuscated JSON over UDP 9999. Plugs, switches and bulbs answer a broadcast.",
    ),
    YEELIGHT(
        displayName = "Yeelight LAN",
        family = ProtocolFamily.VENDOR_LAN, reachability = Reachability.PHONE_NATIVE,
        methods = setOf(DiscoveryMethod.SSDP), ports = listOf(55443),
        summary = "SSDP-style discovery on 239.255.255.250:1982 with a JSON control socket.",
    ),
    WIZ(
        displayName = "WiZ",
        family = ProtocolFamily.VENDOR_LAN, reachability = Reachability.PHONE_NATIVE,
        methods = setOf(DiscoveryMethod.UDP_BROADCAST), ports = listOf(38899, 38900),
        summary = "JSON over UDP 38899. getPilot/getSystemConfig returns full identity.",
    ),
    GOVEE_LAN(
        displayName = "Govee LAN",
        family = ProtocolFamily.VENDOR_LAN, reachability = Reachability.PHONE_NATIVE,
        methods = setOf(DiscoveryMethod.UDP_BROADCAST), ports = listOf(4001, 4002, 4003),
        summary = "Multicast scan on 239.255.255.250:4001 for LAN-enabled Govee lighting.",
    ),
    MIIO(
        displayName = "Xiaomi miIO",
        family = ProtocolFamily.VENDOR_LAN, reachability = Reachability.PHONE_NATIVE,
        methods = setOf(DiscoveryMethod.UDP_BROADCAST), ports = listOf(54321),
        summary = "Xiaomi/Roborock/Aqara hub handshake on UDP 54321.",
    ),
    SWITCHBOT(
        displayName = "SwitchBot",
        family = ProtocolFamily.VENDOR_LAN, reachability = Reachability.PHONE_NATIVE,
        methods = setOf(DiscoveryMethod.BLE_ADVERTISEMENT),
        summary = "BLE service data carries device type, battery and sensor readings.",
    ),
    ROKU_ECP(
        displayName = "Roku ECP",
        family = ProtocolFamily.VENDOR_LAN, reachability = Reachability.PHONE_NATIVE,
        methods = setOf(DiscoveryMethod.SSDP, DiscoveryMethod.TCP_PORT_PROBE), ports = listOf(8060),
        summary = "External Control Protocol over HTTP 8060.",
    ),
    WEBOS(
        displayName = "LG webOS",
        family = ProtocolFamily.VENDOR_LAN, reachability = Reachability.PHONE_NATIVE,
        methods = setOf(DiscoveryMethod.SSDP, DiscoveryMethod.TCP_PORT_PROBE), ports = listOf(3000, 3001),
        summary = "LG TV WebSocket control protocol.",
    ),
    SAMSUNG_TIZEN(
        displayName = "Samsung Tizen",
        family = ProtocolFamily.VENDOR_LAN, reachability = Reachability.PHONE_NATIVE,
        methods = setOf(DiscoveryMethod.SSDP, DiscoveryMethod.TCP_PORT_PROBE), ports = listOf(8001, 8002),
        summary = "Samsung TV remote WebSocket API.",
    ),
    WEMO(
        displayName = "Belkin WeMo",
        family = ProtocolFamily.VENDOR_LAN, reachability = Reachability.PHONE_NATIVE,
        methods = setOf(DiscoveryMethod.SSDP), ports = listOf(49152, 49153, 49154),
        summary = "UPnP switches and motion sensors on high ephemeral ports.",
    ),
    SMARTTHINGS(
        displayName = "SmartThings",
        family = ProtocolFamily.VENDOR_LAN, reachability = Reachability.HYBRID,
        methods = setOf(DiscoveryMethod.SSDP, DiscoveryMethod.HUB_INVENTORY),
        summary = "Samsung hub and directly-connected devices. Fits neatly alongside a Fold.",
    ),
    HOMEY(
        displayName = "Homey", aka = "Athom Homey Pro",
        family = ProtocolFamily.VENDOR_LAN, reachability = Reachability.PHONE_NATIVE,
        methods = setOf(DiscoveryMethod.MDNS, DiscoveryMethod.TCP_PORT_PROBE), ports = listOf(80, 443),
        serviceTypes = listOf("_homey._tcp", "_athom._tcp"),
        summary = "Your hub. Its local Web API is the bridge to every radio this phone lacks.",
    ),
    HOME_ASSISTANT(
        displayName = "Home Assistant",
        family = ProtocolFamily.VENDOR_LAN, reachability = Reachability.PHONE_NATIVE,
        methods = setOf(DiscoveryMethod.MDNS, DiscoveryMethod.TCP_PORT_PROBE), ports = listOf(8123),
        serviceTypes = listOf("_home-assistant._tcp", "_hass._tcp"),
        summary = "Detected as a peer controller if one is present on the network.",
    ),

    // ───────────────────────────── Cloud & ecosystem ─────────────────────────────
    ALEXA(
        displayName = "Alexa / AVS",
        family = ProtocolFamily.CLOUD, reachability = Reachability.HYBRID,
        methods = setOf(DiscoveryMethod.SSDP, DiscoveryMethod.MDNS),
        serviceTypes = listOf("_amzn-wplay._tcp", "_amazonecho-remote._tcp"),
        summary = "Echo hardware is visible locally; skill-linked devices are cloud-side.",
    ),
    GOOGLE_HOME(
        displayName = "Google Home",
        family = ProtocolFamily.CLOUD, reachability = Reachability.HYBRID,
        methods = setOf(DiscoveryMethod.MDNS), serviceTypes = listOf("_googlecast._tcp", "_googlezone._tcp"),
        summary = "Local Cast discovery plus cloud-linked Works-with-Google devices.",
    ),
    IFTTT(
        displayName = "IFTTT / Webhooks",
        family = ProtocolFamily.CLOUD, reachability = Reachability.HUB_BRIDGED,
        methods = setOf(DiscoveryMethod.MANUAL_ONLY),
        summary = "Cloud automation reachable through Homey Flows and webhooks.",
    ),
    CLOUD_ONLY(
        displayName = "Vendor Cloud",
        family = ProtocolFamily.CLOUD, reachability = Reachability.HUB_BRIDGED,
        methods = setOf(DiscoveryMethod.HUB_INVENTORY, DiscoveryMethod.MANUAL_ONLY),
        summary = "Devices with no local API at all, controllable only through their vendor's cloud.",
    ),
    UNKNOWN(
        displayName = "Unidentified",
        family = ProtocolFamily.IP_NETWORK, reachability = Reachability.PHONE_NATIVE,
        methods = setOf(DiscoveryMethod.ARP_SWEEP),
        summary = "Responds on the network but has not yet been fingerprinted.",
    );

    val searchText: String
        get() = "$displayName ${aka.orEmpty()} ${family.displayName}".lowercase()
}

object ProtocolCatalog {
    val all: List<Protocol> = Protocol.entries.filter { it != Protocol.UNKNOWN }

    val byFamily: Map<ProtocolFamily, List<Protocol>> =
        all.groupBy { it.family }.toSortedMap(compareBy { it.ordinal })

    /** Protocols this handset can genuinely scan for on its own. */
    val directlyScannable: List<Protocol> =
        all.filter { it.reachability != Reachability.HUB_BRIDGED }

    /** Protocols that only ever appear through a hub. */
    val hubOnly: List<Protocol> = all.filter { it.reachability == Reachability.HUB_BRIDGED }

    fun withMethod(method: DiscoveryMethod): List<Protocol> = all.filter { method in it.methods }

    /** All mDNS service types across the catalogue, de-duplicated, for the mDNS scanner. */
    val allServiceTypes: List<String> =
        all.flatMap { it.serviceTypes }.distinct()

    fun forServiceType(serviceType: String): Protocol? {
        val normalised = serviceType.trim().removeSuffix(".").lowercase()
        return all.firstOrNull { proto ->
            proto.serviceTypes.any { normalised.startsWith(it.lowercase()) }
        }
    }

    fun forPort(port: Int): List<Protocol> = all.filter { port in it.ports }

    fun fromId(id: String): Protocol? = Protocol.entries.firstOrNull { it.name == id }
}
