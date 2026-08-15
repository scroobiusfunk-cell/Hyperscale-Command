package com.hyperscale.command.ui.screens.protocols

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.outlined.CheckCircle
import androidx.compose.material.icons.outlined.Hub
import androidx.compose.material.icons.outlined.RadioButtonUnchecked
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Surface
import androidx.compose.material3.Switch
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import com.hyperscale.command.core.model.Protocol
import com.hyperscale.command.core.model.ProtocolCatalog
import com.hyperscale.command.core.model.ProtocolFamily
import com.hyperscale.command.core.model.Reachability
import com.hyperscale.command.ui.HyperscaleUiState
import com.hyperscale.command.ui.HyperscaleViewModel
import com.hyperscale.command.ui.components.SectionHeader
import com.hyperscale.command.ui.theme.LocalStatusColours

/**
 * The complete protocol catalogue, grouped by family, with a switch per protocol.
 *
 * This screen exists to answer two questions honestly: what can this app look for, and what can it
 * genuinely find *from a phone*. Protocols that need a hub are labelled as such rather than being
 * quietly omitted or, worse, offered as a scan option that could never succeed.
 */
@Composable
fun ProtocolsScreen(
    state: HyperscaleUiState,
    viewModel: HyperscaleViewModel,
    onShowDevices: () -> Unit,
    modifier: Modifier = Modifier,
) {
    val counts = state.protocolCounts
    val enabled = state.settings.enabledProtocols
    var expandedFamily by remember { mutableStateOf<ProtocolFamily?>(ProtocolFamily.IP_NETWORK) }

    LazyColumn(
        modifier = modifier.fillMaxSize(),
        contentPadding = PaddingValues(horizontal = 20.dp, vertical = 16.dp),
        verticalArrangement = Arrangement.spacedBy(14.dp),
    ) {
        item {
            Column(verticalArrangement = Arrangement.spacedBy(6.dp)) {
                Text("Protocols", style = MaterialTheme.typography.headlineMedium)
                Text(
                    text = "${ProtocolCatalog.all.size} protocols catalogued · " +
                        "${ProtocolCatalog.directlyScannable.size} scannable from this phone · " +
                        "${ProtocolCatalog.hubOnly.size} require Homey Pro",
                    style = MaterialTheme.typography.bodyMedium,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )
                Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    TextButton(onClick = { viewModel.setAllProtocols(true) }) { Text("Enable all") }
                    TextButton(onClick = { viewModel.setAllProtocols(false) }) { Text("Disable all") }
                }
            }
        }

        ProtocolCatalog.byFamily.forEach { (family, protocols) ->
            item(key = "family-${family.name}") {
                FamilyHeader(
                    family = family,
                    protocols = protocols,
                    counts = counts,
                    enabledCount = protocols.count { it in enabled },
                    expanded = expandedFamily == family,
                    onToggle = {
                        expandedFamily = if (expandedFamily == family) null else family
                    },
                )
            }

            if (expandedFamily == family) {
                items(protocols, key = { it.name }) { protocol ->
                    ProtocolRow(
                        protocol = protocol,
                        deviceCount = counts[protocol] ?: 0,
                        enabled = protocol in enabled,
                        onToggle = { viewModel.toggleProtocol(protocol, it) },
                        onShowDevices = {
                            viewModel.setProtocolFilter(protocol)
                            onShowDevices()
                        },
                    )
                }
            }
        }

        item {
            HubExplainer(isHomeyConnected = state.settings.isHomeyConfigured)
        }
    }
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
private fun FamilyHeader(
    family: ProtocolFamily,
    protocols: List<Protocol>,
    counts: Map<Protocol, Int>,
    enabledCount: Int,
    expanded: Boolean,
    onToggle: () -> Unit,
) {
    val found = protocols.count { (counts[it] ?: 0) > 0 }

    Surface(
        onClick = onToggle,
        shape = RoundedCornerShape(14.dp),
        color = if (expanded) {
            MaterialTheme.colorScheme.surfaceContainerHigh
        } else {
            MaterialTheme.colorScheme.surfaceContainer
        },
        modifier = Modifier.fillMaxWidth(),
    ) {
        Row(
            modifier = Modifier.padding(horizontal = 14.dp, vertical = 12.dp),
            verticalAlignment = Alignment.CenterVertically,
            horizontalArrangement = Arrangement.spacedBy(12.dp),
        ) {
            Column(modifier = Modifier.weight(1f)) {
                Text(text = family.displayName, style = MaterialTheme.typography.titleMedium)
                Text(
                    text = "${protocols.size} protocols · $enabledCount enabled" +
                        if (found > 0) " · $found detected here" else "",
                    style = MaterialTheme.typography.bodyMedium,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )
            }
            Text(
                text = if (expanded) "Hide" else "Show",
                style = MaterialTheme.typography.labelLarge,
                color = MaterialTheme.colorScheme.primary,
            )
        }
    }
}

