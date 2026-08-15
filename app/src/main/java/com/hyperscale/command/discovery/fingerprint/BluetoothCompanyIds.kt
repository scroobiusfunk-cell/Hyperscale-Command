package com.hyperscale.command.discovery.fingerprint

/**
 * Bluetooth SIG 16-bit company identifiers, curated to the vendors that turn up in a home.
 *
 * The same numbering space is reused by Matter for vendor IDs, so this table doubles as the
 * Matter vendor lookup in [com.hyperscale.command.discovery.scanners.BleScanner].
 */
object BluetoothCompanyIds {

    fun nameFor(companyId: Int): String? = COMPANIES[companyId]

    private val COMPANIES: Map<Int, String> = mapOf(
        0x0001 to "Nokia",
        0x0002 to "Intel",
        0x0006 to "Microsoft",
        0x000F to "Broadcom",
        0x004C to "Apple",
        0x0059 to "Nordic Semiconductor",
        0x0075 to "Samsung",
        0x0087 to "Garmin",
        0x00E0 to "Google",
        0x0110 to "Sonos",
        0x0131 to "Cypress",
        0x0157 to "Govee (Shenzhen Intellirocks)",
        0x0171 to "Amazon",
        0x0180 to "Xiaomi",
        0x01A9 to "SwitchBot (Woan)",
        0x01D7 to "Wyze",
        0x0224 to "Anker / eufy",
        0x0253 to "Espressif",
        0x02E0 to "Tuya",
        0x02FF to "Silicon Labs",
        0x0310 to "Signify (Philips Hue)",
        0x0362 to "Aqara (Lumi)",
        0x03DA to "Shelly (Allterco)",
        0x0499 to "Ruuvi",
        0x0500 to "Athom (Homey)",
        0x0757 to "LIFX",
        0x075B to "Nanoleaf",
        0x0822 to "Ring",
        0x08A1 to "Ecobee",
        0x0A05 to "Yale",
        0x0C0B to "August Home",
        0x1000 to "Matter reserved",
        0x1049 to "Netatmo",
        0x2323 to "iRobot",
        0xFFF1 to "Matter test vendor",
    )
}
