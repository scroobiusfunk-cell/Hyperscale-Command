package com.hyperscale.command.discovery.scanners

import android.content.Context
import android.net.nsd.NsdManager
import android.net.nsd.NsdServiceInfo
import android.net.wifi.WifiManager
import android.util.Log
import com.hyperscale.command.core.model.DiscoverySource
import com.hyperscale.command.core.model.Observation
import com.hyperscale.command.core.model.Protocol
import com.hyperscale.command.core.model.ProtocolCatalog
import com.hyperscale.command.discovery.ProtocolScanner
import com.hyperscale.command.discovery.ScanContext
import com.hyperscale.command.discovery.ScanDepth
import com.hyperscale.command.discovery.ScannerAvailability
import java.net.Inet4Address
import java.util.concurrent.ConcurrentHashMap
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.channels.awaitClose
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.callbackFlow
import kotlinx.coroutines.flow.flowOn
import kotlinx.coroutines.launch
import kotlinx.coroutines.sync.Semaphore
import kotlinx.coroutines.sync.withPermit

/**
 * DNS-SD discovery over multicast DNS.
 *
 * This is the highest-value scanner in the app: TXT records routinely hand over manufacturer,
 * model, firmware and serial for free, which is exactly what the merger needs to unify a device
 * across protocols.
 *
 * Two Android-specific hazards are handled here:
 *  - Multicast is filtered by the Wi-Fi chipset unless a [WifiManager.MulticastLock] is held.
 *  - [NsdManager.resolveService] historically tolerates only one in-flight resolve; concurrent
 *    calls fail with FAILURE_ALREADY_ACTIVE. Resolves are therefore gated by a semaphore.
 */
class MdnsScanner : ProtocolScanner {

    override val id = "mdns"
    override val label = "mDNS / DNS-SD"
    override val source = DiscoverySource.MDNS

    override val protocols: Set<Protocol> =
        ProtocolCatalog.all.filter { it.serviceTypes.isNotEmpty() }.toSet() + Protocol.MDNS

    override fun availability(context: Context): ScannerAvailability {
        context.getSystemService(NsdManager::class.java)
            ?: return ScannerAvailability.Unavailable("Network service discovery unavailable")
        return ScannerAvailability.Ready
    }

    override fun scan(scanContext: ScanContext): Flow<Observation> = callbackFlow {
        val context = scanContext.context
        val nsdManager = context.getSystemService(NsdManager::class.java)
        if (nsdManager == null) {
            close()
            return@callbackFlow
        }

        val wifiManager = context.applicationContext.getSystemService(WifiManager::class.java)
        val multicastLock = wifiManager?.createMulticastLock("hyperscale-mdns")?.apply {
            setReferenceCounted(true)
            runCatching { acquire() }
        }

        // One resolve at a time keeps NsdManager happy across OEM builds.
        val resolveGate = Semaphore(permits = 1)
        val seen = ConcurrentHashMap.newKeySet<String>()
        val listeners = mutableListOf<Pair<String, NsdManager.DiscoveryListener>>()

        val serviceTypes = serviceTypesFor(scanContext.depth)

        serviceTypes.forEach { serviceType ->
            val listener = object : NsdManager.DiscoveryListener {
                override fun onStartDiscoveryFailed(type: String, errorCode: Int) {
                    Log.d(TAG, "Start discovery failed for $type ($errorCode)")
                }

                override fun onStopDiscoveryFailed(type: String, errorCode: Int) = Unit

                override fun onDiscoveryStarted(type: String) = Unit

                override fun onDiscoveryStopped(type: String) = Unit

                override fun onServiceFound(serviceInfo: NsdServiceInfo) {
                    val key = "${serviceInfo.serviceName}|${serviceInfo.serviceType}"
                    if (!seen.add(key)) return

                    // Emit immediately on the unresolved record so the UI fills in fast, then
                    // resolve for the address and TXT payload.
                    trySend(observationFrom(serviceInfo, serviceType, resolved = false))

                    launch(Dispatchers.IO) {
                        resolveGate.withPermit {
                            runCatching {
                                resolve(nsdManager, serviceInfo)
                            }.onSuccess { resolvedInfo ->
                                if (resolvedInfo != null) {
                                    trySend(observationFrom(resolvedInfo, serviceType, resolved = true))
                                }
                            }.onFailure { error ->
                                Log.d(TAG, "Resolve failed for ${serviceInfo.serviceName}", error)
                            }
                        }
                    }
                }

                override fun onServiceLost(serviceInfo: NsdServiceInfo) = Unit
            }

            runCatching {
                nsdManager.discoverServices(serviceType, NsdManager.PROTOCOL_DNS_SD, listener)
                listeners += serviceType to listener
            }.onFailure { error ->
                Log.d(TAG, "Could not start discovery for $serviceType", error)
            }
        }

        awaitClose {
            listeners.forEach { (_, listener) ->
                runCatching { nsdManager.stopServiceDiscovery(listener) }
            }
            runCatching { multicastLock?.release() }
        }
    }.flowOn(Dispatchers.IO)

    private suspend fun resolve(nsdManager: NsdManager, serviceInfo: NsdServiceInfo): NsdServiceInfo? =
        kotlinx.coroutines.suspendCancellableCoroutine { continuation ->
            val listener = object : NsdManager.ResolveListener {
                override fun onResolveFailed(info: NsdServiceInfo, errorCode: Int) {
                    if (continuation.isActive) continuation.resumeWith(Result.success(null))
                }

                override fun onServiceResolved(info: NsdServiceInfo) {
                    if (continuation.isActive) continuation.resumeWith(Result.success(info))
                }
            }
            runCatching { nsdManager.resolveService(serviceInfo, listener) }
                .onFailure { if (continuation.isActive) continuation.resumeWith(Result.success(null)) }
        }

