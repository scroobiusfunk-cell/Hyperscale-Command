package com.hyperscale.command.homey

import com.hyperscale.command.core.model.Capability
import com.hyperscale.command.core.model.CapabilityType
import com.hyperscale.command.core.model.CapabilityValue
import com.hyperscale.command.core.model.DeviceClass
import com.hyperscale.command.core.model.DiscoverySource
import com.hyperscale.command.core.model.Observation
import com.hyperscale.command.core.model.Protocol
import kotlinx.serialization.json.JsonPrimitive

/**
 * Translates Homey's device model into the app's unified one.
 *
 * This is what makes Zigbee, Z-Wave, 433 MHz, infrared and cloud-only devices appear in the same
 * list as everything the phone found by itself — Homey is the only party in the house with those
 * radios, so its inventory is the source of truth for them.
 *
 * Protocol attribution is deliberately evidence-based rather than guessed: Homey stamps radio
 * specific keys into a device's settings (`zw_node_id` for Z-Wave, `zb_ieee_address` for Zigbee),
 * and those are checked before falling back to reading the driver URI.
 */
object HomeyDeviceMapper {

    fun toObservation(
        device: HomeyDeviceDto,
        zoneNames: Map<String, String>,
        homeyAddress: String,
        nowMillis: Long = System.currentTimeMillis(),
    ): Observation {
        val protocol = inferProtocol(device)
        val zoneName = device.zoneName ?: device.zone?.let { zoneNames[it] }
        val macFromZigbee = device.settings.settingString("zb_ieee_address")

        return Observation(
            protocol = protocol,
            source = DiscoverySource.HOMEY,
            identityKeys = buildSet {
                add("homey:${device.id}")
                macFromZigbee?.let { add("ieee:${it.lowercase()}") }
                device.settings.settingString("address")
                    ?.takeIf { it.count { char -> char == '.' } == 3 }
                    ?.let { add("ip:$it") }
                device.settings.settingString("mac")?.let { add("mac:${it.lowercase()}") }
            },
            ipAddress = device.settings.settingString("address")
                ?.takeIf { it.count { char -> char == '.' } == 3 },
            macAddress = device.settings.settingString("mac")?.lowercase(),
            displayName = device.name,
            manufacturer = inferManufacturer(device),
            model = device.driverId ?: device.deviceClass,
            firmwareVersion = device.settings.settingString("zw_application_version")
                ?: device.settings.settingString("firmware_version"),
            serialNumber = macFromZigbee ?: device.settings.settingString("zw_device_id"),
            attributes = buildAttributes(device, zoneName, homeyAddress, protocol),
            seenAtMillis = nowMillis,
        )
    }

    /**
     * Homey device ids are stable and globally unique within a Homey, so they make the ideal
     * merge key. This is the same id the merger will see from [toObservation].
     */
    fun identityKeyFor(deviceId: String): String = "homey:$deviceId"

    fun toCapabilities(device: HomeyDeviceDto): List<Capability> {
        val objects = device.capabilitiesObj.orEmpty()
        if (objects.isNotEmpty()) {
            return objects.entries
                .mapNotNull { (key, dto) -> toCapability(key, dto) }
                .sortedWith(compareBy({ orderRank(it.id) }, { it.title }))
        }

        // Older firmware only lists capability ids; expose them read-only rather than not at all.
        return device.capabilities.map { id ->
            Capability(
                id = id,
                title = prettifyCapabilityId(id),
                type = CapabilityType.STRING,
                value = CapabilityValue.Absent,
                settable = false,
            )
        }
    }

    fun toDeviceClass(device: HomeyDeviceDto): DeviceClass =
        when (device.virtualClass ?: device.deviceClass) {
            "light" -> DeviceClass.LIGHT
            "socket" -> DeviceClass.PLUG
            "button", "remote" -> DeviceClass.SWITCH
            "sensor" -> DeviceClass.SENSOR
            "thermostat", "heater", "airconditioning", "airtreatment" -> DeviceClass.THERMOSTAT
            "lock", "doorbell" -> if (device.deviceClass == "doorbell") DeviceClass.DOORBELL else DeviceClass.LOCK
            "camera" -> DeviceClass.CAMERA
            "speaker", "amplifier" -> DeviceClass.SPEAKER
            "tv" -> DeviceClass.TV
            "blinds", "curtain", "windowcoverings", "sunshade", "garagedoor" -> DeviceClass.BLINDS
            "fan" -> DeviceClass.FAN
            "vacuumcleaner" -> DeviceClass.VACUUM
            "kettle", "coffeemachine", "washer", "dryer", "dishwasher", "oven", "fridge" -> DeviceClass.APPLIANCE
            "solarpanel", "evcharger", "battery" -> DeviceClass.ENERGY
            "homealarm" -> DeviceClass.SENSOR
            "other" -> DeviceClass.OTHER
            else -> DeviceClass.OTHER
        }