@Composable
private fun ProtocolRow(
    protocol: Protocol,
    deviceCount: Int,
    enabled: Boolean,
    onToggle: (Boolean) -> Unit,
    onShowDevices: () -> Unit,
) {
    val statusColours = LocalStatusColours.current
    val isBridged = protocol.reachability == Reachability.HUB_BRIDGED

    Surface(
        shape = RoundedCornerShape(14.dp),
        color = MaterialTheme.colorScheme.surfaceContainerLow,
        modifier = Modifier
            .fillMaxWidth()
            .padding(start = 12.dp),
    ) {
        Row(
            modifier = Modifier.padding(horizontal = 14.dp, vertical = 12.dp),
            verticalAlignment = Alignment.CenterVertically,
            horizontalArrangement = Arrangement.spacedBy(12.dp),
        ) {
            Icon(
                imageVector = when {
                    isBridged -> Icons.Outlined.Hub
                    deviceCount > 0 -> Icons.Outlined.CheckCircle
                    else -> Icons.Outlined.RadioButtonUnchecked
                },
                contentDescription = null,
                tint = when {
                    isBridged -> statusColours.bridged
                    deviceCount > 0 -> statusColours.online
                    else -> MaterialTheme.colorScheme.outline
                },
                modifier = Modifier.size(20.dp),
            )

            Column(modifier = Modifier.weight(1f)) {
                Row(
                    verticalAlignment = Alignment.CenterVertically,
                    horizontalArrangement = Arrangement.spacedBy(8.dp),
                ) {
                    Text(
                        text = protocol.displayName,
                        style = MaterialTheme.typography.titleMedium,
                    )
                    if (deviceCount > 0) {
                        Text(
                            text = "$deviceCount found",
                            style = MaterialTheme.typography.labelMedium,
                            color = statusColours.online,
                        )
                    }
                }
                protocol.aka?.let {
                    Text(
                        text = it,
                        style = MaterialTheme.typography.labelMedium,
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                    )
                }
                Text(
                    text = protocol.summary,
                    style = MaterialTheme.typography.bodyMedium,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )
                Row(
                    modifier = Modifier.padding(top = 4.dp),
                    horizontalArrangement = Arrangement.spacedBy(10.dp),
                ) {
                    Text(
                        text = protocol.reachability.label,
                        style = MaterialTheme.typography.labelSmall,
                        color = if (isBridged) statusColours.bridged else MaterialTheme.colorScheme.primary,
                    )
                    if (protocol.ports.isNotEmpty()) {
                        Text(
                            text = "Ports ${protocol.ports.joinToString(", ")}",
                            style = MaterialTheme.typography.labelSmall,
                            color = MaterialTheme.colorScheme.onSurfaceVariant,
                        )
                    }
                }
                if (deviceCount > 0) {
                    TextButton(
                        onClick = onShowDevices,
                        modifier = Modifier.padding(top = 2.dp),
                    ) {
                        Text("Show these devices")
                    }
                }
            }

            Switch(checked = enabled, onCheckedChange = onToggle)
        }
    }
}

@Composable
private fun HubExplainer(isHomeyConnected: Boolean) {
    Surface(
        shape = RoundedCornerShape(16.dp),
        color = MaterialTheme.colorScheme.secondaryContainer,
        modifier = Modifier.fillMaxWidth(),
    ) {
        Column(
            modifier = Modifier.padding(16.dp),
            verticalArrangement = Arrangement.spacedBy(8.dp),
        ) {
            SectionHeader(title = "Why some protocols need Homey")
            Text(
                text = "An Android handset has Wi-Fi, Bluetooth and NFC radios — and that is all. " +
                    "Zigbee, Z-Wave, Thread end devices, 433/868 MHz, infrared, EnOcean and " +
                    "powerline protocols like X10 and Insteon are physically unreachable from a " +
                    "phone, no matter what software is installed.",
                style = MaterialTheme.typography.bodyMedium,
                color = MaterialTheme.colorScheme.onSecondaryContainer,
            )
            Text(
                text = if (isHomeyConnected) {
                    "Homey Pro is connected, so those devices appear in your inventory with full " +
                        "controls alongside everything found directly."
                } else {
                    "Connect Homey Pro on the Homey tab and its radios become this app's radios: " +
                        "every bridged device joins the same inventory, searchable and controllable."
                },
                style = MaterialTheme.typography.bodyMedium,
                color = MaterialTheme.colorScheme.onSecondaryContainer,
            )
        }
    }
}
