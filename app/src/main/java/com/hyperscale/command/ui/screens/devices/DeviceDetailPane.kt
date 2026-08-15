package com.hyperscale.command.ui.screens.devices

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ExperimentalLayoutApi
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Star
import androidx.compose.material.icons.outlined.Close
import androidx.compose.material.icons.outlined.Delete
import androidx.compose.material.icons.outlined.Edit
import androidx.compose.material.icons.outlined.StarBorder
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
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
import androidx.compose.ui.draw.clip
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import com.hyperscale.command.core.model.Device
import com.hyperscale.command.core.model.Reachability
import com.hyperscale.command.ui.HyperscaleViewModel
import com.hyperscale.command.ui.components.CapabilityControl
import com.hyperscale.command.ui.components.ProtocolChip
import com.hyperscale.command.ui.components.SectionHeader
import com.hyperscale.command.ui.components.StatusPill
import com.hyperscale.command.ui.components.icon
import com.hyperscale.command.ui.theme.LocalStatusColours
import java.text.DateFormat
import java.util.Date

/**
 * Everything known about one device, and everything that can be done to it.
 *
 * The ordering is deliberate: controls first (what you came here to do), then identity, then the
 * raw evidence that produced that identity. That last section matters in a mixed-brand house —
 * when the app guesses a device wrong, the user can see exactly which TXT record or SSDP header
 * led it astray.
 */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun DeviceDetailPane(
    device: Device,
    viewModel: HyperscaleViewModel,
    onClose: () -> Unit,
    modifier: Modifier = Modifier,
) {
    var showRename by remember(device.id) { mutableStateOf(false) }
    var showForget by remember(device.id) { mutableStateOf(false) }

    LazyColumn(
        modifier = modifier,
        contentPadding = PaddingValues(horizontal = 20.dp, vertical = 16.dp),
        verticalArrangement = Arrangement.spacedBy(18.dp),
    ) {
        item { DetailHeader(device, viewModel, onClose, onRename = { showRename = true }) }

        if (device.capabilities.isNotEmpty()) {
            item { SectionHeader(title = "Controls", trailing = "via Homey Pro") }
            items(device.capabilities, key = { it.id }) { capability ->
                CapabilityControl(
                    capability = capability,
                    enabled = device.homeyDeviceId != null,
                    onSetBoolean = { viewModel.setCapability(device, capability.id, it) },
                    onSetNumber = { viewModel.setCapability(device, capability.id, it) },
                    onSetString = { viewModel.setCapability(device, capability.id, it) },
                )
            }
        } else if (device.primaryProtocol.reachability == Reachability.HUB_BRIDGED) {
            item { BridgedNotice(device) }
        }

        item { SectionHeader(title = "Protocols") }
        item { ProtocolSection(device) }

        item { SectionHeader(title = "Identity") }
        item { IdentitySection(device) }

        if (device.attributes.isNotEmpty()) {
            item {
                SectionHeader(
                    title = "Discovery evidence",
                    trailing = "${device.attributes.size} facts",
                )
            }
            item { EvidenceSection(device) }
        }

        item {
            TextButton(onClick = { showForget = true }) {
                Icon(Icons.Outlined.Delete, contentDescription = null, modifier = Modifier.size(18.dp))
                Text("  Forget this device", color = MaterialTheme.colorScheme.error)
            }
        }
    }

    if (showRename) {
        RenameDialog(
            device = device,
            onDismiss = { showRename = false },
            onConfirm = { newName ->
                viewModel.renameDevice(device, newName)
                showRename = false
            },
        )
    }

    if (showForget) {
        AlertDialog(
            onDismissRequest = { showForget = false },
            title = { Text("Forget ${device.displayName}?") },
            text = {
                Text(
                    "It will disappear from your inventory along with its nickname. If it is " +
                        "still on the network, the next scan will find it again as a new device.",
                )
            },
            confirmButton = {
                TextButton(
                    onClick = {
                        showForget = false
                        viewModel.forgetDevice(device)
                    },
                ) {
                    Text("Forget", color = MaterialTheme.colorScheme.error)
                }
            },
            dismissButton = {
                TextButton(onClick = { showForget = false }) { Text("Cancel") }
            },
        )
    }
}

