package com.hyperscale.command.discovery.fingerprint

import com.hyperscale.command.core.model.Device
import com.hyperscale.command.core.model.DeviceClass
import com.hyperscale.command.core.model.Observation
import com.hyperscale.command.core.model.Protocol

/**
 * Turns accumulated evidence into an identity: who made this, what is it, what should it be called.
 *
 * Runs on every observation, so it must be cheap and idempotent. It only ever *fills in* unknowns
 * or improves on a weaker guess; it never overwrites something the user set or a strong signal
 * with a weak one.
 */
object Fingerprinter {

    fun identify(device: Device, observation: Observation): Device {
        val manufacturer = device.manufacturer
            ?: inferManufacturer(device, observation)

        val deviceClass = if (device.deviceClass != DeviceClass.OTHER) {
            device.deviceClass
        } else {
            inferDeviceClass(device, observation, manufacturer)
        }

        return device.copy(
            manufacturer = manufacturer,
            deviceClass = deviceClass,
        )
    }

    private fun inferManufacturer(device: Device, observation: Observation): String? {
        device.macAddress?.let { mac ->
            OuiDatabase.vendorFor(mac)?.takeIf { it != "Randomised address" }?.let { return it }
        }

        val haystack = haystackOf(device, observation)
        VENDOR_KEYWORDS.forEach { (keyword, vendor) ->
            if (keyword in haystack) return vendor
        }

        // Fall back to the protocol itself when it implies exactly one vendor.
        return when (device.primaryProtocol) {
            Protocol.PHILIPS_HUE, Protocol.HUE_ENTERTAINMENT -> "Philips Hue"
            Protocol.SONOS -> "Sonos"
            Protocol.LIFX_LAN -> "LIFX"
            Protocol.NANOLEAF -> "Nanoleaf"
            Protocol.KASA -> "TP-Link"
            Protocol.WIZ -> "WiZ"
            Protocol.TUYA_LAN -> "Tuya"
            Protocol.SHELLY -> "Shelly"
            Protocol.MIIO -> "Xiaomi"
            Protocol.SWITCHBOT -> "SwitchBot"
            Protocol.WEMO -> "Belkin"
            Protocol.ROKU_ECP -> "Roku"
            Protocol.WEBOS -> "LG"
            Protocol.SAMSUNG_TIZEN, Protocol.SMARTTHINGS -> "Samsung"
            Protocol.HOMEY -> "Athom"
            Protocol.LUTRON -> "Lutron"
            Protocol.CRESTRON -> "Crestron"
            else -> null
        }
    }

    private fun inferDeviceClass(
        device: Device,
        observation: Observation,
        manufacturer: String?,
    ): DeviceClass {
        val haystack = haystackOf(device, observation) + " " + manufacturer.orEmpty().lowercase()

        // Explicit type declarations beat keyword guessing. HomeKit publishes an accessory
        // category integer in its mDNS TXT record, which is authoritative.
        homekitCategory(observation)?.let { return it }

        CLASS_KEYWORDS.forEach { (keyword, deviceClass) ->
            if (keyword in haystack) return deviceClass
        }

        return when (device.primaryProtocol) {
            Protocol.PHILIPS_HUE, Protocol.LIFX_LAN, Protocol.NANOLEAF,
            Protocol.WIZ, Protocol.YEELIGHT, Protocol.HUE_ENTERTAINMENT,
            -> DeviceClass.LIGHT

            Protocol.KASA -> DeviceClass.PLUG
            Protocol.SONOS, Protocol.SPOTIFY_CONNECT, Protocol.AIRPLAY -> DeviceClass.SPEAKER
            Protocol.CHROMECAST, Protocol.ROKU_ECP, Protocol.WEBOS, Protocol.SAMSUNG_TIZEN,
            Protocol.DLNA,
            -> DeviceClass.TV

            Protocol.ONVIF, Protocol.RTSP -> DeviceClass.CAMERA
            Protocol.MODBUS_TCP, Protocol.BACNET, Protocol.KNX, Protocol.DALI -> DeviceClass.ENERGY
            Protocol.HOMEY, Protocol.HOME_ASSISTANT, Protocol.SMARTTHINGS,
            Protocol.MQTT, Protocol.ALEXA,
            -> DeviceClass.HUB

            Protocol.SWITCHBOT -> DeviceClass.SWITCH
            Protocol.ESPHOME, Protocol.TASMOTA, Protocol.SHELLY -> DeviceClass.SWITCH
            else -> DeviceClass.OTHER
        }
    }

