package com.hyperscale.command.ui.screens.settings

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.FilterChip
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Surface
import androidx.compose.material3.Switch
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import com.hyperscale.command.discovery.ScanDepth
import com.hyperscale.command.discovery.ScannerAvailability
import com.hyperscale.command.ui.HyperscaleUiState
import com.hyperscale.command.ui.HyperscaleViewModel
import com.hyperscale.command.ui.components.SectionHeader

/**
 * Settings, plus a diagnostics panel.
 *
 * The scanner status list is the important half: when discovery underperforms it is almost always
 * because Bluetooth is off, a permission was declined, or the phone is on mobile data. Surfacing
 * each scanner's real state turns "the app doesn't work" into "oh, Bluetooth is off".
 */
@Composable
fun SettingsScreen(
    state: HyperscaleUiState,
    viewModel: HyperscaleViewModel,
    modifier: Modifier = Modifier,
) {
    val availability = viewModel.scannerAvailability()

    LazyColumn(
        modifier = modifier.fillMaxSize(),
        contentPadding = PaddingValues(horizontal = 20.dp, vertical = 16.dp),
        verticalArrangement = Arrangement.spacedBy(16.dp),
    ) {
        item { Text("Settings", style = MaterialTheme.typography.headlineMedium) }

        item { SectionHeader(title = "Scanning") }

        item {
            SettingCard {
                Text("Default scan depth", style = MaterialTheme.typography.titleMedium)
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
            }
        }

        item {
            ToggleRow(
                title = "Scan on launch",
                subtitle = "Start a discovery pass as soon as the app opens.",
                checked = state.settings.scanOnLaunch,
                onCheckedChange = viewModel::setScanOnLaunch,
            )
        }

        item {
            ToggleRow(
                title = "Show offline devices",
                subtitle = "Keep devices in the list after they stop responding.",
                checked = state.settings.showOfflineDevices,
                onCheckedChange = viewModel::setShowOfflineDevices,
            )
        }

        item { SectionHeader(title = "Appearance") }

        item {
            ToggleRow(
                title = "Use wallpaper colours",
                subtitle = "Match Material You. Turn off for Hyperscale's own instrument palette, " +
                    "which keeps status colours maximally distinct.",
                checked = state.settings.useDynamicColour,
                onCheckedChange = viewModel::setUseDynamicColour,
            )
        }

        item { SectionHeader(title = "Scanner diagnostics") }

        item {
            SettingCard {
                availability.forEach { (id, status) ->
                    Row(
                        modifier = Modifier.fillMaxWidth(),
                        horizontalArrangement = Arrangement.SpaceBetween,
                        verticalAlignment = Alignment.Top,
                    ) {
                        Text(
                            text = id.replaceFirstChar { it.uppercase() },
                            style = MaterialTheme.typography.bodyLarge,
                            modifier = Modifier.weight(0.35f),
                        )
                        Text(
                            text = status.describe(),
                            style = MaterialTheme.typography.bodyMedium,
                            color = when (status) {
                                is ScannerAvailability.Ready -> MaterialTheme.colorScheme.primary
                                else -> MaterialTheme.colorScheme.onSurfaceVariant
                            },
                            modifier = Modifier.weight(0.65f),
                        )
                    }
                }
            }
        }

        item { SectionHeader(title = "About") }

        item {
            SettingCard {
                Text(
                    text = "Hyperscale Command",
                    style = MaterialTheme.typography.titleMedium,
                )
                Text(
                    text = "A multi-protocol discovery and control console for mixed-brand homes, " +
                        "built for the Galaxy Z Fold's inner display and bridged to Homey Pro for " +
                        "everything a phone's radios cannot reach.",
                    style = MaterialTheme.typography.bodyMedium,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )
                Text(
                    text = "${state.devices.size} devices tracked · " +
                        "${state.protocolCounts.size} protocols observed",
                    style = MaterialTheme.typography.labelMedium,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )
            }
        }
    }
}

@Composable
private fun SettingCard(content: @Composable () -> Unit) {
    Surface(
        shape = RoundedCornerShape(16.dp),
        color = MaterialTheme.colorScheme.surfaceContainer,
        modifier = Modifier.fillMaxWidth(),
    ) {
        Column(
            modifier = Modifier.padding(16.dp),
            verticalArrangement = Arrangement.spacedBy(10.dp),
        ) {
            content()
        }
    }
}

@Composable
private fun ToggleRow(
    title: String,
    subtitle: String,
    checked: Boolean,
    onCheckedChange: (Boolean) -> Unit,
) {
    SettingCard {
        Row(
            modifier = Modifier.fillMaxWidth(),
            verticalAlignment = Alignment.CenterVertically,
            horizontalArrangement = Arrangement.spacedBy(12.dp),
        ) {
            Column(modifier = Modifier.weight(1f)) {
                Text(text = title, style = MaterialTheme.typography.titleMedium)
                Text(
                    text = subtitle,
                    style = MaterialTheme.typography.bodyMedium,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )
            }
            Switch(checked = checked, onCheckedChange = onCheckedChange)
        }
    }
}

private fun ScannerAvailability.describe(): String = when (this) {
    is ScannerAvailability.Ready -> "Ready"
    is ScannerAvailability.NeedsPermission -> "Needs permission — $rationale"
    is ScannerAvailability.Unavailable -> reason
}
