package com.hyperscale.command

import com.hyperscale.command.core.model.Capability
import com.hyperscale.command.core.model.CapabilityType
import com.hyperscale.command.core.model.CapabilityValue
import com.hyperscale.command.core.model.Device
import com.hyperscale.command.core.model.DeviceClass
import com.hyperscale.command.core.model.DiscoverySource
import com.hyperscale.command.core.model.Protocol
import com.hyperscale.command.discovery.NetworkEnvironment
import com.hyperscale.command.homey.HomeyDeviceDto
import com.hyperscale.command.homey.HomeyDeviceMapper
import kotlinx.serialization.builtins.ListSerializer
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.JsonObject
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test
import java.net.Inet4Address
import java.net.InetAddress

class HomeyMappingTest {

    private val json = Json {
        ignoreUnknownKeys = true
        isLenient = true
        coerceInputValues = true
        explicitNulls = false
    }

    /** A realistic slice of what Homey Pro's local API returns from /api/manager/devices/device/. */
    private val payload = """
    {
      "result": {
        "abc-123": {
          "id": "abc-123",
          "name": "Hallway Motion",
          "driverUri": "homey:app:com.athom.zigbee",
          "zone": "zone-1",
          "class": "sensor",
          "available": true,
          "capabilities": ["alarm_motion", "measure_battery"],
          "capabilitiesObj": {
            "alarm_motion": {"id":"alarm_motion","type":"boolean","title":{"en":"Motion"},"value":true,"setable":false},
            "measure_battery": {"id":"measure_battery","type":"number","title":"Battery","units":"%","value":87,"min":0,"max":100,"setable":false}
          },
          "settings": { "zb_ieee_address": "00:12:4B:00:11:22:33:44" }
        },
        "def-456": {
          "id": "def-456",
          "name": "Lounge Lamp",
          "driverUri": "homey:app:com.philips.hue",
          "zone": "zone-2",
          "class": "light",
          "capabilitiesObj": {
            "onoff": {"id":"onoff","type":"boolean","title":"On","value":false,"setable":true},
            "dim": {"id":"dim","type":"number","title":"Dim","value":0.42,"min":0,"max":1,"step":0.01,"setable":true}
          },
          "settings": { "zw_node_id": "12" }
        }
      }
    }
    """.trimIndent()

    private fun parse(): List<HomeyDeviceDto> {
        val result = (json.parseToJsonElement(payload) as JsonObject)["result"] as JsonObject
        return result.values.map { json.decodeFromJsonElement(HomeyDeviceDto.serializer(), it) }
    }

    private val zones = mapOf("zone-1" to "Hallway", "zone-2" to "Lounge")

    @Test
    fun `parses the result envelope Homey wraps collections in`() {
        assertEquals(2, parse().size)
    }

    /**
     * Radio attribution comes from the settings keys Homey's own radio managers write, not from
     * guessing at the driver URI — an app id like `com.philips.hue` names the ecosystem, not the
     * transport, and here the device is genuinely on Z-Wave.
     */
    @Test
    fun `radio settings are stronger evidence than the driver URI`() {
        val lamp = parse().first { it.id == "def-456" }
        val observation = HomeyDeviceMapper.toObservation(lamp, zones, "192.168.1.20")
        assertEquals(Protocol.ZWAVE, observation.protocol)
    }

    @Test
    fun `zigbee devices are attributed from their IEEE address`() {
        val motion = parse().first { it.id == "abc-123" }
        val observation = HomeyDeviceMapper.toObservation(motion, zones, "192.168.1.20")

        assertEquals(Protocol.ZIGBEE, observation.protocol)
        assertEquals(DiscoverySource.HOMEY, observation.source)
        assertTrue("homey:abc-123" in observation.identityKeys)
        assertTrue(observation.identityKeys.any { it.startsWith("ieee:") })
        assertEquals("Hallway", observation.attributes["Zone"])
        assertTrue(observation.attributes["Transport"]?.contains("Via hub") == true)
    }

    @Test
    fun `capability titles are read whether localised or plain`() {
        val motion = parse().first { it.id == "abc-123" }
        val capabilities = HomeyDeviceMapper.toCapabilities(motion)

        assertEquals(2, capabilities.size)
        assertEquals("Motion", capabilities.first { it.id == "alarm_motion" }.title)
        assertEquals("Battery", capabilities.first { it.id == "measure_battery" }.title)
    }

    @Test
    fun `capability values and ranges are read correctly`() {
        val motion = parse().first { it.id == "abc-123" }
        val battery = HomeyDeviceMapper.toCapabilities(motion).first { it.id == "measure_battery" }
        assertEquals(87.0, (battery.value as CapabilityValue.Num).value, 0.001)
        assertEquals("%", battery.unit)
        assertFalse(battery.settable)

        val lamp = parse().first { it.id == "def-456" }
        val dim = HomeyDeviceMapper.toCapabilities(lamp).first { it.id == "dim" }
        assertEquals(0.0, dim.min!!, 0.001)
        assertEquals(1.0, dim.max!!, 0.001)
        assertEquals(0.01, dim.step!!, 0.0001)
        assertTrue(dim.settable)
    }

