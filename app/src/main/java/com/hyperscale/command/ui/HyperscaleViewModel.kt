package com.hyperscale.command.ui

import androidx.lifecycle.ViewModel
import androidx.lifecycle.ViewModelProvider
import androidx.lifecycle.viewModelScope
import com.hyperscale.command.AppContainer
import com.hyperscale.command.core.model.Device
import com.hyperscale.command.core.model.DeviceClass
import com.hyperscale.command.core.model.DeviceStatus
import com.hyperscale.command.core.model.Protocol
import com.hyperscale.command.core.model.ProtocolFamily
import com.hyperscale.command.core.model.ScanProgress
import com.hyperscale.command.data.AppSettings
import com.hyperscale.command.discovery.ScanDepth
import com.hyperscale.command.discovery.ScannerAvailability
import com.hyperscale.command.homey.HomeyCandidate
import com.hyperscale.command.homey.HomeyConnectionState
import com.hyperscale.command.homey.HomeyFlowDto
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.SharingStarted
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.combine
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.flow.stateIn
import kotlinx.coroutines.launch

/** What the user is currently filtering the device list by. */
data class DeviceFilter(
    val query: String = "",
    val protocol: Protocol? = null,
    val family: ProtocolFamily? = null,
    val deviceClass: DeviceClass? = null,
    val onlyControllable: Boolean = false,
    val onlyFavourites: Boolean = false,
) {
    val isActive: Boolean
        get() = query.isNotBlank() || protocol != null || family != null ||
            deviceClass != null || onlyControllable || onlyFavourites
}

data class HyperscaleUiState(
    val devices: List<Device> = emptyList(),
    val filteredDevices: List<Device> = emptyList(),
    val scanProgress: ScanProgress = ScanProgress(),
    val settings: AppSettings = AppSettings(),
    val filter: DeviceFilter = DeviceFilter(),
    val homeyState: HomeyConnectionState = HomeyConnectionState.Disconnected,
    val homeyFlows: List<HomeyFlowDto> = emptyList(),
    val selectedDeviceId: String? = null,
) {
    val selectedDevice: Device?
        get() = devices.firstOrNull { it.id == selectedDeviceId }

    /** Counts per protocol, used by the filter chips and the protocol screen. */
    val protocolCounts: Map<Protocol, Int>
        get() = devices
            .flatMap { it.protocols }
            .groupingBy { it }
            .eachCount()

    val controllableCount: Int get() = devices.count { it.isControllable }
    val onlineCount: Int
        get() = devices.count { it.status == DeviceStatus.ONLINE }
}

/**
 * The single view model behind every screen.
 *
 * One shared state holder rather than one per screen: on a foldable, two panes are visible at once
 * and both are looking at the same device list. Splitting that across view models would mean
 * synchronising selection between them for no benefit.
 */
class HyperscaleViewModel(private val container: AppContainer) : ViewModel() {

    private val repository = container.deviceRepository
    private val homey = container.homeyRepository
    private val settingsRepository = container.settingsRepository

    private val _filter = MutableStateFlow(DeviceFilter())
    private val _selectedDeviceId = MutableStateFlow<String?>(null)
    private val _transientMessage = MutableStateFlow<String?>(null)

    /** One-shot text for the snackbar: errors from Homey, permission notes, scan summaries. */
    val transientMessage: StateFlow<String?> = _transientMessage

    val homeyCandidates: StateFlow<List<HomeyCandidate>> = homey.candidates

    val uiState: StateFlow<HyperscaleUiState> = combine(
        repository.devices,
        repository.scanProgress,
        settingsRepository.settings,
        _filter,
        combine(homey.connectionState, homey.flows, _selectedDeviceId) { state, flows, selected ->
            Triple(state, flows, selected)
        },
    ) { devices, progress, settings, filter, homeyBundle ->
        val (homeyState, flows, selectedId) = homeyBundle
        HyperscaleUiState(
            devices = devices,
            filteredDevices = devices.filter { it.matchesFilter(filter) },
            scanProgress = progress,
            settings = settings,
            filter = filter,
            homeyState = homeyState,
            homeyFlows = flows,
            // Drop a selection that has aged out of the list rather than showing an empty pane.
            selectedDeviceId = selectedId?.takeIf { id -> devices.any { it.id == id } },
        )
    }.stateIn(viewModelScope, SharingStarted.WhileSubscribed(5_000), HyperscaleUiState())

    init {
        viewModelScope.launch {
            repository.warmStart()
            if (settingsRepository.settings.first().scanOnLaunch) repository.startScan()
        }
    }

    // ───────────────────────────── discovery ─────────────────────────────

    fun startScan(depth: ScanDepth? = null) {
        viewModelScope.launch { repository.startScan(depth) }
    }

    fun stopScan() = repository.stopScan()

    fun scannerAvailability(): Map<String, ScannerAvailability> = repository.scannerAvailability()

    // ───────────────────────────── selection & filtering ─────────────────────────────

