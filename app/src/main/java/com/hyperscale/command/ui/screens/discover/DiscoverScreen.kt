package com.hyperscale.command.ui.screens.discover

import android.Manifest
import android.content.pm.PackageManager
import android.os.Build
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.animation.AnimatedVisibility
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.LazyRow
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.outlined.Bluetooth
import androidx.compose.material.icons.outlined.Radar
import androidx.compose.material.icons.outlined.Stop
import androidx.compose.material.icons.outlined.WifiFind
import androidx.compose.material3.AssistChip
import androidx.compose.material3.AssistChipDefaults
import androidx.compose.material3.Button
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.FilterChip
import androidx.compose.material3.Icon
import androidx.compose.material3.LinearProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.core.content.ContextCompat
import com.hyperscale.command.core.model.Device
import com.hyperscale.command.core.model.DeviceStatus
import com.hyperscale.command.core.model.Protocol
import com.hyperscale.command.discovery.ScanDepth
import com.hyperscale.command.ui.HyperscaleUiState
import com.hyperscale.command.ui.HyperscaleViewModel
import com.hyperscale.command.ui.WindowWidth
import com.hyperscale.command.ui.adaptive.FoldState
import com.hyperscale.command.ui.adaptive.HingeAwareTwoPane
import com.hyperscale.command.ui.components.DeviceCard
import com.hyperscale.command.ui.components.EmptyState
import com.hyperscale.command.ui.components.RadarBlip
import com.hyperscale.command.ui.components.RadarSweep
import com.hyperscale.command.ui.components.SectionHeader
import com.hyperscale.command.ui.components.radarAngleFor
import com.hyperscale.command.ui.components.radarDistanceFor
import com.hyperscale.command.ui.theme.LocalStatusColours

/**
 * The landing screen: a live picture of what is on the network right now.
 *
 * On a wide window the radar sits beside the results so both are visible while a scan runs. On a
 * narrow one the radar collapses to a compact header, because a full-width circle would push every
 * result below the fold.
 */
@Composable
fun DiscoverScreen(
    state: HyperscaleUiState,
    foldState: FoldState,
    widthClass: WindowWidth,
    viewModel: HyperscaleViewModel,
    modifier: Modifier = Modifier,
) {
    val statusColours = LocalStatusColours.current

    val blips = remember(state.devices) {
        state.devices.map { device ->
            RadarBlip(
                id = device.id,
                angleDegrees = radarAngleFor(device.id),
                normalisedDistance = radarDistanceFor(device.rssi),
                colour = when (device.status) {
                    DeviceStatus.ONLINE -> statusColours.online
                    DeviceStatus.RECENTLY_SEEN -> statusColours.stale
                    else -> statusColours.offline
                },
            )
        }
    }

    val recentlyFound = remember(state.devices) {
        state.devices.sortedByDescending { it.firstSeenMillis }.take(40)
    }

    if (widthClass == WindowWidth.COMPACT) {
        Column(modifier = modifier.fillMaxSize()) {
            ScanHeader(state = state, viewModel = viewModel, compact = true)
            Box(
                modifier = Modifier
                    .fillMaxWidth()
                    .padding(horizontal = 20.dp, vertical = 4.dp),
                contentAlignment = Alignment.Center,
            ) {
                // Constrained width so the dial stays a glanceable header rather than eating
                // the whole cover screen.
                RadarSweep(
                    isScanning = state.scanProgress.isScanning,
                    blips = blips,
                    modifier = Modifier.width(190.dp),
                )
            }
            DiscoveryResults(
                devices = recentlyFound,
                state = state,
                viewModel = viewModel,
                modifier = Modifier.fillMaxSize(),
            )
        }
    } else {
        HingeAwareTwoPane(
            foldState = foldState,
            modifier = modifier.fillMaxSize(),
            firstPaneWeight = 0.42f,
            first = {
                Column(
                    modifier = Modifier
                        .fillMaxSize()
                        .padding(20.dp),
                    verticalArrangement = Arrangement.spacedBy(20.dp),
                ) {
                    RadarSweep(
                        isScanning = state.scanProgress.isScanning,
                        blips = blips,
                        modifier = Modifier.fillMaxWidth(),
                    )
                    ScanControls(state = state, viewModel = viewModel)
                    ScanSummary(state = state)
                }
            },
            second = {
                Column(modifier = Modifier.fillMaxSize()) {
                    ScanHeader(state = state, viewModel = viewModel, compact = false)
                    DiscoveryResults(
                        devices = recentlyFound,
                        state = state,
                        viewModel = viewModel,
                        modifier = Modifier.fillMaxSize(),
                    )
                }
            },
        )
    }
}