    /** The control a person reaches for first should be the first control on screen. */
    @Test
    fun `on-off sorts ahead of dim`() {
        val lamp = parse().first { it.id == "def-456" }
        assertEquals("onoff", HomeyDeviceMapper.toCapabilities(lamp).first().id)
    }

    @Test
    fun `homey device classes map onto app device classes`() {
        assertEquals(DeviceClass.LIGHT, HomeyDeviceMapper.toDeviceClass(parse().first { it.id == "def-456" }))
        assertEquals(DeviceClass.SENSOR, HomeyDeviceMapper.toDeviceClass(parse().first { it.id == "abc-123" }))
    }

    @Test
    fun `a device gains controls once Homey capabilities are attached`() {
        val discovered = Device(id = "ip:192.168.1.60", name = "Hue bulb")
        assertFalse(discovered.isControllable)

        val bridged = discovered.copy(
            homeyDeviceId = "hue-1",
            capabilities = listOf(
                Capability("onoff", "On", CapabilityType.BOOLEAN, CapabilityValue.Bool(true), settable = true),
            ),
        )
        assertTrue(bridged.isControllable)
        assertEquals(true, bridged.isOn)
    }
}

class NetworkEnvironmentTest {

    private fun env(address: String, prefix: Int) = NetworkEnvironment(
        localAddress = InetAddress.getByName(address) as Inet4Address,
        prefixLength = prefix,
        broadcastAddress = null,
        interfaceName = "wlan0",
        isWifi = true,
        isMetered = false,
        ssid = "Home",
    )

    @Test
    fun `a slash 24 sweep covers every host and excludes network and broadcast`() {
        val hosts = env("192.168.1.37", 24).hostAddresses()
        assertEquals(254, hosts.size)
        assertEquals("192.168.1.1", hosts.first())
        assertEquals("192.168.1.254", hosts.last())
        assertFalse("192.168.1.0" in hosts)
        assertFalse("192.168.1.255" in hosts)
    }

    @Test
    fun `directed broadcast is computed from the prefix`() {
        assertEquals("192.168.1.255", env("192.168.1.37", 24).directedBroadcast())
        assertEquals("10.0.255.255", env("10.0.5.9", 16).directedBroadcast())
    }

    /** A /16 is 65k probes. Capping keeps a scan polite and finite on an odd network. */
    @Test
    fun `large subnets are capped rather than swept exhaustively`() {
        assertEquals(NetworkEnvironment.MAX_SWEEP_HOSTS, env("10.0.5.9", 16).hostAddresses().size)
    }

    @Test
    fun `an unusable environment yields nothing rather than guessing`() {
        assertFalse(NetworkEnvironment.Unavailable.isUsable)
        assertTrue(NetworkEnvironment.Unavailable.hostAddresses().isEmpty())
        assertEquals(null, NetworkEnvironment.Unavailable.directedBroadcast())
    }
}

class DeviceSerializationTest {

    private val json = Json { ignoreUnknownKeys = true; encodeDefaults = true }

    @Test
    fun `the device store round-trips every capability value shape`() {
        val original = listOf(
            Device(
                id = "mac:aa:bb:cc:dd:ee:ff",
                name = "Test",
                nickname = "My thing",
                deviceClass = DeviceClass.BLINDS,
                protocols = listOf(Protocol.ZWAVE, Protocol.HOMEY),
                sources = setOf(DiscoverySource.HOMEY),
                capabilities = listOf(
                    Capability("onoff", "On", CapabilityType.BOOLEAN, CapabilityValue.Bool(false), settable = true),
                    Capability("dim", "Dim", CapabilityType.NUMBER, CapabilityValue.Num(0.5), settable = true),
                    Capability("mode", "Mode", CapabilityType.ENUM, CapabilityValue.Text("auto"), settable = true),
                    Capability("gone", "Gone", CapabilityType.STRING, CapabilityValue.Absent, settable = false),
                ),
                attributes = mapOf("a" to "b"),
                identityKeys = setOf("mac:aa:bb:cc:dd:ee:ff"),
                isFavourite = true,
            ),
        )

        val encoded = json.encodeToString(ListSerializer(Device.serializer()), original)
        val decoded = json.decodeFromString(ListSerializer(Device.serializer()), encoded)

        assertEquals(original, decoded)
        assertEquals(
            listOf("Bool", "Num", "Text", "Absent"),
            decoded.single().capabilities.map { it.value::class.simpleName },
        )
    }

    @Test
    fun `search matches across every identifying field`() {
        val device = Device(
            id = "x",
            name = "Boiler controller",
            manufacturer = "Honeywell",
            ipAddress = "192.168.1.44",
            macAddress = "b8:2c:a0:00:11:22",
            protocols = listOf(Protocol.ZWAVE),
            deviceClass = DeviceClass.THERMOSTAT,
        )

        listOf("boiler", "honeywell", "1.44", "b8:2c", "z-wave", "climate", "").forEach {
            assertTrue("Expected '$it' to match", device.matches(it))
        }
        assertFalse(device.matches("sonos"))
    }
}
