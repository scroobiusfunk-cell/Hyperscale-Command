package com.hyperscale.command.ui.screens.homey

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.LazyRow
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.outlined.Bolt
import androidx.compose.material.icons.outlined.Hub
import androidx.compose.material.icons.outlined.Refresh
import androidx.compose.material.icons.outlined.Search
import androidx.compose.material3.Button
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.input.ImeAction
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.text.input.PasswordVisualTransformation
import androidx.compose.ui.unit.dp
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import com.hyperscale.command.homey.HomeyConnectionState
import com.hyperscale.command.ui.HyperscaleUiState
import com.hyperscale.command.ui.HyperscaleViewModel
import com.hyperscale.command.ui.WindowWidth
import com.hyperscale.command.ui.components.DeviceChipCard
import com.hyperscale.command.ui.components.SectionHeader
import com.hyperscale.command.ui.theme.LocalStatusColours

/**
 * Homey Pro setup and control.
 *
 * The setup flow deliberately leads with automatic discovery: asking someone to find their hub's
 * IP address is the single most common place a local-network integration loses people. The manual
 * entry path stays available underneath for anyone with a static address or a segmented VLAN.
 */
@Composable
fun HomeyScreen(
    state: HyperscaleUiState,
    widthClass: WindowWidth,
    viewModel: HyperscaleViewModel,
    modifier: Modifier = Modifier,
) {
    when (val connection = state.homeyState) {
        is HomeyConnectionState.Connected -> ConnectedView(
            connection = connection,
            state = state,
            widthClass = widthClass,
            viewModel = viewModel,
            modifier = modifier,
        )

        else -> SetupView(
            connection = connection,
            viewModel = viewModel,
            modifier = modifier,
        )
    }
}