@Composable
private fun ScanHeader(
    state: HyperscaleUiState,
    viewModel: HyperscaleViewModel,
    compact: Boolean,
) {
    Column(
        modifier = Modifier
            .fillMaxWidth()
            .padding(horizontal = 20.dp, vertical = 14.dp),
        verticalArrangement = Arrangement.spacedBy(10.dp),
    ) {
        Row(
            modifier = Modifier.fillMaxWidth(),
            horizontalArrangement = Arrangement.SpaceBetween,
            verticalAlignment = Alignment.CenterVertically,
        ) {
            Column {
                Text(
                    text = "Discover",
                    style = MaterialTheme.typography.headlineMedium,
                )
                Text(
                    text = state.scanProgress.statusLine.ifBlank {
                        "${state.devices.size} devices · ${state.onlineCount} online · " +
                            "${state.controllableCount} controllable"
                    },
                    style = MaterialTheme.typography.bodyMedium,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )
            }

            if (compact) {
                ScanButton(state = state, viewModel = viewModel)
            }
        }

        AnimatedVisibility(visible = state.scanProgress.isScanning) {
            LinearProgressIndicator(
                progress = { state.scanProgress.fraction },
                modifier = Modifier
                    .fillMaxWidth()
                    .height(4.dp),
            )
        }

        if (compact) {
            PermissionPrompts(viewModel = viewModel)
        }
    }
}

@Composable
private fun ScanControls(state: HyperscaleUiState, viewModel: HyperscaleViewModel) {
    Column(verticalArrangement = Arrangement.spacedBy(12.dp)) {
        ScanButton(state = state, viewModel = viewModel, fillWidth = true)

        SectionHeader(title = "Scan depth")
        Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            ScanDepth.entries.forEach { depth ->
                FilterChip(
                    selected = state.settings.scanDepth == depth,
                    onClick = { viewModel.setScanDepth(depth) },
                    label = { Text(depth.label) },
                )
            }
        }
        Text(
            text = state.settings.scanDepth.description,
            style = MaterialTheme.typography.bodyMedium,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
        )

        PermissionPrompts(viewModel = viewModel)
    }
}

@Composable
private fun ScanButton(
    state: HyperscaleUiState,
    viewModel: HyperscaleViewModel,
    fillWidth: Boolean = false,
) {
    val modifier = if (fillWidth) Modifier.fillMaxWidth() else Modifier

    if (state.scanProgress.isScanning) {
        OutlinedButton(onClick = { viewModel.stopScan() }, modifier = modifier) {
            Icon(Icons.Outlined.Stop, contentDescription = null, modifier = Modifier.size(18.dp))
            Spacer(Modifier.size(8.dp))
            Text("Stop scan")
        }
    } else {
        Button(onClick = { viewModel.startScan() }, modifier = modifier) {
            Icon(Icons.Outlined.Radar, contentDescription = null, modifier = Modifier.size(18.dp))
            Spacer(Modifier.size(8.dp))
            Text("Scan network")
        }
    }
}

/**
 * A live breakdown of what the scan is doing, by protocol family.
 *
 * This exists because multi-protocol discovery is otherwise opaque — without it, a scan that finds
 * nothing is indistinguishable from a scan that never ran.
 */
