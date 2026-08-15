package com.hyperscale.command.discovery.scanners

import android.content.Context
import android.net.wifi.WifiManager
import android.util.Log
import com.hyperscale.command.core.model.DiscoverySource
import com.hyperscale.command.core.model.Observation
import com.hyperscale.command.core.model.Protocol
import com.hyperscale.command.discovery.ProtocolScanner
import com.hyperscale.command.discovery.ScanContext
import com.hyperscale.command.discovery.ScanDepth
import com.hyperscale.command.discovery.ScannerAvailability
import java.net.DatagramPacket
import java.net.DatagramSocket
import java.net.InetAddress
import java.net.InetSocketAddress
import java.net.SocketTimeoutException
import java.util.concurrent.TimeUnit
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.currentCoroutineContext
import kotlinx.coroutines.ensureActive
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.flow
import kotlinx.coroutines.flow.flowOn
import kotlinx.coroutines.withContext
import okhttp3.OkHttpClient
import okhttp3.Request

/**
 * SSDP (the discovery half of UPnP) plus the vendor variants that reuse its wire format on
 * different multicast ports — Yeelight on 1982 and Govee on 4001.
 *
 * Responses are HTTP-ish header blocks. When a response carries a LOCATION URL we fetch the
 * device description XML, because that is where friendly name, manufacturer, model and serial
 * actually live; the SSDP headers alone rarely identify anything useful.
 */
