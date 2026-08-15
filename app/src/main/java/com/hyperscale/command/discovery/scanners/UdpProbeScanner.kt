package com.hyperscale.command.discovery.scanners

import android.content.Context
import android.net.wifi.WifiManager
import android.util.Log
import com.hyperscale.command.core.model.DiscoverySource
import com.hyperscale.command.core.model.Observation
import com.hyperscale.command.core.model.Protocol
import com.hyperscale.command.discovery.NetworkEnvironment
import com.hyperscale.command.discovery.ProtocolScanner
import com.hyperscale.command.discovery.ScanContext
import com.hyperscale.command.discovery.ScanDepth
import com.hyperscale.command.discovery.ScannerAvailability
import java.net.DatagramPacket
import java.net.DatagramSocket
import java.net.InetAddress
import java.net.InetSocketAddress
import java.net.MulticastSocket
import java.net.SocketTimeoutException
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.coroutineScope
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.channelFlow
import kotlinx.coroutines.flow.flowOn
import kotlinx.coroutines.launch

/**
 * Datagram-based discovery: the protocols that answer a broadcast or multicast probe, and the
 * ones that simply shout into the void and only need someone listening.
 *
 * Covers LIFX, TP-Link Kasa, WiZ, Tuya, Xiaomi miIO, KNXnet/IP, BACnet/IP, CoAP, MQTT-SN and
 * ONVIF WS-Discovery. Each probe runs in its own coroutine and is failure-isolated, so a
 * firewalled multicast group costs one protocol rather than the whole pass.
 */
class UdpProbeScanner : ProtocolScanner {

    override val id = "udp"
    override val label = "UDP broadcast & multicast"
    override val source = DiscoverySource.UDP_BROADCAST

    override val protocols = setOf(
        Protocol.LIFX_LAN, Protocol.KASA, Protocol.WIZ, Protocol.TUYA_LAN, Protocol.MIIO,
        Protocol.KNX, Protocol.BACNET, Protocol.COAP, Protocol.ONVIF, Protocol.MQTT_SN,
    )

    override fun availability(context: Context): ScannerAvailability =
        if (NetworkEnvironment.capture(context).isUsable) {
            ScannerAvailability.Ready
        } else {
            ScannerAvailability.Unavailable("Not connected to a local network")
        }

    override fun scan(scanContext: ScanContext): Flow<Observation> = channelFlow {
        val wifiManager = scanContext.context.applicationContext.getSystemService(WifiManager::class.java)
        val multicastLock = wifiManager?.createMulticastLock("hyperscale-udp")?.apply {
            setReferenceCounted(true)
            runCatching { acquire() }
        }

        val broadcast = scanContext.network.directedBroadcast() ?: "255.255.255.255"
        val probes = probesFor(scanContext.depth).filter { it.protocol in scanContext.enabledProtocols }
        val listenBudget = (scanContext.timeoutMillis - 500L).coerceIn(2_500L, 30_000L)

        try {
            // coroutineScope suspends until every probe has finished, which is what keeps the
            // multicast lock held for exactly as long as it is needed.
            coroutineScope {
                probes.forEach { probe ->
                    launch(Dispatchers.IO) {
                        runCatching {
                            runProbe(probe, broadcast, listenBudget) { observation -> trySend(observation) }
                        }.onFailure { error -> Log.d(TAG, "Probe ${probe.name} failed", error) }
                    }
                }
            }
        } finally {
            runCatching { multicastLock?.release() }
        }
    }.flowOn(Dispatchers.IO)

    private class UdpProbe(
        val name: String,
        val protocol: Protocol,
        /** null means "use the subnet directed broadcast". */
        val targetAddress: String?,
        val targetPort: Int,
        /** Bind locally to this port; required for protocols that reply to a fixed source port. */
        val bindPort: Int? = null,
        val multicastGroup: String? = null,
        val payload: ByteArray?,
        val parse: (source: String, data: ByteArray) -> ParsedResponse?,
    )

    private data class ParsedResponse(
        val displayName: String? = null,
        val manufacturer: String? = null,
        val model: String? = null,
        val firmwareVersion: String? = null,
        val serialNumber: String? = null,
        val macAddress: String? = null,
        val attributes: Map<String, String> = emptyMap(),
    )

