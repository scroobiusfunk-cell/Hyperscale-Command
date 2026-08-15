package com.hyperscale.command

import android.content.Context
import com.hyperscale.command.data.DeviceRepository
import com.hyperscale.command.data.DeviceStore
import com.hyperscale.command.data.SettingsRepository
import com.hyperscale.command.discovery.DiscoveryEngine
import com.hyperscale.command.discovery.ProtocolScanner
import com.hyperscale.command.discovery.scanners.BleScanner
import com.hyperscale.command.discovery.scanners.MdnsScanner
import com.hyperscale.command.discovery.scanners.NetworkSweepScanner
import com.hyperscale.command.discovery.scanners.SsdpScanner
import com.hyperscale.command.discovery.scanners.UdpProbeScanner
import com.hyperscale.command.homey.HomeyClient
import com.hyperscale.command.homey.HomeyRepository
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob

/**
 * Manual dependency container.
 *
 * A single-module app with this few collaborators does not need an annotation processor and a
 * compile-time graph; wiring them by hand keeps the build fast and the object lifetimes obvious.
 */
class AppContainer(context: Context) {

    private val appContext = context.applicationContext

    val applicationScope: CoroutineScope =
        CoroutineScope(SupervisorJob() + Dispatchers.Default)

    val settingsRepository: SettingsRepository = SettingsRepository(appContext)

    val deviceStore: DeviceStore = DeviceStore(appContext)

    /**
     * Scanner order matters only for readability; they all run concurrently. mDNS is first
     * because it produces the richest identity data and therefore the best merge anchors.
     */
    val scanners: List<ProtocolScanner> = listOf(
        MdnsScanner(),
        SsdpScanner(),
        UdpProbeScanner(),
        BleScanner(),
        NetworkSweepScanner(),
    )

    val discoveryEngine: DiscoveryEngine = DiscoveryEngine(
        appContext = appContext,
        scanners = scanners,
        scope = applicationScope,
    )

    val homeyRepository: HomeyRepository = HomeyRepository(
        appContext = appContext,
        settingsRepository = settingsRepository,
        client = HomeyClient(),
    )

    val deviceRepository: DeviceRepository = DeviceRepository(
        engine = discoveryEngine,
        homeyRepository = homeyRepository,
        deviceStore = deviceStore,
        settingsRepository = settingsRepository,
        scope = applicationScope,
    )
}