class SsdpScanner(
    private val httpClient: OkHttpClient = defaultClient(),
) : ProtocolScanner {

    override val id = "ssdp"
    override val label = "SSDP / UPnP"
    override val source = DiscoverySource.SSDP

    override val protocols = setOf(
        Protocol.SSDP, Protocol.DLNA, Protocol.SONOS, Protocol.WEMO, Protocol.ROKU_ECP,
        Protocol.WEBOS, Protocol.SAMSUNG_TIZEN, Protocol.YEELIGHT, Protocol.GOVEE_LAN,
        Protocol.PHILIPS_HUE, Protocol.ONVIF, Protocol.SMARTTHINGS, Protocol.ALEXA,
    )

    override fun availability(context: Context): ScannerAvailability = ScannerAvailability.Ready

    override fun scan(scanContext: ScanContext): Flow<Observation> = flow {
        val wifiManager = scanContext.context.applicationContext.getSystemService(WifiManager::class.java)
        val multicastLock = wifiManager?.createMulticastLock("hyperscale-ssdp")?.apply {
            setReferenceCounted(true)
            runCatching { acquire() }
        }

        val searchTargets = searchTargetsFor(scanContext.depth)
        val listenMillis = (scanContext.timeoutMillis - 1_000L).coerceIn(3_000L, 20_000L)
        val seen = mutableSetOf<String>()

        try {
            for (endpoint in ENDPOINTS) {
                currentCoroutineContext().ensureActive()
                val responses = withContext(Dispatchers.IO) {
                    probe(endpoint, searchTargets, listenMillis / ENDPOINTS.size)
                }
                for (response in responses) {
                    val usn = response.headers["usn"] ?: response.headers["location"] ?: response.sourceIp
                    if (!seen.add("${endpoint.port}|$usn")) continue
                    emit(toObservation(response, endpoint))

                    response.headers["location"]?.let { location ->
                        describe(location)?.let { description ->
                            emit(toObservation(response, endpoint, description))
                        }
                    }
                }
            }
        } finally {
            runCatching { multicastLock?.release() }
        }
    }.flowOn(Dispatchers.IO)

    private data class Endpoint(val address: String, val port: Int, val protocol: Protocol)

    private data class SsdpResponse(
        val sourceIp: String,
        val raw: String,
        val headers: Map<String, String>,
    )

    private fun probe(endpoint: Endpoint, searchTargets: List<String>, budgetMillis: Long): List<SsdpResponse> {
        val results = mutableListOf<SsdpResponse>()
        val socket = runCatching { DatagramSocket() }.getOrNull() ?: return results

        try {
            socket.reuseAddress = true
            socket.broadcast = true
            socket.soTimeout = 900

            val group = InetAddress.getByName(endpoint.address)
            searchTargets.forEach { target ->
                val message = buildMSearch(endpoint, target)
                val bytes = message.toByteArray(Charsets.UTF_8)
                runCatching {
                    socket.send(DatagramPacket(bytes, bytes.size, InetSocketAddress(group, endpoint.port)))
                }.onFailure { Log.d(TAG, "M-SEARCH send failed to ${endpoint.address}", it) }
            }

            val deadline = System.currentTimeMillis() + budgetMillis
            val buffer = ByteArray(8192)
            while (System.currentTimeMillis() < deadline) {
                val packet = DatagramPacket(buffer, buffer.size)
                try {
                    socket.receive(packet)
                } catch (timeout: SocketTimeoutException) {
                    continue
                } catch (error: Exception) {
                    Log.d(TAG, "SSDP receive failed", error)
                    break
                }
                val text = String(packet.data, 0, packet.length, Charsets.UTF_8)
                results += SsdpResponse(
                    sourceIp = packet.address?.hostAddress.orEmpty(),
                    raw = text,
                    headers = parseHeaders(text),
                )
            }
        } finally {
            runCatching { socket.close() }
        }
        return results
    }

    private fun buildMSearch(endpoint: Endpoint, searchTarget: String): String = buildString {
        append("M-SEARCH * HTTP/1.1\r\n")
        append("HOST: ${endpoint.address}:${endpoint.port}\r\n")
        append("MAN: \"ssdp:discover\"\r\n")
        append("MX: 2\r\n")
        append("ST: $searchTarget\r\n")
        // Yeelight's firmware requires this non-standard trailer and ignores the request without it.
        if (endpoint.protocol == Protocol.YEELIGHT) append("\r\n") else append("\r\n")
    }

    private fun parseHeaders(raw: String): Map<String, String> =
        raw.lineSequence()
            .drop(1)
            .mapNotNull { line ->
                val index = line.indexOf(':')
                if (index <= 0) return@mapNotNull null
                line.substring(0, index).trim().lowercase() to line.substring(index + 1).trim()
            }
            .filter { it.second.isNotEmpty() }
            .toMap()

    private fun describe(location: String): DeviceDescription? = runCatching {
        val request = Request.Builder().url(location).header("User-Agent", USER_AGENT).build()
        httpClient.newCall(request).execute().use { response ->
            if (!response.isSuccessful) return null
            val body = response.body?.string().orEmpty()
            if (body.isBlank()) return null
            DeviceDescription(
                friendlyName = body.tagValue("friendlyName"),
                manufacturer = body.tagValue("manufacturer"),
                modelName = body.tagValue("modelName"),
                modelNumber = body.tagValue("modelNumber"),
                serialNumber = body.tagValue("serialNumber"),
                udn = body.tagValue("UDN"),
                deviceType = body.tagValue("deviceType"),
            )
        }
    }.getOrNull()

    private data class DeviceDescription(
        val friendlyName: String?,
        val manufacturer: String?,
        val modelName: String?,
        val modelNumber: String?,
        val serialNumber: String?,
        val udn: String?,
        val deviceType: String?,
    )

    /** Lightweight tag extraction — a full XML parser is overkill for six flat fields. */
    private fun String.tagValue(tag: String): String? {
        val open = "<$tag>"
        val close = "</$tag>"
        val start = indexOf(open, ignoreCase = true).takeIf { it >= 0 } ?: return null
        val end = indexOf(close, startIndex = start, ignoreCase = true).takeIf { it > start } ?: return null
        return substring(start + open.length, end)
            .trim()
            .replace("&amp;", "&")
            .replace("&lt;", "<")
            .replace("&gt;", ">")
            .replace("&quot;", "\"")
            .replace("&apos;", "'")
            .takeIf { it.isNotBlank() }
    }

    private fun toObservation(
        response: SsdpResponse,
        endpoint: Endpoint,
        description: DeviceDescription? = null,
    ): Observation {
        val headers = response.headers
        val server = headers["server"] ?: headers["x-user-agent"]
        val usn = headers["usn"]
        val udn = description?.udn ?: usn?.substringBefore("::")?.trim()

        val protocol = identifyProtocol(endpoint, headers, description, server)

        val identityKeys = buildSet {
            udn?.takeIf { it.isNotBlank() }?.let { add("udn:${it.lowercase()}") }
            response.sourceIp.takeIf { it.isNotBlank() }?.let { add("ip:$it") }
            description?.serialNumber?.let { add("serial:${it.lowercase()}") }
            // Yeelight and Govee use an id header rather than a UDN.
            headers["id"]?.let { add("vendorid:${it.lowercase()}") }
        }

        return Observation(
            protocol = protocol,
            source = DiscoverySource.SSDP,
            identityKeys = identityKeys,
            ipAddress = response.sourceIp.takeIf { it.isNotBlank() },
            hostname = headers["location"]?.let { runCatching { java.net.URI(it).host }.getOrNull() },
            port = headers["location"]?.let { runCatching { java.net.URI(it).port }.getOrNull() }
                ?.takeIf { it > 0 },
            displayName = description?.friendlyName,
            manufacturer = description?.manufacturer ?: manufacturerFromServer(server),
            model = description?.modelName ?: description?.modelNumber,
            firmwareVersion = server,
            serialNumber = description?.serialNumber,
            attributes = buildMap {
                headers["st"]?.let { put("Search target", it) }
                headers["nt"]?.let { put("Notification type", it) }
                usn?.let { put("USN", it) }
                server?.let { put("Server", it) }
                headers["location"]?.let { put("Description URL", it) }
                description?.deviceType?.let { put("Device type", it) }
                description?.modelNumber?.let { put("Model number", it) }
                put("Discovery port", endpoint.port.toString())
            },
            seenAtMillis = System.currentTimeMillis(),
        )
    }

    private fun identifyProtocol(
        endpoint: Endpoint,
        headers: Map<String, String>,
        description: DeviceDescription?,
        server: String?,
    ): Protocol {
        if (endpoint.protocol != Protocol.SSDP) return endpoint.protocol

        val haystack = buildString {
            append(headers["st"].orEmpty()).append(' ')
            append(headers["usn"].orEmpty()).append(' ')
            append(headers["location"].orEmpty()).append(' ')
            append(server.orEmpty()).append(' ')
            append(description?.manufacturer.orEmpty()).append(' ')
            append(description?.modelName.orEmpty()).append(' ')
            append(description?.deviceType.orEmpty())
        }.lowercase()

        return when {
            "sonos" in haystack -> Protocol.SONOS
            "belkin" in haystack || "wemo" in haystack -> Protocol.WEMO
            "roku" in haystack -> Protocol.ROKU_ECP
            "webos" in haystack || "lg electronics" in haystack -> Protocol.WEBOS
            "samsung" in haystack && "tv" in haystack -> Protocol.SAMSUNG_TIZEN
            "hue" in haystack || "philips" in haystack -> Protocol.PHILIPS_HUE
            "onvif" in haystack || "network_video" in haystack -> Protocol.ONVIF
            "smartthings" in haystack -> Protocol.SMARTTHINGS
            "amazon" in haystack || "echo" in haystack -> Protocol.ALEXA
            "mediarenderer" in haystack || "mediaserver" in haystack -> Protocol.DLNA
            else -> Protocol.SSDP
        }
    }

    private fun manufacturerFromServer(server: String?): String? {
        val text = server?.trim().orEmpty()
        if (text.isBlank()) return null
        // SERVER looks like "Linux/3.14 UPnP/1.0 Sonos/70.3-35220". Take the product token.
        return text.split(' ')
            .lastOrNull { '/' in it }
            ?.substringBefore('/')
            ?.takeIf { it.length in 2..24 && it.any(Char::isLetter) }
    }

    private fun searchTargetsFor(depth: ScanDepth): List<String> = when (depth) {
        ScanDepth.QUICK -> listOf("ssdp:all")
        ScanDepth.STANDARD -> listOf("ssdp:all", "upnp:rootdevice")
        ScanDepth.DEEP -> listOf(
            "ssdp:all",
            "upnp:rootdevice",
            "urn:schemas-upnp-org:device:MediaRenderer:1",
            "urn:schemas-upnp-org:device:MediaServer:1",
            "urn:schemas-upnp-org:device:InternetGatewayDevice:1",
            "urn:schemas-upnp-org:device:Basic:1",
            "urn:Belkin:device:**",
            "roku:ecp",
            "urn:dial-multiscreen-org:service:dial:1",
            "urn:schemas-sony-com:service:ScalarWebAPI:1",
        )
    }

    private companion object {
        const val TAG = "SsdpScanner"
        const val USER_AGENT = "Hyperscale/1.0 UPnP/1.0"

        val ENDPOINTS = listOf(
            Endpoint("239.255.255.250", 1900, Protocol.SSDP),
            Endpoint("239.255.255.250", 1982, Protocol.YEELIGHT),
            Endpoint("239.255.255.250", 4001, Protocol.GOVEE_LAN),
        )

        fun defaultClient(): OkHttpClient = OkHttpClient.Builder()
            .connectTimeout(1500, TimeUnit.MILLISECONDS)
            .readTimeout(1500, TimeUnit.MILLISECONDS)
            .callTimeout(2500, TimeUnit.MILLISECONDS)
            .retryOnConnectionFailure(false)
            .build()
    }
}