    private fun runProbe(
        probe: UdpProbe,
        broadcast: String,
        budgetMillis: Long,
        emit: (Observation) -> Unit,
    ) {
        val socket: DatagramSocket = when {
            probe.multicastGroup != null -> MulticastSocket(probe.bindPort ?: 0).apply {
                reuseAddress = true
                // The InetAddress overload is deprecated on the JVM but is the correct API on
                // Android, where the SocketAddress form needs a NetworkInterface we cannot
                // reliably pick on a multi-homed handset.
                @Suppress("DEPRECATION")
                runCatching { joinGroup(InetAddress.getByName(probe.multicastGroup)) }
            }

            probe.bindPort != null -> DatagramSocket(null).apply {
                reuseAddress = true
                bind(InetSocketAddress(probe.bindPort))
            }

            else -> DatagramSocket()
        }

        try {
            socket.broadcast = true
            socket.soTimeout = SOCKET_POLL_MILLIS

            probe.payload?.let { payload ->
                val target = InetAddress.getByName(
                    probe.multicastGroup ?: probe.targetAddress ?: broadcast,
                )
                runCatching {
                    socket.send(DatagramPacket(payload, payload.size, target, probe.targetPort))
                }.onFailure { Log.d(TAG, "${probe.name}: send failed", it) }
            }

            val deadline = System.currentTimeMillis() + budgetMillis
            val buffer = ByteArray(8192)
            val seen = mutableSetOf<String>()

            while (System.currentTimeMillis() < deadline) {
                val packet = DatagramPacket(buffer, buffer.size)
                try {
                    socket.receive(packet)
                } catch (timeout: SocketTimeoutException) {
                    continue
                } catch (error: Exception) {
                    Log.d(TAG, "${probe.name}: receive failed", error)
                    break
                }

                val sourceIp = packet.address?.hostAddress ?: continue
                if (!seen.add(sourceIp)) continue

                val data = packet.data.copyOfRange(0, packet.length)
                val parsed = probe.parse(sourceIp, data) ?: continue

                emit(
                    Observation(
                        protocol = probe.protocol,
                        source = DiscoverySource.UDP_BROADCAST,
                        identityKeys = buildSet {
                            add("ip:$sourceIp")
                            parsed.macAddress?.let { add("mac:${it.lowercase()}") }
                            parsed.serialNumber?.let { add("serial:${it.lowercase()}") }
                        },
                        ipAddress = sourceIp,
                        macAddress = parsed.macAddress,
                        port = probe.targetPort,
                        displayName = parsed.displayName,
                        manufacturer = parsed.manufacturer,
                        model = parsed.model,
                        firmwareVersion = parsed.firmwareVersion,
                        serialNumber = parsed.serialNumber,
                        attributes = parsed.attributes + mapOf("Probe" to probe.name),
                        seenAtMillis = System.currentTimeMillis(),
                    ),
                )
            }
        } finally {
            runCatching { socket.close() }
        }
    }

    private fun probesFor(depth: ScanDepth): List<UdpProbe> = when (depth) {
        ScanDepth.QUICK -> quickProbes()
        ScanDepth.STANDARD -> quickProbes() + standardProbes()
        ScanDepth.DEEP -> quickProbes() + standardProbes() + deepProbes()
    }