    private fun toCapability(key: String, dto: HomeyCapabilityDto): Capability? {
        val id = dto.id ?: key
        val type = when (dto.type?.lowercase()) {
            "boolean" -> CapabilityType.BOOLEAN
            "number" -> CapabilityType.NUMBER
            "enum" -> CapabilityType.ENUM
            "string" -> CapabilityType.STRING
            else -> inferTypeFromValue(dto)
        }

        val value = when (type) {
            CapabilityType.BOOLEAN -> dto.value.asBooleanOrNull()
                ?.let { CapabilityValue.Bool(it) } ?: CapabilityValue.Absent

            CapabilityType.NUMBER -> dto.value.asDoubleOrNull()
                ?.let { CapabilityValue.Num(it) } ?: CapabilityValue.Absent

            else -> dto.value.asStringOrNull()
                ?.let { CapabilityValue.Text(it) } ?: CapabilityValue.Absent
        }

        return Capability(
            id = id,
            title = localisedText(dto.title) ?: prettifyCapabilityId(id),
            type = type,
            value = value,
            unit = localisedText(dto.units),
            settable = dto.setable,
            min = dto.min,
            max = dto.max,
            step = dto.step,
            options = dto.values.orEmpty().mapNotNull { element ->
                (element as? JsonPrimitive)?.content
                    ?: localisedText(element)
            },
        )
    }

    private fun inferTypeFromValue(dto: HomeyCapabilityDto): CapabilityType = when {
        dto.value.asBooleanOrNull() != null -> CapabilityType.BOOLEAN
        dto.value.asDoubleOrNull() != null -> CapabilityType.NUMBER
        else -> CapabilityType.STRING
    }

    /**
     * Works out which radio a Homey device actually uses.
     *
     * Settings keys are checked first because they are hard evidence written by the Homey radio
     * managers themselves. The driver URI is a weaker signal — an app id like
     * `com.philips.hue.zigbee` names the ecosystem, not necessarily the transport.
     */
    private fun inferProtocol(device: HomeyDeviceDto): Protocol {
        val settings = device.settings

        when {
            settings.settingString("zw_node_id") != null -> return Protocol.ZWAVE
            settings.settingString("zb_ieee_address") != null -> return Protocol.ZIGBEE
            settings.settingString("matter_node_id") != null -> return Protocol.MATTER
            settings.settingString("thread_extended_address") != null -> return Protocol.THREAD
        }

        val uri = (device.driverUri.orEmpty() + " " + device.driverId.orEmpty()).lowercase()

        return when {
            "zwave" in uri || "z-wave" in uri -> Protocol.ZWAVE
            "zigbee" in uri -> Protocol.ZIGBEE
            "matter" in uri -> Protocol.MATTER
            "thread" in uri -> Protocol.THREAD
            "infrared" in uri || ":ir" in uri -> Protocol.INFRARED
            "433" in uri || "rf433" in uri -> Protocol.RF_433
            "868" in uri -> Protocol.RF_868
            "315" in uri -> Protocol.RF_315
            "enocean" in uri -> Protocol.ENOCEAN
            "bluetooth" in uri || ":ble" in uri -> Protocol.BLE
            "knx" in uri -> Protocol.KNX
            "modbus" in uri -> Protocol.MODBUS_TCP
            "insteon" in uri -> Protocol.INSTEON
            "x10" in uri -> Protocol.X10
            "lora" in uri -> Protocol.LORAWAN
            "mqtt" in uri -> Protocol.MQTT
            "hue" in uri -> Protocol.PHILIPS_HUE
            "sonos" in uri -> Protocol.SONOS
            "lifx" in uri -> Protocol.LIFX_LAN
            "nanoleaf" in uri -> Protocol.NANOLEAF
            "tuya" in uri -> Protocol.TUYA_LAN
            "shelly" in uri -> Protocol.SHELLY
            "tasmota" in uri -> Protocol.TASMOTA
            "kasa" in uri || "tplink" in uri || "tp-link" in uri -> Protocol.KASA
            "wiz" in uri -> Protocol.WIZ
            "yeelight" in uri -> Protocol.YEELIGHT
            "govee" in uri -> Protocol.GOVEE_LAN
            "switchbot" in uri -> Protocol.SWITCHBOT
            "chromecast" in uri || "googlecast" in uri -> Protocol.CHROMECAST
            "homekit" in uri -> Protocol.HOMEKIT
            "esphome" in uri -> Protocol.ESPHOME
            "xiaomi" in uri || "miio" in uri -> Protocol.MIIO
            "virtual" in uri || "devicecapabilities" in uri -> Protocol.HOMEY
            // Anything left that Homey reaches over the internet rather than a radio.
            "cloud" in uri || "webhook" in uri -> Protocol.CLOUD_ONLY
            else -> Protocol.HOMEY
        }
    }

