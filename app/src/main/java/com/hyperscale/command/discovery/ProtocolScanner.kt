package com.hyperscale.command.discovery

import android.content.Context
import com.hyperscale.command.core.model.DiscoverySource
import com.hyperscale.command.core.model.Observation
import com.hyperscale.command.core.model.Protocol
import kotlinx.coroutines.flow.Flow

/** Everything a scanner needs to know for one pass. */
data class ScanContext(
    val context: Context,
    val network: NetworkEnvironment,
    /** Overall budget for this scanner. Scanners must return by roughly this time. */
    val timeoutMillis: Long,
    /** Deep scans widen port lists and host sweeps; quick scans stay cheap and fast. */
    val depth: ScanDepth,
    /** Protocols the user has enabled. Scanners should skip work for disabled ones. */
    val enabledProtocols: Set<Protocol>,
)

enum class ScanDepth(val label: String, val description: String) {
    QUICK("Quick", "Passive listeners and broadcasts only. A few seconds."),
    STANDARD("Standard", "Adds a subnet sweep and the common control ports."),
    DEEP("Deep", "Full port matrix, longer listen windows, repeated probes."),
}

/**
 * One discovery mechanism. Scanners are independent, run concurrently, and must never throw:
 * a failing radio or a blocked multicast group should degrade that one protocol, not the scan.
 */
interface ProtocolScanner {
    val id: String
    val label: String
    val source: DiscoverySource

    /** Protocols this scanner can produce observations for. */
    val protocols: Set<Protocol>

    /** Runtime availability, e.g. Bluetooth off, permission not granted, no Wi-Fi. */
    fun availability(context: Context): ScannerAvailability

    /** Emits observations as they arrive. Must complete within the context's timeout. */
    fun scan(scanContext: ScanContext): Flow<Observation>
}

sealed interface ScannerAvailability {
    data object Ready : ScannerAvailability

    /** Blocked but fixable by the user; [permission] can be requested if non-null. */
    data class NeedsPermission(val permission: String, val rationale: String) : ScannerAvailability

    /** Blocked by hardware or system state, e.g. Bluetooth disabled. */
    data class Unavailable(val reason: String) : ScannerAvailability

    val isReady: Boolean get() = this is Ready
}
