package com.hyperscale.command.homey

import android.content.Context
import android.util.Log
import com.hyperscale.command.core.model.Observation
import com.hyperscale.command.data.SettingsRepository
import com.hyperscale.command.discovery.NetworkEnvironment
import java.util.concurrent.TimeUnit
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.coroutineScope
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.isActive
import kotlinx.coroutines.launch
import kotlinx.coroutines.sync.Semaphore
import kotlinx.coroutines.sync.withPermit
import kotlinx.coroutines.withContext
import kotlinx.serialization.json.JsonPrimitive
import okhttp3.OkHttpClient
import okhttp3.Request

/**
 * Owns the relationship with the user's Homey Pro: finding it, authenticating, keeping its device
 * inventory in sync, and sending control commands back.
 *
 * Everything is local-network only. Homey's own cloud is never contacted.
 */
class HomeyRepository(
    private val appContext: Context,
    private val settingsRepository: SettingsRepository,
    private val client: HomeyClient = HomeyClient(),
    private val scope: CoroutineScope = CoroutineScope(SupervisorJob() + Dispatchers.IO),
) {

    private val _connectionState = MutableStateFlow<HomeyConnectionState>(HomeyConnectionState.Disconnected)
    val connectionState: StateFlow<HomeyConnectionState> = _connectionState.asStateFlow()

    private val _devices = MutableStateFlow<Map<String, HomeyDeviceDto>>(emptyMap())

    /** Homey's device inventory, keyed by Homey device id. */
    val devices: StateFlow<Map<String, HomeyDeviceDto>> = _devices.asStateFlow()

    private val _zones = MutableStateFlow<Map<String, String>>(emptyMap())
    val zones: StateFlow<Map<String, String>> = _zones.asStateFlow()

    private val _flows = MutableStateFlow<List<HomeyFlowDto>>(emptyList())
    val flows: StateFlow<List<HomeyFlowDto>> = _flows.asStateFlow()

    private val _candidates = MutableStateFlow<List<HomeyCandidate>>(emptyList())

    /** Homey Pros found on the LAN during setup. */
    val candidates: StateFlow<List<HomeyCandidate>> = _candidates.asStateFlow()

    private var pollJob: Job? = null

    /** Connects using whatever is stored in settings. Safe to call repeatedly. */
    fun connectFromSettings() {
        scope.launch {
            val settings = settingsRepository.settings.first()
            val address = settings.homeyAddress
            val token = settings.homeyToken
            if (address.isNullOrBlank() || token.isNullOrBlank()) {
                _connectionState.value = HomeyConnectionState.Disconnected
                return@launch
            }
            connect(address, token)
        }
    }

    /**
     * Verifies credentials, then loads zones, devices and flows.
     * Returns the failure reason, or null on success, so the setup screen can show it inline.
     */
    suspend fun connect(address: String, token: String): String? {
        _connectionState.value = HomeyConnectionState.Connecting(address)

        return when (val system = client.verify(address, token)) {
            is HomeyClient.HomeyResult.Failure -> {
                _connectionState.value = HomeyConnectionState.Failed(address, system.reason)
                system.reason
            }

            is HomeyClient.HomeyResult.Success -> {
                sync(address, token, system.value)
                null
            }
        }
    }

    /** Persists the credentials and connects. Used by the setup flow. */
    suspend fun saveAndConnect(address: String, token: String): String? {
        val failure = connect(address, token)
        if (failure == null) {
            settingsRepository.setHomeyCredentials(address, token)
        }
        return failure
    }

    suspend fun disconnect() {
        pollJob?.cancel()
        pollJob = null
        settingsRepository.setHomeyCredentials(null, null)
        _devices.value = emptyMap()
        _zones.value = emptyMap()
        _flows.value = emptyList()
        _connectionState.value = HomeyConnectionState.Disconnected
    }

    /** One full inventory refresh. */
    suspend fun refresh(): String? {
        val settings = settingsRepository.settings.first()
        val address = settings.homeyAddress ?: return "Homey is not set up yet"
        val token = settings.homeyToken ?: return "Homey API key is missing"
        return connect(address, token)
    }

    private suspend fun sync(address: String, token: String, system: HomeySystemDto?) {
        coroutineScope {
            val zonesDeferred = launch {
                when (val result = client.fetchZones(address, token)) {
                    is HomeyClient.HomeyResult.Success ->
                        _zones.value = result.value.associate { it.id to (it.name ?: "Zone") }

                    is HomeyClient.HomeyResult.Failure ->
                        Log.d(TAG, "Zone sync failed: ${result.reason}")
                }
            }

            val flowsDeferred = launch {
                when (val result = client.fetchFlows(address, token)) {
                    is HomeyClient.HomeyResult.Success -> _flows.value = result.value
                    is HomeyClient.HomeyResult.Failure ->
                        Log.d(TAG, "Flow sync failed: ${result.reason}")
                }
            }

            zonesDeferred.join()
            flowsDeferred.join()
        }

        when (val result = client.fetchDevices(address, token)) {
            is HomeyClient.HomeyResult.Failure -> {
                _connectionState.value = HomeyConnectionState.Failed(address, result.reason)
            }

            is HomeyClient.HomeyResult.Success -> {
                _devices.value = result.value.associateBy { it.id }
                _connectionState.value = HomeyConnectionState.Connected(
                    address = address,
                    system = system,
                    deviceCount = result.value.size,
                    zoneCount = _zones.value.size,
                    lastSyncMillis = System.currentTimeMillis(),
                )
            }
        }
    }

    /** Turns the current Homey inventory into observations for the discovery engine to merge. */
    fun currentObservations(): List<Observation> {
        val state = _connectionState.value
        val address = when (state) {
            is HomeyConnectionState.Connected -> state.address
            is HomeyConnectionState.Connecting -> state.address
            else -> return emptyList()
        }
        val zoneNames = _zones.value
        return _devices.value.values.map { device ->
            HomeyDeviceMapper.toObservation(device, zoneNames, address)
        }
    }

    /**
     * Sends a capability write to Homey, then refreshes that one device so the UI reflects what
     * actually happened rather than what we hoped would happen.
     */
    suspend fun setCapability(
        deviceId: String,
        capabilityId: String,
        value: Any,
    ): String? {
        val settings = settingsRepository.settings.first()
        val address = settings.homeyAddress ?: return "Homey is not set up"
        val token = settings.homeyToken ?: return "Homey API key is missing"

        val element = when (value) {
            is Boolean -> JsonPrimitive(value)
            is Double -> JsonPrimitive(value)
            is Float -> JsonPrimitive(value.toDouble())
            is Int -> JsonPrimitive(value)
            is String -> JsonPrimitive(value)
            else -> return "Unsupported value type for $capabilityId"
        }

        return when (val result = client.setCapability(address, token, deviceId, capabilityId, element)) {
            is HomeyClient.HomeyResult.Failure -> result.reason
            is HomeyClient.HomeyResult.Success -> {
                applyOptimisticUpdate(deviceId, capabilityId, element)
                null
            }
        }
    }

    suspend fun triggerFlow(flowId: String): String? {
        val settings = settingsRepository.settings.first()
        val address = settings.homeyAddress ?: return "Homey is not set up"
        val token = settings.homeyToken ?: return "Homey API key is missing"
        return when (val result = client.triggerFlow(address, token, flowId)) {
            is HomeyClient.HomeyResult.Failure -> result.reason
            is HomeyClient.HomeyResult.Success -> null
        }
    }

    private fun applyOptimisticUpdate(
        deviceId: String,
        capabilityId: String,
        value: kotlinx.serialization.json.JsonElement,
    ) {
        val current = _devices.value
        val device = current[deviceId] ?: return
        val capabilities = device.capabilitiesObj?.toMutableMap() ?: return
        val capability = capabilities[capabilityId] ?: return
        capabilities[capabilityId] = capability.copy(value = value)
        _devices.value = current + (deviceId to device.copy(capabilitiesObj = capabilities))
    }

    /**
     * Polls Homey for state changes.
     *
     * Homey's realtime channel is a socket.io stream, which would mean pulling in a full
     * socket.io client for one feature. Polling every few seconds while the app is in the
     * foreground is a fraction of the code and, on a LAN, indistinguishable to the user.
     */
    fun startPolling(intervalMillis: Long = 5_000L) {
        pollJob?.cancel()
        pollJob = scope.launch {
            while (isActive) {
                delay(intervalMillis)
                val settings = settingsRepository.settings.first()
                val address = settings.homeyAddress ?: continue
                val token = settings.homeyToken ?: continue
                when (val result = client.fetchDevices(address, token)) {
                    is HomeyClient.HomeyResult.Success ->
                        _devices.value = result.value.associateBy { it.id }

                    is HomeyClient.HomeyResult.Failure ->
                        Log.d(TAG, "Poll failed: ${result.reason}")
                }
            }
        }
    }

    fun stopPolling() {
        pollJob?.cancel()
        pollJob = null
    }

    /**
     * Looks for Homey Pros on the LAN so the user does not have to hunt for an IP address.
     *
     * A Homey answers `/api/manager/system/` with 401 when no token is supplied, which is itself
     * a reliable signature — an ordinary web server on port 80 returns 200 or 404 instead.
     */
    suspend fun discoverHomeys() {
        _connectionState.value = HomeyConnectionState.Discovering
        _candidates.value = emptyList()

        val found = mutableListOf<HomeyCandidate>()

        // The mDNS name works on most home networks and costs one request.
        probeCandidate("homey.local")?.let { found += it }

        val network = NetworkEnvironment.capture(appContext)
        if (network.isUsable) {
            val gate = Semaphore(permits = 24)
            withContext(Dispatchers.IO) {
                coroutineScope {
                    network.hostAddresses().forEach { host ->
                        launch {
                            gate.withPermit {
                                probeCandidate(host)?.let { candidate ->
                                    synchronized(found) { found += candidate }
                                }
                            }
                        }
                    }
                }
            }
        }

        _candidates.value = found.distinctBy { it.address }
        _connectionState.value = HomeyConnectionState.Disconnected
    }

    private suspend fun probeCandidate(address: String): HomeyCandidate? = withContext(Dispatchers.IO) {
        runCatching {
            val request = Request.Builder()
                .url("http://$address/api/manager/system/")
                .get()
                .build()

            probeClient.newCall(request).execute().use { response ->
                val body = if (response.isSuccessful) response.body?.string().orEmpty() else ""
                val looksLikeHomey = response.code == 401 ||
                    body.contains("homeyVersion") ||
                    body.contains("homeyModelName")

                if (!looksLikeHomey) return@use null

                HomeyCandidate(
                    address = address,
                    hostname = address.takeIf { it.any(Char::isLetter) },
                    modelName = body.extractJsonString("homeyModelName"),
                    version = body.extractJsonString("homeyVersion"),
                )
            }
        }.getOrNull()
    }

    private fun String.extractJsonString(key: String): String? {
        val index = indexOf("\"$key\"").takeIf { it >= 0 } ?: return null
        val colon = indexOf(':', index).takeIf { it >= 0 } ?: return null
        val rest = substring(colon + 1).trimStart()
        if (!rest.startsWith('"')) return null
        return rest.drop(1).substringBefore('"').takeIf { it.isNotBlank() }
    }

    private companion object {
        const val TAG = "HomeyRepository"

        /** Short timeouts: a sweep of 254 addresses must not take minutes. */
        val probeClient: OkHttpClient = OkHttpClient.Builder()
            .connectTimeout(600, TimeUnit.MILLISECONDS)
            .readTimeout(600, TimeUnit.MILLISECONDS)
            .callTimeout(1200, TimeUnit.MILLISECONDS)
            .retryOnConnectionFailure(false)
            .build()
    }
}
