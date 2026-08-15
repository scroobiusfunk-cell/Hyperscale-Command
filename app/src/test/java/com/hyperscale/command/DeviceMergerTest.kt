package com.hyperscale.command

import com.hyperscale.command.core.model.Device
import com.hyperscale.command.core.model.DeviceClass
import com.hyperscale.command.core.model.DeviceStatus
import com.hyperscale.command.core.model.DiscoverySource
import com.hyperscale.command.core.model.Observation
import com.hyperscale.command.core.model.Protocol
import com.hyperscale.command.discovery.DeviceMerger
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNotEquals
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * The merger is the load-bearing piece of multi-protocol discovery: without it, one speaker seen
 * over mDNS, SSDP, ARP and Homey shows up as four rows and the app is worse than useless.
 */
class DeviceMergerTest {

    private fun observation(
        protocol: Protocol,
        source: DiscoverySource,
        keys: Set<String>,
        ip: String? = null,
        mac: String? = null,
        name: String? = null,
        model: String? = null,
        attributes: Map<String, String> = emptyMap(),
        seenAt: Long = 1_000L,
    ) = Observation(
        protocol = protocol,
        source = source,
        identityKeys = keys,
        ipAddress = ip,
        macAddress = mac,
        displayName = name,
        model = model,
        attributes = attributes,
        seenAtMillis = seenAt,
    )

    @Test
    fun `one device seen over four protocols collapses to a single row`() {
        val merger = DeviceMerger()

        merger.absorb(
            observation(
                Protocol.CHROMECAST, DiscoverySource.MDNS,
                setOf("mdns:living room speaker|_googlecast._tcp"),
                ip = "192.168.1.50", name = "Living Room speaker", model = "Nest Audio",
            ),
        )
        merger.absorb(observation(Protocol.SSDP, DiscoverySource.SSDP, setOf("udn:uuid-abc"), ip = "192.168.1.50"))
        merger.absorb(
            observation(
                Protocol.WIFI, DiscoverySource.ARP,
                setOf("ip:192.168.1.50", "mac:f4:f5:d8:11:22:33"),
                ip = "192.168.1.50", mac = "f4:f5:d8:11:22:33",
            ),
        )
        merger.absorb(
            observation(
                Protocol.HOMEY, DiscoverySource.HOMEY,
                setOf("homey:dev-1", "mac:f4:f5:d8:11:22:33"), name = "Kitchen Speaker",
            ),
        )

        val devices = merger.snapshot()
        assertEquals(1, devices.size)

        val device = devices.single()
        assertEquals("192.168.1.50", device.ipAddress)
        assertEquals("f4:f5:d8:11:22:33", device.macAddress)
        assertEquals(4, device.sources.size)
        assertTrue("homey:dev-1" in device.identityKeys)
        assertEquals(DeviceClass.SPEAKER, device.deviceClass)
    }

    /**
     * A bare Wi-Fi/ARP sighting must never out-rank a specific protocol when labelling a device,
     * or every row in the list would read "Wi-Fi".
     */
    @Test
    fun `specific protocols outrank generic ones in the label`() {
        val merger = DeviceMerger()
        merger.absorb(observation(Protocol.WIFI, DiscoverySource.ARP, setOf("ip:10.0.0.4"), ip = "10.0.0.4"))
        merger.absorb(observation(Protocol.PHILIPS_HUE, DiscoverySource.MDNS, setOf("ip:10.0.0.4"), ip = "10.0.0.4"))

        val device = merger.snapshot().single()
        assertEquals(Protocol.PHILIPS_HUE, device.primaryProtocol)
        assertNotEquals(Protocol.WIFI, device.primaryProtocol)
    }

    @Test
    fun `unrelated devices are not merged`() {
        val merger = DeviceMerger()
        merger.absorb(observation(Protocol.MDNS, DiscoverySource.MDNS, setOf("ip:10.0.0.5"), ip = "10.0.0.5"))
        merger.absorb(observation(Protocol.MDNS, DiscoverySource.MDNS, setOf("ip:10.0.0.6"), ip = "10.0.0.6"))
        assertEquals(2, merger.snapshot().size)
    }

