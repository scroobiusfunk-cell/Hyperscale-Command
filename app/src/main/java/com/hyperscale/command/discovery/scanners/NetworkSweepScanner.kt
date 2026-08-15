package com.hyperscale.command.discovery.scanners

import android.content.Context
import android.util.Log
import com.hyperscale.command.core.model.DiscoverySource
import com.hyperscale.command.core.model.Observation
import com.hyperscale.command.core.model.Protocol
import com.hyperscale.command.core.model.ProtocolCatalog
import com.hyperscale.command.discovery.NetworkEnvironment
import com.hyperscale.command.discovery.ProtocolScanner
import com.hyperscale.command.discovery.ScanContext
import com.hyperscale.command.discovery.ScanDepth
import com.hyperscale.command.discovery.ScannerAvailability
import com.hyperscale.command.discovery.fingerprint.OuiDatabase
import java.io.File
import java.net.InetAddress
import java.net.InetSocketAddress
import java.net.Socket
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.coroutineScope
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.channelFlow
import kotlinx.coroutines.flow.flowOn
import kotlinx.coroutines.launch
import kotlinx.coroutines.sync.Semaphore
import kotlinx.coroutines.sync.withPermit

/**
 * Subnet sweep: finds every host with an IP address, then fingerprints it by which control ports
 * answer.
 *
 * This is the safety net beneath the protocol-specific scanners. A device that speaks nothing we
 * recognise still shows up here with its vendor resolved from the MAC OUI, which is usually enough
 * for the user to say "that's the boiler controller".
 *
 * Probing is deliberately gentle: a bounded number of concurrent connects, short timeouts, and a
 * connect-then-close handshake with no data sent, so nothing on the network gets upset.
 */
class NetworkSweepScanner : ProtocolScanner {

    override val id = "sweep"
    override val label = "Network sweep"
    override val source = DiscoverySource.ARP

    override val protocols = setOf(
        Protocol.WIFI, Protocol.UNKNOWN, Protocol.HTTP, Protocol.HTTPS, Protocol.MQTT,
        Protocol.MODBUS_TCP, Protocol.SSH, Protocol.TELNET, Protocol.ESPHOME, Protocol.SHELLY,
        Protocol.RTSP, Protocol.SONOS, Protocol.ROKU_ECP, Protocol.WEBOS, Protocol.SAMSUNG_TIZEN,
        Protocol.HOME_ASSISTANT, Protocol.HOMEY, Protocol.KNX, Protocol.CBUS, Protocol.CRESTRON,
        Protocol.NANOLEAF, Protocol.HUE_ENTERTAINMENT, Protocol.LUTRON, Protocol.WEMO,
    )

    override fun availability(context: Context): ScannerAvailability =
        if (NetworkEnvironment.capture(context).isUsable) {
            ScannerAvailability.Ready
        } else {
            ScannerAvailability.Unavailable("Not connected to a local network")
        }

    override fun scan(scanContext: ScanContext): Flow<Observation> = channelFlow {
        val network = scanContext.network
        if (!network.isUsable) return@channelFlow

        val hosts = network.hostAddresses()
        if (hosts.isEmpty()) return@channelFlow

        val arpTable = readArpTable()
        val ports = portsFor(scanContext.depth)
        val connectTimeout = when (scanContext.depth) {
            ScanDepth.QUICK -> 250
            ScanDepth.STANDARD -> 400
            ScanDepth.DEEP -> 900
        }
        val gate = Semaphore(permits = MAX_CONCURRENT_PROBES)

        coroutineScope {
            hosts.forEach { host ->
                launch(Dispatchers.IO) {
                    gate.withPermit {
                        val openPorts = ports.filter { port -> isOpen(host, port, connectTimeout) }
                        val reachable = openPorts.isNotEmpty() ||
                            host in arpTable ||
                            isPingable(host, connectTimeout)

                        if (!reachable) return@withPermit

                        val mac = arpTable[host]
                        val hostname = resolveHostname(host)
                        val protocols = protocolsFor(openPorts)

                        // One observation per identified protocol keeps the merger's protocol
                        // list honest — the device genuinely does speak each of them.
                        val emitted = protocols.ifEmpty { listOf(Protocol.UNKNOWN) }
                        emitted.forEach { protocol ->
                            trySend(
                                observation(
                                    host = host,
                                    mac = mac,
                                    hostname = hostname,
                                    protocol = protocol,
                                    openPorts = openPorts,
                                ),
                            )
                        }
                    }
                }
            }
        }
    }.flowOn(Dispatchers.IO)

    private fun observation(
        host: String,
        mac: String?,
        hostname: String?,
        protocol: Protocol,
        openPorts: List<Int>,
    ): Observation {
        val vendor = mac?.let { OuiDatabase.vendorFor(it) }
        return Observation(
            protocol = protocol,
            source = DiscoverySource.ARP,
            identityKeys = buildSet {
                add("ip:$host")
                mac?.let { add("mac:${it.lowercase()}") }
            },
            ipAddress = host,
            macAddress = mac?.lowercase(),
            hostname = hostname,
            port = openPorts.firstOrNull(),
            displayName = hostname?.substringBefore('.')?.takeIf { it.isNotBlank() && it != host },
            manufacturer = vendor,
            attributes = buildMap {
                put("IP address", host)
                mac?.let { put("MAC address", it) }
                vendor?.let { put("MAC vendor", it) }
                hostname?.let { put("Reverse DNS", it) }
                if (openPorts.isNotEmpty()) {
                    put("Open ports", openPorts.joinToString(", "))
                    put(
                        "Port services",
                        openPorts.joinToString(", ") { port ->
                            val names = ProtocolCatalog.forPort(port).map { it.displayName }
                            if (names.isEmpty()) "$port" else "$port (${names.first()})"
                        },
                    )
                }
            },
            seenAtMillis = System.currentTimeMillis(),
        )
    }