@Composable
private fun DetailHeader(
    device: Device,
    viewModel: HyperscaleViewModel,
    onClose: () -> Unit,
    onRename: () -> Unit,
) {
    val statusColours = LocalStatusColours.current

    Column(verticalArrangement = Arrangement.spacedBy(12.dp)) {
        Row(
            modifier = Modifier.fillMaxWidth(),
            horizontalArrangement = Arrangement.spacedBy(14.dp),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            Box(
                modifier = Modifier
                    .size(56.dp)
                    .clip(CircleShape)
                    .background(
                        if (device.isOn == true) {
                            statusColours.controllable.copy(alpha = 0.2f)
                        } else {
                            MaterialTheme.colorScheme.surfaceContainerHighest
                        },
                    ),
                contentAlignment = Alignment.Center,
            ) {
                Icon(
                    imageVector = device.deviceClass.icon(),
                    contentDescription = null,
                    tint = if (device.isOn == true) {
                        statusColours.controllable
                    } else {
                        MaterialTheme.colorScheme.onSurfaceVariant
                    },
                    modifier = Modifier.size(26.dp),
                )
            }

            Column(modifier = Modifier.weight(1f)) {
                Text(
                    text = device.displayName,
                    style = MaterialTheme.typography.headlineSmall,
                    maxLines = 2,
                    overflow = TextOverflow.Ellipsis,
                )
                Text(
                    text = "${device.deviceClass.label}${device.homeyZoneName?.let { " · $it" } ?: ""}",
                    style = MaterialTheme.typography.bodyMedium,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )
            }

            IconButton(onClick = { viewModel.setFavourite(device, !device.isFavourite) }) {
                Icon(
                    imageVector = if (device.isFavourite) Icons.Filled.Star else Icons.Outlined.StarBorder,
                    contentDescription = "Favourite",
                    tint = if (device.isFavourite) {
                        MaterialTheme.colorScheme.tertiary
                    } else {
                        MaterialTheme.colorScheme.onSurfaceVariant
                    },
                )
            }
            IconButton(onClick = onRename) {
                Icon(Icons.Outlined.Edit, contentDescription = "Rename")
            }
            IconButton(onClick = onClose) {
                Icon(Icons.Outlined.Close, contentDescription = "Close")
            }
        }

        Row(
            horizontalArrangement = Arrangement.spacedBy(8.dp),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            StatusPill(status = device.status)
            device.rssi?.let {
                Text(
                    text = "$it dBm",
                    style = MaterialTheme.typography.labelMedium,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )
            }
        }
    }
}

@OptIn(ExperimentalLayoutApi::class)
@Composable
private fun ProtocolSection(device: Device) {
    Column(verticalArrangement = Arrangement.spacedBy(10.dp)) {
        FlowRow(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            device.protocols.forEach { protocol ->
                ProtocolChip(protocol = protocol)
            }
        }

        device.protocols.firstOrNull()?.let { primary ->
            Surface(
                shape = RoundedCornerShape(12.dp),
                color = MaterialTheme.colorScheme.surfaceContainerLow,
                modifier = Modifier.fillMaxWidth(),
            ) {
                Column(
                    modifier = Modifier.padding(12.dp),
                    verticalArrangement = Arrangement.spacedBy(4.dp),
                ) {
                    Text(
                        text = primary.displayName + primary.aka?.let { " ($it)" }.orEmpty(),
                        style = MaterialTheme.typography.titleMedium,
                    )
                    Text(
                        text = primary.summary,
                        style = MaterialTheme.typography.bodyMedium,
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                    )
                    Text(
                        text = "${primary.family.displayName} · ${primary.reachability.label}",
                        style = MaterialTheme.typography.labelMedium,
                        color = MaterialTheme.colorScheme.primary,
                    )
                }
            }
        }
    }
}

