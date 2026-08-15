package com.hyperscale.command.discovery

import android.content.Context
import android.util.Log
import com.hyperscale.command.core.model.Device
import com.hyperscale.command.core.model.Observation
import com.hyperscale.command.core.model.Protocol
import com.hyperscale.command.core.model.ScanProgress
import java.util.concurrent.atomic.AtomicInteger
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.channels.BufferOverflow
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.MutableSharedFlow
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asSharedFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.buffer
import kotlinx.coroutines.flow.catch
import kotlinx.coroutines.flow.channelFlow
import kotlinx.coroutines.flow.onCompletion
import kotlinx.coroutines.isActive
import kotlinx.coroutines.launch
import kotlinx.coroutines.withTimeoutOrNull

/**
 * Runs every enabled [ProtocolScanner] concurrently and folds the results into one device list.
 *
 * Scanners are isolated from each other: one throwing, hanging or being denied a permission never
 * stops the pass. Everything is bounded by a per-scanner timeout so a scan always terminates.
 */
class DiscoveryEngine(
    private val appContext: Context,
    private val scanners: List<ProtocolScanner>,
    private val scope: CoroutineScope = CoroutineScope(SupervisorJob() + Dispatchers.Default),
) {
    private val merger = DeviceMerger()

    private val _devices = MutableStateFlow<List<Device>>(emptyList())
    val devices: StateFlow<List<Device>> = _devices.asStateFlow()

    private val _progress = MutableStateFlow(ScanProgress())
    val progress: StateFlow<ScanProgress> = _progress.asStateFlow()

    private val _newDeviceEvents = MutableSharedFlow<Device>(
        replay = 0,
        extraBufferCapacity = 32,
        onBufferOverflow = BufferOverflow.DROP_OLDEST,
    )

    /** Emits once per device that had never been seen before this pass. Drives the "new!" toast. */
    val newDeviceEvents: Flow<Device> = _newDeviceEvents.asSharedFlow()

    private var scanJob: Job? = null

    val isScanning: Boolean get() = scanJob?.isActive == true

    fun seed(known: List<Device>) {
        merger.seed(known)
        _devices.value = merger.snapshot()
    }

    fun availability(): Map<String, ScannerAvailability> =
        scanners.associate { it.id to runCatching { it.availability(appContext) }
            .getOrElse { error -> ScannerAvailability.Unavailable(error.message ?: "Unavailable") } }

    /**
     * Starts a scan pass. Calling this while a pass is running restarts it, which is what the
     * user means when they hit refresh mid-scan.
     */
    fun startScan(
        depth: ScanDepth = ScanDepth.STANDARD,
        enabledProtocols: Set<Protocol> = ProtocolSelection.allDirect(),
        enabledScannerIds: Set<String>? = null,
    ) {
        scanJob?.cancel()
        scanJob = scope.launch { runScan(depth, enabledProtocols, enabledScannerIds) }
    }

    fun stopScan() {
        scanJob?.cancel()
        scanJob = null
        _progress.value = _progress.value.copy(isScanning = false, statusLine = "Scan stopped")
    }

    /** Merges externally-sourced observations (e.g. the Homey bridge) into the same device list. */
    suspend fun ingest(observations: Flow<Observation>) {
        observations
            .catch { error -> Log.w(TAG, "Ingest failed", error) }
            .collect { observation ->
                val before = merger.snapshot().size
                val device = merger.absorb(observation)
                _devices.value = merger.snapshot()
                if (merger.snapshot().size > before) _newDeviceEvents.tryEmit(device)
            }
    }

    private suspend fun runScan(
        depth: ScanDepth,
        enabledProtocols: Set<Protocol>,
        enabledScannerIds: Set<String>?,
    ) {
        val network = NetworkEnvironment.capture(appContext)
        val startedAt = System.currentTimeMillis()

        val active = scanners.filter { scanner ->
            (enabledScannerIds == null || scanner.id in enabledScannerIds) &&
                scanner.protocols.any { it in enabledProtocols } &&
                scanner.availability(appContext).isReady
        }

        val timeout = when (depth) {
            ScanDepth.QUICK -> 6_000L
            ScanDepth.STANDARD -> 15_000L
            ScanDepth.DEEP -> 45_000L
        }

        val scanContext = ScanContext(
            context = appContext,
            network = network,
            timeoutMillis = timeout,
            depth = depth,
            enabledProtocols = enabledProtocols,
        )

        val completed = AtomicInteger(0)
        _progress.value = ScanProgress(
            isScanning = true,
            startedAtMillis = startedAt,
            totalScanners = active.size,
            devicesFound = _devices.value.size,
            statusLine = if (active.isEmpty()) {
                "No scanners available — check permissions and Wi-Fi"
            } else {
                "Scanning ${active.size} protocol engines…"
            },
        )

        if (active.isEmpty()) {
            _progress.value = _progress.value.copy(isScanning = false)
            return
        }

        // channelFlow gives every scanner its own coroutine while keeping one collection point,
        // which is what lets the (non-thread-safe) merger stay lock-free.
        val observations = channelFlow {
            active.forEach { scanner ->
                launch {
                    val label = scanner.label
                    _progress.update { it.copy(activeProtocols = it.activeProtocols + scanner.protocols) }
                    withTimeoutOrNull(timeout) {
                        runCatching {
                            scanner.scan(scanContext)
                                .catch { error -> Log.w(TAG, "Scanner $label failed", error) }
                                .collect { send(it) }
                        }.onFailure { error -> Log.w(TAG, "Scanner $label crashed", error) }
                    }
                    val done = completed.incrementAndGet()
                    _progress.update {
                        it.copy(
                            completedScanners = done,
                            activeProtocols = it.activeProtocols - scanner.protocols,
                            statusLine = "$label finished · $done of ${active.size}",
                        )
                    }
                }
            }
        }.buffer(capacity = 256)

        observations
            .onCompletion {
                merger.ageOut(
                    nowMillis = System.currentTimeMillis(),
                    staleAfterMillis = STALE_AFTER_MILLIS,
                    offlineAfterMillis = OFFLINE_AFTER_MILLIS,
                )
                _devices.value = merger.snapshot()
                _progress.update {
                    it.copy(
                        isScanning = false,
                        activeProtocols = emptySet(),
                        devicesFound = _devices.value.size,
                        statusLine = "Found ${_devices.value.size} devices",
                    )
                }
            }
            .collect { observation ->
                if (!scope.isActive) return@collect
                val sizeBefore = merger.snapshot().size
                val device = merger.absorb(observation)
                val snapshot = merger.snapshot()
                _devices.value = snapshot
                if (snapshot.size > sizeBefore) {
                    _newDeviceEvents.tryEmit(device)
                }
                _progress.update { it.copy(devicesFound = snapshot.size) }
            }
    }

    private inline fun MutableStateFlow<ScanProgress>.update(transform: (ScanProgress) -> ScanProgress) {
        value = transform(value)
    }

    private companion object {
        const val TAG = "DiscoveryEngine"
        const val STALE_AFTER_MILLIS = 5 * 60_000L
        const val OFFLINE_AFTER_MILLIS = 30 * 60_000L
    }
}

object ProtocolSelection {
    fun allDirect(): Set<Protocol> = Protocol.entries.toSet()
}