    private fun protocolsFor(openPorts: List<Int>): List<Protocol> {
        if (openPorts.isEmpty()) return emptyList()
        return openPorts
            .flatMap { port -> SIGNATURE_PORTS[port].orEmpty() }
            .distinct()
    }

    private fun isOpen(host: String, port: Int, timeoutMillis: Int): Boolean = runCatching {
        Socket().use { socket ->
            socket.connect(InetSocketAddress(host, port), timeoutMillis)
            true
        }
    }.getOrDefault(false)

    private fun isPingable(host: String, timeoutMillis: Int): Boolean = runCatching {
        InetAddress.getByName(host).isReachable(timeoutMillis)
    }.getOrDefault(false)

    private fun resolveHostname(host: String): String? = runCatching {
        val address = InetAddress.getByName(host)
        address.canonicalHostName
            ?.takeIf { it.isNotBlank() && it != host }
            ?.removeSuffix(".")
    }.getOrNull()

    /**
     * Best-effort read of the kernel ARP cache. Android 10 and above sandbox `/proc/net/arp`, so
     * this returns nothing on modern devices — MAC addresses then come from mDNS TXT records,
     * SSDP UDNs and vendor protocols instead. Kept because it is free when it does work.
     */
    private fun readArpTable(): Map<String, String> = runCatching {
        val file = File("/proc/net/arp")
        if (!file.canRead()) return@runCatching emptyMap()
        file.readLines()
            .drop(1)
            .mapNotNull { line ->
                val columns = line.split(Regex("\\s+")).filter { it.isNotBlank() }
                if (columns.size < 4) return@mapNotNull null
                val ip = columns[0]
                val mac = columns[3].lowercase()
                if (mac == "00:00:00:00:00:00" || !mac.contains(':')) return@mapNotNull null
                ip to mac
            }
            .toMap()
    }.getOrElse {
        Log.d(TAG, "ARP table unavailable (expected on Android 10+)")
        emptyMap()
    }

    private fun portsFor(depth: ScanDepth): List<Int> = when (depth) {
        ScanDepth.QUICK -> QUICK_PORTS
        ScanDepth.STANDARD -> QUICK_PORTS + STANDARD_PORTS
        ScanDepth.DEEP -> QUICK_PORTS + STANDARD_PORTS + DEEP_PORTS
    }.distinct()

    private companion object {
        const val TAG = "NetworkSweepScanner"

        /**
         * 48 sockets in flight keeps a /24 sweep to a few seconds without saturating the Wi-Fi
         * chipset or tripping consumer router connection-tracking limits.
         */
        const val MAX_CONCURRENT_PROBES = 48

        val QUICK_PORTS = listOf(80, 443, 8080)

        val STANDARD_PORTS = listOf(
            22, 23, 1883, 8123, 502, 6053, 1400, 8060, 8001, 9999, 16021, 5540, 3671, 554,
        )

        val DEEP_PORTS = listOf(
            21, 25, 53, 81, 88, 445, 548, 631, 1024, 2000, 2100, 3000, 3001, 3389, 4321,
            5000, 5001, 5060, 5222, 5672, 7000, 8008, 8009, 8081, 8443, 8883, 8888, 9000,
            9100, 10001, 20002, 32400, 41794, 49152, 49153, 55443,
        )

        /**
         * Ports that identify a protocol strongly enough to label a device with it. Ports that
         * merely mean "there is a web server here" map to plain HTTP.
         */
        val SIGNATURE_PORTS: Map<Int, List<Protocol>> = mapOf(
            22 to listOf(Protocol.SSH),
            23 to listOf(Protocol.TELNET),
            80 to listOf(Protocol.HTTP),
            81 to listOf(Protocol.HTTP),
            443 to listOf(Protocol.HTTPS),
            502 to listOf(Protocol.MODBUS_TCP),
            554 to listOf(Protocol.RTSP),
            1400 to listOf(Protocol.SONOS),
            1883 to listOf(Protocol.MQTT),
            2100 to listOf(Protocol.HUE_ENTERTAINMENT),
            3000 to listOf(Protocol.WEBOS),
            3001 to listOf(Protocol.WEBOS),
            3671 to listOf(Protocol.KNX),
            5540 to listOf(Protocol.MATTER),
            6053 to listOf(Protocol.ESPHOME),
            8001 to listOf(Protocol.SAMSUNG_TIZEN),
            8002 to listOf(Protocol.SAMSUNG_TIZEN),
            8009 to listOf(Protocol.CHROMECAST),
            8060 to listOf(Protocol.ROKU_ECP),
            8080 to listOf(Protocol.HTTP),
            8081 to listOf(Protocol.HTTP, Protocol.LUTRON),
            8123 to listOf(Protocol.HOME_ASSISTANT),
            8443 to listOf(Protocol.HTTPS),
            8883 to listOf(Protocol.MQTT),
            9999 to listOf(Protocol.KASA),
            10001 to listOf(Protocol.CBUS),
            16021 to listOf(Protocol.NANOLEAF),
            20002 to listOf(Protocol.KASA),
            41794 to listOf(Protocol.CRESTRON),
            49152 to listOf(Protocol.WEMO),
            49153 to listOf(Protocol.WEMO),
            55443 to listOf(Protocol.YEELIGHT),
        )
    }
}
