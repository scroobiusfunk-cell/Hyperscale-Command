package com.hyperscale.command.discovery

import android.content.Context
import android.net.ConnectivityManager
import android.net.LinkAddress
import android.net.NetworkCapabilities
import android.net.wifi.WifiManager
import java.net.Inet4Address
import java.net.InetAddress
import java.net.NetworkInterface

/**
 * Snapshot of the LAN the phone is currently attached to. Everything the IP scanners need in
 * order to know *where* to look.
 */
data class NetworkEnvironment(
    val localAddress: Inet4Address?,
    val prefixLength: Int,
    val broadcastAddress: InetAddress?,
    val interfaceName: String?,
    val isWifi: Boolean,
    val isMetered: Boolean,
    val ssid: String?,
) {
    val isUsable: Boolean get() = localAddress != null && prefixLength in 8..30

    /**
     * Every host address in the local subnet, excluding the network and broadcast addresses.
     *
     * Capped at [MAX_SWEEP_HOSTS]: a /16 would be 65k probes, which is neither polite nor useful
     * on a home network. A /24 (the overwhelmingly common case) yields 254 hosts.
     */
    fun hostAddresses(maxHosts: Int = MAX_SWEEP_HOSTS): List<String> {
        val local = localAddress ?: return emptyList()
        if (prefixLength !in 8..30) return emptyList()

        val addressInt = local.address.fold(0) { acc, byte -> (acc shl 8) or (byte.toInt() and 0xFF) }
        val mask = if (prefixLength == 0) 0 else (-1 shl (32 - prefixLength))
        val network = addressInt and mask
        val broadcast = network or mask.inv()

        val total = (broadcast.toLong() and 0xFFFFFFFFL) - (network.toLong() and 0xFFFFFFFFL) - 1
        if (total <= 0) return emptyList()

        val count = minOf(total, maxHosts.toLong()).toInt()
        return (1..count).map { offset ->
            val host = network + offset
            "${(host ushr 24) and 0xFF}.${(host ushr 16) and 0xFF}.${(host ushr 8) and 0xFF}.${host and 0xFF}"
        }
    }

    /** Directed broadcast for the current subnet, e.g. 192.168.1.255. */
    fun directedBroadcast(): String? {
        val local = localAddress ?: return null
        if (prefixLength !in 8..30) return null
        val addressInt = local.address.fold(0) { acc, byte -> (acc shl 8) or (byte.toInt() and 0xFF) }
        val mask = -1 shl (32 - prefixLength)
        val broadcast = (addressInt and mask) or mask.inv()
        return "${(broadcast ushr 24) and 0xFF}.${(broadcast ushr 16) and 0xFF}." +
            "${(broadcast ushr 8) and 0xFF}.${broadcast and 0xFF}"
    }

    companion object {
        const val MAX_SWEEP_HOSTS = 1022

        val Unavailable = NetworkEnvironment(
            localAddress = null,
            prefixLength = 0,
            broadcastAddress = null,
            interfaceName = null,
            isWifi = false,
            isMetered = false,
            ssid = null,
        )

        @Suppress("DEPRECATION")
        fun capture(context: Context): NetworkEnvironment {
            val connectivity = context.getSystemService(ConnectivityManager::class.java)
            val network = connectivity?.activeNetwork
            val capabilities = network?.let { connectivity.getNetworkCapabilities(it) }
            val linkProperties = network?.let { connectivity.getLinkProperties(it) }

            val isWifi = capabilities?.hasTransport(NetworkCapabilities.TRANSPORT_WIFI) == true
            val isMetered = capabilities?.hasCapability(
                NetworkCapabilities.NET_CAPABILITY_NOT_METERED,
            )?.not() ?: true

            val linkAddress: LinkAddress? = linkProperties?.linkAddresses
                ?.firstOrNull { it.address is Inet4Address && !it.address.isLoopbackAddress }

            var address = linkAddress?.address as? Inet4Address
            var prefix = linkAddress?.prefixLength ?: 0

            // LinkProperties can be null on some OEM builds and in multi-network states; fall
            // back to walking the interfaces directly.
            if (address == null) {
                val fallback = fromInterfaces()
                address = fallback?.first
                prefix = fallback?.second ?: 24
            }

            val ssid = if (isWifi) {
                runCatching {
                    val wifi = context.applicationContext.getSystemService(WifiManager::class.java)
                    wifi?.connectionInfo?.ssid?.trim('"')?.takeIf { it.isNotBlank() && it != "<unknown ssid>" }
                }.getOrNull()
            } else {
                null
            }

            return NetworkEnvironment(
                localAddress = address,
                prefixLength = prefix,
                broadcastAddress = address?.let { runCatching { InetAddress.getByName(
                    NetworkEnvironment(it, prefix, null, null, isWifi, isMetered, null).directedBroadcast(),
                ) }.getOrNull() },
                interfaceName = linkProperties?.interfaceName,
                isWifi = isWifi,
                isMetered = isMetered,
                ssid = ssid,
            )
        }

        private fun fromInterfaces(): Pair<Inet4Address, Int>? = runCatching {
            NetworkInterface.getNetworkInterfaces()
                ?.toList()
                ?.asSequence()
                ?.filter { it.isUp && !it.isLoopback }
                ?.flatMap { nif -> nif.interfaceAddresses.asSequence() }
                ?.mapNotNull { ia ->
                    (ia.address as? Inet4Address)?.let { it to ia.networkPrefixLength.toInt() }
                }
                ?.firstOrNull { (addr, _) -> addr.isSiteLocalAddress }
        }.getOrNull()
    }
}