    private fun quickProbes(): List<UdpProbe> = listOf(
        UdpProbe(
            name = "LIFX GetService",
            protocol = Protocol.LIFX_LAN,
            targetAddress = null,
            targetPort = 56700,
            payload = lifxGetServicePacket(),
            parse = parse@{ source, data ->
                if (data.size < 36) return@parse null
                val mac = data.copyOfRange(8, 14).joinToString(":") { "%02x".format(it) }
                ParsedResponse(
                    displayName = "LIFX device",
                    manufacturer = "LIFX",
                    macAddress = mac,
                    attributes = mapOf("Target MAC" to mac, "Source" to source),
                )
            },
        ),
        UdpProbe(
            name = "TP-Link Kasa sysinfo",
            protocol = Protocol.KASA,
            targetAddress = null,
            targetPort = 9999,
            payload = kasaEncrypt("""{"system":{"get_sysinfo":{}}}"""),
            parse = parse@{ _, data ->
                val json = kasaDecrypt(data)
                if (!json.contains("get_sysinfo")) return@parse null
                ParsedResponse(
                    displayName = json.jsonString("alias"),
                    manufacturer = "TP-Link",
                    model = json.jsonString("model"),
                    firmwareVersion = json.jsonString("sw_ver"),
                    serialNumber = json.jsonString("deviceId"),
                    macAddress = (json.jsonString("mac") ?: json.jsonString("mic_mac"))
                        ?.lowercase()?.replace("-", ":"),
                    attributes = buildMap {
                        json.jsonString("dev_name")?.let { put("Device type", it) }
                        json.jsonString("hw_ver")?.let { put("Hardware version", it) }
                        json.jsonString("rssi")?.let { put("Reported RSSI", "$it dBm") }
                    },
                )
            },
        ),
        UdpProbe(
            name = "WiZ getSystemConfig",
            protocol = Protocol.WIZ,
            targetAddress = null,
            targetPort = 38899,
            payload = """{"method":"getSystemConfig","params":{}}""".toByteArray(Charsets.UTF_8),
            parse = parse@{ _, data ->
                val json = String(data, Charsets.UTF_8)
                if (!json.contains("getSystemConfig") && !json.contains("\"mac\"")) return@parse null
                ParsedResponse(
                    displayName = "WiZ light",
                    manufacturer = "WiZ",
                    model = json.jsonString("moduleName"),
                    firmwareVersion = json.jsonString("fwVersion"),
                    macAddress = json.jsonString("mac")?.asMac(),
                    attributes = buildMap {
                        json.jsonString("homeId")?.let { put("Home ID", it) }
                        json.jsonString("roomId")?.let { put("Room ID", it) }
                    },
                )
            },
        ),
        // Tuya devices broadcast an encrypted heartbeat unprompted; we only need to listen.
        UdpProbe(
            name = "Tuya LAN heartbeat",
            protocol = Protocol.TUYA_LAN,
            targetAddress = null,
            targetPort = 6667,
            bindPort = 6667,
            payload = null,
            parse = parse@{ source, data ->
                if (data.size < 20) return@parse null
                ParsedResponse(
                    displayName = "Tuya device",
                    manufacturer = "Tuya",
                    attributes = mapOf(
                        "Source" to source,
                        "Payload" to "${data.size} bytes (AES-encrypted heartbeat)",
                        "Note" to "Decoding the payload needs this device's local key from your Tuya account",
                    ),
                )
            },
        ),
    )

    private fun standardProbes(): List<UdpProbe> = listOf(
        UdpProbe(
            name = "KNXnet/IP search",
            protocol = Protocol.KNX,
            targetAddress = KNX_GROUP,
            multicastGroup = KNX_GROUP,
            targetPort = 3671,
            payload = knxSearchRequest(),
            parse = parse@{ source, data ->
                // Every KNXnet/IP frame starts with a 0x06 0x10 header.
                if (data.size < 8 || data[0] != 0x06.toByte() || data[1] != 0x10.toByte()) return@parse null
                ParsedResponse(
                    displayName = knxFriendlyName(data) ?: "KNX IP gateway",
                    manufacturer = "KNX",
                    model = "KNXnet/IP interface",
                    attributes = mapOf("Source" to source, "Frame size" to "${data.size} bytes"),
                )
            },
        ),
        UdpProbe(
            name = "BACnet Who-Is",
            protocol = Protocol.BACNET,
            targetAddress = null,
            targetPort = 47808,
            payload = bacnetWhoIs(),
            parse = parse@{ source, data ->
                // BVLC header always begins 0x81.
                if (data.size < 4 || data[0] != 0x81.toByte()) return@parse null
                ParsedResponse(
                    displayName = "BACnet device",
                    manufacturer = "BACnet",
                    model = "BACnet/IP node",
                    attributes = mapOf("Source" to source, "I-Am frame" to "${data.size} bytes"),
                )
            },
        ),
        UdpProbe(
            name = "ONVIF WS-Discovery",
            protocol = Protocol.ONVIF,
            targetAddress = WSD_GROUP,
            multicastGroup = WSD_GROUP,
            targetPort = 3702,
            payload = onvifProbe().toByteArray(Charsets.UTF_8),
            parse = parse@{ source, data ->
                val xml = String(data, Charsets.UTF_8)
                if (!xml.contains("ProbeMatch", ignoreCase = true)) return@parse null
                val scopes = xml.substringAfter("Scopes>", "").substringBefore("</", "")
                ParsedResponse(
                    displayName = scopes.onvifScope("name") ?: "ONVIF camera",
                    manufacturer = scopes.onvifScope("hardware"),
                    model = scopes.onvifScope("hardware"),
                    attributes = mapOf("Source" to source, "Scopes" to scopes.take(400)),
                )
            },
        ),
        UdpProbe(
            name = "Xiaomi miIO handshake",
            protocol = Protocol.MIIO,
            targetAddress = null,
            targetPort = 54321,
            payload = miioHello(),
            parse = parse@{ source, data ->
                if (data.size < 32 || data[0] != 0x21.toByte()) return@parse null
                val deviceId = data.copyOfRange(8, 12).joinToString("") { "%02x".format(it) }
                ParsedResponse(
                    displayName = "Xiaomi device",
                    manufacturer = "Xiaomi",
                    serialNumber = deviceId,
                    attributes = mapOf("Source" to source, "miIO device ID" to deviceId),
                )
            },
        ),
    )

