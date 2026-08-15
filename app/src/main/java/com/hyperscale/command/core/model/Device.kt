package com.hyperscale.command.core.model

import kotlinx.serialization.Serializable

/**
 * A single sighting of something, from one scanner, over one protocol.
 *
 * Scanners only ever emit observations. Merging observations into a coherent [Device] is the
 * [com.hyperscale.command.discovery.DeviceMerger]'s job, so that one physical device seen over
 * mDNS, SSDP, BLE and Homey at once shows up as one row, not four.
 */
@Serializable
data class Observation(
    val protocol: Protocol,
    val source: DiscoverySource,
    /** Best available stable identifier from this scanner's point of view. */
    val identityKeys: Set<String>,
    val ipAddress: String? = null,
    val macAddress: String? = null,
    val hostname: String? = null,
    val port: Int? = null,
    val displayName: String? = null,
    val manufacturer: String? = null,
    val model: String? = null,
    val firmwareVersion: String? = null,
    val serialNumber: String? = null,
    /** RSSI in dBm for radio-based sightings; null for IP-based ones. */
    val rssi: Int? = null,
    /** Raw key/value evidence (mDNS TXT, SSDP headers, BLE service data) shown in the detail pane. */
    val attributes: Map<String, String> = emptyMap(),
    val seenAtMillis: Long,
)

@Serializable
enum class DiscoverySource(val label: String) {
    MDNS("mDNS"),
    SSDP("SSDP"),
    BLE("Bluetooth LE"),
    BLUETOOTH_CLASSIC("Bluetooth"),
    ARP("Network sweep"),
    UDP_BROADCAST("UDP broadcast"),
    IP_MULTICAST("IP multicast"),
    PORT_PROBE("Port probe"),
    HOMEY("Homey Pro"),
    NFC("NFC"),
    MANUAL("Added manually"),
}

/** Broad device class, inferred by the fingerprinter and used for iconography and grouping. */
@Serializable
enum class DeviceClass(val label: String) {
    LIGHT("Light"),
    SWITCH("Switch"),
    PLUG("Smart plug"),
    SENSOR("Sensor"),
    THERMOSTAT("Climate"),
    LOCK("Lock"),
    CAMERA("Camera"),
    DOORBELL("Doorbell"),
    SPEAKER("Speaker"),
    TV("TV / display"),
    MEDIA("Media player"),
    APPLIANCE("Appliance"),
    VACUUM("Vacuum"),
    BLINDS("Blinds / cover"),
    FAN("Fan"),
    ENERGY("Energy"),
    HUB("Hub / bridge"),
    NETWORK("Network gear"),
    COMPUTER("Computer"),
    PRINTER("Printer"),
    WEARABLE("Wearable"),
    VEHICLE("Vehicle"),
    OTHER("Other"),
}

/** Live reachability of a merged device. */
@Serializable
enum class DeviceStatus(val label: String) {
    ONLINE("Online"),
    RECENTLY_SEEN("Recently seen"),
    OFFLINE("Offline"),
    UNREACHABLE("Unreachable"),
}

/**
 * A controllable property exposed by a device, normalised across ecosystems.
 * Mirrors Homey's capability model because that is the richest source we have.
 */
@Serializable
data class Capability(
    val id: String,
    val title: String,
    val type: CapabilityType,
    val value: CapabilityValue,
    val unit: String? = null,
    val settable: Boolean,
    val min: Double? = null,
    val max: Double? = null,
    val step: Double? = null,
    val options: List<String> = emptyList(),
)

@Serializable
enum class CapabilityType { BOOLEAN, NUMBER, STRING, ENUM, COLOR }

@Serializable
sealed interface CapabilityValue {
    @Serializable
    data class Bool(val value: Boolean) : CapabilityValue

    @Serializable
    data class Num(val value: Double) : CapabilityValue

    @Serializable
    data class Text(val value: String) : CapabilityValue

    @Serializable
    data object Absent : CapabilityValue
}

/**
 * A merged, user-facing device: everything we know about one physical thing, from every
 * protocol that has seen it.
 */
@Serializable
data class Device(
    /** Stable app-side id, derived from the strongest identity key available. */
    val id: String,
    val name: String,
    /** User-assigned name; overrides [name] in the UI when present. */
    val nickname: String? = null,
    val deviceClass: DeviceClass = DeviceClass.OTHER,
    val manufacturer: String? = null,
    val model: String? = null,
    val firmwareVersion: String? = null,
    val serialNumber: String? = null,
    val ipAddress: String? = null,
    val macAddress: String? = null,
    val hostname: String? = null,
    /** Every protocol this device has been seen speaking, strongest evidence first. */
    val protocols: List<Protocol> = emptyList(),
    val sources: Set<DiscoverySource> = emptySet(),
    val status: DeviceStatus = DeviceStatus.ONLINE,
    val rssi: Int? = null,
    /** Homey device id, when this device is bridged. Enables direct control. */
    val homeyDeviceId: String? = null,
    val homeyZoneName: String? = null,
    val capabilities: List<Capability> = emptyList(),
    val attributes: Map<String, String> = emptyMap(),
    val identityKeys: Set<String> = emptySet(),
    val firstSeenMillis: Long = 0L,
    val lastSeenMillis: Long = 0L,
    val isFavourite: Boolean = false,
    /** Set when the user has explicitly acknowledged/adopted this device. */
    val isAdopted: Boolean = false,
) {
    val displayName: String get() = nickname?.takeIf { it.isNotBlank() } ?: name

    val isControllable: Boolean
        get() = homeyDeviceId != null && capabilities.any { it.settable }

    val primaryProtocol: Protocol get() = protocols.firstOrNull() ?: Protocol.UNKNOWN

    val onOff: Capability? get() = capabilities.firstOrNull { it.id == "onoff" }

    val isOn: Boolean?
        get() = (onOff?.value as? CapabilityValue.Bool)?.value

    val subtitle: String
        get() = buildList {
            manufacturer?.let { add(it) }
            model?.takeIf { it != manufacturer }?.let { add(it) }
            ipAddress?.let { add(it) }
            homeyZoneName?.let { add(it) }
        }.joinToString(" · ").ifBlank { primaryProtocol.displayName }

    fun matches(query: String): Boolean {
        if (query.isBlank()) return true
        val q = query.trim().lowercase()
        return displayName.lowercase().contains(q) ||
            manufacturer?.lowercase()?.contains(q) == true ||
            model?.lowercase()?.contains(q) == true ||
            ipAddress?.contains(q) == true ||
            macAddress?.lowercase()?.contains(q) == true ||
            hostname?.lowercase()?.contains(q) == true ||
            homeyZoneName?.lowercase()?.contains(q) == true ||
            protocols.any { it.searchText.contains(q) } ||
            deviceClass.label.lowercase().contains(q)
    }
}

/** Progress of a scan pass, surfaced live in the Discover screen. */
data class ScanProgress(
    val isScanning: Boolean = false,
    val startedAtMillis: Long = 0L,
    val completedScanners: Int = 0,
    val totalScanners: Int = 0,
    val activeProtocols: Set<Protocol> = emptySet(),
    val hostsProbed: Int = 0,
    val hostsTotal: Int = 0,
    val devicesFound: Int = 0,
    val statusLine: String = "",
) {
    val fraction: Float
        get() = when {
            totalScanners == 0 -> 0f
            else -> (completedScanners.toFloat() / totalScanners).coerceIn(0f, 1f)
        }
}