    private fun inferManufacturer(device: HomeyDeviceDto): String? {
        val appId = device.driverUri
            ?.substringAfter("homey:app:", "")
            ?.takeIf { it.isNotBlank() }
            ?: return null

        // App ids are reverse-DNS, e.g. com.philips.hue → "philips".
        val parts = appId.split('.')
        val meaningful = parts.getOrNull(1)?.takeIf { it.length > 2 && it !in GENERIC_APP_SEGMENTS }
            ?: parts.lastOrNull()

        return meaningful
            ?.replace('-', ' ')
            ?.replaceFirstChar { it.uppercase() }
            ?.takeIf { it.length in 2..24 }
    }

    private fun buildAttributes(
        device: HomeyDeviceDto,
        zoneName: String?,
        homeyAddress: String,
        protocol: Protocol,
    ): Map<String, String> = buildMap {
        put("Homey device ID", device.id)
        put("Homey", homeyAddress)
        zoneName?.let { put("Zone", it) }
        device.deviceClass?.let { put("Homey class", it) }
        device.virtualClass?.takeIf { it != device.deviceClass }?.let { put("Virtual class", it) }
        device.driverUri?.let { put("Driver", it) }
        device.driverId?.let { put("Driver ID", it) }
        put("Available", device.available.toString())
        put("Transport", "${protocol.displayName} (${protocol.reachability.label})")
        device.note?.takeIf { it.isNotBlank() }?.let { put("Note", it) }
        if (device.capabilities.isNotEmpty()) {
            put("Capabilities", device.capabilities.joinToString(", "))
        }
        device.settings.settingString("zw_node_id")?.let { put("Z-Wave node ID", it) }
        device.settings.settingString("zw_manufacturer_id")?.let { put("Z-Wave manufacturer ID", it) }
        device.settings.settingString("zb_ieee_address")?.let { put("Zigbee IEEE address", it) }
        device.settings.settingString("zb_device_id")?.let { put("Zigbee device ID", it) }
    }

    /** Lower rank sorts first; anything unlisted falls to the bottom in alphabetical order. */
    private fun orderRank(capabilityId: String): Int {
        val index = CAPABILITY_ORDER.indexOfFirst { prefix -> capabilityId.startsWith(prefix) }
        return if (index >= 0) index else CAPABILITY_ORDER.size
    }

    private fun prettifyCapabilityId(id: String): String = id
        .substringBefore('.')
        .replace('_', ' ')
        .replaceFirstChar { it.uppercase() }

    /** Puts the controls a person actually reaches for at the top of the detail pane. */
    private val CAPABILITY_ORDER = listOf(
        "onoff", "dim", "light_hue", "light_saturation", "light_temperature", "light_mode",
        "target_temperature", "thermostat_mode", "windowcoverings", "volume", "speaker",
        "measure_temperature", "measure_humidity", "measure_power", "meter_power",
        "measure_battery", "alarm_",
    )

    private val GENERIC_APP_SEGMENTS = setOf("app", "apps", "homey", "athom", "smart", "io", "co")
}