@Composable
private fun ScanSummary(state: HyperscaleUiState) {
    val counts = state.protocolCounts
    val topProtocols = remember(counts) {
        counts.entries.sortedByDescending { it.value }.take(8)
    }

    Column(verticalArrangement = Arrangement.spacedBy(10.dp)) {
        SectionHeader(
            title = "Protocols seen",
            trailing = "${counts.size} of ${Protocol.entries.size - 1}",
        )

        if (topProtocols.isEmpty()) {
            Text(
                text = "Nothing detected yet. Start a scan to sweep every enabled protocol.",
                style = MaterialTheme.typography.bodyMedium,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
        } else {
            LazyRow(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                items(topProtocols, key = { it.key.name }) { (protocol, count) ->
                    AssistChip(
                        onClick = { },
                        label = { Text("${protocol.displayName} · $count") },
                        colors = AssistChipDefaults.assistChipColors(),
                    )
                }
            }
        }

        if (state.scanProgress.activeProtocols.isNotEmpty()) {
            Text(
                text = "Active: " + state.scanProgress.activeProtocols
                    .take(6)
                    .joinToString(", ") { it.displayName },
                style = MaterialTheme.typography.labelMedium,
                color = MaterialTheme.colorScheme.primary,
            )
        }
    }
}

@Composable
private fun DiscoveryResults(
    devices: List<Device>,
    state: HyperscaleUiState,
    viewModel: HyperscaleViewModel,
    modifier: Modifier = Modifier,
) {
    if (devices.isEmpty()) {
        EmptyState(
            icon = Icons.Outlined.WifiFind,
            title = "Nothing found yet",
            body = "Make sure you are on your home Wi-Fi, then run a scan. Devices on Zigbee, " +
                "Z-Wave, 433 MHz and infrared will appear once Homey Pro is connected — no phone " +
                "has those radios.",
            modifier = modifier,
        )
        return
    }

    LazyColumn(
        modifier = modifier,
        contentPadding = androidx.compose.foundation.layout.PaddingValues(
            start = 20.dp,
            end = 20.dp,
            top = 4.dp,
            bottom = 24.dp,
        ),
        verticalArrangement = Arrangement.spacedBy(10.dp),
    ) {
        item {
            SectionHeader(
                title = "Most recently found",
                trailing = "${devices.size}",
                modifier = Modifier.padding(bottom = 4.dp),
            )
        }

        items(devices, key = { it.id }) { device ->
            DeviceCard(
                device = device,
                selected = device.id == state.selectedDeviceId,
                onClick = { viewModel.selectDevice(device.id) },
                onToggle = if (device.isControllable && device.isOn != null) {
                    { on -> viewModel.setDeviceOn(device, on) }
                } else {
                    null
                },
                onFavourite = { viewModel.setFavourite(device, !device.isFavourite) },
            )
        }
    }
}

/**
 * Asks for Bluetooth and nearby-devices permission at the moment it is needed, with a reason.
 *
 * Deliberately not a launch-time permission wall: the user should see the app find things over
 * mDNS and SSDP first, so the request for Bluetooth arrives with obvious context.
 */
@Composable
private fun PermissionPrompts(viewModel: HyperscaleViewModel) {
    val context = LocalContext.current

    val bluetoothPermission = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S) {
        Manifest.permission.BLUETOOTH_SCAN
    } else {
        Manifest.permission.ACCESS_FINE_LOCATION
    }

    var granted by remember {
        mutableStateOf(
            ContextCompat.checkSelfPermission(context, bluetoothPermission) ==
                PackageManager.PERMISSION_GRANTED,
        )
    }

    val launcher = rememberLauncherForActivityResult(
        contract = ActivityResultContracts.RequestMultiplePermissions(),
    ) { results ->
        granted = results[bluetoothPermission] == true
        if (granted) {
            viewModel.startScan()
        } else {
            viewModel.showMessage(
                "Without Bluetooth permission, locks, sensors and un-commissioned Matter " +
                    "devices stay invisible. Everything on Wi-Fi still works.",
            )
        }
    }

    LaunchedEffect(Unit) {
        granted = ContextCompat.checkSelfPermission(context, bluetoothPermission) ==
            PackageManager.PERMISSION_GRANTED
    }

    if (granted) return

    Card(
        modifier = Modifier.fillMaxWidth(),
        shape = RoundedCornerShape(16.dp),
        colors = CardDefaults.cardColors(
            containerColor = MaterialTheme.colorScheme.tertiaryContainer,
        ),
    ) {
        Row(
            modifier = Modifier.padding(14.dp),
            horizontalArrangement = Arrangement.spacedBy(12.dp),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            Icon(
                imageVector = Icons.Outlined.Bluetooth,
                contentDescription = null,
                tint = MaterialTheme.colorScheme.onTertiaryContainer,
            )
            Column(modifier = Modifier.weight(1f)) {
                Text(
                    text = "Turn on Bluetooth scanning",
                    style = MaterialTheme.typography.titleMedium,
                    fontWeight = FontWeight.SemiBold,
                    color = MaterialTheme.colorScheme.onTertiaryContainer,
                )
                Text(
                    text = "Finds BLE locks, sensors, trackers and Matter devices waiting to pair.",
                    style = MaterialTheme.typography.bodyMedium,
                    color = MaterialTheme.colorScheme.onTertiaryContainer,
                )
            }
            Button(
                onClick = {
                    val permissions = buildList {
                        add(bluetoothPermission)
                        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S) {
                            add(Manifest.permission.BLUETOOTH_CONNECT)
                        }
                        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
                            add(Manifest.permission.NEARBY_WIFI_DEVICES)
                        }
                    }
                    launcher.launch(permissions.toTypedArray())
                },
            ) {
                Text("Allow")
            }
        }
    }
}