    /** HomeKit accessory categories, per the HAP specification's `ci` TXT key. */
    private fun homekitCategory(observation: Observation): DeviceClass? {
        val raw = observation.attributes.entries
            .firstOrNull { it.key.equals("ci", ignoreCase = true) }
            ?.value
            ?.toIntOrNull()
            ?: return null

        return when (raw) {
            2 -> DeviceClass.OTHER      // Bridge
            3 -> DeviceClass.FAN
            5 -> DeviceClass.LIGHT
            6 -> DeviceClass.LOCK
            7 -> DeviceClass.PLUG
            8 -> DeviceClass.SWITCH
            9 -> DeviceClass.THERMOSTAT
            10 -> DeviceClass.SENSOR
            11, 12, 13 -> DeviceClass.SENSOR
            14 -> DeviceClass.BLINDS
            15 -> DeviceClass.BLINDS
            17 -> DeviceClass.CAMERA
            18 -> DeviceClass.DOORBELL
            19 -> DeviceClass.LOCK
            20, 21, 22 -> DeviceClass.SPEAKER
            26 -> DeviceClass.SPEAKER
            28 -> DeviceClass.TV
            29 -> DeviceClass.SPEAKER
            else -> null
        }
    }

    private fun haystackOf(device: Device, observation: Observation): String = buildString {
        append(device.name.lowercase()).append(' ')
        append(device.model.orEmpty().lowercase()).append(' ')
        append(device.hostname.orEmpty().lowercase()).append(' ')
        append(observation.displayName.orEmpty().lowercase()).append(' ')
        append(observation.model.orEmpty().lowercase()).append(' ')
        append(observation.manufacturer.orEmpty().lowercase()).append(' ')
        observation.attributes.forEach { (key, value) ->
            append(key.lowercase()).append(' ').append(value.lowercase()).append(' ')
        }
    }

    private val VENDOR_KEYWORDS: List<Pair<String, String>> = listOf(
        "philips hue" to "Philips Hue",
        "signify" to "Philips Hue",
        "hue bridge" to "Philips Hue",
        "sonos" to "Sonos",
        "shelly" to "Shelly",
        "tasmota" to "Tasmota",
        "esphome" to "ESPHome",
        "esp32" to "Espressif",
        "esp8266" to "Espressif",
        "tp-link" to "TP-Link",
        "tplink" to "TP-Link",
        "kasa" to "TP-Link",
        "tapo" to "TP-Link",
        "lifx" to "LIFX",
        "nanoleaf" to "Nanoleaf",
        "yeelight" to "Yeelight",
        "xiaomi" to "Xiaomi",
        "roborock" to "Roborock",
        "aqara" to "Aqara",
        "lumi" to "Aqara",
        "sonoff" to "Sonoff",
        "tuya" to "Tuya",
        "smart life" to "Tuya",
        "govee" to "Govee",
        "switchbot" to "SwitchBot",
        "ikea" to "IKEA",
        "tradfri" to "IKEA",
        "dirigera" to "IKEA",
        "netatmo" to "Netatmo",
        "tado" to "tado°",
        "nest" to "Google Nest",
        "chromecast" to "Google",
        "google home" to "Google",
        "amazon" to "Amazon",
        "echo" to "Amazon",
        "alexa" to "Amazon",
        "ring" to "Ring",
        "arlo" to "Arlo",
        "eufy" to "eufy",
        "wyze" to "Wyze",
        "reolink" to "Reolink",
        "hikvision" to "Hikvision",
        "dahua" to "Dahua",
        "ubiquiti" to "Ubiquiti",
        "unifi" to "Ubiquiti",
        "synology" to "Synology",
        "qnap" to "QNAP",
        "raspberry" to "Raspberry Pi",
        "homey" to "Athom",
        "athom" to "Athom",
        "homeassistant" to "Home Assistant",
        "home-assistant" to "Home Assistant",
        "hass" to "Home Assistant",
        "samsung" to "Samsung",
        "smartthings" to "Samsung SmartThings",
        "bravia" to "Sony",
        "webos" to "LG",
        "roku" to "Roku",
        "apple tv" to "Apple",
        "homepod" to "Apple",
        "airport" to "Apple",
        "ecobee" to "ecobee",
        "honeywell" to "Honeywell",
        "danfoss" to "Danfoss",
        "bosch" to "Bosch",
        "miele" to "Miele",
        "siemens" to "Siemens",
        "dyson" to "Dyson",
        "irobot" to "iRobot",
        "roomba" to "iRobot",
        "yale" to "Yale",
        "nuki" to "Nuki",
        "august" to "August",
        "somfy" to "Somfy",
        "velux" to "VELUX",
        "fibaro" to "Fibaro",
        "aeotec" to "Aeotec",
        "qubino" to "Qubino",
        "heatit" to "Heatit",
        "lutron" to "Lutron",
        "crestron" to "Crestron",
        "loxone" to "Loxone",
        "solaredge" to "SolarEdge",
        "fronius" to "Fronius",
        "growatt" to "Growatt",
        "victron" to "Victron",
        "zappi" to "myenergi",
        "easee" to "Easee",
        "wallbox" to "Wallbox",
        "tesla" to "Tesla",
    )