    fun selectDevice(deviceId: String?) {
        _selectedDeviceId.value = deviceId
    }

    fun setQuery(query: String) {
        _filter.value = _filter.value.copy(query = query)
    }

    fun setProtocolFilter(protocol: Protocol?) {
        _filter.value = _filter.value.copy(protocol = protocol, family = null)
    }

    fun setFamilyFilter(family: ProtocolFamily?) {
        _filter.value = _filter.value.copy(family = family, protocol = null)
    }

    fun setDeviceClassFilter(deviceClass: DeviceClass?) {
        _filter.value = _filter.value.copy(deviceClass = deviceClass)
    }

    fun toggleControllableOnly() {
        _filter.value = _filter.value.copy(onlyControllable = !_filter.value.onlyControllable)
    }

    fun toggleFavouritesOnly() {
        _filter.value = _filter.value.copy(onlyFavourites = !_filter.value.onlyFavourites)
    }

    fun clearFilters() {
        _filter.value = DeviceFilter()
    }

    // ───────────────────────────── device actions ─────────────────────────────

    fun setDeviceOn(device: Device, on: Boolean) {
        viewModelScope.launch {
            repository.setCapability(device, "onoff", on)?.let { _transientMessage.value = it }
        }
    }

    fun setCapability(device: Device, capabilityId: String, value: Any) {
        viewModelScope.launch {
            repository.setCapability(device, capabilityId, value)?.let { _transientMessage.value = it }
        }
    }

    fun setFavourite(device: Device, favourite: Boolean) {
        viewModelScope.launch { repository.setFavourite(device.id, favourite) }
    }

    fun renameDevice(device: Device, nickname: String?) {
        viewModelScope.launch { repository.setNickname(device.id, nickname) }
    }

    fun forgetDevice(device: Device) {
        viewModelScope.launch {
            repository.forget(device.id)
            if (_selectedDeviceId.value == device.id) _selectedDeviceId.value = null
        }
    }

    // ───────────────────────────── Homey ─────────────────────────────

    fun discoverHomeys() {
        viewModelScope.launch { homey.discoverHomeys() }
    }

    fun connectHomey(address: String, token: String) {
        viewModelScope.launch {
            val failure = homey.saveAndConnect(address, token)
            _transientMessage.value = failure ?: "Connected to Homey at $address"
        }
    }

    fun refreshHomey() {
        viewModelScope.launch {
            homey.refresh()?.let { _transientMessage.value = it }
        }
    }

    fun disconnectHomey() {
        viewModelScope.launch { homey.disconnect() }
    }

    fun triggerFlow(flow: HomeyFlowDto) {
        viewModelScope.launch {
            val failure = homey.triggerFlow(flow.id)
            _transientMessage.value = failure ?: "Started “${flow.name ?: flow.id}”"
        }
    }

    fun startHomeyPolling() = homey.startPolling()

    fun stopHomeyPolling() = homey.stopPolling()

    // ───────────────────────────── settings ─────────────────────────────

    fun toggleProtocol(protocol: Protocol, enabled: Boolean) {
        viewModelScope.launch { settingsRepository.toggleProtocol(protocol, enabled) }
    }

    fun setAllProtocols(enabled: Boolean) {
        viewModelScope.launch {
            settingsRepository.setEnabledProtocols(
                if (enabled) Protocol.entries.toSet() else emptySet(),
            )
        }
    }

    fun setScanDepth(depth: ScanDepth) {
        viewModelScope.launch { settingsRepository.setScanDepth(depth) }
    }

    fun setScanOnLaunch(enabled: Boolean) {
        viewModelScope.launch { settingsRepository.setScanOnLaunch(enabled) }
    }

    fun setShowOfflineDevices(enabled: Boolean) {
        viewModelScope.launch { settingsRepository.setShowOfflineDevices(enabled) }
    }

    fun setUseDynamicColour(enabled: Boolean) {
        viewModelScope.launch { settingsRepository.setUseDynamicColour(enabled) }
    }

    fun consumeMessage() {
        _transientMessage.value = null
    }

    fun showMessage(message: String) {
        _transientMessage.value = message
    }

    class Factory(private val container: AppContainer) : ViewModelProvider.Factory {
        @Suppress("UNCHECKED_CAST")
        override fun <T : ViewModel> create(modelClass: Class<T>): T {
            require(modelClass.isAssignableFrom(HyperscaleViewModel::class.java)) {
                "Unknown ViewModel class: ${modelClass.name}"
            }
            return HyperscaleViewModel(container) as T
        }
    }
}

private fun Device.matchesFilter(filter: DeviceFilter): Boolean {
    if (!matches(filter.query)) return false
    if (filter.protocol != null && filter.protocol !in protocols) return false
    if (filter.family != null && protocols.none { it.family == filter.family }) return false
    if (filter.deviceClass != null && deviceClass != filter.deviceClass) return false
    if (filter.onlyControllable && !isControllable) return false
    if (filter.onlyFavourites && !isFavourite) return false
    return true
}
