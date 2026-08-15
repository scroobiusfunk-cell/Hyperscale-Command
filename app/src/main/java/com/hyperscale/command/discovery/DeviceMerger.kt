package com.hyperscale.command.discovery

import com.hyperscale.command.core.model.Device
import com.hyperscale.command.core.model.DeviceClass
import com.hyperscale.command.core.model.DeviceStatus
import com.hyperscale.command.core.model.Observation
import com.hyperscale.command.core.model.Protocol
import com.hyperscale.command.discovery.fingerprint.Fingerprinter

/**
 * Folds a stream of per-protocol [Observation]s into a de-duplicated device list.
 *
 * The hard part of multi-protocol discovery is not finding things, it is realising that the
 * `_googlecast._tcp` record, the SSDP `ROOT_DEVICE` response, the ARP entry and the Homey device
 * are all the same speaker. Observations therefore carry a set of identity keys (MAC, IP,
 * hostname, BLE address, Homey id, serial). Two observations belong to the same device when their
 * key sets intersect, and merging is transitive — so mDNS can bridge an IP-keyed sighting to a
 * MAC-keyed one.
 *
 * Not thread-safe by design: the engine confines it to a single coroutine.
 */
class DeviceMerger {

    private val devicesById = LinkedHashMap<String, Device>()
    private val deviceIdByKey = HashMap<String, String>()

    fun snapshot(): List<Device> = devicesById.values.toList()

    fun clear() {
        devicesById.clear()
        deviceIdByKey.clear()
    }

    /** Seeds the merger with previously known devices so re-scans update rather than duplicate. */
    fun seed(devices: List<Device>) {
        devices.forEach { device ->
            devicesById[device.id] = device
            device.identityKeys.forEach { deviceIdByKey[it] = device.id }
        }
    }

    /**
     * Absorbs one observation. Returns the device it landed on, whether newly created or updated.
     */
    fun absorb(observation: Observation): Device {
        val keys = normaliseKeys(observation)
        val matchedIds = keys.mapNotNull { deviceIdByKey[it] }.distinct()

        val target = when {
            matchedIds.isEmpty() -> createDevice(observation, keys)
            matchedIds.size == 1 -> devicesById.getValue(matchedIds.first())
            // This observation proves two previously separate records are one device.
            else -> coalesce(matchedIds)
        }

        val updated = apply(target, observation, keys)
        devicesById[updated.id] = updated
        updated.identityKeys.forEach { deviceIdByKey[it] = updated.id }
        return updated
    }

    /** Marks devices not seen since [cutoffMillis] as stale, without removing them. */
    fun ageOut(nowMillis: Long, staleAfterMillis: Long, offlineAfterMillis: Long) {
        devicesById.replaceAll { _, device ->
            val age = nowMillis - device.lastSeenMillis
            val status = when {
                age <= staleAfterMillis -> DeviceStatus.ONLINE
                age <= offlineAfterMillis -> DeviceStatus.RECENTLY_SEEN
                else -> DeviceStatus.OFFLINE
            }
            if (status == device.status) device else device.copy(status = status)
        }
    }

    private fun createDevice(observation: Observation, keys: Set<String>): Device {
        val id = keys.minOrNull() ?: "obs-${observation.protocol.name}-${observation.seenAtMillis}"
        return Device(
            id = id,
            name = observation.displayName ?: observation.hostname ?: observation.ipAddress ?: "Unknown device",
            firstSeenMillis = observation.seenAtMillis,
            lastSeenMillis = observation.seenAtMillis,
        )
    }

    /** Merges several device records into the oldest of them, which keeps the id stable. */
    private fun coalesce(ids: List<String>): Device {
        val records = ids.mapNotNull { devicesById[it] }
        val primary = records.minByOrNull { it.firstSeenMillis } ?: return devicesById.getValue(ids.first())

        var merged = primary
        records.filter { it.id != primary.id }.forEach { other ->
            merged = merged.copy(
                nickname = merged.nickname ?: other.nickname,
                manufacturer = merged.manufacturer ?: other.manufacturer,
                model = merged.model ?: other.model,
                firmwareVersion = merged.firmwareVersion ?: other.firmwareVersion,
                serialNumber = merged.serialNumber ?: other.serialNumber,
                ipAddress = merged.ipAddress ?: other.ipAddress,
                macAddress = merged.macAddress ?: other.macAddress,
                hostname = merged.hostname ?: other.hostname,
                homeyDeviceId = merged.homeyDeviceId ?: other.homeyDeviceId,
                homeyZoneName = merged.homeyZoneName ?: other.homeyZoneName,
                capabilities = merged.capabilities.ifEmpty { other.capabilities },
                deviceClass = if (merged.deviceClass == DeviceClass.OTHER) other.deviceClass else merged.deviceClass,
                protocols = (merged.protocols + other.protocols).distinct(),
                sources = merged.sources + other.sources,
                attributes = other.attributes + merged.attributes,
                identityKeys = merged.identityKeys + other.identityKeys,
                isFavourite = merged.isFavourite || other.isFavourite,
                isAdopted = merged.isAdopted || other.isAdopted,
                firstSeenMillis = minOf(merged.firstSeenMillis, other.firstSeenMillis),
                lastSeenMillis = maxOf(merged.lastSeenMillis, other.lastSeenMillis),
            )
            devicesById.remove(other.id)
        }

        devicesById[merged.id] = merged
        merged.identityKeys.forEach { deviceIdByKey[it] = merged.id }
        return merged
    }