@Composable
private fun ConnectedView(
    connection: HomeyConnectionState.Connected,
    state: HyperscaleUiState,
    widthClass: WindowWidth,
    viewModel: HyperscaleViewModel,
    modifier: Modifier = Modifier,
) {
    val statusColours = LocalStatusColours.current
    val bridged = remember(state.devices) {
        state.devices.filter { it.homeyDeviceId != null }
    }
    val byZone = remember(bridged) {
        bridged.groupBy { it.homeyZoneName ?: "Unassigned" }.toSortedMap()
    }

    LazyColumn(
        modifier = modifier.fillMaxSize(),
        contentPadding = PaddingValues(horizontal = 20.dp, vertical = 16.dp),
        verticalArrangement = Arrangement.spacedBy(16.dp),
    ) {
        item {
            Surface(
                shape = RoundedCornerShape(18.dp),
                color = MaterialTheme.colorScheme.surfaceContainer,
                modifier = Modifier.fillMaxWidth(),
            ) {
                Column(
                    modifier = Modifier.padding(16.dp),
                    verticalArrangement = Arrangement.spacedBy(10.dp),
                ) {
                    Row(
                        verticalAlignment = Alignment.CenterVertically,
                        horizontalArrangement = Arrangement.spacedBy(12.dp),
                    ) {
                        Icon(
                            imageVector = Icons.Outlined.Hub,
                            contentDescription = null,
                            tint = statusColours.online,
                            modifier = Modifier.size(28.dp),
                        )
                        Column(modifier = Modifier.weight(1f)) {
                            Text(
                                text = connection.system?.homeyModelName ?: "Homey Pro",
                                style = MaterialTheme.typography.titleLarge,
                            )
                            Text(
                                text = connection.address +
                                    (connection.system?.homeyVersion?.let { " · firmware $it" } ?: ""),
                                style = MaterialTheme.typography.bodyMedium,
                                color = MaterialTheme.colorScheme.onSurfaceVariant,
                            )
                        }
                        OutlinedButton(onClick = viewModel::refreshHomey) {
                            Icon(
                                Icons.Outlined.Refresh,
                                contentDescription = null,
                                modifier = Modifier.size(18.dp),
                            )
                            Text("  Sync")
                        }
                    }

                    Text(
                        text = "${connection.deviceCount} devices across ${connection.zoneCount} " +
                            "zones · everything below is bridged from radios this phone does not have",
                        style = MaterialTheme.typography.bodyMedium,
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                    )

                    TextButton(onClick = viewModel::disconnectHomey) {
                        Text("Disconnect", color = MaterialTheme.colorScheme.error)
                    }
                }
            }
        }

        if (state.homeyFlows.isNotEmpty()) {
            item { SectionHeader(title = "Flows", trailing = "${state.homeyFlows.size}") }
            item {
                LazyRow(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    items(
                        state.homeyFlows.filter { it.enabled && !it.broken }.take(30),
                        key = { it.id },
                    ) { flow ->
                        OutlinedButton(onClick = { viewModel.triggerFlow(flow) }) {
                            Icon(
                                Icons.Outlined.Bolt,
                                contentDescription = null,
                                modifier = Modifier.size(16.dp),
                            )
                            Text("  ${flow.name ?: "Flow"}")
                        }
                    }
                }
            }
        }

        byZone.forEach { (zone, devices) ->
            item(key = "zone-$zone") {
                SectionHeader(title = zone, trailing = "${devices.size}")
            }
            item(key = "zone-row-$zone") {
                LazyRow(horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                    items(devices, key = { it.id }) { device ->
                        DeviceChipCard(
                            device = device,
                            onClick = { viewModel.selectDevice(device.id) },
                        )
                    }
                }
            }
        }

        if (bridged.isEmpty()) {
            item {
                Text(
                    text = "Homey is connected but has not reported any devices yet. Pull Sync, " +
                        "or check that the API key has device read permission.",
                    style = MaterialTheme.typography.bodyMedium,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )
            }
        }
    }
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
private fun SetupView(
    connection: HomeyConnectionState,
    viewModel: HyperscaleViewModel,
    modifier: Modifier = Modifier,
) {
    val candidates by viewModel.homeyCandidates.collectAsStateWithLifecycle()
    var address by remember { mutableStateOf("") }
    var token by remember { mutableStateOf("") }

    val isDiscovering = connection is HomeyConnectionState.Discovering
    val isConnecting = connection is HomeyConnectionState.Connecting
    val failure = (connection as? HomeyConnectionState.Failed)?.reason

    LazyColumn(
        modifier = modifier.fillMaxSize(),
        contentPadding = PaddingValues(horizontal = 20.dp, vertical = 16.dp),
        verticalArrangement = Arrangement.spacedBy(16.dp),
    ) {
        item {
            Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                Text("Connect Homey Pro", style = MaterialTheme.typography.headlineMedium)
                Text(
                    text = "Hyperscale talks to Homey over your local network only — no Athom " +
                        "cloud account, and nothing about your home leaves the house. Once " +
                        "connected, every Zigbee, Z-Wave, Thread, 433 MHz and infrared device " +
                        "Homey knows about joins your inventory with working controls.",
                    style = MaterialTheme.typography.bodyMedium,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )
            }
        }

        item {
            Button(
                onClick = viewModel::discoverHomeys,
                enabled = !isDiscovering,
                modifier = Modifier.fillMaxWidth(),
            ) {
                if (isDiscovering) {
                    CircularProgressIndicator(
                        modifier = Modifier.size(18.dp),
                        strokeWidth = 2.dp,
                    )
                    Text("  Searching your network…")
                } else {
                    Icon(
                        Icons.Outlined.Search,
                        contentDescription = null,
                        modifier = Modifier.size(18.dp),
                    )
                    Text("  Find Homey automatically")
                }
            }
        }

        if (candidates.isNotEmpty()) {
            item { SectionHeader(title = "Found on your network") }
            items(candidates, key = { it.address }) { candidate ->
                Surface(
                    shape = RoundedCornerShape(14.dp),
                    color = MaterialTheme.colorScheme.surfaceContainer,
                    modifier = Modifier.fillMaxWidth(),
                ) {
                    Row(
                        modifier = Modifier.padding(14.dp),
                        verticalAlignment = Alignment.CenterVertically,
                        horizontalArrangement = Arrangement.spacedBy(12.dp),
                    ) {
                        Icon(Icons.Outlined.Hub, contentDescription = null)
                        Column(modifier = Modifier.weight(1f)) {
                            Text(
                                text = candidate.modelName ?: "Homey",
                                style = MaterialTheme.typography.titleMedium,
                            )
                            Text(
                                text = candidate.address +
                                    (candidate.version?.let { " · $it" } ?: ""),
                                style = MaterialTheme.typography.bodyMedium,
                                color = MaterialTheme.colorScheme.onSurfaceVariant,
                            )
                        }
                        TextButton(onClick = { address = candidate.address }) { Text("Use") }
                    }
                }
            }
        }

        item {
            Column(verticalArrangement = Arrangement.spacedBy(12.dp)) {
                SectionHeader(title = "Connection details")

                OutlinedTextField(
                    value = address,
                    onValueChange = { address = it },
                    label = { Text("Homey address") },
                    placeholder = { Text("192.168.1.20 or homey.local") },
                    singleLine = true,
                    keyboardOptions = KeyboardOptions(
                        keyboardType = KeyboardType.Uri,
                        imeAction = ImeAction.Next,
                    ),
                    modifier = Modifier.fillMaxWidth(),
                )

                OutlinedTextField(
                    value = token,
                    onValueChange = { token = it },
                    label = { Text("Personal Access Token") },
                    singleLine = true,
                    visualTransformation = PasswordVisualTransformation(),
                    keyboardOptions = KeyboardOptions(
                        keyboardType = KeyboardType.Password,
                        imeAction = ImeAction.Done,
                    ),
                    modifier = Modifier.fillMaxWidth(),
                )

                Text(
                    text = "Create the token on your Homey: Settings → General → API Keys → New " +
                        "API Key. Give it device and flow permissions. The token is stored only " +
                        "on this phone and is excluded from cloud backup.",
                    style = MaterialTheme.typography.bodyMedium,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )

                failure?.let {
                    Surface(
                        shape = RoundedCornerShape(12.dp),
                        color = MaterialTheme.colorScheme.errorContainer,
                        modifier = Modifier.fillMaxWidth(),
                    ) {
                        Text(
                            text = it,
                            style = MaterialTheme.typography.bodyMedium,
                            color = MaterialTheme.colorScheme.onErrorContainer,
                            modifier = Modifier.padding(12.dp),
                        )
                    }
                }

                Button(
                    onClick = { viewModel.connectHomey(address, token) },
                    enabled = address.isNotBlank() && token.isNotBlank() && !isConnecting,
                    modifier = Modifier.fillMaxWidth(),
                ) {
                    if (isConnecting) {
                        CircularProgressIndicator(
                            modifier = Modifier.size(18.dp),
                            strokeWidth = 2.dp,
                        )
                        Text("  Connecting…")
                    } else {
                        Text("Connect")
                    }
                }
            }
        }
    }
}