    @Suppress("DEPRECATION")
    private fun observationFrom(
        info: NsdServiceInfo,
        discoveredType: String,
        resolved: Boolean,
    ): Observation {
        val txt: Map<String, String> = runCatching {
            info.attributes.orEmpty().mapNotNull { (key, value) ->
                val text = value?.toString(Charsets.UTF_8)?.trim().orEmpty()
                if (text.isEmpty()) null else key to text
            }.toMap()
        }.getOrDefault(emptyMap())

        val host = runCatching { info.host }.getOrNull()
        val ip = (host as? Inet4Address)?.hostAddress
        val hostname = host?.hostName?.removeSuffix(".")

        val serviceType = info.serviceType?.takeIf { it.isNotBlank() } ?: discoveredType
        val protocol = ProtocolCatalog.forServiceType(serviceType)
            ?: ProtocolCatalog.forServiceType(discoveredType)
            ?: Protocol.MDNS

        val serviceName = info.serviceName?.trim().orEmpty()

        val identityKeys = buildSet {
            add("mdns:${serviceName.lowercase()}|${normaliseType(serviceType)}")
            ip?.let { add("ip:$it") }
            txtValue(txt, "id", "deviceid", "mac")?.let { add("mac:${it.lowercase().replace("-", ":")}") }
            txtValue(txt, "sn", "serialnumber", "serial")?.let { add("serial:${it.lowercase()}") }
        }

        return Observation(
            protocol = protocol,
            source = DiscoverySource.MDNS,
            identityKeys = identityKeys,
            ipAddress = ip,
            macAddress = txtValue(txt, "mac")?.lowercase()?.replace("-", ":"),
            hostname = hostname,
            port = runCatching { info.port }.getOrNull()?.takeIf { it > 0 },
            displayName = friendlyName(serviceName, txt),
            manufacturer = txtValue(txt, "manufacturer", "vendor", "ve", "brand"),
            model = txtValue(txt, "model", "md", "mdl", "ty", "product", "device"),
            firmwareVersion = txtValue(txt, "fw", "version", "vs", "sw", "fwver", "swvers"),
            serialNumber = txtValue(txt, "sn", "serialnumber", "serial"),
            attributes = buildMap {
                put("Service type", serviceType)
                put("Service name", serviceName)
                put("Resolved", resolved.toString())
                putAll(txt)
            },
            seenAtMillis = System.currentTimeMillis(),
        )
    }

    /** Devices put their human name in wildly different TXT keys; try the common ones in order. */
    private fun friendlyName(serviceName: String, txt: Map<String, String>): String? =
        txtValue(txt, "fn", "friendlyname", "n", "name", "devicename", "md")
            ?: serviceName.takeIf { it.isNotBlank() }

    private fun txtValue(txt: Map<String, String>, vararg keys: String): String? {
        val lowered = txt.mapKeys { it.key.lowercase() }
        return keys.firstNotNullOfOrNull { key -> lowered[key]?.takeIf { it.isNotBlank() } }
    }

    private fun normaliseType(type: String) =
        type.trim().removeSuffix(".").removeSuffix(".local").lowercase()

    private fun serviceTypesFor(depth: ScanDepth): List<String> {
        val catalogue = ProtocolCatalog.allServiceTypes
        val generic = GENERIC_SERVICE_TYPES
        return when (depth) {
            // NsdManager gets unhappy with dozens of simultaneous discoveries on some devices,
            // so a quick pass sticks to the types that identify smart-home gear most often.
            ScanDepth.QUICK -> (HIGH_YIELD_TYPES).distinct()
            ScanDepth.STANDARD -> (HIGH_YIELD_TYPES + catalogue).distinct().take(24)
            ScanDepth.DEEP -> (HIGH_YIELD_TYPES + catalogue + generic).distinct()
        }.map { if (it.endsWith(".")) it.dropLast(1) else it }
    }

    private companion object {
        const val TAG = "MdnsScanner"

        val HIGH_YIELD_TYPES = listOf(
            "_googlecast._tcp",
            "_hap._tcp",
            "_matter._tcp",
            "_matterc._udp",
            "_homey._tcp",
            "_hue._tcp",
            "_esphomelib._tcp",
            "_shelly._tcp",
            "_airplay._tcp",
            "_raop._tcp",
            "_sonos._tcp",
            "_nanoleafapi._tcp",
            "_meshcop._udp",
            "_home-assistant._tcp",
            "_mqtt._tcp",
        )

        val GENERIC_SERVICE_TYPES = listOf(
            "_http._tcp",
            "_https._tcp",
            "_workstation._tcp",
            "_device-info._tcp",
            "_ipp._tcp",
            "_ipps._tcp",
            "_printer._tcp",
            "_pdl-datastream._tcp",
            "_smb._tcp",
            "_afpovertcp._tcp",
            "_ssh._tcp",
            "_sftp-ssh._tcp",
            "_rfb._tcp",
            "_daap._tcp",
            "_dacp._tcp",
            "_touch-able._tcp",
            "_companion-link._tcp",
            "_spotify-connect._tcp",
            "_rtsp._tcp",
            "_dosvc._tcp",
            "_amzn-wplay._tcp",
            "_googlezone._tcp",
            "_androidtvremote2._tcp",
            "_coap._udp",
            "_trel._udp",
            "_lutron._tcp",
            "_tasmota._tcp",
            "_nanoleafms._tcp",
        )
    }
}
