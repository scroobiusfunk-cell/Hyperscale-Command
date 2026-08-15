package com.hyperscale.command.discovery.fingerprint

/**
 * MAC address OUI (Organisationally Unique Identifier) lookup.
 *
 * The full IEEE registry is ~35,000 entries and around 1 MB; shipping it would bloat the APK for
 * little gain, so this is a curated set covering the vendors that actually appear in a home. An
 * unmatched MAC simply yields no vendor rather than a wrong one.
 *
 * Locally-administered addresses (the second-least-significant bit of the first octet) are
 * randomised by the device and carry no vendor meaning — those are reported as such.
 */
object OuiDatabase {

    fun vendorFor(macAddress: String): String? {
        val normalised = macAddress
            .lowercase()
            .replace("-", ":")
            .replace(".", ":")
            .trim()

        val octets = normalised.split(":").filter { it.isNotBlank() }
        if (octets.size < 3) return null

        val firstOctet = octets[0].toIntOrNull(16) ?: return null
        if (firstOctet and 0x02 != 0) return "Randomised address"

        val prefix = octets.take(3).joinToString(":")
        return OUI_MAP[prefix]
    }

    fun isRandomised(macAddress: String): Boolean {
        val firstOctet = macAddress.split(':', '-').firstOrNull()?.toIntOrNull(16) ?: return false
        return firstOctet and 0x02 != 0
    }