@Composable
private fun IdentitySection(device: Device) {
    val dateFormat = remember { DateFormat.getDateTimeInstance(DateFormat.MEDIUM, DateFormat.SHORT) }

    val rows = buildList {
        device.manufacturer?.let { add("Manufacturer" to it) }
        device.model?.let { add("Model" to it) }
        device.firmwareVersion?.let { add("Firmware" to it) }
        device.serialNumber?.let { add("Serial" to it) }
        device.ipAddress?.let { add("IP address" to it) }
        device.macAddress?.let { add("MAC address" to it) }
        device.hostname?.let { add("Hostname" to it) }
        device.homeyDeviceId?.let { add("Homey device" to it) }
        device.homeyZoneName?.let { add("Zone" to it) }
        add("Seen via" to device.sources.joinToString(", ") { it.label })
        if (device.firstSeenMillis > 0) {
            add("First seen" to dateFormat.format(Date(device.firstSeenMillis)))
        }
        if (device.lastSeenMillis > 0) {
            add("Last seen" to dateFormat.format(Date(device.lastSeenMillis)))
        }
    }

    KeyValueCard(rows)
}

@Composable
private fun EvidenceSection(device: Device) {
    KeyValueCard(device.attributes.entries.map { it.key to it.value }.sortedBy { it.first })
}

@Composable
private fun KeyValueCard(rows: List<Pair<String, String>>) {
    Surface(
        shape = RoundedCornerShape(14.dp),
        color = MaterialTheme.colorScheme.surfaceContainerLow,
        modifier = Modifier.fillMaxWidth(),
    ) {
        Column(
            modifier = Modifier.padding(horizontal = 14.dp, vertical = 10.dp),
            verticalArrangement = Arrangement.spacedBy(8.dp),
        ) {
            rows.forEach { (key, value) ->
                Row(modifier = Modifier.fillMaxWidth()) {
                    Text(
                        text = key,
                        style = MaterialTheme.typography.bodyMedium,
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                        modifier = Modifier.weight(0.42f),
                    )
                    Text(
                        text = value,
                        style = MaterialTheme.typography.bodyMedium,
                        color = MaterialTheme.colorScheme.onSurface,
                        modifier = Modifier.weight(0.58f),
                    )
                }
            }
        }
    }
}

/**
 * Shown for devices that exist only behind a hub. Explains honestly why there are no controls
 * rather than leaving an empty section, which would read as a bug.
 */
@Composable
private fun BridgedNotice(device: Device) {
    Surface(
        shape = RoundedCornerShape(14.dp),
        color = MaterialTheme.colorScheme.secondaryContainer,
        modifier = Modifier.fillMaxWidth(),
    ) {
        Column(
            modifier = Modifier.padding(14.dp),
            verticalArrangement = Arrangement.spacedBy(6.dp),
        ) {
            Text(
                text = "Reachable only through a hub",
                style = MaterialTheme.typography.titleMedium,
                color = MaterialTheme.colorScheme.onSecondaryContainer,
            )
            Text(
                text = "${device.primaryProtocol.displayName} needs a radio this phone does not " +
                    "have. Connect Homey Pro on the Homey tab and this device gains full controls.",
                style = MaterialTheme.typography.bodyMedium,
                color = MaterialTheme.colorScheme.onSecondaryContainer,
            )
        }
    }
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
private fun RenameDialog(
    device: Device,
    onDismiss: () -> Unit,
    onConfirm: (String?) -> Unit,
) {
    var text by remember { mutableStateOf(device.nickname ?: device.name) }

    AlertDialog(
        onDismissRequest = onDismiss,
        title = { Text("Rename device") },
        text = {
            Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                OutlinedTextField(
                    value = text,
                    onValueChange = { text = it },
                    singleLine = true,
                    label = { Text("Name") },
                )
                Text(
                    text = "Discovered name: ${device.name}",
                    style = MaterialTheme.typography.labelMedium,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )
            }
        },
        confirmButton = {
            TextButton(onClick = { onConfirm(text.takeIf { it.isNotBlank() }) }) { Text("Save") }
        },
        dismissButton = {
            TextButton(onClick = { onConfirm(null) }) { Text("Reset") }
        },
    )
}