    private fun deepProbes(): List<UdpProbe> = listOf(
        UdpProbe(
            name = "CoAP .well-known/core",
            protocol = Protocol.COAP,
            targetAddress = COAP_GROUP,
            multicastGroup = COAP_GROUP,
            targetPort = 5683,
            payload = coapWellKnownCore(),
            parse = parse@{ source, data ->
                if (data.size < 4) return@parse null
                val body = String(data, Charsets.UTF_8)
                    .filter { it.isLetterOrDigit() || it in "/<>;=,.\" -_" }
                    .take(300)
                ParsedResponse(
                    displayName = "CoAP node",
                    model = "CoAP endpoint",
                    attributes = mapOf("Source" to source, "Resource list" to body),
                )
            },
        ),
        UdpProbe(
            name = "MQTT-SN SEARCHGW",
            protocol = Protocol.MQTT_SN,
            targetAddress = null,
            targetPort = 1884,
            payload = byteArrayOf(0x03, 0x01, 0x01), // length, SEARCHGW, radius
            parse = parse@{ source, data ->
                if (data.size < 2) return@parse null
                ParsedResponse(
                    displayName = "MQTT-SN gateway",
                    model = "MQTT-SN",
                    attributes = mapOf("Source" to source),
                )
            },
        ),
    )

    // ───────────────────────────── payload builders ─────────────────────────────

    /**
     * LIFX LAN protocol: a 36-byte header with no payload, message type 2 (GetService).
     * Frame flags encode tagged + addressable + protocol 1024, which is 0x3400 little-endian.
     */
    private fun lifxGetServicePacket(): ByteArray {
        val packet = ByteArray(36)
        packet[0] = 36            // size, uint16 LE
        packet[1] = 0
        packet[2] = 0x00          // protocol/addressable/tagged/origin bitfield
        packet[3] = 0x34
        packet[4] = 0x48          // arbitrary non-zero source id ("HYPE")
        packet[5] = 0x59
        packet[6] = 0x50
        packet[7] = 0x45
        packet[22] = 0x01         // res_required
        packet[32] = 2            // message type 2 = GetService, uint16 LE
        packet[33] = 0
        return packet
    }

    /** Kasa's obfuscation is an XOR autokey cipher seeded with 171. */
    private fun kasaEncrypt(payload: String): ByteArray {
        var key = 171
        return payload.toByteArray(Charsets.UTF_8)
            .map { byte ->
                val encrypted = (byte.toInt() and 0xFF) xor key
                key = encrypted
                encrypted.toByte()
            }
            .toByteArray()
    }

    private fun kasaDecrypt(data: ByteArray): String {
        var key = 171
        val out = StringBuilder(data.size)
        data.forEach { byte ->
            val cipher = byte.toInt() and 0xFF
            out.append((cipher xor key).toChar())
            key = cipher
        }
        return out.toString()
    }

    /** KNXnet/IP SEARCH_REQUEST (service 0x0201) with a wildcard HPAI discovery endpoint. */
    private fun knxSearchRequest(): ByteArray = byteArrayOf(
        0x06, 0x10,             // header length 6, protocol version 1.0
        0x02, 0x01,             // SEARCH_REQUEST
        0x00, 0x0E,             // total length 14
        0x08, 0x01,             // HPAI length 8, UDP over IPv4
        0x00, 0x00, 0x00, 0x00, // 0.0.0.0 — reply to the sender's address
        0x00, 0x00,             // port 0 — reply to the sender's port
    )

    /**
     * SEARCH_RESPONSE layout: 6-byte header, 8-byte HPAI, then a Device Information DIB whose
     * bytes 8..37 hold a 30-character friendly name. That puts the name at absolute offset 22.
     */
    private fun knxFriendlyName(data: ByteArray): String? {
        if (data.size < 52) return null
        return runCatching { String(data, 22, 30, Charsets.UTF_8) }
            .getOrNull()
            ?.trim { it <= ' ' }
            ?.takeIf { it.isNotBlank() }
    }