    private val OUI_MAP: Map<String, String> = mapOf(
        // Hubs and controllers
        "00:1f:d4" to "Athom (Homey)",
        "48:5f:99" to "Athom (Homey)",
        "b0:c5:ca" to "Athom (Homey)",

        // Philips / Signify
        "00:17:88" to "Philips Hue",
        "ec:b5:fa" to "Philips Hue",

        // Amazon
        "44:65:0d" to "Amazon",
        "f0:27:2d" to "Amazon",
        "68:37:e9" to "Amazon",
        "50:dc:e7" to "Amazon",
        "fc:65:de" to "Amazon",
        "74:c2:46" to "Amazon",
        "ac:63:be" to "Amazon",

        // Google / Nest
        "f4:f5:d8" to "Google",
        "f4:f5:e8" to "Google",
        "da:a1:19" to "Google",
        "1c:f2:9a" to "Google",
        "3c:5a:b4" to "Google",
        "54:60:09" to "Google",
        "18:b4:30" to "Nest",
        "64:16:66" to "Nest",

        // Apple
        "00:1c:b3" to "Apple",
        "ac:bc:32" to "Apple",
        "f0:18:98" to "Apple",
        "a4:83:e7" to "Apple",
        "d0:81:7a" to "Apple",
        "90:b0:ed" to "Apple",

        // Samsung / SmartThings
        "00:12:fb" to "Samsung",
        "78:47:1d" to "Samsung",
        "d0:59:e4" to "Samsung",
        "5c:49:7d" to "Samsung",
        "8c:71:f8" to "Samsung",
        "94:51:03" to "Samsung",
        "d0:52:a8" to "SmartThings",
        "24:fd:5b" to "SmartThings",

        // Sonos
        "00:0e:58" to "Sonos",
        "34:7e:5c" to "Sonos",
        "48:a6:b8" to "Sonos",
        "5c:aa:fd" to "Sonos",
        "78:28:ca" to "Sonos",
        "b8:e9:37" to "Sonos",

        // TP-Link / Kasa / Tapo
        "50:c7:bf" to "TP-Link",
        "b0:4e:26" to "TP-Link",
        "1c:3b:f3" to "TP-Link",
        "98:da:c4" to "TP-Link",
        "a4:2b:b0" to "TP-Link",
        "cc:32:e5" to "TP-Link",
        "9c:a2:f4" to "TP-Link",

        // Espressif — the silicon under ESPHome, Tasmota, Shelly, Sonoff and countless others
        "24:0a:c4" to "Espressif",
        "24:6f:28" to "Espressif",
        "30:ae:a4" to "Espressif",
        "3c:71:bf" to "Espressif",
        "48:3f:da" to "Espressif",
        "5c:cf:7f" to "Espressif",
        "60:01:94" to "Espressif",
        "84:cc:a8" to "Espressif",
        "84:f3:eb" to "Espressif",
        "8c:aa:b5" to "Espressif",
        "a0:20:a6" to "Espressif",
        "a4:cf:12" to "Espressif",
        "b4:e6:2d" to "Espressif",
        "bc:dd:c2" to "Espressif",
        "c4:4f:33" to "Espressif",
        "cc:50:e3" to "Espressif",
        "d8:a0:1d" to "Espressif",
        "dc:4f:22" to "Espressif",
        "e8:db:84" to "Espressif",
        "ec:fa:bc" to "Espressif",

        // Shelly (Allterco)
        "e8:9f:6d" to "Shelly",
        "98:cd:ac" to "Shelly",
        "c8:2b:96" to "Shelly",
        "34:94:54" to "Shelly",

        // Tuya
        "10:d5:61" to "Tuya",
        "18:69:d8" to "Tuya",
        "68:57:2d" to "Tuya",
        "d8:1f:12" to "Tuya",
        "a4:c1:38" to "Telink (Tuya/Zigbee)",

        // LIFX
        "d0:73:d5" to "LIFX",

        // Nanoleaf
        "00:55:da" to "Nanoleaf",

        // Wyze / Ring / Arlo / Eufy
        "2c:aa:8e" to "Wyze",
        "7c:78:b2" to "Wyze",
        "00:62:6e" to "Ring",
        "54:e0:19" to "Ring",
        "b0:c5:54" to "Arlo",
        "3c:37:12" to "Arlo",
        "8c:85:80" to "Eufy / Anker",

        // Ecobee / Honeywell / Tado / Netatmo
        "44:61:32" to "ecobee",
        "b8:2c:a0" to "Honeywell",
        "5c:6b:32" to "Texas Instruments (Tado)",
        "70:ee:50" to "Netatmo",

        // Xiaomi / Aqara / Roborock
        "78:11:dc" to "Xiaomi",
        "64:b4:73" to "Xiaomi",
        "04:cf:8c" to "Xiaomi",
        "50:ec:50" to "Xiaomi",
        "54:ef:44" to "Aqara (Lumi)",

        // iRobot / Dyson / Miele / Bosch
        "80:a5:89" to "iRobot",
        "50:14:79" to "iRobot",
        "00:22:19" to "Dyson",
        "68:a4:0e" to "Miele",
        "68:a3:78" to "Bosch",

        // Network gear (frequently the first thing a sweep finds)
        "00:1a:2b" to "Ubiquiti",
        "24:5a:4c" to "Ubiquiti",
        "78:8a:20" to "Ubiquiti",
        "fc:ec:da" to "Ubiquiti",
        "b4:fb:e4" to "Ubiquiti",
        "00:05:ca" to "Netgear",
        "9c:3d:cf" to "Netgear",
        "a0:40:a0" to "Netgear",
        "00:1d:7e" to "Cisco-Linksys",
        "c0:56:27" to "Belkin",
        "94:10:3e" to "Belkin / WeMo",
        "b4:75:0e" to "Belkin / WeMo",
        "ec:1a:59" to "Belkin / WeMo",
        "00:26:5a" to "D-Link",
        "34:08:04" to "D-Link",
        "00:14:6c" to "Netgear",
        "dc:a6:32" to "Raspberry Pi",
        "b8:27:eb" to "Raspberry Pi",
        "e4:5f:01" to "Raspberry Pi",
        "28:cd:c1" to "Raspberry Pi",

        // AV
        "00:09:b0" to "Onkyo",
        "00:a0:de" to "Yamaha",
        "04:20:9a" to "Sony",
        "fc:f1:52" to "Sony",
        "00:1e:c7" to "LG Electronics",
        "cc:2d:8c" to "LG Electronics",
        "10:2c:6b" to "Roku",
        "b0:a7:37" to "Roku",
        "cc:6d:a0" to "Roku",
        "d8:31:34" to "Roku",
        "00:04:4b" to "NVIDIA (Shield)",
        "48:b0:2d" to "NVIDIA (Shield)",

        // Bulb and controller silicon
        "00:12:4b" to "Texas Instruments (Zigbee)",
        "00:0d:6f" to "Ember (Zigbee)",
        "90:fd:9f" to "Silicon Labs",
        "84:71:27" to "Silicon Labs",
        "58:8e:81" to "Nordic Semiconductor",
        "cc:cc:cc" to "Silicon Labs",
    )
}