    /**
     * Merging must be transitive: an observation that shares one key with record A and another
     * with record B proves A and B are the same device.
     */
    @Test
    fun `a bridging observation coalesces two previously separate records`() {
        val merger = DeviceMerger()
        merger.absorb(observation(Protocol.MDNS, DiscoverySource.MDNS, setOf("ip:10.0.0.9")))
        merger.absorb(observation(Protocol.SSDP, DiscoverySource.SSDP, setOf("udn:xyz")))
        assertEquals(2, merger.snapshot().size)

        merger.absorb(
            observation(Protocol.HTTP, DiscoverySource.PORT_PROBE, setOf("ip:10.0.0.9", "udn:xyz")),
        )
        assertEquals(1, merger.snapshot().size)
    }

    @Test
    fun `nicknames and favourites survive a re-scan`() {
        val merger = DeviceMerger()
        merger.seed(
            listOf(
                Device(
                    id = "ip:10.0.0.7",
                    name = "Old discovered name",
                    nickname = "Hallway lamp",
                    isFavourite = true,
                    identityKeys = setOf("ip:10.0.0.7"),
                    firstSeenMillis = 1L,
                    lastSeenMillis = 1L,
                ),
            ),
        )

        merger.absorb(
            observation(Protocol.PHILIPS_HUE, DiscoverySource.MDNS, setOf("ip:10.0.0.7"), ip = "10.0.0.7", seenAt = 5_000L),
        )

        val device = merger.snapshot().single()
        assertEquals("Hallway lamp", device.nickname)
        assertEquals("Hallway lamp", device.displayName)
        assertTrue(device.isFavourite)
        assertEquals(5_000L, device.lastSeenMillis)
    }

    @Test
    fun `devices age out to offline and recover when seen again`() {
        val merger = DeviceMerger()
        merger.absorb(observation(Protocol.MDNS, DiscoverySource.MDNS, setOf("ip:10.0.0.8"), ip = "10.0.0.8", seenAt = 0L))

        merger.ageOut(
            nowMillis = 40 * 60_000L,
            staleAfterMillis = 5 * 60_000L,
            offlineAfterMillis = 30 * 60_000L,
        )
        assertEquals(DeviceStatus.OFFLINE, merger.snapshot().single().status)

        merger.ageOut(
            nowMillis = 10 * 60_000L,
            staleAfterMillis = 5 * 60_000L,
            offlineAfterMillis = 30 * 60_000L,
        )
        assertEquals(DeviceStatus.RECENTLY_SEEN, merger.snapshot().single().status)

        merger.absorb(
            observation(Protocol.MDNS, DiscoverySource.MDNS, setOf("ip:10.0.0.8"), ip = "10.0.0.8", seenAt = 41 * 60_000L),
        )
        assertEquals(DeviceStatus.ONLINE, merger.snapshot().single().status)
    }

    @Test
    fun `fingerprinter classifies by name, vendor keyword and HomeKit category`() {
        val merger = DeviceMerger()

        merger.absorb(
            observation(Protocol.MDNS, DiscoverySource.MDNS, setOf("ip:10.1.1.1"), ip = "10.1.1.1", name = "Front Door Lock"),
        )
        assertEquals(DeviceClass.LOCK, merger.snapshot().single().deviceClass)

        val second = DeviceMerger()
        second.absorb(
            observation(
                Protocol.MDNS, DiscoverySource.MDNS, setOf("ip:10.1.1.2"),
                ip = "10.1.1.2", name = "Shelly Plus 1PM",
                // HomeKit accessory category 7 = outlet. Authoritative, so it beats the keywords.
                attributes = mapOf("ci" to "7"),
            ),
        )
        val shelly = second.snapshot().single()
        assertEquals(DeviceClass.PLUG, shelly.deviceClass)
        assertEquals("Shelly", shelly.manufacturer)
    }

    @Test
    fun `an un-bridged device is not reported as controllable`() {
        val merger = DeviceMerger()
        merger.absorb(observation(Protocol.PHILIPS_HUE, DiscoverySource.MDNS, setOf("ip:192.168.1.60"), ip = "192.168.1.60"))
        assertFalse(merger.snapshot().single().isControllable)
    }
}