    private val CLASS_KEYWORDS: List<Pair<String, DeviceClass>> = listOf(
        "doorbell" to DeviceClass.DOORBELL,
        "camera" to DeviceClass.CAMERA,
        "cam" to DeviceClass.CAMERA,
        "lock" to DeviceClass.LOCK,
        "deadbolt" to DeviceClass.LOCK,
        "thermostat" to DeviceClass.THERMOSTAT,
        "radiator" to DeviceClass.THERMOSTAT,
        "trv" to DeviceClass.THERMOSTAT,
        "heatpump" to DeviceClass.THERMOSTAT,
        "boiler" to DeviceClass.THERMOSTAT,
        "climate" to DeviceClass.THERMOSTAT,
        "aircon" to DeviceClass.THERMOSTAT,
        "blind" to DeviceClass.BLINDS,
        "curtain" to DeviceClass.BLINDS,
        "shade" to DeviceClass.BLINDS,
        "roller" to DeviceClass.BLINDS,
        "awning" to DeviceClass.BLINDS,
        "garage" to DeviceClass.BLINDS,
        "vacuum" to DeviceClass.VACUUM,
        "roomba" to DeviceClass.VACUUM,
        "mop" to DeviceClass.VACUUM,
        "speaker" to DeviceClass.SPEAKER,
        "soundbar" to DeviceClass.SPEAKER,
        "sonos" to DeviceClass.SPEAKER,
        "homepod" to DeviceClass.SPEAKER,
        "echo" to DeviceClass.SPEAKER,
        "tv" to DeviceClass.TV,
        "television" to DeviceClass.TV,
        "display" to DeviceClass.TV,
        "projector" to DeviceClass.TV,
        "chromecast" to DeviceClass.TV,
        "shield" to DeviceClass.MEDIA,
        "apple tv" to DeviceClass.MEDIA,
        "plug" to DeviceClass.PLUG,
        "socket" to DeviceClass.PLUG,
        "outlet" to DeviceClass.PLUG,
        "bulb" to DeviceClass.LIGHT,
        "lamp" to DeviceClass.LIGHT,
        "light" to DeviceClass.LIGHT,
        "strip" to DeviceClass.LIGHT,
        "downlight" to DeviceClass.LIGHT,
        "spot" to DeviceClass.LIGHT,
        "dimmer" to DeviceClass.LIGHT,
        "switch" to DeviceClass.SWITCH,
        "relay" to DeviceClass.SWITCH,
        "button" to DeviceClass.SWITCH,
        "remote" to DeviceClass.SWITCH,
        "sensor" to DeviceClass.SENSOR,
        "motion" to DeviceClass.SENSOR,
        "contact" to DeviceClass.SENSOR,
        "temperature" to DeviceClass.SENSOR,
        "humidity" to DeviceClass.SENSOR,
        "leak" to DeviceClass.SENSOR,
        "smoke" to DeviceClass.SENSOR,
        "co2" to DeviceClass.SENSOR,
        "air quality" to DeviceClass.SENSOR,
        "fan" to DeviceClass.FAN,
        "purifier" to DeviceClass.FAN,
        "extractor" to DeviceClass.FAN,
        "washer" to DeviceClass.APPLIANCE,
        "dryer" to DeviceClass.APPLIANCE,
        "dishwasher" to DeviceClass.APPLIANCE,
        "fridge" to DeviceClass.APPLIANCE,
        "oven" to DeviceClass.APPLIANCE,
        "kettle" to DeviceClass.APPLIANCE,
        "coffee" to DeviceClass.APPLIANCE,
        "meter" to DeviceClass.ENERGY,
        "inverter" to DeviceClass.ENERGY,
        "solar" to DeviceClass.ENERGY,
        "battery" to DeviceClass.ENERGY,
        "charger" to DeviceClass.ENERGY,
        "charge point" to DeviceClass.ENERGY,
        "bridge" to DeviceClass.HUB,
        "hub" to DeviceClass.HUB,
        "gateway" to DeviceClass.HUB,
        "coordinator" to DeviceClass.HUB,
        "router" to DeviceClass.NETWORK,
        "switchport" to DeviceClass.NETWORK,
        "access point" to DeviceClass.NETWORK,
        "unifi" to DeviceClass.NETWORK,
        "nas" to DeviceClass.COMPUTER,
        "synology" to DeviceClass.COMPUTER,
        "raspberry" to DeviceClass.COMPUTER,
        "macbook" to DeviceClass.COMPUTER,
        "iphone" to DeviceClass.COMPUTER,
        "printer" to DeviceClass.PRINTER,
        "watch" to DeviceClass.WEARABLE,
        "band" to DeviceClass.WEARABLE,
        "tesla" to DeviceClass.VEHICLE,
    )
}
