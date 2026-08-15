package com.hyperscale.command.data

import com.hyperscale.command.core.model.Device
import com.hyperscale.command.core.model.DeviceClass
import com.hyperscale.command.core.model.DeviceStatus
import com.hyperscale.command.core.model.Protocol
import com.hyperscale.command.core.model.ScanProgress
import com.hyperscale.command.discovery.DiscoveryEngine
import com.hyperscale.command.discovery.ScanDepth
import com.hyperscale.command.discovery.ScannerAvailability
import com.hyperscale.command.homey.HomeyDeviceDto
import com.hyperscale.command.homey.HomeyDeviceMapper
import com.hyperscale.command.homey.HomeyRepository
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.FlowPreview
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.SharingStarted
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asFlow
import kotlinx.coroutines.flow.combine
import kotlinx.coroutines.flow.debounce
import kotlinx.coroutines.flow.distinctUntilChanged
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.flow.map
import kotlinx.coroutines.flow.stateIn
import kotlinx.coroutines.launch

/**
 * The single source of truth the UI reads from.
 *
 * Fuses three streams into one device list:
 *  1. live discovery from the phone's own radios,
 *  2. Homey Pro's inventory of everything the phone cannot see,
 *  3. the persisted store, which carries the user's nicknames and favourites forward.
 */
@OptIn(FlowPreview::class)
class DeviceRepository(
    private val engine: DiscoveryEngine,
    private val homeyRepository: HomeyRepository,
    private val deviceStore: DeviceStore,
    private val settingsRepository: SettingsRepository,
    private val scope: CoroutineScope,
) {

    val scanProgress: StateFlow<ScanProgress> = engine.progress

    val newDeviceEvents: Flow<Device> = engine.newDeviceEvents

    /**
     * Discovered devices, enriched with Homey capabilities where the two overlap.
     *
     * The enrichment pass is what makes a Hue bulb found over mDNS and the same bulb reported by
     * Homey become one controllable row rather than two half-useful ones.
     */
    val devices: StateFlow<List<Device>> = combine(
        engine.devices,
        homeyRepository.devices,
        homeyRepository.zones,
        settingsRepository.settings,
    ) { discovered, homeyDevices, zones, settings ->
        discovered
            .map { device -> enrich(device, homeyDevices, zones) }
            .filter { device -> settings.showOfflineDevices || device.status != DeviceStatus.OFFLINE }
            .sortedWith(
                compareByDescending<Device> { it.isFavourite }
                    .thenByDescending { it.isControllable }
                    .thenBy { it.deviceClass.ordinal }
                    .thenBy { it.displayName.lowercase() },
            )
    }.stateIn(scope, SharingStarted.WhileSubscribed(5_000), emptyList())

    init {
        // Persist quietly in the background whenever the list settles.
        scope.launch {
            devices
                .debounce(2_000)
                .distinctUntilChanged { old, new -> old.map { it.id } == new.map { it.id } }
                .collect { current -> if (current.isNotEmpty()) deviceStore.save(current) }
        }

        // Keep Homey's inventory folded into the discovery list as it changes.
        scope.launch {
            homeyRepository.devices.collect { ingestHomeyInventory() }
        }
    }

    suspend fun warmStart() {
        val known = deviceStore.load()
        if (known.isNotEmpty()) engine.seed(known)
        homeyRepository.connectFromSettings()
    }

    suspend fun startScan(depth: ScanDepth? = null) {
        val settings = settingsRepository.settings.first()
        engine.startScan(
            depth = depth ?: settings.scanDepth,
            enabledProtocols = settings.enabledProtocols.ifEmpty { Protocol.entries.toSet() },
        )
        // Homey's inventory is refreshed alongside every scan so hub-only devices stay current.
        if (settings.isHomeyConfigured) {
            homeyRepository.refresh()
            ingestHomeyInventory()
        }
    }

    fun stopScan() = engine.stopScan()

    fun scannerAvailability(): Map<String, ScannerAvailability> = engine.availability()

    suspend fun setNickname(deviceId: String, nickname: String?) {
        deviceStore.update(deviceId) { it.copy(nickname = nickname?.takeIf { name -> name.isNotBlank() }) }
        engine.seed(deviceStore.devices.value)
    }

    suspend fun setFavourite(deviceId: String, favourite: Boolean) {
        deviceStore.update(deviceId) { it.copy(isFavourite = favourite) }
        engine.seed(deviceStore.devices.value)
    }

    suspend fun forget(deviceId: String) = deviceStore.forget(deviceId)

    /** Sends a control command through Homey. Returns an error message, or null on success. */
    suspend fun setCapability(device: Device, capabilityId: String, value: Any): String? {
        val homeyId = device.homeyDeviceId
            ?: return "${device.displayName} has no Homey connection, so it cannot be controlled here yet."
        return homeyRepository.setCapability(homeyId, capabilityId, value)
    }

    private suspend fun ingestHomeyInventory() {
        val observations = homeyRepository.currentObservations()
        if (observations.isEmpty()) return
        engine.ingest(observations.asFlow())
    }

    private fun enrich(
        device: Device,
        homeyDevices: Map<String, HomeyDeviceDto>,
        zones: Map<String, String>,
    ): Device {
        val homeyId = device.identityKeys
            .firstOrNull { it.startsWith("homey:") }
            ?.removePrefix("homey:")

        val dto = homeyId?.let { homeyDevices[it] } ?: return device

        val capabilities = HomeyDeviceMapper.toCapabilities(dto)
        val homeyClass = HomeyDeviceMapper.toDeviceClass(dto)

        return device.copy(
            homeyDeviceId = dto.id,
            homeyZoneName = dto.zoneName ?: dto.zone?.let { zones[it] },
            capabilities = capabilities,
            // Homey's own classification is authoritative — it comes from the device driver.
            deviceClass = if (homeyClass != DeviceClass.OTHER) homeyClass else device.deviceClass,
            name = if (device.name.isBlank() || device.name == "Unknown device") {
                dto.name ?: device.name
            } else {
                device.name
            },
        )
    }
}