    /** BVLC Original-Broadcast-NPDU wrapping an unconfirmed Who-Is with no device range. */
    private fun bacnetWhoIs(): ByteArray = byteArrayOf(
        0x81.toByte(), 0x0B,      // BVLC type, Original-Broadcast-NPDU
        0x00, 0x08,               // BVLC length 8
        0x01, 0x20,               // NPDU version 1, control: expecting global broadcast
        0xFF.toByte(), 0xFF.toByte(), // DNET 65535 (global)
        0x00,                     // DLEN 0
        0xFF.toByte(),            // hop count
        0x10, 0x08,               // APDU: unconfirmed request, service 8 = Who-Is
    )

    /** miIO "hello" discovery packet: magic 0x2131, length 32, everything else 0xFF. */
    private fun miioHello(): ByteArray = ByteArray(32).also { packet ->
        packet[0] = 0x21
        packet[1] = 0x31
        packet[2] = 0x00
        packet[3] = 0x20
        for (index in 4 until 32) packet[index] = 0xFF.toByte()
    }

    /** CoAP CON GET with Uri-Path ".well-known" then "core". */
    private fun coapWellKnownCore(): ByteArray = byteArrayOf(
        0x40, 0x01, 0x12, 0x34, // version 1, CON, code GET, message id
        0xBB.toByte(),          // option 11 (Uri-Path), length 11
        '.'.code.toByte(), 'w'.code.toByte(), 'e'.code.toByte(), 'l'.code.toByte(),
        'l'.code.toByte(), '-'.code.toByte(), 'k'.code.toByte(), 'n'.code.toByte(),
        'o'.code.toByte(), 'w'.code.toByte(), 'n'.code.toByte(),
        0x04,                   // option delta 0, length 4
        'c'.code.toByte(), 'o'.code.toByte(), 'r'.code.toByte(), 'e'.code.toByte(),
    )

    private fun onvifProbe(): String =
        """<?xml version="1.0" encoding="UTF-8"?>""" +
            """<e:Envelope xmlns:e="http://www.w3.org/2003/05/soap-envelope" """ +
            """xmlns:w="http://schemas.xmlsoap.org/ws/2004/08/addressing" """ +
            """xmlns:d="http://schemas.xmlsoap.org/ws/2005/04/discovery" """ +
            """xmlns:dn="http://www.onvif.org/ver10/network/wsdl">""" +
            """<e:Header><w:MessageID>uuid:hyperscale-probe-0001</w:MessageID>""" +
            """<w:To e:mustUnderstand="true">urn:schemas-xmlsoap-org:ws:2005:04:discovery</w:To>""" +
            """<w:Action e:mustUnderstand="true">""" +
            """http://schemas.xmlsoap.org/ws/2005/04/discovery/Probe</w:Action></e:Header>""" +
            """<e:Body><d:Probe><d:Types>dn:NetworkVideoTransmitter</d:Types></d:Probe></e:Body>""" +
            """</e:Envelope>"""

    // ───────────────────────────── parsing helpers ─────────────────────────────

    /** Pulls a scalar out of flat JSON without paying for a full parse. */
    private fun String.jsonString(key: String): String? {
        val keyIndex = indexOf("\"$key\"").takeIf { it >= 0 } ?: return null
        val colon = indexOf(':', keyIndex).takeIf { it >= 0 } ?: return null
        val rest = substring(colon + 1).trimStart()
        return when {
            rest.startsWith('"') -> rest.drop(1).substringBefore('"').takeIf { it.isNotBlank() }
            else -> rest.takeWhile { it.isDigit() || it == '.' || it == '-' }.takeIf { it.isNotBlank() }
        }
    }

    private fun String.asMac(): String =
        if (contains(':')) lowercase() else chunked(2).joinToString(":").lowercase()

    private fun String.onvifScope(name: String): String? =
        split(' ')
            .firstOrNull { it.contains("/$name/", ignoreCase = true) }
            ?.substringAfterLast('/')
            ?.replace("%20", " ")
            ?.takeIf { it.isNotBlank() }

    private companion object {
        const val TAG = "UdpProbeScanner"
        const val SOCKET_POLL_MILLIS = 700
        const val KNX_GROUP = "224.0.23.12"
        const val WSD_GROUP = "239.255.255.250"
        const val COAP_GROUP = "224.0.1.187"
    }
}
