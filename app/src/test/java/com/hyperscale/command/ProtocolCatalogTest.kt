package com.hyperscale.command

import com.hyperscale.command.core.model.Protocol
import com.hyperscale.command.core.model.ProtocolCatalog
import com.hyperscale.command.core.model.Reachability
import com.hyperscale.command.discovery.fingerprint.OuiDatabase
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

class ProtocolCatalogTest {

    @Test
    fun `catalogue covers the protocols a mixed-brand home accumulates`() {
        assertTrue(
            "Expected a broad catalogue, got ${ProtocolCatalog.all.size}",
            ProtocolCatalog.all.size >= 60,
        )
        assertTrue(ProtocolCatalog.all.all { it.summary.isNotBlank() })
    }

    /**
     * The direct/hub split is a promise the UI makes to the user, so it must be total and
     * unambiguous: every protocol is in exactly one bucket.
     */
    @Test
    fun `direct and hub-only partition the catalogue exactly`() {
        assertEquals(
            ProtocolCatalog.all.size,
            ProtocolCatalog.directlyScannable.size + ProtocolCatalog.hubOnly.size,
        )
        assertTrue(
            ProtocolCatalog.directlyScannable
                .intersect(ProtocolCatalog.hubOnly.toSet())
                .isEmpty(),
        )
    }

    @Test
    fun `protocols with no phone radio are marked hub-only`() {
        listOf(
            Protocol.ZIGBEE,
            Protocol.ZWAVE,
            Protocol.ZWAVE_LR,
            Protocol.RF_433,
            Protocol.RF_868,
            Protocol.RF_315,
            Protocol.ENOCEAN,
            Protocol.X10,
            Protocol.INSTEON,
        ).forEach { protocol ->
            assertEquals(
                "${protocol.displayName} must be hub-bridged",
                Reachability.HUB_BRIDGED,
                protocol.reachability,
            )
        }
    }

    @Test
    fun `protocols the handset can genuinely scan are not marked hub-only`() {
        listOf(Protocol.MDNS, Protocol.SSDP, Protocol.BLE, Protocol.MATTER, Protocol.KNX)
            .forEach { protocol ->
                assertTrue(
                    "${protocol.displayName} should be scannable from the phone",
                    protocol in ProtocolCatalog.directlyScannable,
                )
            }
    }

    @Test
    fun `service type lookup resolves the ecosystems we advertise support for`() {
        assertEquals(Protocol.CHROMECAST, ProtocolCatalog.forServiceType("_googlecast._tcp"))
        assertEquals(Protocol.HOMEKIT, ProtocolCatalog.forServiceType("_hap._tcp."))
        assertEquals(Protocol.HOMEY, ProtocolCatalog.forServiceType("_homey._tcp"))
        assertEquals(Protocol.ESPHOME, ProtocolCatalog.forServiceType("_esphomelib._tcp"))
        assertNull(ProtocolCatalog.forServiceType("_definitely-not-real._tcp"))
    }

    @Test
    fun `service types are unique so a record maps to one protocol`() {
        val all = ProtocolCatalog.allServiceTypes
        assertEquals(all.size, all.distinct().size)
    }

    @Test
    fun `port lookup finds the protocols behind well-known ports`() {
        assertTrue(Protocol.MQTT in ProtocolCatalog.forPort(1883))
        assertTrue(Protocol.KNX in ProtocolCatalog.forPort(3671))
        assertTrue(Protocol.MODBUS_TCP in ProtocolCatalog.forPort(502))
        assertTrue(ProtocolCatalog.forPort(65000).isEmpty())
    }
}

class OuiDatabaseTest {

    @Test
    fun `resolves vendors regardless of separator or case`() {
        assertEquals("Espressif", OuiDatabase.vendorFor("24:0A:C4:11:22:33"))
        assertEquals("LIFX", OuiDatabase.vendorFor("d0-73-d5-aa-bb-cc"))
        assertEquals("Philips Hue", OuiDatabase.vendorFor("00:17:88:01:02:03"))
    }

    /**
     * Randomised (locally administered) addresses carry no vendor meaning. Reporting one would be
     * actively misleading, and using it as an identity key would fragment the device list every
     * time the address rotated.
     */
    @Test
    fun `locally administered addresses are reported as randomised`() {
        assertEquals("Randomised address", OuiDatabase.vendorFor("02:11:22:33:44:55"))
        assertTrue(OuiDatabase.isRandomised("da:a1:19:00:00:01"))
        assertFalse(OuiDatabase.isRandomised("24:0a:c4:00:00:01"))
    }

    @Test
    fun `unknown and malformed input yields no vendor rather than a wrong one`() {
        assertNull(OuiDatabase.vendorFor("aa:bb"))
        assertNull(OuiDatabase.vendorFor(""))
        assertNull(OuiDatabase.vendorFor("zz:zz:zz:zz:zz:zz"))
    }

    @Test
    fun `known smart home silicon resolves`() {
        assertNotNull(OuiDatabase.vendorFor("b8:27:eb:00:00:01"))
        assertNotNull(OuiDatabase.vendorFor("00:0e:58:00:00:01"))
    }
}
