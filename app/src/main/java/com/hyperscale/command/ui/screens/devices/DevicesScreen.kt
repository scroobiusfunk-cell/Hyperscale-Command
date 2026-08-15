package com.hyperscale.command.ui.screens.devices

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.LazyRow
import androidx.compose.foundation.lazy.items
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.outlined.Close
import androidx.compose.material.icons.outlined.DevicesOther
import androidx.compose.material.icons.outlined.Search
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.FilterChip
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import com.hyperscale.command.ui.HyperscaleUiState
import com.hyperscale.command.ui.HyperscaleViewModel
import com.hyperscale.command.ui.WindowWidth
import com.hyperscale.command.ui.adaptive.FoldState
import com.hyperscale.command.ui.adaptive.HingeAwareTwoPane
import com.hyperscale.command.ui.components.DeviceCard
import com.hyperscale.command.ui.components.EmptyState
import com.hyperscale.command.ui.components.icon

/**
 * The full device inventory, with search and filters.
 *
 * On a wide window this is a list-detail pair: tapping a device fills the second pane without
 * losing the list, which on a Fold's inner screen means the user can work through a dozen devices
 * without a single navigation transition. On a narrow window the detail takes over the screen and
 * the system back gesture returns to the list.
 */
@Composable
fun DevicesScreen(
    state: HyperscaleUiState,
    foldState: FoldState,
    widthClass: WindowWidth,
    viewModel: HyperscaleViewModel,
    modifier: Modifier = Modifier,
) {
    val selected = state.selectedDevice

    if (widthClass == WindowWidth.COMPACT) {
        if (selected != null) {
            DeviceDetailPane(
                device = selected,
                viewModel = viewModel,
                onClose = { viewModel.selectDevice(null) },
                modifier = modifier.fillMaxSize(),
            )
        } else {
            DeviceListPane(
                state = state,
                viewModel = viewModel,
                modifier = modifier.fillMaxSize(),
            )
        }
        return
    }

    HingeAwareTwoPane(
        foldState = foldState,
        modifier = modifier.fillMaxSize(),
        firstPaneWeight = 0.42f,
        first = {
            DeviceListPane(
                state = state,
                viewModel = viewModel,
                modifier = Modifier.fillMaxSize(),
            )
        },
        second = {
            if (selected != null) {
                DeviceDetailPane(
                    device = selected,
                    viewModel = viewModel,
                    onClose = { viewModel.selectDevice(null) },
                    modifier = Modifier.fillMaxSize(),
                )
            } else {
                EmptyState(
                    icon = Icons.Outlined.DevicesOther,
                    title = "Select a device",
                    body = "Pick anything from the list to see every protocol it speaks, the " +
                        "evidence behind its identity, and any controls Homey exposes for it.",
                    modifier = Modifier.fillMaxSize(),
                )
            }
        },
    )
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
private fun DeviceListPane(
    state: HyperscaleUiState,
    viewModel: HyperscaleViewModel,
    modifier: Modifier = Modifier,
) {
    Column(modifier = modifier) {
        Column(
            modifier = Modifier.padding(horizontal = 20.dp, vertical = 12.dp),
            verticalArrangement = Arrangement.spacedBy(12.dp),
        ) {
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.SpaceBetween,
                verticalAlignment = Alignment.CenterVertically,
            ) {
                Text(text = "Devices", style = MaterialTheme.typography.headlineMedium)
                Text(
                    text = "${state.filteredDevices.size} of ${state.devices.size}",
                    style = MaterialTheme.typography.labelMedium,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )
            }

            OutlinedTextField(
                value = state.filter.query,
                onValueChange = viewModel::setQuery,
                modifier = Modifier.fillMaxWidth(),
                singleLine = true,
                leadingIcon = { Icon(Icons.Outlined.Search, contentDescription = null) },
                trailingIcon = {
                    if (state.filter.isActive) {
                        IconButton(onClick = viewModel::clearFilters) {
                            Icon(Icons.Outlined.Close, contentDescription = "Clear filters")
                        }
                    }
                },
                placeholder = { Text("Name, IP, MAC, vendor, protocol…") },
            )

            FilterRow(state = state, viewModel = viewModel)
        }

        if (state.filteredDevices.isEmpty()) {
            EmptyState(
                icon = Icons.Outlined.DevicesOther,
                title = if (state.devices.isEmpty()) "No devices yet" else "Nothing matches",
                body = if (state.devices.isEmpty()) {
                    "Run a scan from the Discover tab to populate your inventory."
                } else {
                    "No device matches the current filters. Clear them to see all " +
                        "${state.devices.size} devices."
                },
                modifier = Modifier.fillMaxSize(),
            )
            return@Column
        }

        LazyColumn(
            modifier = Modifier.fillMaxSize(),
            contentPadding = PaddingValues(start = 20.dp, end = 20.dp, bottom = 24.dp),
            verticalArrangement = Arrangement.spacedBy(10.dp),
        ) {
            items(state.filteredDevices, key = { it.id }) { device ->
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
}

/**
 * Quick filters. Ordered by how often they get used rather than alphabetically: favourites and
 * controllable first, then whichever device classes are actually present in this house.
 */
@Composable
private fun FilterRow(
    state: HyperscaleUiState,
    viewModel: HyperscaleViewModel,
) {
    val presentClasses = state.devices
        .map { it.deviceClass }
        .distinct()
        .sortedBy { it.ordinal }

    LazyRow(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
        item {
            FilterChip(
                selected = state.filter.onlyFavourites,
                onClick = viewModel::toggleFavouritesOnly,
                label = { Text("Favourites") },
            )
        }
        item {
            FilterChip(
                selected = state.filter.onlyControllable,
                onClick = viewModel::toggleControllableOnly,
                label = { Text("Controllable") },
            )
        }
        items(presentClasses, key = { it.name }) { deviceClass ->
            val isSelected = state.filter.deviceClass == deviceClass
            FilterChip(
                selected = isSelected,
                onClick = {
                    viewModel.setDeviceClassFilter(if (isSelected) null else deviceClass)
                },
                label = { Text(deviceClass.label) },
                leadingIcon = {
                    Icon(
                        imageVector = deviceClass.icon(),
                        contentDescription = null,
                        modifier = Modifier.padding(1.dp),
                    )
                },
            )
        }
    }
}