    private fun apply(device: Device, observation: Observation, keys: Set<String>): Device {
        val protocols = orderProtocols(device.protocols, observation.protocol)
        val attributes = device.attributes + observation.attributes.mapKeys { (key, _) ->
            "${observation.source.label}: $key"
        }

        val withEvidence = device.copy(
            manufacturer = observation.manufacturer ?: device.manufacturer,
            model = observation.model ?: device.model,
            firmwareVersion = observation.firmwareVersion ?: device.firmwareVersion,
            serialNumber = observation.serialNumber ?: device.serialNumber,
            ipAddress = observation.ipAddress ?: device.ipAddress,
            macAddress = observation.macAddress ?: device.macAddress,
            hostname = observation.hostname ?: device.hostname,
            protocols = protocols,
            sources = device.sources + observation.source,
            status = DeviceStatus.ONLINE,
            rssi = observation.rssi ?: device.rssi,
            attributes = attributes,
            identityKeys = device.identityKeys + keys,
            firstSeenMillis = if (device.firstSeenMillis == 0L) {
                observation.seenAtMillis
            } else {
                minOf(device.firstSeenMillis, observation.seenAtMillis)
            },
            lastSeenMillis = maxOf(device.lastSeenMillis, observation.seenAtMillis),
        )

        // Let the fingerprinter refine name/vendor/class now that evidence has accumulated.
        val identified = Fingerprinter.identify(withEvidence, observation)
        return identified.copy(
            name = pickName(identified.name, observation, identified),
        )
    }

    /**
     * Keeps the most *identifying* protocol first. A generic ARP sighting should never outrank a
     * specific one like Matter or Hue when labelling a device.
     */
    private fun orderProtocols(existing: List<Protocol>, incoming: Protocol): List<Protocol> =
        (existing + incoming)
            .distinct()
            .sortedWith(compareBy({ protocolSpecificity(it) }, { it.displayName }))

    private fun protocolSpecificity(protocol: Protocol): Int = when (protocol) {
        Protocol.UNKNOWN -> 100
        Protocol.WIFI -> 90
        Protocol.HTTP, Protocol.HTTPS, Protocol.WEBSOCKET -> 80
        Protocol.MDNS, Protocol.SSDP, Protocol.DLNA -> 70
        Protocol.BLE, Protocol.BLUETOOTH_CLASSIC -> 60
        else -> 10
    }

    private fun pickName(current: String, observation: Observation, device: Device): String {
        val candidate = observation.displayName?.takeIf { it.isNotBlank() }
        val currentIsPlaceholder = current.isBlank() ||
            current == "Unknown device" ||
            current == device.ipAddress ||
            current == device.macAddress

        return when {
            candidate != null && currentIsPlaceholder -> candidate
            // Prefer a friendly name over a bare hostname once one turns up.
            candidate != null && current == device.hostname && candidate != device.hostname -> candidate
            currentIsPlaceholder -> device.hostname ?: device.model ?: device.ipAddress ?: current
            else -> current
        }
    }

    /** Identity keys are namespaced so an IP never collides with a MAC or a Homey id. */
    private fun normaliseKeys(observation: Observation): Set<String> = buildSet {
        addAll(observation.identityKeys.map { it.lowercase() })
        observation.macAddress?.let { add("mac:${it.lowercase().replace("-", ":")}") }
        observation.ipAddress?.let { add("ip:$it") }
        observation.hostname?.let { add("host:${it.lowercase().removeSuffix(".").removeSuffix(".local")}") }
        observation.serialNumber?.let { add("serial:${it.lowercase()}") }
    }
}
